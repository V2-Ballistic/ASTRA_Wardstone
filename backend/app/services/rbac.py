"""
ASTRA — Role-Based Access Control (RBAC) Service
=================================================
Provides permission matrix, FastAPI dependencies for enforcing
role-based access, and project membership checks.
"""

from typing import List, Callable
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole
from app.services.auth import get_current_user


# ══════════════════════════════════════
#  Permission Matrix
# ══════════════════════════════════════
# Maps each role to a set of allowed actions.

PERMISSION_MATRIX: dict[UserRole, set[str]] = {
    UserRole.ADMIN: {
        "requirements.create",
        "requirements.update",
        "requirements.delete",
        "requirements.approve",
        "requirements.baseline",
        "baselines.create",
        "baselines.delete",
        "traceability.create",
        "traceability.delete",
        "projects.create",
        "projects.update",
        "users.manage",
        "settings.manage",
        "reports.export",
        "imports.execute",
    },
    UserRole.PROJECT_MANAGER: {
        "requirements.create",
        "requirements.update",
        "requirements.delete",
        "requirements.approve",
        "requirements.baseline",
        "baselines.create",
        "baselines.delete",
        "traceability.create",
        "traceability.delete",
        "projects.create",
        "projects.update",
        "reports.export",
        "imports.execute",
    },
    UserRole.REQUIREMENTS_ENGINEER: {
        "requirements.create",
        "requirements.update",
        "traceability.create",
        "traceability.delete",
        "reports.export",
    },
    UserRole.REVIEWER: {
        "requirements.approve",
    },
    UserRole.STAKEHOLDER: {
        # Read-only + comments (handled at the endpoint level).
        # No write actions granted here.
    },
    UserRole.DEVELOPER: {
        # Read-only requirements; can update verification status.
        # Verification updates are a special case handled via
        # the verification endpoints, not as a generic action.
    },
}


def _get_roles_for_action(action: str) -> List[UserRole]:
    """Return all roles that are allowed to perform *action*."""
    return [role for role, perms in PERMISSION_MATRIX.items() if action in perms]


def has_permission(user: User, action: str) -> bool:
    """Check whether *user* has permission to perform *action*."""
    try:
        role = UserRole(user.role) if isinstance(user.role, str) else user.role
    except ValueError:
        return False
    return action in PERMISSION_MATRIX.get(role, set())


# ══════════════════════════════════════
#  FastAPI Dependencies
# ══════════════════════════════════════

def require_permission(action: str) -> Callable:
    """
    Returns a FastAPI dependency that checks the current user
    has permission for *action*.

    Usage:
        @router.post("/", dependencies=[Depends(require_permission("requirements.create"))])
        def create_requirement(...):
            ...
    """

    def _dependency(current_user: User = Depends(get_current_user)):
        if has_permission(current_user, action):
            return current_user

        required_roles = _get_roles_for_action(action)
        role_names = ", ".join(r.value for r in required_roles) or "none"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions: {action} requires role {role_names}",
        )

    return _dependency


def require_any_role(*roles: UserRole) -> Callable:
    """
    Returns a FastAPI dependency that checks the current user
    has one of the specified roles.

    Usage:
        @router.get("/", dependencies=[Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER))])
        def admin_list(...):
            ...
    """

    def _dependency(current_user: User = Depends(get_current_user)):
        try:
            user_role = UserRole(current_user.role) if isinstance(current_user.role, str) else current_user.role
        except ValueError:
            user_role = None

        if user_role in roles:
            return current_user

        role_names = ", ".join(r.value for r in roles)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions: requires one of [{role_names}]",
        )

    return _dependency


def require_project_member(project_id_param: str = "project_id") -> Callable:
    """
    Returns a FastAPI dependency that checks the user is assigned
    to the project (or is an ADMIN who bypasses the check).

    The *project_id_param* is the name of the path/query parameter
    holding the project id. The dependency pulls it from **kwargs.

    Usage (path param):
        @router.get("/{project_id}")
        def get_something(
            project_id: int,
            member: User = Depends(require_project_member()),
        ):
            ...
    """
    from app.models.project_member import ProjectMember  # avoid circular import

    def _dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
        project_id: int = 0,
    ):
        # Admins bypass project-membership checks
        try:
            user_role = UserRole(current_user.role) if isinstance(current_user.role, str) else current_user.role
        except ValueError:
            user_role = None

        if user_role == UserRole.ADMIN:
            return current_user

        if project_id == 0:
            # If project_id wasn't injected (e.g. body-only), skip check
            return current_user

        membership = (
            db.query(ProjectMember)
            .filter(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == current_user.id,
            )
            .first()
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this project",
            )
        return current_user

    return _dependency
