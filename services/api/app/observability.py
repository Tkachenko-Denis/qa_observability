from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

from app.config import get_settings

settings = get_settings()
registry = CollectorRegistry()

http_requests_total = Counter(
    "http_requests_total",
    "HTTP requests handled by the app",
    ["endpoint", "status"],
    registry=registry,
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["endpoint"],
    registry=registry,
)

http_errors_total = Counter(
    "http_errors_total",
    "HTTP errors handled by the app",
    ["endpoint"],
    registry=registry,
)

user_feedback_total = Counter(
    "user_feedback_total",
    "User feedback events",
    ["rating"],
    registry=registry,
)

retrieval_latency_seconds = Histogram(
    "retrieval_latency_seconds",
    "Retrieval latency in seconds",
    registry=registry,
)

retrieval_empty_results_total = Counter(
    "retrieval_empty_results_total",
    "Retrieval calls with no returned context",
    registry=registry,
)

llm_latency_seconds = Histogram(
    "llm_latency_seconds",
    "LLM provider latency in seconds",
    registry=registry,
)

llm_errors_total = Counter(
    "llm_errors_total",
    "LLM provider errors",
    registry=registry,
)

llm_input_tokens_total = Counter(
    "llm_input_tokens_total",
    "LLM input tokens",
    registry=registry,
)

llm_output_tokens_total = Counter(
    "llm_output_tokens_total",
    "LLM output tokens",
    registry=registry,
)

llm_empty_answers_total = Counter(
    "llm_empty_answers_total",
    "LLM responses with empty answer text",
    registry=registry,
)

validation_pass_total = Counter(
    "validation_pass_total",
    "Responses passing validation",
    registry=registry,
)

validation_failed_total = Counter(
    "validation_failed_total",
    "Responses failing validation",
    registry=registry,
)

groundedness_score = Gauge(
    "groundedness_score",
    "Latest groundedness score",
    registry=registry,
)

relevance_score = Gauge(
    "relevance_score",
    "Latest relevance score",
    registry=registry,
)

completeness_score = Gauge(
    "completeness_score",
    "Latest completeness score",
    registry=registry,
)

citation_correctness_score = Gauge(
    "citation_correctness_score",
    "Latest citation correctness score",
    registry=registry,
)

safety_score = Gauge(
    "safety_score",
    "Latest safety score",
    registry=registry,
)

dq_checks_failed_total = Counter(
    "dq_checks_failed_total",
    "DQ checks failed",
    ["category"],
    registry=registry,
)

quality_gate_status = Gauge(
    "quality_gate_status",
    "Quality gate status where 1 is passed and 0 is failed",
    ["gate"],
    registry=registry,
)

eval_run_status = Gauge(
    "eval_run_status",
    "Latest eval run status by model and prompt version",
    ["model", "prompt_version", "status"],
    registry=registry,
)

eval_metric_value = Gauge(
    "eval_metric_value",
    "Latest aggregate eval metric value",
    ["model", "prompt_version", "metric_name"],
    registry=registry,
)

runtime_dq_failed_checks = Gauge(
    "runtime_dq_failed_checks",
    "Failed runtime DQ checks in the latest runtime DQ run",
    ["run_id"],
    registry=registry,
)

llmops_readiness_status = Gauge(
    "llmops_readiness_status",
    "Latest LLMOps readiness status marker",
    ["status"],
    registry=registry,
)

dq_run_status_gauge = Gauge(
    f"{settings.prometheus_namespace}_run_status",
    "Status of DQ runs by dataset and category",
    ["dataset", "version", "category", "status"],
    registry=registry,
)

dq_metric_gauge = Gauge(
    f"{settings.prometheus_namespace}_metric_value",
    "Generic DQ metric value",
    ["dataset", "version", "category", "metric_name", "status"],
    registry=registry,
)

