from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from math import log
from typing import Any

from app.dirty_data import MetricResult, load_contract, load_records, load_yaml, resolve_project_path


@dataclass(slots=True)
class StalenessDriftResult:
    metrics: list[MetricResult]
    run_status: str
    hard_gate_result: str
    soft_gate_result: str
    summary: dict[str, Any]
    events: list[dict[str, Any]]


def load_staleness_rules() -> dict[str, Any]:
    rules_payload = load_yaml(
        resolve_project_path("services/metric_runner/config/staleness_drift_rules.yaml")
    )
    return rules_payload["staleness_drift_rules"]


def _threshold_hit(metric_value: float, threshold: float, comparator: str) -> bool:
    if comparator == "gt":
        return metric_value > threshold
    return metric_value < threshold


def _build_metric(
    metric_name: str,
    metric_value: float,
    rules: dict[str, Any],
    details: dict[str, Any],
) -> MetricResult:
    thresholds = rules["thresholds"]["metrics"].get(metric_name, {})
    comparator = thresholds.get("comparator", "lt")
    hard_value = thresholds.get("hard_fail")
    soft_value = thresholds.get("soft_warn")
    status = "ok"
    if hard_value is not None and _threshold_hit(metric_value, hard_value, comparator):
        status = "fail"
    elif soft_value is not None and _threshold_hit(metric_value, soft_value, comparator):
        status = "warn"
    return MetricResult(metric_name, round(metric_value, 6), status, details)


def _parse_event_times(records: list[dict[str, Any]], event_time_field: str) -> tuple[list[datetime], list[dict[str, Any]]]:
    parsed_times: list[datetime] = []
    invalid_examples: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        raw_value = record.get(event_time_field)
        if raw_value in (None, ""):
            if len(invalid_examples) < 5:
                invalid_examples.append({"row_index": index, "event_time": raw_value, "reason": "missing"})
            continue
        try:
            parsed_value = datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
        except ValueError:
            if len(invalid_examples) < 5:
                invalid_examples.append({"row_index": index, "event_time": raw_value, "reason": "invalid"})
            continue
        if parsed_value.tzinfo is None:
            parsed_value = parsed_value.replace(tzinfo=UTC)
        parsed_times.append(parsed_value.astimezone(UTC))
    return parsed_times, invalid_examples


