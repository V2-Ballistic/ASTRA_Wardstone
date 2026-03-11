"""
ASTRA — Multi-Stage Approval Workflow Models
==============================================
File: backend/app/models/workflow.py   ← NEW

Five tables:
  ApprovalWorkflow   — reusable workflow template scoped to a project
  WorkflowStage      — ordered stages within a template
  WorkflowInstance   — a running execution of a template, bound to an entity
  StageAction        — individual approve/reject actions within a running stage
  ElectronicSignature — password-verified, hash-sealed e-sig for non-repudiation
"""

import enum
import hashlib
from datetime import datetime

from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime, Boolean,
    ForeignKey, Enum as SQLEnum, Index, JSON,
)
from sqlalchemy.orm import relationship
from app.database import Base


# ══════════════════════════════════════
#  Enums
# ══════════════════════════════════════

class WorkflowStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class InstanceStatus(str, enum.Enum):
    PENDING = "pending"           # not yet started
    IN_PROGRESS = "in_progress"   # at least one stage active
    APPROVED = "approved"         # all stages complete
    REJECTED = "rejected"         # any stage rejected
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class StageInstanceStatus(str, enum.Enum):
    WAITING = "waiting"           # not yet reached
    ACTIVE = "active"             # accepting actions
    COMPLETED = "completed"       # required_count met
    REJECTED = "rejected"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"


class SignatureMeaning(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    REVIEWED = "reviewed"
    WITNESSED = "witnessed"


# ══════════════════════════════════════
#  Workflow Template
# ══════════════════════════════════════

class ApprovalWorkflow(Base):
    __tablename__ = "approval_workflows"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    status = Column(SQLEnum(WorkflowStatus), default=WorkflowStatus.ACTIVE)
    entity_type = Column(String(50), default="requirement")   # what this workflow governs
    created_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    project = relationship("Project")
    created_by = relationship("User")
    stages = relationship(
        "WorkflowStage", back_populates="workflow",
        order_by="WorkflowStage.stage_number",
        cascade="all, delete-orphan",
    )
    instances = relationship("WorkflowInstance", back_populates="workflow")


# ══════════════════════════════════════
#  Workflow Stage (template)
# ══════════════════════════════════════

class WorkflowStage(Base):
    __tablename__ = "workflow_stages"

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("approval_workflows.id", ondelete="CASCADE"), nullable=False)
    stage_number = Column(Integer, nullable=False)          # 1-based order
    name = Column(String(255), nullable=False)              # e.g. "Peer Review"
    description = Column(Text, default="")
    required_role = Column(String(50), nullable=True)       # UserRole value or None for any
    required_count = Column(Integer, default=1)             # how many approvals needed
    timeout_hours = Column(Integer, default=0)              # 0 = no timeout
    auto_escalate_to_role = Column(String(50), nullable=True)  # role to notify on timeout
    can_parallel = Column(Boolean, default=False)           # run in parallel with next stage
    require_signature = Column(Boolean, default=True)       # require e-sig at this stage
    created_at = Column(DateTime, default=datetime.utcnow)

    workflow = relationship("ApprovalWorkflow", back_populates="stages")


# ══════════════════════════════════════
#  Workflow Instance (running execution)
# ══════════════════════════════════════

class WorkflowInstance(Base):
    __tablename__ = "workflow_instances"

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("approval_workflows.id"), nullable=False)
    entity_type = Column(String(50), nullable=False)        # "requirement", "baseline", …
    entity_id = Column(Integer, nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    status = Column(SQLEnum(InstanceStatus), default=InstanceStatus.PENDING)
    current_stage_number = Column(Integer, default=1)
    submitted_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    workflow = relationship("ApprovalWorkflow", back_populates="instances")
    project = relationship("Project")
    submitted_by = relationship("User")
    stage_actions = relationship(
        "StageAction", back_populates="instance",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_wf_instance_entity", "entity_type", "entity_id"),
    )


# ══════════════════════════════════════
#  Stage Action (individual approve/reject within a running instance)
# ══════════════════════════════════════

class StageAction(Base):
    __tablename__ = "workflow_stage_actions"

    id = Column(Integer, primary_key=True, index=True)
    instance_id = Column(Integer, ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False)
    stage_number = Column(Integer, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(20), nullable=False)             # "approved" | "rejected" | "reviewed"
    comment = Column(Text, default="")
    signature_id = Column(Integer, ForeignKey("electronic_signatures.id"), nullable=True)
    acted_at = Column(DateTime, default=datetime.utcnow)

    instance = relationship("WorkflowInstance", back_populates="stage_actions")
    user = relationship("User")
    signature = relationship("ElectronicSignature")


# ══════════════════════════════════════
#  Electronic Signature
# ══════════════════════════════════════

class ElectronicSignature(Base):
    __tablename__ = "electronic_signatures"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(Integer, nullable=False)
    signature_meaning = Column(
        SQLEnum(SignatureMeaning), nullable=False,
    )
    statement = Column(
        Text, nullable=False,
        default="I have reviewed and approve this change.",
    )
    password_verified = Column(Boolean, default=False)
    ip_address = Column(String(45), default="")
    user_agent = Column(String(500), default="")
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    signature_hash = Column(String(64), nullable=False, unique=True)

    user = relationship("User")

    __table_args__ = (
        Index("ix_esig_entity", "entity_type", "entity_id"),
    )

    @staticmethod
    def compute_hash(
        user_id: int, entity_type: str, entity_id: int,
        meaning: str, timestamp_iso: str,
    ) -> str:
        payload = f"{user_id}|{entity_type}|{entity_id}|{meaning}|{timestamp_iso}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
