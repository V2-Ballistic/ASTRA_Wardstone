"""
ASTRA — Project Access Control Dependency
==========================================
File: backend/app/dependencies/project_access.py

Single FastAPI dependency that any router can apply to require the
caller is the project owner, a ProjectMember, or has UserRole.ADMIN.

Two flavors:
  - project_member_required        → reads project_id from the path/query
  - entity_project_member_required → resolves project_id from a loaded entity

Both raise HTTP 403 ("Not a project member") on miss, HTTP 404 on a
missing project, and return the loaded Project on success. Membership
lookup is cached per-request via request.state so multiple deps in the
same call don't re-query.

Covers AUDIT_FINDINGS F-014 (and unblocks F-046, F-051, F-052, F-058).
"""

from typing import Any, Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, User, UserRole
from app.models.project_member import ProjectMember
from app.services.auth import get_current_user


# ══════════════════════════════════════
#  Helpers
# ══════════════════════════════════════


def _is_admin(user: User) -> bool:
    try:
        role = UserRole(user.role) if isinstance(user.role, str) else user.role
    except ValueError:
        return False
    return role == UserRole.ADMIN


def _check_membership(db: Session, project_id: int, user: User) -> Project:
    """
    Returns the Project on success. Raises 404 if missing, 403 if the
    caller is neither owner, member, nor ADMIN.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    if _is_admin(user):
        return project

    if project.owner_id == user.id:
        return project

    is_member = (
        db.query(ProjectMember.id)
        .filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user.id,
        )
        .first()
    )
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a project member",
        )
    return project


def _cached_membership(
    request: Request, db: Session, project_id: int, user: User
) -> Project:
    """Per-request cache so multiple deps in the same call don't re-query."""
    key = f"_project_access_{project_id}_{user.id}"
    cached = getattr(request.state, key, None)
    if cached is not None:
        return cached
    project = _check_membership(db, project_id, user)
    setattr(request.state, key, project)
    return project


# ══════════════════════════════════════
#  Public dependencies
# ══════════════════════════════════════


def project_member_required(
    request: Request,
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Project:
    """
    FastAPI dependency for endpoints whose ``project_id`` lives in the
    path or query string.

    Usage::

        @router.get("/{project_id}/items")
        def list_items(
            project_id: int,
            project: Project = Depends(project_member_required),
        ):
            ...

    For body-supplied project_ids prefer moving to the query string.
    If the body is the only place project_id can live, use
    ``entity_project_member_required`` with a resolver that reads the
    body (via ``await request.json()``).
    """
    return _cached_membership(request, db, project_id, current_user)


def entity_project_member_required(
    project_id_resolver: Callable[[Request, Session], int],
) -> Callable[..., Project]:
    """
    Dependency factory for endpoints whose project_id must be resolved
    from a loaded entity (e.g. ``requirement_id`` → ``requirement.project_id``).

    *project_id_resolver* is called with ``(request, db)`` and must return
    the project_id (or raise ``HTTPException(404)`` if the entity is
    missing). The resolver typically reads a path parameter via
    ``request.path_params`` and looks up the entity.

    Usage::

        def _resolve_req_project(request: Request, db: Session) -> int:
            req_id = int(request.path_params["req_id"])
            req = db.query(Requirement).filter(Requirement.id == req_id).first()
            if not req:
                raise HTTPException(404, "Requirement not found")
            return req.project_id

        @router.patch("/requirements/{req_id}")
        def update_req(
            req_id: int,
            data: ReqUpdate,
            project: Project = Depends(
                entity_project_member_required(_resolve_req_project)
            ),
            ...
        ):
            ...
    """

    def _dep(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ) -> Project:
        project_id = project_id_resolver(request, db)
        return _cached_membership(request, db, project_id, current_user)

    return _dep


# ══════════════════════════════════════
#  Convenience resolvers (commonly needed)
# ══════════════════════════════════════


def resolve_project_for_requirement(request: Request, db: Session) -> int:
    """Path: .../requirements/{req_id}. Returns the project_id."""
    from app.models import Requirement

    raw = request.path_params.get("req_id")
    if raw is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing req_id in path")
    try:
        req_id = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid req_id")

    req = db.query(Requirement.project_id).filter(Requirement.id == req_id).first()
    if not req:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Requirement not found")
    return req[0]


def resolve_project_for_baseline(request: Request, db: Session) -> int:
    """Path: .../baselines/{baseline_id}. Returns the project_id."""
    from app.models import Baseline

    raw = request.path_params.get("baseline_id")
    if raw is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing baseline_id in path")
    try:
        baseline_id = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid baseline_id")

    row = (
        db.query(Baseline.project_id).filter(Baseline.id == baseline_id).first()
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Baseline not found")
    return row[0]


def resolve_project_for_artifact(request: Request, db: Session) -> int:
    """Path: .../artifacts/{artifact_id}. Returns the project_id."""
    from app.models import SourceArtifact

    raw = request.path_params.get("artifact_id")
    if raw is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing artifact_id in path")
    try:
        artifact_id = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid artifact_id")

    row = (
        db.query(SourceArtifact.project_id)
        .filter(SourceArtifact.id == artifact_id)
        .first()
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found")
    return row[0]
