"""
SLA (Service Level Agreement) tracking service.

Responsibilities:
  - Compute sla_deadline when a ticket is created
  - Check whether a ticket is overdue at query time
  - Return SLA status for dashboard and list views
  - Run the escalation sweep (called periodically by background task)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..models.request import Request
from ..models.user import User
from ..models.role import Role
from ..models.status import Status

logger = logging.getLogger(__name__)

# Terminal statuses — SLA is not checked once a ticket reaches one of these
TERMINAL_STATUSES = {"Closed", "Resolved", "Rejected", "Cancelled"}

# Priority multiplier — urgent tickets consume SLA hours faster
# A ticket with sla_hours=72 and priority=urgent gets 72 * 0.25 = 18 hours
PRIORITY_MULTIPLIER: dict[str, float] = {
    "low":    1.5,
    "medium": 1.0,
    "high":   0.5,
    "urgent": 0.25,
}


def compute_sla_deadline(created_at: datetime, sla_hours: int, priority: str) -> datetime:
    """Return the UTC deadline by which the ticket must be resolved."""
    multiplier = PRIORITY_MULTIPLIER.get(priority, 1.0)
    effective_hours = sla_hours * multiplier
    return created_at + timedelta(hours=effective_hours)


def enrich_request_sla(req: Request) -> dict[str, Any]:
    """
    Returns a dict with SLA fields that can be merged into the response.
    Called per-ticket on detail and list views.
    """
    now = datetime.now(timezone.utc)

    if req.sla_deadline is None:
        return {"sla_deadline": None, "sla_hours_remaining": None, "sla_overdue": False, "sla_breached": req.sla_breached}

    status_name = req.status.name if req.status else ""
    if status_name in TERMINAL_STATUSES:
        return {"sla_deadline": req.sla_deadline, "sla_hours_remaining": None, "sla_overdue": False, "sla_breached": req.sla_breached}

    deadline = req.sla_deadline
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)

    hours_remaining = (deadline - now).total_seconds() / 3600
    overdue = hours_remaining < 0

    return {
        "sla_deadline":       req.sla_deadline,
        "sla_hours_remaining": round(hours_remaining, 1),
        "sla_overdue":        overdue,
        "sla_breached":       req.sla_breached,
    }


def run_sla_escalation(db: Session) -> int:
    """
    Sweep all non-terminal, non-escalated tickets with a passed SLA deadline.
    For each breach:
      1. Mark sla_breached=True, escalated_at=now
      2. Bump priority one level (medium→high, high→urgent)
      3. Send SLA breach email to MIS Supervisors
      4. Commit

    Returns the number of tickets escalated.
    """
    from .email_service import notify_sla_breach

    now = datetime.now(timezone.utc)

    # Get terminal status IDs to exclude
    terminal_statuses = db.query(Status).filter(Status.name.in_(TERMINAL_STATUSES)).all()
    terminal_ids      = {s.id for s in terminal_statuses}

    # Find breached but not yet escalated tickets
    overdue = (
        db.query(Request)
        .filter(
            Request.sla_deadline != None,          # noqa: E711
            Request.sla_deadline < now,
            Request.sla_breached == False,         # noqa: E712
            ~Request.status_id.in_(terminal_ids),
        )
        .all()
    )

    if not overdue:
        return 0

    # Get MIS Supervisor emails for escalation notifications
    supervisors = (
        db.query(User)
        .join(Role, User.role_id == Role.id)
        .filter(Role.name.in_(["MIS Supervisor", "Admin", "System Administrator"]), User.is_active.is_(True))
        .all()
    )
    supervisor_emails = [u.email for u in supervisors]

    priority_escalation = {"low": "medium", "medium": "high", "high": "urgent", "urgent": "urgent"}
    escalated = 0

    for req in overdue:
        old_priority = req.priority.value if hasattr(req.priority, "value") else str(req.priority)
        new_priority = priority_escalation.get(old_priority, old_priority)
        hours_overdue = (now - req.sla_deadline.replace(tzinfo=timezone.utc)).total_seconds() / 3600

        req.sla_breached = True
        req.escalated_at = now
        req.priority     = new_priority

        officer = db.query(User).filter(User.id == req.assigned_to_id).first() if req.assigned_to_id else None
        officer_name = officer.full_name or officer.email if officer else None

        notify_sla_breach(
            supervisor_emails=supervisor_emails,
            ticket_id=req.id,
            ticket_title=req.title,
            priority=old_priority,
            hours_overdue=hours_overdue,
            assigned_officer_name=officer_name,
        )
        escalated += 1

    db.commit()
    logger.info("SLA escalation: %d tickets escalated", escalated)
    return escalated
