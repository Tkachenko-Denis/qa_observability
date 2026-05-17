from pathlib import Path

from scripts.airflow_api_smoke import REQUIRED_DAG_IDS, parse_required_dags, run_smoke


class FakeAirflowClient:
    def get_json(self, path: str) -> dict:
        if path == "/health":
            return {"metadatabase": {"status": "healthy"}, "scheduler": {"status": "healthy"}}
        if path == "/api/v1/dags?limit=100":
            return {"dags": [{"dag_id": dag_id} for dag_id in REQUIRED_DAG_IDS]}
        if path == "/api/v1/importErrors":
            return {"import_errors": [], "total_entries": 0}
        raise AssertionError(f"unexpected path: {path}")


def test_airflow_api_smoke_contract_passes_for_required_dags() -> None:
    result = run_smoke(FakeAirflowClient(), REQUIRED_DAG_IDS)

    assert result["status"] == "passed"
    assert result["failed_checks"] == []
    assert result["dag_count"] == len(REQUIRED_DAG_IDS)


def test_airflow_api_smoke_script_and_env_are_documented() -> None:
    script = Path("scripts/airflow_api_smoke.py").read_text(encoding="utf-8")
    env_example = Path(".env.example").read_text(encoding="utf-8")
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "/api/v1/dags?limit=100" in script
    assert "/api/v1/importErrors" in script
    assert "AIRFLOW__API__AUTH_BACKENDS: airflow.api.auth.backend.basic_auth,airflow.api.auth.backend.session" in compose
    assert "AIRFLOW_API_BASE_URL=http://localhost:8080" in env_example
    assert "AIRFLOW_USERNAME=admin" in env_example
    assert "AIRFLOW_API_RETRIES=5" in env_example
    assert "OSError" in script
    assert parse_required_dags("a,b, c") == ("a", "b", "c")
