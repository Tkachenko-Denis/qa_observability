from app.quality.scorers import score_answer
from app.quality.validators import validate_answer, validate_answer_details


def test_answer_without_sources_fails_validation() -> None:
    chunks = [{"chunk_id": "chunk-1", "document_id": "doc-1", "text": "Return policy allows 30 days."}]
    answer = "Return policy allows 30 days."
    citations = [{"document_id": "doc-1", "source": "kb", "chunk_id": "chunk-1"}]

    scores = score_answer("What is the return policy?", answer, chunks)

    assert scores["citation_correctness"] == 0.0
    assert validate_answer(answer, citations, scores) == "failed"
    details = validate_answer_details(answer, citations, scores)
    assert details.is_grounding_failure is True
    assert "missing_sources_line" in details.reasons


def test_answer_with_invalid_source_fails_validation() -> None:
    chunks = [{"chunk_id": "chunk-1", "document_id": "doc-1", "text": "Return policy allows 30 days."}]
    answer = "Return policy allows 30 days. Sources: doc-999#chunk-999"
    citations = [{"document_id": "doc-1", "source": "kb", "chunk_id": "chunk-1"}]

    scores = score_answer("What is the return policy?", answer, chunks)

    assert scores["citation_correctness"] == 0.0
    assert validate_answer(answer, citations, scores) == "failed"
    details = validate_answer_details(answer, citations, scores)
    assert details.is_grounding_failure is True
    assert "low_citation_correctness" in details.reasons


def test_answer_with_low_groundedness_fails_validation() -> None:
    chunks = [{"chunk_id": "chunk-1", "document_id": "doc-1", "text": "Return policy allows 30 days."}]
    answer = "Unrelated generic response. Sources: doc-1#chunk-1"
    citations = [{"document_id": "doc-1", "source": "kb", "chunk_id": "chunk-1"}]

    scores = score_answer("What is the return policy?", answer, chunks)
    details = validate_answer_details(answer, citations, scores)

    assert scores["groundedness"] == 0.0
    assert details.status == "failed"
    assert details.is_grounding_failure is True
    assert "low_groundedness" in details.reasons


def test_answer_with_valid_source_passes_validation() -> None:
    chunks = [{"chunk_id": "chunk-1", "document_id": "doc-1", "text": "Return policy allows 30 days."}]
    answer = "Return policy allows 30 days. Sources: doc-1#chunk-1"
    citations = [{"document_id": "doc-1", "source": "kb", "chunk_id": "chunk-1"}]

    scores = score_answer("What is the return policy?", answer, chunks)

    assert scores["citation_correctness"] == 1.0
    assert validate_answer(answer, citations, scores) == "passed"
