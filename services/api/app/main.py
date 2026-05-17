import logging
import uuid
from collections import Counter
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.dq_service import execute_annotation_qa_run, execute_bias_run, execute_dirty_data_run, execute_staleness_drift_run
from app.logging_config import configure_logging
from app.llm.provider import get_model_profiles
from app.llm.rag_chain import run_rag_ask
from app.models import (
    DQEvent,
    DQMetric,
    DQResult,
    DQRun,
    Dataset,
    DatasetVersion,
    EvalRun,
    EvalScore,
    Feedback,
    LLMOpsRunLink,
    QualityGateResult,
    RequestLog,
    ResponseLog,
    TraceEvent,
    AuditEvent,
)
from app.observability import (
    metrics_payload,
    observe_eval_run,
    observe_feedback,
    observe_metric_value,
    observe_quality_gate,
    observe_readiness,
    observe_run_status,
    observe_runtime_dq,
)
from app.observability_tools.langfuse_client import LangfuseContractClient
from app.observability_tools.mlflow_client import MLflowEvalRunContract, MLflowTrackingClient
from app.retrieval.milvus_client import MilvusContractClient, MilvusSearchRequest, MilvusUpsertRequest
from app.schemas import (
    AskRequest,
    AskResponse,
    AuditEventRead,
    DQEventRead,
    FeedbackCreate,
    FeedbackRead,
    GateDecisionRead,
    LLMOpsRunLinkCreate,
    LLMOpsRunLinkRead,
    DQMetricRead,
    DQResultsLatestRead,
    DQResultRead,
    DQRunCreate,
    DQRunRead,
    DQRunSummaryRead,
    DatasetCreate,
    DatasetRead,
    DatasetVersionCreate,
    DatasetVersionRead,
    EvalRunRead,
    EvalScoreRead,
    HealthResponse,
    IntegrationContractsRead,
    IntegrationStatusRead,
    LLMOpsReadinessRead,
    ModelProfileRead,
    ModelsResponse,
    QualityGateResultRead,
    TraceListRead,
    TraceSummaryRead,
    TraceEventRead,
)
from app.security import build_api_key_middleware, contains_pii, hash_user_id, mask_pii, record_audit_event

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info(
        "starting_api",
        extra={
            "app_name": settings.app_name,
            "app_env": settings.app_env,
            "default_data_contour": settings.default_data_contour,
        },
    )
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.middleware("http")(build_api_key_middleware(settings))


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        app_env=settings.app_env,
    )


@app.get("/metrics", response_class=PlainTextResponse)
def metrics() -> PlainTextResponse:
    return PlainTextResponse(metrics_payload().decode("utf-8"))


@app.get("/models", response_model=ModelsResponse)
def list_models() -> ModelsResponse:
    return ModelsResponse(
        default_model_profile_id=settings.default_model_profile_id,
        models=[
            ModelProfileRead(
                id=profile.id,
                label=profile.label,
                provider=profile.provider,
                model_name=profile.model_name,
                enabled=profile.enabled,
                status=profile.status,
                reason=profile.reason,
                description=profile.description,
                details=profile.details or {},
            )
            for profile in get_model_profiles(settings)
        ],
    )


@app.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest, db: Session = Depends(get_db)) -> dict:
    response = run_rag_ask(db, payload, settings)
    trace_id = response["trace_id"]
    user_id_hash = hash_user_id(payload.user_id)
    if contains_pii({"query": payload.query, "attachments": payload.attachments}):
        record_audit_event(
            db,
            "pii_masked",
            trace_id=trace_id,
            user_id_hash=user_id_hash,
            details={"fields": ["query", "attachments"], "masked_input": {"query": payload.query}},
        )
    record_audit_event(
        db,
        "input_output_audit",
        trace_id=trace_id,
        user_id_hash=user_id_hash,
        details={
            "request_id": str(response["request_id"]),
            "locale": payload.locale,
            "query": payload.query,
            "answer": response["answer"],
            "status": response["status"],
            "score_keys": sorted(response["scores"].keys()),
        },
    )
    return response


