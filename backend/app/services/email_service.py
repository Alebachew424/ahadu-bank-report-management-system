"""
Email notification service.

Sends emails for all workflow events. Uses Python's built-in smtplib so
no extra library is needed beyond what's already installed.

Configuration (add to .env):
    SMTP_HOST=smtp.gmail.com       # or your bank's mail relay
    SMTP_PORT=587
    SMTP_USER=noreply@yourbank.com
    SMTP_PASSWORD=yourpassword
    SMTP_FROM=noreply@yourbank.com
    SMTP_TLS=true
    EMAIL_ENABLED=true             # set false to disable without removing config

If EMAIL_ENABLED=false (default for dev), all calls are logged but no email is sent.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Sequence

from ..core.config import settings

logger = logging.getLogger(__name__)

# ── HTML email template ────────────────────────────────────────────────────────
_BASE_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }}
    .card {{ background: #fff; border-radius: 8px; max-width: 600px; margin: 0 auto;
             box-shadow: 0 2px 8px rgba(0,0,0,.1); overflow: hidden; }}
    .header {{ background: #7B1235; color: #fff; padding: 24px 32px; }}
    .header h2 {{ margin: 0; font-size: 20px; }}
    .header p  {{ margin: 4px 0 0; font-size: 13px; opacity: .85; }}
    .body {{ padding: 28px 32px; color: #333; line-height: 1.6; }}
    .ticket-box {{ background: #faf7f5; border-left: 4px solid #7B1235;
                   border-radius: 4px; padding: 14px 18px; margin: 18px 0; }}
    .ticket-box .id  {{ font-size: 11px; color: #888; margin-bottom: 4px; }}
    .ticket-box .ttl {{ font-size: 16px; font-weight: 700; color: #222; }}
    .ticket-box .det {{ font-size: 13px; color: #555; margin-top: 6px; }}
    .btn {{ display: inline-block; margin-top: 20px; padding: 11px 24px;
            background: #7B1235; color: #fff !important; text-decoration: none;
            border-radius: 6px; font-size: 14px; font-weight: 600; }}
    .footer {{ padding: 16px 32px; font-size: 12px; color: #999;
               border-top: 1px solid #eee; background: #fafafa; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <h2>AHADU BANK — Report Management</h2>
      <p>{subject}</p>
    </div>
    <div class="body">
      <p>{greeting}</p>
      <div class="ticket-box">
        <div class="id">Ticket #{ticket_id_padded}</div>
        <div class="ttl">{ticket_title}</div>
        <div class="det">{ticket_detail}</div>
      </div>
      <p>{message}</p>
      <a class="btn" href="{action_url}">View Ticket</a>
    </div>
    <div class="footer">
      This is an automated message from the Report Management System.
      Please do not reply to this email.
    </div>
  </div>
</body>
</html>
"""


def _build_html(
    subject: str,
    greeting: str,
    ticket_id: int,
    ticket_title: str,
    ticket_detail: str,
    message: str,
    frontend_url: str = "http://localhost:5173",
) -> str:
    return _BASE_HTML.format(
        subject=subject,
        greeting=greeting,
        ticket_id_padded=str(ticket_id).zfill(5),
        ticket_title=ticket_title,
        ticket_detail=ticket_detail,
        message=message,
        action_url=f"{frontend_url}/requests/{ticket_id}",
    )


