from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator


with DAG(
    dag_id="build_embeddings_dag",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["llmops", "rag", "embeddings"],
) as dag:
    bootstrap_milvus = BashOperator(
        task_id="bootstrap_milvus",
        bash_command="PYTHONPATH=/opt/airflow/services/api /opt/airflow/dq_venv/bin/python /opt/airflow/scripts/bootstrap_milvus.py",
    )

    build_embeddings = BashOperator(
        task_id="build_embeddings",
        bash_command="PYTHONPATH=/opt/airflow/services/api /opt/airflow/dq_venv/bin/python /opt/airflow/scripts/build_index.py",
    )

    bootstrap_milvus >> build_embeddings
