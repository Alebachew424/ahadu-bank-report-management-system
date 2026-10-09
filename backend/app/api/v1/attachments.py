from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
import secrets, time

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.attachment import Attachment
from ...models.request import Request
from ...models.user import User
from ...schemas.attachment import AttachmentResponse, AttachmentUploadResponse
from ...services.attachment_service import AttachmentService
from ...utils.file_storage import get_file_path

router = APIRouter()

# Roles that can see any ticket they are linked to
MIS_ROLES = {"MIS Officer", "MIS Analyst", "MIS Manager", "MIS Supervisor", "Admin", "System Administrator"}
# Roles that can see tickets from their own department (dept managers)
DEPT_MANAGER_ROLES = {"Requester Manager"}

# ── short-lived preview tokens ────────────────────────────────────────────────
# { token: { attachment_id, expires_at } }
_preview_tokens: dict = {}
_TOKEN_TTL = 120  # seconds


def _can_access(request: Request, user: User) -> bool:
    role_name = user.role.name if user.role else "Requester"
    return (
        user.is_superuser
        or user.id == request.requester_id
        or user.id == request.assigned_to_id
        or role_name in MIS_ROLES
        or (role_name in DEPT_MANAGER_ROLES and user.department_id == request.department_id)
    )


@router.post("/{request_id}/attachments", response_model=AttachmentUploadResponse, status_code=201)
def upload_attachment(
    request_id: int,
    file: UploadFile = File(...),
    is_final: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    request = db.query(Request).filter(Request.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    role_name = current_user.role.name if current_user.role else "Requester"

    if not _can_access(request, current_user):
        raise HTTPException(status_code=403, detail="Not authorized to upload to this request")

    if is_final and not (current_user.is_superuser or role_name in MIS_ROLES):
        raise HTTPException(status_code=403, detail="Only MIS users can mark a report as final")

    attachment = AttachmentService.upload_attachment(db, request_id, file, current_user.id, is_final)
    return AttachmentUploadResponse(
        id=attachment.id,
        request_id=attachment.request_id,
        file_name=attachment.file_name,
        version=attachment.version,
        message="File uploaded successfully",
    )


@router.get("/{request_id}/attachments", response_model=List[AttachmentResponse])
def list_attachments(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    request = db.query(Request).filter(Request.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    if not _can_access(request, current_user):
        raise HTTPException(status_code=403, detail="Not authorized to view attachments")

    return AttachmentService.get_attachments(db, request_id)


@router.get("/attachments/{attachment_id}/download")
def download_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    request = db.query(Request).filter(Request.id == attachment.request_id).first()
    if not request or not _can_access(request, current_user):
        raise HTTPException(status_code=403, detail="Not authorized to download")

    file_path = get_file_path(attachment.stored_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on server")

    return FileResponse(path=file_path, filename=attachment.file_name)


@router.post("/attachments/{attachment_id}/preview-token")
def issue_preview_token(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Issues a short-lived (120 s) one-time token so the browser can fetch
    the file without an Authorization header — required for Google Docs Viewer
    and Office Online embed iframes.
    """
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    request = db.query(Request).filter(Request.id == attachment.request_id).first()
    if not request or not _can_access(request, current_user):
        raise HTTPException(status_code=403, detail="Not authorized")

    # Purge expired tokens
    now = time.time()
    expired = [t for t, v in _preview_tokens.items() if v["expires_at"] < now]
    for t in expired:
        del _preview_tokens[t]

    token = secrets.token_urlsafe(32)
    _preview_tokens[token] = {"attachment_id": attachment_id, "expires_at": now + _TOKEN_TTL}
    return {"token": token, "expires_in": _TOKEN_TTL}


@router.get("/attachments/preview/{token}")
def preview_by_token(token: str, db: Session = Depends(get_db)):
    """
    Public (no auth) endpoint — serves the file if the token is valid and not expired.
    Used as the URL passed to Google Docs Viewer / Office Online.
    """
    entry = _preview_tokens.get(token)
    if not entry or entry["expires_at"] < time.time():
        raise HTTPException(status_code=410, detail="Preview link expired or invalid")

    attachment = db.query(Attachment).filter(Attachment.id == entry["attachment_id"]).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    file_path = get_file_path(attachment.stored_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on server")

    # Token is single-use
    del _preview_tokens[token]

    return FileResponse(
        path=file_path,
        filename=attachment.file_name,
        headers={"Access-Control-Allow-Origin": "*"},
    )


@router.delete("/attachments/{attachment_id}")
def delete_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    role_name = current_user.role.name if current_user.role else "Requester"
    if not (
        attachment.uploaded_by_id == current_user.id
        or current_user.is_superuser
        or role_name in MIS_ROLES
    ):
        raise HTTPException(status_code=403, detail="Not authorized to delete this attachment")

    return AttachmentService.delete_attachment(db, attachment_id, current_user.id)


@router.put("/attachments/{attachment_id}/final")
def mark_attachment_final(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    role_name = current_user.role.name if current_user.role else "Requester"
    if not current_user.is_superuser and role_name not in MIS_ROLES:
        raise HTTPException(status_code=403, detail="Only MIS users can mark a report as final")

    updated = AttachmentService.mark_as_final(db, attachment_id)
    return {"msg": f"Attachment {updated.id} marked as final"}
