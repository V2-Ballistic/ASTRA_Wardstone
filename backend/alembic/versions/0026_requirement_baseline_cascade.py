"""F-205: ondelete=CASCADE on Requirement.project_id and Baseline.project_id

Revision ID: 0026
Revises: 0025
Create Date: 2026-05-01

F-076 (migration 0018) swept ondelete strategies on most FKs but
missed the two largest tables. Both defaulted to PG's NO ACTION:

  * requirements.project_id
  * baselines.project_id

The relationship-side `Project.requirements = relationship(...,
cascade="all, delete-orphan")` only fires for ORM-mediated deletes.
Raw-SQL `DELETE FROM projects WHERE id=...` (admin tooling, future
hard-delete endpoint, retention sweep) raised a constraint violation.

This migration drops the two existing FKs and recreates them with
ON DELETE CASCADE.

Note: AuditLog.project_id was intentionally left at SET NULL in F-076
(see migration 0018) to preserve audit-trail rows after the parent
project disappears (AU-9). That decision is unchanged.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Requirement.project_id → CASCADE
    op.drop_constraint(
        "requirements_project_id_fkey", "requirements", type_="foreignkey",
    )
    op.create_foreign_key(
        "requirements_project_id_fkey", "requirements", "projects",
        ["project_id"], ["id"], ondelete="CASCADE",
    )

    # Baseline.project_id → CASCADE
    op.drop_constraint(
        "baselines_project_id_fkey", "baselines", type_="foreignkey",
    )
    op.create_foreign_key(
        "baselines_project_id_fkey", "baselines", "projects",
        ["project_id"], ["id"], ondelete="CASCADE",
    )


def downgrade() -> None:
    # Restore the pre-F-205 NO ACTION semantics. Note that any project
    # rows that were hard-deleted between upgrade and downgrade will
    # have already lost their requirements/baselines, so this is a
    # one-way ratchet in practice — but the constraint syntax is
    # symmetric.
    op.drop_constraint(
        "requirements_project_id_fkey", "requirements", type_="foreignkey",
    )
    op.create_foreign_key(
        "requirements_project_id_fkey", "requirements", "projects",
        ["project_id"], ["id"],
    )

    op.drop_constraint(
        "baselines_project_id_fkey", "baselines", type_="foreignkey",
    )
    op.create_foreign_key(
        "baselines_project_id_fkey", "baselines", "projects",
        ["project_id"], ["id"],
    )
