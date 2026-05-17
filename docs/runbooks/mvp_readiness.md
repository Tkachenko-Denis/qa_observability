# MVP Readiness

## Objective

This document summarizes whether the MVP is ready for demonstration, code review, and technical defense.

## Delivered Capabilities

- Dataset registration and versioning
- DQ run execution across 4 categories
- Persistent DQ metrics and events
- Prometheus export and Grafana provisioning
- Hard and soft quality gates
- Gate summary endpoint for downstream policy decisions
- MLflow-style run linkage persistence
- Optional MLflow SDK-backed eval tracking
- Persistent MLflow tracking backend and artifacts in Docker volume `mlflow_data`
- Docker `api-migrate` service blocks API startup until Alembic migrations pass
- Airflow orchestration runtime for ingestion, indexing, DQ, eval, and quality gate
- RAG `/ask` vertical slice with retrieval, LLM provider abstraction, citations, trace events, and quality scores
- Streamlit demo UI for asking questions, selecting backend-approved model profiles, viewing citations/scores/traces, and submitting feedback
- Real LLM provider adapters for OpenAI-compatible APIs, Ollama, and Qwen over Ollama with mock fallback
- Eval runs, runtime DQ results, readiness API, and Prometheus gauges for gate/readiness state
- Airflow REST API smoke for DAG visibility and import errors
- MVP-compatible Milvus and Langfuse contracts with optional Docker Compose profiles
- Optional Milvus SDK-backed vector upsert/search path with file-backed fallback
- Milvus collection bootstrap for deterministic 16-dim MVP embeddings
- LangChain PromptTemplate/retriever/RunnableSequence wrapper; custom `/ask` orchestrator remains default runtime
- GX-style/custom runtime DQ checks; full Great Expectations checkpoint runner is not implemented
- Optional Langfuse SDK-backed span export with PostgreSQL fallback
- Configurable API key middleware, input/output PII masking, and audit event drill-down

## Evidence Of Utility

- Synthetic degradation scenarios are defined in `datasets/synthetic/validation_matrix.yaml`
- Dirty-data and staleness/drift E2E flows were verified through runtime checks
- Live Airflow DAG smoke completed for ingestion, indexing, runtime DQ, and eval
- Quality gate DAG failed by design on below-threshold deterministic mock eval quality
- Airflow REST API smoke validates scheduler/metadatabase health, visible DAGs, and import errors
- E2E validation smoke passed against `http://localhost:8000` with `--require-success-ask`; quality gate/readiness reported failed by design on strict mock thresholds
- Automated tests cover the active MVP contracts
- Unit tests cover:
  - dirty-data metric degradation
  - staleness/drift degradation
  - annotation QA degradation
  - bias degradation
  - RAG retrieval/provider scoring behavior
- Integration tests cover:
  - health endpoint
  - observability endpoints
  - LLMOps linkage endpoints
  - presence of validation artifacts
  - Grafana dashboard artifacts
  - Milvus/Langfuse contracts and optional profiles
  - Airflow runtime/API smoke artifacts
  - security and audit contracts

## MVP Ready For

- demo and technical walkthrough
- architecture review
- code review
- extension into richer orchestration
- extension into production calibration work
- local end-to-end LLMOps DQ observability demonstration

## MVP Not Yet Ready For

- production-scale throughput claims
- domain-specific threshold guarantees
- high-stakes fairness or compliance assertions
- full operational SRE posture
- production real embedding model operation for Milvus
- full Great Expectations checkpoint runner
- production secret management / RBAC / tenant isolation

## Recommended Final Demo Sequence

1. Start stack
2. Run migrations
3. Run `python scripts/e2e_validation_smoke.py --base-url http://localhost:8000 --require-success-ask`
4. Run `/ask` and inspect `/trace/{trace_id}`
5. Execute runtime DQ and eval flows
6. Show `/dq/summary`, `/dq/results`, `/eval/runs`, and `/quality-gates/latest`
7. Show `/llmops/readiness`
8. Show `/metrics`, Prometheus alerts, and Grafana dashboard
9. Run Airflow DAG smoke and Airflow API smoke
10. Show optional `milvus` and `langfuse` Compose profiles
11. Show `/audit/events`

## Outstanding Technical Debt

- add production real embedding model integration for Milvus
- add full Great Expectations checkpoint runner if required
- add production Langfuse project/session/user setup and retention policy
- add production MLflow experiment naming/model registry linkage if required by target deployment
- add DB-backed integration tests with isolated test database
- replace demo secrets with secret manager integration for production
- expand PII masking beyond MVP regex coverage