@app.post("/feedback", response_model=FeedbackRead, status_code=201)
def create_feedback(payload: FeedbackCreate, db: Session = Depends(get_db)) -> Feedback:
    masked_payload = payload.model_dump()
    if masked_payload.get("comment") is not None:
        masked_payload["comment"] = mask_pii(masked_payload["comment"])
    masked_payload["payload"] = mask_pii(masked_payload.get("payload", {}))
    feedback = Feedback(**masked_payload)
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    if contains_pii(payload.model_dump()):
        record_audit_event(
            db,
            "pii_masked",
            trace_id=feedback.trace_id,
            details={"fields": ["comment", "payload"], "source": "feedback"},
        )
    observe_feedback(feedback.rating)
    return feedback


@app.get("/audit/events", response_model=list[AuditEventRead])
def list_audit_events(
    event_type: str | None = Query(default=None),
    trace_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[AuditEvent]:
    stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
    if event_type:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    if trace_id:
        stmt = stmt.where(AuditEvent.trace_id == trace_id)
    return list(db.scalars(stmt).all())


@app.get("/trace/{trace_id}", response_model=list[TraceEventRead])
def get_trace(trace_id: str, db: Session = Depends(get_db)) -> list[TraceEvent]:
    events = list(
        db.scalars(
            select(TraceEvent).where(TraceEvent.trace_id == trace_id).order_by(TraceEvent.created_at.asc())
        ).all()
    )
    if not events:
        raise HTTPException(status_code=404, detail="trace not found")
    return events


@app.get("/traces", response_model=TraceListRead)
def list_traces(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)) -> TraceListRead:
    requests = list(db.scalars(select(RequestLog).order_by(RequestLog.created_at.desc()).limit(limit)).all())
    trace_summaries: list[TraceSummaryRead] = []
    for request in requests:
        response = db.scalar(
            select(ResponseLog).where(ResponseLog.request_id == request.id).order_by(ResponseLog.created_at.desc())
        )
        payload = response.payload if response is not None and isinstance(response.payload, dict) else {}
        trace_summaries.append(
            TraceSummaryRead(
                trace_id=request.trace_id,
                request_id=request.id,
                created_at=request.created_at,
                status=response.status if response is not None else request.status,
                model_name=_safe_string(payload.get("model_name")),
                model_profile_id=_safe_string(payload.get("model_profile_id")),
                query_preview=_preview(request.query),
            )
        )
    return TraceListRead(traces=trace_summaries)


def _preview(value: str | None, limit: int = 160) -> str:
    if not value:
        return ""
    return value if len(value) <= limit else f"{value[:limit].rstrip()}..."


def _safe_string(value: Any) -> str | None:
    return str(value) if value is not None else None


def _integration_status(raw_status: dict[str, object]) -> IntegrationStatusRead:
    known = {"name", "enabled", "mode", "required_for_mvp", "fallback", "capabilities"}
    return IntegrationStatusRead(
        name=str(raw_status["name"]),
        enabled=bool(raw_status["enabled"]),
        mode=str(raw_status["mode"]),
        required_for_mvp=bool(raw_status["required_for_mvp"]),
        fallback=str(raw_status["fallback"]),
        capabilities=[str(item) for item in raw_status["capabilities"]],  # type: ignore[union-attr]
        details={key: value for key, value in raw_status.items() if key not in known},
    )


@app.get("/integrations", response_model=list[IntegrationStatusRead])
def list_integrations() -> list[IntegrationStatusRead]:
    return [
        _integration_status(MilvusContractClient(settings).status()),
        _integration_status(LangfuseContractClient(settings).status()),
        _integration_status(MLflowTrackingClient(settings).status()),
    ]


