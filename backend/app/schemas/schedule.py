from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional


class ScheduleCreate(BaseModel):
    title:                str
    description:          Optional[str]  = None
    request_type_id:      int
    priority:             str            = "medium"
    due_in_hours:         int            = 24
    preferred_officer_id: Optional[int] = None
    completion_mode:      str            = "require_feedback"  # or "auto_close"
    frequency:            str            # daily|weekly|biweekly|monthly
    hour:                 int            = 9
    minute:               int            = 0
    day_of_week:          Optional[int]  = None   # 0=Mon … 6=Sun
    day_of_month:         Optional[int]  = None   # 1–28

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        if v not in {"low", "medium", "high", "urgent"}:
            raise ValueError("priority must be low|medium|high|urgent")
        return v

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v: str) -> str:
        if v not in {"daily", "weekly", "biweekly", "monthly"}:
            raise ValueError("frequency must be daily|weekly|biweekly|monthly")
        return v

    @field_validator("completion_mode")
    @classmethod
    def validate_completion_mode(cls, v: str) -> str:
        if v not in {"require_feedback", "auto_close"}:
            raise ValueError("completion_mode must be require_feedback|auto_close")
        return v

    @field_validator("hour")
    @classmethod
    def validate_hour(cls, v: int) -> int:
        if not 0 <= v <= 23:
            raise ValueError("hour must be 0–23")
        return v

    @field_validator("minute")
    @classmethod
    def validate_minute(cls, v: int) -> int:
        if not 0 <= v <= 59:
            raise ValueError("minute must be 0–59")
        return v


class ScheduleUpdate(BaseModel):
    title:                Optional[str] = None
    description:          Optional[str] = None
    priority:             Optional[str] = None
    due_in_hours:         Optional[int] = None
    preferred_officer_id: Optional[int] = None
    completion_mode:      Optional[str] = None
    frequency:            Optional[str] = None
    hour:                 Optional[int] = None
    minute:               Optional[int] = None
    day_of_week:          Optional[int] = None
    day_of_month:         Optional[int] = None


class ScheduleResponse(BaseModel):
    id:                   int
    owner_id:             int
    title:                str
    description:          Optional[str]
    request_type_id:      int
    priority:             str
    due_in_hours:         int
    preferred_officer_id: Optional[int]
    completion_mode:      str
    frequency:            str
    hour:                 int
    minute:               int
    day_of_week:          Optional[int]
    day_of_month:         Optional[int]
    is_active:            bool
    last_fired_at:        Optional[datetime]
    next_run_at:          Optional[datetime]
    total_fired:          int
    created_at:           datetime
    updated_at:           Optional[datetime]

    # Resolved names for display
    request_type_name:      Optional[str] = None
    preferred_officer_name: Optional[str] = None
    owner_name:             Optional[str] = None

    class Config:
        from_attributes = True
