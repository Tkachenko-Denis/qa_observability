from pathlib import Path

from fastapi.testclient import TestClient
import yaml

from app.config import get_settings
from app.main import app
from app.observability_tools.mlflow_client import MLflowEvalRunContract, MLflowTrackingClient


def test_mlflow_integration_status_and_contract_are_exposed() -> None:
    client = TestClient(app)

    status_response = client.get("/integrations/mlflow/status")
    contracts_response = client.get("/integrations/contracts")

    assert status_response.status_code == 200
    assert contracts_response.status_code == 200
    status = status_response.json()
    contracts = contracts_response.json()
    assert status["name"] == "mlflow"
    assert status["fallback"] == "postgres_eval_runs_and_local_artifacts"
    assert contracts["mlflow"]["eval_run"]["tool_name"] == "mlflow_eval_tracker"
    assert contracts["mlflow"]["eval_run"]["action"] == "log_eval_run"


def test_mlflow_client_skips_sdk_when_disabled() -> None:
    settings = get_settings()
    client = MLflowTrackingClient(settings)
    result = client.log_eval_run(
        MLflowEvalRunContract(
            run_name="unit_eval",
            model_name="local_llama:llama3",
            model_version="mock-v1",
            prompt_version="rag-v1",
            metrics={"groundedness": 1.0},
            artifacts={},
            params={"eval_dataset_version": "not specified"},
        )
    )

    assert result == {"status": "skipped", "reason": "mlflow_disabled"}


def test_docker_services_use_container_mlflow_tracking_uri_and_env_example_stays_host_friendly() -> None:
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    env_example = Path(".env.example").read_text(encoding="utf-8")
    for service_name in ("api", "airflow-init", "airflow-webserver", "airflow-scheduler"):
        assert compose["services"][service_name]["environment"]["MLFLOW_TRACKING_URI"] == "http://mlflow:5000"
    assert "MLFLOW_TRACKING_URI=http://localhost:5000" in env_example
    assert "DATABASE_URL=postgresql+psycopg://dq:dq@localhost:5432/dq_observability" in env_example
    assert "UI_BACKEND_URL=http://localhost:8000" in env_example
    assert "UI_PROMETHEUS_URL=http://localhost:9090" in env_example


def test_mlflow_service_uses_persistent_backend_and_artifact_volume() -> None:
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    mlflow = compose["services"]["mlflow"]
    command = mlflow["command"]
    command_text = " ".join(command) if isinstance(command, list) else command

    assert "mlflow_data" in compose["volumes"]
    assert "mlflow_data:/mlflow" in mlflow["volumes"]
    assert "--backend-store-uri sqlite:////mlflow/mlflow.db" in command_text
    assert "--default-artifact-root /mlflow/artifacts" in command_text
