from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.user import User
from ...schemas.user import DepartmentCreate, DepartmentUpdate, RoleCreate, RoleResponse, UserAdminCreate, UserAdminUpdate, UserResponse
from ...models.role import Role
from ...core.security import get_password_hash
from ...models.department import Department

router = APIRouter()


@router.get("/mis-team")
def list_mis_team(
	db: Session = Depends(get_db),
	current_user: User = Depends(get_current_user),
):
	"""Returns all active MIS Officers and Analysts for assignment dropdown."""
	role_name = current_user.role.name if current_user.role else "Requester"
	if not current_user.is_superuser and role_name not in {
		"MIS Manager", "MIS Supervisor", "Admin", "System Administrator"
	}:
		raise HTTPException(status_code=403, detail="Access denied")

	mis_role_names = ["MIS Officer", "MIS Analyst"]
	users = (
		db.query(User)
		.join(Role, User.role_id == Role.id)
		.filter(Role.name.in_(mis_role_names), User.is_active.is_(True))
		.order_by(User.full_name)
		.all()
	)
	return [
		{
			"id": u.id,
			"full_name": u.full_name,
			"email": u.email,
			"role_name": u.role.name if u.role else None,
		}
		for u in users
	]


@router.get("/performance")
def get_performance_stats(
	db: Session = Depends(get_db),
	current_user: User = Depends(get_current_user),
):
	"""
	Performance dashboard for MIS Managers.
	Returns per-officer ticket stats, dept manager throughput, overall summary, and SLA metrics.
	"""
	role_name = current_user.role.name if current_user.role else "Requester"
	if not current_user.is_superuser and role_name not in {
		"MIS Manager", "MIS Supervisor", "Admin", "System Administrator"
	}:
		raise HTTPException(status_code=403, detail="Access denied")

	from ...models.request import Request
	from ...models.status import Status
	from datetime import datetime, timezone

	all_requests = db.query(Request).all()
	all_users    = db.query(User).join(Role, User.role_id == Role.id).filter(
		Role.name.in_(["MIS Officer", "MIS Analyst", "MIS Manager", "MIS Supervisor"]),
		User.is_active.is_(True),
	).all()

	terminal_statuses = {"Closed", "Resolved", "Rejected", "Cancelled"}
	now = datetime.now(timezone.utc)

	# Per-officer breakdown
	officer_stats = []
	for u in all_users:
		assigned   = [r for r in all_requests if r.assigned_to_id == u.id]
		completed  = [r for r in assigned if r.status and r.status.name in {"Closed", "Resolved"}]
		pending    = [r for r in assigned if r.status and r.status.name not in terminal_statuses]
		in_prog    = [r for r in assigned if r.status and r.status.name == "In Progress"]
		overdue    = [
			r for r in pending
			if r.sla_deadline and (
				r.sla_deadline.replace(tzinfo=timezone.utc) if r.sla_deadline.tzinfo is None else r.sla_deadline
			) < now
		]
		officer_stats.append({
			"id":           u.id,
			"full_name":    u.full_name,
			"email":        u.email,
			"role_name":    u.role.name if u.role else None,
			"total":        len(assigned),
			"completed":    len(completed),
			"pending":      len(pending),
			"in_progress":  len(in_prog),
			"overdue":      len(overdue),
		})

	# Overall summary
	total      = len(all_requests)
	closed     = sum(1 for r in all_requests if r.status and r.status.name in {"Closed", "Resolved"})
	pending    = sum(1 for r in all_requests if r.status and r.status.name not in terminal_statuses)
	unassigned = sum(1 for r in all_requests if not r.assigned_to_id
	                 and r.status and r.status.name not in terminal_statuses
	                 and r.status.name != "Pending Dept Approval")

	# SLA summary
	sla_tracked = [r for r in all_requests if r.sla_deadline is not None]
	sla_active  = [r for r in sla_tracked if r.status and r.status.name not in terminal_statuses]
	sla_overdue = [
		r for r in sla_active
		if (r.sla_deadline.replace(tzinfo=timezone.utc) if r.sla_deadline.tzinfo is None else r.sla_deadline) < now
	]
	sla_breached_total = sum(1 for r in sla_tracked if r.sla_breached)
	sla_on_time = sum(
		1 for r in sla_tracked
		if r.status and r.status.name in {"Closed", "Resolved"} and not r.sla_breached
	)
	sla_resolved_with_tracking = sum(
		1 for r in sla_tracked if r.status and r.status.name in {"Closed", "Resolved"}
	)
	on_time_pct = round(sla_on_time / sla_resolved_with_tracking * 100, 1) if sla_resolved_with_tracking else None

	# Dept manager breakdown (Requester Manager role)
	dept_managers = db.query(User).join(Role, User.role_id == Role.id).filter(
		Role.name == "Requester Manager", User.is_active.is_(True)
	).all()
	dept_stats = []
	for m in dept_managers:
		dept_requests = [r for r in all_requests if r.department_id == m.department_id]
		dept_stats.append({
			"id":        m.id,
			"full_name": m.full_name,
			"email":     m.email,
			"total":     len(dept_requests),
			"pending":   sum(1 for r in dept_requests if r.status and r.status.name not in terminal_statuses),
			"closed":    sum(1 for r in dept_requests if r.status and r.status.name in {"Closed", "Resolved"}),
		})

	return {
		"summary": {
			"total":      total,
			"closed":     closed,
			"pending":    pending,
			"unassigned": unassigned,
		},
		"sla": {
			"tracked":          len(sla_tracked),
			"currently_overdue": len(sla_overdue),
			"total_breached":    sla_breached_total,
			"on_time_pct":       on_time_pct,
		},
		"officers":      officer_stats,
		"dept_managers": dept_stats,
	}


