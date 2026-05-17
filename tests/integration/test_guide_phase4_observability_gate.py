from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_readiness_metrics_are_exported_after_readiness_call() -> None:
    client = TestClient(app)

    readiness_response = client.get("/llmops/readiness")
    metrics_response = client.get("/metrics")

    assert readiness_response.status_code == 200
    assert metrics_response.status_code == 200

    metrics_text = metrics_response.text
    assert "llmops_readiness_status" in metrics_text
    assert "runtime_dq_failed_checks" in metrics_text


def test_readiness_gate_and_alert_artifacts_exist() -> None:
    assert Path("scripts/readiness_gate.py").exists()

    quality_gate_dag = Path("airflow/dags/quality_gate_dag.py").read_text(encoding="utf-8")
    alert_rules = Path("dashboards/alerts/dq_rules.yml").read_text(encoding="utf-8")

    assert "readiness_gate.py" in quality_gate_dag
    assert "LLMOpsReadinessFailed" in alert_rules
    assert "LLMOpsQualityGateFailed" in alert_rules
    assert "LLMOpsEvalGroundednessLow" in alert_rules
