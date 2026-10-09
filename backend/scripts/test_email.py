"""
Quick SMTP test — sends one real email to the configured SMTP_FROM address.
Run from backend/ directory:
    python scripts/test_email.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.services.email_service import send_email

print(f"EMAIL_ENABLED : {settings.EMAIL_ENABLED}")
print(f"SMTP_HOST     : {settings.SMTP_HOST}:{settings.SMTP_PORT}")
print(f"SMTP_USER     : {settings.SMTP_USER}")
print(f"SMTP_FROM     : {settings.SMTP_FROM}")
print()

if not settings.EMAIL_ENABLED:
    print("EMAIL_ENABLED is false — set it to true in .env first.")
    sys.exit(1)

print("Sending test email...")
send_email(
    to=settings.SMTP_FROM,   # send to yourself
    subject="RMS Email Test",
    html_body="""
    <div style="font-family:Arial,sans-serif;padding:24px;max-width:500px">
      <h2 style="color:#7B1235">✅ Email is working!</h2>
      <p>This is a test from the <strong>Report Management System</strong>.</p>
      <p>Email notifications are now active.</p>
    </div>
    """,
)
print("Done. Check your inbox at", settings.SMTP_FROM)
