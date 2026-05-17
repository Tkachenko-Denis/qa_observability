import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DatasetCreate(BaseModel):
    name: str
    category: str = Field(default="rag_documents")
    description: str | None = None
    status: str = Field(default="draft")
    payload: dict[str, Any] = Field(default_factory=dict)


class DatasetRead(DatasetCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


class DatasetVersionCreate(BaseModel):
    version: str
    status: str = Field(default="draft")
    location_uri: str | None = None
    event_time_min: datetime | None = None
    event_time_max: datetime | None = None
    baseline_id: uuid.UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class DatasetVersionRead(DatasetVersionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_id: uuid.UUID
    created_at: datetime


class DQRunCreate(BaseModel):
    dataset_id: uuid.UUID
    dataset_version_id: uuid.UUID
    category: str
    baseline_id: uuid.UUID | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class DQRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_id: uuid.UUID
    dataset_version_id: uuid.UUID
    category: str
    status: str
    baseline_id: uuid.UUID | None
    hard_gate_result: str
    soft_gate_result: str
    details: dict[str, Any]
    created_at: datetime


class DQRunSummaryRead(BaseModel):
    dataset_id: uuid.UUID
    dataset_version_id: uuid.UUID
    category: str
    latest_run_id: uuid.UUID | None
    latest_status: str | None
    hard_gate_result: str | None
    soft_gate_result: str | None
    metric_count: int
    event_count: int
    metrics_by_status: dict[str, int]
    recent_alerts: list[dict[str, Any]]


class GateDecisionRead(BaseModel):
    dataset_id: uuid.UUID
    dataset_version_id: uuid.UUID
    publish_allowed: bool
    hard_gate_result: str | None
    soft_gate_result: str | None
    latest_categories: dict[str, dict[str, Any]]
    linked_runs: list[dict[str, Any]]


class DQMetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dq_run_id: uuid.UUID
    dataset_id: uuid.UUID
    dataset_version_id: uuid.UUID
    category: str
    metric_name: str
    metric_value: float
    status: str
    event_time_min: datetime | None
    event_time_max: datetime | None
    baseline_id: uuid.UUID | None
    details: dict[str, Any]
    created_at: datetime


class DQEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_id: uuid.UUID
    dataset_version_id: uuid.UUID | None
    dq_run_id: uuid.UUID | None
    category: str
    status: str
    severity: str
    event_time_min: datetime | None
    event_time_max: datetime | None
    details: dict[str, Any]
    created_at: datetime


class LLMOpsRunLinkCreate(BaseModel):
    dataset_id: uuid.UUID
    dataset_version_id: uuid.UUID
    dq_run_id: uuid.UUID | None = None
    external_system: str = Field(default="mlflow")
    external_run_id: str
    run_type: str
    status: str = Field(default="linked")
    run_name: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class LLMOpsRunLinkRead(LLMOpsRunLinkCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
    app_name: str
    app_env: str


class AskRequest(BaseModel):
    query: str = Field(min_length=1)
    session_id: uuid.UUID | None = None
    user_id: str | None = None
    locale: str = Field(default="en")
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    model_profile_id: str | None = None


class CitationRead(BaseModel):
    document_id: str
    source: str
    chunk_id: str


class AskResponse(BaseModel):
    request_id: uuid.UUID
    trace_id: uuid.UUID
    answer: str
    citations: list[CitationRead]
    scores: dict[str, float]
    status: str
    validation_status: str = "unknown"
    validation_reasons: list[str] = Field(default_factory=list)
    model_profile_id: str
    provider: str
    model_name: str
    model_version: str
    finish_reason: str
    scorer_version: str


class ModelProfileRead(BaseModel):
    id: str
    label: str
    provider: str
    model_name: str
    enabled: bool
    status: str
    reason: str | None = None
    description: str
    details: dict[str, Any] = Field(default_factory=dict)


class ModelsResponse(BaseModel):
    default_model_profile_id: str
    models: list[ModelProfileRead]


class FeedbackCreate(BaseModel):
    request_id: uuid.UUID | None = None
    trace_id: uuid.UUID | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class FeedbackRead(FeedbackCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trace_id: uuid.UUID | None
    event_type: str
    user_id_hash: str | None
    details: dict[str, Any]
    created_at: datetime


class TraceEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trace_id: uuid.UUID
    request_id: uuid.UUID | None
    span_name: str
    status: str
    latency_ms: int | None
    payload: dict[str, Any]
    created_at: datetime


class TraceSummaryRead(BaseModel):
    trace_id: uuid.UUID
    request_id: uuid.UUID
    created_at: datetime
    status: str
    model_name: str | None = None
    model_profile_id: str | None = None
    query_preview: str


class TraceListRead(BaseModel):
    traces: list[TraceSummaryRead]


class EvalRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_name: str
    model_name: str
    model_version: str
    prompt_version: str
    status: str
    metrics: dict[str, Any]
    artifacts: dict[str, Any]
    created_at: datetime


class EvalScoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    eval_run_id: uuid.UUID
    eval_item_id: uuid.UUID
    metric_name: str
    metric_value: float
    scorer: str
    details: dict[str, Any]
    created_at: datetime


class DQResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID | None
    trace_id: uuid.UUID | None
    entity_type: str
    check_name: str
    status: str
    metric_value: float | None
    details: dict[str, Any]
    created_at: datetime


class DQResultsLatestRead(BaseModel):
    run_id: uuid.UUID | None
    status: str
    check_count: int
    passed_count: int
    failed_count: int
    results: list[DQResultRead]


class QualityGateResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID | None
    trace_id: uuid.UUID | None
    gate_status: str
    failed_checks: dict[str, Any] | list[Any]
    metrics_snapshot: dict[str, Any]
    created_at: datetime


class LLMOpsReadinessRead(BaseModel):
    status: str
    failed_signals: list[str]
    latest_eval_run: dict[str, Any] | None
    latest_dq_run: dict[str, Any] | None
    latest_quality_gate: dict[str, Any] | None
    metrics: dict[str, Any]


class IntegrationStatusRead(BaseModel):
    name: str
    enabled: bool
    mode: str
    required_for_mvp: bool
    fallback: str
    capabilities: list[str]
    details: dict[str, Any] = Field(default_factory=dict)


class IntegrationContractsRead(BaseModel):
    milvus: dict[str, Any]
    langfuse: dict[str, Any]
    mlflow: dict[str, Any]

