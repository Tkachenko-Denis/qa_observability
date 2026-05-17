from types import SimpleNamespace

from scripts.quality_gate import aggregate_response_metrics


def test_aggregate_response_metrics_uses_last_response_window_values() -> None:
    responses = [
        SimpleNamespace(
            status="success",
            validation_status="passed",
            scores={"groundedness": 1.0, "relevance": 0.8, "citation_correctness": 1.0, "safety": 1.0},
        ),
        SimpleNamespace(
            status="failed",
            validation_status="failed",
            scores={"groundedness": 0.5, "relevance": 0.4, "citation_correctness": 0.0, "safety": 1.0},
        ),
    ]

    aggregate = aggregate_response_metrics(responses)

    assert aggregate["response_count"] == 2
    assert aggregate["avg_groundedness"] == 0.75
    assert aggregate["avg_relevance"] == 0.6
    assert aggregate["avg_citation_correctness"] == 0.5
    assert aggregate["avg_safety"] == 1.0
    assert aggregate["validation_pass_rate"] == 0.5
    assert aggregate["failed_response_rate"] == 0.5


def test_quality_gate_contract_uses_aggregate_metrics_and_latest_response_diagnostics() -> None:
    from pathlib import Path

    config = Path("services/api/app/config.py").read_text(encoding="utf-8")
    env_example = Path(".env.example").read_text(encoding="utf-8")
    script = Path("scripts/quality_gate.py").read_text(encoding="utf-8")
    thresholds = Path("config/quality_thresholds.yaml").read_text(encoding="utf-8")

    assert "quality_gate_response_window" in config
    assert "QUALITY_GATE_RESPONSE_WINDOW=50" in env_example
    for metric_name in (
        "avg_groundedness",
        "avg_relevance",
        "avg_citation_correctness",
        "avg_safety",
        "validation_pass_rate",
        "failed_response_rate",
    ):
        assert metric_name in script
    assert '"latest_response"' in script
    assert "validation_pass_rate_min" in thresholds
    assert "failed_response_rate_max" in thresholds
