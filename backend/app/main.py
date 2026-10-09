import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.v1 import auth, requests, attachments, users, comments, admin, schedules
from .core.database import engine, Base, SessionLocal
from . import models

logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)


# ── Background loops ─────────────────────────────────────────────────────────
async def _sla_escalation_loop() -> None:
    """Runs every hour — checks for SLA breaches and escalates overdue tickets."""
    from .services.sla_service import run_sla_escalation
    while True:
        try:
            db = SessionLocal()
            count = run_sla_escalation(db)
            if count:
                logger.info("SLA sweep: escalated %d ticket(s)", count)
        except Exception as exc:
            logger.error("SLA sweep error: %s", exc, exc_info=True)
        finally:
            try:
                db.close()
            except Exception:
                pass
        await asyncio.sleep(3600)  # run every hour


async def _schedule_sweep_loop() -> None:
    """Runs every 60 seconds — fires any recurring schedules that are due."""
    from .services.schedule_service import process_due_schedules
    while True:
        try:
            db = SessionLocal()
            count = process_due_schedules(db)
            if count:
                logger.info("Schedule sweep: created %d recurring ticket(s)", count)
        except Exception as exc:
            logger.error("Schedule sweep error: %s", exc, exc_info=True)
        finally:
            try:
                db.close()
            except Exception:
                pass
        await asyncio.sleep(60)  # check every minute


@asynccontextmanager
async def lifespan(app: FastAPI):
    sla_task      = asyncio.create_task(_sla_escalation_loop())
    schedule_task = asyncio.create_task(_schedule_sweep_loop())
    logger.info("Background tasks started (SLA sweep: 60 min | Schedule sweep: 1 min)")
    yield
    sla_task.cancel()
    schedule_task.cancel()
    for t in (sla_task, schedule_task):
        try:
            await t
        except asyncio.CancelledError:
            pass


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Report Management System",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,        prefix="/api/v1/auth",       tags=["auth"])
app.include_router(requests.router,    prefix="/api/v1/requests",   tags=["requests"])
app.include_router(attachments.router, prefix="/api/v1/requests",   tags=["attachments"])
app.include_router(users.router,       prefix="/api/v1/users",      tags=["users"])
app.include_router(comments.router,    prefix="/api/v1",            tags=["communications"])
app.include_router(admin.router,       prefix="/api/v1/admin",      tags=["admin"])
app.include_router(schedules.router,   prefix="/api/v1/schedules",  tags=["schedules"])


@app.get("/health")
def health_check():
    return {"status": "ok", "version": "2.0.0"}
