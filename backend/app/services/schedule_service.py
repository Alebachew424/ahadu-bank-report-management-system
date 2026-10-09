"""
Schedule service — computes next_run_at and fires due recurring schedules.

Responsibilities:
  compute_next_run(schedule)  → next datetime the schedule should fire
  fire_schedule(db, schedule) → create ticket + optional auto-assign + audit
  process_due_schedules(db)   → sweep all active due schedules and fire them
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..models.request import Request, PriorityEnum
from ..models.request_type import RequestType
from ..models.schedule import RecurringSchedule
from ..models.status import Status
from ..models.user import User
from ..services import audit_service, email_service
from ..services.sla_service import compute_sla_deadline

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {"Closed", "Resolved", "Rejected", "Cancelled"}


# ─────────────────────────────────────────────────────────────────────────────
# Next-run computation
# ─────────────────────────────────────────────────────────────────────────────

def compute_next_run(schedule: RecurringSchedule, after: Optional[datetime] = None) -> datetime:
    """
    Return the next UTC datetime this schedule should fire, starting from `after`
    (defaults to now).  We work in UTC throughout.
    """
    now  = (after or datetime.now(timezone.utc)).replace(second=0, microsecond=0)
    h, m = schedule.hour, schedule.minute

    if schedule.frequency == "daily":
        # Next occurrence of HH:MM today or tomorrow
        candidate = now.replace(hour=h, minute=m)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    if schedule.frequency in ("weekly", "biweekly"):
        dow    = schedule.day_of_week or 0      # target weekday (0=Mon)
        days_ahead = (dow - now.weekday()) % 7
        if days_ahead == 0:
            candidate = now.replace(hour=h, minute=m)
            if candidate <= now:
                days_ahead = 7
        candidate = (now + timedelta(days=days_ahead)).replace(hour=h, minute=m)
        if schedule.frequency == "biweekly":
            # If we already fired within the last 7 days, add another week
            if (
                schedule.last_fired_at
                and (candidate - schedule.last_fired_at.replace(tzinfo=timezone.utc)).days < 14
            ):
                candidate += timedelta(weeks=1)
        return candidate

    if schedule.frequency == "monthly":
        dom = min(schedule.day_of_month or 1, 28)
        # Try this month first
        try:
            candidate = now.replace(day=dom, hour=h, minute=m)
        except ValueError:
            candidate = now.replace(day=28, hour=h, minute=m)
        if candidate <= now:
            # Move to next month
            if now.month == 12:
                candidate = candidate.replace(year=now.year + 1, month=1)
            else:
                candidate = candidate.replace(month=now.month + 1)
        return candidate

    # Fallback: daily
    return now.replace(hour=h, minute=m) + timedelta(days=1)


# ─────────────────────────────────────────────────────────────────────────────
# Fire one schedule — creates the ticket
# ─────────────────────────────────────────────────────────────────────────────

def fire_schedule(db: Session, schedule: RecurringSchedule) -> Optional[Request]:
    """
    Creates a ticket from the schedule template.
    Returns the created Request, or None if the owner has no department.
    """
    owner = db.query(User).filter(User.id == schedule.owner_id).first()
    if not owner or not owner.department_id:
        logger.warning(
            "Schedule %d skipped — owner %s has no department",
            schedule.id, getattr(owner, "email", "unknown"),
        )
        return None

    pending = db.query(Status).filter(
        Status.name == "Pending Dept Approval",
        Status.is_active.is_(True),
    ).first()
    if not pending:
        logger.error("Schedule %d: workflow statuses not seeded", schedule.id)
        return None

    now      = datetime.now(timezone.utc)
    due_date = now + timedelta(hours=schedule.due_in_hours)

    # Map priority string → enum safely
    try:
        priority_enum = PriorityEnum(schedule.priority)
    except ValueError:
        priority_enum = PriorityEnum.MEDIUM

    req = Request(
        title           = schedule.title,
        description     = schedule.description,
        request_type_id = schedule.request_type_id,
        priority        = priority_enum,
        due_date        = due_date,
        additional_data = {},
        requester_id    = schedule.owner_id,
        department_id   = owner.department_id,
        status_id       = pending.id,
    )
    db.add(req)
    db.flush()   # get req.id without committing yet

    # ── SLA deadline ──────────────────────────────────────────
    rt = db.query(RequestType).filter(RequestType.id == schedule.request_type_id).first()
    if rt and rt.sla_hours:
        req.sla_deadline = compute_sla_deadline(now, rt.sla_hours, schedule.priority)

    # ── Auto-assign preferred officer ─────────────────────────
    if schedule.preferred_officer_id:
        assigned  = db.query(Status).filter(Status.name == "Assigned").first()
        submitted = db.query(Status).filter(Status.name == "Submitted").first()
        if assigned and submitted:
            req.assigned_to_id = schedule.preferred_officer_id
            req.status_id      = assigned.id   # skip dept-approval + MIS-assign for recurring

    # ── Update schedule counters ─────────────────────────────
    schedule.last_fired_at = now
    schedule.total_fired   = (schedule.total_fired or 0) + 1
    schedule.next_run_at   = compute_next_run(schedule, after=now)

    # ── Audit log ─────────────────────────────────────────────
    audit_service.log(
        db,
        action      = "recurring_ticket_created",
        entity_type = "request",
        entity_id   = req.id,
        user_id     = schedule.owner_id,
        new_value   = {
            "schedule_id":   schedule.id,
            "title":         req.title,
            "priority":      schedule.priority,
            "auto_assigned": schedule.preferred_officer_id is not None,
        },
        description = (
            f"Recurring ticket #{req.id} created from schedule #{schedule.id} "
            f"'{schedule.title}'"
        ),
    )

    db.commit()
    db.refresh(req)

    # ── Email notifications ───────────────────────────────────
    from ..models.department import Department
    dept = db.query(Department).filter(Department.id == owner.department_id).first()

    if schedule.preferred_officer_id:
        # Auto-assigned → notify the officer
        officer = db.query(User).filter(User.id == schedule.preferred_officer_id).first()
        if officer:
            email_service.notify_ticket_assigned(
                officer_email  = officer.email,
                officer_name   = officer.full_name or officer.email,
                ticket_id      = req.id,
                ticket_title   = req.title,
                priority       = schedule.priority,
                due_date       = due_date.strftime("%Y-%m-%d"),
            )
    else:
        # Normal flow → notify dept manager
        if dept and dept.manager_id:
            mgr = db.query(User).filter(User.id == dept.manager_id).first()
            if mgr:
                email_service.notify_ticket_created(
                    dept_manager_email = mgr.email,
                    dept_manager_name  = mgr.full_name or mgr.email,
                    requester_name     = owner.full_name or owner.email,
                    ticket_id          = req.id,
                    ticket_title       = req.title,
                    priority           = schedule.priority,
                    due_date           = due_date.strftime("%Y-%m-%d"),
                )

    logger.info(
        "Schedule %d fired → ticket #%d (next_run=%s)",
        schedule.id, req.id, schedule.next_run_at,
    )
    return req


# ─────────────────────────────────────────────────────────────────────────────
# Sweep — called by Celery beat every minute
# ─────────────────────────────────────────────────────────────────────────────

def process_due_schedules(db: Session) -> int:
    """
    Find all active schedules whose next_run_at has passed and fire them.
    Returns the number of tickets created.
    """
    now = datetime.now(timezone.utc)

    due = (
        db.query(RecurringSchedule)
        .filter(
            RecurringSchedule.is_active.is_(True),
            RecurringSchedule.next_run_at != None,   # noqa: E711
            RecurringSchedule.next_run_at <= now,
        )
        .all()
    )

    fired = 0
    for schedule in due:
        try:
            result = fire_schedule(db, schedule)
            if result:
                fired += 1
        except Exception as exc:
            db.rollback()
            logger.error(
                "Error firing schedule %d: %s", schedule.id, exc, exc_info=True
            )

    return fired


# ─────────────────────────────────────────────────────────────────────────────
# Auto-close helper — called when MIS Officer resolves a recurring ticket
# ─────────────────────────────────────────────────────────────────────────────

def maybe_auto_close(db: Session, request: Request) -> bool:
    """
    If the ticket was created by a recurring schedule with completion_mode='auto_close',
    automatically move it to 'Closed' instead of waiting for requester feedback.
    Returns True if auto-closed.
    """
    # Find the schedule that owns this ticket (same owner + title + recurring)
    schedule = (
        db.query(RecurringSchedule)
        .filter(
            RecurringSchedule.owner_id == request.requester_id,
            RecurringSchedule.title    == request.title,
            RecurringSchedule.completion_mode == "auto_close",
        )
        .first()
    )
    if not schedule:
        return False

    closed = db.query(Status).filter(Status.name == "Closed").first()
    if not closed:
        return False

    request.status_id = closed.id
    db.commit()
    logger.info("Ticket #%d auto-closed (schedule #%d)", request.id, schedule.id)
    return True
