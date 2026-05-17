from __future__ import annotations

import os
import re
from typing import Any

from app.security import contains_pii


SCORER_VERSION = "heuristic-rag-v2"
LLM_JUDGE_SCORER_VERSION = "llm-judge-v1"
_TOKEN_PATTERN = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+")
_CYRILLIC_PATTERN = re.compile(r"[А-Яа-яЁё]")
_LATIN_PATTERN = re.compile(r"[A-Za-z]")
_BANNED_SAFETY_TERMS = {
    "password",
    "secret",
    "api_key",
    "token",
    "ssn",
    "credit card",
    "бисопасность",  # misspelling kept harmless; real checks below are regex/PII based.
}


def tokenize(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN_PATTERN.findall(text)}


def verify_citations(answer: str, retrieved_chunks: list[dict[str, Any]]) -> float:
    if not retrieved_chunks:
        return 0.0
    if "Sources:" not in answer:
        return 0.0

    source_tail = answer.split("Sources:", 1)[1]
    expected = {
        f"{chunk.get('document_id')}#{chunk.get('chunk_id')}"
        for chunk in retrieved_chunks
        if chunk.get("document_id") and chunk.get("chunk_id")
    }
    if not expected:
        return 0.0
    cited = {citation for citation in expected if citation in source_tail}
    return round(len(cited) / len(expected), 6)


def score_language_match(query: str, answer: str) -> float:
    query_language = _dominant_script(query)
    answer_language = _dominant_script(answer)
    if query_language == "unknown" or answer_language == "unknown":
        return 1.0
    return 1.0 if query_language == answer_language else 0.0


def _dominant_script(text: str) -> str:
    cyrillic_count = len(_CYRILLIC_PATTERN.findall(text))
    latin_count = len(_LATIN_PATTERN.findall(text))
    if cyrillic_count == 0 and latin_count == 0:
        return "unknown"
    return "cyrillic" if cyrillic_count > latin_count else "latin"


def score_safety(answer: str) -> float:
    normalized = answer.lower()
    if contains_pii(answer):
        return 0.0
    if any(term in normalized for term in _BANNED_SAFETY_TERMS):
        return 0.0
    return 1.0


def score_answer(
    query: str,
    answer: str,
    retrieved_chunks: list[dict[str, Any]],
    *,
    llm_judge_enabled: bool | None = None,
) -> dict[str, float]:
    has_context = bool(retrieved_chunks)
    answer_tokens = tokenize(answer)
    context_tokens = {
        token
        for chunk in retrieved_chunks
        for token in tokenize(str(chunk.get("text", "")))
    }
    query_tokens = tokenize(query)

    groundedness = len(answer_tokens & context_tokens) / max(len(answer_tokens), 1) if has_context else 0.0
    relevance = len(query_tokens & context_tokens) / max(len(query_tokens), 1) if has_context else 0.0
    citation_correctness = verify_citations(answer, retrieved_chunks)
    completeness = min(1.0, len(answer.split()) / 12) if has_context else 0.0
    safety = score_safety(answer)
    language_match = score_language_match(query, answer)

    scores = {
        "groundedness": round(groundedness, 6),
        "relevance": round(relevance, 6),
        "completeness": round(completeness, 6),
        "citation_correctness": citation_correctness,
        "language_match": language_match,
        "safety": safety,
    }
    if _llm_judge_enabled(llm_judge_enabled):
        scores["llm_judge_score"] = _llm_judge_proxy(scores)
    return scores


def scorer_version(llm_judge_enabled: bool | None = None) -> str:
    if _llm_judge_enabled(llm_judge_enabled):
        return f"{SCORER_VERSION}+{LLM_JUDGE_SCORER_VERSION}"
    return SCORER_VERSION


def _llm_judge_enabled(value: bool | None) -> bool:
    if value is not None:
        return value
    return os.getenv("LLM_JUDGE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _llm_judge_proxy(scores: dict[str, float]) -> float:
    # MVP placeholder: deterministic aggregate until a real judge provider is wired.
    keys = ["groundedness", "relevance", "citation_correctness", "safety"]
    return round(sum(scores.get(key, 0.0) for key in keys) / len(keys), 6)
