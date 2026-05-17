from __future__ import annotations

from sqlalchemy.orm import Session

from app.bias import analyze_bias
from app.annotation_qa import analyze_annotation_qa
from app.dirty_data import analyze_dirty_data, default_contract_path
from app.models import DQEvent, DQMetric, DQRun, Dataset, DatasetVersion
from app.observability import observe_metric_value, observe_run_status
from app.staleness_drift import analyze_staleness_drift


def execute_dirty_data_run(
    db: Session,
    dataset: Dataset,
    version: DatasetVersion,
    run: DQRun,
) -> DQRun:
    dataset_path = version.location_uri
    if not dataset_path:
        run.status = "failed"
        run.hard_gate_result = "fail"
        run.soft_gate_result = "warn"
        run.details = {
            **run.details,
            "error": "dataset version location_uri is not specified",
        }
        db.add(
            DQEvent(
                dataset_id=dataset.id,
                dataset_version_id=version.id,
                dq_run_id=run.id,
                category="dirty_data",
                status="fail",
                severity="critical",
                details={"reason": "location_uri is not specified"},
            )
        )
        db.commit()
        db.refresh(run)
        observe_run_status(dataset.id, version.id, run.category, run.status)
        return run

    contract_path = dataset.payload.get("contract_path") or default_contract_path(dataset.category)
    if not contract_path:
        run.status = "failed"
        run.hard_gate_result = "fail"
        run.soft_gate_result = "warn"
        run.details = {
            **run.details,
            "error": "contract_path is not specified",
        }
        db.add(
            DQEvent(
                dataset_id=dataset.id,
                dataset_version_id=version.id,
                dq_run_id=run.id,
                category="dirty_data",
                status="fail",
                severity="critical",
                details={"reason": "contract_path is not specified"},
            )
        )
        db.commit()
        db.refresh(run)
        observe_run_status(dataset.id, version.id, run.category, run.status)
        return run

    try:
        result = analyze_dirty_data(
            dataset_path=dataset_path,
            contract_path=contract_path,
            run_context={"dataset_id": str(dataset.id), "dataset_version_id": str(version.id)},
        )
    except Exception as exc:
        run.status = "failed"
        run.hard_gate_result = "fail"
        run.soft_gate_result = "warn"
        run.details = {
            **run.details,
            "error": str(exc),
            "dataset_path": dataset_path,
            "contract_path": contract_path,
        }
        db.add(
            DQEvent(
                dataset_id=dataset.id,
                dataset_version_id=version.id,
                dq_run_id=run.id,
                category="dirty_data",
                status="fail",
                severity="critical",
                details={"reason": "dirty data analyzer failed", "error": str(exc)},
            )
        )
        db.commit()
        db.refresh(run)
        observe_run_status(dataset.id, version.id, run.category, run.status)
        return run

    run.status = result.run_status
    run.hard_gate_result = result.hard_gate_result
    run.soft_gate_result = result.soft_gate_result
    run.details = {**run.details, **result.summary}

    for metric in result.metrics:
        db.add(
            DQMetric(
                dq_run_id=run.id,
                dataset_id=dataset.id,
                dataset_version_id=version.id,
                category="dirty_data",
                metric_name=metric.name,
                metric_value=metric.value,
                status=metric.status,
                event_time_min=version.event_time_min,
                event_time_max=version.event_time_max,
                baseline_id=version.baseline_id,
                details=metric.details,
            )
        )
        observe_metric_value(dataset.id, version.id, "dirty_data", metric.name, metric.status, metric.value)

    for event in result.events:
        db.add(
            DQEvent(
                dataset_id=dataset.id,
                dataset_version_id=version.id,
                dq_run_id=run.id,
                category=event["category"],
                status=event["status"],
                severity=event["severity"],
                event_time_min=version.event_time_min,
                event_time_max=version.event_time_max,
                details=event["details"],
            )
        )

    if run.hard_gate_result == "fail":
        version.status = "blocked"
    elif run.soft_gate_result == "warn" and version.status == "draft":
        version.status = "ready_with_warnings"

    db.add(run)
    db.add(version)
    db.commit()
    db.refresh(run)
    observe_run_status(dataset.id, version.id, run.category, run.status)
    return run


