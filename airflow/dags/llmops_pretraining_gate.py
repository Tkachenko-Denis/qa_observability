from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator


with DAG(
    dag_id="llmops_pretraining_gate",
    description="Pre-training gate that checks DQ summary before linking an MLflow run",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["llmops", "dq", "gate"],
) as dag:
    gate_check = BashOperator(
        task_id="gate_check",
        bash_command="python /opt/airflow/scripts/llmops_gate_check.py",
        env={
            "DQ_API_BASE_URL": "{{ var.value.dq_api_base_url | default('http://api:8000') }}",
            "DQ_API_KEY": "{{ var.value.dq_api_key | default('', true) }}",
            "DATASET_ID": "{{ dag_run.conf['dataset_id'] }}",
            "DATASET_VERSION_ID": "{{ dag_run.conf['dataset_version_id'] }}",
            "MLFLOW_RUN_ID": "{{ dag_run.conf.get('mlflow_run_id', '') }}",
            "MLFLOW_RUN_NAME": "{{ dag_run.conf.get('mlflow_run_name', '') }}",
            "RUN_TYPE": "{{ dag_run.conf.get('run_type', 'train') }}",
        },
    )
