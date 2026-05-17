from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.config import Settings
from app.llm.prompts import assemble_prompt, default_rag_prompt
from app.llm.provider import ModelProfileError, build_provider_from_profile, resolve_model_profile
from app.models import Message, RequestLog, ResponseCitation, ResponseLog, SessionRecord
from app.observability import observe_ask_flow
from app.observability_tools.trace_logger import log_trace_event
from app.quality.retrieval_metrics import retrieval_metric_snapshot
from app.quality.scorers import score_answer, scorer_version
from app.quality.validators import validate_answer_details
from app.retrieval.milvus_client import MilvusRetriever
from app.retrieval.retriever import BaseRetriever, FileBackedRetriever, RetrievalResult
from app.security import contains_pii, mask_pii


FALLBACK_ANSWER = (
    "I do not have enough context to answer this question based on the available documents.\n"
    "Sources: none"
)


def _hash_user_id(user_id: str | None) -> str | None:
    if not user_id:
        return None
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()


def build_retriever(settings: Settings) -> BaseRetriever:
    file_retriever = FileBackedRetriever(settings.default_rag_dataset_path, top_k=settings.rag_top_k)
    if settings.milvus_enabled:
        return MilvusRetriever(settings, fallback_retriever=file_retriever, top_k=settings.rag_top_k)
    return file_retriever


def prepare_persisted_input(
    query: str,
    normalized_query: str,
    attachments: list[dict[str, Any]],
    *,
    store_raw_input: bool,
) -> dict[str, Any]:
    pii_detected = contains_pii({"query": query, "attachments": attachments})
    if store_raw_input:
        return {
            "query": query,
            "normalized_query": normalized_query,
            "attachments": attachments,
            "pii_detected": pii_detected,
            "raw_input_stored": True,
        }
    return {
        "query": mask_pii(query),
        "normalized_query": mask_pii(normalized_query),
        "attachments": mask_pii(attachments),
        "pii_detected": pii_detected,
        "raw_input_stored": False,
    }


def prepare_persisted_output(answer: str, *, store_raw_output: bool) -> dict[str, Any]:
    pii_detected = contains_pii(answer)
    if store_raw_output:
        return {
            "answer": answer,
            "pii_detected": pii_detected,
            "raw_output_stored": True,
        }
    return {
        "answer": mask_pii(answer),
        "pii_detected": pii_detected,
        "raw_output_stored": False,
    }


def best_retrieval_score(retrieval: RetrievalResult) -> float:
    if not retrieval.chunks:
        return 0.0
    return max(float(chunk.get("score", 0.0) or 0.0) for chunk in retrieval.chunks)


def has_sufficient_context(retrieval: RetrievalResult, min_score: float) -> bool:
    if retrieval.no_context or not retrieval.chunks:
        return False
    return best_retrieval_score(retrieval) >= min_score


def fallback_scores(query: str, answer: str) -> dict[str, float]:
    return {
        "groundedness": 0.0,
        "relevance": 0.0,
        "completeness": 0.0,
        "citation_correctness": 0.0,
        "language_match": 1.0,
        "safety": 1.0 if not contains_pii(answer) else 0.0,
    }


def raw_answer_diagnostics(raw_answer: str, *, store_raw_output: bool) -> dict[str, Any]:
    if store_raw_output:
        return {
            "raw_model_answer": raw_answer,
            "raw_model_answer_stored": True,
        }
    masked = mask_pii(raw_answer)
    return {
        "raw_model_answer_preview": str(masked)[:240],
        "raw_model_answer_sha256": hashlib.sha256(raw_answer.encode("utf-8")).hexdigest(),
        "raw_model_answer_stored": False,
    }


