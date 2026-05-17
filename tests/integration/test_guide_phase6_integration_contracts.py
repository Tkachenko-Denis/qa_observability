from fastapi.testclient import TestClient

from app.main import app


def test_milvus_and_langfuse_status_contracts_exist() -> None:
    client = TestClient(app)

    integrations_response = client.get("/integrations")
    milvus_response = client.get("/integrations/milvus/status")
    langfuse_response = client.get("/integrations/langfuse/status")

    assert integrations_response.status_code == 200
    assert milvus_response.status_code == 200
    assert langfuse_response.status_code == 200

    integrations = {item["name"]: item for item in integrations_response.json()}
    assert integrations["milvus"]["mode"] in {"contract_only", "runtime"}
    assert integrations["milvus"]["fallback"] == "file_backed_retriever"
    assert integrations["langfuse"]["mode"] in {"contract_only", "runtime", "keys_missing", "sdk_missing"}
    assert integrations["langfuse"]["fallback"] == "postgres_trace_events"


def test_integration_contracts_describe_search_upsert_and_trace() -> None:
    client = TestClient(app)

    response = client.get("/integrations/contracts")

    assert response.status_code == 200
    body = response.json()

    assert body["milvus"]["search"]["tool_name"] == "milvus_retriever"
    assert body["milvus"]["search"]["action"] == "search"
    assert body["milvus"]["upsert"]["tool_name"] == "milvus_indexer"
    assert body["langfuse"]["trace"]["scenario"] == "rag_qa"
    assert body["langfuse"]["trace"]["export_status"] in {"not_executed", "runtime", "keys_missing", "sdk_missing"}
    assert body["mlflow"]["eval_run"]["tool_name"] == "mlflow_eval_tracker"
