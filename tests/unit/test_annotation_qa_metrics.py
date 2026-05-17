from app.annotation_qa import analyze_annotation_qa


def test_annotation_metrics_degrade_on_disagreement_dataset() -> None:
    consensus = analyze_annotation_qa("datasets/samples/annotation_eval_consensus_v1.jsonl")
    disagreement = analyze_annotation_qa("datasets/synthetic/annotation_eval_disagreement_v1.jsonl")

    consensus_metrics = {metric.name: metric for metric in consensus.metrics}
    disagreement_metrics = {metric.name: metric for metric in disagreement.metrics}

    assert consensus_metrics["cohens_kappa"].value > disagreement_metrics["cohens_kappa"].value
    assert consensus_metrics["krippendorffs_alpha"].value > disagreement_metrics["krippendorffs_alpha"].value
    assert consensus_metrics["min_class_agreement"].value > disagreement_metrics["min_class_agreement"].value
    assert consensus_metrics["dawid_skene_error_rate"].value < disagreement_metrics["dawid_skene_error_rate"].value
    assert disagreement.hard_gate_result == "fail"


def test_annotation_reannotation_queue_and_annotator_quality_exist() -> None:
    disagreement = analyze_annotation_qa("datasets/synthetic/annotation_eval_disagreement_v1.jsonl")
    metrics = {metric.name: metric for metric in disagreement.metrics}

    assert metrics["min_annotator_quality"].details["annotator_quality"]
    assert disagreement.summary["reannotation_queue_size"] > 0
    assert disagreement.summary["reannotation_queue"]
    assert any(event["details"].get("metric_name") == "reannotation_queue" for event in disagreement.events)
