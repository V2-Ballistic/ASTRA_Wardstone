"""F-076: ondelete strategies on core FKs (Project, SourceArtifact,
Verification, RequirementHistory, AuditLog)

Revision ID: 0018
Revises: 0017
Create Date: 2026-04-30

Pre-fix every core-model ForeignKey defaulted to NO ACTION / RESTRICT —
deleting a User who owned a Project, or a Project that owned an artifact,
errored out instead of doing the right thing. This migration aligns
the FK delete strategies with the model intent:

  * `projects.owner_id`            : SET NULL (column made nullable)
      Deleting a User shouldn't orphan their Projects' history; SET NULL
      keeps the row intact so audit trails / report archives still
      resolve.
  * `source_artifacts.project_id`  : CASCADE
  * `source_artifacts.created_by_id`: SET NULL
  * `verifications.requirement_id`  : CASCADE
  * `verifications.responsible_id`  : SET NULL
  * `requirement_history.requirement_id`: CASCADE
  * `audit_log.project_id`          : SET NULL
  * `audit_log.user_id`             : SET NULL (column made nullable)
      AU-9 immutability is about the row not changing — see migration
      0010 triggers — not about the FK targets persisting. Letting a
      user be deleted without nuking the audit trail is the right call.

Interface-module FKs (interface.py) are NOT swept in this migration.
That sweep needs more thought (cascading project-deletes through
~15 interface tables has implications) and is tracked for Phase 3.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (constraint_name, table, [columns], referenced_table, ondelete)
_NEW_FKS = [
    ("projects_owner_id_fkey", "projects", ["owner_id"], "users", "SET NULL"),
    ("source_artifacts_project_id_fkey", "source_artifacts", ["project_id"], "projects", "CASCADE"),
    ("source_artifacts_created_by_id_fkey", "source_artifacts", ["created_by_id"], "users", "SET NULL"),
    ("verifications_requirement_id_fkey", "verifications", ["requirement_id"], "requirements", "CASCADE"),
    ("verifications_responsible_id_fkey", "verifications", ["responsible_id"], "users", "SET NULL"),
    ("requirement_history_requirement_id_fkey", "requirement_history", ["requirement_id"], "requirements", "CASCADE"),
    ("audit_log_project_id_fkey", "audit_log", ["project_id"], "projects", "SET NULL"),
    ("audit_log_user_id_fkey", "audit_log", ["user_id"], "users", "SET NULL"),
]


def upgrade() -> None:
    # Make the columns that are being switched to SET NULL actually
    # nullable.
    op.alter_column("projects", "owner_id", nullable=True)
    op.alter_column("audit_log", "user_id", nullable=True)

    for name, table, cols, ref, ondelete in _NEW_FKS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            name, table, ref, cols, ["id"], ondelete=ondelete,
        )


def downgrade() -> None:
    # Restore the legacy NO-ACTION strategies. Ordering doesn't matter
    # because we drop+recreate each constraint independently.
    for name, table, cols, ref, _ in _NEW_FKS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, ref, cols, ["id"])
    op.alter_column("audit_log", "user_id", nullable=False)
    op.alter_column("projects", "owner_id", nullable=False)
