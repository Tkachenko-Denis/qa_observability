PYTHONPATH=services/api

install:
	pip install -e .[dev]

run-api:
	set PYTHONPATH=$(PYTHONPATH) && uvicorn app.main:app --reload

migrate:
	set PYTHONPATH=$(PYTHONPATH) && alembic -c services/api/alembic.ini upgrade head

test:
	set PYTHONPATH=$(PYTHONPATH) && pytest
