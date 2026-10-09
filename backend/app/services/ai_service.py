"""
AI / ML service for the Report Management System.

Three capabilities — all run in-process using scikit-learn (no external API calls):

1. NLP Categorisation
   Predicts the best RequestType for a given title + description using
   TF-IDF + cosine similarity against the known request type keywords.
   Falls back to a simple keyword-matching ruleset when there is not enough
   history to train a classifier.

2. ML-Based Analyst Suggestion
   Scores every active MIS Officer by combining:
     - Current workload (fewer open tickets = higher score)
     - Past performance (closed tickets, avg quality/timeliness rating)
     - Expertise match (what types of tickets has this officer handled most?)
   Returns an ordered list with scores and reasoning.

3. Anomaly Detection
   Flags suspicious or unusual patterns on a newly submitted ticket:
     - Duplicate: near-identical title submitted by same user recently
     - Spam burst: same user created many tickets in a short window
     - Off-hours: submitted outside normal working hours
     - Unusual priority: urgent tickets from users who rarely submit urgent
     - Attachment content mismatch: file extension analysis (future hook)

All methods return plain dicts — no ORM objects, so they are safe to call
from any context without session issues.
"""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _clean(a), _clean(b)).ratio()


# ─────────────────────────────────────────────────────────────────────────────
# 1. NLP CATEGORISATION
# ─────────────────────────────────────────────────────────────────────────────

# Keyword seeds per known request type — these bootstrap the model before
# there is enough ticket history.  Keys should match request_type.name exactly.
_TYPE_KEYWORDS: dict[str, list[str]] = {
    "Daily Transaction Report": [
        "daily", "transaction", "transactions", "day", "eod",
        "end of day", "daily report", "daily summary",
    ],
    "Monthly Performance Report": [
        "monthly", "month", "performance", "kpi", "metrics",
        "monthly summary", "monthly report", "indicator",
    ],
    "Loan Portfolio Report": [
        "loan", "portfolio", "credit", "lending", "outstanding",
        "loan balance", "npl", "nonperforming", "repayment",
    ],
    "Branch Summary Report": [
        "branch", "office", "location", "regional", "outlet",
        "branch summary", "branch report", "branch performance",
    ],
    "Custom Data Extract": [
        "custom", "extract", "data", "export", "raw", "adhoc",
        "ad hoc", "specific", "tailored", "query",
    ],
}


