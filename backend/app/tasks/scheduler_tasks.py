"""
Celery tasks — recurring schedule sweep and SLA escalation.
"""
import logging

logger = logging.getLogger(__name__)


def get_celery():
    """Lazy import to avoid circular imports."""
    from app.celery_app import celery_app
    return celery_app


celery_app = get_celery()


@celery_app.task(
    name        = "app.tasks.process_due_schedules",
    bind        = True,
    max_retries = 3,
    default_retry_delay = 30,
)
def process_due_schedules(self) -> dict:
    """
    Called by Celery beat every minute.
    Finds all active recurring schedules whose next_run_at has passed and fires them.
    """
    from app.core.database import SessionLocal
    from app.services.schedule_service import process_due_schedules as _sweep
    db = SessionLocal()
    try:
        count = _sweep(db)
        if count:
            logger.info("process_due_schedules: created %d ticket(s)", count)
        return {"tickets_created": count}
    except Exception as exc:
        db.rollback()
        logger.error("process_due_schedules failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(
    name        = "app.tasks.run_sla_escalation",
    bind        = True,
    max_retries = 3,
    default_retry_delay = 60,
)
def run_sla_escalation(self) -> dict:
    """
    Called by Celery beat every hour.
    Checks for SLA breaches, bumps priority, and emails supervisors.
    """
    from app.core.database import SessionLocal
    from app.services.sla_service import run_sla_escalation as _escalate
    db = SessionLocal()
    try:
        count = _escalate(db)
        if count:
            logger.info("run_sla_escalation: escalated %d ticket(s)", count)
        return {"escalated": count}
    except Exception as exc:
        db.rollback()
        logger.error("run_sla_escalation failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)
    finally:
        db.close()
