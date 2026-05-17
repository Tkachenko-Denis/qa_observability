from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UISettings:
    backend_url: str = "http://localhost:8000"
    prometheus_url: str = "http://localhost:9090"
    grafana_url: str = "http://localhost:3000"
    mlflow_url: str = "http://localhost:5000"
    langfuse_url: str = "http://localhost:3010"
    airflow_url: str = "http://localhost:8080"
    request_timeout_seconds: int = 30


def get_settings() -> UISettings:
    return UISettings(
        backend_url=os.getenv("UI_BACKEND_URL", "http://localhost:8000").rstrip("/"),
        prometheus_url=os.getenv("UI_PROMETHEUS_URL", "http://localhost:9090").rstrip("/"),
        grafana_url=os.getenv("UI_GRAFANA_URL", "http://localhost:3000").rstrip("/"),
        mlflow_url=os.getenv("UI_MLFLOW_URL", "http://localhost:5000").rstrip("/"),
        langfuse_url=os.getenv("UI_LANGFUSE_URL", "http://localhost:3010").rstrip("/"),
        airflow_url=os.getenv("UI_AIRFLOW_URL", "http://localhost:8080").rstrip("/"),
        request_timeout_seconds=int(os.getenv("UI_REQUEST_TIMEOUT_SECONDS", "30")),
    )
