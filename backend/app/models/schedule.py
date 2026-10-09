"""
RecurringSchedule — stores a saved ticket template that fires on a cron-like schedule.

Frequency options:
  daily        — every day at the given hour:minute
  weekly       — every week on day_of_week (0=Mon … 6=Sun) at hour:minute
  monthly      — every month on day_of_month (1–28) at hour:minute
  biweekly     — every two weeks on day_of_week at hour:minute

Auto-completion behaviour:
  require_feedback  — ticket goes through normal workflow; closes only after requester feedback
  auto_close        — ticket is marked Resolved automatically once MIS Officer resolves it
                      (skips the feedback step)
"""
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey,
    Integer, String, Text,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..core.database import Base


class RecurringSchedule(Base):
    __tablename__ = "recurring_schedules"

    id = Column(Integer, primary_key=True, index=True)

    # ── Who owns this schedule ──────────────────────────────────
    owner_id       = Column(Integer, ForeignKey("users.id"), nullable=False)

    # ── Ticket template ─────────────────────────────────────────
    title          = Column(String,  nullable=False)
    description    = Column(Text,    nullable=True)
    request_type_id= Column(Integer, ForeignKey("request_types.id"), nullable=False)
    priority       = Column(String,  nullable=False, default="medium")

    # How many hours after creation should the due_date be set?
    due_in_hours   = Column(Integer, nullable=False, default=24)

    # ── Preferred MIS Officer (optional auto-assign) ────────────
    preferred_officer_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # ── Auto-completion mode ────────────────────────────────────
    # "require_feedback" | "auto_close"
    completion_mode = Column(String, nullable=False, default="require_feedback")

    # ── Schedule definition ─────────────────────────────────────
    # "daily" | "weekly" | "biweekly" | "monthly"
    frequency     = Column(String,  nullable=False)
    hour          = Column(Integer, nullable=False, default=9)   # 0–23
    minute        = Column(Integer, nullable=False, default=0)   # 0–59
    day_of_week   = Column(Integer, nullable=True)               # 0=Mon … 6=Sun  (weekly/biweekly)
    day_of_month  = Column(Integer, nullable=True)               # 1–28           (monthly)

    # ── State ────────────────────────────────────────────────────
    is_active      = Column(Boolean, nullable=False, default=True)    # False = paused
    last_fired_at  = Column(DateTime(timezone=True), nullable=True)
    next_run_at    = Column(DateTime(timezone=True), nullable=True)
    total_fired    = Column(Integer,  nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # ── Relationships ────────────────────────────────────────────
    owner            = relationship("User", foreign_keys=[owner_id])
    preferred_officer= relationship("User", foreign_keys=[preferred_officer_id])
    request_type     = relationship("RequestType")
