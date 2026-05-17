from fastapi.testclient import TestClient

from app.main import app


def test_observability_endpoints_exist() -> None:
    client = TestClient(app)

    runs_response = client.get("/dq/runs")
    events_response = client.get("/dq/events")
    summary_response = client.get("/dq/summary")

    assert runs_response.status_code == 200
    assert events_response.status_code == 200
    assert summary_response.status_code == 200
    assert isinstance(runs_response.json(), list)
    assert isinstance(events_response.json(), list)
    assert isinstance(summary_response.json(), list)
