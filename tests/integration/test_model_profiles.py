from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import Settings
from app.llm.provider import LLMResult, get_model_profiles, resolve_model_profile
from app.llm.rag_chain import run_rag_ask
from app.main import app
from app.models import ResponseLog, TraceEvent
from app.retrieval.retriever import RetrievalResult


class FakeDb:
    def __init__(self) -> None:
        self.added = []
        self.committed = False

    def get(self, *_args):
        return None

    def add(self, obj):
        self.added.append(obj)

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        self.committed = True


class FakeRetriever:
    def retrieve(self, _query: str) -> RetrievalResult:
        return RetrievalResult(
            chunks=[
                {
                    "document_id": "doc-001",
                    "chunk_id": "doc-001-chunk-0",
                    "source": "kb",
                    "text": "Customers may return unopened items within 30 days.",
                    "score": 1.0,
                    "metadata": {},
                }
            ],
            latency_ms=1,
            no_context=False,
        )


class FakeProvider:
    def generate(self, *_args) -> LLMResult:
        return LLMResult(
            raw_answer="Customers may return unopened items within 30 days. Sources: doc-001#doc-001-chunk-0",
            model_name="mock:mock-v1",
            model_version="mock-v1",
            input_tokens=10,
            output_tokens=8,
            latency_ms=1,
            finish_reason="stop",
        )


def test_models_endpoint_returns_default_model_and_safe_profile_list() -> None:
    response = TestClient(app).get("/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["default_model_profile_id"] == "mock"
    assert any(model["id"] == "mock" and model["enabled"] is True for model in payload["models"])
    assert "api_key" not in str(payload).lower()
    assert "secret" not in str(payload).lower()


def test_resolve_model_profile_rejects_unknown_and_disabled_profiles() -> None:
    settings = Settings()

    with pytest.raises(Exception) as unknown:
        resolve_model_profile(settings, "missing-profile")
    assert "unknown model_profile_id" in str(unknown.value)

    with pytest.raises(Exception) as disabled:
        resolve_model_profile(settings, "ollama_llama")
    assert "disabled" in str(disabled.value)


def test_default_and_explicit_mock_model_profiles_are_enabled() -> None:
    settings = Settings()
    profiles = {profile.id: profile for profile in get_model_profiles(settings)}

    assert resolve_model_profile(settings, None).id == "mock"
    assert resolve_model_profile(settings, "mock").id == "mock"
    assert profiles["mock"].provider == "mock"


def test_legacy_qwen_ollama_profile_id_resolves_without_public_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.llm.provider as provider

    monkeypatch.setattr(
        provider,
        "_ollama_runtime_status",
        lambda _settings: {
            "reachable": True,
            "models": ["qwen2.5:7b"],
            "base_url": "http://ollama.test:11434",
            "reason": None,
        },
    )
    settings = Settings(
        DEFAULT_MODEL_PROFILE_ID="qwen_ollama",
        MODEL_PROFILE_QWEN_OLLAMA_ENABLED=True,
        QWEN_OLLAMA_MODEL="qwen2.5:7b",
        QWEN_OLLAMA_7B_MODEL="qwen2.5:7b",
    )

    profile = resolve_model_profile(settings, "qwen_ollama")
    public_profile_ids = [item.id for item in get_model_profiles(settings)]

    assert profile.id == "qwen_ollama"
    assert profile.model_name == "qwen2.5:7b"
    assert profile.enabled is True
    assert "qwen_ollama" not in public_profile_ids
    assert "qwen_ollama_7b" in public_profile_ids


def test_docs_examples_use_concrete_qwen_profile_ids() -> None:
    from pathlib import Path

    readme = Path("README.md").read_text(encoding="utf-8")
    ui_readme = Path("services/ui/README.md").read_text(encoding="utf-8")

    assert "DEFAULT_MODEL_PROFILE_ID=qwen_ollama_7b" in readme
    assert "DEFAULT_MODEL_PROFILE_ID=qwen_ollama_7b" in ui_readme
    assert "DEFAULT_MODEL_PROFILE_ID=qwen_ollama\n" not in readme
    assert "DEFAULT_MODEL_PROFILE_ID=qwen_ollama\n" not in ui_readme


def test_run_rag_ask_returns_and_persists_selected_model_metadata(monkeypatch) -> None:
    import app.llm.rag_chain as rag_chain

    fake_db = FakeDb()
    monkeypatch.setattr(rag_chain, "build_retriever", lambda _settings: FakeRetriever())
    monkeypatch.setattr(rag_chain, "build_provider_from_profile", lambda _settings, _profile: FakeProvider())

    result = run_rag_ask(
        fake_db,
        SimpleNamespace(
            query="What is the return policy?",
            attachments=[],
            locale="en",
            session_id=None,
            user_id=None,
            model_profile_id="mock",
        ),
        Settings(),
    )

    response_log = next(obj for obj in fake_db.added if isinstance(obj, ResponseLog))
    trace_events = [obj for obj in fake_db.added if isinstance(obj, TraceEvent)]
    assert result["model_profile_id"] == "mock"
    assert result["provider"] == "mock"
    assert result["model_name"] == "mock:mock-v1"
    assert response_log.payload["model_profile_id"] == "mock"
    assert response_log.payload["provider"] == "mock"
    assert any(event.payload.get("model_profile_id") == "mock" for event in trace_events)
    assert any(event.payload.get("provider") == "mock" for event in trace_events)


def test_run_rag_ask_returns_clear_error_for_disabled_profile() -> None:
    with pytest.raises(HTTPException) as exc_info:
        run_rag_ask(
            FakeDb(),
            SimpleNamespace(
                query="What is the return policy?",
                attachments=[],
                locale="en",
                session_id=None,
                user_id=None,
                model_profile_id="ollama_llama",
            ),
            Settings(),
        )

    assert exc_info.value.status_code == 400
    assert "disabled" in str(exc_info.value.detail)
