"""
Celery application + beat schedule for the Report Management System.

Workers:
    celery -A app.celery_app worker --loglevel=info

Beat (scheduler):
    celery -A app.celery_app beat --loglevel=info

Both can run together in development:
    celery -A app.celery_app worker --beat --loglevel=info

Requires Redis running on REDIS_URL (see .env).
"""
import os
import sys

# Make sure the backend/ directory is on the path when running from CLI
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

# ── Create Celery app ─────────────────────────────────────────────────────────
celery_app = Celery(
    "rms",
    broker  = settings.REDIS_URL or "redis://localhost:6379/0",
    backend = settings.REDIS_URL or "redis://localhost:6379/0",
    include = ["app.tasks.scheduler_tasks"],
)

celery_app.conf.update(
    task_serializer        = "json",
    result_serializer      = "json",
    accept_content         = ["json"],
    timezone               = "UTC",
    enable_utc             = True,
    task_track_started     = True,
    # Beat schedule
    beat_schedule = {
        # Run the recurring-schedule sweep every minute
        "process-due-schedules": {
            "task":     "app.tasks.process_due_schedules",
            "schedule": crontab(minute="*"),   # every minute
        },
        # SLA escalation sweep every hour (mirrors the asyncio loop in main.py)
        "sla-escalation-sweep": {
            "task":     "app.tasks.run_sla_escalation",
            "schedule": crontab(minute=0),     # top of every hour
        },
    },
)