def send_email(
    *,
    to: str | Sequence[str],
    subject: str,
    html_body: str,
) -> None:
    """Low-level send. Silently logs if disabled or on SMTP error."""
    if not getattr(settings, "EMAIL_ENABLED", False):
        logger.info("EMAIL DISABLED — would send '%s' to %s", subject, to)
        return

    recipients = [to] if isinstance(to, str) else list(to)
    if not recipients:
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[RMS] {subject}"
    msg["From"]    = settings.SMTP_FROM
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html"))

    try:
        smtp_host = settings.SMTP_HOST
        smtp_port = int(getattr(settings, "SMTP_PORT", 587))
        use_tls   = str(getattr(settings, "SMTP_TLS", "true")).lower() == "true"

        if use_tls:
            context = ssl.create_default_context()
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.ehlo()
                server.starttls(context=context)
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.SMTP_FROM, recipients, msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                if getattr(settings, "SMTP_USER", None):
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.SMTP_FROM, recipients, msg.as_string())

        logger.info("Email '%s' sent to %s", subject, recipients)
    except Exception as exc:
        logger.error("Email send failed: %s", exc, exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Domain-level notification functions — called from workflow endpoints
# ─────────────────────────────────────────────────────────────────────────────

def notify_ticket_created(
    *,
    dept_manager_email: str,
    dept_manager_name: str,
    requester_name: str,
    ticket_id: int,
    ticket_title: str,
    priority: str,
    due_date: str,
) -> None:
    html = _build_html(
        subject="New ticket awaiting your approval",
        greeting=f"Hello {dept_manager_name},",
        ticket_id=ticket_id,
        ticket_title=ticket_title,
        ticket_detail=f"Priority: {priority.upper()} · Due: {due_date}",
        message=f"<strong>{requester_name}</strong> has submitted a new report request "
                f"that requires your approval before it reaches the MIS team.",
    )
    send_email(to=dept_manager_email, subject="New ticket awaiting your approval", html_body=html)


def notify_dept_approved(
    *,
    mis_manager_emails: list[str],
    requester_name: str,
    dept_name: str,
    ticket_id: int,
    ticket_title: str,
    priority: str,
) -> None:
    html = _build_html(
        subject="Ticket approved — action required",
        greeting="Hello MIS Team,",
        ticket_id=ticket_id,
        ticket_title=ticket_title,
        ticket_detail=f"Department: {dept_name} · Priority: {priority.upper()}",
        message=f"A ticket from <strong>{requester_name}</strong> ({dept_name}) has been "
                f"approved by the department manager and is ready to be assigned to an MIS Officer.",
    )
    send_email(to=mis_manager_emails, subject="Ticket approved — action required", html_body=html)


def notify_ticket_assigned(
    *,
    officer_email: str,
    officer_name: str,
    ticket_id: int,
    ticket_title: str,
    priority: str,
    due_date: str,
) -> None:
    html = _build_html(
        subject="Ticket assigned to you",
        greeting=f"Hello {officer_name},",
        ticket_id=ticket_id,
        ticket_title=ticket_title,
        ticket_detail=f"Priority: {priority.upper()} · Due: {due_date}",
        message="A ticket has been assigned to you. Please review the details and begin working at your earliest convenience.",
    )
    send_email(to=officer_email, subject="Ticket assigned to you", html_body=html)


def notify_ticket_resolved(
    *,
    requester_email: str,
    requester_name: str,
    ticket_id: int,
    ticket_title: str,
) -> None:
    html = _build_html(
        subject="Your ticket has been resolved",
        greeting=f"Hello {requester_name},",
        ticket_id=ticket_id,
        ticket_title=ticket_title,
        ticket_detail="Status: Resolved",
        message="The MIS team has resolved your report request. "
                "Please log in and submit your feedback to close the ticket.",
    )
    send_email(to=requester_email, subject="Your ticket has been resolved", html_body=html)


def notify_new_comment(
    *,
    recipient_emails: list[str],
    author_name: str,
    ticket_id: int,
    ticket_title: str,
    comment_preview: str,
    is_internal: bool = False,
) -> None:
    if not recipient_emails:
        return
    label   = "internal note" if is_internal else "message"
    subject = f"New {label} on ticket #{str(ticket_id).zfill(5)}"
    html = _build_html(
        subject=subject,
        greeting="Hello,",
        ticket_id=ticket_id,
        ticket_title=ticket_title,
        ticket_detail=f"From: {author_name}",
        message=f"A new {label} has been posted:<br><br>"
                f"<em>\"{comment_preview[:200]}{'…' if len(comment_preview) > 200 else ''}\"</em>",
    )
    send_email(to=recipient_emails, subject=subject, html_body=html)


def notify_sla_breach(
    *,
    supervisor_emails: list[str],
    ticket_id: int,
    ticket_title: str,
    priority: str,
    hours_overdue: float,
    assigned_officer_name: str | None,
) -> None:
    officer_info = f"Assigned to: {assigned_officer_name}" if assigned_officer_name else "Unassigned"
    html = _build_html(
        subject=f"SLA BREACH — Ticket #{str(ticket_id).zfill(5)}",
        greeting="Hello Supervisor,",
        ticket_id=ticket_id,
        ticket_title=ticket_title,
        ticket_detail=f"Priority: {priority.upper()} · {officer_info}",
        message=f"⚠ This ticket has exceeded its SLA by "
                f"<strong>{hours_overdue:.1f} hour(s)</strong>. "
                f"Immediate action is required.",
    )
    send_email(to=supervisor_emails, subject=f"SLA BREACH — Ticket #{str(ticket_id).zfill(5)}", html_body=html)
