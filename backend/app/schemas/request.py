from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum

class PriorityEnum(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class RequestCreate(BaseModel):
    title: str
    description: Optional[str] = None
    request_type_id: int
    priority: PriorityEnum = PriorityEnum.MEDIUM
    due_date: datetime
    additional_data: Optional[Dict[str, Any]] = {}

class RequestUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[PriorityEnum] = None
    due_date: Optional[datetime] = None
    additional_data: Optional[Dict[str, Any]] = None

class RequestResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    request_type_id: int
    status_id: int
    status_name: Optional[str] = None
    priority: str
    due_date: datetime
    additional_data: Optional[Dict[str, Any]]
    requester_id: int
    assigned_to_id: Optional[int]
    department_id: Optional[int]
    created_at: datetime
    updated_at: Optional[datetime]

    # SLA fields — None when request type has no SLA configured
    sla_deadline:        Optional[datetime] = None
    sla_breached:        bool               = False
    sla_hours_remaining: Optional[float]    = None   # negative = overdue
    sla_overdue:         bool               = False
    escalated_at:        Optional[datetime] = None

    # AI / ML fields — populated automatically on ticket creation
    ai_suggested_type_id:    Optional[int]   = None
    ai_type_confidence:      Optional[float] = None   # 0.0–1.0
    ai_suggested_officer_id: Optional[int]   = None
    ai_officer_score:        Optional[float] = None
    ai_anomaly_flagged:      bool            = False
    ai_anomaly_details:      Optional[list]  = None

    class Config:
        from_attributes = True
