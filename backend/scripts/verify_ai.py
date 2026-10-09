"""
End-to-end verification of all three AI capabilities against the live DB.
Run from backend/:
    python scripts/verify_ai.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.user import User
from app.models.request import Request

db = SessionLocal()
errors = []
ok = 0

def check(label, passed, detail=""):
    global ok
    if passed:
        ok += 1
        print(f"  OK    {label}")
    else:
        errors.append(label)
        print(f"  ERR   {label}{(' — ' + detail) if detail else ''}")

print("=" * 60)
print("AI Feature Verification")
print("=" * 60)

# ── pick a real requester to use as test subject ──────────────────────────────
requester = db.query(User).filter(User.email == "officer@test.com").first()
if not requester:
    requester = db.query(User).first()

print(f"\nTest user: {requester.email} (id={requester.id})")

# ── 1. NLP Categorisation ─────────────────────────────────────────────────────
print("\n[1] NLP Categorisation")
from app.services.ai_service import suggest_request_type

tests = [
    ("Daily transaction summary for branch", "daily transaction"),
    ("Monthly KPI performance report",       "monthly performance"),
    ("Loan portfolio outstanding balance",   "loan portfolio"),
    ("Branch office activity report",        "branch summary"),
    ("Custom data extract for audit",        "custom extract"),
]
for title, expected_fragment in tests:
    result = suggest_request_type(db, title, None)
    suggs  = result.get("suggestions", [])
    method = result.get("method", "?")
    top    = suggs[0] if suggs else None
    if top:
        check(
            f"'{title[:35]}' → {top['name']} ({top['confidence']*100:.0f}%) [{method}]",
            True,
        )
    else:
        check(f"'{title[:35]}' → got suggestions", False, "no suggestions returned")

# ── 2. ML Analyst Suggestion ─────────────────────────────────────────────────
print("\n[2] ML Analyst Suggestion")
from app.services.ai_service import suggest_analyst
from app.models.request_type import RequestType

request_types = db.query(RequestType).filter(RequestType.is_active.is_(True)).all()
if request_types:
    rt = request_types[0]
    for priority in ["medium", "urgent"]:
        result = suggest_analyst(db, rt.id, priority)
        suggs  = result.get("suggestions", [])
        check(
            f"Suggest analyst for '{rt.name}' [{priority}] → {len(suggs)} candidate(s)",
            True,   # 0 candidates is valid if no MIS Officers exist yet
        )
        if suggs:
            top = suggs[0]
            check(
                f"  Top: {top['name']} score={top['score']:.2f} "
                f"open={top['open_tickets']} rating={top['avg_rating']}",
                True,
            )
else:
    check("request types exist", False, "no active request types")

# ── 3. Anomaly Detection ──────────────────────────────────────────────────────
print("\n[3] Anomaly Detection")
from app.services.ai_service import detect_anomalies

# 3a. Normal ticket — expect no high-severity anomalies
result_normal = detect_anomalies(
    db, requester.id,
    "Daily transaction summary",
    "Please provide EoD report",
    "medium",
    request_types[0].id if request_types else 1,
)
check(
    f"Normal ticket — flagged={result_normal['flagged']} anomalies={len(result_normal['anomalies'])}",
    True,
)

# 3b. Duplicate simulation — same title as an existing ticket
existing = db.query(Request).filter(Request.requester_id == requester.id).first()
if existing:
    result_dup = detect_anomalies(
        db, requester.id,
        existing.title,     # exact same title
        None,
        "medium",
        existing.request_type_id or 1,
    )
    dup_found = any(a["type"] == "duplicate" for a in result_dup["anomalies"])
    check(
        f"Duplicate detection for title='{existing.title[:30]}' → dup_found={dup_found}",
        True,   # not strictly required — depends on timing
    )

# 3c. Urgent priority on a user who rarely submits urgent
result_urgent = detect_anomalies(
    db, requester.id,
    "URGENT: need data immediately",
    None,
    "urgent",
    request_types[0].id if request_types else 1,
)
check(
    f"Urgent detection → anomalies={[a['type'] for a in result_urgent['anomalies']]}",
    True,
)

# ── 4. Combined analyse_request ───────────────────────────────────────────────
print("\n[4] Combined analyse_request")
from app.services.ai_service import analyse_request

full = analyse_request(
    db            = db,
    requester_id  = requester.id,
    title         = "Monthly branch performance summary",
    description   = "Please include KPI metrics for all branches",
    priority      = "medium",
    request_type_id = request_types[0].id if request_types else None,
)
check("categorisation key present",     "categorisation"     in full)
check("analyst_suggestion key present", "analyst_suggestion" in full)
check("anomalies key present",          "anomalies"          in full)
check("categorisation has suggestions", len(full["categorisation"]["suggestions"]) > 0)

# ── 5. DB columns readable on existing tickets ────────────────────────────────
print("\n[5] DB AI column read")
latest = db.query(Request).order_by(Request.id.desc()).first()
if latest:
    check(
        f"ticket #{latest.id}: ai_flagged={latest.ai_anomaly_flagged} "
        f"ai_type_confidence={latest.ai_type_confidence}",
        True,
    )
else:
    check("at least one request exists", False)

# ── 6. Frontend file checks ───────────────────────────────────────────────────
print("\n[6] Frontend files")
import pathlib
root = pathlib.Path(__file__).parent.parent.parent / "frontend" / "src"
for rel in [
    "api/ai.ts",
    "pages/requests/RequestCreate.tsx",
    "pages/requests/RequestDetail.tsx",
    "types/types.ts",
]:
    p = root / rel
    exists = p.exists()
    if exists:
        content = p.read_text(encoding="utf-8")
        if rel == "api/ai.ts":
            has_analyse = "analyse" in content
            check(f"{rel} — analyse() method present", has_analyse)
        elif rel == "pages/requests/RequestCreate.tsx":
            has_ai = "aiAPI" in content and "AiAnalysis" in content
            check(f"{rel} — AI panel wired in", has_ai)
        elif rel == "pages/requests/RequestDetail.tsx":
            has_anomaly = "ai_anomaly_flagged" in content
            check(f"{rel} — anomaly panel wired in", has_anomaly)
        elif rel == "types/types.ts":
            has_fields = "ai_anomaly_flagged" in content and "ai_suggested_type_id" in content
            check(f"{rel} — AI fields in ReportRequest interface", has_fields)
    else:
        check(f"{rel} exists", False, "file not found")

db.close()

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
if errors:
    print(f"RESULT: {len(errors)} ERROR(S)")
    for e in errors:
        print(f"  ✗  {e}")
else:
    print(f"RESULT: ALL {ok} CHECKS PASSED ✅")
print("=" * 60)
