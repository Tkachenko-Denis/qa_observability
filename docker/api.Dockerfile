FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN mkdir -p /tmp/prometheus

COPY pyproject.toml README.md ./
COPY services ./services
COPY db ./db
COPY datasets ./datasets
COPY ge ./ge
COPY config ./config
COPY eval ./eval
COPY scripts ./scripts

RUN pip install --upgrade pip && pip install ".[dq]"

ENV PYTHONPATH=/app/services/api

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
