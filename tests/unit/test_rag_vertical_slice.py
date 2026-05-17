from pathlib import Path
from types import SimpleNamespace

from app.llm.prompts import assemble_prompt, default_rag_prompt
from app.llm.provider import LLMResult, LocalMockProvider, OllamaProvider, OpenAICompatibleProvider, QwenOllamaProvider, build_provider
from app.llm.rag_chain import FALLBACK_ANSWER, build_retriever, has_sufficient_context, run_rag_ask
from app.config import Settings
from app.models import ResponseLog, TraceEvent
from app.quality.scorers import score_answer
from app.quality.validators import validate_answer
from app.retrieval.milvus_client import MilvusRetriever
from app.retrieval.retriever import FileBackedRetriever, RetrievalResult


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


def test_file_backed_retriever_returns_relevant_chunk() -> None:
    retriever = FileBackedRetriever("datasets/samples/rag_documents_extended_v2.jsonl", top_k=2)

    result = retriever.retrieve("What is the return policy?")

    assert result.no_context is False
    assert result.chunks
    assert result.chunks[0]["document_id"] == "doc-001"


def test_default_rag_prompt_hardens_real_model_instructions() -> None:
    prompt = default_rag_prompt()
    prompt_text = " ".join(
        [
            prompt.system_prompt,
            prompt.citation_instruction,
            prompt.safety_instruction,
            prompt.format_instruction,
        ]
    )

    assert "Use only the provided Context" in prompt_text
    assert "Do not answer from general knowledge" in prompt_text
    assert "I do not have enough context" in prompt_text
    assert "Sources: none" in prompt_text
    assert "Sources: doc-001#doc-001-chunk-0" in prompt_text


def test_has_sufficient_context_requires_chunks_and_min_score() -> None:
    assert has_sufficient_context(RetrievalResult(chunks=[], latency_ms=1, no_context=True), 0.0) is False
    assert (
        has_sufficient_context(
            RetrievalResult(chunks=[{"score": 0.2}], latency_ms=1, no_context=False),
            0.5,
        )
        is False
    )
    assert (
        has_sufficient_context(
            RetrievalResult(chunks=[{"score": 0.7}], latency_ms=1, no_context=False),
            0.5,
        )
        is True
    )


def test_build_retriever_selects_file_or_milvus_by_settings() -> None:
    file_retriever = build_retriever(Settings(MILVUS_ENABLED=False))
    milvus_retriever = build_retriever(Settings(MILVUS_ENABLED=True))

    assert isinstance(file_retriever, FileBackedRetriever)
    assert isinstance(milvus_retriever, MilvusRetriever)
    assert isinstance(milvus_retriever.fallback_retriever, FileBackedRetriever)


def test_milvus_retriever_uses_client_payload_without_live_milvus() -> None:
    class FakeMilvusClient:
        def search_vectors(self, collection: str, query_vector: list[float], top_k: int, filters: str | None = None) -> dict:
            return {
                "status": "searched",
                "payload": [
                    {
                        "chunk_id": "chunk-1",
                        "document_id": "doc-1",
                        "text": "Milvus payload text",
                        "source": "milvus",
                        "score": 0.91,
                        "metadata": {"collection": collection, "top_k": top_k, "dimension": len(query_vector)},
                    }
                ],
            }

    retriever = MilvusRetriever(Settings(MILVUS_ENABLED=True), client=FakeMilvusClient(), top_k=1)

    result = retriever.retrieve("return policy")

    assert result.no_context is False
    assert result.chunks[0]["chunk_id"] == "chunk-1"
    assert result.chunks[0]["metadata"]["dimension"] == 16


def test_mock_provider_answer_has_citation_and_scores() -> None:
    chunks = [
        {
            "chunk_id": "doc-001-chunk-0",
            "document_id": "doc-001",
            "text": "Customers may return unopened items within 30 days.",
            "source": "kb",
            "score": 1.0,
            "metadata": {},
        }
    ]
    prompt = assemble_prompt("What is the return policy?", chunks, default_rag_prompt())
    provider = build_provider("local_llama", "llama3")

    llm_result = provider.generate(prompt, chunks, "What is the return policy?")
    citations = [{"document_id": "doc-001", "source": "kb", "chunk_id": "doc-001-chunk-0"}]
    scores = score_answer("What is the return policy?", llm_result.raw_answer, chunks)

    assert "Sources:" in llm_result.raw_answer
    assert scores["citation_correctness"] == 1.0
    assert validate_answer(llm_result.raw_answer, citations, scores) == "passed"


