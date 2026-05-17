from fastapi.testclient import TestClient

from app.main import app


def test_llmops_endpoints_exist() -> None:
    client = TestClient(app)

    links_response = client.get("/llmops/mlflow/links")
    gate_response = client.get(
        "/datasets/00000000-0000-0000-0000-000000000000/versions/00000000-0000-0000-0000-000000000000/gate"
    )

    assert links_response.status_code == 200
    assert gate_response.status_code == 404
    assert isinstance(links_response.json(), list)