def execute_staleness_drift_run(
    db: Session,
    dataset: Dataset,
    version: DatasetVersion,
    run: DQRun,
) -> DQRun:
    dataset_path = version.location_uri
    if not dataset_path:
        run.status = "failed"
        run.hard_gate_result = "fail"
        run.soft_gate_result = "warn"
        run.details = {**run.details, "error": "dataset version location_uri is not specified"}
        db.add(
            DQEvent(
                dataset_id=dataset.id,
                dataset_version_id=version.id,
                dq_run_id=run.id,
                category="staleness_drift",
                status="fail",
                severity="critical",
                details={"reason": "location_uri is not specified"},
            )
        )
        db.commit()
        db.refresh(run)
        observe_run_status(dataset.id, version.id, run.category, run.status)
        return run

    contract_path = dataset.payload.get("contract_path") or default_contract_path(dataset.category)
    if not contract_path:
        run.status = "failed"
        run.hard_gate_result = "fail"
        run.soft_gate_result = "warn"
        run.details = {**run.details, "error": "contract_path is not specified"}
        db.add(
            DQEvent(
                dataset_id=dataset.id,
                dataset_version_id=version.id,
                dq_run_id=run.id,
                category="staleness_drift",
                status="fail",
                severity="critical",
                details={"reason": "contract_path is not specified"},
            )
        )
        db.commit()
        db.refresh(run)
        observe_run_status(dataset.id, version.id, run.category, run.status)
        return run

    baseline_version = db.get(DatasetVersion, version.baseline_id) if version.baseline_id else None
    baseline_dataset_path = baseline_version.location_uri if baseline_version else None

    try:
        result = analyze_staleness_drift(
            dataset_path=dataset_path,
            contract_path=contract_path,
            baseline_dataset_path=baseline_dataset_path,
            run_context={
                "dataset_id": str(dataset.id),
                "dataset_version_id": str(version.id),
                "baseline_version_id": str(version.baseline_id) if version.baseline_id else None,
            },
        )
    except Exception as exc:
        run.status = "failed"
        run.hard_gate_result = "fail"
        run.soft_gate_result = "warn"
        run.details = {
            **run.details,
            "error": str(exc),
            "dataset_path": dataset_path,
            "contract_path": contract_path,
            "baseline_dataset_path": baseline_dataset_path,
        }
        db.add(
            DQEvent(
                dataset_id=dataset.id,
                dataset_version_id=version.id,
                dq_run_id=run.id,
                category="staleness_drift",
                status="fail",
                severity="critical",
                details={"reason": "staleness drift analyzer failed", "error": str(exc)},
            )
        )
        db.commit()
        db.refresh(run)
        observe_run_status(dataset.id, version.id, run.category, run.status)
        return run

    run.status = result.run_status
    run.hard_gate_result = result.hard_gate_result
    run.soft_gate_result = result.soft_gate_result
    run.details = {**run.details, **result.summary}

    for metric in result.metrics:
        db.add(
            DQMetric(
                dq_run_id=run.id,
                dataset_id=dataset.id,
                dataset_version_id=version.id,
                category="staleness_drift",
                metric_name=metric.name,
                metric_value=metric.value,
                status=metric.status,
                event_time_min=version.event_time_min,
                event_time_max=version.event_time_max,
                baseline_id=version.baseline_id,
                details=metric.details,
            )
        )
        observe_metric_value(dataset.id, version.id, "staleness_drift", metric.name, metric.status, metric.value)

    for event in result.events:
        db.add(
            DQEvent(
                dataset_id=dataset.id,
                dataset_version_id=version.id,
                dq_run_id=run.id,
                category=event["category"],
                status=event["status"],
                severity=event["severity"],
                event_time_min=version.event_time_min,
                event_time_max=version.event_time_max,
                details=event["details"],
            )
        )

    if run.hard_gate_result == "fail":
        version.status = "blocked"
    elif run.soft_gate_result == "warn" and version.status in {"draft", "ready_with_warnings"}:
        version.status = "ready_with_warnings"

    db.add(run)
    db.add(version)
    db.commit()
    db.refresh(run)
    observe_run_status(dataset.id, version.id, run.category, run.status)
    return run


