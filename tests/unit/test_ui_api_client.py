from __future__ import annotations

import json
from urllib.error import HTTPError, URLError

import pytest

from services.ui.api_client import APIError, DQAPIClient, build_ask_payload, build_feedback_payload


class FakeResponse:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload.encode("utf-8")

    def close(self) -> None:
        return None


def test_ui_client_parses_successful_ask_response(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout: int):
        captured["headers"] = dict(request.header_items())
        captured["data"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(
            json.dumps(
                {
                    "request_id": "req-1",
                    "trace_id": "trace-1",
                    "answer": "answer",
                    "citations": [],
                    "scores": {"groundedness": 1.0},
                    "status": "success",
                    "model_profile_id": "mock",
                    "provider": "mock",
                    "model_name": "mock",
                    "model_version": "v1",
                    "finish_reason": "stop",
                    "scorer_version": "heuristic",
                }
            )
        )

    monkeypatch.setattr("services.ui.api_client.urlopen", fake_urlopen)
    response = DQAPIClient("http://api:8000", api_key="secret").ask(
        "What is the return policy?",
        session_id="sid",
        model_profile_id="mock",
    )

    assert response["status"] == "success"
    assert response["model_profile_id"] == "mock"
    assert captured["headers"]["X-api-key"] == "secret"
    assert captured["data"] == {
        "query": "What is the return policy?",
        "locale": "en",
        "session_id": "sid",
        "model_profile_id": "mock",
    }


def test_ui_client_parses_models_and_injects_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout: int):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        return FakeResponse(
            json.dumps(
                {
                    "default_model_profile_id": "mock",
                    "models": [
                        {
                            "id": "mock",
                            "label": "Mock model",
                            "provider": "mock",
                            "model_name": "mock-v1",
                            "enabled": True,
                        }
                    ],
                }
            )
        )

    monkeypatch.setattr("services.ui.api_client.urlopen", fake_urlopen)
    response = DQAPIClient("http://api:8000", api_key="secret").models()

    assert captured["url"] == "http://api:8000/models"
    assert captured["headers"]["X-api-key"] == "secret"
    assert response["default_model_profile_id"] == "mock"
    assert response["models"][0]["id"] == "mock"


def test_ui_client_models_handles_backend_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(_request, timeout: int):
        raise HTTPError(
            url="http://api:8000/models",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=FakeResponse('{"detail":"invalid api key"}'),
        )

    monkeypatch.setattr("services.ui.api_client.urlopen", fake_urlopen)

    with pytest.raises(APIError) as exc_info:
        DQAPIClient("http://api:8000").models()

    assert exc_info.value.status_code == 401
    assert exc_info.value.endpoint == "/models"


def test_ui_client_raises_structured_backend_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(_request, timeout: int):
        raise HTTPError(
            url="http://api:8000/ask",
            code=422,
            msg="Unprocessable Entity",
            hdrs=None,
            fp=FakeResponse('{"detail":"validation error"}'),
        )

    monkeypatch.setattr("services.ui.api_client.urlopen", fake_urlopen)

    with pytest.raises(APIError) as exc_info:
        DQAPIClient("http://api:8000").ask("")

    assert exc_info.value.status_code == 422
    assert exc_info.value.endpoint == "/ask"
    assert "validation error" in exc_info.value.message


def test_ui_client_handles_backend_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(_request, timeout: int):
        raise URLError("connection refused")

    monkeypatch.setattr("services.ui.api_client.urlopen", fake_urlopen)

    with pytest.raises(APIError) as exc_info:
        DQAPIClient("http://api:8000").health()

    assert exc_info.value.status_code is None
    assert "connection refused" in exc_info.value.message


