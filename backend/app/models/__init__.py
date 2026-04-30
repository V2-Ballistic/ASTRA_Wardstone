from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, ForeignKey,
    Enum as SQLEnum, Float, JSON, Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.database import Base
import enum

from app.models.interface import (
    System, Unit, Connector, Pin, BusDefinition, PinBusAssignment,
    MessageDefinition, MessageField, WireHarness, Wire, Interface,
    UnitEnvironmentalSpec, InterfaceRequirementLink,
    AutoRequirementLog, InterfaceChangeImpact,
)

# Workflow + e-signature models — re-exported here so consumers can write
# `from app.models import ApprovalWorkflow` (covers AUDIT_FINDINGS F-138 and
# unblocks the workflow router that now lives at app/routers/workflows.py).
from app.models.workflow import (
    ApprovalWorkflow, WorkflowStage, WorkflowInstance, StageAction,
    ElectronicSignature,
    WorkflowStatus, InstanceStatus, StageInstanceStatus, SignatureMeaning,
)

# ══════════════════════════════════════
#  Enums
# ══════════════════════════════════════

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    PROJECT_MANAGER = "project_manager"
    REQUIREMENTS_ENGINEER = "requirements_engineer"
    REVIEWER = "reviewer"
    STAKEHOLDER = "stakeholder"
    DEVELOPER = "developer"


class RequirementType(str, enum.Enum):
    FUNCTIONAL = "functional"
    PERFORMANCE = "performance"
    INTERFACE = "interface"
    ENVIRONMENTAL = "environmental"
    CONSTRAINT = "constraint"
    SAFETY = "safety"
    SECURITY = "security"
    RELIABILITY = "reliability"
    MAINTAINABILITY = "maintainability"
    DERIVED = "derived"


class RequirementPriority(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RequirementLevel(str, enum.Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"


class RequirementStatus(str, enum.Enum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    BASELINED = "baselined"
    IMPLEMENTED = "implemented"
    VERIFIED = "verified"
    VALIDATED = "validated"
    DEFERRED = "deferred"
    DELETED = "deleted"
    PENDING_REVIEW = "pending_review"
    AUTO_GENERATED = "auto_generated"


class ArtifactType(str, enum.Enum):
    INTERVIEW = "interview"
    MEETING = "meeting"
    DECISION = "decision"
    STANDARD = "standard"
    LEGACY = "legacy"
    EMAIL = "email"
    MULTIMEDIA = "multimedia"
    DOCUMENT = "document"


class TraceLinkType(str, enum.Enum):
    SATISFACTION = "satisfaction"
    EVOLUTION = "evolution"
    DEPENDENCY = "dependency"
    RATIONALE = "rationale"
    CONTRIBUTION = "contribution"
    VERIFICATION = "verification"
    DECOMPOSITION = "decomposition"


class VerificationMethod(str, enum.Enum):
    TEST = "test"
    ANALYSIS = "analysis"
    INSPECTION = "inspection"
    DEMONSTRATION = "demonstration"


class VerificationStatus(str, enum.Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    PASS = "pass"
    FAIL = "fail"


# ══════════════════════════════════════
#  Models
# ══════════════════════════════════════

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole, values_callable=lambda x: [e.value for e in x]), nullable=False, default=UserRole.DEVELOPER)
    department = Column(String(100))
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owned_projects = relationship("Project", back_populates="owner")
    owned_requirements = relationship("Requirement", back_populates="owner", foreign_keys="Requirement.owner_id")
    comments = relationship("Comment", back_populates="author")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, nullable=False, index=True)  # e.g., "PROJ-ALPHA"
    name = Column(String(255), nullable=False)
    description = Column(Text)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(50), default="active")
    config = Column(JSON, default=dict)  # Project-specific settings
    auto_req_approval_required = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owner = relationship("User", back_populates="owned_projects")
    requirements = relationship("Requirement", back_populates="project", cascade="all, delete-orphan")
    source_artifacts = relationship("SourceArtifact", back_populates="project", cascade="all, delete-orphan")
    baselines = relationship("Baseline", back_populates="project", cascade="all, delete-orphan")


