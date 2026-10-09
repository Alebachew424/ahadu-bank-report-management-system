from sqlalchemy import Column, Integer, String, JSON, Boolean
from ..core.database import Base

class RequestType(Base):
    __tablename__ = "request_types"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String)
    form_schema = Column(JSON, default={})
    is_active = Column(Boolean, default=True)
    # SLA: working hours before a ticket of this type is considered overdue.
    # None means no SLA enforced. Examples: Standard=72, Urgent=4
    sla_hours = Column(Integer, nullable=True, default=None)
