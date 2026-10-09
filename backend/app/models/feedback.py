from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..core.database import Base


class RequestFeedback(Base):
    __tablename__ = "request_feedback"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("requests.id"), nullable=False, unique=True)
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    quality_rating = Column(Integer, nullable=False)
    timeliness_rating = Column(Integer, nullable=False)
    comment = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    request = relationship("Request")
    requester = relationship("User")