class Requirement(Base):
    __tablename__ = "requirements"

    id = Column(Integer, primary_key=True, index=True)
    req_id = Column(String(50), nullable=False, index=True)  # e.g., "FR-AUTH-001"
    title = Column(String(500), nullable=False)
    statement = Column(Text, nullable=False)
    rationale = Column(Text)
    req_type = Column(SQLEnum(RequirementType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    priority = Column(SQLEnum(RequirementPriority, values_callable=lambda x: [e.value for e in x]), nullable=False, default=RequirementPriority.MEDIUM)
    status = Column(SQLEnum(RequirementStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=RequirementStatus.DRAFT)
    version = Column(Integer, default=1)
    quality_score = Column(Float, default=0.0)

    # Hierarchy
    level = Column(SQLEnum(RequirementLevel, values_callable=lambda x: [e.value for e in x]), nullable=False, default=RequirementLevel.L1)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("requirements.id"), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_id = Column(Integer, ForeignKey("users.id"))

    # Relationships
    project = relationship("Project", back_populates="requirements")
    owner = relationship("User", back_populates="owned_requirements", foreign_keys=[owner_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    parent = relationship("Requirement", remote_side=[id], backref="children")
    verifications = relationship("Verification", back_populates="requirement", cascade="all, delete-orphan")
    history = relationship("RequirementHistory", back_populates="requirement", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="requirement", cascade="all, delete-orphan")

    __table_args__ = (
        # F-075: req_id must be unique within a project. Pre-fix this
        # was just a comment — duplicates could be inserted indefinitely.
        UniqueConstraint("project_id", "req_id", name="uq_req_per_project"),
        # F-075: composite indexes for the dashboard / list filters.
        # The first two are also created by migration 0002; migration
        # 0017 promotes the (project_id, req_id) one to UNIQUE and adds
        # the missing (project_id, owner_id) one.
        Index("ix_req_project_status", "project_id", "status"),
        Index("ix_req_project_type", "project_id", "req_type"),
        Index("ix_req_project_owner", "project_id", "owner_id"),
    )


class SourceArtifact(Base):
    __tablename__ = "source_artifacts"

    id = Column(Integer, primary_key=True, index=True)
    artifact_id = Column(String(50), nullable=False, index=True)  # e.g., "SA-INT-001"
    title = Column(String(500), nullable=False)
    artifact_type = Column(SQLEnum(ArtifactType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    description = Column(Text)
    file_path = Column(String(500))  # Path to uploaded file
    source_date = Column(DateTime)
    participants = Column(JSON, default=list)  # List of participant names
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    project = relationship("Project", back_populates="source_artifacts")
    created_by = relationship("User")


class TraceLink(Base):
    __tablename__ = "trace_links"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    source_type = Column(String(50), nullable=False)  # "requirement", "source_artifact", "verification"
    source_id = Column(Integer, nullable=False)
    target_type = Column(String(50), nullable=False)
    target_id = Column(Integer, nullable=False)
    link_type = Column(SQLEnum(TraceLinkType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    description = Column(Text)
    status = Column(String(20), default="active")
    created_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    created_by = relationship("User")
    project = relationship("Project")

    __table_args__ = (
        UniqueConstraint(
            "source_type", "source_id", "target_type", "target_id", "link_type",
            name="uq_trace_link_endpoints",
        ),
        Index("ix_trace_links_project", "project_id"),
        Index("ix_trace_links_source_pair", "source_type", "source_id"),
        Index("ix_trace_links_target_pair", "target_type", "target_id"),
    )


class Verification(Base):
    __tablename__ = "verifications"

    id = Column(Integer, primary_key=True, index=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)
    method = Column(SQLEnum(VerificationMethod, values_callable=lambda x: [e.value for e in x]), nullable=False)
    status = Column(SQLEnum(VerificationStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=VerificationStatus.PLANNED)
    responsible_id = Column(Integer, ForeignKey("users.id"))
    evidence = Column(Text)  # Reference to test results, analysis docs, etc.
    criteria = Column(Text)  # Pass/fail criteria
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    requirement = relationship("Requirement", back_populates="verifications")
    responsible = relationship("User")


class RequirementHistory(Base):
    __tablename__ = "requirement_history"

    id = Column(Integer, primary_key=True, index=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)
    version = Column(Integer, nullable=False)
    field_changed = Column(String(100), nullable=False)
    old_value = Column(Text)
    new_value = Column(Text)
    change_description = Column(Text)
    changed_by_id = Column(Integer, ForeignKey("users.id"))
    changed_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    requirement = relationship("Requirement", back_populates="history")
    changed_by = relationship("User")


class Baseline(Base):
    __tablename__ = "baselines"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)  # e.g., "PDR Baseline v1.0"
    description = Column(Text)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    requirements_count = Column(Integer, default=0)
    created_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    project = relationship("Project", back_populates="baselines")
    created_by = relationship("User")
    requirements = relationship("BaselineRequirement", back_populates="baseline", cascade="all, delete-orphan")


class BaselineRequirement(Base):
    __tablename__ = "baseline_requirements"

    id = Column(Integer, primary_key=True, index=True)
    baseline_id = Column(Integer, ForeignKey("baselines.id"), nullable=False)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)

    # Frozen field snapshots at time of baseline
    req_id_snapshot = Column(String(50), nullable=False)
    title_snapshot = Column(String(500), nullable=False)
    statement_snapshot = Column(Text)
    rationale_snapshot = Column(Text)
    status_snapshot = Column(String(30), nullable=False)
    level_snapshot = Column(String(5), nullable=False)
    type_snapshot = Column(String(50))
    priority_snapshot = Column(String(20))
    quality_score_snapshot = Column(Float, default=0.0)
    version_snapshot = Column(Integer, default=1)
    parent_id_snapshot = Column(Integer, nullable=True)

    # Relationships
    baseline = relationship("Baseline", back_populates="requirements")
    requirement = relationship("Requirement")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    parent_id = Column(Integer, ForeignKey("comments.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    requirement = relationship("Requirement", back_populates="comments")
    author = relationship("User", back_populates="comments")
    parent = relationship("Comment", remote_side=[id], backref="replies")