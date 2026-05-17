from __future__ import annotations

import json
from pathlib import Path

import yaml
from sqlalchemy import func, select

from app.config import get_settings
from app.db import SessionLocal
from app.models import DQResult, EvalRun, QualityGateResult, ResponseLog


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_thresholds() -> dict:
    settings = get_settings()
    path = Path(settings.quality_thresholds_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def aggregate_response_metrics(responses: list[ResponseLog]) -> dict:
    response_count = len(responses)
    if response_count == 0:
        return {
            "response_count": 0,
            "avg_groundedness": 0.0,
            "avg_relevance": 0.0,
            "avg_citation_correctness": 0.0,
            "avg_safety": 0.0,
            "validation_pass_rate": 0.0,
            "failed_response_rate": 1.0,
        }

    def avg_score(metric_name: str) -> float:
        return round(sum(float(response.scores.get(metric_name, 0.0)) for response in responses) / response_count, 6)

    passed_count = sum(1 for response in responses if response.validation_status == "passed")
    failed_count = sum(1 for response in responses if response.status != "success" or response.validation_status != "passed")
    return {
        "response_count": response_count,
        "avg_groundedness": avg_score("groundedness"),
        "avg_relevance": avg_score("relevance"),
        "avg_citation_correctness": avg_score("citation_correctness"),
        "avg_safety": avg_score("safety"),
        "validation_pass_rate": round(passed_count / response_count, 6),
        "failed_response_rate": round(failed_count / response_count, 6),
    }


def evaluate_latest_response_gate() -> dict:
    settings = get_settings()
    thresholds = load_thresholds()
    with SessionLocal() as db:
        responses = list(
            db.scalars(
                select(ResponseLog)
                .order_by(ResponseLog.created_at.desc())
                .limit(settings.quality_gate_response_window)
            ).all()
        )
        response = responses[0] if responses else None
        eval_run = db.scalar(select(EvalRun).order_by(EvalRun.created_at.desc()))
        latest_dq_run_id = db.scalar(
            select(DQResult.run_id).where(DQResult.run_id.is_not(None)).order_by(DQResult.created_at.desc())
        )
        critical_dq_failures = 0
        if latest_dq_run_id is not None:
            critical_dq_failures = (
                db.scalar(
                    select(func.count())
                    .select_from(DQResult)
                    .where(DQResult.run_id == latest_dq_run_id, DQResult.status == "failed")
                )
                or 0
            )

        if response is None:
            result = {
                "gate_status": "failed",
                "failed_checks": ["no_responses"],
                "metrics_snapshot": aggregate_response_metrics([]),
            }
            db.add(QualityGateResult(gate_status="failed", failed_checks=result["failed_checks"], metrics_snapshot=result["metrics_snapshot"]))
            db.commit()
            return result

        response_aggregate = aggregate_response_metrics(responses)
        scores = response.scores
        failed_checks = []
        if response_aggregate["avg_groundedness"] < thresholds["groundedness_min"]:
            failed_checks.append("avg_groundedness_min")
        if response_aggregate["avg_relevance"] < thresholds["relevance_min"]:
            failed_checks.append("avg_relevance_min")
        if response_aggregate["avg_citation_correctness"] < thresholds["citation_correctness_min"]:
            failed_checks.append("avg_citation_correctness_min")
        if response_aggregate["avg_safety"] < thresholds["safety_min"]:
            failed_checks.append("avg_safety_min")
        if response_aggregate["validation_pass_rate"] < thresholds.get("validation_pass_rate_min", 1.0):
            failed_checks.append("validation_pass_rate_min")
        if response_aggregate["failed_response_rate"] > thresholds.get("failed_response_rate_max", 0.0):
            failed_checks.append("failed_response_rate_max")
        if eval_run is None:
            failed_checks.append("eval_run_missing")
        else:
            eval_metrics = eval_run.metrics
            if eval_metrics.get("source_hit", 0.0) < thresholds["retrieval_hit_rate_min"]:
                failed_checks.append("retrieval_hit_rate_min")
            if eval_metrics.get("groundedness", 0.0) < thresholds["groundedness_min"]:
                failed_checks.append("eval_groundedness_min")
            if eval_metrics.get("citation_correctness", 0.0) < thresholds["citation_correctness_min"]:
                failed_checks.append("eval_citation_correctness_min")
        if critical_dq_failures > thresholds["critical_dq_failures_max"]:
            failed_checks.append("critical_dq_failures_max")

        gate_status = "failed" if failed_checks else "passed"
        metrics_snapshot = {
            **response_aggregate,
            "response_window": settings.quality_gate_response_window,
            "latest_response": {
                "id": str(response.id),
                "trace_id": str(response.trace_id),
                "status": response.status,
                "validation_status": response.validation_status,
                "scores": scores,
                "payload": response.payload,
                "created_at": response.created_at.isoformat(),
            },
            "latest_eval_run_id": str(eval_run.id) if eval_run is not None else None,
            "latest_eval_metrics": eval_run.metrics if eval_run is not None else {},
            "latest_dq_run_id": str(latest_dq_run_id) if latest_dq_run_id is not None else None,
            "critical_dq_failures": critical_dq_failures,
        }
        db.add(
            QualityGateResult(
                trace_id=response.trace_id,
                gate_status=gate_status,
                failed_checks=failed_checks,
                metrics_snapshot=metrics_snapshot,
            )
        )
        db.commit()
        return {"gate_status": gate_status, "failed_checks": failed_checks, "metrics_snapshot": metrics_snapshot}


if __name__ == "__main__":
    result = evaluate_latest_response_gate()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["gate_status"] == "passed" else 1)