def _bucket_label(dt: datetime, bucket_days: int) -> str:
    day_index = (dt.toordinal() // bucket_days) * bucket_days
    return str(day_index)


def _coverage_ratio(
    timestamps: list[datetime],
    reference_time: datetime,
    lookback_days: int,
    bucket_days: int,
) -> tuple[float, list[str], list[str]]:
    total_buckets = max(1, lookback_days // bucket_days)
    occupied_buckets: set[str] = set()

    for timestamp in timestamps:
        delta_days = (reference_time - timestamp).days
        if 0 <= delta_days < lookback_days:
            occupied_buckets.add(_bucket_label(timestamp, bucket_days))

    coverage = len(occupied_buckets) / total_buckets
    missing_buckets = [f"bucket_{index}" for index in range(total_buckets - len(occupied_buckets))]
    return coverage, sorted(occupied_buckets), missing_buckets


def _distribution_by_bucket(
    timestamps: list[datetime],
    lookback_days: int,
    bucket_days: int,
    reference_time: datetime,
) -> dict[str, float]:
    relevant = [timestamp for timestamp in timestamps if 0 <= (reference_time - timestamp).days < lookback_days]
    if not relevant:
        return {}
    counts = Counter(_bucket_label(timestamp, bucket_days) for timestamp in relevant)
    total = sum(counts.values())
    return {bucket: count / total for bucket, count in counts.items()}


def _psi(current_dist: dict[str, float], baseline_dist: dict[str, float]) -> float:
    epsilon = 1e-6
    all_buckets = set(current_dist) | set(baseline_dist)
    if not all_buckets:
        return 0.0

    value = 0.0
    for bucket in all_buckets:
        current_share = current_dist.get(bucket, epsilon)
        baseline_share = baseline_dist.get(bucket, epsilon)
        value += (current_share - baseline_share) * log(current_share / baseline_share)
    return value


def analyze_staleness_drift(
    dataset_path: str,
    contract_path: str,
    baseline_dataset_path: str | None = None,
    reference_time: datetime | None = None,
    run_context: dict[str, Any] | None = None,
) -> StalenessDriftResult:
    contract = load_contract(contract_path)
    rules = load_staleness_rules()
    records = load_records(dataset_path)
    baseline_records = load_records(baseline_dataset_path) if baseline_dataset_path else []
    run_context = run_context or {}

    event_time_field = contract.get("event_time_field", "updated_at")
    lookback_days = int(rules["window"].get("lookback_days", 28))
    bucket_days = int(rules["window"].get("bucket_days", 7))
    reference_time = reference_time or datetime.now(UTC)
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=UTC)

    timestamps, invalid_examples = _parse_event_times(records, event_time_field)
    baseline_timestamps, _ = _parse_event_times(baseline_records, event_time_field)

    if timestamps:
        max_timestamp = max(timestamps)
        freshness_hours = (reference_time - max_timestamp).total_seconds() / 3600
        average_lag_hours = sum(
            (reference_time - timestamp).total_seconds() / 3600 for timestamp in timestamps
        ) / len(timestamps)
    else:
        max_timestamp = None
        freshness_hours = float("inf")
        average_lag_hours = float("inf")

    coverage_ratio, occupied_buckets, missing_buckets = _coverage_ratio(
        timestamps,
        reference_time,
        lookback_days,
        bucket_days,
    )

    current_distribution = _distribution_by_bucket(timestamps, lookback_days, bucket_days, reference_time)
    baseline_distribution = _distribution_by_bucket(
        baseline_timestamps, lookback_days, bucket_days, reference_time
    )
    temporal_psi = _psi(current_distribution, baseline_distribution) if baseline_timestamps else 0.0

    metrics = [
        _build_metric(
            "freshness_hours",
            freshness_hours,
            rules,
            {
                "latest_event_time": max_timestamp.isoformat() if max_timestamp else None,
                "invalid_examples": invalid_examples,
            },
        ),
        _build_metric(
            "update_lag_hours_avg",
            average_lag_hours,
            rules,
            {
                "record_count_with_timestamps": len(timestamps),
                "reference_time": reference_time.isoformat(),
            },
        ),
        _build_metric(
            f"coverage_ratio_{lookback_days}d",
            coverage_ratio,
            rules,
            {
                "occupied_buckets": occupied_buckets,
                "missing_buckets": missing_buckets,
                "lookback_days": lookback_days,
                "bucket_days": bucket_days,
            },
        ),
        _build_metric(
            "temporal_psi",
            temporal_psi,
            rules,
            {
                "feature": event_time_field,
                "current_distribution": current_distribution,
                "baseline_distribution": baseline_distribution,
                "baseline_dataset_path": baseline_dataset_path,
            },
        ),
    ]

    hard_failed_metrics = [metric.name for metric in metrics if metric.status == "fail"]
    soft_warn_metrics = [metric.name for metric in metrics if metric.status == "warn"]

    events: list[dict[str, Any]] = []
    for metric in metrics:
        if metric.status == "ok":
            continue
        severity = "critical" if metric.status == "fail" else "warning"
        events.append(
            {
                "category": "staleness_drift",
                "status": metric.status,
                "severity": severity,
                "details": {
                    "metric_name": metric.name,
                    "metric_value": metric.value,
                    "diagnostics": metric.details,
                    "recommendation": rules["actions"].get(
                        metric.name,
                        "inspect dataset freshness and temporal distribution",
                    ),
                },
            }
        )

    summary = {
        "record_count": len(records),
        "dataset_path": dataset_path,
        "baseline_dataset_path": baseline_dataset_path,
        "contract_path": contract_path,
        "reference_time": reference_time.isoformat(),
        "hard_failed_metrics": hard_failed_metrics,
        "soft_warn_metrics": soft_warn_metrics,
        "run_context": run_context,
    }

    return StalenessDriftResult(
        metrics=metrics,
        run_status="completed",
        hard_gate_result="fail" if hard_failed_metrics else "pass",
        soft_gate_result="warn" if soft_warn_metrics else "pass",
        summary=summary,
        events=events,
    )
