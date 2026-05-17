from __future__ import annotations

import importlib
import time
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.retrieval.retriever import BaseRetriever, RetrievalResult


@dataclass(frozen=True, slots=True)
class MilvusSearchRequest:
    query: str
    top_k: int
    filters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class MilvusUpsertRequest:
    collection: str
    vectors: list[list[float]]
    payloads: list[dict[str, Any]]


def deterministic_query_embedding(text: str, dimension: int = 16) -> list[float]:
    import hashlib

    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = []
    for index in range(dimension):
        raw = digest[index] / 255.0
        values.append(round((raw * 2.0) - 1.0, 6))
    return values


class MilvusContractClient:
    """Optional Milvus SDK integration with file-backed retriever fallback.

    The project can run without Milvus. When `MILVUS_ENABLED=true` and pymilvus
    is installed, this client can upsert/search vectors against a configured
    collection. Collection bootstrap is intentionally explicit for MVP safety.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _load_pymilvus(self) -> Any | None:
        try:
            return importlib.import_module("pymilvus")
        except ImportError:
            return None

    def status(self) -> dict[str, Any]:
        sdk_available = self._load_pymilvus() is not None
        if not self.settings.milvus_enabled:
            mode = "contract_only"
        elif sdk_available:
            mode = "runtime"
        else:
            mode = "sdk_missing"
        return {
            "name": "milvus",
            "enabled": self.settings.milvus_enabled,
            "mode": mode,
            "host": self.settings.milvus_host,
            "port": self.settings.milvus_port,
            "collection": self.settings.milvus_collection,
            "embedding_model": self.settings.embedding_model,
            "sdk_available": sdk_available,
            "required_for_mvp": False,
            "fallback": "file_backed_retriever",
            "capabilities": ["vector_search", "semantic_dedup", "embedding_drift_extension"],
        }

    def search_contract(self, request: MilvusSearchRequest) -> dict[str, Any]:
        return {
            "tool_name": "milvus_retriever",
            "action": "search",
            "status": "not_executed" if not self.settings.milvus_enabled else self.status()["mode"],
            "parameters": {
                "query": request.query,
                "top_k": request.top_k,
                "filters": request.filters,
                "collection": self.settings.milvus_collection,
            },
            "response_schema": {
                "payload": [
                    {
                        "chunk_id": "string",
                        "document_id": "string",
                        "text": "string",
                        "source": "string",
                        "score": 0.0,
                        "metadata": {},
                    }
                ],
                "latency_ms": 0,
                "error_message": None,
            },
        }

    def upsert_contract(self, request: MilvusUpsertRequest) -> dict[str, Any]:
        return {
            "tool_name": "milvus_indexer",
            "action": "upsert",
            "status": "not_executed" if not self.settings.milvus_enabled else self.status()["mode"],
            "parameters": {
                "collection": request.collection,
                "vector_count": len(request.vectors),
                "payload_count": len(request.payloads),
                "embedding_model": self.settings.embedding_model,
            },
            "response_schema": {
                "inserted_count": 0,
                "updated_count": 0,
                "failed_count": 0,
                "error_message": None,
            },
        }

    def upsert_vectors(self, request: MilvusUpsertRequest) -> dict[str, Any]:
        if not self.settings.milvus_enabled:
            return {"status": "skipped", "reason": "milvus_disabled", "inserted_count": 0}
        pymilvus = self._load_pymilvus()
        if pymilvus is None:
            return {"status": "skipped", "reason": "pymilvus_sdk_missing", "inserted_count": 0}
        if not request.vectors:
            return {"status": "skipped", "reason": "no_vectors", "inserted_count": 0}

        try:
            pymilvus.connections.connect(alias="default", host=self.settings.milvus_host, port=str(self.settings.milvus_port))
            collection = pymilvus.Collection(request.collection)
            rows = []
            for index, vector in enumerate(request.vectors):
                payload = request.payloads[index] if index < len(request.payloads) else {}
                rows.append({**payload, "embedding": vector})
            insert_result = collection.insert(rows)
            collection.flush()
            primary_keys = getattr(insert_result, "primary_keys", []) or []
            return {"status": "upserted", "inserted_count": len(primary_keys) or len(rows), "collection": request.collection}
        except Exception as exc:  # pragma: no cover - defensive around optional external SDK/server.
            return {"status": "failed", "reason": type(exc).__name__, "message": str(exc), "inserted_count": 0}

    def search_vectors(self, collection: str, query_vector: list[float], top_k: int, filters: str | None = None) -> dict[str, Any]:
        if not self.settings.milvus_enabled:
            return {"status": "skipped", "reason": "milvus_disabled", "payload": []}
        pymilvus = self._load_pymilvus()
        if pymilvus is None:
            return {"status": "skipped", "reason": "pymilvus_sdk_missing", "payload": []}

        try:
            pymilvus.connections.connect(alias="default", host=self.settings.milvus_host, port=str(self.settings.milvus_port))
            milvus_collection = pymilvus.Collection(collection)
            milvus_collection.load()
            results = milvus_collection.search(
                data=[query_vector],
                anns_field="embedding",
                param={"metric_type": "COSINE", "params": {"nprobe": 10}},
                limit=top_k,
                expr=filters,
                output_fields=["chunk_id", "document_id", "text", "source", "metadata"],
            )
            payload = []
            for hits in results:
                for hit in hits:
                    entity = hit.entity
                    payload.append(
                        {
                            "chunk_id": entity.get("chunk_id"),
                            "document_id": entity.get("document_id"),
                            "text": entity.get("text"),
                            "source": entity.get("source"),
                            "score": float(hit.score),
                            "metadata": entity.get("metadata") or {},
                        }
                    )
            return {"status": "searched", "payload": payload}
        except Exception as exc:  # pragma: no cover - defensive around optional external SDK/server.
            return {"status": "failed", "reason": type(exc).__name__, "message": str(exc), "payload": []}


class MilvusRetriever(BaseRetriever):
    """Retriever adapter over optional Milvus runtime with safe fallback.

    Milvus remains an optional MVP extension. If the SDK/server is unavailable,
    or a search returns no payload, the adapter delegates to the configured
    fallback retriever so `/ask` remains operational.
    """

    def __init__(
        self,
        settings: Settings,
        client: MilvusContractClient | None = None,
        fallback_retriever: BaseRetriever | None = None,
        top_k: int | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or MilvusContractClient(settings)
        self.fallback_retriever = fallback_retriever
        self.top_k = top_k or settings.rag_top_k

    def retrieve(self, query: str) -> RetrievalResult:
        started = time.perf_counter()
        result = self.client.search_vectors(
            collection=self.settings.milvus_collection,
            query_vector=deterministic_query_embedding(query),
            top_k=self.top_k,
        )
        chunks = self._normalize_payload(result.get("payload", []))
        if result.get("status") == "searched" and chunks:
            latency_ms = int((time.perf_counter() - started) * 1000)
            return RetrievalResult(chunks=chunks, latency_ms=latency_ms, no_context=False)

        if self.fallback_retriever is not None:
            fallback = self.fallback_retriever.retrieve(query)
            return RetrievalResult(
                chunks=fallback.chunks,
                latency_ms=fallback.latency_ms + int((time.perf_counter() - started) * 1000),
                no_context=fallback.no_context,
            )

        latency_ms = int((time.perf_counter() - started) * 1000)
        return RetrievalResult(chunks=[], latency_ms=latency_ms, no_context=True)

    def _normalize_payload(self, payload: Any) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        if not isinstance(payload, list):
            return chunks
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                continue
            chunks.append(
                {
                    "chunk_id": str(item.get("chunk_id", f"milvus-{index}")),
                    "document_id": str(item.get("document_id", f"milvus-doc-{index}")),
                    "text": str(item.get("text", "")),
                    "source": str(item.get("source", "milvus")),
                    "score": float(item.get("score", 0.0) or 0.0),
                    "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
                }
            )
        return chunks
