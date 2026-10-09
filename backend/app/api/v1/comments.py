from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request as FastAPIRequest
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.comment import RequestComment
from ...models.request import Request
from ...models.user import User
from ...schemas.comment import CommentCreate, CommentResponse
from ...services import audit_service, email_service

router = APIRouter()

MIS_ROLES         = {"MIS Officer", "MIS Analyst", "MIS Manager", "MIS Supervisor", "Admin", "System Administrator"}
DEPT_MANAGER_ROLES = {"Requester Manager"}


def get_visible_request(db: Session, request_id: int, user: User) -> Request:
    request = db.query(Request).filter(Request.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    role_name = user.role.name if user.role else "Requester"
    allowed = (
        user.is_superuser
        or request.requester_id == user.id
        or request.assigned_to_id == user.id
        or role_name in MIS_ROLES
        or (role_name in DEPT_MANAGER_ROLES and user.department_id == request.department_id)
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="You cannot access this ticket")
    return request


@router.get("/requests/{request_id}/comments", response_model=List[CommentResponse])
def list_comments(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_visible_request(db, request_id, current_user)
    query = db.query(RequestComment).filter(RequestComment.request_id == request_id)
    role_name = current_user.role.name if current_user.role else "Requester"
    if not (current_user.is_superuser or role_name in MIS_ROLES):
        query = query.filter(RequestComment.is_internal.is_(False))
    return query.order_by(RequestComment.created_at).all()


@router.post("/requests/{request_id}/comments", response_model=CommentResponse, status_code=201)
def create_comment(
    request_id: int,
    data: CommentCreate,
    http_req: FastAPIRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = get_visible_request(db, request_id, current_user)

    role_name = current_user.role.name if current_user.role else "Requester"
    if data.is_internal and not (current_user.is_superuser or role_name in MIS_ROLES):
        raise HTTPException(status_code=403, detail="Only MIS staff can post internal notes")

    body = data.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="Comment cannot be empty")

    comment = RequestComment(
        request_id=request_id,
        author_id=current_user.id,
        body=body,
        is_internal=data.is_internal,
    )
    db.add(comment)

    # Audit log
    ip = (http_req.headers.get("X-Forwarded-For") or "").split(",")[0].strip() or (
        http_req.client.host if http_req.client else "unknown"
    )
    audit_service.log(
        db,
        action="comment_added",
        entity_type="request",
        entity_id=request_id,
        user_id=current_user.id,
        new_value={"is_internal": data.is_internal, "preview": body[:100]},
        description=f"{'Internal note' if data.is_internal else 'Comment'} added to ticket #{request_id} by {current_user.email}",
        ip_address=ip,
    )

    db.commit()
    db.refresh(comment)

    # Email notifications (only for public comments)
    if not data.is_internal:
        recipients: list[str] = []
        author_name = current_user.full_name or current_user.email

        # Always notify the requester (unless they're the author)
        requester = db.query(User).filter(User.id == req.requester_id).first()
        if requester and requester.id != current_user.id:
            recipients.append(requester.email)

        # Notify assigned officer if different from author
        if req.assigned_to_id and req.assigned_to_id != current_user.id:
            officer = db.query(User).filter(User.id == req.assigned_to_id).first()
            if officer:
                recipients.append(officer.email)

        if recipients:
            email_service.notify_new_comment(
                recipient_emails=list(set(recipients)),
                author_name=author_name,
                ticket_id=req.id,
                ticket_title=req.title,
                comment_preview=body,
                is_internal=False,
            )
    else:
        # Internal notes: notify MIS Managers only
        from ...models.role import Role as RoleModel
        mgrs = (
            db.query(User)
            .join(RoleModel, User.role_id == RoleModel.id)
            .filter(RoleModel.name.in_(["MIS Manager", "MIS Supervisor"]), User.is_active.is_(True))
            .all()
        )
        mgr_emails = [m.email for m in mgrs if m.id != current_user.id]
        if mgr_emails:
            email_service.notify_new_comment(
                recipient_emails=mgr_emails,
                author_name=current_user.full_name or current_user.email,
                ticket_id=req.id,
                ticket_title=req.title,
                comment_preview=body,
                is_internal=True,
            )

    return comment
