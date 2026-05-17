import csv
from pathlib import Path


def test_eval_bank_has_minimum_50_items() -> None:
    with Path("eval/eval_items.csv").open("r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) >= 50
    assert {"item_id", "question", "expected_sources", "construct", "locale"} <= set(rows[0])


def test_eval_bank_covers_extended_rag_documents_and_constructs() -> None:
    with Path("eval/eval_items.csv").open("r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    required_docs = {f"doc-{index:03d}" for index in range(4, 14)}
    required_constructs = {
        "groundedness",
        "citation_correctness",
        "retrieval_quality",
        "completeness",
        "instruction_following",
    }

    by_doc = {
        doc_id: {row["construct"] for row in rows if row["expected_sources"] == doc_id}
        for doc_id in required_docs
    }

    assert all(doc_id in {row["expected_sources"] for row in rows} for doc_id in required_docs)
    for doc_id, constructs in by_doc.items():
        assert required_constructs <= constructs, f"{doc_id} missing constructs: {required_constructs - constructs}"


def test_eval_and_gx_scripts_exist() -> None:
    assert Path("scripts/run_eval.py").exists()
    assert Path("scripts/run_gx_dq_checks.py").exists()
    assert Path("ge/expectations/rag_runtime_tables_suite.json").exists()


def test_airflow_dags_for_guide_phase2_exist() -> None:
    expected = [
        "airflow/dags/ingest_documents_dag.py",
        "airflow/dags/build_embeddings_dag.py",
        "airflow/dags/run_gx_dq_checks_dag.py",
        "airflow/dags/run_eval_suite_dag.py",
        "airflow/dags/quality_gate_dag.py",
    ]

    for path in expected:
        assert Path(path).exists()