@router.get("/sla")
def get_sla_dashboard(
	db: Session = Depends(get_db),
	current_user: User = Depends(get_current_user),
):
	"""
	Dedicated SLA dashboard.
	Returns overdue tickets, breach trends by request type, and per-priority stats.
	Accessible to MIS Manager, MIS Supervisor, Admin, System Administrator.
	"""
	role_name = current_user.role.name if current_user.role else "Requester"
	if not current_user.is_superuser and role_name not in {
		"MIS Manager", "MIS Supervisor", "Admin", "System Administrator"
	}:
		raise HTTPException(status_code=403, detail="Access denied")

	from ...models.request import Request
	from ...models.request_type import RequestType
	from ...models.status import Status
	from datetime import datetime, timezone

	terminal_statuses = {"Closed", "Resolved", "Rejected", "Cancelled"}
	now = datetime.now(timezone.utc)

	# All tickets with SLA configured
	sla_tickets = db.query(Request).filter(Request.sla_deadline != None).all()  # noqa: E711
	active_sla  = [r for r in sla_tickets if r.status and r.status.name not in terminal_statuses]

	def _deadline(r: Request) -> datetime:
		d = r.sla_deadline
		return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d

	# Overdue tickets (full detail for the table)
	overdue = [r for r in active_sla if _deadline(r) < now]
	overdue_list = []
	for r in sorted(overdue, key=lambda x: _deadline(x)):
		hours_over = (now - _deadline(r)).total_seconds() / 3600
		officer    = db.query(User).filter(User.id == r.assigned_to_id).first() if r.assigned_to_id else None
		overdue_list.append({
			"id":               r.id,
			"title":            r.title,
			"priority":         str(r.priority.value if hasattr(r.priority, "value") else r.priority),
			"status":           r.status.name if r.status else None,
			"sla_deadline":     r.sla_deadline,
			"hours_overdue":    round(hours_over, 1),
			"assigned_to":      officer.full_name or officer.email if officer else None,
			"department_id":    r.department_id,
			"created_at":       r.created_at,
		})

	# On-time / breached breakdown by request type
	all_request_types = db.query(RequestType).filter(RequestType.sla_hours != None).all()  # noqa: E711
	by_type = []
	for rt in all_request_types:
		rt_tickets   = [r for r in sla_tickets if r.request_type_id == rt.id]
		rt_resolved  = [r for r in rt_tickets if r.status and r.status.name in {"Closed", "Resolved"}]
		rt_on_time   = sum(1 for r in rt_resolved if not r.sla_breached)
		rt_breached  = sum(1 for r in rt_resolved if r.sla_breached)
		rt_active    = [r for r in rt_tickets if r.status and r.status.name not in terminal_statuses]
		rt_overdue   = sum(1 for r in rt_active if _deadline(r) < now)
		by_type.append({
			"request_type_id":   rt.id,
			"request_type_name": rt.name,
			"sla_hours":         rt.sla_hours,
			"total":             len(rt_tickets),
			"resolved":          len(rt_resolved),
			"on_time":           rt_on_time,
			"breached":          rt_breached,
			"currently_overdue": rt_overdue,
			"on_time_pct":       round(rt_on_time / len(rt_resolved) * 100, 1) if rt_resolved else None,
		})

	# Breakdown by priority
	priority_stats = {}
	for r in sla_tickets:
		p = str(r.priority.value if hasattr(r.priority, "value") else r.priority)
		if p not in priority_stats:
			priority_stats[p] = {"total": 0, "breached": 0, "on_time": 0, "overdue": 0}
		priority_stats[p]["total"] += 1
		if r.sla_breached:
			priority_stats[p]["breached"] += 1
		elif r.status and r.status.name in {"Closed", "Resolved"}:
			priority_stats[p]["on_time"] += 1
		if r.status and r.status.name not in terminal_statuses and _deadline(r) < now:
			priority_stats[p]["overdue"] += 1

	return {
		"summary": {
			"total_tracked":      len(sla_tickets),
			"currently_overdue":  len(overdue),
			"total_breached":     sum(1 for r in sla_tickets if r.sla_breached),
			"active_with_sla":    len(active_sla),
		},
		"overdue_tickets": overdue_list,
		"by_request_type": by_type,
		"by_priority":     [{"priority": k, **v} for k, v in priority_stats.items()],
	}


