from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=True)   # nullable for system events
    action      = Column(String, nullable=False, index=True)               # e.g. "status_change", "login"
    entity_type = Column(String, nullable=False, index=True)               # e.g. "request", "user"
    entity_id   = Column(Integer, nullable=True, index=True)
    old_value   = Column(JSON, nullable=True)
    new_value   = Column(JSON, nullable=True)
    ip_address  = Column(String, nullable=True)
    description = Column(Text, nullable=True)                              # human-readable summary
    created_at  = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", foreign_keys=[user_id])