dirty_metric_gauges = {
    "schema_validity_ratio": Gauge(
        f"{settings.prometheus_namespace}_schema_validity_ratio",
        "Share of records with valid schema",
        ["dataset", "version", "status"],
        registry=registry,
    ),
    "completeness_ratio": Gauge(
        f"{settings.prometheus_namespace}_completeness_ratio",
        "Share of present required cells",
        ["dataset", "version", "status"],
        registry=registry,
    ),
    "missing_ratio": Gauge(
        f"{settings.prometheus_namespace}_missing_ratio",
        "Share of missing required cells",
        ["dataset", "version", "status"],
        registry=registry,
    ),
    "duplicate_free_ratio": Gauge(
        f"{settings.prometheus_namespace}_duplicate_free_ratio",
        "Share of non-duplicate rows",
        ["dataset", "version", "status"],
        registry=registry,
    ),
    "duplicate_ratio": Gauge(
        f"{settings.prometheus_namespace}_duplicate_ratio",
        "Share of duplicate rows",
        ["dataset", "version", "status"],
        registry=registry,
    ),
    "pattern_validity_ratio": Gauge(
        f"{settings.prometheus_namespace}_pattern_validity_ratio",
        "Share of rows passing pattern checks",
        ["dataset", "version", "status"],
        registry=registry,
    ),
}

staleness_metric_gauges = {
    "freshness_hours": Gauge(
        f"{settings.prometheus_namespace}_freshness_hours",
        "Freshness lag in hours",
        ["dataset", "version", "status"],
        registry=registry,
    ),
    "update_lag_hours_avg": Gauge(
        f"{settings.prometheus_namespace}_update_lag_hours_avg",
        "Average age of events in hours",
        ["dataset", "version", "status"],
        registry=registry,
    ),
    "coverage_ratio_28d": Gauge(
        f"{settings.prometheus_namespace}_coverage_ratio",
        "Coverage ratio across recent time buckets",
        ["dataset", "version", "status", "window"],
        registry=registry,
    ),
    "temporal_psi": Gauge(
        f"{settings.prometheus_namespace}_drift_psi",
        "Temporal PSI for dataset event time distribution",
        ["dataset", "version", "status", "feature"],
        registry=registry,
    ),
}

annotation_metric_gauges = {
    "cohens_kappa": Gauge(
        f"{settings.prometheus_namespace}_annot_kappa",
        "Cohen's kappa for annotation overlap",
        ["dataset", "version", "status", "task"],
        registry=registry,
    ),
    "krippendorffs_alpha": Gauge(
        f"{settings.prometheus_namespace}_annot_alpha",
        "Krippendorff's alpha for annotation task",
        ["dataset", "version", "status", "task"],
        registry=registry,
    ),
    "dawid_skene_error_rate": Gauge(
        f"{settings.prometheus_namespace}_annot_error_rate",
        "Dawid-Skene based average probability of annotation error",
        ["dataset", "version", "status", "task"],
        registry=registry,
    ),
}

bias_metric_gauges = {
    "bias_score": Gauge(
        f"{settings.prometheus_namespace}_bias_score",
        "Composite slice-based bias score",
        ["dataset", "version", "status"],
        registry=registry,
    ),
    "min_slice_representation": Gauge(
        f"{settings.prometheus_namespace}_slice_representation_min",
        "Minimum slice representation ratio",
        ["dataset", "version", "status"],
        registry=registry,
    ),
    "slice_label_distribution_gap": Gauge(
        f"{settings.prometheus_namespace}_slice_distribution_gap",
        "Maximum label distribution gap across slices",
        ["dataset", "version", "status"],
        registry=registry,
    ),
    "min_slice_quality": Gauge(
        f"{settings.prometheus_namespace}_slice_quality_min",
        "Minimum slice-level quality score",
        ["dataset", "version", "status"],
        registry=registry,
    ),
}


def metrics_payload() -> bytes:
    return generate_latest(registry)


def observe_run_status(dataset_id: object, version_id: object, category: str, status: str) -> None:
    dq_run_status_gauge.labels(
        dataset=str(dataset_id),
        version=str(version_id),
        category=category,
        status=status,
    ).set(1)


