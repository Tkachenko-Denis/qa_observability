# Final Architecture Summary

## Project Goal

MVP DQ Observability layer for LLMOps data with:
- data versioning
- DQ runs
- DQ metrics
- alerting
- observability
- policy / gate behavior
- orchestration and external run linkage

## Default Demo Contour

- Primary default contour: `RAG / knowledge base documents`
- Additional optional synthetic contours:
  - annotation QA
  - bias analysis

## End-To-End Lifecycle

`ingestion -> cleaning -> annotation -> versioning -> monitoring -> archiving`

## Runtime Components

- FastAPI:
  - RAG `/ask`, metadata, dataset versions, DQ runs, metrics, events, summaries, gate decisions, audit events, input/output PII masking, MLflow-style linkage
  - Docker startup is guarded by `api-migrate`, which runs Alembic before `api`
- Streamlit UI:
  - user-facing demo for `/ask`, backend-approved model profile selection, citations, quality scores, trace viewer, feedback, health, readiness, and integration status
- PostgreSQL:
  - metadata, traces, eval, DQ, quality gates, audit, and observability persistence
- Prometheus:
  - time-series scraping from `/metrics`
- Grafana:
  - category-aware LLMOps/DQ dashboard
- Airflow runtime:
  - ingestion, indexing, runtime DQ, eval, and quality gate DAGs
- MLflow linkage layer:
  - persisted external run associations in PostgreSQL and optional SDK-backed eval logging
  - MLflow tracking metadata persists in Docker volume `mlflow_data` at `/mlflow/mlflow.db`
  - MLflow artifacts persist in Docker volume `mlflow_data` at `/mlflow/artifacts`
- Milvus:
  - optional Docker Compose profile, MVP-compatible search/upsert contract, collection bootstrap for deterministic 16-dim MVP embeddings, and optional SDK upsert/search path
- LangChain:
  - PromptTemplate, retriever wrapper, and RunnableSequence compatibility layer exist; the custom `/ask` orchestrator remains the default runtime path
- Langfuse:
  - optional Docker Compose profile, MVP-compatible trace/span contract, and optional SDK span export
- Great Expectations:
  - runtime DQ is GX-style/custom and writes JSON data docs; full Great Expectations checkpoint runner is not implemented yet

## DQ Categories Implemented

1. Dirty data
2. Staleness / temporal drift
3. Annotation QA
4. Bias

## Storage Model

Core tables:
- `datasets`
- `dataset_versions`
- `dq_runs`
- `dq_metrics`
- `dq_alert_rules`
- `dq_events`
- `llmops_run_links`
- `documents`
- `chunks`
- `requests`
- `responses`
- `response_citations`
- `trace_events`
- `eval_runs`
- `eval_scores`
- `quality_gate_results`
- `audit_events`

## API Model

Core endpoints:
- dataset and dataset version CRUD subset
- `POST /dq/run`
- `GET /dq/runs`
- `GET /dq/events`
- `GET /dq/metrics`
- `GET /dq/summary`
- `POST /ask`
- `POST /feedback`
- `GET /trace/{trace_id}`
- `GET /eval/runs`
- `GET /dq/results`
- `GET /quality-gates/latest`
- `GET /llmops/readiness`
- `GET /integrations`
- `GET /integrations/contracts`
- `GET /audit/events`
- `GET /datasets/{dataset_id}/versions/{version_id}/gate`
- `POST /llmops/mlflow/link`
- `GET /llmops/mlflow/links`
- `GET /metrics`

## Policy Model

- hard gate:
  - block publication or downstream progression
- soft gate:
  - allow with warnings

Policy decisions are currently driven by the latest per-category run results for a dataset version.

## Validation Posture

Validation assets include:
- unit tests for metric calculations
- integration endpoint smoke tests
- synthetic degradation matrix
- reproducible E2E validation smoke script
- live Airflow DAG smoke runbook
- Airflow REST API smoke script
- Grafana/Prometheus provisioning checks
- optional integration profile checks
- security/audit contract checks

## Current Gaps

- production real embedding model operation is not implemented; current Milvus bootstrap is for deterministic MVP embeddings only
- full Great Expectations checkpoint runner is not implemented; current runtime DQ is GX-style/custom
- LangChain wrapper exists, but the custom orchestrator remains the default `/ask` runtime
- production Langfuse project/session/user setup and retention policy is not implemented
- production MLflow experiment naming/model registry linkage is not implemented
- production RBAC, tenant isolation, secret manager integration, TLS, and retention policies are not implemented
- browser-level Grafana validation is not automated
