from sqlalchemy import Column, Integer, String, JSON
from sqlalchemy.orm import relationship
from ..core.database import Base

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    role_type = Column(String, nullable=False, default="Officer")
    permissions = Column(JSON, default=list)

    users = relationship("User", back_populates="role")
