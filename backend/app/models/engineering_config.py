"""
ASTRA — Engineering Configurations tracker (HAROLD-named, CFG)
==============================================================
File: backend/app/models/engineering_config.py   ← NEW
(ASTRA_CONFIG_ECOSYSTEM_BUILD_SPEC §8 — Configurations tracker,
§9 — CITADEL bundle export storage)

``vehicle_configs`` is the stable identity row (one per HAROLD CFG
base index); ``vehicle_config_revisions`` is the IMMUTABLE history —
every change to a config's BOM / aero binding / stage map is a new
revision with HAROLD's next ``-REV`` letter. A persisted revision is
never mutated.

``config_bundle_exports`` records every CITADEL bundle export of a
config revision (§9). The bundle directory + zip are content-addressed
by the deterministic ``bundle_hash``;
UNIQUE(config_wpn, rev_letter, bundle_hash) makes lookup by hash
unambiguous, so historical bundles are retrievable without re-export.

Identity notes (same contract as motors / aero):
- ``vehicle_configs.wpn`` stores the BASE identity WPN exactly as
  HAROLD issued it for revision A (e.g. ``WS-CFG-P000001-A``). The
  base *index* + ``system_code`` identify the config across its life.
- Every ``vehicle_config_revisions.wpn`` is HAROLD's response
  verbatim. Nothing here computes a WPN.
- ``active_revision_id`` is a plain Integer; the real FK
  (fk_vehicle_configs_active_revision → vehicle_config_revisions.id,
  ON DELETE SET NULL) is added post-create by migration 0047 to break
  the FK cycle — the ORM keeps it FK-free because SQLite (test
  engine) cannot execute the ALTER a ``use_alter`` FK would emit
  during ``Base.metadata.create_all`` (same pattern as 0045/0046).
"""

from __future__ import annotations

