from __future__ import annotations

import json
import math
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    chunks: list[dict[str, Any]]
    latency_ms: int
    no_context: bool


class BaseRetriever(ABC):
    @abstractmethod
    def retrieve(self, query: str) -> RetrievalResult:
        raise NotImplementedError


def _resolve_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _tokenize(text: str) -> set[str]:
    return {token.strip(".,!?;:()[]{}\"'").lower() for token in text.split() if token.strip()}


def _load_jsonl_documents(dataset_path: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with _resolve_path(dataset_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


class FileBackedRetriever(BaseRetriever):
    def __init__(self, dataset_path: str, top_k: int = 5) -> None:
        self.dataset_path = dataset_path
        self.top_k = top_k

    def retrieve(self, query: str) -> RetrievalResult:
        started = time.perf_counter()
        query_tokens = _tokenize(query)
        scored_chunks: list[dict[str, Any]] = []

        for index, record in enumerate(_load_jsonl_documents(self.dataset_path)):
            text = str(record.get("text", ""))
            text_tokens = _tokenize(text + " " + str(record.get("title", "")))
            overlap = len(query_tokens & text_tokens)
            score = overlap / math.sqrt(max(len(text_tokens), 1)) if query_tokens else 0.0
            if overlap == 0 and query_tokens:
                continue
            scored_chunks.append(
                {
                    "chunk_id": f"{record.get('doc_id', f'doc-{index}')}-chunk-0",
                    "document_id": str(record.get("doc_id", f"doc-{index}")),
                    "text": text,
                    "source": str(record.get("source", "sample")),
                    "score": round(score, 6),
                    "metadata": {
                        "title": record.get("title"),
                        "language": record.get("language"),
                        "updated_at": record.get("updated_at"),
                    },
                }
            )

        chunks = sorted(scored_chunks, key=lambda item: item["score"], reverse=True)[: self.top_k]
        latency_ms = int((time.perf_counter() - started) * 1000)
        return RetrievalResult(chunks=chunks, latency_ms=latency_ms, no_context=not chunks)