@app.get("/integrations/milvus/status", response_model=IntegrationStatusRead)
def get_milvus_status() -> IntegrationStatusRead:
    return _integration_status(MilvusContractClient(settings).status())


@app.get("/integrations/langfuse/status", response_model=IntegrationStatusRead)
def get_langfuse_status() -> IntegrationStatusRead:
    return _integration_status(LangfuseContractClient(settings).status())


@app.get("/integrations/mlflow/status", response_model=IntegrationStatusRead)
def get_mlflow_status() -> IntegrationStatusRead:
    return _integration_status(MLflowTrackingClient(settings).status())


@app.get("/integrations/contracts", response_model=IntegrationContractsRead)
def get_integration_contracts() -> IntegrationContractsRead:
    milvus = MilvusContractClient(settings)
    langfuse = LangfuseContractClient(settings)
    mlflow = MLflowTrackingClient(settings)
    sample_trace_id = uuid.uuid4()
    sample_request_id = uuid.uuid4()
    return IntegrationContractsRead(
        milvus={
            "status": milvus.status(),
            "search": milvus.search_contract(
                MilvusSearchRequest(query="sample question", top_k=settings.rag_top_k, filters={})
            ),
            "upsert": milvus.upsert_contract(
                MilvusUpsertRequest(collection=settings.milvus_collection, vectors=[], payloads=[])
            ),
        },
        langfuse={
            "status": langfuse.status(),
            "trace": langfuse.trace_contract(sample_trace_id, sample_request_id, None),
        },
        mlflow={
            "status": mlflow.status(),
            "eval_run": mlflow.eval_run_contract(
                MLflowEvalRunContract(
                    run_name="sample_eval_run",
                    model_name=f"{settings.llm_provider}:{settings.local_llm_model}",
                    model_version="mock-v1",
                    prompt_version="rag-v1",
                    metrics={"groundedness": 0.0, "relevance": 0.0},
                    artifacts={"eval_results": "mlflow/eval_runs/<run_id>/eval_results.csv"},
                    params={"eval_dataset_version": "not specified", "retrieval_config": {"top_k": settings.rag_top_k}},
                )
            ),
        },
    )


@app.post("/datasets", response_model=DatasetRead, status_code=201)
def create_dataset(payload: DatasetCreate, db: Session = Depends(get_db)) -> Dataset:
    dataset = Dataset(**payload.model_dump())
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return dataset


@app.get("/datasets", response_model=list[DatasetRead])
def list_datasets(db: Session = Depends(get_db)) -> list[Dataset]:
    return list(db.scalars(select(Dataset).order_by(Dataset.created_at.desc())).all())


@app.get("/datasets/{dataset_id}", response_model=DatasetRead)
def get_dataset(dataset_id: str, db: Session = Depends(get_db)) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return dataset


@app.post("/datasets/{dataset_id}/versions", response_model=DatasetVersionRead, status_code=201)
def create_dataset_version(
    dataset_id: str,
    payload: DatasetVersionCreate,
    db: Session = Depends(get_db),
) -> DatasetVersion:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    version = DatasetVersion(dataset_id=dataset.id, **payload.model_dump())
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


