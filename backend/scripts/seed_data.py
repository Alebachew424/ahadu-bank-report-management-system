import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text

from app.core.database import Base, SessionLocal, engine
from app import models
from app.models.role import Role
from app.models.status import Status
from app.models.transition import Transition
from app.models.request_type import RequestType
from app.models.department import Department

Base.metadata.create_all(bind=engine)
inspector = inspect(engine)
if engine.url.get_backend_name() == "sqlite":
    with engine.begin() as connection:
        for table, column, definition in (
            ("users", "department_id", "INTEGER"),
            ("requests", "department_id", "INTEGER"),
            ("roles", "role_type", "VARCHAR DEFAULT 'Officer'"),
        ):
            if table in inspector.get_table_names() and column not in {
                item["name"] for item in inspector.get_columns(table)
            }:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))

db = SessionLocal()

# ── Departments ────────────────────────────────────────────────────────────────
for department_name in ["Finance", "Digital", "Loan Credit Appraisal", "Districts", "Retail", "Branch", "IBD"]:
    if not db.query(Department).filter(Department.name == department_name).first():
        db.add(Department(name=department_name))

# ── Roles ──────────────────────────────────────────────────────────────────────
# role_type:  "Manager" = dept manager / MIS manager / supervisor
#             "Officer" = regular business user or MIS analyst
roles = [
    # Business-side roles
    ("Requester",         ["request:create", "request:view_own", "request:comment",
                           "report:download", "report:export", "feedback:create"],   "Officer"),
    ("Requester Manager", ["request:view_dept", "request:approve"],                  "Manager"),
    # MIS-side roles
    ("MIS Manager",       ["request:view_all", "request:assign", "request:process",
                           "request:comment", "request:internal_note",
                           "request:upload", "report:download", "report:export"],    "Manager"),
    ("MIS Officer",       ["request:view_assigned", "request:process",
                           "request:comment", "request:upload",
                           "request:resolve", "request:clarify"],                    "Officer"),
    ("MIS Supervisor",    ["request:view_all", "request:assign", "request:review",
                           "request:approve", "request:internal_note"],              "Manager"),
    ("Admin",             ["*"],                                                     "Manager"),
]
for name, perms, rtype in roles:
    role = db.query(Role).filter(Role.name == name).first()
    if not role:
        db.add(Role(name=name, permissions=perms, role_type=rtype))
    else:
        role.permissions = perms
        role.role_type = rtype

db.flush()

# ── Statuses ───────────────────────────────────────────────────────────────────
# Exact lifecycle statuses that match the described workflow
status_defs = [
    # name,                  is_final
    ("Pending Dept Approval", False),   # just created — waiting for dept manager
    ("Submitted",             False),   # dept manager approved → visible to MIS
    ("Assigned",              False),   # MIS Manager assigned to MIS Officer
    ("In Progress",           False),   # MIS Officer actively working
    ("Needs Clarification",   False),   # MIS Officer asked for more info
    ("Resolved",              False),   # MIS Officer marked as done — awaiting feedback
    ("Closed",                True),    # Requester submitted feedback
    ("Rejected",              True),    # Dept manager or MIS rejected
    ("Cancelled",             True),    # Requester cancelled
]
for name, is_final in status_defs:
    s = db.query(Status).filter(Status.name == name).first()
    if not s:
        db.add(Status(name=name, is_final=is_final, is_active=True))
    else:
        s.is_final = is_final
        s.is_active = True

db.flush()

# ── Request Types ──────────────────────────────────────────────────────────────
for rt_name, rt_desc in [
    ("Daily Transaction Report",  "Daily transaction summary"),
    ("Monthly Performance Report","Monthly KPI and performance summary"),
    ("Loan Portfolio Report",     "Loan portfolio analysis and metrics"),
    ("Branch Summary Report",     "Branch-level activity summary"),
    ("Custom Data Extract",       "Ad-hoc data extraction request"),
]:
    if not db.query(RequestType).filter(RequestType.name == rt_name).first():
        db.add(RequestType(name=rt_name, description=rt_desc, form_schema={}, is_active=True))

db.flush()

# ── Transitions ────────────────────────────────────────────────────────────────
# Build status lookup after flush so IDs are available
statuses = {s.name: s for s in db.query(Status).all()}

transitions = [
    # (from,                    to,                      who_can_do_it)
    # Step 1 → 2: dept manager approves
    ("Pending Dept Approval",  "Submitted",              "Requester Manager,Admin"),
    # Step 1: dept manager rejects
    ("Pending Dept Approval",  "Rejected",               "Requester Manager,Admin"),
    # Step 2 → 3: MIS Manager assigns
    ("Submitted",              "Assigned",               "MIS Manager,MIS Supervisor,Admin"),
    # Step 3 → 4: MIS Officer picks it up / starts working
    ("Assigned",               "In Progress",            "MIS Officer,MIS Manager,MIS Supervisor,Admin"),
    # Step 4 → needs info from requester
    ("In Progress",            "Needs Clarification",    "MIS Officer,MIS Manager,MIS Supervisor,Admin"),
    # Requester responded — back to working
    ("Needs Clarification",    "In Progress",            "Requester,MIS Officer,MIS Manager,MIS Supervisor,Admin"),
    # Step 4 → resolved
    ("In Progress",            "Resolved",               "MIS Officer,MIS Manager,MIS Supervisor,Admin"),
    # Requester submits feedback → closed
    ("Resolved",               "Closed",                 "Requester,Admin"),
    # Requester cancels (only while still in business-side queue or submitted)
    ("Pending Dept Approval",  "Cancelled",              "Requester,Admin"),
    ("Submitted",              "Cancelled",              "Requester,MIS Manager,MIS Supervisor,Admin"),
    # MIS rejects after submission
    ("Submitted",              "Rejected",               "MIS Manager,MIS Supervisor,Admin"),
    # Requester resubmits a rejected ticket
    ("Rejected",               "Pending Dept Approval",  "Requester,Admin"),
]

for from_name, to_name, allowed_roles in transitions:
    from_s = statuses.get(from_name)
    to_s   = statuses.get(to_name)
    if not from_s or not to_s:
        print(f"  ⚠  skipping transition {from_name!r} → {to_name!r}: status not found")
        continue
    existing = db.query(Transition).filter(
        Transition.from_status_id == from_s.id,
        Transition.to_status_id   == to_s.id,
    ).first()
    if not existing:
        db.add(Transition(from_status_id=from_s.id, to_status_id=to_s.id, allowed_roles=allowed_roles))
    else:
        existing.allowed_roles = allowed_roles

db.commit()
db.close()
print("✅  Seed data created / updated successfully")
print()
print("Workflow:")
print("  Officer creates ticket → 'Pending Dept Approval'")
print("  Dept Manager approves  → 'Submitted'  (MIS team can now see it)")
print("  MIS Manager assigns    → 'Assigned'")
print("  MIS Officer works      → 'In Progress'")
print("  MIS Officer resolves   → 'Resolved'   (or 'Needs Clarification')")
print("  Requester gives rating → 'Closed'")
