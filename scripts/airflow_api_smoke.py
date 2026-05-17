from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REQUIRED_DAG_IDS = (
    "ingest_documents_dag",
    "build_embeddings_dag",
    "run_gx_dq_checks_dag",
    "run_eval_suite_dag",
    "quality_gate_dag",
)


@dataclass(frozen=True)
class AirflowApiClient:
    base_url: str
    username: str
    password: str
    timeout_seconds: int

    def get_json(self, path: str) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}{path}"
        token = base64.b64encode(f"{self.username}:{self.password}".encode("utf-8")).decode("ascii")
        request = Request(url, headers={"Accept": "application/json", "Authorization": f"Basic {token}"})
        with urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


def run_smoke(client: AirflowApiClient, required_dag_ids: tuple[str, ...]) -> dict[str, Any]:
    health = client.get_json("/health")
    dags_response = client.get_json("/api/v1/dags?limit=100")
    import_errors = client.get_json("/api/v1/importErrors")

    dag_ids = sorted(dag["dag_id"] for dag in dags_response.get("dags", []))
    missing_dags = [dag_id for dag_id in required_dag_ids if dag_id not in dag_ids]
    import_error_count = import_errors.get("total_entries", len(import_errors.get("import_errors", [])))

    failed_checks: list[str] = []
    if health.get("metadatabase", {}).get("status") != "healthy":
        failed_checks.append("metadatabase_unhealthy")
    if health.get("scheduler", {}).get("status") not in {"healthy", None}:
        failed_checks.append("scheduler_unhealthy")
    if missing_dags:
        failed_checks.append("missing_required_dags")
    if import_error_count:
        failed_checks.append("dag_import_errors")

    return {
        "status": "passed" if not failed_checks else "failed",
        "failed_checks": failed_checks,
        "health": health,
        "dag_count": len(dag_ids),
        "required_dag_ids": list(required_dag_ids),
        "missing_dag_ids": missing_dags,
        "import_error_count": import_error_count,
    }


def parse_required_dags(value: str) -> tuple[str, ...]:
    if not value.strip():
        return REQUIRED_DAG_IDS
    return tuple(item.strip() for item in value.split(",") if item.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Airflow webserver/API readiness for MVP DAG orchestration.")
    parser.add_argument("--base-url", default=os.getenv("AIRFLOW_API_BASE_URL", "http://localhost:8080"))
    parser.add_argument("--username", default=os.getenv("AIRFLOW_USERNAME", "admin"))
    parser.add_argument("--password", default=os.getenv("AIRFLOW_PASSWORD", "admin"))
    parser.add_argument("--timeout-seconds", type=int, default=int(os.getenv("AIRFLOW_API_TIMEOUT_SECONDS", "10")))
    parser.add_argument("--retries", type=int, default=int(os.getenv("AIRFLOW_API_RETRIES", "5")))
    parser.add_argument("--retry-delay-seconds", type=float, default=float(os.getenv("AIRFLOW_API_RETRY_DELAY_SECONDS", "2")))
    parser.add_argument(
        "--required-dags",
        default=os.getenv("AIRFLOW_REQUIRED_DAGS", ",".join(REQUIRED_DAG_IDS)),
        help="Comma-separated DAG IDs that must be visible through Airflow API.",
    )
    args = parser.parse_args()

    client = AirflowApiClient(
        base_url=args.base_url,
        username=args.username,
        password=args.password,
        timeout_seconds=args.timeout_seconds,
    )

    result: dict[str, Any] = {}
    for attempt in range(1, args.retries + 1):
        try:
            result = run_smoke(client, parse_required_dags(args.required_dags))
            break
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            result = {
                "status": "failed",
                "failed_checks": ["airflow_api_unavailable"],
                "attempt": attempt,
                "max_attempts": args.retries,
                "error": str(exc),
            }
            if attempt < args.retries:
                time.sleep(args.retry_delay_seconds)

    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
