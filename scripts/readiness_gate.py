from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def fetch_readiness(base_url: str, timeout_seconds: int) -> dict:
    url = f"{base_url.rstrip('/')}/llmops/readiness"
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail CI/CD when LLMOps readiness is not passed.")
    parser.add_argument("--base-url", default=os.getenv("DQ_API_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--timeout-seconds", type=int, default=10)
    args = parser.parse_args()

    try:
        result = fetch_readiness(args.base_url, args.timeout_seconds)
    except (HTTPError, URLError, TimeoutError) as exc:
        print(json.dumps({"status": "failed", "failed_signals": ["readiness_api_unavailable"], "error": str(exc)}))
        return 1

    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
