from sqlalchemy.orm import Session
from fastapi import UploadFile, HTTPException, status
from ..models.attachment import Attachment
from ..models.request import Request
from ..utils.file_storage import save_upload_file, delete_file
from ..schemas.attachment import AttachmentResponse

class AttachmentService:
    @staticmethod
    def upload_attachment(
        db: Session,
        request_id: int,
        file: UploadFile,
        user_id: int,
        is_final: bool = False
    ):
        request = db.query(Request).filter(Request.id == request_id).first()
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")

        # Determine next version for this request
        last_attachment = db.query(Attachment).filter(
            Attachment.request_id == request_id
        ).order_by(Attachment.version.desc()).first()
        next_version = (last_attachment.version + 1) if last_attachment else 1

        # Save file
        file_info = save_upload_file(file, request_id, next_version)

        # Create DB record
        attachment = Attachment(
            request_id=request_id,
            file_name=file_info["file_name"],
            stored_path=file_info["stored_path"],
            file_size=file_info["file_size"],
            mime_type=file_info["mime_type"],
            version=next_version,
            is_final=is_final,
            uploaded_by_id=user_id,
        )
        db.add(attachment)
        db.commit()
        db.refresh(attachment)
        return attachment

    @staticmethod
    def get_attachments(db: Session, request_id: int):
        return db.query(Attachment).filter(Attachment.request_id == request_id).order_by(Attachment.version).all()

    @staticmethod
    def delete_attachment(db: Session, attachment_id: int, user_id: int):
        attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
        if not attachment:
            raise HTTPException(status_code=404, detail="Attachment not found")
        # Optionally check permissions
        delete_file(attachment.stored_path)
        db.delete(attachment)
        db.commit()
        return {"msg": "Attachment deleted"}

    @staticmethod
    def mark_as_final(db: Session, attachment_id: int):
        attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
        if not attachment:
            raise HTTPException(status_code=404, detail="Attachment not found")
        attachment.is_final = True
        db.commit()
        db.refresh(attachment)
        return attachment
