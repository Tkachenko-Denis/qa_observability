from __future__ import annotations

import json

from app.config import get_settings
from app.retrieval.milvus_client import MilvusContractClient


EMBEDDING_DIMENSION = 16


def bootstrap_milvus_collection() -> dict:
    settings = get_settings()
    client = MilvusContractClient(settings)
    pymilvus = client._load_pymilvus()

    if not settings.milvus_enabled:
        return {
            "status": "skipped",
            "reason": "milvus_disabled",
            "collection": settings.milvus_collection,
            "embedding_dimension": EMBEDDING_DIMENSION,
        }
    if pymilvus is None:
        return {
            "status": "skipped",
            "reason": "pymilvus_sdk_missing",
            "collection": settings.milvus_collection,
            "embedding_dimension": EMBEDDING_DIMENSION,
        }

    try:
        pymilvus.connections.connect(alias="default", host=settings.milvus_host, port=str(settings.milvus_port))
        utility = pymilvus.utility
        collection_exists = bool(utility.has_collection(settings.milvus_collection))
        if not collection_exists:
            fields = [
                pymilvus.FieldSchema(name="chunk_id", dtype=pymilvus.DataType.VARCHAR, is_primary=True, max_length=128),
                pymilvus.FieldSchema(name="document_id", dtype=pymilvus.DataType.VARCHAR, max_length=128),
                pymilvus.FieldSchema(name="text", dtype=pymilvus.DataType.VARCHAR, max_length=8192),
                pymilvus.FieldSchema(name="source", dtype=pymilvus.DataType.VARCHAR, max_length=512),
                pymilvus.FieldSchema(name="metadata", dtype=pymilvus.DataType.JSON),
                pymilvus.FieldSchema(
                    name="embedding",
                    dtype=pymilvus.DataType.FLOAT_VECTOR,
                    dim=EMBEDDING_DIMENSION,
                ),
            ]
            schema = pymilvus.CollectionSchema(fields=fields, description="RAG chunks for LLMOps DQ observability")
            collection = pymilvus.Collection(name=settings.milvus_collection, schema=schema)
        else:
            collection = pymilvus.Collection(settings.milvus_collection)

        index_created = False
        if not collection.has_index():
            collection.create_index(
                field_name="embedding",
                index_params={
                    "index_type": "IVF_FLAT",
                    "metric_type": "COSINE",
                    "params": {"nlist": 128},
                },
            )
            index_created = True
        collection.load()
        return {
            "status": "ready",
            "collection": settings.milvus_collection,
            "collection_created": not collection_exists,
            "index_created": index_created,
            "embedding_dimension": EMBEDDING_DIMENSION,
            "fields": ["chunk_id", "document_id", "text", "source", "metadata", "embedding"],
            "index": {"field": "embedding", "index_type": "IVF_FLAT", "metric_type": "COSINE"},
        }
    except Exception as exc:  # pragma: no cover - defensive around optional external SDK/server.
        return {
            "status": "failed",
            "reason": type(exc).__name__,
            "message": str(exc),
            "collection": settings.milvus_collection,
            "embedding_dimension": EMBEDDING_DIMENSION,
        }


if __name__ == "__main__":
    result = bootstrap_milvus_collection()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] in {"ready", "skipped"} else 1)
