from datetime import datetime

from pydantic import BaseModel, Field


class FeedbackCreate(BaseModel):
    quality_rating: int = Field(ge=1, le=5)
    timeliness_rating: int = Field(ge=1, le=5)
    comment: str | None = None


class FeedbackResponse(FeedbackCreate):
    id: int
    request_id: int
    requester_id: int
    created_at: datetime

    class Config:
        from_attributes = True