from sqlalchemy import (
    Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

# JSONB on PostgreSQL, generic JSON on SQLite (test env).
_JSON = JSON().with_variant(JSONB(), "postgresql")


class VehicleConfig(Base):
    """Stable identity of a vehicle configuration (one HAROLD CFG
    base index)."""

    __tablename__ = "vehicle_configs"

    id                 = Column(Integer, primary_key=True)
    #: HAROLD-issued base WPN, verbatim (e.g. ``WS-CFG-P000001-A``).
    wpn                = Column(String(64), nullable=False, unique=True, index=True)
    #: The ``P<NNNNNN>`` index from HAROLD's ledger entry
    #: (``part_number_int``) — never derived locally.
    base_index         = Column(Integer, nullable=True, index=True)
    system_code        = Column(String(8), nullable=False, default="CFG")
    name               = Column(String(500), nullable=False, index=True)
    #: Published-revision pointer; plain Integer (see module docstring).
    active_revision_id = Column(Integer, nullable=True)

    created_by_id      = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at         = Column(DateTime(timezone=True), server_default=func.now())
    updated_at         = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    revisions = relationship(
        "VehicleConfigRevision",
        back_populates="config",
        cascade="all, delete-orphan",
        foreign_keys="VehicleConfigRevision.vehicle_config_id",
        order_by="VehicleConfigRevision.id",
    )
    active_revision = relationship(
        "VehicleConfigRevision",
        primaryjoin=(
            "VehicleConfig.active_revision_id == "
            "foreign(VehicleConfigRevision.id)"
        ),
        uselist=False,
        viewonly=True,
    )

    def __repr__(self) -> str:  # pragma: no cover — debug only
        return f"<VehicleConfig {self.wpn!r} name={self.name!r}>"


class VehicleConfigRevision(Base):
    """One IMMUTABLE config revision — never updated in place; a
    change is a NEW row with HAROLD's next ``-REV`` letter.

    JSON column shapes (validated at save time by
    ``app.services.engineering.config_service``):

    components   list of {role, wpn, rev?, name, placement? (4×4
                 nested list, row-major homogeneous transform),
                 notes?}; role from the closed §1 set.
    aero_binding {wpn, rev_letter} or NULL.
    stage_map    ordered [{stageNum, motorWpn, motorRevLetter,
                 ignitionTime_s, thrustAxis_B[3], mcTrialId?}].
    rollup       {totalMass_kg, cg_m_B[3], inertia_kgm2_B[3][3],
                 referencePoint_m_B[3], method: "parallel_axis"} —
                 computed at save time.
    validation   {warnings: [...]} — non-fatal findings recorded at
                 save time (fatal findings are 422s and never persist).
    """

    __tablename__ = "vehicle_config_revisions"
    __table_args__ = (
        UniqueConstraint(
            "vehicle_config_id", "rev_letter",
            name="uq_vehicle_config_revision_letter",
        ),
        Index("ix_vehicle_config_revisions_config", "vehicle_config_id"),
    )

    id                = Column(Integer, primary_key=True)
    vehicle_config_id = Column(
        Integer,
        ForeignKey("vehicle_configs.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: FULL HAROLD-issued WPN incl. revision letter, verbatim.
    wpn               = Column(String(64), nullable=False, unique=True, index=True)
    rev_letter        = Column(String(8), nullable=False)
    description       = Column(Text, nullable=True)
    top_assembly_wpn  = Column(String(64), nullable=True)

    # Frame stamp (spec §3): the ICD id + the immutable revision number
    # every vector in this config revision is expressed against.
    frame_icd_id      = Column(
        Integer, ForeignKey("frame_icds.id"), nullable=False,
    )
    frame_icd_rev     = Column(Integer, nullable=False)

    astra_baseline_id = Column(
        Integer, ForeignKey("baselines.id", ondelete="SET NULL"), nullable=True,
    )

    components        = Column(_JSON, nullable=False)
    aero_binding      = Column(_JSON, nullable=True)
    stage_map         = Column(_JSON, nullable=False, default=list)
    rollup            = Column(_JSON, nullable=False)
    validation        = Column(_JSON, nullable=False, default=dict)
    notes             = Column(Text, nullable=True)

    created_by_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_utc       = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    config = relationship(
        "VehicleConfig",
        back_populates="revisions",
        foreign_keys=[vehicle_config_id],
    )
    frame_icd = relationship("FrameIcd", foreign_keys=[frame_icd_id])
    bundle_exports = relationship(
        "ConfigBundleExport",
        back_populates="config_revision",
        cascade="all, delete-orphan",
        order_by="ConfigBundleExport.id",
    )

    def __repr__(self) -> str:  # pragma: no cover — debug only
        return f"<VehicleConfigRevision {self.wpn!r}>"


class ConfigBundleExport(Base):
    """One CITADEL bundle export of a config revision (spec §9).

    Content-addressed: ``bundle_hash`` is the deterministic hash (see
    ``bundle_export.compute_deterministic_bundle_hash``) — re-export of
    the same revision yields the SAME hash, and the
    UNIQUE(config_wpn, rev_letter, bundle_hash) constraint makes a
    repeat export idempotent (the existing row is returned) while
    keeping lookup-by-hash unambiguous for the retrieval endpoints.
    """

    __tablename__ = "config_bundle_exports"
    __table_args__ = (
        UniqueConstraint(
            "config_wpn", "rev_letter", "bundle_hash",
            name="uq_config_bundle_exports_hash",
        ),
        Index(
            "ix_config_bundle_exports_revision",
            "vehicle_config_revision_id",
        ),
    )

    id                         = Column(Integer, primary_key=True)
    vehicle_config_revision_id = Column(
        Integer,
        ForeignKey("vehicle_config_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    config_wpn      = Column(String(64), nullable=False, index=True)
    rev_letter      = Column(String(8), nullable=False)
    bundle_hash     = Column(String(64), nullable=False, index=True)
    bundle_dirname  = Column(String(200), nullable=False)
    manifest        = Column(_JSON, nullable=False)
    zip_path        = Column(Text, nullable=False)
    artifact_count  = Column(Integer, nullable=False)

    created_by_id   = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_utc     = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    config_revision = relationship(
        "VehicleConfigRevision", back_populates="bundle_exports",
    )

    def __repr__(self) -> str:  # pragma: no cover — debug only
        return (
            f"<ConfigBundleExport {self.config_wpn}-{self.rev_letter} "
            f"{self.bundle_hash[:8]}>"
        )
