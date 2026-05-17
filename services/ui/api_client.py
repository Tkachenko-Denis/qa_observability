from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class APIError(Exception):
    endpoint: str
    message: str
    status_code: int | None = None
    raw_response: str | None = None

    def __str__(self) -> str:
        status = f"HTTP {self.status_code}" if self.status_code is not None else "request error"
        return f"{status} at {self.endpoint}: {self.message}"


class DQAPIClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: int = 30,
        prometheus_url: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip() if api_key else None
        self.timeout_seconds = timeout_seconds
        self.prometheus_url = prometheus_url.rstrip("/") if prometheus_url else None

    def health(self) -> dict[str, Any]:
        return self._request_json("GET", "/health")

    def readiness(self) -> dict[str, Any]:
        return self._request_json("GET", "/llmops/readiness")

    def integrations(self) -> list[dict[str, Any]]:
        payload = self._request_json("GET", "/integrations")
        if not isinstance(payload, list):
            raise APIError("/integrations", "expected JSON list", raw_response=json.dumps(payload))
        return payload

    def models(self) -> dict[str, Any]:
        payload = self._request_json("GET", "/models")
        if not isinstance(payload, dict):
            raise APIError("/models", "expected JSON object", raw_response=json.dumps(payload))
        models = payload.get("models")
        if not isinstance(models, list):
            raise APIError("/models", "expected models list", raw_response=json.dumps(payload))
        return payload

    def ask(
        self,
        query: str,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        locale: str = "en",
        model_profile_id: str | None = None,
    ) -> dict[str, Any]:
        payload = build_ask_payload(
            query,
            session_id=session_id,
            user_id=user_id,
            locale=locale,
            model_profile_id=model_profile_id,
        )
        response = self._request_json("POST", "/ask", payload)
        if not isinstance(response, dict):
            raise APIError("/ask", "expected JSON object", raw_response=json.dumps(response))
        return response

    def trace(self, trace_id: str) -> list[dict[str, Any]]:
        if not trace_id.strip():
            raise APIError("/trace/{trace_id}", "trace_id is required")
        payload = self._request_json("GET", f"/trace/{trace_id.strip()}")
        if not isinstance(payload, list):
            raise APIError(f"/trace/{trace_id}", "expected JSON list", raw_response=json.dumps(payload))
        return payload

    def traces(self, limit: int = 50) -> dict[str, Any]:
        payload = self._request_json("GET", f"/traces?limit={limit}")
        if not isinstance(payload, dict):
            raise APIError("/traces", "expected JSON object", raw_response=json.dumps(payload))
        return payload

    def dq_latest(self) -> dict[str, Any]:
        payload = self._request_json("GET", "/dq/results/latest")
        if not isinstance(payload, dict):
            raise APIError("/dq/results/latest", "expected JSON object", raw_response=json.dumps(payload))
        return payload

    def dq_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        payload = self._request_json("GET", f"/dq/runs?limit={limit}")
        if not isinstance(payload, list):
            raise APIError("/dq/runs", "expected JSON list", raw_response=json.dumps(payload))
        return payload

    def dq_run(self, run_id: str) -> dict[str, Any]:
        payload = self._request_json("GET", f"/dq/runs/{run_id}")
        if not isinstance(payload, dict):
            raise APIError(f"/dq/runs/{run_id}", "expected JSON object", raw_response=json.dumps(payload))
        return payload

    def eval_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        payload = self._request_json("GET", f"/eval/runs?limit={limit}")
        if not isinstance(payload, list):
            raise APIError("/eval/runs", "expected JSON list", raw_response=json.dumps(payload))
        return payload

    def eval_run(self, run_id: str) -> dict[str, Any]:
        payload = self._request_json("GET", f"/eval/runs/{run_id}")
        if not isinstance(payload, dict):
            raise APIError(f"/eval/runs/{run_id}", "expected JSON object", raw_response=json.dumps(payload))
        return payload

    def eval_scores(self, run_id: str, limit: int = 500) -> list[dict[str, Any]]:
        payload = self._request_json("GET", f"/eval/runs/{run_id}/scores?limit={limit}")
        if not isinstance(payload, list):
            raise APIError(f"/eval/runs/{run_id}/scores", "expected JSON list", raw_response=json.dumps(payload))
        return payload

    def quality_gates(self, limit: int = 50) -> list[dict[str, Any]]:
        payload = self._request_json("GET", f"/quality-gates?limit={limit}")
        if not isinstance(payload, list):
            raise APIError("/quality-gates", "expected JSON list", raw_response=json.dumps(payload))
        return payload

    def quality_gate_latest(self) -> dict[str, Any]:
        payload = self._request_json("GET", "/quality-gates/latest")
        if not isinstance(payload, dict):
            raise APIError("/quality-gates/latest", "expected JSON object", raw_response=json.dumps(payload))
        return payload

    def prometheus_query(self, query: str) -> dict[str, Any]:
        return self._prometheus_json("/api/v1/query", {"query": query})

    def feedback(
        self,
        *,
        request_id: str | None,
        trace_id: str | None,
        rating: int | None,
        helpful: bool | None,
        comment: str | None,
    ) -> dict[str, Any]:
        payload = build_feedback_payload(
            request_id=request_id,
            trace_id=trace_id,
            rating=rating,
            helpful=helpful,
            comment=comment,
        )
        response = self._request_json("POST", "/feedback", payload)
        if not isinstance(response, dict):
            raise APIError("/feedback", "expected JSON object", raw_response=json.dumps(response))
        return response

    def _request_json(self, method: str, endpoint: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | list[Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = self._headers(json_payload=payload is not None)
        request = Request(f"{self.base_url}{endpoint}", data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as exc:
            raw_body = exc.read().decode("utf-8")
            raise APIError(
                endpoint,
                _error_message_from_body(raw_body) or exc.reason,
                status_code=exc.code,
                raw_response=raw_body,
            ) from exc
        except URLError as exc:
            raise APIError(endpoint, str(exc.reason), raw_response=str(exc)) from exc
        except TimeoutError as exc:
            raise APIError(endpoint, "request timed out", raw_response=str(exc)) from exc

        if not raw_body.strip():
            raise APIError(endpoint, "empty response")
        try:
            return json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise APIError(endpoint, "response is not valid JSON", raw_response=raw_body) from exc

    def _prometheus_json(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if not self.prometheus_url:
            raise APIError(endpoint, "Prometheus URL is not configured")
        url = f"{self.prometheus_url}{endpoint}?{urlencode(params)}"
        request = Request(url, headers={}, method="GET")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as exc:
            raw_body = exc.read().decode("utf-8")
            raise APIError(endpoint, _error_message_from_body(raw_body) or exc.reason, exc.code, raw_body) from exc
        except URLError as exc:
            raise APIError(endpoint, str(exc.reason), raw_response=str(exc)) from exc
        except TimeoutError as exc:
            raise APIError(endpoint, "request timed out", raw_response=str(exc)) from exc
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise APIError(endpoint, "response is not valid JSON", raw_response=raw_body) from exc
        if not isinstance(payload, dict):
            raise APIError(endpoint, "expected JSON object", raw_response=raw_body)
        return payload

    def _headers(self, *, json_payload: bool) -> dict[str, str]:
        headers: dict[str, str] = {}
        if json_payload:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers


def build_ask_payload(
    query: str,
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    locale: str = "en",
    model_profile_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"query": query, "locale": locale or "en"}
    if session_id and session_id.strip():
        payload["session_id"] = session_id.strip()
    if user_id and user_id.strip():
        payload["user_id"] = user_id.strip()
    if model_profile_id and model_profile_id.strip():
        payload["model_profile_id"] = model_profile_id.strip()
    return payload


def build_feedback_payload(
    *,
    request_id: str | None,
    trace_id: str | None,
    rating: int | None,
    helpful: bool | None,
    comment: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"payload": {"source": "streamlit_ui"}}
    if request_id:
        payload["request_id"] = request_id
    if trace_id:
        payload["trace_id"] = trace_id
    if rating is not None:
        payload["rating"] = rating
    if comment and comment.strip():
        payload["comment"] = comment.strip()
    if helpful is not None:
        payload["payload"]["helpful"] = helpful
    return payload


def _error_message_from_body(raw_body: str) -> str | None:
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return raw_body.strip() or None
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str):
        return detail
    if detail is not None:
        return json.dumps(detail)
    return json.dumps(payload)
