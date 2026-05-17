from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import TraceEvent
from app.observability_tools.langfuse_client import LangfuseContractClient, LangfuseSpanContract


def log_trace_event(
    db: Session,
    trace_id: uuid.UUID,
    request_id: uuid.UUID | None,
    span_name: str,
    status: str,
    payload: dict[str, Any] | None = None,
    latency_ms: int | None = None,
    session_id: uuid.UUID | None = None,
    prompt_version: str | None = None,
    model_name: str | None = None,
    retrieval_top_k: int | None = None,
    dataset_version: str | None = None,
    model_profile_id: str | None = None,
    provider: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    scores: dict[str, Any] | None = None,
    validation_status: str | None = None,
) -> TraceEvent:
    trace_payload = _trace_payload(
        payload or {},
        session_id=session_id,
        prompt_version=prompt_version,
        model_name=model_name,
        retrieval_top_k=retrieval_top_k,
        dataset_version=dataset_version,
        model_profile_id=model_profile_id,
        provider=provider,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        scores=scores,
        validation_status=validation_status,
    )
    span = LangfuseSpanContract(
        trace_id=trace_id,
        request_id=request_id,
        session_id=session_id,
        span_name=span_name,
        status=status,
        payload=payload or {},
        latency_ms=latency_ms,
        prompt_version=prompt_version,
        model_name=model_name,
        retrieval_top_k=retrieval_top_k,
        dataset_version=dataset_version,
        model_profile_id=model_profile_id,
        provider=provider,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        scores=scores,
        validation_status=validation_status,
    )
    client = LangfuseContractClient(get_settings())
    langfuse_contract = client.span_contract(span)
    langfuse_export = client.export_span(span)
    event = TraceEvent(
        trace_id=trace_id,
        request_id=request_id,
        span_name=span_name,
        status=status,
        payload={**trace_payload, "langfuse_contract": langfuse_contract, "langfuse_export": langfuse_export},
        latency_ms=latency_ms,
    )
    db.add(event)
    return event


def _trace_payload(
    payload: dict[str, Any],
    *,
    session_id: uuid.UUID | None,
    prompt_version: str | None,
    model_name: str | None,
    retrieval_top_k: int | None,
    dataset_version: str | None,
    model_profile_id: str | None = None,
    provider: str | None = None,
    input_tokens: int | None,
    output_tokens: int | None,
    scores: dict[str, Any] | None,
    validation_status: str | None,
) -> dict[str, Any]:
    enriched = dict(payload)
    if session_id is not None:
        enriched["session_id"] = str(session_id)
    optional_fields: dict[str, Any] = {
        "prompt_version": prompt_version,
        "model_name": model_name,
        "retrieval_top_k": retrieval_top_k,
        "dataset_version": dataset_version,
        "model_profile_id": model_profile_id,
        "provider": provider,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "scores": scores,
        "validation_status": validation_status,
    }
    for key, value in optional_fields.items():
        if value is not None:
            enriched[key] = value
    return enriched