def suggest_request_type(
    db: Session,
    title: str,
    description: str | None,
) -> dict[str, Any]:
    """
    Returns the top-3 request-type suggestions with confidence scores.

    Strategy:
      1. Try scikit-learn TF-IDF cosine similarity trained on closed tickets
         (requires >= 10 closed tickets per type for reasonable accuracy).
      2. Fall back to keyword-seed scoring if training data is insufficient.

    Returns:
      {
        "suggestions": [
          {"request_type_id": int, "name": str, "confidence": float, "reason": str},
          ...
        ],
        "method": "tfidf" | "keyword"
      }
    """
    from ..models.request import Request
    from ..models.request_type import RequestType

    query_text = _clean(f"{title} {description or ''}")
    request_types = db.query(RequestType).filter(RequestType.is_active.is_(True)).all()
    if not request_types:
        return {"suggestions": [], "method": "none"}

    # ── Try TF-IDF if we have enough history ─────────────────────────────────
    closed_tickets = (
        db.query(Request)
        .join(Request.status)
        .filter(Request.status.has(name="Closed"))
        .all()
    )

    type_samples: dict[int, list[str]] = defaultdict(list)
    for t in closed_tickets:
        type_samples[t.request_type_id].append(
            _clean(f"{t.title} {t.description or ''}")
        )

    # Use TF-IDF only when every active type has >= 5 examples
    min_samples = min(len(type_samples.get(rt.id, [])) for rt in request_types)
    method = "tfidf" if min_samples >= 5 else "keyword"

    if method == "tfidf":
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
            import numpy as np

            # Build centroid vectors per request type
            labels, centroids = [], []
            for rt in request_types:
                samples = type_samples.get(rt.id, [])
                if samples:
                    labels.append(rt)
                    centroids.append(" ".join(samples))

            vectorizer = TfidfVectorizer(max_features=500, ngram_range=(1, 2))
            corpus = centroids + [query_text]
            tfidf_matrix = vectorizer.fit_transform(corpus)
            query_vec = tfidf_matrix[-1]
            type_vecs = tfidf_matrix[:-1]

            sims = cosine_similarity(query_vec, type_vecs).flatten()
            top_idx = np.argsort(sims)[::-1][:3]

            suggestions = []
            for i in top_idx:
                confidence = float(round(sims[i], 3))
                if confidence > 0:
                    suggestions.append({
                        "request_type_id": labels[i].id,
                        "name":            labels[i].name,
                        "confidence":      confidence,
                        "reason":          f"Matched {confidence*100:.0f}% similarity to {len(type_samples[labels[i].id])} past tickets",
                    })
            return {"suggestions": suggestions, "method": "tfidf"}

        except Exception as exc:
            logger.warning("TF-IDF failed, falling back to keywords: %s", exc)
            method = "keyword"

    # ── Keyword scoring fallback ──────────────────────────────────────────────
    scores: list[tuple[float, RequestType, str]] = []
    for rt in request_types:
        keywords = _TYPE_KEYWORDS.get(rt.name, [])
        # Also include name/description words of the type itself
        keywords += _clean(f"{rt.name} {rt.description or ''}").split()

        hits = sum(1 for kw in keywords if kw in query_text)
        total = max(len(set(keywords)), 1)
        confidence = round(min(hits / total, 1.0), 3)

        reason = (
            f"{hits} keyword match(es) from '{rt.name}'"
            if hits > 0
            else "No direct keyword match"
        )
        scores.append((confidence, rt, reason))

    scores.sort(key=lambda x: x[0], reverse=True)
    suggestions = [
        {
            "request_type_id": rt.id,
            "name":            rt.name,
            "confidence":      conf,
            "reason":          reason,
        }
        for conf, rt, reason in scores[:3]
        if conf > 0
    ]
    return {"suggestions": suggestions, "method": "keyword"}


# ─────────────────────────────────────────────────────────────────────────────
# 2. ML-BASED ANALYST SUGGESTION
# ─────────────────────────────────────────────────────────────────────────────