def run_rag_ask(db: Session, payload: Any, settings: Settings) -> dict[str, Any]:
    try:
        model_profile = resolve_model_profile(settings, getattr(payload, "model_profile_id", None))
    except ModelProfileError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    request_id = uuid.uuid4()
    trace_id = uuid.uuid4()
    session_id = uuid.UUID(str(payload.session_id)) if payload.session_id else uuid.uuid4()
    user_id_hash = _hash_user_id(payload.user_id)
    normalized_query = payload.query.strip()
    persisted_input = prepare_persisted_input(
        payload.query,
        normalized_query,
        payload.attachments,
        store_raw_input=settings.store_raw_input,
    )

    session_record = db.get(SessionRecord, session_id)
    if session_record is None:
        session_record = SessionRecord(id=session_id, user_id_hash=user_id_hash, payload={})
        db.add(session_record)
        db.flush()

    request_log = RequestLog(
        id=request_id,
        trace_id=trace_id,
        session_id=session_id,
        user_id_hash=user_id_hash,
        query=persisted_input["query"],
        normalized_query=persisted_input["normalized_query"],
        locale=payload.locale,
        channel="api",
        status="running",
        payload={
            "attachments": persisted_input["attachments"],
            "model_profile_id": model_profile.id,
            "provider": model_profile.provider,
            "pii_detected": persisted_input["pii_detected"],
            "raw_input_stored": persisted_input["raw_input_stored"],
        },
    )
    db.add(request_log)
    db.flush()
    db.add(
        Message(
            session_id=session_id,
            trace_id=trace_id,
            role="user",
            content=persisted_input["query"],
            payload={
                "pii_detected": persisted_input["pii_detected"],
                "raw_input_stored": persisted_input["raw_input_stored"],
            },
        )
    )

    prompt_config = default_rag_prompt()
    trace_context = {
        "session_id": session_id,
        "prompt_version": prompt_config.prompt_version,
        "retrieval_top_k": settings.rag_top_k,
        "dataset_version": settings.default_rag_dataset_version,
        "model_profile_id": model_profile.id,
        "provider": model_profile.provider,
    }
    log_trace_event(
        db,
        trace_id,
        request_id,
        "input_normalization",
        "success",
        {"locale": payload.locale},
        **trace_context,
    )
    retriever = build_retriever(settings)
    retrieval = retriever.retrieve(normalized_query)
    log_trace_event(
        db,
        trace_id,
        request_id,
        "retrieval",
        "success",
        retrieval_metric_snapshot(retrieval.chunks, retrieval.latency_ms),
        retrieval.latency_ms,
        **trace_context,
    )
    active_scorer_version = scorer_version(settings.llm_judge_enabled)
    best_score = best_retrieval_score(retrieval)
    if not has_sufficient_context(retrieval, settings.rag_min_retrieval_score):
        scores = fallback_scores(normalized_query, FALLBACK_ANSWER)
        validation_status = "fallback"
        response_status = "fallback"
        persisted_output = prepare_persisted_output(
            FALLBACK_ANSWER,
            store_raw_output=settings.store_raw_output,
        )
        log_trace_event(
            db,
            trace_id,
            request_id,
            "fallback_decision",
            "fallback",
            {
                "reason": "insufficient_context",
                "retrieval_no_context": retrieval.no_context,
                "best_retrieval_score": best_score,
                "min_retrieval_score": settings.rag_min_retrieval_score,
            },
            scores=scores,
            validation_status=validation_status,
            **trace_context,
        )
        log_trace_event(
            db,
            trace_id,
            request_id,
            "llm_call",
            "skipped",
            {
                "reason": "insufficient_context",
                "model_profile_id": model_profile.id,
                "provider": model_profile.provider,
                "model_name": model_profile.model_name,
            },
            model_name=f"{model_profile.provider}:{model_profile.model_name}",
            input_tokens=0,
            output_tokens=0,
            **trace_context,
        )

        response_log = ResponseLog(
            request_id=request_id,
            trace_id=trace_id,
            answer=persisted_output["answer"],
            status=response_status,
            validation_status=validation_status,
            scores=scores,
            payload={
                "retrieval": retrieval_metric_snapshot(retrieval.chunks, retrieval.latency_ms),
                "model_name": f"{model_profile.provider}:{model_profile.model_name}",
                "model_profile_id": model_profile.id,
                "provider": model_profile.provider,
                "model_version": "fallback",
                "finish_reason": "fallback:insufficient_context",
                "prompt_version": prompt_config.prompt_version,
                "scorer_version": active_scorer_version,
                "pii_detected": persisted_output["pii_detected"],
                "raw_output_stored": persisted_output["raw_output_stored"],
                "reason": "insufficient_context",
                "fallback_reason": "insufficient_context",
                "validation_reasons": ["insufficient_context"],
                "user_visible_answer_replaced": False,
                "best_retrieval_score": best_score,
                "min_retrieval_score": settings.rag_min_retrieval_score,
            },
        )
        db.add(response_log)
        db.flush()
        db.add(
            Message(
                session_id=session_id,
                trace_id=trace_id,
                role="assistant",
                content=persisted_output["answer"],
                payload={
                    "scores": scores,
                    "citations": [],
                    "scorer_version": active_scorer_version,
                    "pii_detected": persisted_output["pii_detected"],
                    "raw_output_stored": persisted_output["raw_output_stored"],
                    "validation_status": validation_status,
                    "validation_reasons": ["insufficient_context"],
                },
            )
        )
        request_log.status = response_status
        request_log.finished_at = datetime.now(UTC)
        log_trace_event(
            db,
            trace_id,
            request_id,
            "response_delivery",
            response_status,
            {
                "status": response_status,
                "scorer_version": active_scorer_version,
                "validation_reasons": ["insufficient_context"],
            },
            scores=scores,
            validation_status=validation_status,
            model_name=f"{model_profile.provider}:{model_profile.model_name}",
            input_tokens=0,
            output_tokens=0,
            **trace_context,
        )
        observe_ask_flow(
            status=response_status,
            retrieval_latency_ms=retrieval.latency_ms,
            llm_latency_ms=0,
            scores=scores,
            input_tokens=0,
            output_tokens=0,
            no_context=True,
        )
        db.commit()

        return {
            "request_id": request_id,
            "trace_id": trace_id,
            "answer": FALLBACK_ANSWER,
            "citations": [],
            "scores": scores,
            "status": response_status,
            "validation_status": validation_status,
            "validation_reasons": ["insufficient_context"],
            "model_name": f"{model_profile.provider}:{model_profile.model_name}",
            "model_profile_id": model_profile.id,
            "provider": model_profile.provider,
            "model_version": "fallback",
            "finish_reason": "fallback:insufficient_context",
            "scorer_version": active_scorer_version,
        }

    assembled_prompt = assemble_prompt(normalized_query, retrieval.chunks, prompt_config)
    log_trace_event(
        db,
        trace_id,
        request_id,
        "prompt_assembly",
        "success",
        {"prompt_version": prompt_config.prompt_version, "prompt_hash": prompt_config.prompt_hash},
        **trace_context,
    )

    provider = build_provider_from_profile(settings, model_profile)
    llm_result = provider.generate(assembled_prompt, retrieval.chunks, normalized_query)
    llm_call_status = "failed" if llm_result.finish_reason.startswith("error:") else "success"
    log_trace_event(
        db,
        trace_id,
        request_id,
        "llm_call",
        llm_call_status,
        {
            "model_name": llm_result.model_name,
            "model_profile_id": model_profile.id,
            "provider": model_profile.provider,
            "model_version": llm_result.model_version,
            "input_tokens": llm_result.input_tokens,
            "output_tokens": llm_result.output_tokens,
            "finish_reason": llm_result.finish_reason,
            "mock_fallback_allowed": settings.llm_allow_mock_fallback,
        },
        llm_result.latency_ms,
        model_name=llm_result.model_name,
        input_tokens=llm_result.input_tokens,
        output_tokens=llm_result.output_tokens,
        **trace_context,
    )

    citations = [
        {
            "document_id": chunk["document_id"],
            "source": chunk["source"],
            "chunk_id": chunk["chunk_id"],
        }
        for chunk in retrieval.chunks
    ]
    scores = score_answer(
        normalized_query,
        llm_result.raw_answer,
        retrieval.chunks,
        llm_judge_enabled=settings.llm_judge_enabled,
    )
    validation = validate_answer_details(llm_result.raw_answer, citations, scores)
    validation_status = validation.status
    validation_reasons = validation.reasons
    response_status = "success" if validation_status == "passed" else "failed"
    user_visible_answer = llm_result.raw_answer
    user_visible_citations = citations
    post_validation_fallback_applied = False
    raw_diagnostics: dict[str, Any] = {}
    llm_call_failed = llm_result.finish_reason.startswith("error:")
    if not llm_call_failed and validation.status == "failed" and validation.is_grounding_failure:
        post_validation_fallback_applied = True
        response_status = "fallback"
        validation_status = "fallback"
        user_visible_answer = FALLBACK_ANSWER
        user_visible_citations = []
        raw_diagnostics = raw_answer_diagnostics(
            llm_result.raw_answer,
            store_raw_output=settings.store_raw_output,
        )
        log_trace_event(
            db,
            trace_id,
            request_id,
            "post_validation_fallback",
            "fallback",
            {
                "reason": "validation_failed",
                "validation_reasons": validation_reasons,
                **raw_diagnostics,
            },
            scores=scores,
            validation_status=validation_status,
            model_name=llm_result.model_name,
            input_tokens=llm_result.input_tokens,
            output_tokens=llm_result.output_tokens,
            **trace_context,
        )
    persisted_output = prepare_persisted_output(
        user_visible_answer,
        store_raw_output=settings.store_raw_output,
    )
    log_trace_event(
        db,
        trace_id,
        request_id,
        "validation",
        validation_status,
        {
            "scores": scores,
            "citation_count": len(citations),
            "scorer_version": active_scorer_version,
            "validation_reasons": validation_reasons,
            "user_visible_answer_replaced": post_validation_fallback_applied,
        },
        scores=scores,
        validation_status=validation_status,
        model_name=llm_result.model_name,
        input_tokens=llm_result.input_tokens,
        output_tokens=llm_result.output_tokens,
        **trace_context,
    )

    response_log = ResponseLog(
        request_id=request_id,
        trace_id=trace_id,
        answer=persisted_output["answer"],
        status=response_status,
        validation_status=validation_status,
        scores=scores,
        payload={
            "retrieval": retrieval_metric_snapshot(retrieval.chunks, retrieval.latency_ms),
            "model_name": llm_result.model_name,
            "model_profile_id": model_profile.id,
            "provider": model_profile.provider,
            "model_version": llm_result.model_version,
            "finish_reason": llm_result.finish_reason,
            "prompt_version": prompt_config.prompt_version,
            "scorer_version": active_scorer_version,
            "pii_detected": persisted_output["pii_detected"],
            "raw_output_stored": persisted_output["raw_output_stored"],
            "validation_reasons": validation_reasons,
            "user_visible_answer_replaced": post_validation_fallback_applied,
            "fallback_reason": "validation_failed" if post_validation_fallback_applied else None,
            **raw_diagnostics,
        },
    )
    db.add(response_log)
    db.flush()
    for citation in user_visible_citations:
        db.add(ResponseCitation(response_id=response_log.id, **citation))

    db.add(
        Message(
            session_id=session_id,
            trace_id=trace_id,
            role="assistant",
            content=persisted_output["answer"],
            payload={
                "scores": scores,
                "citations": user_visible_citations,
                "scorer_version": active_scorer_version,
                "pii_detected": persisted_output["pii_detected"],
                "raw_output_stored": persisted_output["raw_output_stored"],
                "validation_status": validation_status,
                "validation_reasons": validation_reasons,
                "user_visible_answer_replaced": post_validation_fallback_applied,
            },
        )
    )
    request_log.status = response_log.status
    request_log.finished_at = datetime.now(UTC)
    log_trace_event(
        db,
        trace_id,
        request_id,
        "response_delivery",
        response_log.status,
        {"status": response_log.status, "scorer_version": active_scorer_version},
        scores=scores,
        validation_status=validation_status,
        model_name=llm_result.model_name,
        input_tokens=llm_result.input_tokens,
        output_tokens=llm_result.output_tokens,
        **trace_context,
    )

    observe_ask_flow(
        status=response_log.status,
        retrieval_latency_ms=retrieval.latency_ms,
        llm_latency_ms=llm_result.latency_ms,
        scores=scores,
        input_tokens=llm_result.input_tokens,
        output_tokens=llm_result.output_tokens,
        no_context=retrieval.no_context,
    )
    db.commit()

    return {
        "request_id": request_id,
        "trace_id": trace_id,
        "answer": user_visible_answer,
        "citations": user_visible_citations,
        "scores": scores,
        "status": response_log.status,
        "validation_status": validation_status,
        "validation_reasons": validation_reasons,
        "model_name": llm_result.model_name,
        "model_profile_id": model_profile.id,
        "provider": model_profile.provider,
        "model_version": llm_result.model_version,
        "finish_reason": llm_result.finish_reason,
        "scorer_version": active_scorer_version,
    }
