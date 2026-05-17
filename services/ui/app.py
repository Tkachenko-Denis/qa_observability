from __future__ import annotations

import json
from html import escape
from typing import Any

import streamlit as st

from api_client import APIError, DQAPIClient
from config import get_settings
from formatting import render_links_markdown_table


st.set_page_config(page_title="LLMOps DQ Observability", page_icon="DQ", layout="wide")


def client_from_sidebar() -> tuple[DQAPIClient, bool, Any]:
    settings = get_settings()
    with st.sidebar:
        st.header("Connection")
        backend_url = st.text_input("Backend URL", value=settings.backend_url)
        prometheus_url = st.text_input("Prometheus URL", value=settings.prometheus_url)
        api_key = st.text_input("API key", value="", type="password")
        show_raw = st.toggle("Show raw JSON responses", value=False)
        client = DQAPIClient(
            backend_url,
            api_key=api_key or None,
            timeout_seconds=settings.request_timeout_seconds,
            prometheus_url=prometheus_url,
        )
        if st.button("Check backend", use_container_width=True):
            render_backend_status(client, show_raw=show_raw, settings=settings)

    return client, show_raw, settings


def render_api_error(error: APIError) -> None:
    st.error(str(error))
    with st.expander("Raw error response"):
        st.code(error.raw_response or "not available", language="json")


def load_model_profiles(client: DQAPIClient, *, show_raw: bool) -> tuple[str | None, list[dict[str, Any]]]:
    try:
        payload = client.models()
    except APIError as exc:
        st.warning("Model profiles are unavailable; backend default model will be used.")
        render_api_error(exc)
        return None, []

    default_id = payload.get("default_model_profile_id")
    if show_raw:
        with st.expander("Raw /models response"):
            st.json(payload)
    return default_id, payload.get("models", [])


def model_option_label(model: dict[str, Any]) -> str:
    return f"{model.get('label', model.get('id'))} - {model.get('model_name')} ({model.get('provider')})"


def model_status_text(model: dict[str, Any]) -> str:
    if model.get("enabled"):
        return str(model.get("reason") or "available")
    return f"unavailable: {model.get('reason', 'not selectable')}"


def render_model_details(models: list[dict[str, Any]]) -> None:
    if not models:
        st.info("No model profiles returned by backend.")
        return
    with st.expander("Model details", expanded=False):
        rows = []
        for model in models:
            enabled = bool(model.get("enabled"))
            title = model_option_label(model)
            status = model_status_text(model)
            description = str(model.get("description") or "")
            color = "#18864b" if enabled else "#b25d00"
            background = "#eefaf3" if enabled else "#fff5e6"
            tooltip = " ".join(part for part in [status, description] if part).strip()
            rows.append(
                f"""
                <div title="{escape(tooltip, quote=True)}"
                     style="border-left:5px solid {color}; background:{background};
                            border-radius:8px; padding:0.65rem 0.8rem; margin:0.45rem 0;">
                  <div style="font-weight:700; color:{color};">{escape(str(title), quote=False)}</div>
                  <div style="font-size:0.9rem; color:#3f3f3f;">{escape(status, quote=False)}</div>
                  <div style="font-size:0.85rem; color:#595959;">{escape(description, quote=False)}</div>
                </div>
                """
            )
        st.markdown("\n".join(rows), unsafe_allow_html=True)


