from fastapi import APIRouter, Depends, HTTPException, Request as FastAPIRequest
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.security import verify_password, create_access_token, get_password_hash, get_current_user
from ...models.user import User
from ...models.role import Role
from ...schemas.user import UserCreate, LoginRequest, Token, UserResponse
from ...services import audit_service

router = APIRouter()


def _ip(request: FastAPIRequest) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.get("/me", response_model=UserResponse)
def current_user(current_user: User = Depends(get_current_user)):
    return {
        "id":           current_user.id,
        "email":        current_user.email,
        "full_name":    current_user.full_name,
        "is_active":    current_user.is_active,
        "is_superuser": current_user.is_superuser,
        "role_id":      current_user.role_id,
        "role_name":    current_user.role.name if current_user.role else "Requester",
        "department_id": current_user.department_id,
        "permissions":  current_user.role.permissions if current_user.role else [
            "request:create", "request:view_own", "request:comment",
            "report:download", "report:export",
        ],
        "role_type": current_user.role.role_type if current_user.role else "Officer",
    }


@router.post("/login", response_model=Token)
def login(
    data: LoginRequest,
    http_req: FastAPIRequest,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == data.email).first()

    if not user or not verify_password(data.password, user.hashed_password):
        # Log failed attempt (no user_id since we may not know who it is)
        audit_service.log(
            db,
            action="login_failed",
            entity_type="auth",
            entity_id=None,
            user_id=user.id if user else None,
            new_value={"email": data.email},
            description=f"Failed login attempt for {data.email}",
            ip_address=_ip(http_req),
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    if not user.is_active:
        audit_service.log(
            db,
            action="login_blocked",
            entity_type="auth",
            entity_id=None,
            user_id=user.id,
            new_value={"reason": "inactive"},
            description=f"Login blocked — account inactive: {data.email}",
            ip_address=_ip(http_req),
        )
        db.commit()
        raise HTTPException(status_code=403, detail="This account is inactive")

    # Successful login
    audit_service.log(
        db,
        action="login_success",
        entity_type="auth",
        entity_id=None,
        user_id=user.id,
        description=f"User {data.email} logged in",
        ip_address=_ip(http_req),
    )
    db.commit()

    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/register", status_code=201)
def register(
    user_data: UserCreate,
    http_req: FastAPIRequest,
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed       = get_password_hash(user_data.password)
    default_role = db.query(Role).filter(Role.name == "Requester").first()
    new_user = User(
        email=user_data.email,
        hashed_password=hashed,
        full_name=user_data.full_name,
        role_id=default_role.id if default_role else None,
    )
    db.add(new_user)
    db.flush()

    audit_service.log(
        db,
        action="user_registered",
        entity_type="user",
        entity_id=new_user.id,
        user_id=new_user.id,
        new_value={"email": user_data.email, "full_name": user_data.full_name},
        description=f"New user registered: {user_data.email}",
        ip_address=_ip(http_req),
    )
    db.commit()
    return {"msg": "User created successfully"}
