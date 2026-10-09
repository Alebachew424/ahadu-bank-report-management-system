"""
Audit logging service.
All writes are fire-and-forget — they must never raise and block the main workflow.
The audit_logs table is append-only: no updates or deletes are ever issued.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from ..models.audit_log import AuditLog

logger = logging.getLogger(__name__)


def log(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    user_id: int | None = None,
    old_value: Any = None,
    new_value: Any = None,
    description: str | None = None,
    ip_address: str | None = None,
) -> None:
    """
    Append one audit record. Silently swallows exceptions so a logging
    failure never aborts the business transaction.
    """
    try:
        entry = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=old_value,
            new_value=new_value,
            description=description,
            ip_address=ip_address,
        )
        db.add(entry)
        # We intentionally do NOT commit here — the caller's transaction
        # will commit both the business change and the audit row together.
    except Exception as exc:  # pragma: no cover
        logger.error("audit_service.log failed: %s", exc, exc_info=True)
