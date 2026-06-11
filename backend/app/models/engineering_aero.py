"""ASTRA — Engineering hub: Aero Decks (spec §6).

HAROLD-named (system code ``AER``) aero-deck identities with immutable
revisions, mirroring the Motors module shape:

  aero_decks           — the identity (base WPN, no revision letter)
  aero_deck_revisions  — immutable snapshots; each carries the FULL
                         HAROLD-issued WPN (``WS-AER-Pxxxxxx-A``), the
                         raw source text, and the normalized
                         ``astra-aero-deck/1.0`` deck artifact.

Revisions are append-only: no endpoint mutates a persisted revision —
corrections are a new revision via HAROLD's ``/wpn/{wpn}/revise``.

NOTE (deliberate deviation, documented): aero decks get NO
``catalog_parts`` row. They are engineering data products, not
procurable parts — the catalog layer models suppliers/LRUs, none of
which applies to a coefficient deck.
"""
from __future__ import annotations

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String,
    Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

# JSONB on PostgreSQL, plain JSON on SQLite (test environment).
_JSON = JSON().with_variant(JSONB(), "postgresql")


class AeroDeck(Base):
    """Aero-deck identity. ``wpn`` is the BASE WPN (HAROLD's issued
    WPN with the revision suffix removed) — the full per-revision WPNs
    live on ``aero_deck_revisions``."""

    __tablename__ = "aero_decks"

    id = Column(Integer, primary_key=True, index=True)

    # HAROLD identity — base WPN, e.g. "WS-AER-P000001". NEVER
    # computed locally: derived by stripping HAROLD's own revision
    # letter from HAROLD's issued WPN.
    wpn = Column(String(64), nullable=False, unique=True, index=True)
    base_index = Column(Integer, nullable=True)
    system_code = Column(String(8), nullable=False, default="AER")

    name = Column(String(500), nullable=False)
    oml_wpn = Column(String(64), nullable=True)

    # The revision served by default (artifact / preview). use_alter
    # breaks the FK cycle with aero_deck_revisions.
    active_revision_id = Column(
        Integer,
        ForeignKey(
            "aero_deck_revisions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_aero_decks_active_revision_id",
        ),
        nullable=True,
    )

    created_by_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )

    revisions = relationship(
        "AeroDeckRevision",
        back_populates="deck_parent",
        foreign_keys="AeroDeckRevision.aero_deck_id",
        cascade="all, delete-orphan",
        order_by="AeroDeckRevision.id",
    )
    active_revision = relationship(
        "AeroDeckRevision",
        foreign_keys=[active_revision_id],
        post_update=True,
    )


class AeroDeckRevision(Base):
    """Immutable aero-deck revision. Append-only — rows are never
    updated after commit; a correction is a NEW revision issued by
    HAROLD (same index, next letter)."""

    __tablename__ = "aero_deck_revisions"
    __table_args__ = (
        UniqueConstraint(
            "aero_deck_id", "rev_letter",
            name="uq_aero_deck_revisions_deck_rev",
        ),
        Index("ix_aero_deck_revisions_aero_deck_id", "aero_deck_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    aero_deck_id = Column(
        Integer,
        ForeignKey("aero_decks.id", ondelete="CASCADE"),
        nullable=False,
    )

    # FULL HAROLD-issued WPN for this revision, verbatim.
    wpn = Column(String(64), nullable=False, unique=True, index=True)
    rev_letter = Column(String(8), nullable=False)

    # Provenance: raw sources, preserved.
    source_filenames = Column(_JSON, nullable=False, default=list)
    source_sha256s = Column(_JSON, nullable=False, default=list)
    # JSON-encoded list of the raw source texts (one entry per file).
    source_text = Column(Text, nullable=True)

    # The normalized artifact (astra-aero-deck/1.0) + canonical hash.
    deck = Column(_JSON, nullable=False)
    deck_sha256 = Column(String(64), nullable=False)

    # Denormalized envelope for the list view.
    mach_min = Column(Float, nullable=True)
    mach_max = Column(Float, nullable=True)
    alpha_min_deg = Column(Float, nullable=True)
    alpha_max_deg = Column(Float, nullable=True)
    sref_m2 = Column(Float, nullable=True)
    lref_m = Column(Float, nullable=True)

    defaulted_fields = Column(_JSON, nullable=False, default=list)
    warnings = Column(_JSON, nullable=False, default=list)
    notes = Column(Text, nullable=True)

    created_by_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    created_utc = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    deck_parent = relationship(
        "AeroDeck",
        back_populates="revisions",
        foreign_keys=[aero_deck_id],
    )

    # NOTE: 'deck' is the JSON column; the parent relationship is
    # named deck_parent to avoid the collision.
