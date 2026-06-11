"""ASTRA_CONFIG_ECOSYSTEM_BUILD_SPEC §9 — CITADEL bundle export storage.

Revision ID: 0048
Revises: 0047
Create Date: 2026-06-10

Creates ``config_bundle_exports`` — one row per CITADEL bundle export
of a config revision. The bundle is content-addressed by the
deterministic ``bundle_hash`` (volatile manifest fields normalized
out), so UNIQUE(config_wpn, rev_letter, bundle_hash) both dedups
identical re-exports and makes the retrieval endpoints'
lookup-by-hash unambiguous. ``zip_path`` points at the stable-byte
zip on disk; ``manifest`` retains the full manifest JSON so history
is servable even without touching disk.

All DDL uses IF NOT EXISTS — safe to run on a populated DB and
re-runnable. Hand-written per Mason's standing rule (no autogenerate).
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0048"
down_revision: Union[str, None] = "0047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS config_bundle_exports (
            id                          SERIAL PRIMARY KEY,
            vehicle_config_revision_id  INTEGER NOT NULL
                                            REFERENCES vehicle_config_revisions(id)
                                            ON DELETE CASCADE,
            config_wpn      VARCHAR(64)  NOT NULL,
            rev_letter      VARCHAR(8)   NOT NULL,
            bundle_hash     VARCHAR(64)  NOT NULL,
            bundle_dirname  VARCHAR(200) NOT NULL,
            manifest        JSONB        NOT NULL,
            zip_path        TEXT         NOT NULL,
            artifact_count  INTEGER      NOT NULL,
            created_by_id   INTEGER      NOT NULL REFERENCES users(id),
            created_utc     TIMESTAMPTZ  NOT NULL DEFAULT now(),
            CONSTRAINT uq_config_bundle_exports_hash
                UNIQUE (config_wpn, rev_letter, bundle_hash)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_config_bundle_exports_revision "
        "ON config_bundle_exports (vehicle_config_revision_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_config_bundle_exports_config_wpn "
        "ON config_bundle_exports (config_wpn)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_config_bundle_exports_bundle_hash "
        "ON config_bundle_exports (bundle_hash)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS config_bundle_exports")
