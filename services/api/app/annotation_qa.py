from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from app.dirty_data import MetricResult, load_records, load_yaml, resolve_project_path


@dataclass(slots=True)
class AnnotationQAResult:
    metrics: list[MetricResult]
    run_status: str
    hard_gate_result: str
    soft_gate_result: str
    summary: dict[str, Any]
    events: list[dict[str, Any]]


def load_annotation_rules() -> dict[str, Any]:
    rules_payload = load_yaml(
        resolve_project_path("services/metric_runner/config/annotation_qa_rules.yaml")
    )
    return rules_payload["annotation_qa_rules"]


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


def _group_annotations(records: list[dict[str, Any]]) -> tuple[dict[str, dict[str, str]], list[str], list[str]]:
    annotations_by_example: dict[str, dict[str, str]] = defaultdict(dict)
    labels: set[str] = set()
    annotators: set[str] = set()
    for record in records:
        example_id = str(record["example_id"])
        annotator_id = str(record["annotator_id"])
        label = str(record["label"])
        annotations_by_example[example_id][annotator_id] = label
        labels.add(label)
        annotators.add(annotator_id)
    return annotations_by_example, sorted(labels), sorted(annotators)


def _cohens_kappa(annotations_by_example: dict[str, dict[str, str]], annotators: list[str], labels: list[str]) -> tuple[float, dict[str, Any]]:
    if len(annotators) < 2:
        return 1.0, {"pair": None, "overlap_examples": 0}

    a1, a2 = annotators[:2]
    overlap = []
    for example_id, annotations in annotations_by_example.items():
        if a1 in annotations and a2 in annotations:
            overlap.append((example_id, annotations[a1], annotations[a2]))

    if not overlap:
        return 1.0, {"pair": [a1, a2], "overlap_examples": 0}

    observed = sum(1 for _, l1, l2 in overlap if l1 == l2) / len(overlap)
    p1 = Counter(l1 for _, l1, _ in overlap)
    p2 = Counter(l2 for _, _, l2 in overlap)
    expected = sum((p1[label] / len(overlap)) * (p2[label] / len(overlap)) for label in labels)
    if expected == 1:
        score = 1.0
    else:
        score = (observed - expected) / (1 - expected)
    return score, {"pair": [a1, a2], "overlap_examples": len(overlap), "observed_agreement": round(observed, 6)}


def _krippendorffs_alpha_nominal(annotations_by_example: dict[str, dict[str, str]]) -> float:
    pair_disagreements = 0.0
    pair_total = 0.0
    label_counts: Counter[str] = Counter()

    for annotations in annotations_by_example.values():
        values = list(annotations.values())
        for label in values:
            label_counts[label] += 1
        n = len(values)
        if n < 2:
            continue
        pair_total += n * (n - 1)
        counts = Counter(values)
        agreement_pairs = sum(count * (count - 1) for count in counts.values())
        pair_disagreements += pair_total - agreement_pairs

    total_labels = sum(label_counts.values())
    if pair_total == 0 or total_labels < 2:
        return 1.0

    observed_disagreement = 0.0
    for annotations in annotations_by_example.values():
        values = list(annotations.values())
        n = len(values)
        if n < 2:
            continue
        counts = Counter(values)
        disagreement_pairs = n * (n - 1) - sum(count * (count - 1) for count in counts.values())
        observed_disagreement += disagreement_pairs
    observed_disagreement /= pair_total

    expected_disagreement = 1.0 - sum(
        (count / total_labels) * ((count - 1) / (total_labels - 1))
        for count in label_counts.values()
    )
    if expected_disagreement == 0:
        return 1.0
    return 1.0 - (observed_disagreement / expected_disagreement)


def _majority_vote_posteriors(
    annotations_by_example: dict[str, dict[str, str]],
    labels: list[str],
    iterations: int = 5,
) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    priors = {label: 1.0 / len(labels) for label in labels}
    annotators = sorted({annotator for annotations in annotations_by_example.values() for annotator in annotations})
    confusion = {
        annotator: {
            true_label: {observed_label: (0.9 if true_label == observed_label else 0.1 / max(1, len(labels) - 1)) for observed_label in labels}
            for true_label in labels
        }
        for annotator in annotators
    }

    posteriors: dict[str, dict[str, float]] = {}

    for _ in range(iterations):
        for example_id, annotations in annotations_by_example.items():
            raw_scores: dict[str, float] = {}
            for true_label in labels:
                score = priors[true_label]
                for annotator_id, observed_label in annotations.items():
                    score *= confusion[annotator_id][true_label].get(observed_label, 1e-6)
                raw_scores[true_label] = score
            normalizer = sum(raw_scores.values()) or 1.0
            posteriors[example_id] = {label: raw_scores[label] / normalizer for label in labels}

        priors = {
            label: sum(posteriors[example_id][label] for example_id in posteriors) / max(1, len(posteriors))
            for label in labels
        }

        for annotator in annotators:
            for true_label in labels:
                denom = 0.0
                numerators = {observed_label: 1e-6 for observed_label in labels}
                for example_id, annotations in annotations_by_example.items():
                    if annotator not in annotations:
                        continue
                    posterior = posteriors[example_id][true_label]
                    denom += posterior
                    numerators[annotations[annotator]] += posterior
                if denom == 0:
                    continue
                confusion[annotator][true_label] = {
                    observed_label: numerators[observed_label] / (denom + 1e-6 * len(labels))
                    for observed_label in labels
                }

    annotator_quality: dict[str, float] = {}
    for annotator in annotators:
        quality_scores = []
        for true_label in labels:
            quality_scores.append(confusion[annotator][true_label].get(true_label, 0.0))
        annotator_quality[annotator] = sum(quality_scores) / len(quality_scores)

    return posteriors, annotator_quality


