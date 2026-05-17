from __future__ import annotations

import uuid
from types import SimpleNamespace

import scripts.build_index as build_index


class FakeScalarResult:
    def __init__(self, chunks: list[SimpleNamespace]) -> None:
        self.chunks = chunks

    def all(self) -> list[SimpleNamespace]:
        return self.chunks


class FakeSession:
    def __init__(self, rows: list[tuple[SimpleNamespace, SimpleNamespace]]) -> None:
        self.rows = rows
        self.committed = False

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, _statement: object) -> FakeScalarResult:
        return FakeScalarResult(self.rows)

    def commit(self) -> None:
        self.committed = True


class FakeMilvusClient:
    last_request = None

    def __init__(self, _settings: object) -> None:
        return None

    def upsert_vectors(self, request: object) -> dict:
        FakeMilvusClient.last_request = request
        return {"status": "skipped", "reason": "milvus_disabled", "inserted_count": 0}


def test_mark_chunks_indexed_uses_chunk_text_field(monkeypatch) -> None:
    document = SimpleNamespace(
        id=uuid.uuid4(),
        doc_id="doc-001",
        source="unit-test-source",
    )
    chunk = SimpleNamespace(
        id=uuid.uuid4(),
        chunk_id="doc-001-chunk-0",
        document_id=document.id,
        chunk_text="Index this chunk text",
        embedding_status="missing",
        metadata_payload={"source": "unit-test"},
    )
    fake_session = FakeSession([(chunk, document)])

    monkeypatch.setattr(build_index, "SessionLocal", lambda: fake_session)
    monkeypatch.setattr(build_index, "MilvusContractClient", FakeMilvusClient)

    result = build_index.mark_chunks_indexed()

    assert result["indexed_chunks"] == 1
    assert chunk.embedding_status == "indexed"
    assert fake_session.committed is True
    assert FakeMilvusClient.last_request is not None
    payload = FakeMilvusClient.last_request.payloads[0]
    assert payload["document_id"] == "doc-001"
    assert payload["chunk_id"] == "doc-001-chunk-0"
    assert payload["text"] == "Index this chunk text"
    assert payload["metadata"]["internal_chunk_uuid"] == str(chunk.id)
    assert payload["metadata"]["internal_document_uuid"] == str(document.id)
    assert len(FakeMilvusClient.last_request.vectors[0]) == 16
