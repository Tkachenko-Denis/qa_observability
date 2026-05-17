from __future__ import annotations

import hashlib
import json

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Chunk, Document
from app.retrieval.milvus_client import MilvusContractClient, MilvusUpsertRequest


def deterministic_embedding(text: str, dimension: int = 16) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = []
    for index in range(dimension):
        raw = digest[index] / 255.0
        values.append(round((raw * 2.0) - 1.0, 6))
    return values


def mark_chunks_indexed() -> dict[str, int]:
    settings = get_settings()
    updated = 0
    vectors: list[list[float]] = []
    payloads: list[dict] = []
    with SessionLocal() as db:
        chunk_rows = list(
            db.execute(
                select(Chunk, Document)
                .join(Document, Chunk.document_id == Document.id)
                .where(Chunk.embedding_status != "indexed")
            ).all()
        )
        for chunk, document in chunk_rows:
            metadata = {
                **(chunk.metadata_payload or {}),
                "internal_chunk_uuid": str(chunk.id),
                "internal_document_uuid": str(document.id),
            }
            vectors.append(deterministic_embedding(chunk.chunk_text))
            payloads.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "document_id": document.doc_id,
                    "text": chunk.chunk_text,
                    "source": metadata.get("source", document.source),
                    "metadata": metadata,
                }
            )
            chunk.embedding_status = "indexed"
            updated += 1
        db.commit()

    milvus_result = MilvusContractClient(settings).upsert_vectors(
        MilvusUpsertRequest(collection=settings.milvus_collection, vectors=vectors, payloads=payloads)
    )
    return {"indexed_chunks": updated, "milvus": milvus_result}


if __name__ == "__main__":
    print(json.dumps(mark_chunks_indexed(), indent=2))
