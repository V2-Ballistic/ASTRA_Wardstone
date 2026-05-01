"""
ASTRA — Reactive Requirement Sync Engine — model layer
=======================================================
File: backend/app/models/req_sync.py   ← NEW (Phase 1, ASTRA-TDD-INTF-002)

Replaces the older single-purpose `InterfaceRequirementLink` (which only
modelled "this auto-req came from this interface entity") with a more general
`RequirementSourceLink` that captures every architectural source for a
requirement (system, LRU, connector, pin, wire, bus, message field, env spec,
catalog part, parent requirement). The fan-out engine in Phase 5 walks these
links to surface `RequirementSyncProposal` rows whenever source data changes.

`InterfaceRequirementLink` itself is kept for one release (deprecated, to be
dropped in 0024 once readers are gone). Migration 0023 backfills the new table
1-to-1 from the old one.
"""

from __future__ import annotations

import enum

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean,
    ForeignKey, Enum as SQLEnum, Index, JSON, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


# JSONB on PostgreSQL, plain JSON on SQLite (test environment).
_JSON = JSON().with_variant(JSONB(), "postgresql")


# ══════════════════════════════════════════════════════════════
#  Enums
# ══════════════════════════════════════════════════════════════

class SourceEntityType(str, enum.Enum):
    SYSTEM         = "system"
    UNIT           = "unit"
    CONNECTOR      = "connector"
    PIN            = "pin"
    INTERFACE      = "interface"
    WIRE_HARNESS   = "wire_harness"
    WIRE           = "wire"
    BUS_DEFINITION = "bus_definition"
    MESSAGE        = "message_definition"
    MESSAGE_FIELD  = "message_field"
    UNIT_ENV_SPEC  = "unit_env_spec"
    CATALOG_PART   = "catalog_part"
    REQUIREMENT    = "requirement"


class SyncProposalType(str, enum.Enum):
    UPDATE_STATEMENT  = "update_statement"
    OBSOLETE          = "obsolete"
    REGENERATE        = "regenerate"


class SyncProposalStatus(str, enum.Enum):
    PENDING          = "pending"
    ACCEPTED         = "accepted"
    REJECTED         = "rejected"
    AUTO_APPLIED     = "auto_applied"
    SUPERSEDED       = "superseded"


_PG_SOURCE_ENTITY_TYPE = "source_entity_type"
_PG_SYNC_PROPOSAL_TYPE = "sync_proposal_type"
_PG_SYNC_PROPOSAL_STATUS = "sync_proposal_status"


# ══════════════════════════════════════════════════════════════
#  RequirementSourceLink
# ══════════════════════════════════════════════════════════════

class RequirementSourceLink(Base):
    """
    The 'this requirement was generated FROM this source' record.

    A requirement can have multiple source links (e.g., a wire requirement
    cites the wire, the harness, and the bus). Roles distinguish primary
    citation from supporting context. Indexed by (entity_type, entity_id) so
    the fan-out engine can locate every dependent requirement in one query
    when source data changes.
    """
    __tablename__ = "requirement_source_links"
    __table_args__ = (
        Index("ix_req_source_link_entity", "source_entity_type", "source_entity_id"),
        Index("ix_req_source_link_req", "requirement_id"),
        UniqueConstraint(
            "requirement_id", "source_entity_type", "source_entity_id",
            name="uq_req_source_unique",
        ),
    )

    id                 = Column(Integer, primary_key=True)
    requirement_id     = Column(
        Integer, ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False
    )
    source_entity_type = Column(
        SQLEnum(
            SourceEntityType,
            name=_PG_SOURCE_ENTITY_TYPE,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    source_entity_id   = Column(Integer, nullable=False)
    template_id        = Column(String(100), nullable=False)
    template_inputs    = Column(_JSON, nullable=False)
    role               = Column(String(50), nullable=False, default="primary")
    last_synced_at     = Column(DateTime(timezone=True), server_default=func.now())

    requirement        = relationship("Requirement")


# ══════════════════════════════════════════════════════════════
#  RequirementSyncProposal
# ══════════════════════════════════════════════════════════════

class RequirementSyncProposal(Base):
    """
    Surfaces when source data changes and an auto-generated requirement no
    longer reflects current reality. The user reviews and accepts / rejects.

    For requirements in `pending_review` status, the fan-out engine
    auto-applies the new content silently and sets `auto_applied=True` plus
    `status=AUTO_APPLIED`. For higher-status requirements, the proposal stays
    `PENDING` until a reviewer acts.
    """
    __tablename__ = "requirement_sync_proposals"
    __table_args__ = (
        Index("ix_req_sync_proposal_status", "status"),
        Index("ix_req_sync_proposal_req", "requirement_id"),
    )

    id                       = Column(Integer, primary_key=True)
    requirement_id           = Column(
        Integer, ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False
    )
    triggered_by_entity_type = Column(
        SQLEnum(
            SourceEntityType,
            name=_PG_SOURCE_ENTITY_TYPE,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    triggered_by_entity_id   = Column(Integer, nullable=False)
    trigger_event            = Column(String(50), nullable=False)

    old_statement            = Column(Text, nullable=False)
    new_statement            = Column(Text, nullable=True)
    old_rationale            = Column(Text, nullable=True)
    new_rationale            = Column(Text, nullable=True)
    field_diffs              = Column(_JSON, nullable=False)

    proposal_type            = Column(
        SQLEnum(
            SyncProposalType,
            name=_PG_SYNC_PROPOSAL_TYPE,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    status                   = Column(
        SQLEnum(
            SyncProposalStatus,
            name=_PG_SYNC_PROPOSAL_STATUS,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=SyncProposalStatus.PENDING,
    )

    auto_applied             = Column(Boolean, default=False)

    created_at               = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at              = Column(DateTime(timezone=True), nullable=True)
    reviewed_by_id           = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewer_notes           = Column(Text, nullable=True)

    requirement              = relationship("Requirement")
