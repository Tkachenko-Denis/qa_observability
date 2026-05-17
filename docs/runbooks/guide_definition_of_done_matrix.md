# Guide Definition Of Done Matrix

## Goal

Map the implementation guide's Definition of Done to concrete MVP artifacts and verification commands.

## Assumptions

- Domain / end LLM use case: not specified.
- Annotation type: not specified.
- Scale, volumes, ingestion frequency: not specified.
- Default demonstration contour is RAG / knowledge base documents.

## DoD Coverage

| Guide DoD Item | MVP Evidence | Status |
| --- | --- | --- |
| `docker-compose up` starts core services | `docker-compose.yml`, `docker compose config`, live stack used for Airflow/Grafana/Prometheus checks | covered |
| Load documents and build index | `scripts/ingest_documents.py`, `scripts/bootstrap_milvus.py`, `scripts/build_index.py`, `ingest_documents_dag`, `build_embeddings_dag` | covered |
| Ask through `/ask` | `POST /ask`, RAG vertical slice tests | covered |
| LLM provider modes | `mock`, `openai`, `ollama`, `qwen_ollama` provider adapters with fallback | covered |
| Answer contains citations | `AskResponse.citations`, `response_citations` table | covered |
| Trace stages are persisted | `trace_events`, `GET /trace/{trace_id}`, Langfuse contract/export payloads | covered |
| Numeric metrics are in Prometheus | `/metrics`, Prometheus gauges/counters, alert rules | covered |
| Grafana dashboard shows API/LLM/retrieval/DQ/eval | `dashboards/grafana/dashboards/mvp-overview.json` | covered |
| GX checks run and write results | `scripts/run_gx_dq_checks.py`, GX-style/custom runtime checks, `run_gx_dq_checks_dag`, `dq_results` | covered |
| MLflow eval run exists | `scripts/run_eval.py`, `eval_runs`, `eval_scores`, local artifacts, optional MLflow SDK logging, persistent `mlflow_data` volume | covered |
| Airflow runs ingestion, DQ, eval, quality gate | `docs/runbooks/airflow_smoke.md` | covered |
| Quality gate returns passed/failed | `scripts/quality_gate.py`, `/quality-gates/latest`, `quality_gate_dag` | covered |
| README explains launch, UI tabs, and metrics | `README.md` | covered |
| Security and audit MVP | API key middleware, PII masking, `/audit/events` | covered |
| Milvus and Langfuse availability | Optional Compose profiles plus SDK-backed best-effort runtime paths/fallbacks | extension-ready |

## Verification Commands

```bash
docker compose config
docker compose --profile milvus config
docker compose --profile langfuse config
python scripts/airflow_api_smoke.py --base-url http://localhost:8080 --username admin --password admin
python scripts/e2e_validation_smoke.py --base-url http://localhost:8000 --require-success-ask
python -m pytest -v
```

Windows local venv equivalent:

```powershell
.\.venv\Scripts\python.exe scripts\airflow_api_smoke.py --base-url http://localhost:8080 --username admin --password admin
.\.venv\Scripts\python.exe scripts\e2e_validation_smoke.py --base-url http://localhost:8000 --require-success-ask
.\.venv\Scripts\python.exe -m pytest -v
```

## Verification Notes

- E2E smoke covers `/ask`, `/trace`, `/metrics`, `/feedback`, eval, runtime DQ, quality gate, and readiness.
- Airflow smoke checks the current required DAG set and import errors.
- `quality_gate_dag` may fail by design when configured thresholds are not met.

## Remaining Non-MVP Work

- Production real embedding model integration; current Milvus bootstrap uses deterministic MVP embeddings.
- Full Great Expectations checkpoint runner; current runtime DQ is GX-style/custom.
- Production Langfuse project/session/user setup and retention policy.
- Production MLflow experiment naming/model registry linkage.
- Production RBAC, tenant isolation, TLS, retention, secret manager integration.
- Browser-level Grafana automation.
