from pathlib import Path

import yaml


def test_airflow_services_declared_in_compose() -> None:
    compose_text = Path("docker-compose.yml").read_text(encoding="utf-8")
    compose = yaml.safe_load(compose_text)

    assert "airflow-init:" in compose_text
    assert "airflow-webserver:" in compose_text
    assert "airflow-scheduler:" in compose_text
    assert "8080:8080" in compose_text
    assert compose["services"]["ui"]["ports"] == ["8501:8501"]
    assert compose["services"]["ui"]["environment"]["UI_BACKEND_URL"] == "http://api:8000"
    assert compose["services"]["ui"]["environment"]["UI_PROMETHEUS_URL"] == "http://prometheus:9090"
    assert compose["services"]["ui"]["depends_on"]["api"]["condition"] == "service_healthy"
    assert "http://127.0.0.1:8000/health" in compose["services"]["api"]["healthcheck"]["test"][1]


def test_api_waits_for_docker_migration_service() -> None:
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    readme = Path("README.md").read_text(encoding="utf-8")
    config = Path("services/api/app/config.py").read_text(encoding="utf-8")

    migrate = compose["services"]["api-migrate"]
    api = compose["services"]["api"]
    airflow_init = compose["services"]["airflow-init"]
    mlflow = compose["services"]["mlflow"]
    langfuse = compose["services"]["langfuse"]
    langfuse_postgres = compose["services"]["langfuse-postgres"]

    assert migrate["env_file"] == [".env"]
    assert api["env_file"] == [".env"]
    assert 'extra="ignore"' in config
    assert migrate["command"] == "alembic -c services/api/alembic.ini upgrade head"
    assert migrate["environment"]["DATABASE_URL"] == "postgresql+psycopg://dq:dq@postgres:5432/dq_observability"
    assert migrate["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert compose["services"]["postgres"]["healthcheck"]["test"] == [
        "CMD-SHELL",
        "pg_isready -U dq -d dq_observability",
    ]
    assert api["depends_on"]["api-migrate"]["condition"] == "service_completed_successfully"
    assert api["depends_on"]["mlflow"]["condition"] == "service_healthy"
    assert compose["services"]["prometheus"]["depends_on"]["api"]["condition"] == "service_healthy"
    assert airflow_init["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert "http://127.0.0.1:5000/health" in mlflow["healthcheck"]["test"][1]
    assert langfuse_postgres["healthcheck"]["test"] == [
        "CMD-SHELL",
        "pg_isready -U langfuse -d langfuse",
    ]
    assert langfuse["depends_on"]["langfuse-postgres"]["condition"] == "service_healthy"
    assert "миграции применяются автоматически сервисом `api-migrate`" in readme
    assert "cp .env.example .env" in readme


def test_airflow_gate_uses_compose_internal_api() -> None:
    dag_text = Path("airflow/dags/llmops_pretraining_gate.py").read_text(encoding="utf-8")
    gate_script = Path("scripts/llmops_gate_check.py").read_text(encoding="utf-8")

    assert not Path("airflow/dags/scripts/llmops_gate_check.py").exists()
    assert "python /opt/airflow/scripts/llmops_gate_check.py" in dag_text
    assert "/opt/airflow/dags/scripts/llmops_gate_check.py" not in dag_text
    assert "http://api:8000" in dag_text
    assert '"DQ_API_KEY"' in dag_text
    assert 'os.environ.get("DQ_API_BASE_URL", "http://localhost:8000")' in gate_script
    assert 'os.environ.get("DQ_API_KEY"' in gate_script
    assert '"X-API-Key"' in gate_script
    assert "headers=api_headers()" in gate_script
    assert "headers=api_headers(json_payload=True)" in gate_script


def test_airflow_smoke_runbook_exists() -> None:
    runbook = Path("docs/runbooks/airflow_smoke.md")

    assert runbook.exists()
    contents = runbook.read_text(encoding="utf-8")
    assert "Airflow Smoke" in contents
    assert "Проверка через CLI" in contents
    assert "Проверка через REST API" in contents
