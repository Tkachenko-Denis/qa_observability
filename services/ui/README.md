# LLMOps DQ Streamlit UI

Demo-friendly observability console for the FastAPI LLMOps / DQ backend. It summarizes source systems; it does not replace Grafana, MLflow, Langfuse, Airflow, or FastAPI docs.

## Local Run

```bash
pip install -r services/ui/requirements.txt
set UI_BACKEND_URL=http://localhost:8000
set UI_PROMETHEUS_URL=http://localhost:9090
streamlit run services/ui/app.py --server.port=8501
```

Open `http://localhost:8501`.

## Docker Run

```bash
docker compose up --build -d ui
```

Inside Docker, `UI_BACKEND_URL` defaults to `http://api:8000` and `UI_PROMETHEUS_URL` defaults to `http://prometheus:9090`.

## Sections

- `Overview`: health, readiness, quality gate summary, integrations, and source-system links.
- `Ask / RAG Demo`: model selector, `/ask`, citations, scores, trace id, model metadata, and feedback.
- `Trace Explorer`: recent traces from `/traces` and detailed events from `/trace/{trace_id}`.
- `DQ Dashboard`: latest runtime DQ status from `/dq/results/latest` and DQ run history.
- `Evaluation Dashboard`: eval runs and score aggregates from `/eval/runs/*`.
- `Quality Gates`: latest gate, failed checks, metrics snapshot, history, and readiness signals.
- `Runtime Metrics`: Prometheus query cards for latency/error/quality signals.
- `Integrations`: Milvus, Langfuse, and MLflow status from backend integration endpoints.
- `Links / Operations`: where to inspect each system and non-destructive demo commands.

## Interpreting Failures

`Readiness: failed` means one or more release signals failed. The `Quality gate details` block shows the concrete `failed_checks` and `metrics_snapshot` returned by the backend.

`Quality gate: failed` means current metrics do not meet configured thresholds. The UI is a summary; Grafana remains the detailed time-series monitoring view.

`Request status: fallback` in `Ask / RAG Demo` is a controlled RAG outcome, not a system crash. It means retrieved documents were missing/weak or the model answer failed grounding validation, so the backend returned:

```text
I do not have enough context to answer this question based on the available documents.
Sources: none
```

`Request status: failed` means the request was processed but did not pass quality validation and was not converted to controlled fallback. Use the scores, validation reasons, and trace events to inspect the failure.

## Source-System Boundaries

- UI: demo-friendly summary and navigation.
- Grafana: detailed time-series monitoring and alert panels.
- Prometheus: metrics storage and query API.
- MLflow: experiment/eval run tracking and artifacts.
- Langfuse: specialized LLM trace observability when enabled.
- Airflow: orchestration runtime for DAG execution.

## Model Selector

The UI loads backend-approved model profiles from `GET /models` and sends the selected `model_profile_id` to `/ask`.

The selector does not edit `.env`, restart containers, or accept arbitrary provider URLs/API keys.

Default mock profile:

```env
LLM_PROVIDER=mock
DEFAULT_MODEL_PROFILE_ID=mock
LLM_ALLOW_MOCK_FALLBACK=false
```

Qwen via Ollama:

```env
DEFAULT_MODEL_PROFILE_ID=qwen_ollama_7b
MODEL_PROFILE_QWEN_OLLAMA_ENABLED=true
LOCAL_LLM_BASE_URL=http://host.docker.internal:11434
QWEN_OLLAMA_MODEL=qwen2.5:7b
QWEN_OLLAMA_7B_MODEL=qwen2.5:7b
```

Legacy `DEFAULT_MODEL_PROFILE_ID=qwen_ollama` is accepted by the backend as an alias, but UI examples use the concrete profile IDs `qwen_ollama_7b` or `qwen_ollama_3b`.

OpenAI-compatible provider:

```env
DEFAULT_MODEL_PROFILE_ID=openai_default
OPENAI_MODEL=gpt-4o-mini
OPENAI_API_KEY=<configured outside UI>
```
