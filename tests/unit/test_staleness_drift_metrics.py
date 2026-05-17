from datetime import UTC, datetime

from app.dirty_data import analyze_dirty_data
from app.staleness_drift import analyze_staleness_drift


REFERENCE_TIME = datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC)


def test_recent_rag_dataset_is_contract_valid_baseline() -> None:
    result = analyze_dirty_data(
        dataset_path="datasets/samples/rag_documents_recent_v2.jsonl",
        contract_path="datasets/samples/rag_dataset_contract.yaml",
    )
    metrics = {metric.name: metric for metric in result.metrics}

    assert metrics["schema_validity_ratio"].value == 1.0
    assert metrics["completeness_ratio"].value == 1.0
    assert metrics["duplicate_ratio"].value == 0.0
    assert result.hard_gate_result == "pass"


def test_staleness_metrics_degrade_for_stale_dataset() -> None:
    fresh = analyze_staleness_drift(
        dataset_path="datasets/samples/rag_documents_recent_v2.jsonl",
        contract_path="datasets/samples/rag_dataset_contract.yaml",
        reference_time=REFERENCE_TIME,
    )
    stale = analyze_staleness_drift(
        dataset_path="datasets/synthetic/rag_documents_stale_v1.jsonl",
        contract_path="datasets/samples/rag_dataset_contract.yaml",
        baseline_dataset_path="datasets/samples/rag_documents_recent_v2.jsonl",
        reference_time=REFERENCE_TIME,
    )

    fresh_metrics = {metric.name: metric for metric in fresh.metrics}
    stale_metrics = {metric.name: metric for metric in stale.metrics}

    assert fresh_metrics["freshness_hours"].value < stale_metrics["freshness_hours"].value
    assert fresh_metrics["update_lag_hours_avg"].value < stale_metrics["update_lag_hours_avg"].value
    assert fresh_metrics["coverage_ratio_28d"].value > stale_metrics["coverage_ratio_28d"].value
    assert stale_metrics["temporal_psi"].value > 0.1
    assert fresh.hard_gate_result == "pass"
    assert stale.hard_gate_result == "fail"


def test_staleness_drilldown_contains_missing_buckets_and_baseline() -> None:
    stale = analyze_staleness_drift(
        dataset_path="datasets/synthetic/rag_documents_stale_v1.jsonl",
        contract_path="datasets/samples/rag_dataset_contract.yaml",
        baseline_dataset_path="datasets/samples/rag_documents_recent_v2.jsonl",
        reference_time=REFERENCE_TIME,
    )
    metrics = {metric.name: metric for metric in stale.metrics}

    assert metrics["coverage_ratio_28d"].details["missing_buckets"]
    assert metrics["temporal_psi"].details["baseline_dataset_path"]
    assert any(event["severity"] == "critical" for event in stale.events)
