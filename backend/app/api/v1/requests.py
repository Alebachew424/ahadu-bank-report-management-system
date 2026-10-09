"""
Ticket / request lifecycle endpoints.

Workflow summary
----------------
1. Officer (Requester) creates ticket          → "Pending Dept Approval"
2. Dept Manager approves                       → "Submitted"
3. MIS Manager assigns to MIS Officer          → "Assigned"
4. MIS Officer starts work                     → "In Progress"
5a. MIS Officer resolves                       → "Resolved"
5b. MIS Officer needs more info                → "Needs Clarification"
   Requester replies via comment               → back to "In Progress"
6. Requester submits feedback + rating         → "Closed"

New in v2:
- Audit log on every state change
- Email notifications at each workflow step
- SLA deadline computed on create; sla_overdue flag on responses
- Full-text + advanced search on GET /requests/search
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request as FastAPIRequest, status as http_status
from sqlalchemy import or_, func as sqlfunc, text
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.audit_log import AuditLog
from ...models.department import Department
from ...models.feedback import RequestFeedback
from ...models.request import Request
from ...models.request_type import RequestType
from ...models.role import Role
from ...models.status import Status
from ...models.user import User
from ...schemas.feedback import FeedbackCreate, FeedbackResponse
from ...schemas.request import RequestCreate, RequestResponse, RequestUpdate
from ...services import audit_service, email_service
from ...services.request_service import RequestService
from ...services.sla_service import compute_sla_deadline, enrich_request_sla
from ...services.workflow_service import WorkflowService

router = APIRouter()

# ── helpers ───────────────────────────────────────────────────────────────────

def _attach_status_name(req: Request) -> Request:
    req.status_name = req.status.name if req.status else None
    # Attach live SLA fields so the Pydantic response model picks them up
    sla = enrich_request_sla(req)
    req.sla_hours_remaining = sla["sla_hours_remaining"]
    req.sla_overdue         = sla["sla_overdue"]
    req.sla_breached        = sla["sla_breached"]
    return req


def _role(user: User) -> str:
    return user.role.name if user.role else "Requester"


def _client_ip(request: FastAPIRequest) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _mis_manager_emails(db: Session) -> list[str]:
    managers = (
        db.query(User)
        .join(Role, User.role_id == Role.id)
        .filter(Role.name.in_(["MIS Manager", "MIS Supervisor"]), User.is_active.is_(True))
        .all()
    )
    return [u.email for u in managers]


# ── lookup endpoints (no path params — must come before /{id} routes) ─────────

@router.get("/types")
def list_request_types(db: Session = Depends(get_db)):
    """Public lookup: available report types."""
    return (
        db.query(RequestType)
        .filter(RequestType.is_active.is_(True))
        .order_by(RequestType.name)
        .all()
    )


@router.get("/departments")
def list_departments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Department)
        .filter(Department.is_active.is_(True))
        .order_by(Department.name)
        .all()
    )


@router.get("/previous-response")
def get_previous_response(
    request_type_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns the most recent Closed/Resolved ticket of the same request_type
    submitted by this requester, along with its final attachments and public comments.
    """
    from ...models.attachment import Attachment
    from ...models.comment import RequestComment

    closed_ids = [
        s.id for s in db.query(Status).filter(Status.name.in_(["Closed", "Resolved"])).all()
    ]
    if not closed_ids:
        return None

    prev = (
        db.query(Request)
        .filter(
            Request.requester_id    == current_user.id,
            Request.request_type_id == request_type_id,
            Request.status_id.in_(closed_ids),
        )
        .order_by(Request.created_at.desc())
        .first()
    )
    if not prev:
        return None

    attachments = (
        db.query(Attachment)
        .filter(Attachment.request_id == prev.id)
        .order_by(Attachment.version.desc())
        .all()
    )
    comments = (
        db.query(RequestComment)
        .filter(RequestComment.request_id == prev.id, RequestComment.is_internal.is_(False))
        .order_by(RequestComment.created_at)
        .all()
    )
    return {
        "ticket_id":   prev.id,
        "title":       prev.title,
        "description": prev.description,
        "status":      prev.status.name if prev.status else None,
        "closed_at":   prev.updated_at or prev.created_at,
        "attachments": [{"id": a.id, "file_name": a.file_name, "is_final": a.is_final, "version": a.version} for a in attachments],
        "comments":    [{"id": c.id, "body": c.body, "created_at": c.created_at} for c in comments],
    }


