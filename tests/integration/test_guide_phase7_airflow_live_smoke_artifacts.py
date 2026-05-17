from pathlib import Path


def test_airflow_uses_separate_metadata_database_and_script_venv() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = Path("docker/airflow.Dockerfile").read_text(encoding="utf-8")
    postgres_init_sql = Path("docker/postgres/init/01-create-airflow-db.sql").read_text(encoding="utf-8")
    runbook = Path("docs/runbooks/airflow_smoke.md").read_text(encoding="utf-8")

    assert "airflow_metadata" in compose
    assert "./docker/postgres/init:/docker-entrypoint-initdb.d:ro" in compose
    assert "CREATE DATABASE airflow_metadata OWNER dq" in postgres_init_sql
    assert "автоматически создает базу `airflow_metadata`" in runbook
    assert "старом уже созданном volume" in runbook
    assert "airflow_mlflow:/opt/airflow/mlflow" in compose
    assert "DATABASE_URL: postgresql+psycopg://dq:dq@postgres:5432/dq_observability" in compose
    assert "/opt/airflow/dq_venv" in dockerfile
    assert "chmod -R g+rwX /opt/airflow/mlflow" in dockerfile
    assert "sqlalchemy>=2.0.36" in dockerfile
    assert "prometheus-client>=0.21.0" in dockerfile
    assert "great-expectations>=1.2.0" in dockerfile
    assert "mlflow>=2.19.0" in dockerfile
    assert "pymilvus>=2.5.0" in dockerfile
    assert "langfuse>=2.60.0" in dockerfile


def test_airflow_dags_use_script_venv_and_container_safe_paths() -> None:
    eval_dag = Path("airflow/dags/run_eval_suite_dag.py").read_text(encoding="utf-8")
    ingest_dag = Path("airflow/dags/ingest_documents_dag.py").read_text(encoding="utf-8")

    assert "/opt/airflow/dq_venv/bin/python" in ingest_dag
    assert "--eval-items /opt/airflow/eval/eval_items.csv" in eval_dag
    assert "--output-dir /opt/airflow/mlflow/eval_runs" in eval_dag
