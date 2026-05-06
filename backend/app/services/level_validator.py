"""
ASTRA — L0 Level Validation Helpers
=====================================
File: backend/app/services/level_validator.py

Enforces business rules specific to L0 (Customer/Contractual) requirements:
  1. L0 reqs MUST link to a source artifact (MRD, SOW, contract clause).
  2. L0 reqs are edit-restricted to users with role='admin' after creation.

Called from the requirements router on create/update/delete.

NIST 800-53: AC-3 (Access Enforcement), AU-2 (Audit Events for L0 changes)
"""

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Requirement, SourceArtifact, User


def validate_l0_source_artifact(
    db: Session,
    level: str,
    source_artifact_id: Optional[int],
) -> None:
    """
    Reject creation/update of an L0 requirement that has no linked source artifact.

    Raises:
        HTTPException 400 if level=='L0' and source_artifact_id is missing or invalid.
    """
    # Coerce enum to string so callers can pass either RequirementLevel or str.
    level_value = level.value if hasattr(level, "value") else str(level)

    if level_value != "L0":
        return  # Only L0 is gated

    if source_artifact_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "L0 (Customer/Contractual) requirements must link to a source "
                "artifact (e.g. MRD, SOW, contract clause). "
                "Provide 'source_artifact_id' referencing the originating document."
            ),
        )

    artifact = db.query(SourceArtifact).filter(
        SourceArtifact.id == source_artifact_id
    ).first()
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Source artifact id={source_artifact_id} not found.",
        )


def enforce_l0_admin_only(
    requirement: Requirement,
    current_user: User,
    operation: str = "modify",
) -> None:
    """
    Block non-admin users from editing or deleting an existing L0 requirement.

    Admins always pass. All other roles (PM, requirements_engineer, reviewer,
    stakeholder, developer) are blocked.

    Raises:
        HTTPException 403 if requirement.level == 'L0' and user is not admin.
    """
    # Coerce enum to string for both ORM enum and string columns
    level_value = (
        requirement.level.value
        if hasattr(requirement.level, "value")
        else str(requirement.level)
    )

    if level_value != "L0":
        return  # Only L0 is gated

    role_value = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role)
    )

    if role_value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"L0 (Customer/Contractual) requirements are admin-only. "
                f"Cannot {operation} requirement '{requirement.req_id}' as role '{role_value}'. "
                f"Submit a change request to an admin."
            ),
        )
