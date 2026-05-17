from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(slots=True)
class MetricResult:
    name: str
    value: float
    status: str
    details: dict[str, Any]


@dataclass(slots=True)
class DirtyDataResult:
    metrics: list[MetricResult]
    run_status: str
    hard_gate_result: str
    soft_gate_result: str
    summary: dict[str, Any]
    events: list[dict[str, Any]]


def resolve_project_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def default_contract_path(category: str) -> str | None:
    default_paths = {
        "rag_documents": "datasets/samples/rag_dataset_contract.yaml",
    }
    return default_paths.get(category)


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"YAML payload must be a mapping: {path}")
    return payload


def load_contract(contract_path: str) -> dict[str, Any]:
    contract_payload = load_yaml(resolve_project_path(contract_path))
    return contract_payload["dataset_contract"]


def load_records(dataset_path: str) -> list[dict[str, Any]]:
    resolved_path = resolve_project_path(dataset_path)
    records: list[dict[str, Any]] = []
    with resolved_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def load_dirty_rules() -> dict[str, Any]:
    rules_payload = load_yaml(
        resolve_project_path("services/metric_runner/config/dirty_data_rules.yaml")
    )
    return rules_payload["dirty_data_rules"]


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 1.0
    return round(numerator / denominator, 6)


def _parse_timestamp(value: Any) -> bool:
    if value in (None, ""):
        return False
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _text_length_valid(value: Any, min_length: int, max_length: int) -> bool:
    if not isinstance(value, str):
        return False
    length = len(value.strip())
    return min_length <= length <= max_length


def _normalized_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value == unicodedata.normalize("NFC", value)


def _build_metric(
    metric_name: str,
    metric_value: float,
    rules: dict[str, Any],
    details: dict[str, Any],
) -> MetricResult:
    thresholds = rules["thresholds"]["metrics"].get(metric_name, {})
    comparator = thresholds.get("comparator", "lt")
    hard_value = thresholds.get("hard_fail")
    soft_value = thresholds.get("soft_warn")
    status = "ok"
    if hard_value is not None and _threshold_hit(metric_value, hard_value, comparator):
        status = "fail"
    elif soft_value is not None and _threshold_hit(metric_value, soft_value, comparator):
        status = "warn"
    return MetricResult(metric_name, metric_value, status, details)


def _threshold_hit(metric_value: float, threshold: float, comparator: str) -> bool:
    if comparator == "gt":
        return metric_value > threshold
    return metric_value < threshold


