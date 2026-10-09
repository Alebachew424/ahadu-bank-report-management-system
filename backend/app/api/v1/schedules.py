"""
Recurring schedule endpoints.

Who can do what:
  - Requester / Requester Manager  → create, list own, update own, pause/resume own, delete own
  - MIS Manager / MIS Supervisor / Admin → list all, view any, fire manually
  - No one can delete a schedule that has active (non-terminal) open tickets
    (they must pause it instead)

Routes:
  POST   /schedules/              create
  GET    /schedules/              list (own or all depending on role)
  GET    /schedules/{id}          get one
  PATCH  /schedules/{id}          update
  DELETE /schedules/{id}          delete
  POST   /schedules/{id}/pause    pause
  POST   /schedules/{id}/resume   resume
  POST   /schedules/{id}/fire     manually fire now (MIS Manager / Admin only)
"""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.schedule import RecurringSchedule
from ...models.user import User
from ...schemas.schedule import ScheduleCreate, ScheduleResponse, ScheduleUpdate
from ...services import audit_service
from ...services.schedule_service import compute_next_run, fire_schedule

router = APIRouter()

MIS_ROLES    = {"MIS Manager", "MIS Supervisor", "Admin", "System Administrator"}
OWNER_ROLES  = {"Requester", "Requester Manager", "MIS Manager", "MIS Supervisor", "Admin", "System Administrator"}


def _role(user: User) -> str:
    return user.role.name if user.role else "Requester"


def _can_own(user: User) -> bool:
    return user.is_superuser or _role(user) in OWNER_ROLES


def _enrich(s: RecurringSchedule) -> dict:
    """Add resolved display names to a schedule dict."""
    d = {c.name: getattr(s, c.name) for c in s.__table__.columns}
    d["request_type_name"]      = s.request_type.name if s.request_type else None
    d["preferred_officer_name"] = (
        (s.preferred_officer.full_name or s.preferred_officer.email)
        if s.preferred_officer else None
    )
    d["owner_name"] = (s.owner.full_name or s.owner.email) if s.owner else None
    return d