def analyze_annotation_qa(dataset_path: str, run_context: dict[str, Any] | None = None) -> AnnotationQAResult:
    rules = load_annotation_rules()
    records = load_records(dataset_path)
    run_context = run_context or {}

    annotations_by_example, labels, annotators = _group_annotations(records)
    if not labels:
        raise ValueError("annotation dataset has no labels")

    kappa, kappa_details = _cohens_kappa(annotations_by_example, annotators, labels)
    alpha = _krippendorffs_alpha_nominal(annotations_by_example)

    agreement_by_class: dict[str, float] = {}
    confusion_examples: list[dict[str, Any]] = []
    for label in labels:
        matching = 0
        total = 0
        for example_id, annotations in annotations_by_example.items():
            values = list(annotations.values())
            if label not in values:
                continue
            total += 1
            if len(set(values)) == 1 and values[0] == label:
                matching += 1
            elif len(confusion_examples) < 5:
                confusion_examples.append({"example_id": example_id, "labels": values})
        agreement_by_class[label] = matching / total if total else 1.0

    min_class_agreement = min(agreement_by_class.values()) if agreement_by_class else 1.0

    posteriors, annotator_quality = _majority_vote_posteriors(annotations_by_example, labels)
    error_probs = {example_id: 1 - max(label_probs.values()) for example_id, label_probs in posteriors.items()}
    dawid_skene_error_rate = sum(error_probs.values()) / max(1, len(error_probs))
    min_annotator_quality = min(annotator_quality.values()) if annotator_quality else 1.0

    reannotation_threshold = float(rules["actions"].get("reannotation_threshold", 0.25))
    reannotation_queue = [
        {
            "example_id": example_id,
            "probability_of_error": round(error_prob, 6),
            "posterior": {label: round(prob, 6) for label, prob in posteriors[example_id].items()},
        }
        for example_id, error_prob in sorted(error_probs.items(), key=lambda item: item[1], reverse=True)
        if error_prob >= reannotation_threshold
    ]

    metrics = [
        _build_metric(
            "cohens_kappa",
            kappa,
            rules,
            {"pair_details": kappa_details},
        ),
        _build_metric(
            "krippendorffs_alpha",
            alpha,
            rules,
            {"annotator_count": len(annotators), "example_count": len(annotations_by_example)},
        ),
        _build_metric(
            "min_class_agreement",
            min_class_agreement,
            rules,
            {"agreement_by_class": {label: round(value, 6) for label, value in agreement_by_class.items()}},
        ),
        _build_metric(
            "dawid_skene_error_rate",
            dawid_skene_error_rate,
            rules,
            {"top_risky_examples": reannotation_queue[:5]},
        ),
        _build_metric(
            "min_annotator_quality",
            min_annotator_quality,
            rules,
            {"annotator_quality": {annotator: round(value, 6) for annotator, value in annotator_quality.items()}},
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
                "category": "annotation_qa",
                "status": metric.status,
                "severity": severity,
                "details": {
                    "metric_name": metric.name,
                    "metric_value": metric.value,
                    "diagnostics": metric.details,
                    "recommendation": rules["actions"]["recommendations"].get(
                        metric.name,
                        "review annotation quality diagnostics",
                    ),
                },
            }
        )

    if reannotation_queue:
        events.append(
            {
                "category": "annotation_qa",
                "status": "warn",
                "severity": "warning",
                "details": {
                    "metric_name": "reannotation_queue",
                    "queue_size": len(reannotation_queue),
                    "examples": reannotation_queue[:10],
                    "recommendation": "send high-risk examples to reannotation queue",
                },
            }
        )

    summary = {
        "dataset_path": dataset_path,
        "record_count": len(records),
        "example_count": len(annotations_by_example),
        "annotator_count": len(annotators),
        "labels": labels,
        "hard_failed_metrics": hard_failed_metrics,
        "soft_warn_metrics": soft_warn_metrics,
        "reannotation_queue_size": len(reannotation_queue),
        "reannotation_queue": reannotation_queue[:10],
        "confusion_examples": confusion_examples,
        "run_context": run_context,
    }

    return AnnotationQAResult(
        metrics=metrics,
        run_status="completed",
        hard_gate_result="fail" if hard_failed_metrics else "pass",
        soft_gate_result="warn" if soft_warn_metrics else "pass",
        summary=summary,
        events=events,
    )
