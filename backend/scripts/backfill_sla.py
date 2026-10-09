"""
Backfill sla_deadline for existing tickets that were created before SLA was introduced.
Run once from backend/ directory:
    python scripts/backfill_sla.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.request import Request
from app.models.request_type import RequestType
from app.services.sla_service import compute_sla_deadline
from datetime import timezone

db = SessionLocal()
updated = 0
skipped = 0

requests = db.query(Request).filter(Request.sla_deadline == None).all()  # noqa: E711
print(f"Found {len(requests)} tickets with no sla_deadline")

for req in requests:
    rt = db.query(RequestType).filter(RequestType.id == req.request_type_id).first()
    if not rt or not rt.sla_hours:
        skipped += 1
        continue

    priority = req.priority.value if hasattr(req.priority, "value") else str(req.priority)
    created  = req.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)

    req.sla_deadline = compute_sla_deadline(created, rt.sla_hours, priority)
    updated += 1

db.commit()
db.close()

print(f"  Updated : {updated}")
print(f"  Skipped : {skipped} (no SLA configured for their type)")
print("Done.")
