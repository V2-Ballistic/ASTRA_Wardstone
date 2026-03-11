"""
ASTRA — Admin Router (Audit-Instrumented)
==========================================
File: backend/app/routers/admin.py   ← REPLACES existing

Adds record_event() to all user management and project-member operations.
"""

from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole, Project
from app.services.auth import get_current_user
from app.services.audit_service import record_event

try:
    from app.models.project_member import ProjectMember
except ImportError:
    ProjectMember = None

try:
    from app.services.rbac import require_permission, require_any_role
    from app.services.auth_providers.local import get_password_hash
except ImportError:
    from app.services.auth import get_password_hash
    def require_permission(action):
        return get_current_user
    def require_any_role(*roles):
        return get_current_user

router = APIRouter(prefix="/admin", tags=["Admin"])


# ── Schemas ──

class AdminUserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str
    role: str = "developer"
    department: Optional[str] = None

class AdminUserUpdate(BaseModel):
    role: Optional[str] = None
    full_name: Optional[str] = None
    department: Optional[str] = None
    is_active: Optional[bool] = None

class UserResponse(BaseModel):
    id: int; username: str; email: str; full_name: str
    role: str; department: Optional[str]; is_active: bool
    created_at: datetime
    class Config:
        from_attributes = True

class ProjectMemberAdd(BaseModel):
    user_id: int
    role_override: Optional[str] = None

class ProjectMemberResponse(BaseModel):
    id: int; project_id: int; user_id: int; role_override: Optional[str]
    added_at: datetime; username: Optional[str] = None; full_name: Optional[str] = None
    class Config:
        from_attributes = True


# ══════════════════════════════════════
#  User management  ← AUDITED
# ══════════════════════════════════════

@router.post("/users", response_model=UserResponse, status_code=201,
             dependencies=[Depends(require_permission("users.manage"))])
def create_user(data: AdminUserCreate, request: Request,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(400, "Username already taken")
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(400, "Email already registered")
    valid_roles = [r.value for r in UserRole]
    if data.role not in valid_roles:
        raise HTTPException(400, f"Invalid role. Must be one of: {valid_roles}")

    user = User(username=data.username, email=data.email,
                hashed_password=get_password_hash(data.password),
                full_name=data.full_name, role=data.role,
                department=data.department)
    db.add(user)
    db.commit()
    db.refresh(user)

    record_event(db, "user.created", "user", user.id, current_user.id,
                 {"username": user.username, "role": user.role}, request=request)
    return user


@router.get("/users", response_model=List[UserResponse],
            dependencies=[Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER))])
def list_users(db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    return db.query(User).order_by(User.id).all()


@router.patch("/users/{user_id}", response_model=UserResponse,
              dependencies=[Depends(require_permission("users.manage"))])
def update_user(user_id: int, data: AdminUserUpdate, request: Request,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    update = data.model_dump(exclude_unset=True)
    if "role" in update and update["role"]:
        valid = [r.value for r in UserRole]
        if update["role"] not in valid:
            raise HTTPException(400, f"Invalid role. Must be one of: {valid}")

    changes = {}
    for field, value in update.items():
        old = getattr(user, field)
        old_str = old.value if hasattr(old, "value") else str(old)
        if str(old_str) != str(value):
            changes[field] = {"old": old_str, "new": str(value)}
        setattr(user, field, value)
    db.commit()
    db.refresh(user)

    if changes:
        record_event(db, "user.updated", "user", user_id, current_user.id,
                     {"changes": changes}, request=request)
    return user


@router.delete("/users/{user_id}", status_code=200,
               dependencies=[Depends(require_permission("users.manage"))])
def deactivate_user(user_id: int, request: Request,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == current_user.id:
        raise HTTPException(400, "Cannot deactivate yourself")
    user.is_active = False
    db.commit()

    record_event(db, "user.deactivated", "user", user_id, current_user.id,
                 {"username": user.username}, request=request)
    return {"status": "deactivated", "user_id": user_id, "username": user.username}


# ══════════════════════════════════════
#  Project members  ← AUDITED
# ══════════════════════════════════════

@router.post("/projects/{project_id}/members", response_model=ProjectMemberResponse,
             status_code=201,
             dependencies=[Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER))])
def add_project_member(project_id: int, data: ProjectMemberAdd, request: Request,
                       db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    if not ProjectMember:
        raise HTTPException(501, "Project member feature not available")
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if db.query(ProjectMember).filter(ProjectMember.project_id == project_id,
                                       ProjectMember.user_id == data.user_id).first():
        raise HTTPException(400, "User is already a member")

    member = ProjectMember(project_id=project_id, user_id=data.user_id,
                           role_override=data.role_override, added_by_id=current_user.id)
    db.add(member)
    db.commit()
    db.refresh(member)

    record_event(db, "project_member.added", "project", project_id, current_user.id,
                 {"added_user_id": data.user_id, "username": user.username},
                 project_id=project_id, request=request)

    return ProjectMemberResponse(
        id=member.id, project_id=member.project_id, user_id=member.user_id,
        role_override=member.role_override, added_at=member.added_at,
        username=user.username, full_name=user.full_name,
    )


@router.get("/projects/{project_id}/members", response_model=List[ProjectMemberResponse],
            dependencies=[Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER))])
def list_project_members(project_id: int, db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    if not ProjectMember:
        return []
    members = db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()
    return [ProjectMemberResponse(
        id=m.id, project_id=m.project_id, user_id=m.user_id,
        role_override=m.role_override, added_at=m.added_at,
        username=(db.query(User).filter(User.id == m.user_id).first() or User(username="?")).username,
        full_name=(db.query(User).filter(User.id == m.user_id).first() or User(full_name="?")).full_name,
    ) for m in members]


@router.delete("/projects/{project_id}/members/{user_id}", status_code=204,
               dependencies=[Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER))])
def remove_project_member(project_id: int, user_id: int, request: Request,
                          db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    if not ProjectMember:
        raise HTTPException(501, "Project member feature not available")
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
    ).first()
    if not member:
        raise HTTPException(404, "Project member not found")
    db.delete(member)
    db.commit()

    record_event(db, "project_member.removed", "project", project_id, current_user.id,
                 {"removed_user_id": user_id},
                 project_id=project_id, request=request)