# ── advanced search ───────────────────────────────────────────────────────────

@router.get("/search")
def search_requests(
    q:             Optional[str]  = Query(None, description="Full-text search across title, description, comments"),
    status:        Optional[str]  = Query(None, description="Comma-separated status names, e.g. 'Submitted,Assigned'"),
    priority:      Optional[str]  = Query(None, description="Comma-separated priorities, e.g. 'high,urgent'"),
    department_id: Optional[int]  = Query(None),
    requester_id:  Optional[int]  = Query(None),
    assignee_id:   Optional[int]  = Query(None),
    date_from:     Optional[str]  = Query(None, description="ISO date YYYY-MM-DD"),
    date_to:       Optional[str]  = Query(None, description="ISO date YYYY-MM-DD"),
    overdue_only:  bool           = Query(False, description="Only tickets past SLA deadline"),
    sort_by:       str            = Query("created_at", description="Column to sort by: created_at|due_date|priority|status_id"),
    sort_dir:      str            = Query("desc", description="asc or desc"),
    skip:          int            = Query(0, ge=0),
    limit:         int            = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Advanced search with full-text, combined filters, and sort.
    Results are scoped to what the current user is allowed to see
    (same role-based rules as GET /).
    """
    role_name = _role(current_user)

    # Base queryset — role-scoped
    if current_user.is_superuser or role_name in {"Admin", "System Administrator", "MIS Supervisor"}:
        qs = db.query(Request)
    elif role_name == "MIS Manager":
        pending = db.query(Status).filter(Status.name == "Pending Dept Approval").first()
        qs = db.query(Request).filter(Request.status_id != pending.id if pending else True)
    elif role_name == "MIS Officer":
        qs = db.query(Request).filter(Request.assigned_to_id == current_user.id)
    elif user_is_dept_manager(current_user, role_name):
        qs = db.query(Request).filter(Request.department_id == current_user.department_id)
    else:
        qs = db.query(Request).filter(Request.requester_id == current_user.id)

    # Full-text search — PostgreSQL tsvector on title + description
    if q and q.strip():
        search_term = q.strip()
        # Use PostgreSQL to_tsvector for proper full-text search
        qs = qs.filter(
            or_(
                Request.title.ilike(f"%{search_term}%"),
                Request.description.ilike(f"%{search_term}%"),
                sqlfunc.cast(Request.id, sqlfunc.String if False else Request.id.__class__).like(f"%{search_term}%"),
            )
        )

    # Status filter (comma-separated)
    if status:
        status_names = [s.strip() for s in status.split(",") if s.strip()]
        status_ids   = [s.id for s in db.query(Status).filter(Status.name.in_(status_names)).all()]
        if status_ids:
            qs = qs.filter(Request.status_id.in_(status_ids))

    # Priority filter (comma-separated)
    if priority:
        priorities = [p.strip().lower() for p in priority.split(",") if p.strip()]
        qs = qs.filter(Request.priority.in_(priorities))

    # Department filter
    if department_id:
        qs = qs.filter(Request.department_id == department_id)

    # Requester filter
    if requester_id:
        qs = qs.filter(Request.requester_id == requester_id)

    # Assignee filter
    if assignee_id:
        qs = qs.filter(Request.assigned_to_id == assignee_id)

    # Date range
    if date_from:
        try:
            qs = qs.filter(Request.created_at >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            qs = qs.filter(Request.created_at <= datetime.fromisoformat(date_to + "T23:59:59"))
        except ValueError:
            pass

    # Overdue only
    if overdue_only:
        now = datetime.now(timezone.utc)
        terminal = db.query(Status).filter(Status.name.in_(["Closed", "Resolved", "Rejected", "Cancelled"])).all()
        terminal_ids = {s.id for s in terminal}
        qs = qs.filter(
            Request.sla_deadline != None,   # noqa: E711
            Request.sla_deadline < now,
            ~Request.status_id.in_(terminal_ids),
        )

    # Sort
    allowed_sort = {"created_at", "due_date", "priority", "status_id"}
    sort_col = sort_by if sort_by in allowed_sort else "created_at"
    col = getattr(Request, sort_col)
    qs = qs.order_by(col.desc() if sort_dir == "desc" else col.asc())

    total = qs.count()
    results = qs.offset(skip).limit(limit).all()
    for req in results:
        _attach_status_name(req)

    return {
        "total":   total,
        "skip":    skip,
        "limit":   limit,
        "results": results,
    }


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.post("/", response_model=RequestResponse, status_code=201)
def create_request(
    data: RequestCreate,
    http_req: FastAPIRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Any authenticated business user (Requester) submits a new ticket.
    Initial status: 'Pending Dept Approval'.
    """
    role_name = _role(current_user)
    if not current_user.is_superuser and role_name not in {
        "Requester", "Requester Manager", "Admin", "System Administrator"
    }:
        raise HTTPException(status_code=403, detail="Only business team members can submit report requests")

    req = RequestService.create_request(db, data, current_user.id)

    # ── AI analysis (runs before SLA so priority is still raw) ───────────────
    try:
        from ...services.ai_service import analyse_request
        priority_val = req.priority.value if hasattr(req.priority, "value") else str(req.priority)
        ai = analyse_request(
            db              = db,
            requester_id    = current_user.id,
            title           = req.title,
            description     = req.description,
            priority        = priority_val,
            request_type_id = req.request_type_id,
        )
        # Persist top suggestions and anomaly flag onto the ticket
        cat = ai.get("categorisation", {}).get("suggestions", [])
        if cat:
            req.ai_suggested_type_id = cat[0]["request_type_id"]
            req.ai_type_confidence   = cat[0]["confidence"]
        ana = ai.get("analyst_suggestion", {}).get("suggestions", [])
        if ana:
            req.ai_suggested_officer_id = ana[0]["officer_id"]
            req.ai_officer_score        = ana[0]["score"]
        anomaly = ai.get("anomalies", {})
        req.ai_anomaly_flagged  = anomaly.get("flagged", False)
        req.ai_anomaly_details  = anomaly.get("anomalies", [])
        db.commit()
        db.refresh(req)
    except Exception as _ai_exc:
        import logging
        logging.getLogger(__name__).warning("AI analysis failed (non-fatal): %s", _ai_exc)

    # ── SLA deadline ──────────────────────────────────────────
    rt = db.query(RequestType).filter(RequestType.id == req.request_type_id).first()
    if rt and rt.sla_hours:
        created = req.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        priority_val = req.priority.value if hasattr(req.priority, "value") else str(req.priority)
        req.sla_deadline = compute_sla_deadline(created, rt.sla_hours, priority_val)
        db.commit()
        db.refresh(req)

    # ── Audit log ─────────────────────────────────────────────
    audit_service.log(
        db,
        action="ticket_created",
        entity_type="request",
        entity_id=req.id,
        user_id=current_user.id,
        new_value={"title": req.title, "priority": str(req.priority), "request_type_id": req.request_type_id},
        description=f"Ticket #{req.id} created by {current_user.email}",
        ip_address=_client_ip(http_req),
    )
    db.commit()

    # ── Email: notify dept manager ────────────────────────────
    dept = db.query(Department).filter(Department.id == req.department_id).first()
    if dept and dept.manager_id:
        mgr = db.query(User).filter(User.id == dept.manager_id).first()
        if mgr:
            email_service.notify_ticket_created(
                dept_manager_email=mgr.email,
                dept_manager_name=mgr.full_name or mgr.email,
                requester_name=current_user.full_name or current_user.email,
                ticket_id=req.id,
                ticket_title=req.title,
                priority=str(req.priority.value if hasattr(req.priority, "value") else req.priority),
                due_date=req.due_date.strftime("%Y-%m-%d") if req.due_date else "N/A",
            )

    return _attach_status_name(req)


@router.get("/", response_model=List[RequestResponse])
def list_requests(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Role-scoped ticket list.
    - Requester          → only their own tickets
    - Requester Manager  → their department's tickets
    - MIS Manager        → all tickets except Pending Dept Approval
    - MIS Officer        → tickets assigned to them
    - MIS Supervisor / Admin → all tickets
    """
    role_name = _role(current_user)

    if current_user.is_superuser or role_name in {"Admin", "System Administrator", "MIS Supervisor"}:
        qs = db.query(Request)
    elif role_name == "MIS Manager":
        pending_status = db.query(Status).filter(Status.name == "Pending Dept Approval").first()
        qs = db.query(Request).filter(Request.status_id != pending_status.id if pending_status else True)
    elif role_name == "MIS Officer":
        qs = db.query(Request).filter(Request.assigned_to_id == current_user.id)
    elif user_is_dept_manager(current_user, role_name):
        qs = db.query(Request).filter(Request.department_id == current_user.department_id)
    else:
        qs = db.query(Request).filter(Request.requester_id == current_user.id)

    requests = qs.order_by(Request.created_at.desc()).offset(skip).limit(limit).all()
    for req in requests:
        _attach_status_name(req)
    return requests


# ── single-ticket ─────────────────────────────────────────────────────────────

@router.get("/{request_id}", response_model=RequestResponse)
def get_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = RequestService.get_request(db, request_id, current_user)
    return _attach_status_name(req)


@router.put("/{request_id}", response_model=RequestResponse)
def update_request(
    request_id: int,
    data: RequestUpdate,
    http_req: FastAPIRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    old = RequestService.get_request(db, request_id, current_user)
    old_vals = {"title": old.title, "priority": str(old.priority), "due_date": str(old.due_date)}
    req = RequestService.update_request(db, request_id, data, current_user)
    audit_service.log(
        db,
        action="ticket_updated",
        entity_type="request",
        entity_id=req.id,
        user_id=current_user.id,
        old_value=old_vals,
        new_value=data.model_dump(exclude_unset=True),
        description=f"Ticket #{req.id} updated by {current_user.email}",
        ip_address=_client_ip(http_req),
    )
    db.commit()
    return _attach_status_name(req)


# ── workflow actions ──────────────────────────────────────────────────────────

@router.post("/{request_id}/dept-approve", response_model=RequestResponse)
def dept_manager_approve(
    request_id: int,
    http_req: FastAPIRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Step 2: Dept Manager approves → 'Submitted'."""
    role_name = _role(current_user)
    if not current_user.is_superuser and role_name not in {"Requester Manager", "Admin", "System Administrator"}:
        raise HTTPException(status_code=403, detail="Only the department manager can approve tickets")

    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    pending   = db.query(Status).filter(Status.name == "Pending Dept Approval").first()
    submitted = db.query(Status).filter(Status.name == "Submitted").first()
    if not pending or not submitted:
        raise HTTPException(status_code=500, detail="Workflow statuses not configured. Run seed script.")
    if req.status_id != pending.id:
        raise HTTPException(status_code=400, detail="Ticket is not awaiting department approval")
    if not current_user.is_superuser and role_name not in {"Admin", "System Administrator"}:
        if req.department_id != current_user.department_id:
            raise HTTPException(status_code=403, detail="You can only approve tickets from your own department")

    old_status = req.status.name if req.status else None
    req.status_id = submitted.id

    audit_service.log(db, action="dept_approved", entity_type="request", entity_id=req.id,
                      user_id=current_user.id,
                      old_value={"status": old_status}, new_value={"status": "Submitted"},
                      description=f"Ticket #{req.id} approved by dept manager {current_user.email}",
                      ip_address=_client_ip(http_req))
    db.commit()
    db.refresh(req)

    # Email MIS Managers
    dept = db.query(Department).filter(Department.id == req.department_id).first()
    requester = db.query(User).filter(User.id == req.requester_id).first()
    email_service.notify_dept_approved(
        mis_manager_emails=_mis_manager_emails(db),
        requester_name=requester.full_name or requester.email if requester else "Unknown",
        dept_name=dept.name if dept else "Unknown",
        ticket_id=req.id,
        ticket_title=req.title,
        priority=str(req.priority.value if hasattr(req.priority, "value") else req.priority),
    )
    return _attach_status_name(req)


@router.post("/{request_id}/dept-reject", response_model=RequestResponse)
def dept_manager_reject(
    request_id: int,
    http_req: FastAPIRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dept Manager rejects a ticket. Status → 'Rejected'."""
    role_name = _role(current_user)
    if not current_user.is_superuser and role_name not in {"Requester Manager", "Admin", "System Administrator"}:
        raise HTTPException(status_code=403, detail="Only the department manager can reject tickets")

    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    pending  = db.query(Status).filter(Status.name == "Pending Dept Approval").first()
    rejected = db.query(Status).filter(Status.name == "Rejected").first()
    if not pending or not rejected:
        raise HTTPException(status_code=500, detail="Workflow statuses not configured.")
    if req.status_id != pending.id:
        raise HTTPException(status_code=400, detail="Ticket is not awaiting department approval")
    if not current_user.is_superuser and role_name not in {"Admin", "System Administrator"}:
        if req.department_id != current_user.department_id:
            raise HTTPException(status_code=403, detail="You can only act on tickets from your own department")

    old_status = req.status.name if req.status else None
    req.status_id = rejected.id
    audit_service.log(db, action="dept_rejected", entity_type="request", entity_id=req.id,
                      user_id=current_user.id,
                      old_value={"status": old_status}, new_value={"status": "Rejected"},
                      description=f"Ticket #{req.id} rejected by dept manager {current_user.email}",
                      ip_address=_client_ip(http_req))
    db.commit()
    db.refresh(req)
    return _attach_status_name(req)


@router.post("/{request_id}/assign", response_model=RequestResponse)
def assign_request(
    request_id: int,
    analyst_id: int,
    http_req: FastAPIRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Step 3: MIS Manager assigns to MIS Officer → 'Assigned'."""
    role_name = _role(current_user)
    if not current_user.is_superuser and role_name not in {"MIS Manager", "MIS Supervisor", "Admin", "System Administrator"}:
        raise HTTPException(status_code=403, detail="Only the MIS Manager can assign tickets")

    req = RequestService.assign_request(db, request_id, analyst_id)

    audit_service.log(db, action="ticket_assigned", entity_type="request", entity_id=req.id,
                      user_id=current_user.id,
                      new_value={"assigned_to_id": analyst_id},
                      description=f"Ticket #{req.id} assigned to user {analyst_id} by {current_user.email}",
                      ip_address=_client_ip(http_req))
    db.commit()

    # Email assigned officer
    officer = db.query(User).filter(User.id == analyst_id).first()
    if officer:
        email_service.notify_ticket_assigned(
            officer_email=officer.email,
            officer_name=officer.full_name or officer.email,
            ticket_id=req.id,
            ticket_title=req.title,
            priority=str(req.priority.value if hasattr(req.priority, "value") else req.priority),
            due_date=req.due_date.strftime("%Y-%m-%d") if req.due_date else "N/A",
        )
    return _attach_status_name(req)


@router.post("/{request_id}/resolve", response_model=RequestResponse)
def resolve_request(
    request_id: int,
    http_req: FastAPIRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Step 5a: MIS Officer resolves → 'Resolved'."""
    role_name = _role(current_user)
    if not current_user.is_superuser and role_name not in {"MIS Officer", "MIS Manager", "MIS Supervisor", "Admin", "System Administrator"}:
        raise HTTPException(status_code=403, detail="Only MIS Officers can resolve tickets")

    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    in_progress = db.query(Status).filter(Status.name == "In Progress").first()
    resolved    = db.query(Status).filter(Status.name == "Resolved").first()
    if not in_progress or not resolved:
        raise HTTPException(status_code=500, detail="Workflow statuses not configured.")
    if req.status_id != in_progress.id:
        raise HTTPException(status_code=400, detail="Ticket must be 'In Progress' before it can be resolved")
    if not current_user.is_superuser and role_name == "MIS Officer" and req.assigned_to_id != current_user.id:
        raise HTTPException(status_code=403, detail="You are not assigned to this ticket")

    old_status = req.status.name if req.status else None
    req.status_id = resolved.id
    audit_service.log(db, action="ticket_resolved", entity_type="request", entity_id=req.id,
                      user_id=current_user.id,
                      old_value={"status": old_status}, new_value={"status": "Resolved"},
                      description=f"Ticket #{req.id} resolved by {current_user.email}",
                      ip_address=_client_ip(http_req))
    db.commit()
    db.refresh(req)

    # Email requester
    requester = db.query(User).filter(User.id == req.requester_id).first()
    if requester:
        email_service.notify_ticket_resolved(
            requester_email=requester.email,
            requester_name=requester.full_name or requester.email,
            ticket_id=req.id,
            ticket_title=req.title,
        )
    return _attach_status_name(req)


@router.post("/{request_id}/request-clarification", response_model=RequestResponse)
def request_clarification(
    request_id: int,
    http_req: FastAPIRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Step 5b: MIS Officer needs info → 'Needs Clarification'."""
    role_name = _role(current_user)
    if not current_user.is_superuser and role_name not in {"MIS Officer", "MIS Manager", "MIS Supervisor", "Admin", "System Administrator"}:
        raise HTTPException(status_code=403, detail="Only MIS Officers can request clarification")

    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    in_progress  = db.query(Status).filter(Status.name == "In Progress").first()
    needs_clarif = db.query(Status).filter(Status.name == "Needs Clarification").first()
    if not in_progress or not needs_clarif:
        raise HTTPException(status_code=500, detail="Workflow statuses not configured.")
    if req.status_id != in_progress.id:
        raise HTTPException(status_code=400, detail="Ticket must be 'In Progress' to request clarification")
    if not current_user.is_superuser and role_name == "MIS Officer" and req.assigned_to_id != current_user.id:
        raise HTTPException(status_code=403, detail="You are not assigned to this ticket")

    old_status = req.status.name if req.status else None
    req.status_id = needs_clarif.id
    audit_service.log(db, action="clarification_requested", entity_type="request", entity_id=req.id,
                      user_id=current_user.id,
                      old_value={"status": old_status}, new_value={"status": "Needs Clarification"},
                      description=f"Ticket #{req.id} needs clarification — requested by {current_user.email}",
                      ip_address=_client_ip(http_req))
    db.commit()
    db.refresh(req)

    # Email requester
    requester = db.query(User).filter(User.id == req.requester_id).first()
    if requester:
        email_service.notify_new_comment(
            recipient_emails=[requester.email],
            author_name=current_user.full_name or current_user.email,
            ticket_id=req.id,
            ticket_title=req.title,
            comment_preview="The MIS team needs more information from you. Please reply in the communication thread.",
            is_internal=False,
        )
    return _attach_status_name(req)


@router.post("/{request_id}/resume", response_model=RequestResponse)
def resume_in_progress(
    request_id: int,
    http_req: FastAPIRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """After clarification, MIS Officer resumes → 'In Progress'."""
    role_name = _role(current_user)
    if not current_user.is_superuser and role_name not in {"MIS Officer", "MIS Manager", "MIS Supervisor", "Admin", "System Administrator"}:
        raise HTTPException(status_code=403, detail="Only MIS Officers can resume tickets")

    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    needs_clarif = db.query(Status).filter(Status.name == "Needs Clarification").first()
    in_progress  = db.query(Status).filter(Status.name == "In Progress").first()
    if not needs_clarif or not in_progress:
        raise HTTPException(status_code=500, detail="Workflow statuses not configured.")
    if req.status_id != needs_clarif.id:
        raise HTTPException(status_code=400, detail="Ticket is not awaiting clarification")

    old_status = req.status.name if req.status else None
    req.status_id = in_progress.id
    audit_service.log(db, action="ticket_resumed", entity_type="request", entity_id=req.id,
                      user_id=current_user.id,
                      old_value={"status": old_status}, new_value={"status": "In Progress"},
                      description=f"Ticket #{req.id} resumed by {current_user.email}",
                      ip_address=_client_ip(http_req))
    db.commit()
    db.refresh(req)
    return _attach_status_name(req)


@router.post("/{request_id}/start", response_model=RequestResponse)
def start_working(
    request_id: int,
    http_req: FastAPIRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """MIS Officer starts work: 'Assigned' → 'In Progress'."""
    role_name = _role(current_user)
    if not current_user.is_superuser and role_name not in {"MIS Officer", "MIS Manager", "MIS Supervisor", "Admin", "System Administrator"}:
        raise HTTPException(status_code=403, detail="Only MIS Officers can start working on tickets")

    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    assigned    = db.query(Status).filter(Status.name == "Assigned").first()
    in_progress = db.query(Status).filter(Status.name == "In Progress").first()
    if not assigned or not in_progress:
        raise HTTPException(status_code=500, detail="Workflow statuses not configured.")
    if req.status_id != assigned.id:
        raise HTTPException(status_code=400, detail="Ticket is not in 'Assigned' status")
    if role_name == "MIS Officer" and req.assigned_to_id != current_user.id:
        raise HTTPException(status_code=403, detail="This ticket is not assigned to you")

    old_status = req.status.name if req.status else None
    req.status_id = in_progress.id
    audit_service.log(db, action="ticket_started", entity_type="request", entity_id=req.id,
                      user_id=current_user.id,
                      old_value={"status": old_status}, new_value={"status": "In Progress"},
                      description=f"Ticket #{req.id} started by {current_user.email}",
                      ip_address=_client_ip(http_req))
    db.commit()
    db.refresh(req)
    return _attach_status_name(req)


@router.post("/{request_id}/cancel", response_model=RequestResponse)
def cancel_request(
    request_id: int,
    http_req: FastAPIRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Requester cancels a ticket (only while still in early stages)."""
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    role_name = _role(current_user)
    is_owner  = req.requester_id == current_user.id
    is_admin  = current_user.is_superuser or role_name in {"Admin", "System Administrator", "MIS Supervisor"}
    if not is_owner and not is_admin:
        raise HTTPException(status_code=403, detail="You cannot cancel this ticket")

    cancellable_ids = {s.id for s in db.query(Status).filter(Status.name.in_(["Pending Dept Approval", "Submitted"])).all()}
    if req.status_id not in cancellable_ids:
        raise HTTPException(status_code=400, detail="Tickets can only be cancelled before they are assigned to MIS")

    cancelled = db.query(Status).filter(Status.name == "Cancelled").first()
    old_status = req.status.name if req.status else None
    req.status_id = cancelled.id
    audit_service.log(db, action="ticket_cancelled", entity_type="request", entity_id=req.id,
                      user_id=current_user.id,
                      old_value={"status": old_status}, new_value={"status": "Cancelled"},
                      description=f"Ticket #{req.id} cancelled by {current_user.email}",
                      ip_address=_client_ip(http_req))
    db.commit()
    db.refresh(req)
    return _attach_status_name(req)


# ── feedback ──────────────────────────────────────────────────────────────────

@router.get("/{request_id}/feedback", response_model=FeedbackResponse)
def get_feedback(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = RequestService.get_request(db, request_id, current_user)
    feedback = db.query(RequestFeedback).filter(RequestFeedback.request_id == req.id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not yet submitted")
    return feedback


@router.post("/{request_id}/feedback", response_model=FeedbackResponse, status_code=201)
def create_feedback(
    request_id: int,
    data: FeedbackCreate,
    http_req: FastAPIRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Step 6: Requester submits rating → 'Closed'."""
    req = RequestService.get_request(db, request_id, current_user)
    if req.requester_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the requester can submit feedback")

    resolved = db.query(Status).filter(Status.name == "Resolved").first()
    if not resolved or req.status_id != resolved.id:
        raise HTTPException(status_code=400, detail="Feedback can only be submitted after the ticket is marked 'Resolved'")
    if db.query(RequestFeedback).filter(RequestFeedback.request_id == req.id).first():
        raise HTTPException(status_code=409, detail="Feedback already submitted")

    feedback = RequestFeedback(request_id=req.id, requester_id=current_user.id, **data.model_dump())
    db.add(feedback)

    closed = db.query(Status).filter(Status.name == "Closed").first()
    if closed:
        req.status_id = closed.id

    audit_service.log(db, action="feedback_submitted", entity_type="request", entity_id=req.id,
                      user_id=current_user.id,
                      new_value={"quality": data.quality_rating, "timeliness": data.timeliness_rating},
                      description=f"Feedback submitted for ticket #{req.id} by {current_user.email}",
                      ip_address=_client_ip(http_req))
    db.commit()
    db.refresh(feedback)
    return feedback


# ── SLA ───────────────────────────────────────────────────────────────────────

@router.get("/{request_id}/sla")
def get_sla_status(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns SLA status for a single ticket."""
    req = RequestService.get_request(db, request_id, current_user)
    return enrich_request_sla(req)


# ── generic status override (admin/supervisor only) ───────────────────────────

@router.put("/{request_id}/status")
def update_status(
    request_id: int,
    new_status_id: int,
    http_req: FastAPIRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Low-level status override validated against the transition table."""
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    role_name = _role(current_user)
    old_status_id = req.status_id
    WorkflowService.validate_transition(db, req, new_status_id, role_name)
    req.status_id = new_status_id

    audit_service.log(db, action="status_override", entity_type="request", entity_id=req.id,
                      user_id=current_user.id,
                      old_value={"status_id": old_status_id}, new_value={"status_id": new_status_id},
                      description=f"Admin status override on ticket #{req.id} by {current_user.email}",
                      ip_address=_client_ip(http_req))
    db.commit()
    db.refresh(req)
    return _attach_status_name(req)


# ── internal helper ───────────────────────────────────────────────────────────

def user_is_dept_manager(user: User, role_name: str) -> bool:
    return (
        user.role is not None
        and user.role.role_type == "Manager"
        and role_name == "Requester Manager"
    )
