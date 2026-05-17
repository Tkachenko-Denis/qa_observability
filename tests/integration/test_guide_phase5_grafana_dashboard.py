import json
from pathlib import Path


def test_grafana_dashboard_covers_guide_metric_groups() -> None:
    dashboard_path = Path("dashboards/grafana/dashboards/mvp-overview.json")
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))

    panel_titles = {panel["title"] for panel in dashboard["panels"]}
    required_titles = {
        "API Requests And Errors",
        "Latency P95",
        "LLM Tokens And Errors",
        "Retrieval Quality",
        "LLM Eval Scores",
        "DQ Runs And Failed Checks",
        "Data Quality And Drift",
        "Annotation QA And Bias",
        "Quality Gate Status",
        "LLMOps Readiness",
    }

    assert required_titles.issubset(panel_titles)


def test_grafana_dashboard_references_phase4_metrics() -> None:
    dashboard_text = Path("dashboards/grafana/dashboards/mvp-overview.json").read_text(encoding="utf-8")

    required_metrics = [
        "quality_gate_status",
        "llmops_readiness_status",
        "runtime_dq_failed_checks",
        "eval_metric_value",
        "http_requests_total",
        "llm_latency_seconds",
        "retrieval_latency_seconds",
        "dq_checks_failed_total",
    ]

    for metric_name in required_metrics:
        assert metric_name in dashboard_text
