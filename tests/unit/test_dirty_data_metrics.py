from app.dirty_data import analyze_dirty_data


def test_dirty_data_metrics_degrade_on_synthetic_dataset() -> None:
    clean = analyze_dirty_data(
        dataset_path="datasets/samples/rag_documents_extended_v2.jsonl",
        contract_path="datasets/samples/rag_dataset_contract.yaml",
    )
    dirty = analyze_dirty_data(
        dataset_path="datasets/synthetic/rag_documents_dirty_v1.jsonl",
        contract_path="datasets/samples/rag_dataset_contract.yaml",
    )

    clean_metrics = {metric.name: metric for metric in clean.metrics}
    dirty_metrics = {metric.name: metric for metric in dirty.metrics}

    assert clean_metrics["schema_validity_ratio"].value > dirty_metrics["schema_validity_ratio"].value
    assert clean_metrics["completeness_ratio"].value > dirty_metrics["completeness_ratio"].value
    assert clean_metrics["duplicate_free_ratio"].value > dirty_metrics["duplicate_free_ratio"].value
    assert clean_metrics["pattern_validity_ratio"].value > dirty_metrics["pattern_validity_ratio"].value
    assert clean_metrics["text_length_validity_ratio"].value > dirty_metrics["text_length_validity_ratio"].value
    assert dirty.hard_gate_result == "fail"
    assert dirty.run_status == "completed"
    assert clean.hard_gate_result == "pass"


def test_dirty_data_drilldown_contains_examples() -> None:
    dirty = analyze_dirty_data(
        dataset_path="datasets/synthetic/rag_documents_dirty_v1.jsonl",
        contract_path="datasets/samples/rag_dataset_contract.yaml",
    )
    metrics = {metric.name: metric for metric in dirty.metrics}

    assert metrics["schema_validity_ratio"].details["invalid_examples"]
    assert metrics["duplicate_ratio"].details["duplicate_examples"]
    assert metrics["pattern_validity_ratio"].details["invalid_language_examples"]
    assert any(event["severity"] == "critical" for event in dirty.events)


def test_dirty_data_clean_sample_passes_soft_gate() -> None:
    clean = analyze_dirty_data(
        dataset_path="datasets/samples/rag_documents_extended_v2.jsonl",
        contract_path="datasets/samples/rag_dataset_contract.yaml",
    )
    assert clean.soft_gate_result == "pass"
    metrics = {metric.name: metric for metric in clean.metrics}
    assert metrics["language_ratio"].status == "ok"
