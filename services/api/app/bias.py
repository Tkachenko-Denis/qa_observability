from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from app.dirty_data import MetricResult, load_records, load_yaml, resolve_project_path


@dataclass(slots=True)
class BiasResult:
    metrics: list[MetricResult]
    run_status: str
    hard_gate_result: str
    soft_gate_result: str
    summary: dict[str, Any]
    events: list[dict[str, Any]]


def load_bias_rules() -> dict[str, Any]:
    rules_payload = load_yaml(resolve_project_path("services/metric_runner/config/bias_rules.yaml"))
    return rules_payload["bias_rules"]


def _threshold_hit(metric_value: float, threshold: float, comparator: str) -> bool:
    if comparator == "gt":
        return metric_value > threshold
    return metric_value < threshold


def _build_metric(metric_name: str, metric_value: float, rules: dict[str, Any], details: dict[str, Any]) -> MetricResult:
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


def _majority_label_by_example(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record["example_id"])].append(record)

    reduced: dict[str, dict[str, Any]] = {}
    for example_id, items in grouped.items():
        label_counts = Counter(str(item["label"]) for item in items)
        majority_label = label_counts.most_common(1)[0][0]
        reduced[example_id] = {
            "slice": str(items[0].get("slice", "unknown")),
            "label": majority_label,
            "labels": dict(label_counts),
            "text": items[0].get("text"),
        }
    return reduced


def analyze_bias(dataset_path: str, run_context: dict[str, Any] | None = None) -> BiasResult:
    rules = load_bias_rules()
    records = load_records(dataset_path)
    run_context = run_context or {}

    examples = _majority_label_by_example(records)
    if not examples:
        raise ValueError("bias dataset has no examples")

    slice_counts = Counter(item["slice"] for item in examples.values())
    total_examples = sum(slice_counts.values())
    slice_ratios = {slice_name: count / total_examples for slice_name, count in slice_counts.items()}
    min_slice_representation = min(slice_ratios.values()) if slice_ratios else 1.0

    labels = sorted({item["label"] for item in examples.values()})
    overall_label_distribution = Counter(item["label"] for item in examples.values())
    overall_probs = {label: overall_label_distribution.get(label, 0) / total_examples for label in labels}

    slice_distribution_gap = 0.0
    slice_quality = {}
    slice_reports = []
    label_shift_examples = []

    for slice_name, count in slice_counts.items():
        slice_examples = [item for item in examples.values() if item["slice"] == slice_name]
        label_counts = Counter(item["label"] for item in slice_examples)
        label_probs = {label: label_counts.get(label, 0) / count for label in labels}
        max_diff = max(abs(label_probs[label] - overall_probs[label]) for label in labels) if labels else 0.0
        slice_distribution_gap = max(slice_distribution_gap, max_diff)

        agreement_scores = []
        for item in slice_examples:
            votes = item["labels"]
            agreement_scores.append(max(votes.values()) / sum(votes.values()))
        avg_quality = sum(agreement_scores) / len(agreement_scores) if agreement_scores else 1.0
        slice_quality[slice_name] = avg_quality

        slice_reports.append(
            {
                "slice": slice_name,
                "representation_ratio": round(slice_ratios[slice_name], 6),
                "label_distribution": {label: round(label_probs[label], 6) for label in labels},
                "slice_quality": round(avg_quality, 6),
            }
        )
        if max_diff > 0.2 and len(label_shift_examples) < 5:
            label_shift_examples.append(
                {
                    "slice": slice_name,
                    "max_distribution_gap": round(max_diff, 6),
                    "label_distribution": {label: round(label_probs[label], 6) for label in labels},
                }
            )

    min_slice_quality = min(slice_quality.values()) if slice_quality else 1.0
    bias_score = max(1 - min_slice_representation, slice_distribution_gap, 1 - min_slice_quality)

    metrics = [
        _build_metric(
            "min_slice_representation",
            min_slice_representation,
            rules,
            {"slice_ratios": {slice_name: round(value, 6) for slice_name, value in slice_ratios.items()}},
        ),
        _build_metric(
            "slice_label_distribution_gap",
            slice_distribution_gap,
            rules,
            {"overall_label_distribution": {label: round(prob, 6) for label, prob in overall_probs.items()}, "shift_examples": label_shift_examples},
        ),
        _build_metric(
            "min_slice_quality",
            min_slice_quality,
            rules,
            {"slice_quality": {slice_name: round(value, 6) for slice_name, value in slice_quality.items()}},
        ),
        _build_metric(
            "bias_score",
            bias_score,
            rules,
            {"slice_reports": slice_reports},
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
                "category": "bias",
                "status": metric.status,
                "severity": severity,
                "details": {
                    "metric_name": metric.name,
                    "metric_value": metric.value,
                    "diagnostics": metric.details,
                    "recommendation": rules["actions"]["recommendations"].get(metric.name, "review slice imbalance and quality by group"),
                },
            }
        )

    summary = {
        "dataset_path": dataset_path,
        "record_count": len(records),
        "example_count": len(examples),
        "slice_count": len(slice_counts),
        "hard_failed_metrics": hard_failed_metrics,
        "soft_warn_metrics": soft_warn_metrics,
        "slice_reports": slice_reports,
        "run_context": run_context,
    }

    return BiasResult(
        metrics=metrics,
        run_status="completed",
        hard_gate_result="fail" if hard_failed_metrics else "pass",
        soft_gate_result="warn" if soft_warn_metrics else "pass",
        summary=summary,
        events=events,
    )
