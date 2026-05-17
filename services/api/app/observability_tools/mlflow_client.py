from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import Settings


@dataclass(frozen=True, slots=True)
class MLflowEvalRunContract:
    run_name: str
    model_name: str
    model_version: str
    prompt_version: str
    metrics: dict[str, float]
    artifacts: dict[str, str]
    params: dict[str, Any]


class MLflowTrackingClient:
    """Optional MLflow SDK integration with local MVP fallback.

    The MVP can run without the `mlflow` Python package or a tracking server.
    When `MLFLOW_ENABLED=true` and the SDK is installed, eval metrics and
    artifacts are logged to the configured tracking URI.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _load_mlflow(self) -> Any | None:
        try:
            return importlib.import_module("mlflow")
        except ImportError:
            return None

    def status(self) -> dict[str, Any]:
        sdk_available = self._load_mlflow() is not None
        if not self.settings.mlflow_enabled:
            mode = "contract_only"
        elif sdk_available:
            mode = "runtime"
        else:
            mode = "sdk_missing"
        return {
            "name": "mlflow",
            "enabled": self.settings.mlflow_enabled,
            "mode": mode,
            "tracking_uri": self.settings.mlflow_tracking_uri,
            "sdk_available": sdk_available,
            "required_for_mvp": False,
            "fallback": "postgres_eval_runs_and_local_artifacts",
            "capabilities": ["eval_metrics", "params", "artifacts", "run_tags"],
        }

    def eval_run_contract(self, run: MLflowEvalRunContract) -> dict[str, Any]:
        return {
            "tool_name": "mlflow_eval_tracker",
            "action": "log_eval_run",
            "status": "not_executed" if not self.settings.mlflow_enabled else self.status()["mode"],
            "tracking_uri": self.settings.mlflow_tracking_uri,
            "run": {
                "run_name": run.run_name,
                "model_name": run.model_name,
                "model_version": run.model_version,
                "prompt_version": run.prompt_version,
                "metric_names": sorted(run.metrics),
                "artifact_names": sorted(run.artifacts),
                "params": run.params,
            },
            "fallback": "postgres_eval_runs_and_local_artifacts",
        }

    def log_eval_run(self, run: MLflowEvalRunContract) -> dict[str, Any]:
        if not self.settings.mlflow_enabled:
            return {"status": "skipped", "reason": "mlflow_disabled"}

        mlflow = self._load_mlflow()
        if mlflow is None:
            return {"status": "skipped", "reason": "mlflow_sdk_missing"}

        try:
            mlflow.set_tracking_uri(self.settings.mlflow_tracking_uri)
            with mlflow.start_run(run_name=run.run_name) as active_run:
                mlflow.set_tags(
                    {
                        "model_name": run.model_name,
                        "model_version": run.model_version,
                        "prompt_version": run.prompt_version,
                        "component": "llmops_dq_eval",
                    }
                )
                mlflow.log_params({key: str(value) for key, value in run.params.items()})
                mlflow.log_metrics({key: float(value) for key, value in run.metrics.items()})
                for artifact_name, artifact_path in run.artifacts.items():
                    path = Path(artifact_path)
                    if path.exists():
                        mlflow.log_artifact(str(path), artifact_path=artifact_name)
                return {"status": "logged", "mlflow_run_id": active_run.info.run_id}
        except Exception as exc:  # pragma: no cover - defensive around optional external SDK/server.
            return {"status": "failed", "reason": type(exc).__name__, "message": str(exc)}
