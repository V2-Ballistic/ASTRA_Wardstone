"""
ASTRA — Auto-Requirement Approval Toggle Implementation
==========================================================

This file contains ALL patches needed for the toggle feature.
Each section is clearly marked with the target file and exact placement.

OVERVIEW:
  1. Alembic migration — adds auto_req_approval_required column to projects table
  2. Project model patch — add the column
  3. Project schema patch — add the field to response/update schemas
  4. AutoRequirementGenerator patch — check the toggle before setting status
  5. Settings page — full replacement with toggle UI
  6. Sidebar — conditional visibility of Auto Requirements nav item
"""

# ══════════════════════════════════════════════════════════════
#  1. ALEMBIC MIGRATION
#     Create file: backend/alembic/versions/xxx_add_auto_req_approval.py
#     Or run: alembic revision --autogenerate -m "add auto_req_approval_required"
# ══════════════════════════════════════════════════════════════

MIGRATION_SQL = """
-- Run this in your PostgreSQL database, or let Alembic handle it:
ALTER TABLE projects ADD COLUMN IF NOT EXISTS auto_req_approval_required BOOLEAN DEFAULT TRUE;
"""


# ══════════════════════════════════════════════════════════════
#  2. PROJECT MODEL PATCH
#     File: backend/app/models/__init__.py
#     Find the Project class, add this column after the 'config' line:
# ══════════════════════════════════════════════════════════════

PROJECT_MODEL_PATCH = '''
# ADD this line to the Project class in backend/app/models/__init__.py
# Insert after:  config = Column(JSON, default={})
# Insert before: created_at = Column(DateTime, default=datetime.utcnow)

    auto_req_approval_required = Column(Boolean, default=True)
'''


# ══════════════════════════════════════════════════════════════
#  3. PROJECT SCHEMA PATCH
#     File: backend/app/schemas/__init__.py
#     Add the field to ProjectResponse so GET /projects/{id} returns it.
#     Add the field to a ProjectUpdate schema so PATCH accepts it.
# ══════════════════════════════════════════════════════════════

PROJECT_SCHEMA_PATCH = '''
# In ProjectResponse, add:
    auto_req_approval_required: bool = True

# If you don't have a ProjectUpdate schema yet, add one:
class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = None
    auto_req_approval_required: Optional[bool] = None
'''


# ══════════════════════════════════════════════════════════════
#  4. AUTO-REQUIREMENT GENERATOR PATCH
#     File: backend/app/services/interface/auto_requirements.py
#     Modify the _create_requirement method
# ══════════════════════════════════════════════════════════════

AUTO_REQ_GENERATOR_PATCH = '''
# In AutoRequirementGenerator._create_requirement(), find this line:
#     status="pending_review",
#
# REPLACE with:

        # Check project-level approval toggle
        project = self.db.query(Project).filter(Project.id == self.project_id).first()
        approval_required = getattr(project, 'auto_req_approval_required', True) if project else True
        req_status = "pending_review" if approval_required else "draft"
        link_status = "pending_review" if approval_required else "approved"

# Then use req_status instead of the hardcoded "pending_review":
        req = Requirement(
            ...
            status=req_status,        # ← was "pending_review"
            ...
        )

# And for the InterfaceRequirementLink, use link_status:
            link = InterfaceRequirementLink(
                ...
                status=link_status,   # ← was "pending_review"
                ...
            )

# Also add this import at the top of auto_requirements.py if not present:
#   from app.models import Project

# When approval_required is False and status is "draft", also auto-create
# trace links immediately (same logic as the approve endpoint):
        if not approval_required and req.parent_id:
            from app.models import TraceLink
            existing = self.db.query(TraceLink).filter(
                TraceLink.source_type == "requirement",
                TraceLink.source_id == req.id,
                TraceLink.target_type == "requirement",
                TraceLink.target_id == req.parent_id,
                TraceLink.link_type == "derives_from",
            ).first()
            if not existing:
                trace = TraceLink(
                    source_type="requirement",
                    source_id=req.id,
                    target_type="requirement",
                    target_id=req.parent_id,
                    link_type="derives_from",
                    description=f"Auto-traced: {req.req_id} derives from parent (auto-approved)",
                    status="active",
                    created_by_id=self.user.id,
                )
                self.db.add(trace)
'''
