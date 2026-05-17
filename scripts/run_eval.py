from __future__ import annotations

import argparse
import csv
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.llm.rag_chain import run_rag_ask
from app.models import EvalItem, EvalRun, EvalScore
from app.observability_tools.mlflow_client import MLflowEvalRunContract, MLflowTrackingClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def load_eval_items(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _upsert_eval_item(db, row: dict[str, str]) -> EvalItem:
    item = db.scalar(select(EvalItem).where(EvalItem.item_id == row["item_id"]))
    expected_sources = [source.strip() for source in row["expected_sources"].split("|") if source.strip()]
    if item is None:
        item = EvalItem(
            item_id=row["item_id"],
            question=row["question"],
            expected_sources={"document_ids": expected_sources},
            metadata_payload={"construct": row["construct"], "locale": row["locale"]},
        )
        db.add(item)
        db.flush()
        return item

    item.question = row["question"]
    item.expected_sources = {"document_ids": expected_sources}
    item.metadata_payload = {"construct": row["construct"], "locale": row["locale"]}
    return item


def run_eval(eval_items_path: str, output_dir: str) -> dict:
    settings = get_settings()
    rows = load_eval_items(resolve_path(eval_items_path))
    run_id = uuid.uuid4()
    output = resolve_path(output_dir) / str(run_id)
    output.mkdir(parents=True, exist_ok=True)

    eval_results: list[dict] = []
    failed_cases: list[dict] = []
    observed_model_name: str | None = None
    observed_model_version: str | None = None

    with SessionLocal() as db:
        eval_run = EvalRun(
            id=run_id,
            run_name=f"rag_eval_{run_id}",
            model_name=f"{settings.llm_provider}:{settings.local_llm_model}",
            model_version="pending",
            prompt_version="rag-v1",
            status="running",
            metrics={},
            artifacts={},
        )
        db.add(eval_run)
        db.flush()

        for row in rows:
            item = _upsert_eval_item(db, row)
            db.commit()
            response = run_rag_ask(
                db,
                SimpleNamespace(
                    query=row["question"],
                    session_id=None,
                    user_id="eval-runner",
                    locale=row["locale"],
                    attachments=[],
                ),
                settings,
            )
            observed_model_name = observed_model_name or str(response["model_name"])
            observed_model_version = observed_model_version or str(response["model_version"])
            cited_documents = {citation["document_id"] for citation in response["citations"]}
            expected_documents = set(item.expected_sources["document_ids"])
            source_hit = 1.0 if cited_documents & expected_documents else 0.0

            metrics = dict(response["scores"])
            metrics["source_hit"] = source_hit
            for metric_name, metric_value in metrics.items():
                db.add(
                    EvalScore(
                        eval_run_id=eval_run.id,
                        eval_item_id=item.id,
                        metric_name=metric_name,
                        metric_value=float(metric_value),
                        scorer="custom",
                        details={"trace_id": str(response["trace_id"])},
                    )
                )

            result_row = {
                "item_id": row["item_id"],
                "trace_id": str(response["trace_id"]),
                "status": response["status"],
                "model_name": response["model_name"],
                "model_version": response["model_version"],
                "finish_reason": response["finish_reason"],
                "scorer_version": response["scorer_version"],
                "expected_sources": row["expected_sources"],
                "cited_sources": "|".join(sorted(cited_documents)),
                **{key: metrics[key] for key in sorted(metrics)},
            }
            eval_results.append(result_row)
            if source_hit < 1.0 or response["status"] != "success":
                failed_cases.append(result_row)

        metadata_columns = {
            "item_id",
            "trace_id",
            "status",
            "model_name",
            "model_version",
            "finish_reason",
            "scorer_version",
            "expected_sources",
            "cited_sources",
        }
        metric_names = sorted({key for row in eval_results for key in row if key not in metadata_columns})
        aggregate_metrics = {
            metric_name: round(
                sum(float(row[metric_name]) for row in eval_results) / max(len(eval_results), 1),
                6,
            )
            for metric_name in metric_names
        }
        eval_run.status = "completed"
        eval_run.model_name = observed_model_name or eval_run.model_name
        eval_run.model_version = observed_model_version or "not_available"
        eval_run.metrics = aggregate_metrics
        eval_run.artifacts = {
            "eval_results": str(output / "eval_results.csv"),
            "failed_cases": str(output / "failed_cases.json"),
        }
        db.commit()

    results_path = output / "eval_results.csv"
    with results_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(eval_results[0].keys()))
        writer.writeheader()
        writer.writerows(eval_results)
    failed_cases_path = output / "failed_cases.json"
    failed_cases_path.write_text(json.dumps(failed_cases, indent=2), encoding="utf-8")

    mlflow_status = MLflowTrackingClient(settings).log_eval_run(
        MLflowEvalRunContract(
            run_name=f"rag_eval_{run_id}",
            model_name=observed_model_name or f"{settings.llm_provider}:{settings.local_llm_model}",
            model_version=observed_model_version or "not_available",
            prompt_version="rag-v1",
            metrics={key: float(value) for key, value in aggregate_metrics.items()},
            artifacts={
                "eval_results": str(results_path),
                "failed_cases": str(failed_cases_path),
            },
            params={
                "eval_dataset_path": str(resolve_path(eval_items_path)),
                "eval_dataset_version": "not specified",
                "retrieval_top_k": settings.rag_top_k,
                "llm_provider": settings.llm_provider,
                "llm_model_name": observed_model_name or "not_available",
                "llm_model_version": observed_model_version or "not_available",
                "scorer_version": eval_results[0].get("scorer_version", "not_available") if eval_results else "not_available",
            },
        )
    )

    with SessionLocal() as db:
        eval_run = db.get(EvalRun, run_id)
        if eval_run is not None:
            eval_run.artifacts = {**eval_run.artifacts, "mlflow": mlflow_status}
            db.commit()

    return {
        "eval_run_id": str(run_id),
        "item_count": len(rows),
        "failed_case_count": len(failed_cases),
        "metrics": aggregate_metrics,
        "artifacts": {
            "eval_results": str(results_path),
            "failed_cases": str(output / "failed_cases.json"),
        },
        "mlflow": mlflow_status,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-items", default="eval/eval_items.csv")
    parser.add_argument("--output-dir", default="mlflow/eval_runs")
    args = parser.parse_args()

    print(json.dumps(run_eval(args.eval_items, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
