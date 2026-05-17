from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator


with DAG(
    dag_id="quality_gate_dag",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["llmops", "quality-gate"],
) as dag:
    quality_gate = BashOperator(
        task_id="quality_gate",
        bash_command="PYTHONPATH=/opt/airflow/services/api /opt/airflow/dq_venv/bin/python /opt/airflow/scripts/quality_gate.py",
    )

    readiness_gate = BashOperator(
        task_id="readiness_gate",
        bash_command="python /opt/airflow/scripts/readiness_gate.py --base-url ${DQ_API_BASE_URL}",
    )

    quality_gate >> readiness_gate
