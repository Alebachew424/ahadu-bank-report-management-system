import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.database import SessionLocal
from app.models.user import User
from app.models.role import Role
from app.models.department import Department

db = SessionLocal()

# Show current dept manager links
depts = db.query(Department).all()
print("Dept ID | Dept Name            | manager_id | manager email")
print("-"*70)
for d in depts:
    mgr = db.query(User).filter(User.id == d.manager_id).first() if d.manager_id else None
    mgr_email = mgr.email if mgr else "(none)"
    print(f"{d.id:<8}| {d.name:<21}| {str(d.manager_id):<11}| {mgr_email}")

print()
# Show all Requester Managers with their dept
managers = db.query(User).join(Role, User.role_id == Role.id).filter(Role.name == "Requester Manager").all()
print("Requester Managers:")
for m in managers:
    print(f"  {m.email:<35} dept_id={m.department_id}")

print()
# Auto-fix: for each Requester Manager with a dept, set them as dept manager_id
fixed = 0
for m in managers:
    if m.department_id:
        dept = db.query(Department).filter(Department.id == m.department_id).first()
        if dept and dept.manager_id != m.id:
            dept.manager_id = m.id
            print(f"  Fixed: dept '{dept.name}' manager_id -> {m.email}")
            fixed += 1

db.commit()
print(f"\n{fixed} department manager link(s) fixed.")
db.close()