@router.get("/", response_model=List[UserResponse])
def list_users(
	db: Session = Depends(get_db),
	current_user: User = Depends(get_current_user),
):
	role_name = current_user.role.name if current_user.role else "Requester"
	if not current_user.is_superuser and role_name not in {"Admin", "System Administrator", "MIS Supervisor", "MIS Manager"}:
		raise HTTPException(status_code=403, detail="Only administrators and supervisors can view users")
	users = db.query(User).order_by(User.full_name, User.email).all()
	result = []
	for u in users:
		result.append({
			"id": u.id,
			"email": u.email,
			"full_name": u.full_name,
			"is_active": u.is_active,
			"is_superuser": u.is_superuser,
			"role_id": u.role_id,
			"role_name": u.role.name if u.role else None,
			"role_type": u.role.role_type if u.role else "Officer",
			"permissions": u.role.permissions if u.role else [],
			"department_id": u.department_id,
		})
	return result

def require_admin(user: User):
	permissions = user.role.permissions if user.role else []
	if not user.is_superuser and "*" not in permissions and "user:manage" not in permissions:
		raise HTTPException(status_code=403, detail="Administrator access required")

@router.get("/roles", response_model=List[RoleResponse])
def list_roles(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
	require_admin(current_user)
	return db.query(Role).order_by(Role.name).all()

@router.get("/departments")
def list_departments(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
	require_admin(current_user)
	return db.query(Department).filter(Department.is_active.is_(True)).order_by(Department.name).all()

@router.post("/departments", status_code=201)
def create_department(data: DepartmentCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
	require_admin(current_user)
	name = data.name.strip()
	if not name:
		raise HTTPException(status_code=422, detail="Department name is required")
	if db.query(Department).filter(Department.name.ilike(name)).first():
		raise HTTPException(status_code=400, detail="Department already exists")
	department = Department(name=name, manager_id=data.manager_id)
	db.add(department)
	db.commit()
	db.refresh(department)
	return department

@router.patch("/departments/{department_id}")
def update_department(department_id: int, data: DepartmentUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
	require_admin(current_user)
	department = db.query(Department).filter(Department.id == department_id).first()
	if not department:
		raise HTTPException(status_code=404, detail="Department not found")
	for field, value in data.model_dump(exclude_unset=True).items():
		setattr(department, field, value)
	db.commit()
	db.refresh(department)
	return department

@router.post("/roles", response_model=RoleResponse, status_code=201)
def create_role(data: RoleCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
	require_admin(current_user)
	if db.query(Role).filter(Role.name == data.name.strip()).first():
		raise HTTPException(status_code=400, detail="Role already exists")
	if data.role_type not in {"Manager", "Officer"}:
		raise HTTPException(status_code=422, detail="Role type must be Manager or Officer")
	role = Role(name=data.name.strip(), permissions=data.permissions, role_type=data.role_type)
	db.add(role)
	db.commit()
	db.refresh(role)
	return role

@router.post("/", response_model=UserResponse, status_code=201)
def create_user(data: UserAdminCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
	require_admin(current_user)
	if db.query(User).filter(User.email == data.email).first():
		raise HTTPException(status_code=400, detail="Email already registered")
	user = User(email=data.email, hashed_password=get_password_hash(data.password), full_name=data.full_name, role_id=data.role_id, department_id=data.department_id)
	db.add(user)
	db.flush()
	role = db.query(Role).filter(Role.id == data.role_id).first() if data.role_id else None
	if role and role.role_type == "Manager" and data.department_id:
		db.query(Department).filter(Department.id == data.department_id).update({"manager_id": user.id})
	db.commit()
	db.refresh(user)
	return user

@router.patch("/{user_id}", response_model=UserResponse)
def update_user(user_id: int, data: UserAdminUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
	require_admin(current_user)
	user = db.query(User).filter(User.id == user_id).first()
	if not user:
		raise HTTPException(status_code=404, detail="User not found")
	changes = data.model_dump(exclude_unset=True)
	if "password" in changes:
		changes["hashed_password"] = get_password_hash(changes.pop("password"))
	for field, value in changes.items():
		setattr(user, field, value)
	role = db.query(Role).filter(Role.id == user.role_id).first() if user.role_id else None
	if role and role.role_type == "Manager" and user.department_id:
		db.query(Department).filter(Department.id == user.department_id).update({"manager_id": user.id})
	db.commit()
	db.refresh(user)
	return user
