"""
ASTRA — AI Writing Assistant Router
=======================================
File: backend/app/routers/ai_writer.py   ← NEW
Path: C:\\Users\\Mason\\Documents\\ASTRA\\backend\\app\\routers\\ai_writer.py

Endpoints:
  POST /ai/writer/convert-prose         — convert free text to structured requirements
  POST /ai/writer/improve               — improve a requirement statement
  POST /ai/writer/decompose             — decompose requirement into sub-requirements
  POST /ai/writer/generate-verification — generate verification criteria
  POST /ai/writer/generate-rationale    — generate rationale for a requirement
  POST /ai/writer/summarize-changes     — generate change summary for review board

All endpoints gracefully degrade when no AI provider is configured.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.services.auth import get_current_user
from app.services.ai.llm_client import is_ai_available

from app.services.ai.requirement_writer import (
    convert_prose_to_requirements,
    improve_requirement,
    decompose_requirement,
    generate_verification_criteria,
    generate_rationale,
    summarize_changes,
)
from app.schemas.ai_writer import (
    ProseConvertRequest, ProseConvertResponse,
    ImproveRequest, ImproveResponse,
    DecomposeRequest, DecomposeResponse,
    GenerateVerificationRequest, VerificationCriteria,
    GenerateRationaleRequest, GenerateRationaleResponse,
    SummarizeChangesRequest, SummarizeChangesResponse,
)

# Optional audit
try:
    from app.services.audit_service import record_event as _audit
except ImportError:
    def _audit(*a, **kw):
        pass

logger = logging.getLogger("astra.ai.writer.router")

router = APIRouter(prefix="/ai/writer", tags=["AI — Writing Assistant"])


# ══════════════════════════════════════
#  1. Convert Prose → Requirements
# ══════════════════════════════════════

@router.post("/convert-prose", response_model=ProseConvertResponse)
def api_convert_prose(
    data: ProseConvertRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Convert free-form stakeholder text (meeting notes, emails, specifications)
    into structured requirements with SHALL statements.
    """
    result = convert_prose_to_requirements(
        prose=data.prose,
        project_context=data.project_context,
        target_level=data.target_level,
        domain_hint=data.domain_hint,
    )

    _audit(
        db, "ai.prose_converted", "ai_writer", 0, current_user.id,
        {"extracted": result.total_extracted, "source_length": len(data.prose)},
    )

    return result


# ══════════════════════════════════════
#  2. Improve Requirement
# ══════════════════════════════════════

@router.post("/improve", response_model=ImproveResponse)
def api_improve(
    data: ImproveRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Generate improved versions of a requirement that fix identified quality issues.
    """
    return improve_requirement(
        statement=data.statement,
        title=data.title,
        rationale=data.rationale,
        issues=data.issues,
        domain_context=data.domain_context,
    )


# ══════════════════════════════════════
#  3. Decompose Requirement
# ══════════════════════════════════════

@router.post("/decompose", response_model=DecomposeResponse)
def api_decompose(
    data: DecomposeRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Decompose a high-level requirement into sub-requirements at the next level.
    E.g., L1 system requirement → multiple L2 subsystem requirements.
    """
    return decompose_requirement(
        statement=data.statement,
        title=data.title,
        current_level=data.current_level,
        target_level=data.target_level,
        req_type=data.req_type,
        project_context=data.project_context,
    )


# ══════════════════════════════════════
#  4. Generate Verification Criteria
# ══════════════════════════════════════

@router.post("/generate-verification", response_model=VerificationCriteria)
def api_generate_verification(
    data: GenerateVerificationRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Generate detailed pass/fail criteria and verification steps for a requirement.
    """
    return generate_verification_criteria(
        statement=data.statement,
        title=data.title,
        method=data.method,
        domain_context=data.domain_context,
    )


# ══════════════════════════════════════
#  5. Generate Rationale
# ══════════════════════════════════════

@router.post("/generate-rationale", response_model=GenerateRationaleResponse)
def api_generate_rationale(
    data: GenerateRationaleRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Generate a professional rationale for a requirement that lacks one.
    """
    return generate_rationale(
        statement=data.statement,
        title=data.title,
        req_type=data.req_type,
        project_context=data.project_context,
    )


# ══════════════════════════════════════
#  6. Summarize Changes for Review Board
# ══════════════════════════════════════

@router.post("/summarize-changes", response_model=SummarizeChangesResponse)
def api_summarize_changes(
    data: SummarizeChangesRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Generate a professional change summary for a CCB, PRR, CDR, or other review board.
    """
    return summarize_changes(
        changes=data.changes,
        project_name=data.project_name,
        board_type=data.board_type,
    )


# ══════════════════════════════════════
#  Status endpoint
# ══════════════════════════════════════

@router.get("/status")
def writer_status(current_user: User = Depends(get_current_user)):
    """Check if the AI writing assistant is available."""
    return {
        "available": is_ai_available(),
        "features": [
            "convert-prose",
            "improve",
            "decompose",
            "generate-verification",
            "generate-rationale",
            "summarize-changes",
        ],
    }
