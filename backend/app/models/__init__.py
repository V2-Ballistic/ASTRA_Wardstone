from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, ForeignKey,
    Enum as SQLEnum, Float, JSON
)
from sqlalchemy.orm import relationship
from app.database import Base
import enum


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
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.DEVELOPER)
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
    config = Column(JSON, default={})  # Project-specific settings
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
    req_type = Column(SQLEnum(RequirementType), nullable=False)
    priority = Column(SQLEnum(RequirementPriority), nullable=False, default=RequirementPriority.MEDIUM)
    status = Column(SQLEnum(RequirementStatus), nullable=False, default=RequirementStatus.DRAFT)
    version = Column(Integer, default=1)
    quality_score = Column(Float, default=0.0)

    # Hierarchy
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

    # Unique constraint per project
    __table_args__ = (
        # Each req_id must be unique within a project
    )


class SourceArtifact(Base):
    __tablename__ = "source_artifacts"

    id = Column(Integer, primary_key=True, index=True)
    artifact_id = Column(String(50), nullable=False, index=True)  # e.g., "SA-INT-001"
    title = Column(String(500), nullable=False)
    artifact_type = Column(SQLEnum(ArtifactType), nullable=False)
    description = Column(Text)
    file_path = Column(String(500))  # Path to uploaded file
    source_date = Column(DateTime)
    participants = Column(JSON, default=[])  # List of participant names
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
    source_type = Column(String(50), nullable=False)  # "requirement", "source_artifact", "verification"
    source_id = Column(Integer, nullable=False)
    target_type = Column(String(50), nullable=False)
    target_id = Column(Integer, nullable=False)
    link_type = Column(SQLEnum(TraceLinkType), nullable=False)
    description = Column(Text)
    status = Column(String(20), default="active")
    created_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    created_by = relationship("User")


class Verification(Base):
    __tablename__ = "verifications"

    id = Column(Integer, primary_key=True, index=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)
    method = Column(SQLEnum(VerificationMethod), nullable=False)
    status = Column(SQLEnum(VerificationStatus), nullable=False, default=VerificationStatus.PLANNED)
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
    name = Column(String(255), nullable=False)  # e.g., "v1.0 Release Baseline"
    description = Column(Text)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    snapshot = Column(JSON, nullable=False)  # Full snapshot of all req versions
    created_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    project = relationship("Project", back_populates="baselines")
    created_by = relationship("User")


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
