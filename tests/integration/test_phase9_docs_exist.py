from pathlib import Path


def test_phase9_documents_exist() -> None:
    assert Path("docs/datasheets/rag_demo_datasheet.md").exists()
    assert Path("docs/data_statements/annotation_eval_statement.md").exists()
    assert Path("docs/architecture/final_architecture_summary.md").exists()
    assert Path("docs/runbooks/mvp_readiness.md").exists()
    assert Path("docs/runbooks/guide_definition_of_done_matrix.md").exists()
    assert Path("docs/runbooks/final_demo_ui.md").exists()


def test_readiness_docs_reflect_current_airflow_security_and_integration_scope() -> None:
    readiness = Path("docs/runbooks/mvp_readiness.md").read_text(encoding="utf-8")
    architecture = Path("docs/architecture/final_architecture_summary.md").read_text(encoding="utf-8")
    dod = Path("docs/runbooks/guide_definition_of_done_matrix.md").read_text(encoding="utf-8")

    assert "Airflow REST API smoke" in readiness
    assert "MVP-compatible Milvus and Langfuse contracts" in readiness
    assert "Optional Langfuse SDK-backed span export" in readiness
    assert "Configurable API key middleware" in readiness
    assert "input/output PII masking" in readiness
    assert "Optional MLflow SDK-backed eval tracking" in readiness
    assert "Docker `api-migrate` service blocks API startup" in readiness
    assert "Milvus collection bootstrap for deterministic 16-dim MVP embeddings" in readiness
    assert "--require-success-ask" in readiness
    assert "LangChain PromptTemplate/retriever/RunnableSequence wrapper" in readiness
    assert "Streamlit demo UI" in readiness
    assert "backend-approved model profiles" in readiness
    assert "GX-style/custom runtime DQ checks" in readiness
    assert "Airflow runtime" in architecture
    assert "collection bootstrap for deterministic 16-dim MVP embeddings" in architecture
    assert "production real embedding model operation is not implemented" in architecture
    assert "custom `/ask` orchestrator remains the default runtime path" in architecture
    assert "runtime DQ is GX-style/custom" in architecture
    assert "Docker startup is guarded by `api-migrate`" in architecture
    assert "Streamlit UI" in architecture
    assert "backend-approved model profile selection" in architecture
    assert "MLflow tracking metadata persists in Docker volume `mlflow_data`" in architecture
    assert "production Langfuse project/session/user setup and retention policy is not implemented" in architecture
    assert "production MLflow experiment naming/model registry linkage is not implemented" in architecture
    assert "input/output PII masking" in architecture
    assert "Airflow smoke checks the current required DAG set" in dod
    assert "`quality_gate_dag` may fail by design" in dod
