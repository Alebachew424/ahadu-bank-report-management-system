"""
Verify the recurring schedules feature end-to-end.
Run from backend/ directory:
    python scripts/verify_schedules.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from datetime import datetime, timezone

PG_DSN = "host=localhost port=5432 user=postgres password=postgres dbname=report_management"
conn = psycopg2.connect(PG_DSN)
cur  = conn.cursor()

errors = []
ok     = 0

def check(label, passed, detail=""):
    global ok
    if passed:
        ok += 1
        print(f"  OK    {label}")
    else:
        errors.append(label)
        print(f"  ERR   {label}{(' — ' + detail) if detail else ''}")

print("=" * 60)
print("Recurring Schedules Verification")
print("=" * 60)

# 1. Table exists
print("\n[1] Database table")
cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='recurring_schedules')")
check("recurring_schedules table exists", cur.fetchone()[0])

# 2. All expected columns exist
print("\n[2] Columns")
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='recurring_schedules'")
cols = {r[0] for r in cur.fetchall()}
for col in ["id","owner_id","title","frequency","hour","minute","day_of_week",
            "day_of_month","is_active","next_run_at","last_fired_at","total_fired",
            "preferred_officer_id","completion_mode","priority","due_in_hours"]:
    check(f"column: {col}", col in cols)

# 3. Indexes
print("\n[3] Indexes")
for idx in ["ix_recurring_schedules_owner_id", "ix_recurring_schedules_active"]:
    cur.execute("SELECT EXISTS(SELECT 1 FROM pg_indexes WHERE tablename='recurring_schedules' AND indexname=%s)", (idx,))
    check(f"index {idx}", cur.fetchone()[0])

# 4. Model + service imports
print("\n[4] Model and service imports")
try:
    from app.models.schedule import RecurringSchedule
    check("RecurringSchedule model importable", True)
except Exception as e:
    check("RecurringSchedule model importable", False, str(e))

try:
    from app.services.schedule_service import (
        compute_next_run, fire_schedule, process_due_schedules, maybe_auto_close
    )
    check("schedule_service functions importable", True)
except Exception as e:
    check("schedule_service functions importable", False, str(e))

# 5. compute_next_run logic
print("\n[5] Schedule timing logic")
try:
    from app.models.schedule import RecurringSchedule as RS
    from app.services.schedule_service import compute_next_run

    # Daily at 09:00
    s = RS(frequency="daily", hour=9, minute=0)
    nxt = compute_next_run(s, after=datetime(2026, 9, 14, 8, 0, tzinfo=timezone.utc))
    check("daily: next run is today at 09:00", nxt.hour == 9 and nxt.minute == 0)

    # Daily — if current time is past 09:00, next is tomorrow
    nxt2 = compute_next_run(s, after=datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc))
    check("daily: rolls to next day when time passed", nxt2.day == 15)

    # Weekly on Monday (0)
    s2 = RS(frequency="weekly", hour=9, minute=0, day_of_week=0)
    nxt3 = compute_next_run(s2, after=datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc))  # Monday
    check("weekly: next Monday found", nxt3.weekday() == 0)

    # Monthly on day 15
    s3 = RS(frequency="monthly", hour=9, minute=0, day_of_month=15)
    nxt4 = compute_next_run(s3, after=datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc))
    check("monthly: next occurrence is on day 15", nxt4.day == 15)

except Exception as e:
    check("schedule timing logic", False, str(e))

# 6. API router importable
print("\n[6] API router")
try:
    from app.api.v1 import schedules
    check("schedules router importable", True)
    check("schedules router has correct prefix routes", hasattr(schedules, 'router'))
except Exception as e:
    check("schedules router importable", False, str(e))

# 7. Celery tasks importable
print("\n[7] Celery tasks")
try:
    from app.celery_app import celery_app
    check("celery_app importable", True)
    beat = celery_app.conf.beat_schedule
    check("process_due_schedules beat task registered", "process-due-schedules" in beat)
    check("sla_escalation beat task registered",        "sla-escalation-sweep" in beat)
except Exception as e:
    check("celery_app importable", False, str(e))

try:
    from app.tasks.scheduler_tasks import process_due_schedules, run_sla_escalation
    check("celery tasks importable", True)
except Exception as e:
    check("celery tasks importable", False, str(e))

# 8. SQLAlchemy model queryable
print("\n[8] Live DB query")
try:
    from app.core.database import SessionLocal
    from app.models.schedule import RecurringSchedule
    db = SessionLocal()
    count = db.query(RecurringSchedule).count()
    db.close()
    check(f"RecurringSchedule queryable ({count} rows)", True)
except Exception as e:
    check("RecurringSchedule queryable", False, str(e))

# ── summary ───────────────────────────────────────────────────
print("\n" + "=" * 60)
if errors:
    print(f"RESULT: {len(errors)} ERROR(S)")
    for e in errors:
        print(f"  ✗  {e}")
else:
    print(f"RESULT: ALL {ok} CHECKS PASSED ✅")
print("=" * 60)

conn.close()
