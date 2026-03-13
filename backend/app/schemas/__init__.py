from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ══════════════════════════════════════
#  Auth Schemas
# ══════════════════════════════════════

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    username: Optional[str] = None

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str
    role: str = "developer"
    department: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: str
    role: str
    department: Optional[str]
    is_active: bool
    created_at: datetime
    class Config:
        from_attributes = True


# ══════════════════════════════════════
#  Project Schemas
# ══════════════════════════════════════

class ProjectCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=20)
    name: str = Field(..., max_length=255)
    description: Optional[str] = None

class ProjectResponse(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str]
    owner_id: int
    status: str
    created_at: datetime
    class Config:
        from_attributes = True


# ══════════════════════════════════════
#  Requirement Schemas
# ══════════════════════════════════════

class RequirementCreate(BaseModel):
    title: str = Field(..., max_length=500)
    statement: str = Field(..., min_length=10)
    rationale: Optional[str] = None
    req_type: str = "functional"
    priority: str = "medium"
    level: str = "L1"
    parent_id: Optional[int] = None

class RequirementUpdate(BaseModel):
    title: Optional[str] = None
    statement: Optional[str] = None
    rationale: Optional[str] = None
    req_type: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    level: Optional[str] = None
    parent_id: Optional[int] = None

class RequirementResponse(BaseModel):
    id: int
    req_id: str
    title: str
    statement: str
    rationale: Optional[str]
    req_type: str
    priority: str
    status: str
    level: str
    version: int
    quality_score: float
    project_id: int
    parent_id: Optional[int]
    owner_id: int
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True

class RequirementDetail(RequirementResponse):
    owner: Optional[UserResponse] = None
    children: List["RequirementResponse"] = []
    verifications: list = []
    trace_count: int = 0
    verification_status: Optional[str] = None


# ══════════════════════════════════════
#  Source Artifact Schemas
# ══════════════════════════════════════

class SourceArtifactCreate(BaseModel):
    title: str = Field(..., max_length=500)
    artifact_type: str
    description: Optional[str] = None
    source_date: Optional[datetime] = None
    participants: List[str] = []

class SourceArtifactResponse(BaseModel):
    id: int
    artifact_id: str
    title: str
    artifact_type: str
    description: Optional[str]
    file_path: Optional[str]
    source_date: Optional[datetime]
    participants: list
    project_id: int
    created_at: datetime
    class Config:
        from_attributes = True


# ══════════════════════════════════════
#  Trace Link Schemas
# ══════════════════════════════════════

class TraceLinkCreate(BaseModel):
    source_type: str
    source_id: int
    target_type: str
    target_id: int
    link_type: str
    description: Optional[str] = None

class TraceLinkResponse(BaseModel):
    id: int
    source_type: str
    source_id: int
    target_type: str
    target_id: int
    link_type: str
    description: Optional[str]
    status: str
    created_at: datetime
    class Config:
        from_attributes = True


# ══════════════════════════════════════
#  Verification Schemas
# ══════════════════════════════════════

class VerificationCreate(BaseModel):
    requirement_id: int
    method: str  # test, analysis, inspection, demonstration
    criteria: Optional[str] = None
    responsible_id: Optional[int] = None

class VerificationUpdate(BaseModel):
    status: Optional[str] = None
    evidence: Optional[str] = None
    criteria: Optional[str] = None

class VerificationResponse(BaseModel):
    id: int
    requirement_id: int
    method: str
    status: str
    responsible_id: Optional[int]
    evidence: Optional[str]
    criteria: Optional[str]
    completed_at: Optional[datetime]
    created_at: datetime
    class Config:
        from_attributes = True


# ══════════════════════════════════════
#  Quality Check Response
# ══════════════════════════════════════

class QualityCheckResult(BaseModel):
    score: float
    passed: bool
    warnings: List[str] = []
    suggestions: List[str] = []


# ══════════════════════════════════════
#  Dashboard / Stats
# ══════════════════════════════════════

class DashboardStats(BaseModel):
    total_requirements: int
    by_status: dict
    by_type: dict
    by_level: dict
    verified_count: int
    avg_quality_score: float
    total_trace_links: int
    orphan_count: int
    recent_activity: list