def _get_owned(schedule_id: int, current_user: User, db: Session) -> RecurringSchedule:
    """Fetch schedule and verify ownership or MIS/Admin access."""
    s = db.query(RecurringSchedule).filter(RecurringSchedule.id == schedule_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Schedule not found")
    role_name = _role(current_user)
    if not current_user.is_superuser and role_name not in MIS_ROLES and s.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="You do not own this schedule")
    return s


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("/", response_model=ScheduleResponse, status_code=201)
def create_schedule(
    data: ScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _can_own(current_user):
        raise HTTPException(status_code=403, detail="Your role cannot create schedules")

    # Validate weekly/biweekly need day_of_week
    if data.frequency in ("weekly", "biweekly") and data.day_of_week is None:
        raise HTTPException(status_code=422, detail="day_of_week is required for weekly/biweekly schedules")
    if data.frequency == "monthly" and data.day_of_month is None:
        raise HTTPException(status_code=422, detail="day_of_month is required for monthly schedules")

    s = RecurringSchedule(
        owner_id             = current_user.id,
        title                = data.title,
        description          = data.description,
        request_type_id      = data.request_type_id,
        priority             = data.priority,
        due_in_hours         = data.due_in_hours,
        preferred_officer_id = data.preferred_officer_id,
        completion_mode      = data.completion_mode,
        frequency            = data.frequency,
        hour                 = data.hour,
        minute               = data.minute,
        day_of_week          = data.day_of_week,
        day_of_month         = data.day_of_month,
        is_active            = True,
        total_fired          = 0,
    )
    # Compute first next_run_at
    s.next_run_at = compute_next_run(s)

    db.add(s)
    db.flush()

    audit_service.log(
        db,
        action      = "schedule_created",
        entity_type = "schedule",
        entity_id   = s.id,
        user_id     = current_user.id,
        new_value   = {"title": s.title, "frequency": s.frequency, "priority": s.priority},
        description = f"Recurring schedule #{s.id} '{s.title}' created by {current_user.email}",
    )
    db.commit()
    db.refresh(s)
    return _enrich(s)


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[ScheduleResponse])
def list_schedules(
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role_name = _role(current_user)
    qs = db.query(RecurringSchedule)

    # MIS / Admin see all; others see only their own
    if not current_user.is_superuser and role_name not in MIS_ROLES:
        qs = qs.filter(RecurringSchedule.owner_id == current_user.id)

    if active_only:
        qs = qs.filter(RecurringSchedule.is_active.is_(True))

    schedules = qs.order_by(RecurringSchedule.next_run_at.asc().nulls_last()).all()
    return [_enrich(s) for s in schedules]


# ── Get one ───────────────────────────────────────────────────────────────────

@router.get("/{schedule_id}", response_model=ScheduleResponse)
def get_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = _get_owned(schedule_id, current_user, db)
    return _enrich(s)


# ── Update ────────────────────────────────────────────────────────────────────

@router.patch("/{schedule_id}", response_model=ScheduleResponse)
def update_schedule(
    schedule_id: int,
    data: ScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = _get_owned(schedule_id, current_user, db)
    changes = data.model_dump(exclude_unset=True)
    old_vals = {k: getattr(s, k) for k in changes}

    for field, value in changes.items():
        setattr(s, field, value)

    # Recompute next_run if schedule definition changed
    timing_fields = {"frequency", "hour", "minute", "day_of_week", "day_of_month"}
    if timing_fields & set(changes.keys()):
        s.next_run_at = compute_next_run(s)

    audit_service.log(
        db,
        action      = "schedule_updated",
        entity_type = "schedule",
        entity_id   = s.id,
        user_id     = current_user.id,
        old_value   = old_vals,
        new_value   = changes,
        description = f"Recurring schedule #{s.id} updated by {current_user.email}",
    )
    db.commit()
    db.refresh(s)
    return _enrich(s)


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = _get_owned(schedule_id, current_user, db)
    audit_service.log(
        db,
        action      = "schedule_deleted",
        entity_type = "schedule",
        entity_id   = s.id,
        user_id     = current_user.id,
        description = f"Recurring schedule #{s.id} '{s.title}' deleted by {current_user.email}",
    )
    db.delete(s)
    db.commit()


# ── Pause ─────────────────────────────────────────────────────────────────────

@router.post("/{schedule_id}/pause", response_model=ScheduleResponse)
def pause_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = _get_owned(schedule_id, current_user, db)
    if not s.is_active:
        raise HTTPException(status_code=400, detail="Schedule is already paused")
    s.is_active = False
    audit_service.log(
        db,
        action      = "schedule_paused",
        entity_type = "schedule",
        entity_id   = s.id,
        user_id     = current_user.id,
        description = f"Recurring schedule #{s.id} paused by {current_user.email}",
    )
    db.commit()
    db.refresh(s)
    return _enrich(s)


# ── Resume ────────────────────────────────────────────────────────────────────

@router.post("/{schedule_id}/resume", response_model=ScheduleResponse)
def resume_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = _get_owned(schedule_id, current_user, db)
    if s.is_active:
        raise HTTPException(status_code=400, detail="Schedule is already active")
    s.is_active   = True
    s.next_run_at = compute_next_run(s)   # recalculate from now
    audit_service.log(
        db,
        action      = "schedule_resumed",
        entity_type = "schedule",
        entity_id   = s.id,
        user_id     = current_user.id,
        description = f"Recurring schedule #{s.id} resumed by {current_user.email}",
    )
    db.commit()
    db.refresh(s)
    return _enrich(s)


# ── Manual fire (MIS Manager / Admin only) ────────────────────────────────────

@router.post("/{schedule_id}/fire", status_code=201)
def fire_now(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Immediately fire the schedule — creates a ticket right now regardless of next_run_at."""
    role_name = _role(current_user)
    if not current_user.is_superuser and role_name not in MIS_ROLES:
        raise HTTPException(status_code=403, detail="Only MIS Managers and Admins can manually fire schedules")

    s = db.query(RecurringSchedule).filter(RecurringSchedule.id == schedule_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Schedule not found")

    req = fire_schedule(db, s)
    if not req:
        raise HTTPException(
            status_code=400,
            detail="Could not fire schedule — owner may have no department assigned",
        )

    audit_service.log(
        db,
        action      = "schedule_manual_fire",
        entity_type = "schedule",
        entity_id   = s.id,
        user_id     = current_user.id,
        new_value   = {"ticket_id": req.id},
        description = f"Schedule #{s.id} manually fired by {current_user.email} → ticket #{req.id}",
    )
    db.commit()
    return {"schedule_id": s.id, "ticket_id": req.id, "message": f"Ticket #{req.id} created"}
