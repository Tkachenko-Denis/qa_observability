import uuid

from app.config import get_settings
from app.observability_tools.langfuse_client import LangfuseContractClient, LangfuseSpanContract
from app.observability_tools.trace_logger import _trace_payload


def test_langfuse_export_skips_when_disabled() -> None:
    client = LangfuseContractClient(get_settings())
    span = LangfuseSpanContract(
        trace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        span_name="retrieval",
        status="success",
        payload={"chunk_count": 1},
        latency_ms=10,
    )

    result = client.export_span(span)

    assert result == {"status": "skipped", "reason": "langfuse_disabled"}


def test_langfuse_span_contract_includes_rag_trace_metadata() -> None:
    session_id = uuid.uuid4()
    span = LangfuseSpanContract(
        trace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        session_id=session_id,
        span_name="validation",
        status="passed",
        payload={"citation_count": 2},
        latency_ms=12,
        prompt_version="rag-v1",
        model_name="mock:llama3",
        retrieval_top_k=5,
        dataset_version="sample-v1",
        input_tokens=100,
        output_tokens=40,
        scores={"citation_correctness": 1.0},
        validation_status="passed",
    )

    contract = LangfuseContractClient(get_settings()).span_contract(span)

    assert contract["session_id"] == str(session_id)
    assert contract["metadata"]["prompt_version"] == "rag-v1"
    assert contract["metadata"]["model_name"] == "mock:llama3"
    assert contract["metadata"]["retrieval_top_k"] == 5
    assert contract["metadata"]["dataset_version"] == "sample-v1"
    assert contract["metadata"]["input_tokens"] == 100
    assert contract["metadata"]["output_tokens"] == 40
    assert contract["metadata"]["scores"]["citation_correctness"] == 1.0
    assert contract["metadata"]["validation_status"] == "passed"


def test_langfuse_status_reports_sdk_readiness_fields() -> None:
    status = LangfuseContractClient(get_settings()).status()

    assert status["name"] == "langfuse"
    assert "sdk_available" in status
    assert "ready_for_sdk_export" in status
    assert status["fallback"] == "postgres_trace_events"


def test_trace_payload_includes_required_rag_observability_fields() -> None:
    session_id = uuid.uuid4()

    payload = _trace_payload(
        {"stage": "validation"},
        session_id=session_id,
        prompt_version="rag-v1",
        model_name="mock:llama3",
        retrieval_top_k=3,
        dataset_version="sample-v1",
        input_tokens=20,
        output_tokens=10,
        scores={"groundedness": 0.9},
        validation_status="passed",
    )

    assert payload["session_id"] == str(session_id)
    assert payload["prompt_version"] == "rag-v1"
    assert payload["model_name"] == "mock:llama3"
    assert payload["retrieval_top_k"] == 3
    assert payload["dataset_version"] == "sample-v1"
    assert payload["input_tokens"] == 20
    assert payload["output_tokens"] == 10
    assert payload["scores"]["groundedness"] == 0.9
    assert payload["validation_status"] == "passed"
