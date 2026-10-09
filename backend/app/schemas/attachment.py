from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class AttachmentResponse(BaseModel):
    id: int
    request_id: int
    file_name: str
    file_size: Optional[int]
    mime_type: Optional[str]
    version: int
    is_final: bool
    uploaded_by_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True

class AttachmentUploadResponse(BaseModel):
    id: int
    request_id: int
    file_name: str
    version: int
    message: str
