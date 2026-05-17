FROM apache/airflow:2.10.5-python3.11

RUN python -m venv /opt/airflow/dq_venv && \
    /opt/airflow/dq_venv/bin/pip install --no-cache-dir \
    "sqlalchemy>=2.0.36" \
    "psycopg[binary]>=3.2.0" \
    "pydantic-settings>=2.6.0" \
    "prometheus-client>=0.21.0" \
    "pyyaml>=6.0.2" \
    "python-json-logger>=2.0.7" \
    "great-expectations>=1.2.0" \
    "mlflow>=2.19.0" \
    "pymilvus>=2.5.0" \
    "langfuse>=2.60.0"

USER root

RUN mkdir -p /opt/airflow/mlflow/eval_runs && \
    chown -R airflow:0 /opt/airflow/mlflow && \
    chmod -R g+rwX /opt/airflow/mlflow

USER airflow
