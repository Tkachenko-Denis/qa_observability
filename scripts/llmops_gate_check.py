from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def api_headers(*, json_payload: bool = False) -> dict[str, str]:
    headers: dict[str, str] = {}
    if json_payload:
        headers["Content-Type"] = "application/json"
    api_key = os.environ.get("DQ_API_KEY", "").strip()
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def fetch_json(url: str) -> dict:
    request = Request(url, headers=api_headers(), method="GET")
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=api_headers(json_payload=True),
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    api_base = os.environ.get("DQ_API_BASE_URL", "http://localhost:8000")
    dataset_id = os.environ["DATASET_ID"]
    dataset_version_id = os.environ["DATASET_VERSION_ID"]
    mlflow_run_id = os.environ.get("MLFLOW_RUN_ID")
    run_type = os.environ.get("RUN_TYPE", "train")

    gate = fetch_json(f"{api_base}/datasets/{dataset_id}/versions/{dataset_version_id}/gate")
    print(json.dumps(gate, indent=2))

    if mlflow_run_id:
        latest_runs = gate.get("latest_categories", {})
        representative_dq_run_id = None
        if latest_runs:
            representative_dq_run_id = next(iter(latest_runs.values())).get("dq_run_id")

        link_payload = {
            "dataset_id": dataset_id,
            "dataset_version_id": dataset_version_id,
            "dq_run_id": representative_dq_run_id,
            "external_system": "mlflow",
            "external_run_id": mlflow_run_id,
            "run_type": run_type,
            "status": "linked" if gate["publish_allowed"] else "blocked_by_gate",
            "run_name": os.environ.get("MLFLOW_RUN_NAME"),
            "details": {
                "publish_allowed": gate["publish_allowed"],
                "hard_gate_result": gate["hard_gate_result"],
                "soft_gate_result": gate["soft_gate_result"],
            },
        }
        created = post_json(f"{api_base}/llmops/mlflow/link", link_payload)
        print(json.dumps(created, indent=2))

    return 0 if gate["publish_allowed"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HTTPError, URLError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