def analyze_dirty_data(
    dataset_path: str,
    contract_path: str,
    run_context: dict[str, Any] | None = None,
) -> DirtyDataResult:
    contract = load_contract(contract_path)
    rules = load_dirty_rules()
    records = load_records(dataset_path)
    run_context = run_context or {}

    required_fields: list[str] = contract.get("required_fields", [])
    primary_key: str = contract.get("primary_key", "id")
    event_time_field: str = contract.get("event_time_field", "updated_at")
    min_text_length = int(rules["constraints"].get("min_text_length", 1))
    max_text_length = int(rules["constraints"].get("max_text_length", 10000))
    allowed_languages = set(rules["constraints"].get("allowed_languages", []))
    expected_language = rules["constraints"].get("expected_primary_language")

    record_count = len(records)
    valid_schema = 0
    valid_patterns = 0
    valid_text_length = 0
    valid_normalization = 0
    complete_cells = 0
    total_required_cells = record_count * len(required_fields)
    schema_examples: list[dict[str, Any]] = []
    missing_examples: list[dict[str, Any]] = []
    duplicate_examples: list[dict[str, Any]] = []
    pattern_examples: list[dict[str, Any]] = []
    length_examples: list[dict[str, Any]] = []
    normalization_examples: list[dict[str, Any]] = []

    seen_primary_keys: dict[Any, int] = {}

    for index, record in enumerate(records):
        missing_fields = [field for field in required_fields if record.get(field) in (None, "")]
        complete_cells += len(required_fields) - len(missing_fields)

        schema_ok = not missing_fields and _parse_timestamp(record.get(event_time_field))
        if schema_ok:
            valid_schema += 1
        elif len(schema_examples) < 5:
            schema_examples.append(
                {"row_index": index, "doc_id": record.get(primary_key), "missing_fields": missing_fields}
            )

        if missing_fields and len(missing_examples) < 5:
            missing_examples.append(
                {"row_index": index, "doc_id": record.get(primary_key), "missing_fields": missing_fields}
            )

        language = record.get("language")
        pattern_ok = isinstance(language, str) and language in allowed_languages
        if pattern_ok:
            valid_patterns += 1
        elif len(pattern_examples) < 5:
            pattern_examples.append(
                {"row_index": index, "doc_id": record.get(primary_key), "language": language}
            )

        text_value = record.get("text")
        if _text_length_valid(text_value, min_text_length, max_text_length):
            valid_text_length += 1
        elif len(length_examples) < 5:
            length_examples.append(
                {
                    "row_index": index,
                    "doc_id": record.get(primary_key),
                    "text_length": len(text_value) if isinstance(text_value, str) else None,
                }
            )

        normalized_ok = _normalized_text(text_value)
        if normalized_ok:
            valid_normalization += 1
        elif len(normalization_examples) < 5:
            normalization_examples.append(
                {"row_index": index, "doc_id": record.get(primary_key), "text_preview": str(text_value)[:80]}
            )

        pk_value = record.get(primary_key)
        seen_primary_keys[pk_value] = seen_primary_keys.get(pk_value, 0) + 1

    duplicate_count = sum(count - 1 for count in seen_primary_keys.values() if count > 1)
    for index, record in enumerate(records):
        pk_value = record.get(primary_key)
        if seen_primary_keys.get(pk_value, 0) > 1 and len(duplicate_examples) < 5:
            duplicate_examples.append(
                {"row_index": index, "doc_id": pk_value, "duplicate_count": seen_primary_keys[pk_value]}
            )

    language_ratio = 0.0
    if expected_language and record_count:
        language_ratio = _safe_ratio(
            sum(1 for record in records if record.get("language") == expected_language),
            record_count,
        )

    metrics = [
        _build_metric(
            "schema_validity_ratio",
            _safe_ratio(valid_schema, record_count),
            rules,
            {"invalid_examples": schema_examples},
        ),
        _build_metric(
            "completeness_ratio",
            _safe_ratio(complete_cells, total_required_cells),
            rules,
            {"missing_examples": missing_examples},
        ),
        _build_metric(
            "missing_ratio",
            round(1 - _safe_ratio(complete_cells, total_required_cells), 6),
            rules,
            {"missing_examples": missing_examples},
        ),
        _build_metric(
            "duplicate_free_ratio",
            _safe_ratio(record_count - duplicate_count, record_count),
            rules,
            {"duplicate_examples": duplicate_examples},
        ),
        _build_metric(
            "duplicate_ratio",
            _safe_ratio(duplicate_count, record_count),
            rules,
            {"duplicate_examples": duplicate_examples},
        ),
        _build_metric(
            "pattern_validity_ratio",
            _safe_ratio(valid_patterns, record_count),
            rules,
            {"invalid_language_examples": pattern_examples},
        ),
        _build_metric(
            "text_length_validity_ratio",
            _safe_ratio(valid_text_length, record_count),
            rules,
            {"invalid_length_examples": length_examples},
        ),
        _build_metric(
            "normalization_ratio",
            _safe_ratio(valid_normalization, record_count),
            rules,
            {"non_normalized_examples": normalization_examples},
        ),
        _build_metric(
            "language_ratio",
            language_ratio if expected_language else 1.0,
            rules,
            {"expected_primary_language": expected_language},
        ),
    ]

    hard_failed_metrics = [metric.name for metric in metrics if metric.status == "fail"]
    soft_warn_metrics = [metric.name for metric in metrics if metric.status == "warn"]

    events: list[dict[str, Any]] = []
    for metric in metrics:
        if metric.status == "ok":
            continue
        severity = "critical" if metric.status == "fail" else "warning"
        events.append(
            {
                "category": "dirty_data",
                "status": metric.status,
                "severity": severity,
                "details": {
                    "metric_name": metric.name,
                    "metric_value": metric.value,
                    "diagnostics": metric.details,
                    "recommendation": rules["actions"].get(metric.name, "review dirty data issues"),
                },
            }
        )

    summary = {
        "record_count": record_count,
        "dataset_path": dataset_path,
        "contract_path": contract_path,
        "run_context": run_context,
        "hard_failed_metrics": hard_failed_metrics,
        "soft_warn_metrics": soft_warn_metrics,
        "ge_suite_path": "ge/expectations/rag_documents_dirty_data_suite.json",
        "data_docs_path": "ge/data_docs/index.html",
    }

    return DirtyDataResult(
        metrics=metrics,
        run_status="completed",
        hard_gate_result="fail" if hard_failed_metrics else "pass",
        soft_gate_result="warn" if soft_warn_metrics else "pass",
        summary=summary,
        events=events,
    )