def execute_annotation_qa_run(
    db: Session,
    dataset: Dataset,
    version: DatasetVersion,
    run: DQRun,
) -> DQRun:
    dataset_path = version.location_uri
    if not dataset_path:
        run.status = "failed"
        run.hard_gate_result = "fail"
        run.soft_gate_result = "warn"
        run.details = {**run.details, "error": "dataset version location_uri is not specified"}
        db.add(
            DQEvent(
                dataset_id=dataset.id,
                dataset_version_id=version.id,
                dq_run_id=run.id,
                category="annotation_qa",
                status="fail",
                severity="critical",
                details={"reason": "location_uri is not specified"},
            )
        )
        db.commit()
        db.refresh(run)
        observe_run_status(dataset.id, version.id, run.category, run.status)
        return run

    try:
        result = analyze_annotation_qa(
            dataset_path=dataset_path,
            run_context={"dataset_id": str(dataset.id), "dataset_version_id": str(version.id)},
        )
    except Exception as exc:
        run.status = "failed"
        run.hard_gate_result = "fail"
        run.soft_gate_result = "warn"
        run.details = {
            **run.details,
            "error": str(exc),
            "dataset_path": dataset_path,
        }
        db.add(
            DQEvent(
                dataset_id=dataset.id,
                dataset_version_id=version.id,
                dq_run_id=run.id,
                category="annotation_qa",
                status="fail",
                severity="critical",
                details={"reason": "annotation QA analyzer failed", "error": str(exc)},
            )
        )
        db.commit()
        db.refresh(run)
        observe_run_status(dataset.id, version.id, run.category, run.status)
        return run

    run.status = result.run_status
    run.hard_gate_result = result.hard_gate_result
    run.soft_gate_result = result.soft_gate_result
    run.details = {**run.details, **result.summary}

    for metric in result.metrics:
        db.add(
            DQMetric(
                dq_run_id=run.id,
                dataset_id=dataset.id,
                dataset_version_id=version.id,
                category="annotation_qa",
                metric_name=metric.name,
                metric_value=metric.value,
                status=metric.status,
                event_time_min=version.event_time_min,
                event_time_max=version.event_time_max,
                baseline_id=version.baseline_id,
                details=metric.details,
            )
        )
        observe_metric_value(dataset.id, version.id, "annotation_qa", metric.name, metric.status, metric.value)

    for event in result.events:
        db.add(
            DQEvent(
                dataset_id=dataset.id,
                dataset_version_id=version.id,
                dq_run_id=run.id,
                category=event["category"],
                status=event["status"],
                severity=event["severity"],
                event_time_min=version.event_time_min,
                event_time_max=version.event_time_max,
                details=event["details"],
            )
        )

    if run.hard_gate_result == "fail":
        version.status = "blocked"
    elif run.soft_gate_result == "warn" and version.status in {"draft", "ready_with_warnings"}:
        version.status = "ready_with_warnings"

    db.add(run)
    db.add(version)
    db.commit()
    db.refresh(run)
    observe_run_status(dataset.id, version.id, run.category, run.status)
    return run


def execute_bias_run(
    db: Session,
    dataset: Dataset,
    version: DatasetVersion,
    run: DQRun,
) -> DQRun:
    dataset_path = version.location_uri
    if not dataset_path:
        run.status = "failed"
        run.hard_gate_result = "fail"
        run.soft_gate_result = "warn"
        run.details = {**run.details, "error": "dataset version location_uri is not specified"}
        db.add(
            DQEvent(
                dataset_id=dataset.id,
                dataset_version_id=version.id,
                dq_run_id=run.id,
                category="bias",
                status="fail",
                severity="critical",
                details={"reason": "location_uri is not specified"},
            )
        )
        db.commit()
        db.refresh(run)
        observe_run_status(dataset.id, version.id, run.category, run.status)
        return run

    try:
        result = analyze_bias(
            dataset_path=dataset_path,
            run_context={"dataset_id": str(dataset.id), "dataset_version_id": str(version.id)},
        )
    except Exception as exc:
        run.status = "failed"
        run.hard_gate_result = "fail"
        run.soft_gate_result = "warn"
        run.details = {**run.details, "error": str(exc), "dataset_path": dataset_path}
        db.add(
            DQEvent(
                dataset_id=dataset.id,
                dataset_version_id=version.id,
                dq_run_id=run.id,
                category="bias",
                status="fail",
                severity="critical",
                details={"reason": "bias analyzer failed", "error": str(exc)},
            )
        )
        db.commit()
        db.refresh(run)
        observe_run_status(dataset.id, version.id, run.category, run.status)
        return run

    run.status = result.run_status
    run.hard_gate_result = result.hard_gate_result
    run.soft_gate_result = result.soft_gate_result
    run.details = {**run.details, **result.summary}

    for metric in result.metrics:
        db.add(
            DQMetric(
                dq_run_id=run.id,
                dataset_id=dataset.id,
                dataset_version_id=version.id,
                category="bias",
                metric_name=metric.name,
                metric_value=metric.value,
                status=metric.status,
                event_time_min=version.event_time_min,
                event_time_max=version.event_time_max,
                baseline_id=version.baseline_id,
                details=metric.details,
            )
        )
        observe_metric_value(dataset.id, version.id, "bias", metric.name, metric.status, metric.value)

    for event in result.events:
        db.add(
            DQEvent(
                dataset_id=dataset.id,
                dataset_version_id=version.id,
                dq_run_id=run.id,
                category=event["category"],
                status=event["status"],
                severity=event["severity"],
                event_time_min=version.event_time_min,
                event_time_max=version.event_time_max,
                details=event["details"],
            )
        )

    if run.hard_gate_result == "fail":
        version.status = "blocked"
    elif run.soft_gate_result == "warn" and version.status in {"draft", "ready_with_warnings"}:
        version.status = "ready_with_warnings"

    db.add(run)
    db.add(version)
    db.commit()
    db.refresh(run)
    observe_run_status(dataset.id, version.id, run.category, run.status)
    return run
