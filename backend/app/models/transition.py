from sqlalchemy import Column, Integer, ForeignKey, String
from ..core.database import Base

class Transition(Base):
    __tablename__ = "transitions"
    id = Column(Integer, primary_key=True, index=True)
    from_status_id = Column(Integer, ForeignKey("statuses.id"))
    to_status_id = Column(Integer, ForeignKey("statuses.id"))
    allowed_roles = Column(String, default="")
