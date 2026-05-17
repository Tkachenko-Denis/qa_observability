from pathlib import Path

from app.config import get_settings
from app.retrieval.milvus_client import MilvusContractClient, MilvusUpsertRequest
from scripts.build_index import deterministic_embedding


def test_milvus_runtime_client_skips_when_disabled() -> None:
    settings = get_settings()
    client = MilvusContractClient(settings)
    result = client.upsert_vectors(MilvusUpsertRequest(collection=settings.milvus_collection, vectors=[], payloads=[]))

    assert result == {"status": "skipped", "reason": "milvus_disabled", "inserted_count": 0}


def test_milvus_status_and_embedding_contract_are_runtime_ready() -> None:
    status = MilvusContractClient(get_settings()).status()
    vector = deterministic_embedding("hello retrieval")

    assert status["name"] == "milvus"
    assert "sdk_available" in status
    assert status["fallback"] == "file_backed_retriever"
    assert len(vector) == 16
    assert all(-1.0 <= value <= 1.0 for value in vector)


def test_optional_runtime_sdks_are_installed_in_docker_images_but_disabled_by_default() -> None:
    api_dockerfile = Path("docker/api.Dockerfile").read_text(encoding="utf-8")
    airflow_dockerfile = Path("docker/airflow.Dockerfile").read_text(encoding="utf-8")
    env_example = Path(".env.example").read_text(encoding="utf-8")

    assert 'pip install ".[dq]"' in api_dockerfile
    for package in ("great-expectations>=1.2.0", "mlflow>=2.19.0", "pymilvus>=2.5.0", "langfuse>=2.60.0"):
        assert package in airflow_dockerfile
    assert "MILVUS_ENABLED=false" in env_example
    assert "LANGFUSE_ENABLED=false" in env_example
    assert "MLFLOW_ENABLED=false" in env_example


def test_milvus_bootstrap_script_declares_collection_schema_index_and_airflow_task() -> None:
    script = Path("scripts/bootstrap_milvus.py").read_text(encoding="utf-8")
    dag = Path("airflow/dags/build_embeddings_dag.py").read_text(encoding="utf-8")
    for field_name in ("chunk_id", "document_id", "text", "source", "metadata", "embedding"):
        assert field_name in script
    assert "EMBEDDING_DIMENSION = 16" in script
    assert "DataType.FLOAT_VECTOR" in script
    assert "index_type" in script
    assert "IVF_FLAT" in script
    assert "metric_type" in script
    assert "COSINE" in script
    assert "json.dumps(result, indent=2)" in script
    assert "bootstrap_milvus.py" in dag
    assert "bootstrap_milvus >> build_embeddings" in dag
