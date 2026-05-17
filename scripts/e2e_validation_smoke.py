from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TIMEOUT_SECONDS = 120


class SmokeFailure(RuntimeError):
    pass


def request_json(
    method: str,
    base_url: str,
    path: str,
    payload: dict[str, Any] | None = None,
    api_key: str | None = None,
    timeout_seconds: int = 30,
) -> dict[str, Any] | list[Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    request = Request(f"{base_url.rstrip('/')}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise SmokeFailure(f"{method} {path} failed with HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise SmokeFailure(f"{method} {path} failed: {exc.reason}") from exc


def request_text(
    method: str,
    base_url: str,
    path: str,
    api_key: str | None = None,
    timeout_seconds: int = 30,
) -> str:
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    request = Request(f"{base_url.rstrip('/')}{path}", headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise SmokeFailure(f"{method} {path} failed with HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise SmokeFailure(f"{method} {path} failed: {exc.reason}") from exc


def run_python_script(script_path: str, allowed_exit_codes: set[int] | None = None) -> dict[str, Any]:
    allowed = allowed_exit_codes or {0}
    env = os.environ.copy()
    pythonpath = str(PROJECT_ROOT / "services" / "api")
    env["PYTHONPATH"] = pythonpath if not env.get("PYTHONPATH") else f"{pythonpath}{os.pathsep}{env['PYTHONPATH']}"
    completed = subprocess.run(
        [sys.executable, script_path],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    parsed = parse_json_output(completed.stdout)
    if completed.returncode not in allowed:
        raise SmokeFailure(
            f"{script_path} exited with {completed.returncode}; stdout={completed.stdout}; stderr={completed.stderr}"
        )
    return {
        "script": script_path,
        "exit_code": completed.returncode,
        "stdout_json": parsed,
        "stderr": completed.stderr.strip(),
    }


def parse_json_output(raw_output: str) -> dict[str, Any]:
    stripped = raw_output.strip()
    if not stripped:
        raise SmokeFailure("script produced empty stdout")
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise SmokeFailure(f"script stdout is not JSON: {raw_output}") from None
        return json.loads(stripped[start : end + 1])


def assert_keys(name: str, payload: dict[str, Any], required_keys: set[str]) -> None:
    missing = sorted(required_keys - set(payload))
    if missing:
        raise SmokeFailure(f"{name} missing keys: {missing}")


def main() -> int:
    parser = argparse.ArgumentParser(description="End-to-end MVP validation smoke for live API and local pipeline scripts.")
    parser.add_argument("--base-url", default=os.environ.get("DQ_API_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--api-key", default=os.environ.get("DQ_API_KEY"))
    parser.add_argument(
        "--require-success-ask",
        action="store_true",
        help="Fail the smoke run when /ask returns a status other than success.",
    )
    args = parser.parse_args()

    started = time.perf_counter()
    steps: dict[str, Any] = {}

    health = request_json("GET", args.base_url, "/health", api_key=args.api_key)
    if not isinstance(health, dict) or health.get("status") != "ok":
        raise SmokeFailure(f"/health returned unexpected payload: {health}")
    steps["health"] = health

    ask = request_json(
        "POST",
        args.base_url,
        "/ask",
        {
            "query": "What is the return policy?",
            "user_id": "e2e-smoke",
            "locale": "en",
            "attachments": [],
        },
        api_key=args.api_key,
    )
    if not isinstance(ask, dict):
        raise SmokeFailure(f"/ask returned non-object payload: {ask}")
    assert_keys("ask", ask, {"request_id", "trace_id", "answer", "citations", "scores", "status"})
    if ask["status"] not in {"success", "failed"}:
        raise SmokeFailure(f"/ask returned unexpected status: {ask['status']}")
    if args.require_success_ask and ask["status"] != "success":
        raise SmokeFailure(f"/ask returned status={ask['status']} while --require-success-ask is enabled")
    steps["ask"] = {
        "request_id": ask["request_id"],
        "trace_id": ask["trace_id"],
        "status": ask["status"],
        "citation_count": len(ask.get("citations", [])),
        "score_keys": sorted(ask.get("scores", {}).keys()),
    }

    trace = request_json("GET", args.base_url, f"/trace/{ask['trace_id']}", api_key=args.api_key)
    if not isinstance(trace, list) or not trace:
        raise SmokeFailure(f"/trace/{ask['trace_id']} returned no events")
    span_names = {str(event.get("span_name")) for event in trace if isinstance(event, dict)}
    required_spans = {"input_normalization", "retrieval", "prompt_assembly", "llm_call", "validation", "response_delivery"}
    missing_spans = sorted(required_spans - span_names)
    if missing_spans:
        raise SmokeFailure(f"trace missing spans: {missing_spans}")
    steps["trace"] = {"event_count": len(trace), "span_names": sorted(span_names)}

    metrics = request_text("GET", args.base_url, "/metrics", api_key=args.api_key)
    required_metric_tokens = ["http_requests_total", "retrieval_latency_seconds", "llm_latency_seconds"]
    missing_metrics = [token for token in required_metric_tokens if token not in metrics]
    if missing_metrics:
        raise SmokeFailure(f"/metrics missing tokens: {missing_metrics}")
    steps["metrics"] = {"checked_tokens": required_metric_tokens}

    feedback = request_json(
        "POST",
        args.base_url,
        "/feedback",
        {
            "request_id": ask["request_id"],
            "trace_id": ask["trace_id"],
            "rating": 5,
            "comment": "e2e smoke feedback",
            "payload": {"source": "scripts/e2e_validation_smoke.py"},
        },
        api_key=args.api_key,
    )
    if not isinstance(feedback, dict):
        raise SmokeFailure(f"/feedback returned non-object payload: {feedback}")
    assert_keys("feedback", feedback, {"id", "request_id", "trace_id", "rating"})
    steps["feedback"] = {"id": feedback["id"], "rating": feedback["rating"]}

    run_eval = run_python_script("scripts/run_eval.py")
    assert_keys("run_eval.py", run_eval["stdout_json"], {"eval_run_id", "item_count", "metrics", "artifacts"})
    steps["run_eval.py"] = {
        "exit_code": run_eval["exit_code"],
        "eval_run_id": run_eval["stdout_json"]["eval_run_id"],
        "item_count": run_eval["stdout_json"]["item_count"],
    }

    gx = run_python_script("scripts/run_gx_dq_checks.py", allowed_exit_codes={0, 1})
    assert_keys("run_gx_dq_checks.py", gx["stdout_json"], {"run_id", "status", "check_count", "failed_check_count"})
    if gx["stdout_json"]["status"] not in {"passed", "failed"}:
        raise SmokeFailure(f"run_gx_dq_checks.py returned unexpected status: {gx['stdout_json']['status']}")
    steps["run_gx_dq_checks.py"] = {
        "exit_code": gx["exit_code"],
        "run_id": gx["stdout_json"]["run_id"],
        "status": gx["stdout_json"]["status"],
        "failed_check_count": gx["stdout_json"]["failed_check_count"],
    }

    gate = run_python_script("scripts/quality_gate.py", allowed_exit_codes={0, 1})
    assert_keys("quality_gate.py", gate["stdout_json"], {"gate_status", "failed_checks", "metrics_snapshot"})
    if gate["stdout_json"]["gate_status"] not in {"passed", "failed"}:
        raise SmokeFailure(f"quality_gate.py returned unexpected status: {gate['stdout_json']['gate_status']}")
    steps["quality_gate.py"] = {
        "exit_code": gate["exit_code"],
        "gate_status": gate["stdout_json"]["gate_status"],
        "failed_checks": gate["stdout_json"]["failed_checks"],
    }

    readiness = request_json("GET", args.base_url, "/llmops/readiness", api_key=args.api_key)
    if not isinstance(readiness, dict):
        raise SmokeFailure(f"/llmops/readiness returned non-object payload: {readiness}")
    assert_keys("llmops_readiness", readiness, {"status", "failed_signals", "latest_eval_run", "latest_dq_run", "latest_quality_gate"})
    if readiness["status"] not in {"passed", "failed", "unknown"}:
        raise SmokeFailure(f"/llmops/readiness returned unexpected status: {readiness['status']}")
    steps["llmops_readiness"] = {
        "status": readiness["status"],
        "failed_signals": readiness["failed_signals"],
    }

    output = {
        "status": "passed",
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "base_url": args.base_url,
        "steps": steps,
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SmokeFailure, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2), file=sys.stderr)
        raise SystemExit(1)
