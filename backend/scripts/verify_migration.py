"""
Full verification of the PostgreSQL migration.
Checks: row counts, FK integrity, sequences, key users, app-level DB connection.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2

PG_DSN = "host=localhost port=5432 user=postgres password=postgres dbname=report_management"
conn = psycopg2.connect(PG_DSN)
cur  = conn.cursor()

errors   = []
warnings = []

print("=" * 60)
print("PostgreSQL Migration Verification")
print("=" * 60)

# ── 1. Row counts ─────────────────────────────────────────────
print("\n[1] Row counts")
expected = {
    "roles":            (1,  999),
    "departments":      (1,  999),
    "users":            (1,  999),
    "statuses":         (9,  999),   # at least 9 workflow statuses
    "request_types":    (1,  999),
    "requests":         (0,  999),   # may be 0 in fresh installs
    "transitions":      (12, 999),   # at least 12 transitions defined
    "attachments":      (0,  999),
    "request_comments": (0,  999),
    "request_feedback": (0,  999),
}
for table, (min_rows, max_rows) in expected.items():
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    count = cur.fetchone()[0]
    status = "OK" if min_rows <= count <= max_rows else "WARN"
    if status == "WARN":
        warnings.append(f"{table}: expected >={min_rows} rows, got {count}")
    print(f"  {'OK' if status=='OK' else '⚠ ':>4}  {table:<30} {count} rows")

# ── 2. Critical system roles ──────────────────────────────────
print("\n[2] System roles")
required_roles = ["Requester", "Requester Manager", "MIS Manager", "MIS Officer", "MIS Supervisor", "Admin"]
for role in required_roles:
    cur.execute("SELECT id, role_type FROM roles WHERE name = %s", (role,))
    row = cur.fetchone()
    if row:
        print(f"  OK    {role:<25} id={row[0]}  type={row[1]}")
    else:
        errors.append(f"Missing required role: {role}")
        print(f"  ERR   {role} MISSING")

# ── 3. Workflow statuses ──────────────────────────────────────
print("\n[3] Workflow statuses")
required_statuses = [
    "Pending Dept Approval", "Submitted", "Assigned",
    "In Progress", "Needs Clarification", "Resolved",
    "Closed", "Rejected", "Cancelled"
]
for name in required_statuses:
    cur.execute("SELECT id, is_final FROM statuses WHERE name = %s", (name,))
    row = cur.fetchone()
    if row:
        print(f"  OK    {name:<30} id={row[0]}  is_final={row[1]}")
    else:
        errors.append(f"Missing status: {name}")
        print(f"  ERR   {name} MISSING")

# ── 4. Key test users ─────────────────────────────────────────
print("\n[4] Test users")
test_users = [
    "officer@test.com",
    "deptmgr@test.com",
    "mismgr@test.com",
    "misofficer@test.com",
]
for email in test_users:
    cur.execute("""
        SELECT u.email, r.name, u.department_id, u.is_active
        FROM users u
        LEFT JOIN roles r ON u.role_id = r.id
        WHERE u.email = %s
    """, (email,))
    row = cur.fetchone()
    if row:
        dept_ok = "dept=OK" if row[2] is not None or "MIS" in (row[1] or "") else "dept=MISSING"
        print(f"  OK    {row[0]:<35} role={row[1]:<22} {dept_ok}  active={row[3]}")
        if "MIS" not in (row[1] or "") and row[2] is None:
            warnings.append(f"{email} has no department_id")
    else:
        errors.append(f"Missing test user: {email}")
        print(f"  ERR   {email} MISSING")

# ── 5. Department → manager links ─────────────────────────────
print("\n[5] Department manager links")
cur.execute("""
    SELECT d.name, d.manager_id, u.email
    FROM departments d
    LEFT JOIN users u ON d.manager_id = u.id
    WHERE d.is_active = TRUE
    ORDER BY d.name
""")
for dept_name, mgr_id, mgr_email in cur.fetchall():
    if mgr_id:
        print(f"  OK    {dept_name:<25} manager={mgr_email}")
    else:
        print(f"  --    {dept_name:<25} (no manager set)")

# ── 6. Sequence values ────────────────────────────────────────
print("\n[6] Sequences (next value should be > max id)")
seq_tables = ["roles", "departments", "users", "statuses",
              "request_types", "requests", "transitions",
              "attachments", "request_comments", "request_feedback"]
for table in seq_tables:
    cur.execute(f"SELECT MAX(id) FROM {table}")
    max_id = cur.fetchone()[0] or 0
    cur.execute(f"SELECT last_value FROM {table}_id_seq")
    seq_val = cur.fetchone()[0]
    ok = seq_val >= max_id
    mark = "OK" if ok else "ERR"
    if not ok:
        errors.append(f"{table}_id_seq ({seq_val}) < max id ({max_id})")
    print(f"  {mark}    {table:<30} max_id={max_id}  seq={seq_val}")

# ── 7. FK integrity spot-check ────────────────────────────────
print("\n[7] FK integrity checks")

checks = [
    ("users with invalid role_id",
     "SELECT COUNT(*) FROM users u LEFT JOIN roles r ON u.role_id = r.id WHERE u.role_id IS NOT NULL AND r.id IS NULL"),
    ("users with invalid department_id",
     "SELECT COUNT(*) FROM users u LEFT JOIN departments d ON u.department_id = d.id WHERE u.department_id IS NOT NULL AND d.id IS NULL"),
    ("requests with invalid requester_id",
     "SELECT COUNT(*) FROM requests r LEFT JOIN users u ON r.requester_id = u.id WHERE u.id IS NULL"),
    ("requests with invalid status_id",
     "SELECT COUNT(*) FROM requests r LEFT JOIN statuses s ON r.status_id = s.id WHERE s.id IS NULL"),
    ("attachments with invalid request_id",
     "SELECT COUNT(*) FROM attachments a LEFT JOIN requests r ON a.request_id = r.id WHERE r.id IS NULL"),
    ("comments with invalid request_id",
     "SELECT COUNT(*) FROM request_comments c LEFT JOIN requests r ON c.request_id = r.id WHERE r.id IS NULL"),
]
for label, sql in checks:
    cur.execute(sql)
    count = cur.fetchone()[0]
    mark = "OK" if count == 0 else "ERR"
    if count > 0:
        errors.append(f"FK violation: {label} ({count})")
    print(f"  {mark}    {label}: {count} violations")

# ── 8. Live app connection via SQLAlchemy ─────────────────────
print("\n[8] App-level SQLAlchemy connection")
try:
    from app.core.database import SessionLocal
    from app.models.user import User
    db = SessionLocal()
    user_count = db.query(User).count()
    db.close()
    print(f"  OK    SQLAlchemy connected — {user_count} users visible")
except Exception as e:
    errors.append(f"SQLAlchemy connection failed: {e}")
    print(f"  ERR   {e}")

# ── Summary ───────────────────────────────────────────────────
print("\n" + "=" * 60)
if errors:
    print(f"RESULT: {len(errors)} ERROR(S) FOUND")
    for e in errors:
        print(f"  ✗  {e}")
elif warnings:
    print(f"RESULT: PASSED with {len(warnings)} warning(s)")
    for w in warnings:
        print(f"  ⚠  {w}")
else:
    print("RESULT: ALL CHECKS PASSED ✅")
print("=" * 60)

conn.close()
