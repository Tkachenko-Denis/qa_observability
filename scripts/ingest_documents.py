from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Chunk, Document, DocumentVersion


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ingest_jsonl(dataset_path: str, version: str) -> dict[str, int]:
    path = resolve_path(dataset_path)
    inserted_documents = 0
    inserted_chunks = 0

    with SessionLocal() as db:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                doc_id = str(record["doc_id"])
                text = str(record["text"])
                digest = content_hash(text)

                document = db.scalar(select(Document).where(Document.doc_id == doc_id))
                if document is None:
                    document = Document(
                        doc_id=doc_id,
                        source=str(record.get("source", "unknown")),
                        title=record.get("title"),
                        content_hash=digest,
                        language=record.get("language"),
                        metadata_payload={
                            "updated_at": record.get("updated_at"),
                            "sensitivity": record.get("sensitivity"),
                        },
                    )
                    db.add(document)
                    db.flush()
                    inserted_documents += 1

                existing_chunk = db.scalar(select(Chunk).where(Chunk.chunk_id == f"{doc_id}-chunk-0"))
                if existing_chunk is None:
                    db.add(
                        Chunk(
                            chunk_id=f"{doc_id}-chunk-0",
                            document_id=document.id,
                            chunk_index=0,
                            chunk_text=text,
                            embedding_status="missing",
                            metadata_payload={"source": record.get("source"), "language": record.get("language")},
                        )
                    )
                    inserted_chunks += 1

                db.add(
                    DocumentVersion(
                        document_id=document.id,
                        version=version,
                        content_hash=digest,
                        status="active",
                        metadata_payload={"dataset_path": dataset_path},
                    )
                )
        db.commit()

    return {"inserted_documents": inserted_documents, "inserted_chunks": inserted_chunks}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-path", default="datasets/samples/rag_documents_extended_v2.jsonl")
    parser.add_argument("--version", default="sample-v2")
    args = parser.parse_args()

    print(json.dumps(ingest_jsonl(args.dataset_path, args.version), indent=2))


if __name__ == "__main__":
    main()
