from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import SessionLocal
from app.models import AuditEvent


EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")
AUTH_EXCLUDED_PATHS = {
    "/health",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
}


def hash_user_id(user_id: str | None) -> str | None:
    if not user_id:
        return None
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()


def mask_pii(value: Any) -> Any:
    if isinstance(value, str):
        masked = EMAIL_PATTERN.sub("[EMAIL]", value)
        return PHONE_PATTERN.sub("[PHONE]", masked)
    if isinstance(value, list):
        return [mask_pii(item) for item in value]
    if isinstance(value, dict):
        return {key: mask_pii(item) for key, item in value.items()}
    return value


def contains_pii(value: Any) -> bool:
    return mask_pii(value) != value


def record_audit_event(
    db: Session,
    event_type: str,
    *,
    trace_id: uuid.UUID | None = None,
    user_id_hash: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        trace_id=trace_id,
        event_type=event_type,
        user_id_hash=user_id_hash,
        details=mask_pii(details or {}),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _extract_api_key(request: Request) -> str | None:
    header_key = request.headers.get("x-api-key")
    if header_key:
        return header_key
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


def should_skip_auth(path: str) -> bool:
    return path in AUTH_EXCLUDED_PATHS or path.startswith("/docs/") or path.startswith("/static/")


def build_api_key_middleware(settings: Settings) -> Callable:
    async def api_key_middleware(request: Request, call_next: Callable) -> Response:
        if not settings.api_key_auth_enabled or should_skip_auth(request.url.path):
            return await call_next(request)

        provided_key = _extract_api_key(request)
        with SessionLocal() as db:
            if provided_key != settings.api_key:
                record_audit_event(
                    db,
                    "auth_failed",
                    details={"path": request.url.path, "method": request.method},
                )
                return JSONResponse(status_code=401, content={"detail": "invalid or missing API key"})

            record_audit_event(
                db,
                "auth_success",
                details={"path": request.url.path, "method": request.method},
            )

        return await call_next(request)

    return api_key_middleware
