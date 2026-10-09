"""
Admin endpoints:
  GET  /api/v1/admin/audit-logs          — search / filter audit logs
  GET  /api/v1/admin/audit-logs/export   — download as CSV
  GET  /api/v1/admin/audit-logs/{id}     — single entry detail

Access: Admin, System Administrator, MIS Supervisor only.
Audit logs are read-only — no POST / PATCH / DELETE.
"""
import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.audit_log import AuditLog
from ...models.user import User

router = APIRouter()

ALLOWED_ROLES = {"Admin", "System Administrator", "MIS Supervisor"}


def _require_admin(current_user: User) -> None:
    if current_user.is_superuser:
        return
    role_name = current_user.role.name if current_user.role else ""
    if role_name not in ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")


# ── helpers ───────────────────────────────────────────────────────────────────

def _build_query(
    db: Session,
    action:      Optional[str],
    entity_type: Optional[str],
    entity_id:   Optional[int],
    user_id:     Optional[int],
    date_from:   Optional[str],
    date_to:     Optional[str],
    search:      Optional[str],
):
    qs = db.query(AuditLog)

    if action:
        qs = qs.filter(AuditLog.action == action)
    if entity_type:
        qs = qs.filter(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        qs = qs.filter(AuditLog.entity_id == entity_id)
    if user_id is not None:
        qs = qs.filter(AuditLog.user_id == user_id)
    if date_from:
        try:
            qs = qs.filter(AuditLog.created_at >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            qs = qs.filter(AuditLog.created_at <= datetime.fromisoformat(date_to + "T23:59:59"))
        except ValueError:
            pass
    if search:
        term = f"%{search.strip()}%"
        qs = qs.filter(AuditLog.description.ilike(term))

    return qs.order_by(AuditLog.created_at.desc())


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("/audit-logs")
def list_audit_logs(
    action:      Optional[str] = Query(None, description="e.g. login_success, ticket_created, dept_approved"),
    entity_type: Optional[str] = Query(None, description="e.g. request, auth, user"),
    entity_id:   Optional[int] = Query(None),
    user_id:     Optional[int] = Query(None),
    date_from:   Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to:     Optional[str] = Query(None, description="YYYY-MM-DD"),
    search:      Optional[str] = Query(None, description="Search in description"),
    skip:  int = Query(0,  ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)

    qs    = _build_query(db, action, entity_type, entity_id, user_id, date_from, date_to, search)
    total = qs.count()
    rows  = qs.offset(skip).limit(limit).all()

    return {
        "total": total,
        "skip":  skip,
        "limit": limit,
        "results": [
            {
                "id":          r.id,
                "user_id":     r.user_id,
                "user_email":  r.user.email if r.user else None,
                "action":      r.action,
                "entity_type": r.entity_type,
                "entity_id":   r.entity_id,
                "old_value":   r.old_value,
                "new_value":   r.new_value,
                "description": r.description,
                "ip_address":  r.ip_address,
                "created_at":  r.created_at,
            }
            for r in rows
        ],
    }


@router.get("/audit-logs/export")
def export_audit_logs_csv(
    action:      Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    entity_id:   Optional[int] = Query(None),
    user_id:     Optional[int] = Query(None),
    date_from:   Optional[str] = Query(None),
    date_to:     Optional[str] = Query(None),
    search:      Optional[str] = Query(None),
    token:       Optional[str] = Query(None),   # browser download fallback
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download the filtered audit log as a UTF-8 CSV file."""
    _require_admin(current_user)

    rows = _build_query(db, action, entity_type, entity_id, user_id, date_from, date_to, search).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "timestamp", "user_email", "user_id",
        "action", "entity_type", "entity_id",
        "description", "old_value", "new_value", "ip_address",
    ])
    for r in rows:
        writer.writerow([
            r.id,
            r.created_at.isoformat() if r.created_at else "",
            r.user.email if r.user else "",
            r.user_id or "",
            r.action,
            r.entity_type,
            r.entity_id or "",
            r.description or "",
            str(r.old_value) if r.old_value else "",
            str(r.new_value) if r.new_value else "",
            r.ip_address or "",
        ])

    output.seek(0)
    filename = f"audit_log_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/audit-logs/{log_id}")
def get_audit_log(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    entry = db.query(AuditLog).filter(AuditLog.id == log_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Audit log entry not found")
    return {
        "id":          entry.id,
        "user_id":     entry.user_id,
        "user_email":  entry.user.email if entry.user else None,
        "action":      entry.action,
        "entity_type": entry.entity_type,
        "entity_id":   entry.entity_id,
        "old_value":   entry.old_value,
        "new_value":   entry.new_value,
        "description": entry.description,
        "ip_address":  entry.ip_address,
        "created_at":  entry.created_at,
    }


# ── distinct action/entity values for filter dropdowns ───────────────────────

@router.get("/audit-logs-meta")
def audit_log_meta(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns distinct action and entity_type values for filter dropdowns."""
    _require_admin(current_user)
    from sqlalchemy import distinct
    actions      = [r[0] for r in db.query(distinct(AuditLog.action)).order_by(AuditLog.action).all()]
    entity_types = [r[0] for r in db.query(distinct(AuditLog.entity_type)).order_by(AuditLog.entity_type).all()]
    return {"actions": actions, "entity_types": entity_types}


# ── AI / ML endpoints ─────────────────────────────────────────────────────────

@router.post("/ai/analyse")
def ai_analyse(
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run all three AI analyses on a draft ticket before submission.

    Request body:
      { "title": str, "description": str|null, "priority": str, "request_type_id": int|null }

    Returns categorisation suggestions, analyst suggestions, and anomaly flags.
    Callable by any authenticated user (used from the create-ticket form).
    """
    from ...services.ai_service import analyse_request

    title           = (body.get("title") or "").strip()
    description     = body.get("description")
    priority        = body.get("priority") or "medium"
    request_type_id = body.get("request_type_id")

    if not title:
        raise HTTPException(status_code=422, detail="title is required")

    result = analyse_request(
        db             = db,
        requester_id   = current_user.id,
        title          = title,
        description    = description,
        priority       = priority,
        request_type_id= request_type_id,
    )
    return result


@router.get("/ai/analyst-suggestion")
def ai_analyst_suggestion(
    request_type_id: int  = Query(...),
    priority:        str  = Query("medium"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns the top-5 MIS Officer suggestions for a given ticket type + priority.
    Used in the MIS Manager assign panel.
    Restricted to MIS Manager / MIS Supervisor / Admin.
    """
    role_name = current_user.role.name if current_user.role else ""
    if not current_user.is_superuser and role_name not in {
        "MIS Manager", "MIS Supervisor", "Admin", "System Administrator"
    }:
        raise HTTPException(status_code=403, detail="Access denied")

    from ...services.ai_service import suggest_analyst
    return suggest_analyst(db, request_type_id, priority)


@router.get("/ai/anomaly-report")
def ai_anomaly_report(
    days: int = Query(7, ge=1, le=90, description="Look-back window in days"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns all tickets flagged as anomalous in the last N days.
    Admin / MIS Supervisor / MIS Manager only.
    """
    role_name = current_user.role.name if current_user.role else ""
    if not current_user.is_superuser and role_name not in {
        "MIS Manager", "MIS Supervisor", "Admin", "System Administrator"
    }:
        raise HTTPException(status_code=403, detail="Access denied")

    from ...models.request import Request
    from datetime import datetime, timezone, timedelta

    since = datetime.now(timezone.utc) - timedelta(days=days)
    flagged = (
        db.query(Request)
        .filter(
            Request.ai_anomaly_flagged.is_(True),
            Request.created_at >= since,
        )
        .order_by(Request.created_at.desc())
        .all()
    )

    return {
        "total":   len(flagged),
        "days":    days,
        "tickets": [
            {
                "id":              r.id,
                "title":           r.title,
                "requester_id":    r.requester_id,
                "priority":        str(r.priority.value if hasattr(r.priority, "value") else r.priority),
                "status":          r.status.name if r.status else None,
                "created_at":      r.created_at,
                "anomaly_details": r.ai_anomaly_details or [],
            }
            for r in flagged
        ],
    }
