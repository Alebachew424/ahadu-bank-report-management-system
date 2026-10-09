import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.role import Role
from app.models.user import User


def main():
	email = input("Administrator email: ").strip()
	full_name = input("Administrator name: ").strip()
	password = getpass.getpass("Administrator password: ")
	if not email or not full_name or not password:
		raise SystemExit("Email, name, and password are required")

	db = SessionLocal()
	try:
		role = db.query(Role).filter(Role.name == "System Administrator").first()
		if not role:
			role = Role(name="System Administrator", permissions=["*"])
			db.add(role)
			db.flush()

		user = db.query(User).filter(User.email == email).first()
		if user:
			user.full_name = full_name
			user.hashed_password = get_password_hash(password)
			user.role_id = role.id
			user.is_superuser = True
			user.is_active = True
			message = "Administrator account updated"
		else:
			user = User(
				email=email,
				full_name=full_name,
				hashed_password=get_password_hash(password),
				role_id=role.id,
				is_superuser=True,
				is_active=True,
			)
			db.add(user)
			message = "Administrator account created"
		db.commit()
		print(message)
	finally:
		db.close()


if __name__ == "__main__":
	main()
