from fastapi.testclient import TestClient
from types import SimpleNamespace

from app.config import Settings
from app.llm.provider import LLMResult
from app.llm.rag_chain import prepare_persisted_input, prepare_persisted_output, run_rag_ask
from app.main import app
from app.models import Message, ResponseLog
from app.retrieval.retriever import RetrievalResult
from app.security import contains_pii, mask_pii, should_skip_auth


def test_pii_masking_covers_email_and_phone() -> None:
    payload = {
        "query": "Contact alice@example.com or +1 202 555 0199",
        "nested": ["bob@example.org"],
    }

    masked = mask_pii(payload)

    assert masked["query"] == "Contact [EMAIL] or [PHONE]"
    assert masked["nested"] == ["[EMAIL]"]
    assert contains_pii(payload) is True
    assert contains_pii(masked) is False


def test_security_contract_is_exposed_in_api_schema() -> None:
    client = TestClient(app)

    schema = client.get("/openapi.json").json()

    assert "/audit/events" in schema["paths"]
    assert should_skip_auth("/health") is True
    assert should_skip_auth("/metrics") is True
    assert should_skip_auth("/ask") is False


def test_ask_persistence_masks_email_and_phone_by_default() -> None:
    persisted = prepare_persisted_input(
        "Contact alice@example.com or +1 202 555 0199",
        "Contact alice@example.com or +1 202 555 0199",
        [{"note": "backup bob@example.org"}],
        store_raw_input=False,
    )

    assert persisted["query"] == "Contact [EMAIL] or [PHONE]"
    assert persisted["normalized_query"] == "Contact [EMAIL] or [PHONE]"
    assert persisted["attachments"] == [{"note": "backup [EMAIL]"}]
    assert persisted["pii_detected"] is True
    assert persisted["raw_input_stored"] is False
    assert contains_pii(persisted["query"]) is False


def test_ask_persistence_can_store_raw_input_only_when_explicitly_enabled() -> None:
    persisted = prepare_persisted_input(
        "Contact alice@example.com",
        "Contact alice@example.com",
        [],
        store_raw_input=True,
    )

    assert persisted["query"] == "Contact alice@example.com"
    assert persisted["normalized_query"] == "Contact alice@example.com"
    assert persisted["pii_detected"] is True
    assert persisted["raw_input_stored"] is True


def test_ask_output_persistence_masks_email_and_phone_by_default() -> None:
    persisted = prepare_persisted_output(
        "Contact alice@example.com or +1 202 555 0199. Sources: doc-001#doc-001-chunk-0",
        store_raw_output=False,
    )

    assert persisted["answer"] == "Contact [EMAIL] or [PHONE]. Sources: doc-001#doc-001-chunk-0"
    assert persisted["pii_detected"] is True
    assert persisted["raw_output_stored"] is False
    assert contains_pii(persisted["answer"]) is False


def test_run_rag_ask_persists_masked_assistant_answer_and_message(monkeypatch) -> None:
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
                raw_answer=(
                    "Customers may return unopened items within 30 days. "
                    "Contact alice@example.com or +1 202 555 0199. "
                    "Sources: doc-001#doc-001-chunk-0"
                ),
                model_name="fake",
                model_version="fake-v1",
                input_tokens=10,
                output_tokens=12,
                latency_ms=1,
                finish_reason="stop",
            )

    import app.llm.rag_chain as rag_chain

    fake_db = FakeDb()
    monkeypatch.setattr(rag_chain, "build_retriever", lambda _settings: FakeRetriever())
    monkeypatch.setattr(rag_chain, "build_provider_from_profile", lambda _settings, _profile: FakeProvider())

    result = run_rag_ask(
        fake_db,
        SimpleNamespace(query="What is the return policy?", attachments=[], locale="en", session_id=None, user_id=None),
        Settings(STORE_RAW_OUTPUT=False),
    )

    response_log = next(obj for obj in fake_db.added if isinstance(obj, ResponseLog))
    assistant_message = next(
        obj for obj in fake_db.added if isinstance(obj, Message) and obj.role == "assistant"
    )
    assert result["answer"].count("alice@example.com") == 1
    assert response_log.answer == (
        "Customers may return unopened items within 30 days. "
        "Contact [EMAIL] or [PHONE]. "
        "Sources: doc-001#doc-001-chunk-0"
    )
    assert assistant_message.content == response_log.answer
    assert response_log.payload["pii_detected"] is True
    assert response_log.payload["raw_output_stored"] is False
    assert response_log.payload["model_profile_id"] == "mock"
    assert response_log.payload["provider"] == "mock"
    assert assistant_message.payload["pii_detected"] is True
    assert contains_pii(response_log.answer) is False
