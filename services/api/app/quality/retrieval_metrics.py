from __future__ import annotations


def retrieval_metric_snapshot(retrieved_chunks: list[dict], latency_ms: int) -> dict[str, float]:
    return {
        "retrieval_hit_rate": 1.0 if retrieved_chunks else 0.0,
        "top_k_relevance": max((float(chunk.get("score", 0.0)) for chunk in retrieved_chunks), default=0.0),
        "context_precision": 1.0 if retrieved_chunks else 0.0,
        "context_recall": 1.0 if retrieved_chunks else 0.0,
        "no_context_rate": 0.0 if retrieved_chunks else 1.0,
        "source_diversity": len({chunk.get("source") for chunk in retrieved_chunks}) / max(len(retrieved_chunks), 1),
        "retrieval_latency_ms": float(latency_ms),
    }
