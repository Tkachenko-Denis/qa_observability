from app.bias import analyze_bias


def test_bias_metrics_degrade_on_skewed_dataset() -> None:
    balanced = analyze_bias("datasets/samples/annotation_bias_balanced_v1.jsonl")
    skewed = analyze_bias("datasets/synthetic/annotation_bias_skewed_v1.jsonl")

    balanced_metrics = {metric.name: metric for metric in balanced.metrics}
    skewed_metrics = {metric.name: metric for metric in skewed.metrics}

    assert balanced_metrics["min_slice_representation"].value > skewed_metrics["min_slice_representation"].value
    assert balanced_metrics["slice_label_distribution_gap"].value < skewed_metrics["slice_label_distribution_gap"].value
    assert balanced_metrics["min_slice_quality"].value > skewed_metrics["min_slice_quality"].value
    assert balanced_metrics["bias_score"].value < skewed_metrics["bias_score"].value
    assert skewed.hard_gate_result == "fail"


def test_bias_slice_reports_and_shift_examples_exist() -> None:
    skewed = analyze_bias("datasets/synthetic/annotation_bias_skewed_v1.jsonl")
    metrics = {metric.name: metric for metric in skewed.metrics}

    assert skewed.summary["slice_reports"]
    assert metrics["slice_label_distribution_gap"].details["shift_examples"]
    assert any(event["category"] == "bias" for event in skewed.events)
