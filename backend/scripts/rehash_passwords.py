"""
Re-hash passwords for test/seed users using the current pbkdf2_sha256 scheme.

Run from the backend/ directory:
    python scripts/rehash_passwords.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User

# Map of email → plain-text password for known test accounts
TEST_USERS = {
    "officer@test.com":   "password123",
    "deptmgr@test.com":   "Test1234!",
    "mismgr@test.com":    "Test1234!",
    "misofficer@test.com": "Test1234!",
}

db = SessionLocal()
try:
    updated = 0
    for email, plain_password in TEST_USERS.items():
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.hashed_password = get_password_hash(plain_password)
            print(f"  ✅  Re-hashed password for {email}")
            updated += 1
        else:
            print(f"  ⚠️   User not found: {email} — skipping")
    db.commit()
    print(f"\nDone. {updated} user(s) updated.")
finally:
    db.close()
