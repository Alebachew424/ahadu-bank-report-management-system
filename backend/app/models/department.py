from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from ..core.database import Base


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    manager_id = Column(Integer, ForeignKey("users.id", use_alter=True, name="fk_department_manager"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    manager = relationship("User", foreign_keys=[manager_id])
    users = relationship("User", foreign_keys="User.department_id", back_populates="department")