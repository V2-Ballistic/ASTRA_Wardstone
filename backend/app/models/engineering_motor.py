"""
ASTRA — Engineering Motors (solid rocket motors, HAROLD-named)
==============================================================
File: backend/app/models/engineering_motor.py   ← NEW
(ASTRA_CONFIG_ECOSYSTEM_BUILD_SPEC §5 — Motors tab backend)

``motors`` is the stable identity row (one per HAROLD base index for
the ``MTR`` system code); ``motor_revisions`` is the IMMUTABLE history
— every new piece of data (CSV re-upload, design re-run) becomes a new
revision with the next HAROLD ``-REV`` letter. A published revision is
never mutated: there are no UPDATE endpoints on revisions, and the
router never writes to an existing ``motor_revisions`` row.

Identity notes
--------------
- ``motors.wpn`` stores the BASE identity WPN exactly as HAROLD issued
  it for the first revision (e.g. ``WS-MTR-P000001-A``). The base
  *index* (``base_index``) plus ``system_code`` identify the motor
  across its life — revisions bump the letter, never the index.
- ``motors.wpn`` and every ``motor_revisions.wpn`` come from HAROLD
  verbatim (spec §2). Nothing in this module computes a WPN; the
  ``base_index`` column is populated from HAROLD's ledger entry
  (``part_number_int``), not derived locally.
- ``active_revision_id`` is the motor's published pointer (what the
  catalog entry reflects). Nullable + ``use_alter`` because of the
  motors ↔ motor_revisions FK cycle.
"""

from __future__ import annotations

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Float, ForeignKey, JSON,
    Index, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

# JSONB on PostgreSQL, generic JSON on SQLite (test env) — same
# pattern as app/models/catalog.py.
_JSON = JSON().with_variant(JSONB(), "postgresql")


class Motor(Base):
    """Stable identity of a solid motor (one HAROLD MTR base index)."""

    __tablename__ = "motors"

    id                 = Column(Integer, primary_key=True)
    #: HAROLD-issued base WPN, verbatim (e.g. ``WS-MTR-P000001-A``).
    wpn                = Column(String(32), nullable=False, unique=True, index=True)
    #: The ``P<NNNNNN>`` index from HAROLD's ledger entry — stored so
    #: lineage queries don't need to re-parse the WPN string.
    base_index         = Column(Integer, nullable=False, index=True)
    system_code        = Column(String(8), nullable=False, default="MTR")
    name               = Column(String(255), nullable=False, index=True)
    #: Computed letter (¹⁄₈A…O, 'P+') from the active revision's total
    #: impulse. Denormalized for the list view.
    motor_class        = Column(String(8), nullable=True)
    #: Published-revision pointer. The REAL foreign key
    #: (fk_motors_active_revision → motor_revisions.id, ON DELETE SET
    #: NULL) is added by migration 0045 with a post-create ALTER to
    #: break the motors ↔ motor_revisions cycle. The ORM keeps this a
    #: plain Integer because SQLite (the test engine) cannot execute
    #: ALTER TABLE ADD CONSTRAINT, which a ``use_alter`` FK would emit
    #: during ``Base.metadata.create_all``.
    active_revision_id = Column(Integer, nullable=True)
    catalog_part_id    = Column(
        Integer,
        ForeignKey("catalog_parts.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_by_id      = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at         = Column(DateTime(timezone=True), server_default=func.now())
    updated_at         = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    revisions = relationship(
        "MotorRevision",
        back_populates="motor",
        cascade="all, delete-orphan",
        foreign_keys="MotorRevision.motor_id",
        order_by="MotorRevision.id",
    )
    active_revision = relationship(
        "MotorRevision",
        primaryjoin="Motor.active_revision_id == foreign(MotorRevision.id)",
        uselist=False,
        viewonly=True,
    )
    catalog_part = relationship("CatalogPart", foreign_keys=[catalog_part_id])

    def __repr__(self) -> str:  # pragma: no cover — debug only
        return f"<Motor {self.wpn!r} name={self.name!r}>"


class MotorRevision(Base):
    """One IMMUTABLE motor revision. Never updated in place — new data
    means a new row with HAROLD's next ``-REV`` letter."""

    __tablename__ = "motor_revisions"
    __table_args__ = (
        UniqueConstraint("motor_id", "rev_letter", name="uq_motor_revision_letter"),
        Index("ix_motor_revisions_motor", "motor_id"),
    )

    id                  = Column(Integer, primary_key=True)
    motor_id            = Column(
        Integer,
        ForeignKey("motors.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Full HAROLD WPN incl. revision letter (e.g. ``WS-MTR-P000001-B``).
    wpn                 = Column(String(32), nullable=False, unique=True, index=True)
    rev_letter          = Column(String(4), nullable=False)
    #: 'design' | 'csv'
    origin              = Column(String(16), nullable=False)

    # Design-origin provenance (NULL for csv-origin revisions).
    design_inputs       = Column(_JSON, nullable=True)

    # CSV-origin provenance (NULL for design-origin revisions). The raw
    # CSV text is retained verbatim so a revision is always
    # re-derivable from its source.
    source_csv_filename = Column(String(500), nullable=True)
    source_csv_sha256   = Column(String(64), nullable=True)
    source_csv_text     = Column(Text, nullable=True)

    #: The normalized motor artifact (spec §5.4) — the whole point.
    artifact            = Column(_JSON, nullable=False)
    artifact_sha256     = Column(String(64), nullable=False)

    # Derived scalars (denormalized from the artifact for list views).
    total_impulse_ns    = Column(Float, nullable=True)
    peak_thrust_n       = Column(Float, nullable=True)
    burn_time_s         = Column(Float, nullable=True)
    isp_s               = Column(Float, nullable=True)

    #: 'workable' | 'good' | 'excellent'
    quality_tier        = Column(String(16), nullable=False)
    defaulted_fields    = Column(_JSON, nullable=True)
    warnings            = Column(_JSON, nullable=True)
    notes               = Column(Text, nullable=True)

    created_by_id       = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_utc         = Column(DateTime(timezone=True), server_default=func.now())

    motor = relationship(
        "Motor", back_populates="revisions", foreign_keys=[motor_id]
    )

    def __repr__(self) -> str:  # pragma: no cover — debug only
        return f"<MotorRevision {self.wpn!r} origin={self.origin!r}>"