def test_run_rag_ask_skips_provider_when_retrieval_has_no_context(monkeypatch) -> None:
    class EmptyRetriever:
        def retrieve(self, _query: str) -> RetrievalResult:
            return RetrievalResult(chunks=[], latency_ms=1, no_context=True)

    provider_build_calls = {"count": 0}

    def provider_should_not_be_built(*_args):
        provider_build_calls["count"] += 1
        raise AssertionError("provider should not be built when context is insufficient")

    import app.llm.rag_chain as rag_chain

    fake_db = FakeDb()
    monkeypatch.setattr(rag_chain, "build_retriever", lambda _settings: EmptyRetriever())
    monkeypatch.setattr(rag_chain, "build_provider_from_profile", provider_should_not_be_built)

    result = run_rag_ask(
        fake_db,
        SimpleNamespace(
            query="What can you answer?",
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
    assert provider_build_calls["count"] == 0
    assert result["status"] == "fallback"
    assert result["answer"] == FALLBACK_ANSWER
    assert result["citations"] == []
    assert response_log.status == "fallback"
    assert response_log.validation_status == "fallback"
    assert any(event.span_name == "fallback_decision" and event.status == "fallback" for event in trace_events)
    assert any(event.span_name == "llm_call" and event.status == "skipped" for event in trace_events)


def test_run_rag_ask_replaces_generic_real_model_answer_with_fallback(monkeypatch) -> None:
    class RelevantRetriever:
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

    class GenericProvider:
        def generate(self, *_args) -> LLMResult:
            return LLMResult(
                raw_answer="I can answer many questions from general knowledge.",
                model_name="qwen_ollama:qwen2.5:3b",
                model_version="qwen2.5:3b",
                input_tokens=10,
                output_tokens=8,
                latency_ms=1,
                finish_reason="stop",
            )

    import app.llm.rag_chain as rag_chain

    fake_db = FakeDb()
    monkeypatch.setattr(rag_chain, "build_retriever", lambda _settings: RelevantRetriever())
    monkeypatch.setattr(rag_chain, "build_provider_from_profile", lambda _settings, _profile: GenericProvider())

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
        Settings(STORE_RAW_OUTPUT=False),
    )

    response_log = next(obj for obj in fake_db.added if isinstance(obj, ResponseLog))
    trace_events = [obj for obj in fake_db.added if isinstance(obj, TraceEvent)]
    assert result["status"] == "fallback"
    assert result["answer"] == FALLBACK_ANSWER
    assert result["citations"] == []
    assert "general knowledge" not in result["answer"]
    assert response_log.answer == FALLBACK_ANSWER
    assert response_log.payload["user_visible_answer_replaced"] is True
    assert response_log.payload["fallback_reason"] == "validation_failed"
    assert response_log.payload["raw_model_answer_stored"] is False
    assert "raw_model_answer_preview" in response_log.payload
    assert "missing_sources_line" in response_log.payload["validation_reasons"]
    assert any(event.span_name == "post_validation_fallback" for event in trace_events)


def test_run_rag_ask_keeps_valid_grounded_answer(monkeypatch) -> None:
    class RelevantRetriever:
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

    class GroundedProvider:
        def generate(self, *_args) -> LLMResult:
            return LLMResult(
                raw_answer="Customers may return unopened items within 30 days. Sources: doc-001#doc-001-chunk-0",
                model_name="qwen_ollama:qwen2.5:3b",
                model_version="qwen2.5:3b",
                input_tokens=10,
                output_tokens=9,
                latency_ms=1,
                finish_reason="stop",
            )

    import app.llm.rag_chain as rag_chain

    fake_db = FakeDb()
    monkeypatch.setattr(rag_chain, "build_retriever", lambda _settings: RelevantRetriever())
    monkeypatch.setattr(rag_chain, "build_provider_from_profile", lambda _settings, _profile: GroundedProvider())

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
    assert result["status"] == "success"
    assert result["answer"].startswith("Customers may return unopened items")
    assert response_log.payload["user_visible_answer_replaced"] is False


def test_build_provider_selects_supported_modes() -> None:
    assert isinstance(build_provider("mock", "llama3"), LocalMockProvider)
    assert isinstance(build_provider("local_llama", "llama3"), LocalMockProvider)
    assert isinstance(build_provider("openai", "gpt-4o-mini"), OpenAICompatibleProvider)
    assert isinstance(build_provider("ollama", "llama3"), OllamaProvider)
    assert isinstance(build_provider("qwen_ollama", "llama3"), QwenOllamaProvider)
    assert isinstance(build_provider("unknown", "model"), LocalMockProvider)


def test_build_provider_uses_settings_values() -> None:
    openai_provider = build_provider(
        Settings(
            LLM_PROVIDER="openai",
            OPENAI_MODEL="gpt-test",
            OPENAI_BASE_URL="https://example.test/v1",
            OPENAI_API_KEY="test-key",
        )
    )
    ollama_provider = build_provider(
        Settings(
            LLM_PROVIDER="ollama",
            LOCAL_LLM_MODEL="llama-test",
            LOCAL_LLM_BASE_URL="http://ollama.test:11434",
        )
    )
    qwen_provider = build_provider(
        Settings(
            LLM_PROVIDER="qwen_ollama",
            LOCAL_LLM_BASE_URL="http://ollama.test:11434",
            QWEN_OLLAMA_MODEL="qwen-test:latest",
        )
    )

    assert isinstance(openai_provider, OpenAICompatibleProvider)
    assert openai_provider.model_name == "gpt-test"
    assert openai_provider.base_url == "https://example.test/v1"
    assert openai_provider.api_key == "test-key"
    assert isinstance(ollama_provider, OllamaProvider)
    assert ollama_provider.model_name == "llama-test"
    assert ollama_provider.base_url == "http://ollama.test:11434"
    assert isinstance(qwen_provider, QwenOllamaProvider)
    assert qwen_provider.model_name == "qwen-test:latest"
    assert qwen_provider.base_url == "http://ollama.test:11434"


def test_external_providers_fallback_without_running_services(monkeypatch) -> None:
    chunks = [
        {
            "chunk_id": "doc-001-chunk-0",
            "document_id": "doc-001",
            "text": "Customers may return unopened items within 30 days.",
            "source": "kb",
            "score": 1.0,
            "metadata": {},
        }
    ]
    prompt = assemble_prompt("What is the return policy?", chunks, default_rag_prompt())
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    openai_result = build_provider("openai", "gpt-4o-mini").generate(prompt, chunks, "What is the return policy?")
    ollama_result = build_provider("ollama", "llama3").generate(prompt, chunks, "What is the return policy?")

    assert "Sources:" in openai_result.raw_answer
    assert openai_result.finish_reason.startswith("fallback:")
    assert "Sources:" in ollama_result.raw_answer
    assert ollama_result.finish_reason.startswith("fallback:")


def test_openai_provider_returns_controlled_error_when_fallback_disabled() -> None:
    chunks = [
        {
            "chunk_id": "doc-001-chunk-0",
            "document_id": "doc-001",
            "text": "Customers may return unopened items within 30 days.",
            "source": "kb",
            "score": 1.0,
            "metadata": {},
        }
    ]
    prompt = assemble_prompt("What is the return policy?", chunks, default_rag_prompt())
    provider = build_provider(
        Settings(
            LLM_PROVIDER="openai",
            OPENAI_MODEL="gpt-test",
            OPENAI_API_KEY="",
            LLM_ALLOW_MOCK_FALLBACK=False,
        )
    )

    result = provider.generate(prompt, chunks, "What is the return policy?")

    assert result.raw_answer == ""
    assert result.model_name == "openai:gpt-test"
    assert result.model_version == "error"
    assert result.output_tokens == 0
    assert result.finish_reason == "error:missing_api_key"


def test_ask_response_schema_and_eval_runner_use_model_metadata() -> None:
    schema = Path("services/api/app/schemas.py").read_text(encoding="utf-8")
    rag_chain = Path("services/api/app/llm/rag_chain.py").read_text(encoding="utf-8")
    run_eval = Path("scripts/run_eval.py").read_text(encoding="utf-8")

    assert "model_name: str" in schema
    assert "model_version: str" in schema
    assert "finish_reason: str" in schema
    assert '"model_name": llm_result.model_name' in rag_chain
    assert '"model_version": llm_result.model_version' in rag_chain
    assert '"finish_reason": llm_result.finish_reason' in rag_chain
    assert 'model_version="mock-v1"' not in run_eval
    assert 'response["model_name"]' in run_eval
    assert 'response["model_version"]' in run_eval
    assert 'response["finish_reason"]' in run_eval


def test_rag_chain_logs_failed_llm_call_for_strict_provider_errors() -> None:
    rag_chain = Path("services/api/app/llm/rag_chain.py").read_text(encoding="utf-8")
    config = Path("services/api/app/config.py").read_text(encoding="utf-8")
    env_example = Path(".env.example").read_text(encoding="utf-8")

    assert "llm_allow_mock_fallback" in config
    assert "LLM_ALLOW_MOCK_FALLBACK=true" in env_example
    assert 'llm_call_status = "failed" if llm_result.finish_reason.startswith("error:") else "success"' in rag_chain
    assert '"mock_fallback_allowed": settings.llm_allow_mock_fallback' in rag_chain
