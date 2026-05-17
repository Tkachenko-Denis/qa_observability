# Airflow Smoke

## Назначение

Проверить, что Airflow использует отдельную служебную базу, видит актуальные DAG и может запускать оркестрационные задачи без локальных абсолютных путей.

## Предпосылки

- PostgreSQL при первом старте автоматически создает базу `airflow_metadata` через `docker/postgres/init/01-create-airflow-db.sql`.
- При старом уже созданном volume база могла отсутствовать; в этом случае нужна разовая миграция состояния или пересоздание volume.
- Проектные скрипты внутри Airflow запускаются через `/opt/airflow/dq_venv/bin/python`.

## Проверка через CLI

```bash
docker compose up --build -d airflow-init airflow-webserver airflow-scheduler
docker compose exec -T airflow-scheduler airflow dags list
docker compose exec -T airflow-scheduler airflow dags test ingest_documents_dag 2026-04-27
docker compose exec -T airflow-scheduler airflow dags test build_embeddings_dag 2026-04-27
docker compose exec -T airflow-scheduler airflow dags test run_gx_dq_checks_dag 2026-04-27
docker compose exec -T airflow-scheduler airflow dags test run_eval_suite_dag 2026-04-28
docker compose exec -T airflow-scheduler airflow dags test quality_gate_dag 2026-04-28
```

## Проверка через REST API

```bash
python scripts/airflow_api_smoke.py --base-url http://localhost:8080 --username admin --password admin
```

Скрипт проверяет:

- `GET /health`;
- `GET /api/v1/dags?limit=100`;
- `GET /api/v1/importErrors`;
- наличие обязательных DAG:
  - `ingest_documents_dag`;
  - `build_embeddings_dag`;
  - `run_gx_dq_checks_dag`;
  - `run_eval_suite_dag`;
  - `quality_gate_dag`.

## Ожидаемый результат

- Метабаза Airflow здорова.
- Ошибок импорта DAG нет.
- Все обязательные DAG доступны.
- `quality_gate_dag` может завершаться неуспешно при нарушении порогов качества; это ожидаемое поведение жесткого правила допуска, а не ошибка Airflow.
