from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_superuser: bool
    role_id: int | None
    role_name: str | None = None
    permissions: list[str] = []
    department_id: int | None = None
    role_type: str = "Officer"

    class Config:
        from_attributes = True

class UserAdminCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role_id: int | None = None
    department_id: int | None = None

class UserAdminUpdate(BaseModel):
    full_name: str | None = None
    role_id: int | None = None
    is_active: bool | None = None
    password: str | None = None
    department_id: int | None = None

class RoleResponse(BaseModel):
    id: int
    name: str
    permissions: list[str]
    role_type: str = "Officer"

    class Config:
        from_attributes = True

class RoleCreate(BaseModel):
    name: str
    permissions: list[str] = []
    role_type: str = "Officer"

class DepartmentCreate(BaseModel):
    name: str
    manager_id: int | None = None

class DepartmentUpdate(BaseModel):
    name: str | None = None
    manager_id: int | None = None
