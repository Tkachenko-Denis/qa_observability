from pathlib import Path

from app.quality.scorers import SCORER_VERSION, score_answer, score_language_match, score_safety, verify_citations


def test_citation_verifier_requires_exact_retrieved_chunk_reference() -> None:
    chunks = [
        {
            "chunk_id": "doc-001-chunk-0",
            "document_id": "doc-001",
            "text": "Customers may return unopened items within 30 days.",
        }
    ]

    assert verify_citations("Answer. Sources: doc-001#doc-001-chunk-0", chunks) == 1.0
    assert verify_citations("Answer. Sources: doc-999#missing", chunks) == 0.0
    assert verify_citations("Answer without source", chunks) == 0.0


def test_language_match_detects_script_mismatch() -> None:
    assert score_language_match("What is the return policy?", "Customers may return items.") == 1.0
    assert score_language_match("Как вернуть товар?", "Customers may return items.") == 0.0
    assert score_language_match("123", "Customers may return items.") == 1.0


def test_safety_scorer_flags_pii_and_sensitive_terms() -> None:
    assert score_safety("Contact support at user@example.com") == 0.0
    assert score_safety("The secret token is abc") == 0.0
    assert score_safety("Customers may return unopened items.") == 1.0


def test_score_answer_keeps_baseline_metrics_and_optional_llm_judge_proxy() -> None:
    chunks = [
        {
            "chunk_id": "doc-001-chunk-0",
            "document_id": "doc-001",
            "text": "Customers may return unopened items within 30 days.",
        }
    ]

    scores = score_answer(
        "What is the return policy?",
        "Customers may return unopened items. Sources: doc-001#doc-001-chunk-0",
        chunks,
        llm_judge_enabled=True,
    )

    assert scores["citation_correctness"] == 1.0
    assert scores["language_match"] == 1.0
    assert scores["safety"] == 1.0
    assert "llm_judge_score" in scores


def test_scorer_version_is_stored_in_response_and_eval_contracts() -> None:
    schema = Path("services/api/app/schemas.py").read_text(encoding="utf-8")
    rag_chain = Path("services/api/app/llm/rag_chain.py").read_text(encoding="utf-8")
    run_eval = Path("scripts/run_eval.py").read_text(encoding="utf-8")

    assert f'SCORER_VERSION = "{SCORER_VERSION}"' in Path("services/api/app/quality/scorers.py").read_text(encoding="utf-8")
    assert "scorer_version: str" in schema
    assert '"scorer_version": active_scorer_version' in rag_chain
    assert 'response["scorer_version"]' in run_eval
