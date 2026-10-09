from datetime import datetime

from pydantic import BaseModel


class CommentCreate(BaseModel):
    body: str
    is_internal: bool = False


class CommentResponse(BaseModel):
    id: int
    request_id: int
    author_id: int
    body: str
    is_internal: bool
    created_at: datetime

    class Config:
        from_attributes = True