def render_quality_gate_details(readiness: dict[str, Any], *, show_raw: bool) -> None:
    gate = readiness.get("latest_quality_gate")
    if not isinstance(gate, dict):
        st.info("Quality gate details: not available")
        return

    gate_status = str(gate.get("gate_status", "unknown"))
    failed_checks = gate.get("failed_checks") or []
    metrics_snapshot = gate.get("metrics_snapshot") or {}

    with st.expander("Quality gate details", expanded=gate_status == "failed"):
        if gate_status == "passed":
            st.success("Quality gate: passed")
        elif gate_status == "failed":
            st.error("Quality gate: failed")
        else:
            st.info(f"Quality gate: {gate_status}")

        st.caption(f"Created at: {gate.get('created_at', 'not specified')}")

        if failed_checks:
            st.markdown("**Failed checks**")
            st.dataframe(
                [{"check": str(check)} for check in failed_checks],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No failed checks reported.")

        if isinstance(metrics_snapshot, dict) and metrics_snapshot:
            st.markdown("**Metrics snapshot**")
            rows = []
            for key, value in metrics_snapshot.items():
                if isinstance(value, dict):
                    rows.append({"metric": key, "value": json.dumps(value, ensure_ascii=False)})
                else:
                    rows.append({"metric": key, "value": value})
            st.dataframe(rows, use_container_width=True, hide_index=True)

        if show_raw:
            with st.expander("Raw quality gate payload"):
                st.json(gate)


def safe_call(label: str, func):
    try:
        return func()
    except APIError as exc:
        st.warning(f"{label} unavailable")
        render_api_error(exc)
        return None


def render_backend_status(client: DQAPIClient, *, show_raw: bool, settings: Any | None = None) -> None:
    cols = st.columns(3)
    try:
        health = client.health()
        cols[0].success(f"Backend: {health.get('status', 'unknown')}")
        cols[0].caption(f"{health.get('app_name', 'api')} / {health.get('app_env', 'env unknown')}")
        if show_raw:
            cols[0].json(health)
    except APIError as exc:
        cols[0].error("Backend unavailable")
        render_api_error(exc)

    try:
        readiness = client.readiness()
        status = str(readiness.get("status", "unknown"))
        if status == "passed":
            cols[1].success(f"Readiness: {status}")
        elif status == "failed":
            cols[1].warning(f"Readiness: {status}")
        else:
            cols[1].info(f"Readiness: {status}")
        failed = readiness.get("failed_signals") or []
        if failed:
            cols[1].caption("Failed signals: " + ", ".join(map(str, failed)))
        if show_raw:
            cols[1].json(readiness)
        render_quality_gate_details(readiness, show_raw=show_raw)
    except APIError as exc:
        cols[1].warning("Readiness unavailable")
        render_api_error(exc)

    try:
        integrations = client.integrations()
        runtime_count = sum(1 for item in integrations if item.get("mode") == "runtime")
        cols[2].info(f"Integrations: {len(integrations)} total, {runtime_count} runtime")
        cols[2].dataframe(
            [
                {
                    "name": item.get("name"),
                    "enabled": item.get("enabled"),
                    "mode": item.get("mode"),
                    "fallback": item.get("fallback"),
                }
                for item in integrations
            ],
            use_container_width=True,
            hide_index=True,
        )
        if show_raw:
            cols[2].json(integrations)
    except APIError as exc:
        cols[2].warning("Integrations unavailable")
        render_api_error(exc)


def render_answer(response: dict[str, Any], *, show_raw: bool) -> None:
    status = str(response.get("status", "unknown"))
    if status == "success":
        st.success("Request status: success")
    elif status == "fallback":
        st.warning("Request status: fallback")
        st.info(
            "The model did not have enough grounded context to answer from the available documents. "
            "A controlled fallback answer was returned."
        )
    elif status == "failed":
        st.error("Request status: failed")
        st.info(
            "The request was processed, but the answer did not pass quality validation. "
            "Check scores and trace for details."
        )
    else:
        st.warning(f"Request status: {status}")

    st.subheader("Answer")
    st.markdown(response.get("answer") or "_No answer returned._")

    metadata = {
        "request_id": response.get("request_id"),
        "trace_id": response.get("trace_id"),
        "model_profile_id": response.get("model_profile_id"),
        "provider": response.get("provider"),
        "model_name": response.get("model_name"),
        "model_version": response.get("model_version"),
        "finish_reason": response.get("finish_reason"),
        "scorer_version": response.get("scorer_version"),
    }
    st.subheader("Metadata")
    st.dataframe([metadata], use_container_width=True, hide_index=True)
    if response.get("trace_id"):
        st.code(str(response["trace_id"]), language="text")
    validation_reasons = response.get("validation_reasons") or []
    if validation_reasons:
        with st.expander("Validation reasons", expanded=status in {"fallback", "failed"}):
            st.dataframe(
                [{"reason": str(reason)} for reason in validation_reasons],
                use_container_width=True,
                hide_index=True,
            )

    render_citations(response.get("citations") or [])
    render_scores(response.get("scores") or {})

    if show_raw:
        with st.expander("Raw /ask response"):
            st.json(response)


def render_citations(citations: list[dict[str, Any]]) -> None:
    st.subheader("Citations")
    if not citations:
        st.warning("No citations returned")
        return
    rows = []
    for citation in citations:
        metadata = citation.get("metadata") if isinstance(citation.get("metadata"), dict) else {}
        rows.append(
            {
                "document_id": citation.get("document_id"),
                "chunk_id": citation.get("chunk_id"),
                "source": citation.get("source") or metadata.get("source") or metadata.get("title"),
                "score": citation.get("score"),
                "text_preview": str(citation.get("text") or "")[:240],
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_scores(scores: dict[str, Any]) -> None:
    st.subheader("Quality scores")
    if not scores:
        st.info("No scores returned")
        return
    rows = [{"metric": key, "value": value} for key, value in scores.items()]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    numeric_scores = {key: value for key, value in scores.items() if isinstance(value, int | float)}
    if numeric_scores:
        st.bar_chart(numeric_scores)


def render_trace(client: DQAPIClient, trace_id: str | None, *, show_raw: bool) -> None:
    st.subheader("Trace viewer")
    trace_id_input = st.text_input("Trace ID", value=trace_id or "")
    if st.button("Load trace", disabled=not bool(trace_id_input.strip())):
        try:
            trace = client.trace(trace_id_input)
        except APIError as exc:
            render_api_error(exc)
            return
        rows = [
            {
                "created_at": event.get("created_at"),
                "span_name": event.get("span_name"),
                "status": event.get("status"),
                "latency_ms": event.get("latency_ms"),
                "payload": json.dumps(event.get("payload", {}), ensure_ascii=False)[:500],
            }
            for event in trace
            if isinstance(event, dict)
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
        with st.expander("Raw JSON trace", expanded=show_raw):
            st.json(trace)


def render_feedback(client: DQAPIClient, response: dict[str, Any]) -> None:
    st.subheader("Feedback")
    with st.form("feedback_form"):
        rating = st.slider("Rating", min_value=1, max_value=5, value=5)
        helpful_label = st.selectbox("Helpful", ["yes", "no", "not specified"])
        comment = st.text_area("Comment", value="", height=100)
        submitted = st.form_submit_button("Submit feedback")
    if not submitted:
        return

    helpful = None if helpful_label == "not specified" else helpful_label == "yes"
    try:
        created = client.feedback(
            request_id=response.get("request_id"),
            trace_id=response.get("trace_id"),
            rating=rating,
            helpful=helpful,
            comment=comment,
        )
    except APIError as exc:
        render_api_error(exc)
        return
    st.success(f"Feedback submitted: {created.get('id', 'created')}")


def render_overview(client: DQAPIClient, *, show_raw: bool, settings: Any) -> None:
    st.header("Overview")
    st.caption("High-level status of the LLMOps / DQ & Observability layer.")
    if st.button("Refresh overview"):
        st.rerun()
    render_backend_status(client, show_raw=show_raw, settings=settings)


def render_ask_demo(client: DQAPIClient, *, show_raw: bool) -> None:
    st.header("Ask / RAG Demo")
    st.caption("User-facing RAG flow with answer, citations, quality scores, trace ID, model metadata and feedback.")
    default_model_profile_id, models = load_model_profiles(client, show_raw=show_raw)
    render_model_details(models)
    selected_model_profile_id = None
    selected_model_is_enabled = True
    if models:
        default_index = next(
            (index for index, model in enumerate(models) if model.get("id") == default_model_profile_id),
            0,
        )
        selected_model = st.selectbox(
            "Model",
            models,
            index=default_index,
            format_func=model_option_label,
            help="Only backend-approved models are listed. Unavailable models are visible in Model details but cannot be used.",
        )
        if isinstance(selected_model, dict):
            selected_model_is_enabled = bool(selected_model.get("enabled"))
            if selected_model_is_enabled:
                selected_model_profile_id = selected_model.get("id")
            else:
                st.warning(model_status_text(selected_model))
    else:
        st.info("No model profiles returned; /ask will use backend default behavior.")

    with st.form("ask_form"):
        query = st.text_area("Question / query", value="What is the return policy?", height=120)
        session_id = st.text_input("Session ID (optional)", value="")
        user_id = st.text_input("User ID (optional)", value="streamlit-demo")
        locale = st.text_input("Locale", value="en")
        submitted = st.form_submit_button("Ask", disabled=not selected_model_is_enabled)

    if submitted:
        if not query.strip():
            st.error("Question is required")
        else:
            with st.spinner("Calling /ask..."):
                try:
                    response = client.ask(
                        query,
                        session_id=session_id or None,
                        user_id=user_id or None,
                        locale=locale or "en",
                        model_profile_id=selected_model_profile_id,
                    )
                except APIError as exc:
                    render_api_error(exc)
                else:
                    st.session_state["last_ask_response"] = response
                    if response.get("trace_id"):
                        st.session_state["latest_trace_id"] = str(response["trace_id"])

    response = st.session_state.get("last_ask_response")
    if isinstance(response, dict):
        st.divider()
        render_answer(response, show_raw=show_raw)
        st.divider()
        render_feedback(client, response)


def render_trace_explorer(client: DQAPIClient, *, show_raw: bool) -> None:
    st.header("Request Trace Explorer")
    st.caption("A trace is a timeline of one request: retrieval, prompt assembly, LLM call, validation and response delivery.")
    traces = safe_call("Trace list", lambda: client.traces(limit=50))
    trace_options = []
    if isinstance(traces, dict):
        trace_options = traces.get("traces") or []
        if trace_options:
            st.dataframe(trace_options, use_container_width=True, hide_index=True)
    selected_trace = None
    if trace_options:
        selected = st.selectbox(
            "Recent traces",
            trace_options,
            format_func=lambda item: f"{item.get('created_at')} | {item.get('status')} | {item.get('query_preview')}",
        )
        selected_trace = selected.get("trace_id") if isinstance(selected, dict) else None
    default_trace_id = selected_trace or st.session_state.get("latest_trace_id") or ""
    render_trace(client, str(default_trace_id) if default_trace_id else None, show_raw=show_raw)


def render_dq_dashboard(client: DQAPIClient, *, show_raw: bool) -> None:
    st.header("DQ Dashboard")
    st.caption("DQ checks verify whether source data, chunks, metadata and evaluation datasets are valid enough for the LLM application.")
    st.subheader("Runtime DQ Checks")
    st.caption(
        "Runtime DQ checks come from `/dq/results/latest`. They validate operational RAG data such as "
        "loaded documents, chunks, embeddings, eval items, trace events and response logs."
    )
    latest = safe_call("Latest runtime DQ checks", client.dq_latest)
    if isinstance(latest, dict):
        cols = st.columns(4)
        cols[0].metric("Latest status", latest.get("status", "unknown"))
        cols[1].metric("Checks", latest.get("check_count", 0))
        cols[2].metric("Passed", latest.get("passed_count", 0))
        cols[3].metric("Failed", latest.get("failed_count", 0))
        results = latest.get("results") or []
        failed = [row for row in results if row.get("status") == "failed"]
        st.markdown("**Failed runtime checks**")
        st.dataframe(failed, use_container_width=True, hide_index=True)
        if show_raw:
            with st.expander("Raw latest runtime DQ payload"):
                st.json(latest)

    st.divider()
    st.subheader("Dataset DQ Runs")
    st.caption(
        "Dataset DQ runs come from `/dq/runs`. They represent configured dataset/version checks across "
        "dirty data, staleness/drift, annotation QA and bias categories."
    )
    runs = safe_call("Dataset DQ runs", lambda: client.dq_runs(limit=20))
    if isinstance(runs, list):
        st.markdown("**Dataset DQ run history**")
        st.dataframe(runs, use_container_width=True, hide_index=True)


def aggregate_scores(scores: list[dict[str, Any]]) -> dict[str, float]:
    buckets: dict[str, list[float]] = {}
    for row in scores:
        name = str(row.get("metric_name") or "unknown")
        value = row.get("metric_value")
        if isinstance(value, int | float):
            buckets.setdefault(name, []).append(float(value))
    return {key: round(sum(values) / len(values), 4) for key, values in buckets.items() if values}


def render_evaluation_dashboard(client: DQAPIClient, *, show_raw: bool) -> None:
    st.header("Evaluation Dashboard")
    st.caption("Evaluation checks whether the LLM application gives useful and grounded answers on a fixed test set.")
    runs = safe_call("Eval runs", lambda: client.eval_runs(limit=20))
    if not isinstance(runs, list) or not runs:
        st.info("No eval runs available.")
        return
    st.dataframe(runs, use_container_width=True, hide_index=True)
    selected = st.selectbox("Eval run", runs, format_func=lambda row: f"{row.get('created_at')} | {row.get('run_name')} | {row.get('status')}")
    run_id = str(selected.get("id"))
    scores = safe_call("Eval scores", lambda: client.eval_scores(run_id, limit=1000))
    if isinstance(scores, list):
        aggregates = aggregate_scores(scores)
        cols = st.columns(min(len(aggregates), 5) or 1)
        for index, (metric, value) in enumerate(aggregates.items()):
            cols[index % len(cols)].metric(metric, value)
        st.subheader("Scores")
        st.dataframe(scores, use_container_width=True, hide_index=True)
        if aggregates:
            st.bar_chart(aggregates)
    if show_raw:
        with st.expander("Raw selected eval run"):
            st.json(selected)


def render_quality_gates(client: DQAPIClient, *, show_raw: bool) -> None:
    st.header("Quality Gates")
    st.caption("Quality gates are release checks. If key quality metrics fall below thresholds, the system should not be promoted.")
    latest = safe_call("Latest quality gate", client.quality_gate_latest)
    if isinstance(latest, dict):
        status = str(latest.get("gate_status", "unknown"))
        if status == "passed":
            st.success("Latest gate: passed")
        elif status == "failed":
            st.error("Latest gate: failed")
        else:
            st.info(f"Latest gate: {status}")
        render_quality_gate_details({"latest_quality_gate": latest}, show_raw=show_raw)
    readiness = safe_call("Readiness", client.readiness)
    if isinstance(readiness, dict):
        st.subheader("Readiness")
        st.write({"status": readiness.get("status"), "failed_signals": readiness.get("failed_signals", [])})
    history = safe_call("Quality gate history", lambda: client.quality_gates(limit=50))
    if isinstance(history, list):
        st.subheader("Gate history")
        st.dataframe(history, use_container_width=True, hide_index=True)


def prometheus_scalar(payload: dict[str, Any]) -> str:
    try:
        result = payload["data"]["result"]
        if not result:
            return "n/a"
        return str(result[0]["value"][1])
    except (KeyError, IndexError, TypeError):
        return "n/a"


def render_runtime_metrics(client: DQAPIClient, *, show_raw: bool) -> None:
    st.header("Runtime Metrics")
    st.caption("Prometheus stores numeric time-series metrics such as latency, errors, tokens and quality scores.")
    queries = {
        "API req/s": "sum(rate(http_requests_total[5m]))",
        "API errors/s": "sum(rate(http_errors_total[5m]))",
        "LLM errors/s": "sum(rate(llm_errors_total[5m]))",
        "Groundedness": "avg(groundedness_score)",
        "Quality gate": "max(quality_gate_status)",
    }
    cols = st.columns(len(queries))
    raw: dict[str, Any] = {}
    for index, (label, query) in enumerate(queries.items()):
        payload = safe_call(label, lambda query=query: client.prometheus_query(query))
        if isinstance(payload, dict):
            cols[index].metric(label, prometheus_scalar(payload))
            raw[label] = payload
        else:
            cols[index].metric(label, "n/a")
    if show_raw and raw:
        with st.expander("Raw Prometheus responses"):
            st.json(raw)


def render_integrations_section(client: DQAPIClient, *, show_raw: bool, settings: Any) -> None:
    st.header("Integrations")
    st.caption("contract_only means local fallback data; runtime means SDK/service integration is active; disabled means env config turned it off.")
    integrations = safe_call("Integrations", client.integrations)
    if isinstance(integrations, list):
        st.dataframe(integrations, use_container_width=True, hide_index=True)
    if show_raw and isinstance(integrations, list):
        with st.expander("Raw integrations"):
            st.json(integrations)


def render_operations(settings: Any, client: DQAPIClient) -> None:
    st.header("Links / Operations")
    st.caption("Demo map of source systems. UI summarizes; Grafana, MLflow, Langfuse and Airflow remain source systems.")
    links = [
        {"system": "FastAPI docs", "url": f"{client.base_url}/docs", "purpose": "API contracts and manual calls"},
        {"system": "Streamlit UI", "url": "http://localhost:8501", "purpose": "Demo-friendly summary console"},
        {"system": "Grafana", "url": settings.grafana_url, "purpose": "Detailed time-series monitoring"},
        {"system": "Prometheus", "url": settings.prometheus_url, "purpose": "Metrics storage and query API"},
        {"system": "MLflow", "url": settings.mlflow_url, "purpose": "Experiment and eval tracking"},
        {"system": "Langfuse", "url": settings.langfuse_url, "purpose": "Specialized LLM tracing platform"},
        {"system": "Airflow", "url": settings.airflow_url, "purpose": "Pipeline orchestration"},
    ]
    st.markdown(render_links_markdown_table(links))
    st.code(
        "\n".join(
            [
                "docker compose ps",
                "curl http://localhost:8000/health",
                "python scripts/e2e_validation_smoke.py --base-url http://localhost:8000 --require-success-ask",
                "docker compose exec -T api python scripts/run_gx_dq_checks.py",
                "docker compose exec -T api python scripts/run_eval.py",
                "docker compose exec -T api python scripts/quality_gate.py",
            ]
        ),
        language="powershell",
    )


def main() -> None:
    client, show_raw, settings = client_from_sidebar()

    st.title("LLMOps DQ & Observability")
    st.caption("Demo-friendly observability console. Source systems remain Grafana, MLflow, Langfuse, Airflow and FastAPI.")

    tabs = st.tabs(
        [
            "Overview",
            "Ask / RAG Demo",
            "Trace Explorer",
            "DQ Dashboard",
            "Evaluation Dashboard",
            "Quality Gates",
            "Runtime Metrics",
            "Integrations",
            "Links / Operations",
        ]
    )
    with tabs[0]:
        render_overview(client, show_raw=show_raw, settings=settings)
    with tabs[1]:
        render_ask_demo(client, show_raw=show_raw)
    with tabs[2]:
        render_trace_explorer(client, show_raw=show_raw)
    with tabs[3]:
        render_dq_dashboard(client, show_raw=show_raw)
    with tabs[4]:
        render_evaluation_dashboard(client, show_raw=show_raw)
    with tabs[5]:
        render_quality_gates(client, show_raw=show_raw)
    with tabs[6]:
        render_runtime_metrics(client, show_raw=show_raw)
    with tabs[7]:
        render_integrations_section(client, show_raw=show_raw, settings=settings)
    with tabs[8]:
        render_operations(settings, client)


if __name__ == "__main__":
    main()
