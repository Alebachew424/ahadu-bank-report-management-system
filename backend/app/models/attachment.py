from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Integer
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..core.database import Base

class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("requests.id"), nullable=False)
    file_name = Column(String, nullable=False)          # original filename
    stored_path = Column(String, nullable=False)        # relative path in media/
    file_size = Column(Integer)                         # in bytes
    mime_type = Column(String)
    version = Column(Integer, default=1)                # auto-incremented per request
    is_final = Column(Boolean, default=False)           # mark as final delivered report
    uploaded_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    request = relationship("Request", back_populates="attachments")
    uploader = relationship("User")
