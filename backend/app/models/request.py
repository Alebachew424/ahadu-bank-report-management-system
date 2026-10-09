from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Enum, Boolean, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..core.database import Base
import enum

class PriorityEnum(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class Request(Base):
    __tablename__ = "requests"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    request_type_id = Column(Integer, ForeignKey("request_types.id"))
    status_id = Column(Integer, ForeignKey("statuses.id"))
    priority = Column(Enum(PriorityEnum), default=PriorityEnum.MEDIUM)
    due_date = Column(DateTime(timezone=True))
    additional_data = Column(JSON, default={})

    requester_id = Column(Integer, ForeignKey("users.id"))
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # SLA tracking
    sla_deadline = Column(DateTime(timezone=True), nullable=True)
    sla_breached = Column(Boolean, default=False, nullable=False)
    escalated_at = Column(DateTime(timezone=True), nullable=True)

    # AI / ML fields
    ai_suggested_type_id    = Column(Integer, ForeignKey("request_types.id"), nullable=True)
    ai_type_confidence      = Column(Float,   nullable=True)   # 0.0–1.0
    ai_suggested_officer_id = Column(Integer, ForeignKey("users.id"),         nullable=True)
    ai_officer_score        = Column(Float,   nullable=True)   # composite score
    ai_anomaly_flagged      = Column(Boolean, default=False,   nullable=False)
    ai_anomaly_details      = Column(JSON,    nullable=True)   # list of anomaly dicts

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    requester = relationship("User", foreign_keys=[requester_id])
    department = relationship("Department")
    assigned_to = relationship("User", foreign_keys=[assigned_to_id])
    request_type = relationship("RequestType", foreign_keys=[request_type_id])
    ai_suggested_type    = relationship("RequestType", foreign_keys=[ai_suggested_type_id])
    ai_suggested_officer = relationship("User",        foreign_keys=[ai_suggested_officer_id])
    status = relationship("Status")
    attachments = relationship("Attachment", back_populates="request", cascade="all, delete-orphan")
