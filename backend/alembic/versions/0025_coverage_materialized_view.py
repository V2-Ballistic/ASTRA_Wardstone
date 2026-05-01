"""INTF-002 Phase 6: source coverage materialized view.

Revision ID: 0025
Revises: 0024
Create Date: 2026-04-30

Per spec §13.4. Materializes the per-requirement source-coverage state used
by ``GET /coverage/source/{project_id}`` so the dashboard doesn't recompute
from raw tables on every load.

Schema rationale (per spec §13)
-------------------------------
Each row carries everything the validator needs to render a per-level
summary + orphan list:

* ``requirement_id``         — PK
* ``project_id``             — for the per-project summary query
* ``level``                  — L1..L5
* ``has_direct_source``      — TRUE iff the requirement has ≥1 link in
                                requirement_source_links
* ``source_link_count``      — # of direct source links (UI hint)
* ``has_traced_parent``      — TRUE iff this requirement is the *source* of a
                                decomposition / satisfaction TraceLink whose
                                target itself has a direct source. The MV
                                only resolves *one* hop — multi-hop coverage
                                propagation happens in Python in the live
                                validator. The MV exists to short-circuit
                                the common 1-hop case at MV-render speed.
* ``has_active_exception``   — TRUE iff a non-expired admin-cosigned
                                CoverageException covers the requirement
* ``computed_severity``      — 'ok' | 'warning' | 'error', applying the
                                §13.2 rules in SQL (so a single GROUP BY can
                                build the per-level traffic light).

Critical schema adaptation (digest §10 anomaly #5)
--------------------------------------------------
The spec §13.4 sample DDL references:
  - ``trace_links.target_requirement_id`` — DOES NOT EXIST. The actual
    schema is polymorphic: ``source_type``, ``source_id``, ``target_type``,
    ``target_id``.
  - ``link_type IN ('derives_from', 'refines')`` — NEITHER VALUE EXISTS.
    The TraceLinkType enum is: SATISFACTION, EVOLUTION, DEPENDENCY,
    RATIONALE, CONTRIBUTION, VERIFICATION, DECOMPOSITION.

We map the spec's intent ("L4 with parent-trace to traced L3") to:
  - source_type='requirement' AND target_type='requirement'
  - link_type IN ('decomposition', 'satisfaction')

``decomposition`` is the closest analog to "derives_from" (a child that
decomposes from a parent), and ``satisfaction`` covers the "refines" intent
(a more specific requirement that satisfies a higher-level one).

Coverage exception column adaptation
------------------------------------
The actual ``coverage_exceptions`` table (created in 0023) names the admin
co-sign columns ``approved_by_id`` / ``approved_at`` — the spec text uses
``admin_cosigned_*``. We treat ``approved_by_id IS NOT NULL`` as "admin
cosigned" and only count rows where ``is_active = TRUE`` AND not expired.

Reversibility
-------------
``downgrade()`` drops the MV (and its three indexes go with it). The
``alembic downgrade -1; alembic upgrade head`` round-trip is the smoke test.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_MV_DDL = """
CREATE MATERIALIZED VIEW mv_requirement_source_coverage AS
WITH direct_sources AS (
    SELECT requirement_id, COUNT(*) AS link_count
      FROM requirement_source_links
     GROUP BY requirement_id
), active_exceptions AS (
    SELECT requirement_id
      FROM coverage_exceptions
     WHERE is_active = TRUE
       AND approved_by_id IS NOT NULL
       AND (expires_at IS NULL OR expires_at > now())
), pending_exceptions AS (
    SELECT requirement_id
      FROM coverage_exceptions
     WHERE is_active = TRUE
       AND approved_by_id IS NULL
       AND (expires_at IS NULL OR expires_at > now())
), traced_parents AS (
    -- The requirement is the *source* of a decomposition / satisfaction
    -- trace link whose *target* has a direct source link or is admin-
    -- cosign exception covered. Mirrors digest §10 anomaly #5 mapping.
    SELECT DISTINCT tl.source_id AS requirement_id
      FROM trace_links tl
     WHERE tl.source_type = 'requirement'
       AND tl.target_type = 'requirement'
       AND tl.link_type IN ('decomposition', 'satisfaction')
       AND (
            tl.target_id IN (SELECT requirement_id FROM direct_sources)
         OR tl.target_id IN (SELECT requirement_id FROM active_exceptions)
       )
)
SELECT r.id                                         AS requirement_id,
       r.project_id                                 AS project_id,
       r.level::text                                AS level,
       (ds.link_count IS NOT NULL)                  AS has_direct_source,
       COALESCE(ds.link_count, 0)::int              AS source_link_count,
       (tp.requirement_id IS NOT NULL)              AS has_traced_parent,
       (ae.requirement_id IS NOT NULL)              AS has_active_exception,
       CASE
           WHEN r.level::text = 'L1'                                  THEN 'ok'
           WHEN ds.link_count > 0                                     THEN 'ok'
           WHEN ae.requirement_id IS NOT NULL                         THEN 'ok'
           WHEN r.level::text = 'L2' AND tp.requirement_id IS NOT NULL THEN 'ok'
           WHEN r.level::text = 'L2'                                  THEN 'warning'
           WHEN r.level::text IN ('L4','L5')
                AND tp.requirement_id IS NOT NULL                     THEN 'ok'
           WHEN r.level::text = 'L5'
                AND pe.requirement_id IS NOT NULL                     THEN 'warning'
           ELSE 'error'
       END                                          AS computed_severity
  FROM requirements r
  LEFT JOIN direct_sources    ds ON ds.requirement_id = r.id
  LEFT JOIN traced_parents    tp ON tp.requirement_id = r.id
  LEFT JOIN active_exceptions ae ON ae.requirement_id = r.id
  LEFT JOIN pending_exceptions pe ON pe.requirement_id = r.id
 WHERE r.status NOT IN ('deleted')
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite (test harness) and other dialects don't support MVs. The
        # validator has a live-mode fallback that's used in tests.
        return

    op.execute(sa.text(_MV_DDL))
    # Unique index is REQUIRED for REFRESH MATERIALIZED VIEW CONCURRENTLY.
    op.execute(sa.text(
        "CREATE UNIQUE INDEX uq_mv_coverage_req "
        "ON mv_requirement_source_coverage (requirement_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX ix_mv_coverage_project "
        "ON mv_requirement_source_coverage (project_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX ix_mv_coverage_severity "
        "ON mv_requirement_source_coverage (computed_severity)"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # DROP MV implicitly drops its indexes.
    op.execute(sa.text("DROP MATERIALIZED VIEW IF EXISTS mv_requirement_source_coverage"))
