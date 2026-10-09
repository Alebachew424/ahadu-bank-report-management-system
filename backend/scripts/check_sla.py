import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.request import Request
from app.services.sla_service import enrich_request_sla

db = SessionLocal()
reqs = db.query(Request).order_by(Request.id.desc()).limit(8).all()

print(f"{'ID':<5} {'Priority':<10} {'sla_deadline':<32} {'overdue':<9} {'hrs_remaining'}")
print("-" * 75)
for r in reqs:
    sla  = enrich_request_sla(r)
    hrs  = sla["sla_hours_remaining"]
    p    = r.priority.value if hasattr(r.priority, "value") else str(r.priority)
    dl   = str(r.sla_deadline)[:25] if r.sla_deadline else "None"
    print(f"{r.id:<5} {p:<10} {dl:<32} {str(sla['sla_overdue']):<9} {f'{hrs:.1f}h' if hrs is not None else 'N/A'}")
db.close()
