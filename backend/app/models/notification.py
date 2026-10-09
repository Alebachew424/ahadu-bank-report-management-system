from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..core.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    request_id = Column(Integer, ForeignKey("requests.id"), nullable=True, index=True)
    subject    = Column(String, nullable=False)
    body       = Column(Text, nullable=False)
    is_read    = Column(Boolean, default=False, nullable=False)
    sent_at    = Column(DateTime(timezone=True), server_default=func.now())

    user    = relationship("User")
    request = relationship("Request")
