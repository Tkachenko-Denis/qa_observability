from fastapi.testclient import TestClient

from app.main import app


def test_eval_dq_gate_readiness_endpoints_exist() -> None:
    client = TestClient(app)

    eval_runs_response = client.get("/eval/runs")
    dq_results_response = client.get("/dq/results")
    quality_gates_response = client.get("/quality-gates")
    readiness_response = client.get("/llmops/readiness")
    traces_response = client.get("/traces")
    dq_latest_response = client.get("/dq/results/latest")

    assert eval_runs_response.status_code == 200
    assert dq_results_response.status_code == 200
    assert quality_gates_response.status_code == 200
    assert readiness_response.status_code == 200
    assert traces_response.status_code == 200
    assert dq_latest_response.status_code == 200

    assert isinstance(eval_runs_response.json(), list)
    assert isinstance(dq_results_response.json(), list)
    assert isinstance(quality_gates_response.json(), list)
    assert readiness_response.json()["status"] in {"passed", "failed", "unknown"}
    assert "traces" in traces_response.json()
    assert dq_latest_response.json()["status"] in {"passed", "failed", "unknown"}
