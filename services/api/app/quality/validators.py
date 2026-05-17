from __future__ import annotations

from dataclasses import dataclass


GROUNDING_FAILURE_REASONS = {
    "missing_sources_line",
    "missing_citations",
    "low_citation_correctness",
    "low_groundedness",
}


@dataclass(frozen=True, slots=True)
class ValidationResult:
    status: str
    reasons: list[str]

    @property
    def is_grounding_failure(self) -> bool:
        return any(reason in GROUNDING_FAILURE_REASONS for reason in self.reasons)


def validate_answer_details(answer: str, citations: list[dict], scores: dict[str, float]) -> ValidationResult:
    reasons: list[str] = []
    if not answer.strip():
        reasons.append("empty_answer")
    if not citations:
        reasons.append("missing_citations")
    if "Sources:" not in answer:
        reasons.append("missing_sources_line")
    if scores.get("citation_correctness", 0.0) <= 0:
        reasons.append("low_citation_correctness")
    if scores.get("groundedness", 0.0) <= 0:
        reasons.append("low_groundedness")
    return ValidationResult(status="passed" if not reasons else "failed", reasons=reasons)


def validate_answer(answer: str, citations: list[dict], scores: dict[str, float]) -> str:
    return validate_answer_details(answer, citations, scores).status
