# Final Demo UI Runbook

## Start

```bash
docker compose up --build -d
```

Open:

```text
http://localhost:8501
```

## Demo Flow

1. Confirm backend health is visible.
2. Confirm readiness status is visible.
3. Select an enabled model profile.
4. Submit a question through `/ask`.
5. Review answer, status, trace ID, model profile, provider, model metadata, citations, and quality scores.
6. Click `Load trace` and inspect trace events.
7. Submit feedback with rating/comment.
8. Optionally open FastAPI docs, Grafana, MLflow, or Langfuse from `Links / Operations`.

## RAG Fallback Behavior

The demo must not show ungrounded general-knowledge answers as normal RAG output. If retrieved context is missing or the model answer fails citation/grounding checks, `/ask` returns:

```text
I do not have enough context to answer this question based on the available documents.
Sources: none
```

`status=fallback` means the system avoided an ungrounded answer. In the trace, inspect `fallback_decision` for pre-generation fallback or `post_validation_fallback` when a raw model answer was replaced. `status=failed` means a technical or validation failure that was not converted to controlled fallback.

## UI Demo Checklist

- [ ] Backend health visible
- [ ] Readiness status visible
- [ ] Model profile selector visible
- [ ] `/ask` works
- [ ] Answer displayed
- [ ] Citations displayed
- [ ] Scores displayed
- [ ] Trace loaded
- [ ] Feedback submitted
- [ ] Errors handled correctly

## Notes

- Host UI URL: `http://localhost:8501`
- Docker backend URL: `http://api:8000`
- Host backend URL for local Streamlit: `http://localhost:8000`
- API key can be passed through the sidebar and is sent as `X-API-Key`.
- Model profiles are loaded from `GET /models`; disabled profiles are not selectable.