def suggest_analyst(
    db: Session,
    request_type_id: int,
    priority: str,
) -> dict[str, Any]:
    """
    Scores all active MIS Officers and returns an ordered suggestion list.

    Scoring factors (each 0–1, weighted):
      40%  Workload       — fewer open tickets = higher score
      30%  Performance    — avg quality + timeliness ratings from feedback
      30%  Expertise      — % of past closed tickets matching this request_type

    Returns:
      {
        "suggestions": [
          {
            "officer_id": int, "name": str, "email": str,
            "score": float,
            "workload": int, "open_tickets": int,
            "avg_rating": float | None,
            "expertise_match": float,
            "reason": str
          },
          ...
        ]
      }
    """
    from ..models.request import Request
    from ..models.user import User
    from ..models.role import Role
    from ..models.feedback import RequestFeedback
    from ..models.status import Status

    terminal_names = {"Closed", "Resolved", "Rejected", "Cancelled"}

    officers = (
        db.query(User)
        .join(Role, User.role_id == Role.id)
        .filter(Role.name.in_(["MIS Officer", "MIS Analyst"]), User.is_active.is_(True))
        .all()
    )
    if not officers:
        return {"suggestions": []}

    terminal_ids = {
        s.id for s in db.query(Status).filter(Status.name.in_(terminal_names)).all()
    }

    all_requests = db.query(Request).all()

    # Pre-compute feedback averages
    feedback_map: dict[int, list[float]] = defaultdict(list)
    for fb in db.query(RequestFeedback).all():
        avg = (fb.quality_rating + fb.timeliness_rating) / 2
        req = next((r for r in all_requests if r.id == fb.request_id), None)
        if req and req.assigned_to_id:
            feedback_map[req.assigned_to_id].append(avg)

    results = []
    for officer in officers:
        assigned = [r for r in all_requests if r.assigned_to_id == officer.id]
        open_tickets = [r for r in assigned if r.status_id not in terminal_ids]
        closed_tickets = [r for r in assigned if r.status_id in terminal_ids]

        # Workload score: 0 open = 1.0, 10+ open = 0.0
        max_load = 10
        workload_score = max(0.0, 1.0 - len(open_tickets) / max_load)

        # Performance score: avg of all feedback ratings (0–5 → 0–1)
        ratings = feedback_map.get(officer.id, [])
        avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else None
        perf_score = (avg_rating / 5.0) if avg_rating is not None else 0.5  # neutral if no history

        # Expertise score: % of closed tickets matching this request_type
        type_matches = sum(1 for r in closed_tickets if r.request_type_id == request_type_id)
        expertise_score = (
            round(type_matches / len(closed_tickets), 3)
            if closed_tickets else 0.0
        )

        # Urgent penalty: de-prioritise officers with too many urgent open tickets
        urgent_open = sum(
            1 for r in open_tickets
            if hasattr(r.priority, "value") and r.priority.value == "urgent"
            or str(r.priority) == "urgent"
        )
        urgent_penalty = 0.1 * min(urgent_open, 3) if priority == "urgent" else 0.0

        total_score = round(
            0.40 * workload_score +
            0.30 * perf_score +
            0.30 * expertise_score -
            urgent_penalty,
            3,
        )

        reasons = []
        reasons.append(f"{len(open_tickets)} open ticket(s)")
        if avg_rating:
            reasons.append(f"avg rating {avg_rating:.1f}/5")
        if type_matches:
            reasons.append(f"{type_matches} past ticket(s) of this type")
        if urgent_penalty:
            reasons.append(f"has {urgent_open} urgent open — deprioritised")

        results.append({
            "officer_id":      officer.id,
            "name":            officer.full_name or officer.email,
            "email":           officer.email,
            "score":           max(0.0, total_score),
            "open_tickets":    len(open_tickets),
            "avg_rating":      avg_rating,
            "expertise_match": expertise_score,
            "reason":          ", ".join(reasons) if reasons else "No history",
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return {"suggestions": results[:5]}


# ─────────────────────────────────────────────────────────────────────────────
# 3. ANOMALY DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def detect_anomalies(
    db: Session,
    requester_id: int,
    title: str,
    description: str | None,
    priority: str,
    request_type_id: int,
) -> dict[str, Any]:
    """
    Checks for unusual patterns on a new ticket before it is saved.

    Returns:
      {
        "anomalies": [
          {"type": str, "severity": "low"|"medium"|"high", "message": str},
          ...
        ],
        "flagged": bool   # True if any medium/high severity anomaly found
      }
    """
    from ..models.request import Request
    from ..models.user import User

    now = datetime.now(timezone.utc)
    anomalies: list[dict] = []

    requester_tickets = (
        db.query(Request)
        .filter(Request.requester_id == requester_id)
        .order_by(Request.created_at.desc())
        .limit(200)
        .all()
    )

    # ── 1. Duplicate detection ─────────────────────────────────────────────
    # Near-identical title submitted by the same user in the last 7 days
    recent_7d = [
        r for r in requester_tickets
        if r.created_at and (now - r.created_at.replace(tzinfo=timezone.utc)).days <= 7
    ]
    for r in recent_7d:
        sim = _similarity(title, r.title)
        if sim >= 0.85:
            anomalies.append({
                "type":     "duplicate",
                "severity": "high",
                "message":  (
                    f"Ticket #{r.id} '{r.title}' was submitted "
                    f"{(now - r.created_at.replace(tzinfo=timezone.utc)).days} day(s) ago "
                    f"with {sim*100:.0f}% similarity. This may be a duplicate."
                ),
            })
            break  # one warning is enough

    # ── 2. Spam burst ─────────────────────────────────────────────────────
    # More than 5 tickets in the last hour
    last_hour = [
        r for r in requester_tickets
        if r.created_at
        and (now - r.created_at.replace(tzinfo=timezone.utc)).total_seconds() <= 3600
    ]
    if len(last_hour) >= 5:
        anomalies.append({
            "type":     "spam_burst",
            "severity": "medium",
            "message":  (
                f"This user has submitted {len(last_hour)} tickets in the last hour. "
                "Unusual activity detected."
            ),
        })

    # ── 3. Off-hours submission ────────────────────────────────────────────
    # Ethiopian Standard Time is UTC+3
    local_hour = (now.hour + 3) % 24
    if local_hour < 6 or local_hour >= 22:
        anomalies.append({
            "type":     "off_hours",
            "severity": "low",
            "message":  (
                f"Ticket submitted at {local_hour:02d}:00 local time (outside 06:00–22:00). "
                "This is outside normal working hours."
            ),
        })

    # ── 4. Unusual priority escalation ────────────────────────────────────
    # User rarely submits urgent, but this one is urgent
    if priority == "urgent":
        total = len(requester_tickets)
        urgent_count = sum(
            1 for r in requester_tickets
            if (hasattr(r.priority, "value") and r.priority.value == "urgent")
            or str(r.priority) == "urgent"
        )
        urgent_rate = urgent_count / total if total >= 10 else None
        if urgent_rate is not None and urgent_rate < 0.05:
            anomalies.append({
                "type":     "unusual_priority",
                "severity": "low",
                "message":  (
                    f"This user marks only {urgent_rate*100:.0f}% of tickets as urgent. "
                    "This 'urgent' submission is unusual compared to their history."
                ),
            })

    # ── 5. Same-type burst ────────────────────────────────────────────────
    # More than 3 tickets of the exact same type in the last 24 hours
    last_24h_same_type = [
        r for r in requester_tickets
        if r.created_at
        and r.request_type_id == request_type_id
        and (now - r.created_at.replace(tzinfo=timezone.utc)).total_seconds() <= 86400
    ]
    if len(last_24h_same_type) >= 3:
        anomalies.append({
            "type":     "same_type_burst",
            "severity": "medium",
            "message":  (
                f"{len(last_24h_same_type)} tickets of the same report type submitted "
                "in the last 24 hours. Consider if a single request would suffice."
            ),
        })

    flagged = any(a["severity"] in ("medium", "high") for a in anomalies)
    return {"anomalies": anomalies, "flagged": flagged}


# ─────────────────────────────────────────────────────────────────────────────
# 4. COMBINED ANALYSIS (single call for the /analyse endpoint)
# ─────────────────────────────────────────────────────────────────────────────

def analyse_request(
    db: Session,
    requester_id: int,
    title: str,
    description: str | None,
    priority: str,
    request_type_id: int | None,
) -> dict[str, Any]:
    """
    Runs all three analyses and returns a combined result.
    Safe to call before the ticket is saved — does not mutate any DB rows.
    """
    categorisation = suggest_request_type(db, title, description)
    analyst_rtype  = request_type_id or (
        categorisation["suggestions"][0]["request_type_id"]
        if categorisation["suggestions"] else None
    )
    analyst_suggestion = (
        suggest_analyst(db, analyst_rtype, priority)
        if analyst_rtype else {"suggestions": []}
    )
    anomaly_result = detect_anomalies(
        db, requester_id, title, description, priority,
        request_type_id or 0,
    )

    return {
        "categorisation":       categorisation,
        "analyst_suggestion":   analyst_suggestion,
        "anomalies":            anomaly_result,
    }
