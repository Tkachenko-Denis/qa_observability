from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator


with DAG(
    dag_id="run_gx_dq_checks_dag",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["llmops", "dq", "great-expectations"],
) as dag:
    run_gx_dq_checks = BashOperator(
        task_id="run_gx_dq_checks",
        bash_command="PYTHONPATH=/opt/airflow/services/api /opt/airflow/dq_venv/bin/python /opt/airflow/scripts/run_gx_dq_checks.py",
    )
