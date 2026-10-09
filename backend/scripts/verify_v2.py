"""
Post-migration verification for v2 features:
  - audit_logs table exists and is writable
  - notifications table exists
  - requests has sla_deadline, sla_breached, escalated_at
  - request_types has sla_hours with seeded values
  - requests.search_vector column exists with GIN index
  - All new API endpoints importable (no import errors)
  - App-level SQLAlchemy connection
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2

PG_DSN = "host=localhost port=5432 user=postgres password=postgres dbname=report_management"
conn = psycopg2.connect(PG_DSN)
cur  = conn.cursor()

errors = []
ok_count = 0

def check(label, passed, detail=""):
    global ok_count
    if passed:
        ok_count += 1
        print(f"  OK    {label}")
    else:
        errors.append(label)
        print(f"  ERR   {label}{(' — ' + detail) if detail else ''}")

print("=" * 60)
print("v2 Migration Verification")
print("=" * 60)

# ── 1. New tables ─────────────────────────────────────────────
print("\n[1] New tables")
for table in ("audit_logs", "notifications"):
    cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s)", (table,))
    check(f"table '{table}' exists", cur.fetchone()[0])

# ── 2. New columns on requests ────────────────────────────────
print("\n[2] New columns on 'requests'")
for col in ("sla_deadline", "sla_breached", "escalated_at"):
    cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='requests' AND column_name=%s)", (col,))
    check(f"requests.{col}", cur.fetchone()[0])

# ── 3. sla_hours on request_types ────────────────────────────
print("\n[3] SLA hours seeded on request_types")
cur.execute("SELECT name, sla_hours FROM request_types WHERE sla_hours IS NOT NULL ORDER BY name")
rows = cur.fetchall()
check("at least one request_type has sla_hours set", len(rows) > 0)
for name, hrs in rows:
    print(f"        {name:<40} sla_hours={hrs}")

# ── 4. search_vector column ───────────────────────────────────
print("\n[4] Full-text search vector")
cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='requests' AND column_name='search_vector')")
check("requests.search_vector column exists", cur.fetchone()[0])
cur.execute("SELECT EXISTS(SELECT 1 FROM pg_indexes WHERE tablename='requests' AND indexname='ix_requests_search_vector')")
check("GIN index on search_vector exists", cur.fetchone()[0])

# ── 5. Audit log write test ───────────────────────────────────
print("\n[5] Audit log write test")
try:
    cur.execute("INSERT INTO audit_logs (action, entity_type, description) VALUES ('verify_test', 'system', 'v2 verification test') RETURNING id")
    log_id = cur.fetchone()[0]
    conn.commit()
    cur.execute("DELETE FROM audit_logs WHERE id = %s", (log_id,))
    conn.commit()
    check("audit_logs insert/delete works", True)
except Exception as e:
    conn.rollback()
    check("audit_logs insert/delete works", False, str(e))

# ── 6. New indexes ────────────────────────────────────────────
print("\n[6] Indexes")
expected_indexes = [
    ("audit_logs",    "ix_audit_logs_action"),
    ("audit_logs",    "ix_audit_logs_entity_type"),
    ("audit_logs",    "ix_audit_logs_created_at"),
    ("notifications", "ix_notifications_user_id"),
]
for table, idx in expected_indexes:
    cur.execute("SELECT EXISTS(SELECT 1 FROM pg_indexes WHERE tablename=%s AND indexname=%s)", (table, idx))
    check(f"index {idx}", cur.fetchone()[0])

# ── 7. App-level SQLAlchemy + new models ─────────────────────
print("\n[7] App-level model imports")
try:
    from app.models.audit_log import AuditLog
    from app.models.notification import Notification
    from app.core.database import SessionLocal
    db = SessionLocal()
    db.query(AuditLog).count()
    db.query(Notification).count()
    db.close()
    check("AuditLog + Notification models queryable via SQLAlchemy", True)
except Exception as e:
    check("AuditLog + Notification models queryable via SQLAlchemy", False, str(e))

# ── 8. New API routers importable ─────────────────────────────
print("\n[8] API router imports")
try:
    from app.api.v1 import admin
    check("admin router importable", True)
except Exception as e:
    check("admin router importable", False, str(e))

try:
    from app.services import audit_service, email_service, sla_service
    check("audit_service, email_service, sla_service importable", True)
except Exception as e:
    check("audit_service, email_service, sla_service importable", False, str(e))

# ── Summary ───────────────────────────────────────────────────
print("\n" + "=" * 60)
if errors:
    print(f"RESULT: {len(errors)} ERROR(S)")
    for e in errors:
        print(f"  ✗  {e}")
else:
    print(f"RESULT: ALL {ok_count} CHECKS PASSED ✅")
print("=" * 60)

conn.close()
