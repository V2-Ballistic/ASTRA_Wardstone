"""
ASTRA — Engineering Frame ICD (CITADEL Vehicle Body Frame)
===========================================================
File: backend/app/models/engineering_frame.py   ← NEW
(ASTRA_CONFIG_ECOSYSTEM_BUILD_SPEC §3 — "build first, everything
references it")

The Frame ICD is the single, versioned definition of the CITADEL
vehicle body frame: datum, axis convention, units, and the rules text
that ties every other numeric surface (CADPORT referencePoint_m_B,
component CG, motor CG offset, aero refPoint_m_B) back to that one
datum. Config bundles stamp ``frame.icdId`` / ``frame.icdRev`` so a
manifest is never ambiguous about which frame its vectors live in.

Design notes
------------
- The ICD header row (``frame_icds``) is the stable identity; the
  actual content lives in immutable ``frame_icd_revisions`` rows.
  "Current" is simply the highest ``rev`` for the ICD — there is no
  mutable "current" pointer to drift.
- Revisions are append-only: a changed datum/axes/units/rules creates
  a NEW revision; existing revisions are never updated in place
  (bundle manifests reference them by (icdId, icdRev) forever).
- This is its own model module (not part of the electrical-interface
  catalog layer): the frame ICD is a vehicle-level engineering
  reference shared by motors / aero / configs, with no relationship
  to suppliers, connectors, or pins.
"""

from __future__ import annotations

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


# Canonical key of the one spec-mandated ICD. Other ICDs are possible
# (the table is generic) but §3 only requires this one.
CITADEL_FRAME_KEY = "citadel-vehicle-body-frame"


class FrameIcd(Base):
    """Identity row for a frame ICD. Content lives in revisions."""

    __tablename__ = "frame_icds"

    id            = Column(Integer, primary_key=True)
    key           = Column(String(100), nullable=False, unique=True, index=True)
    name          = Column(String(255), nullable=False)

    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    revisions     = relationship(
        "FrameIcdRevision",
        back_populates="frame_icd",
        cascade="all, delete-orphan",
        order_by="FrameIcdRevision.rev",
    )

    def __repr__(self) -> str:  # pragma: no cover — debug only
        return f"<FrameIcd {self.key!r} id={self.id}>"


class FrameIcdRevision(Base):
    """One immutable revision of a frame ICD. Never updated in place."""

    __tablename__ = "frame_icd_revisions"
    __table_args__ = (
        UniqueConstraint("frame_icd_id", "rev", name="uq_frame_icd_rev"),
    )

    id            = Column(Integer, primary_key=True)
    frame_icd_id  = Column(
        Integer,
        ForeignKey("frame_icds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rev           = Column(Integer, nullable=False)  # starts at 1

    # PARAMETERIZED — stakeholder unconfirmed; defaults to "OML_nose_tip"
    # at register time (see app/services/engineering/frame.py).
    datum         = Column(String(100), nullable=False)
    axes          = Column(String(100), nullable=False)
    units         = Column(String(20), nullable=False)
    rules         = Column(Text, nullable=False)
    notes         = Column(Text, nullable=True)

    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    frame_icd     = relationship("FrameIcd", back_populates="revisions")

    def __repr__(self) -> str:  # pragma: no cover — debug only
        return f"<FrameIcdRevision icd={self.frame_icd_id} rev={self.rev}>"
