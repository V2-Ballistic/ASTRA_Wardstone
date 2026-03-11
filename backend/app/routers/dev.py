"""
ASTRA — Dev Router (RBAC-patched)
==================================
Changes from original:
  - seed_database now creates 6 users with different roles
  - Adds all users as project members
  - Returns credentials for each test user
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db, Base, engine
from app.models import User, Project, Requirement
from app.models.project_member import ProjectMember
from app.services.auth import get_password_hash
from app.services.quality_checker import check_requirement_quality

router = APIRouter(prefix="/dev", tags=["Development"])


SAMPLE_REQUIREMENTS = [
    {
        "title": "Structured Requirement Form",
        "statement": "The system shall provide a structured form for capturing requirements with fields for title, statement, rationale, type, and priority.",
        "rationale": "Structured input ensures consistency and completeness across all requirements.",
        "req_type": "functional",
        "priority": "high",
    },
    {
        "title": "Auto-Generate Hierarchical IDs",
        "statement": "The system shall automatically generate unique hierarchical requirement IDs based on project code and requirement type.",
        "rationale": "Automated ID generation prevents duplicates and ensures a consistent naming convention.",
        "req_type": "functional",
        "priority": "high",
    },
    {
        "title": "Source Artifact Management",
        "statement": "The system shall allow users to create, view, and link source artifacts such as interviews, meeting notes, and standards to requirements.",
        "rationale": "Tracing requirements back to their origin ensures completeness and supports auditing.",
        "req_type": "functional",
        "priority": "high",
    },
    {
        "title": "Backward Traceability Links",
        "statement": "The system shall support creating trace links from requirements back to source artifacts with categorized link types.",
        "rationale": "Backward traceability is mandated by NASA NPR 7150.2 and DO-178C.",
        "req_type": "functional",
        "priority": "high",
    },
    {
        "title": "NASA Appendix C Editorial Checks",
        "statement": "The system shall perform automated quality checks on requirement statements based on NASA Appendix C editorial guidelines.",
        "rationale": "Automated checks reduce review cycles and catch common quality issues early.",
        "req_type": "functional",
        "priority": "high",
    },
    {
        "title": "Prohibited Terms Detection",
        "statement": "The system shall flag requirement statements that contain prohibited or ambiguous terms such as shall not, adequate, and appropriate.",
        "rationale": "Ambiguous language leads to misinterpretation and increases defect rates.",
        "req_type": "functional",
        "priority": "medium",
    },
    {
        "title": "Interactive Traceability Graph",
        "statement": "The system shall display an interactive directed graph showing traceability relationships between requirements, artifacts, and verification records.",
        "rationale": "Visual traceability aids in impact analysis and completeness reviews.",
        "req_type": "functional",
        "priority": "high",
    },
    {
        "title": "Automated Impact Analysis",
        "statement": "The system shall identify and display all directly and transitively linked items when a requirement is modified or deleted.",
        "rationale": "Impact analysis prevents unintended side effects when requirements change.",
        "req_type": "functional",
        "priority": "critical",
    },
    {
        "title": "Page Load Under 2 Seconds",
        "statement": "The system shall render any page within 2 seconds under normal operating conditions with up to 50 concurrent users.",
        "rationale": "Performance targets ensure usability and user adoption.",
        "req_type": "performance",
        "priority": "high",
    },
    {
        "title": "User Authentication (bcrypt + JWT)",
        "statement": "The system shall authenticate users via username and password with bcrypt hashing and issue JWT tokens for session management.",
        "rationale": "Secure authentication protects sensitive requirements data from unauthorized access.",
        "req_type": "security",
        "priority": "critical",
    },
    {
        "title": "RESTful API over HTTPS",
        "statement": "The system shall expose all functionality through a RESTful API served over HTTPS with JSON request and response bodies.",
        "rationale": "A standard API enables integration with external tools and future automation.",
        "req_type": "interface",
        "priority": "high",
    },
    {
        "title": "Internal Linux Server Deployment",
        "statement": "The system shall be deployable on an internal Linux server using Docker containers with no external cloud dependencies.",
        "rationale": "Self-hosted deployment satisfies air-gapped and ITAR-restricted environments.",
        "req_type": "environmental",
        "priority": "high",
    },
    {
        "title": "Requirement Version History",
        "statement": "The system shall maintain a complete version history of all changes to requirement fields including the user, timestamp, and previous value.",
        "rationale": "Full audit trails are required for configuration management and compliance.",
        "req_type": "functional",
        "priority": "high",
    },
    {
        "title": "Role-Based Access Control",
        "statement": "The system shall enforce role-based access control with at least four roles: admin, project manager, requirements engineer, and reviewer.",
        "rationale": "Access control prevents unauthorized modifications and supports separation of duties.",
        "req_type": "security",
        "priority": "high",
    },
    {
        "title": "Baseline Snapshot Creation",
        "statement": "The system shall allow project managers to create named baseline snapshots that capture the state of all requirements at a point in time.",
        "rationale": "Baselines provide a frozen reference for reviews, audits, and milestone tracking.",
        "req_type": "functional",
        "priority": "medium",
    },
]


# ══════════════════════════════════════
#  Test Users — one per role
# ══════════════════════════════════════

SEED_USERS = [
    {"username": "mason",     "email": "mason@astra.local",     "full_name": "Mason (Admin)",           "role": "admin",                  "department": "Systems Engineering"},
    {"username": "priya",     "email": "priya@astra.local",     "full_name": "Priya (PM)",              "role": "project_manager",        "department": "Program Office"},
    {"username": "chen",      "email": "chen@astra.local",      "full_name": "Chen (Req Engineer)",     "role": "requirements_engineer",  "department": "Systems Engineering"},
    {"username": "jess",      "email": "jess@astra.local",      "full_name": "Jess (Reviewer)",         "role": "reviewer",               "department": "Quality Assurance"},
    {"username": "hank",      "email": "hank@astra.local",      "full_name": "Hank (Stakeholder)",      "role": "stakeholder",            "department": "Customer Programs"},
    {"username": "dev_alex",  "email": "dev_alex@astra.local",  "full_name": "Alex (Developer)",        "role": "developer",              "department": "Software Engineering"},
]

DEFAULT_PASSWORD = "password123"


@router.post("/seed")
def seed_database(db: Session = Depends(get_db)):
    """Seed the database with test users (all roles), a project, and sample requirements."""

    # Check if already seeded
    existing_user = db.query(User).filter(User.username == "mason").first()
    if existing_user:
        project = db.query(Project).filter(Project.owner_id == existing_user.id).first()
        req_count = db.query(Requirement).filter(Requirement.project_id == project.id).count() if project else 0
        user_count = db.query(User).count()
        return {
            "status": "already_seeded",
            "user_count": user_count,
            "project_id": project.id if project else None,
            "project_code": project.code if project else None,
            "requirements_count": req_count,
            "credentials": {u["username"]: DEFAULT_PASSWORD for u in SEED_USERS},
        }

    # ── Create all test users ──
    users = {}
    for u in SEED_USERS:
        user = User(
            username=u["username"],
            email=u["email"],
            hashed_password=get_password_hash(DEFAULT_PASSWORD),
            full_name=u["full_name"],
            role=u["role"],
            department=u["department"],
        )
        db.add(user)
        db.flush()
        users[u["username"]] = user

    admin_user = users["mason"]

    # ── Create project ──
    project = Project(
        code="SMDS",
        name="Satellite Missile Deployment System",
        description="Requirements tracker for satellite-deployed kinetic interceptor system",
        owner_id=admin_user.id,
        status="active",
    )
    db.add(project)
    db.flush()

    # ── Add all users as project members ──
    for username, user in users.items():
        member = ProjectMember(
            project_id=project.id,
            user_id=user.id,
            added_by_id=admin_user.id,
        )
        db.add(member)

    # ── Create requirements ──
    TYPE_PREFIX = {
        "functional": "FR",
        "performance": "PR",
        "security": "SR",
        "interface": "IR",
        "environmental": "ER",
    }
    type_counters = {}

    statuses = ["draft", "under_review", "approved", "baselined", "approved",
                 "draft", "under_review", "approved", "baselined", "approved",
                 "baselined", "approved", "under_review", "approved", "draft"]

    levels = ["L1", "L1", "L2", "L2", "L2",
              "L3", "L2", "L2", "L2", "L1",
              "L2", "L1", "L3", "L2", "L3"]

    for i, sample in enumerate(SAMPLE_REQUIREMENTS):
        req_type = sample["req_type"]
        prefix = TYPE_PREFIX.get(req_type, "GR")
        type_counters[req_type] = type_counters.get(req_type, 0) + 1
        req_id = f"{prefix}-{project.code}-{type_counters[req_type]:03d}"

        quality = check_requirement_quality(sample["statement"], sample["title"], sample.get("rationale", ""))

        req = Requirement(
            req_id=req_id,
            title=sample["title"],
            statement=sample["statement"],
            rationale=sample.get("rationale"),
            req_type=req_type,
            priority=sample["priority"],
            status=statuses[i % len(statuses)],
            level=levels[i % len(levels)],
            project_id=project.id,
            owner_id=admin_user.id,
            created_by_id=admin_user.id,
            quality_score=quality["score"],
        )
        db.add(req)

    db.commit()

    return {
        "status": "seeded",
        "users": {u["username"]: {"role": u["role"], "password": DEFAULT_PASSWORD} for u in SEED_USERS},
        "project_id": project.id,
        "project_code": project.code,
        "requirements_count": len(SAMPLE_REQUIREMENTS),
        "project_members": len(SEED_USERS),
    }


@router.post("/reset")
def reset_and_seed(db: Session = Depends(get_db)):
    """Drop all tables, recreate, and seed. DEV ONLY."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return seed_database(db)
