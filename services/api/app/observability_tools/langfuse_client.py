from __future__ import annotations

import uuid
import importlib
from dataclasses import dataclass
from typing import Any

from app.config import Settings


@dataclass(frozen=True, slots=True)
class LangfuseSpanContract:
    trace_id: uuid.UUID
    request_id: uuid.UUID | None
    session_id: uuid.UUID | None
    span_name: str
    status: str
    payload: dict[str, Any]
    latency_ms: int | None
    prompt_version: str | None = None
    model_name: str | None = None
    model_profile_id: str | None = None
    provider: str | None = None
    retrieval_top_k: int | None = None
    dataset_version: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    scores: dict[str, Any] | None = None
    validation_status: str | None = None


class LangfuseContractClient:
    """Optional Langfuse SDK integration with PostgreSQL fallback.

    Local MVP runs persist traces to PostgreSQL. When `LANGFUSE_ENABLED=true`,
    keys are configured, and the SDK is installed, spans are best-effort
    exported to Langfuse without blocking the request path.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _load_langfuse_class(self) -> Any | None:
        try:
            module = importlib.import_module("langfuse")
        except ImportError:
            return None
        return getattr(module, "Langfuse", None)

    def status(self) -> dict[str, Any]:
        keys_configured = bool(self.settings.langfuse_public_key and self.settings.langfuse_secret_key)
        sdk_available = self._load_langfuse_class() is not None
        if not self.settings.langfuse_enabled:
            mode = "contract_only"
        elif not keys_configured:
            mode = "keys_missing"
        elif not sdk_available:
            mode = "sdk_missing"
        else:
            mode = "runtime"
        return {
            "name": "langfuse",
            "enabled": self.settings.langfuse_enabled,
            "mode": mode,
            "host": self.settings.langfuse_host,
            "public_key_configured": bool(self.settings.langfuse_public_key),
            "secret_key_configured": bool(self.settings.langfuse_secret_key),
            "sdk_available": sdk_available,
            "ready_for_sdk_export": self.settings.langfuse_enabled and keys_configured and sdk_available,
            "required_for_mvp": False,
            "fallback": "postgres_trace_events",
            "capabilities": ["trace", "span", "score", "prompt_metadata"],
        }

    def trace_contract(self, trace_id: uuid.UUID, request_id: uuid.UUID | None, session_id: uuid.UUID | None) -> dict[str, Any]:
        return {
            "trace_id": str(trace_id),
            "request_id": str(request_id) if request_id else None,
            "session_id": str(session_id) if session_id else None,
            "scenario": "rag_qa",
            "pipeline_version": "mvp",
            "export_status": "not_executed" if not self.settings.langfuse_enabled else self.status()["mode"],
        }

    def span_contract(self, span: LangfuseSpanContract) -> dict[str, Any]:
        metadata = self._span_metadata(span)
        return {
            "trace_id": str(span.trace_id),
            "request_id": str(span.request_id) if span.request_id else None,
            "session_id": str(span.session_id) if span.session_id else None,
            "name": span.span_name,
            "status": span.status,
            "metadata": metadata,
            "latency_ms": span.latency_ms,
            "export_status": "not_executed" if not self.settings.langfuse_enabled else self.status()["mode"],
        }

    def _span_metadata(self, span: LangfuseSpanContract) -> dict[str, Any]:
        metadata = dict(span.payload)
        if span.session_id is not None:
            metadata["session_id"] = str(span.session_id)
        optional_fields: dict[str, Any] = {
            "prompt_version": span.prompt_version,
            "model_name": span.model_name,
            "model_profile_id": span.model_profile_id,
            "provider": span.provider,
            "retrieval_top_k": span.retrieval_top_k,
            "dataset_version": span.dataset_version,
            "input_tokens": span.input_tokens,
            "output_tokens": span.output_tokens,
            "scores": span.scores,
            "validation_status": span.validation_status,
        }
        for key, value in optional_fields.items():
            if value is not None:
                metadata[key] = value
        return metadata

    def export_span(self, span: LangfuseSpanContract) -> dict[str, Any]:
        if not self.settings.langfuse_enabled:
            return {"status": "skipped", "reason": "langfuse_disabled"}
        if not (self.settings.langfuse_public_key and self.settings.langfuse_secret_key):
            return {"status": "skipped", "reason": "langfuse_keys_missing"}

        langfuse_class = self._load_langfuse_class()
        if langfuse_class is None:
            return {"status": "skipped", "reason": "langfuse_sdk_missing"}

        try:
            client = langfuse_class(
                public_key=self.settings.langfuse_public_key,
                secret_key=self.settings.langfuse_secret_key,
                host=self.settings.langfuse_host,
            )
            trace = client.trace(
                id=str(span.trace_id),
                name="rag_qa",
                metadata={
                    "request_id": str(span.request_id) if span.request_id else None,
                    "session_id": str(span.session_id) if span.session_id else None,
                    "dataset_version": span.dataset_version,
                    "prompt_version": span.prompt_version,
                    "model_name": span.model_name,
                    "model_profile_id": span.model_profile_id,
                    "provider": span.provider,
                },
            )
            trace.span(
                name=span.span_name,
                metadata=self._span_metadata(span),
                level="ERROR" if span.status == "failed" else "DEFAULT",
            )
            flush = getattr(client, "flush", None)
            if callable(flush):
                flush()
            return {"status": "exported", "trace_id": str(span.trace_id), "span_name": span.span_name}
        except Exception as exc:  # pragma: no cover - defensive around optional external SDK/server.
            return {"status": "failed", "reason": type(exc).__name__, "message": str(exc)}