def test_feedback_payload_matches_backend_schema() -> None:
    payload = build_feedback_payload(
        request_id="req-1",
        trace_id="trace-1",
        rating=4,
        helpful=True,
        comment=" useful ",
    )

    assert payload == {
        "request_id": "req-1",
        "trace_id": "trace-1",
        "rating": 4,
        "comment": "useful",
        "payload": {"source": "streamlit_ui", "helpful": True},
    }


def test_trace_loading_uses_trace_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout: int):
        captured["url"] = request.full_url
        return FakeResponse('[{"span_name":"retrieval","status":"success"}]')

    monkeypatch.setattr("services.ui.api_client.urlopen", fake_urlopen)
    trace = DQAPIClient("http://api:8000").trace("trace-1")

    assert captured["url"] == "http://api:8000/trace/trace-1"
    assert trace[0]["span_name"] == "retrieval"


def test_ask_payload_omits_empty_optional_fields() -> None:
    assert build_ask_payload("q", session_id="", user_id="", locale="en") == {"query": "q", "locale": "en"}


def test_ask_payload_includes_model_profile_only_when_provided() -> None:
    assert build_ask_payload("q", model_profile_id="mock") == {
        "query": "q",
        "locale": "en",
        "model_profile_id": "mock",
    }
    assert build_ask_payload("q", model_profile_id="") == {"query": "q", "locale": "en"}


def test_ui_client_prometheus_query_success(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout: int):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        return FakeResponse('{"status":"success","data":{"result":[{"value":[1,"2"]}]}}')

    monkeypatch.setattr("services.ui.api_client.urlopen", fake_urlopen)
    payload = DQAPIClient("http://api:8000", api_key="secret", prometheus_url="http://prometheus:9090").prometheus_query(
        "up"
    )

    assert captured["url"] == "http://prometheus:9090/api/v1/query?query=up"
    assert payload["status"] == "success"


def test_ui_client_does_not_send_backend_api_key_to_prometheus(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout: int):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        return FakeResponse('{"status":"success","data":{"result":[]}}')

    monkeypatch.setattr("services.ui.api_client.urlopen", fake_urlopen)
    DQAPIClient("http://api:8000", api_key="secret", prometheus_url="http://prometheus:9090").prometheus_query("up")

    assert captured["url"] == "http://prometheus:9090/api/v1/query?query=up"
    assert "X-api-key" not in captured["headers"]
    assert "X-API-Key" not in captured["headers"]


def test_ui_client_prometheus_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(_request, timeout: int):
        raise URLError("connection refused")

    monkeypatch.setattr("services.ui.api_client.urlopen", fake_urlopen)

    with pytest.raises(APIError) as exc_info:
        DQAPIClient("http://api:8000", prometheus_url="http://prometheus:9090").prometheus_query("up")

    assert "connection refused" in exc_info.value.message


@pytest.mark.parametrize(
    ("method_name", "payload", "expected"),
    [
        ("dq_latest", {"run_id": None, "status": "unknown", "check_count": 0, "passed_count": 0, "failed_count": 0, "results": []}, "unknown"),
        ("eval_runs", [{"id": "run-1", "status": "completed"}], "completed"),
        ("quality_gate_latest", {"id": "gate-1", "gate_status": "failed", "failed_checks": [], "metrics_snapshot": {}}, "failed"),
        ("traces", {"traces": [{"trace_id": "trace-1", "status": "success"}]}, "success"),
    ],
)
def test_ui_client_new_observability_methods_parse_responses(
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    payload: dict | list,
    expected: str,
) -> None:
    def fake_urlopen(_request, timeout: int):
        return FakeResponse(json.dumps(payload))

    monkeypatch.setattr("services.ui.api_client.urlopen", fake_urlopen)
    response = getattr(DQAPIClient("http://api:8000"), method_name)()

    if method_name == "eval_runs":
        assert response[0]["status"] == expected
    elif method_name == "quality_gate_latest":
        assert response["gate_status"] == expected
    elif method_name == "traces":
        assert response["traces"][0]["status"] == expected
    else:
        assert response["status"] == expected
