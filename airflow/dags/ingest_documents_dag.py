from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator


with DAG(
    dag_id="ingest_documents_dag",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["llmops", "rag", "ingestion"],
) as dag:
    ingest_documents = BashOperator(
        task_id="ingest_documents",
        bash_command="PYTHONPATH=/opt/airflow/services/api /opt/airflow/dq_venv/bin/python /opt/airflow/scripts/ingest_documents.py",
    )
