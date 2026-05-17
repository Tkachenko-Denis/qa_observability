from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator


with DAG(
    dag_id="run_eval_suite_dag",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["llmops", "eval"],
) as dag:
    run_eval = BashOperator(
        task_id="run_eval",
        bash_command=(
            "PYTHONPATH=/opt/airflow/services/api /opt/airflow/dq_venv/bin/python "
            "/opt/airflow/scripts/run_eval.py "
            "--eval-items /opt/airflow/eval/eval_items.csv "
            "--output-dir /opt/airflow/mlflow/eval_runs"
        ),
    )
