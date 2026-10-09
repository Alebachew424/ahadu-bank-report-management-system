"""
Manually trigger the SLA escalation sweep.
Run from backend/ directory:
    python scripts/run_escalation.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.services.sla_service import run_sla_escalation

db = SessionLocal()
count = run_sla_escalation(db)
db.close()
print(f"Escalated {count} ticket(s).")
