from pathlib import Path

import sys

sys.path.insert(0, str(Path("services/ui").resolve()))

from formatting import render_links_markdown_table


def test_dq_dashboard_labels_separate_runtime_checks_from_dataset_runs() -> None:
    app = Path("services/ui/app.py").read_text(encoding="utf-8")

    assert 'st.subheader("Runtime DQ Checks")' in app
    assert "`/dq/results/latest`" in app
    assert "Failed runtime checks" in app
    assert 'st.subheader("Dataset DQ Runs")' in app
    assert "`/dq/runs`" in app
    assert "Dataset DQ run history" in app


def test_source_system_links_are_only_rendered_in_operations_tab() -> None:
    app = Path("services/ui/app.py").read_text(encoding="utf-8")
    before_operations, operations = app.split("def render_operations", maxsplit=1)

    assert "Links: " not in before_operations
    assert "[FastAPI docs]" not in before_operations
    assert "[Grafana]" not in before_operations
    assert "[MLflow]" not in before_operations
    assert "[Langfuse]" not in before_operations
    assert "[Airflow]" not in before_operations
    assert "FastAPI docs" in operations
    assert "Grafana" in operations
    assert "MLflow" in operations
    assert "Langfuse" in operations
    assert "Airflow" in operations


def test_operations_links_render_as_clickable_markdown_table() -> None:
    markdown = render_links_markdown_table(
        [
            {
                "system": "FastAPI docs",
                "url": "http://localhost:8000/docs",
                "purpose": "API contracts",
            }
        ]
    )

    assert "| Service | Purpose |" in markdown
    assert "[FastAPI docs](http://localhost:8000/docs)" in markdown


def test_ask_ui_explains_fallback_and_failed_statuses() -> None:
    app = Path("services/ui/app.py").read_text(encoding="utf-8")

    assert 'status == "fallback"' in app
    assert "controlled fallback answer was returned" in app
    assert 'status == "failed"' in app
    assert "did not pass quality validation" in app
    assert "Validation reasons" in app