def observe_metric_value(
    dataset_id: object,
    version_id: object,
    category: str,
    metric_name: str,
    status: str,
    metric_value: float,
) -> None:
    dq_metric_gauge.labels(
        dataset=str(dataset_id),
        version=str(version_id),
        category=category,
        metric_name=metric_name,
        status=status,
    ).set(metric_value)

    specialized_gauge = dirty_metric_gauges.get(metric_name)
    if specialized_gauge is not None:
        specialized_gauge.labels(
            dataset=str(dataset_id),
            version=str(version_id),
            status=status,
        ).set(metric_value)

    staleness_gauge = staleness_metric_gauges.get(metric_name)
    if staleness_gauge is None:
        pass
    else:
        if metric_name == "coverage_ratio_28d":
            staleness_gauge.labels(
                dataset=str(dataset_id),
                version=str(version_id),
                status=status,
                window="28d",
            ).set(metric_value)
            return

        if metric_name == "temporal_psi":
            staleness_gauge.labels(
                dataset=str(dataset_id),
                version=str(version_id),
                status=status,
                feature="updated_at",
            ).set(metric_value)
            return

        staleness_gauge.labels(
            dataset=str(dataset_id),
            version=str(version_id),
            status=status,
        ).set(metric_value)
        return

    annotation_gauge = annotation_metric_gauges.get(metric_name)
    if annotation_gauge is not None:
        annotation_gauge.labels(
            dataset=str(dataset_id),
            version=str(version_id),
            status=status,
            task="annotation_qa",
        ).set(metric_value)
        return

    bias_gauge = bias_metric_gauges.get(metric_name)
    if bias_gauge is not None:
        bias_gauge.labels(
            dataset=str(dataset_id),
            version=str(version_id),
            status=status,
        ).set(metric_value)

    if status == "fail":
        dq_checks_failed_total.labels(category=category).inc()


def observe_ask_flow(
    status: str,
    retrieval_latency_ms: int,
    llm_latency_ms: int,
    scores: dict[str, float],
    input_tokens: int,
    output_tokens: int,
    no_context: bool,
) -> None:
    http_requests_total.labels(endpoint="/ask", status=status).inc()
    retrieval_latency_seconds.observe(retrieval_latency_ms / 1000)
    llm_latency_seconds.observe(llm_latency_ms / 1000)
    llm_input_tokens_total.inc(input_tokens)
    llm_output_tokens_total.inc(output_tokens)
    if no_context:
        retrieval_empty_results_total.inc()
    if status == "success":
        validation_pass_total.inc()
    else:
        validation_failed_total.inc()
        http_errors_total.labels(endpoint="/ask").inc()

    groundedness_score.set(scores.get("groundedness", 0.0))
    relevance_score.set(scores.get("relevance", 0.0))
    completeness_score.set(scores.get("completeness", 0.0))
    citation_correctness_score.set(scores.get("citation_correctness", 0.0))
    safety_score.set(scores.get("safety", 0.0))


def observe_feedback(rating: int | None) -> None:
    user_feedback_total.labels(rating=str(rating or "not_provided")).inc()


def observe_eval_run(model_name: str, prompt_version: str, status: str, metrics: dict[str, float]) -> None:
    eval_run_status.labels(model=model_name, prompt_version=prompt_version, status=status).set(1)
    for metric_name, metric_value in metrics.items():
        if isinstance(metric_value, int | float):
            eval_metric_value.labels(
                model=model_name,
                prompt_version=prompt_version,
                metric_name=metric_name,
            ).set(float(metric_value))


def observe_quality_gate(gate_status: str) -> None:
    quality_gate_status.labels(gate="latest").set(1 if gate_status == "passed" else 0)


def observe_runtime_dq(run_id: object | None, failed_check_count: int) -> None:
    runtime_dq_failed_checks.labels(run_id=str(run_id or "not_available")).set(failed_check_count)


def observe_readiness(status: str) -> None:
    llmops_readiness_status.labels(status=status).set(1)
