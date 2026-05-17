from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Chunk, DQResult, Document, EvalItem, ResponseLog, TraceEvent


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class CheckResult:
    entity_type: str
    check_name: str
    status: str
    metric_value: float
    details: dict


def _status(condition: bool) -> str:
    return "passed" if condition else "failed"


def run_checks() -> dict:
    run_id = uuid.uuid4()
    checks: list[CheckResult] = []

    with SessionLocal() as db:
        document_count = db.scalar(select(func.count()).select_from(Document)) or 0
        duplicate_hashes = db.execute(
            select(Document.content_hash, func.count(Document.id))
            .group_by(Document.content_hash)
            .having(func.count(Document.id) > 1)
        ).all()
        missing_document_sources = db.scalar(select(func.count()).select_from(Document).where(Document.source == "")) or 0

        chunk_count = db.scalar(select(func.count()).select_from(Chunk)) or 0
        empty_chunks = db.scalar(select(func.count()).select_from(Chunk).where(Chunk.chunk_text == "")) or 0
        missing_embeddings = db.scalar(select(func.count()).select_from(Chunk).where(Chunk.embedding_status != "indexed")) or 0

        eval_item_count = db.scalar(select(func.count()).select_from(EvalItem)) or 0
        eval_items_without_sources = (
            db.scalar(select(func.count()).select_from(EvalItem).where(EvalItem.expected_sources == {})) or 0
        )

        trace_event_count = db.scalar(select(func.count()).select_from(TraceEvent)) or 0
        responses_count = db.scalar(select(func.count()).select_from(ResponseLog)) or 0
        responses_missing_validation = (
            db.scalar(
                select(func.count())
                .select_from(ResponseLog)
                .where(ResponseLog.validation_status.is_(None))
            )
            or 0
        )

        checks.extend(
            [
                CheckResult("documents", "documents_exist", _status(document_count > 0), float(document_count), {}),
                CheckResult("documents", "content_hash_unique", _status(not duplicate_hashes), float(len(duplicate_hashes)), {"duplicates": [row[0] for row in duplicate_hashes]}),
                CheckResult("documents", "source_not_null", _status(missing_document_sources == 0), float(missing_document_sources), {}),
                CheckResult("chunks", "chunks_exist", _status(chunk_count > 0), float(chunk_count), {}),
                CheckResult("chunks", "chunk_text_not_empty", _status(empty_chunks == 0), float(empty_chunks), {}),
                CheckResult("chunks", "embedding_coverage", _status(missing_embeddings == 0), 1 - (missing_embeddings / max(chunk_count, 1)), {"missing_embeddings": missing_embeddings}),
                CheckResult("eval_items", "eval_items_min_50", _status(eval_item_count >= 50), float(eval_item_count), {}),
                CheckResult("eval_items", "expected_sources_not_empty", _status(eval_items_without_sources == 0), float(eval_items_without_sources), {}),
                CheckResult("trace_events", "trace_events_exist", _status(trace_event_count > 0), float(trace_event_count), {}),
                CheckResult("responses", "responses_exist", _status(responses_count > 0), float(responses_count), {}),
                CheckResult(
                    "responses",
                    "responses_validation_status_present",
                    _status(responses_missing_validation == 0),
                    float(responses_missing_validation),
                    {},
                ),
            ]
        )

        for check in checks:
            db.add(
                DQResult(
                    run_id=run_id,
                    entity_type=check.entity_type,
                    check_name=check.check_name,
                    status=check.status,
                    metric_value=check.metric_value,
                    details=check.details,
                )
            )
        db.commit()

    failed = [check for check in checks if check.status == "failed"]
    report = {
        "run_id": str(run_id),
        "status": "failed" if failed else "passed",
        "check_count": len(checks),
        "failed_check_count": len(failed),
        "checks": [asdict(check) for check in checks],
    }
    output = PROJECT_ROOT / "ge" / "data_docs" / "gx_runtime_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    result = run_checks()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "passed" else 1)