@app.post("/dq/run", response_model=DQRunRead, status_code=201)
def create_dq_run(payload: DQRunCreate, db: Session = Depends(get_db)) -> DQRun:
    dataset = db.get(Dataset, payload.dataset_id)
    version = db.get(DatasetVersion, payload.dataset_version_id)
    if dataset is None or version is None:
        raise HTTPException(status_code=404, detail="dataset or version not found")

    run = DQRun(
        dataset_id=payload.dataset_id,
        dataset_version_id=payload.dataset_version_id,
        category=payload.category,
        baseline_id=payload.baseline_id,
        status="queued",
        hard_gate_result="pending",
        soft_gate_result="pending",
        details=payload.details,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    observe_run_status(payload.dataset_id, payload.dataset_version_id, payload.category, run.status)

    if payload.category == "dirty_data" and payload.details.get("execute_immediately", True):
        return execute_dirty_data_run(db, dataset, version, run)
    if payload.category == "staleness_drift" and payload.details.get("execute_immediately", True):
        return execute_staleness_drift_run(db, dataset, version, run)
    if payload.category == "annotation_qa" and payload.details.get("execute_immediately", True):
        return execute_annotation_qa_run(db, dataset, version, run)
    if payload.category == "bias" and payload.details.get("execute_immediately", True):
        return execute_bias_run(db, dataset, version, run)

    return run


@app.get("/dq/runs/{run_id}", response_model=DQRunRead)
def get_dq_run(run_id: str, db: Session = Depends(get_db)) -> DQRun:
    run = db.get(DQRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="dq run not found")
    return run


@app.get("/dq/runs", response_model=list[DQRunRead])
def list_dq_runs(
    dataset_id: str | None = Query(default=None),
    category: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[DQRun]:
    stmt = select(DQRun).order_by(DQRun.created_at.desc()).limit(limit)
    if dataset_id:
        stmt = stmt.where(DQRun.dataset_id == dataset_id)
    if category:
        stmt = stmt.where(DQRun.category == category)
    if status:
        stmt = stmt.where(DQRun.status == status)
    return list(db.scalars(stmt).all())


@app.get("/dq/metrics", response_model=list[DQMetricRead])
def list_dq_metrics(
    dataset_id: str | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[DQMetric]:
    stmt = select(DQMetric).order_by(DQMetric.created_at.desc())
    if dataset_id:
        stmt = stmt.where(DQMetric.dataset_id == dataset_id)
    if category:
        stmt = stmt.where(DQMetric.category == category)
    metrics_result = list(db.scalars(stmt).all())
    for metric in metrics_result:
        observe_metric_value(
            metric.dataset_id,
            metric.dataset_version_id,
            metric.category,
            metric.metric_name,
            metric.status,
            metric.metric_value,
        )
    return metrics_result


@app.get("/dq/events", response_model=list[DQEventRead])
def list_dq_events(
    dataset_id: str | None = Query(default=None),
    category: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    dq_run_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[DQEvent]:
    stmt = select(DQEvent).order_by(DQEvent.created_at.desc()).limit(limit)
    if dataset_id:
        stmt = stmt.where(DQEvent.dataset_id == dataset_id)
    if category:
        stmt = stmt.where(DQEvent.category == category)
    if severity:
        stmt = stmt.where(DQEvent.severity == severity)
    if dq_run_id:
        stmt = stmt.where(DQEvent.dq_run_id == dq_run_id)
    return list(db.scalars(stmt).all())


@app.get("/dq/summary", response_model=list[DQRunSummaryRead])
def list_dq_summaries(
    dataset_id: str | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[DQRunSummaryRead]:
    run_stmt = select(DQRun).order_by(DQRun.created_at.desc())
    if dataset_id:
        run_stmt = run_stmt.where(DQRun.dataset_id == dataset_id)
    if category:
        run_stmt = run_stmt.where(DQRun.category == category)

    runs = list(db.scalars(run_stmt).all())
    latest_by_key: dict[tuple[str, str, str], DQRun] = {}
    for run in runs:
        key = (str(run.dataset_id), str(run.dataset_version_id), run.category)
        if key not in latest_by_key:
            latest_by_key[key] = run

    summaries: list[DQRunSummaryRead] = []
    for _, run in latest_by_key.items():
        metric_rows = list(
            db.scalars(
                select(DQMetric).where(DQMetric.dq_run_id == run.id).order_by(DQMetric.created_at.desc())
            ).all()
        )
        event_rows = list(
            db.scalars(
                select(DQEvent).where(DQEvent.dq_run_id == run.id).order_by(DQEvent.created_at.desc())
            ).all()
        )
        metrics_by_status = dict(Counter(metric.status for metric in metric_rows))
        recent_alerts = [
            {
                "severity": event.severity,
                "status": event.status,
                "metric_name": event.details.get("metric_name"),
                "created_at": event.created_at.isoformat(),
            }
            for event in event_rows[:5]
        ]
        summaries.append(
            DQRunSummaryRead(
                dataset_id=run.dataset_id,
                dataset_version_id=run.dataset_version_id,
                category=run.category,
                latest_run_id=run.id,
                latest_status=run.status,
                hard_gate_result=run.hard_gate_result,
                soft_gate_result=run.soft_gate_result,
                metric_count=len(metric_rows),
                event_count=len(event_rows),
                metrics_by_status=metrics_by_status,
                recent_alerts=recent_alerts,
            )
        )
    return summaries


@app.post("/llmops/mlflow/link", response_model=LLMOpsRunLinkRead, status_code=201)
def create_llmops_run_link(
    payload: LLMOpsRunLinkCreate,
    db: Session = Depends(get_db),
) -> LLMOpsRunLink:
    dataset = db.get(Dataset, payload.dataset_id)
    version = db.get(DatasetVersion, payload.dataset_version_id)
    if dataset is None or version is None:
        raise HTTPException(status_code=404, detail="dataset or version not found")
    if payload.dq_run_id is not None and db.get(DQRun, payload.dq_run_id) is None:
        raise HTTPException(status_code=404, detail="dq run not found")

    link = LLMOpsRunLink(**payload.model_dump())
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@app.get("/llmops/mlflow/links", response_model=list[LLMOpsRunLinkRead])
def list_llmops_run_links(
    dataset_id: str | None = Query(default=None),
    dataset_version_id: str | None = Query(default=None),
    run_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[LLMOpsRunLink]:
    stmt = select(LLMOpsRunLink).order_by(LLMOpsRunLink.created_at.desc())
    if dataset_id:
        stmt = stmt.where(LLMOpsRunLink.dataset_id == dataset_id)
    if dataset_version_id:
        stmt = stmt.where(LLMOpsRunLink.dataset_version_id == dataset_version_id)
    if run_type:
        stmt = stmt.where(LLMOpsRunLink.run_type == run_type)
    return list(db.scalars(stmt).all())


@app.get("/eval/runs", response_model=list[EvalRunRead])
def list_eval_runs(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[EvalRun]:
    stmt = select(EvalRun).order_by(EvalRun.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(EvalRun.status == status)
    eval_runs = list(db.scalars(stmt).all())
    if eval_runs:
        latest = eval_runs[0]
        observe_eval_run(latest.model_name, latest.prompt_version, latest.status, latest.metrics)
    return eval_runs


@app.get("/eval/runs/{eval_run_id}", response_model=EvalRunRead)
def get_eval_run(eval_run_id: str, db: Session = Depends(get_db)) -> EvalRun:
    eval_run = db.get(EvalRun, eval_run_id)
    if eval_run is None:
        raise HTTPException(status_code=404, detail="eval run not found")
    observe_eval_run(eval_run.model_name, eval_run.prompt_version, eval_run.status, eval_run.metrics)
    return eval_run


@app.get("/eval/runs/{eval_run_id}/scores", response_model=list[EvalScoreRead])
def list_eval_scores(
    eval_run_id: str,
    metric_name: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> list[EvalScore]:
    if db.get(EvalRun, eval_run_id) is None:
        raise HTTPException(status_code=404, detail="eval run not found")
    stmt = select(EvalScore).where(EvalScore.eval_run_id == eval_run_id).order_by(EvalScore.created_at.desc()).limit(limit)
    if metric_name:
        stmt = stmt.where(EvalScore.metric_name == metric_name)
    return list(db.scalars(stmt).all())


@app.get("/dq/results", response_model=list[DQResultRead])
def list_runtime_dq_results(
    run_id: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[DQResult]:
    stmt = select(DQResult).order_by(DQResult.created_at.desc()).limit(limit)
    if run_id:
        stmt = stmt.where(DQResult.run_id == run_id)
    if entity_type:
        stmt = stmt.where(DQResult.entity_type == entity_type)
    if status:
        stmt = stmt.where(DQResult.status == status)
    results = list(db.scalars(stmt).all())
    if results:
        current_run_id = results[0].run_id
        failed_count = sum(1 for result in results if result.run_id == current_run_id and result.status == "failed")
        observe_runtime_dq(current_run_id, failed_count)
    return results


@app.get("/dq/results/latest", response_model=DQResultsLatestRead)
def get_latest_runtime_dq_results(db: Session = Depends(get_db)) -> DQResultsLatestRead:
    latest = db.scalar(select(DQResult).where(DQResult.run_id.is_not(None)).order_by(DQResult.created_at.desc()))
    if latest is None or latest.run_id is None:
        return DQResultsLatestRead(
            run_id=None,
            status="unknown",
            check_count=0,
            passed_count=0,
            failed_count=0,
            results=[],
        )
    results = list(
        db.scalars(select(DQResult).where(DQResult.run_id == latest.run_id).order_by(DQResult.created_at.desc())).all()
    )
    failed_count = sum(1 for result in results if result.status == "failed")
    passed_count = sum(1 for result in results if result.status == "passed")
    observe_runtime_dq(latest.run_id, failed_count)
    return DQResultsLatestRead(
        run_id=latest.run_id,
        status="failed" if failed_count else "passed",
        check_count=len(results),
        passed_count=passed_count,
        failed_count=failed_count,
        results=results,
    )


@app.get("/quality-gates", response_model=list[QualityGateResultRead])
def list_quality_gate_results(
    gate_status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[QualityGateResult]:
    stmt = select(QualityGateResult).order_by(QualityGateResult.created_at.desc()).limit(limit)
    if gate_status:
        stmt = stmt.where(QualityGateResult.gate_status == gate_status)
    gates = list(db.scalars(stmt).all())
    if gates:
        observe_quality_gate(gates[0].gate_status)
    return gates


@app.get("/quality-gates/latest", response_model=QualityGateResultRead)
def get_latest_quality_gate(db: Session = Depends(get_db)) -> QualityGateResult:
    gate = db.scalar(select(QualityGateResult).order_by(QualityGateResult.created_at.desc()))
    if gate is None:
        raise HTTPException(status_code=404, detail="quality gate result not found")
    observe_quality_gate(gate.gate_status)
    return gate


@app.get("/llmops/readiness", response_model=LLMOpsReadinessRead)
def get_llmops_readiness(db: Session = Depends(get_db)) -> LLMOpsReadinessRead:
    latest_eval = db.scalar(select(EvalRun).order_by(EvalRun.created_at.desc()))
    latest_gate = db.scalar(select(QualityGateResult).order_by(QualityGateResult.created_at.desc()))
    latest_dq = db.scalar(select(DQResult).where(DQResult.run_id.is_not(None)).order_by(DQResult.created_at.desc()))

    latest_dq_rows: list[DQResult] = []
    if latest_dq and latest_dq.run_id:
        latest_dq_rows = list(
            db.scalars(select(DQResult).where(DQResult.run_id == latest_dq.run_id).order_by(DQResult.created_at.desc())).all()
        )

    failed_signals: list[str] = []
    if latest_eval is None:
        failed_signals.append("eval_run_missing")
    elif latest_eval.status != "completed":
        failed_signals.append("eval_run_not_completed")

    dq_failed_count = sum(1 for row in latest_dq_rows if row.status == "failed")
    if latest_dq is None:
        failed_signals.append("runtime_dq_missing")
    elif dq_failed_count > 0:
        failed_signals.append("runtime_dq_failed")

    if latest_gate is None:
        failed_signals.append("quality_gate_missing")
    elif latest_gate.gate_status != "passed":
        failed_signals.append("quality_gate_failed")

    status = "passed"
    if failed_signals:
        status = "failed" if any(signal.endswith("failed") for signal in failed_signals) else "unknown"

    observe_runtime_dq(latest_dq.run_id if latest_dq is not None else None, dq_failed_count)
    if latest_eval is not None:
        observe_eval_run(latest_eval.model_name, latest_eval.prompt_version, latest_eval.status, latest_eval.metrics)
    if latest_gate is not None:
        observe_quality_gate(latest_gate.gate_status)
    observe_readiness(status)

    return LLMOpsReadinessRead(
        status=status,
        failed_signals=failed_signals,
        latest_eval_run=None
        if latest_eval is None
        else {
            "id": str(latest_eval.id),
            "status": latest_eval.status,
            "metrics": latest_eval.metrics,
            "artifacts": latest_eval.artifacts,
            "created_at": latest_eval.created_at.isoformat(),
        },
        latest_dq_run=None
        if latest_dq is None
        else {
            "run_id": str(latest_dq.run_id),
            "check_count": len(latest_dq_rows),
            "failed_check_count": dq_failed_count,
            "created_at": latest_dq.created_at.isoformat(),
        },
        latest_quality_gate=None
        if latest_gate is None
        else {
            "id": str(latest_gate.id),
            "gate_status": latest_gate.gate_status,
            "failed_checks": latest_gate.failed_checks,
            "metrics_snapshot": latest_gate.metrics_snapshot,
            "created_at": latest_gate.created_at.isoformat(),
        },
        metrics={
            "dq_failed_count": dq_failed_count,
            "dq_check_count": len(latest_dq_rows),
        },
    )


@app.get("/datasets/{dataset_id}/versions/{version_id}/gate", response_model=GateDecisionRead)
def get_dataset_version_gate(
    dataset_id: str,
    version_id: str,
    db: Session = Depends(get_db),
) -> GateDecisionRead:
    dataset = db.get(Dataset, dataset_id)
    version = db.get(DatasetVersion, version_id)
    if dataset is None or version is None:
        raise HTTPException(status_code=404, detail="dataset or version not found")

    runs = list(
        db.scalars(
            select(DQRun)
            .where(DQRun.dataset_id == dataset.id, DQRun.dataset_version_id == version.id)
            .order_by(DQRun.created_at.desc())
        ).all()
    )
    latest_categories: dict[str, dict[str, object]] = {}
    publish_allowed = True
    hard_gate_result: str | None = None
    soft_gate_result: str | None = None
    for run in runs:
        if run.category in latest_categories:
            continue
        latest_categories[run.category] = {
            "dq_run_id": str(run.id),
            "status": run.status,
            "hard_gate_result": run.hard_gate_result,
            "soft_gate_result": run.soft_gate_result,
            "created_at": run.created_at.isoformat(),
        }
        if run.hard_gate_result == "fail":
            publish_allowed = False
        if hard_gate_result is None and run.hard_gate_result:
            hard_gate_result = run.hard_gate_result
        if soft_gate_result is None and run.soft_gate_result:
            soft_gate_result = run.soft_gate_result

    links = list(
        db.scalars(
            select(LLMOpsRunLink)
            .where(
                LLMOpsRunLink.dataset_id == dataset.id,
                LLMOpsRunLink.dataset_version_id == version.id,
            )
            .order_by(LLMOpsRunLink.created_at.desc())
        ).all()
    )
    linked_runs = [
        {
            "external_system": link.external_system,
            "external_run_id": link.external_run_id,
            "run_type": link.run_type,
            "status": link.status,
            "run_name": link.run_name,
            "created_at": link.created_at.isoformat(),
        }
        for link in links
    ]

    return GateDecisionRead(
        dataset_id=dataset.id,
        dataset_version_id=version.id,
        publish_allowed=publish_allowed,
        hard_gate_result=hard_gate_result,
        soft_gate_result=soft_gate_result,
        latest_categories=latest_categories,
        linked_runs=linked_runs,
    )
