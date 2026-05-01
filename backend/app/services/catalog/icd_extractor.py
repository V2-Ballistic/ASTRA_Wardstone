"""
ASTRA — ICD Extractor Orchestrator (Phase 7, ASTRA-TDD-INTF-002)
==================================================================
File: backend/app/services/catalog/icd_extractor.py   ← NEW

Coordinates the full extraction pipeline for a single SupplierDocument:

    SupplierDocument (UPLOADED)
            │
            ▼
    pre-extract (PyMuPDF / docx / openpyxl)
            │
            ▼
    build prompt (system + user, schema-pinned)
            │
            ▼
    LLM call via app.services.ai.llm_client.LLMClient
            │
            ▼
    Validate response against IcdExtractionResultSchema
            │
            ▼
    PendingCatalogImport (PENDING_REVIEW)  +  SupplierDocument(PENDING_REVIEW)

Status transitions on SupplierDocument:
    UPLOADED → EXTRACTING → PENDING_REVIEW   (happy path)
    UPLOADED → EXTRACTING → FAILED            (any failure)

Failure modes captured in ``extraction_log`` JSON blob:
    * ``ai_unavailable``    no AI provider configured
    * ``ai_returned_null``  LLM returned None (network / parse error)
    * ``schema_invalid``    Pydantic validation failed (raw response saved)
    * ``unsupported_type``  document_extractor raised NotImplementedError
    * ``corrupt_file``      DocumentExtractionError
    * ``other``             any other unexpected exception

Public API
----------
``trigger_extraction(db, document_id)`` — synchronous orchestrator. Wrap with
a FastAPI BackgroundTask so the HTTP request returns 202 immediately.
"""

from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime
from typing import Optional

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.catalog import (
    ExtractionStatus,
    PendingCatalogImport,
    PendingImportStatus,
    SupplierDocument,
)
from app.schemas.catalog import IcdExtractionResultSchema

logger = logging.getLogger("astra.catalog.icd_extractor")


# ──────────────────────────────────────────────────────────────
#  Status transition helpers
# ──────────────────────────────────────────────────────────────

def _set_status(
    db: Session,
    document: SupplierDocument,
    status: ExtractionStatus,
    *,
    log_blob: Optional[dict] = None,
) -> None:
    """Update extraction_status + extraction_log + extraction_at + commit."""
    document.extraction_status = status
    if log_blob is not None:
        document.extraction_log = log_blob
    document.extraction_at = datetime.utcnow()
    db.commit()


def _failed(
    db: Session,
    document: SupplierDocument,
    *,
    code: str,
    message: str,
    detail: Optional[dict] = None,
) -> None:
    """Mark a SupplierDocument as FAILED with structured log."""
    blob = {"code": code, "message": message, "failed_at": datetime.utcnow().isoformat()}
    if detail:
        blob["detail"] = detail
    logger.warning(
        "ICD extraction FAILED for SupplierDocument %s: %s — %s",
        document.id, code, message,
    )
    _set_status(db, document, ExtractionStatus.FAILED, log_blob=blob)


# ──────────────────────────────────────────────────────────────
#  Public entry point
# ──────────────────────────────────────────────────────────────

def trigger_extraction(db: Session, document_id: int) -> Optional[int]:
    """
    Run the extraction pipeline for one SupplierDocument.

    Parameters
    ----------
    db : sqlalchemy.orm.Session
        Owned by the caller. The function commits its own state transitions.
    document_id : int
        Primary key of the :class:`SupplierDocument`.

    Returns
    -------
    pending_import_id : int | None
        The new ``PendingCatalogImport.id`` on success, ``None`` on failure
        (the document's ``extraction_log`` carries the failure reason).
    """
    # Lazy imports so importing the module doesn't drag PyMuPDF / camelot
    # in for callers that just want the type annotations.
    from app.services.ai.llm_client import LLMClient, is_ai_available
    from app.services.catalog import document_extractor as doc_ext
    from app.services.catalog import prompts as prompt_mod

    document = (
        db.query(SupplierDocument)
        .filter(SupplierDocument.id == document_id)
        .first()
    )
    if document is None:
        logger.error("trigger_extraction: SupplierDocument %s not found", document_id)
        return None

    # Idempotency guard — refuse to re-run on a document already past UPLOADED
    # unless it's in the FAILED state (operator may have fixed env / model).
    if document.extraction_status not in (
        ExtractionStatus.UPLOADED, ExtractionStatus.FAILED,
    ):
        logger.info(
            "trigger_extraction: SupplierDocument %s already in %s — skipping re-run",
            document_id, document.extraction_status,
        )
        return None

    # Mark EXTRACTING up-front so the UI can show progress.
    _set_status(db, document, ExtractionStatus.EXTRACTING, log_blob={
        "started_at": datetime.utcnow().isoformat(),
    })

    # ── 1. Pre-extract ──
    try:
        extracted = doc_ext.extract_document(
            file_path=document.file_path,
            mime_type=document.mime_type,
        )
    except NotImplementedError as exc:
        _failed(db, document, code="unsupported_type", message=str(exc))
        return None
    except doc_ext.DocumentExtractionError as exc:
        _failed(db, document, code="corrupt_file", message=str(exc))
        return None
    except Exception as exc:    # noqa: BLE001 - catch-all by design
        _failed(
            db, document,
            code="other",
            message=f"Pre-extraction crashed: {exc}",
            detail={"traceback": traceback.format_exc()},
        )
        return None

    # Capture page_count even when extraction succeeds — useful in the UI.
    document.page_count = extracted.page_count
    db.flush()

    # ── 2. Build prompt ──
    schema_json = prompt_mod.schema_json_repr(IcdExtractionResultSchema)
    sys_prompt, user_prompt, prompt_warnings = prompt_mod.build_extraction_prompts(
        extracted, schema_json=schema_json,
    )

    # ── 3. LLM call ──
    if not is_ai_available():
        _failed(
            db, document,
            code="ai_unavailable",
            message=(
                "No AI provider configured (set AI_PROVIDER + AI_API_KEY + "
                "AI_MODEL in environment). The pre-extraction succeeded but "
                "no LLM is wired up to interpret the document."
            ),
        )
        return None

    client = LLMClient()
    raw_response = client.complete(
        system_prompt=sys_prompt,
        user_prompt=user_prompt,
        temperature=0.0,
        # Allow large output for long pin tables — bounded by the env var
        # AI_MAX_TOKENS; pass a higher upper bound here just in case.
        max_tokens=8192,
        json_mode=True,
    )
    if raw_response is None:
        _failed(
            db, document,
            code="ai_returned_null",
            message=(
                "AI provider returned no parseable response after retries. "
                "Falling back to regex is not yet implemented for ICD "
                "extraction; manual entry required."
            ),
        )
        return None

    # ── 4. Validate against schema ──
    try:
        result = IcdExtractionResultSchema.model_validate(raw_response)
    except ValidationError as exc:
        _failed(
            db, document,
            code="schema_invalid",
            message="LLM response failed schema validation",
            detail={
                "errors": json.loads(exc.json()),
                "raw_response": _truncate_for_log(raw_response),
            },
        )
        return None

    # ── 5. Persist PendingCatalogImport ──
    # Combine prompt-time warnings + AI-emitted warnings + truncation flag.
    combined_warnings = []
    combined_warnings.extend(extracted.warnings or [])
    combined_warnings.extend(prompt_warnings or [])
    combined_warnings.extend(result.extraction_warnings or [])
    if extracted.truncated:
        combined_warnings.append(
            f"Document truncated to first {len(extracted.pages)} of "
            f"{extracted.page_count} pages during pre-extraction"
        )

    pending = PendingCatalogImport(
        source_document_id=document.id,
        supplier_id=document.supplier_id,
        extracted_data=json.loads(result.model_dump_json()),
        extraction_warnings={"warnings": combined_warnings} if combined_warnings else None,
        extraction_confidence=result.extraction_confidence,
        status=PendingImportStatus.PENDING,
    )
    db.add(pending)
    db.flush()

    # ── 6. Update document status ──
    success_log = {
        "code": "ok",
        "completed_at": datetime.utcnow().isoformat(),
        "pending_import_id": pending.id,
        "page_count_extracted": len(extracted.pages),
        "page_count_total": extracted.page_count,
        "truncated": extracted.truncated,
        "warning_count": len(combined_warnings),
        "ai_provider": getattr(client, "provider", None),
        "ai_model": getattr(client, "model", None),
    }
    _set_status(db, document, ExtractionStatus.PENDING_REVIEW, log_blob=success_log)

    logger.info(
        "ICD extraction OK for SupplierDocument %s → PendingCatalogImport %s "
        "(%d pages, %d warnings)",
        document.id, pending.id, len(extracted.pages), len(combined_warnings),
    )
    return pending.id


# ──────────────────────────────────────────────────────────────
#  Internal helpers
# ──────────────────────────────────────────────────────────────

_LOG_TRUNC_KEYS = 1500


def _truncate_for_log(blob) -> dict:
    """Trim long string fields in a JSONable blob so the audit log doesn't
    swell to megabytes when an extraction returns a giant response."""
    if isinstance(blob, dict):
        out: dict = {}
        for k, v in blob.items():
            if isinstance(v, str) and len(v) > _LOG_TRUNC_KEYS:
                out[k] = v[:_LOG_TRUNC_KEYS] + "...[truncated]"
            elif isinstance(v, (dict, list)):
                out[k] = _truncate_for_log(v)
            else:
                out[k] = v
        return out
    if isinstance(blob, list):
        return [_truncate_for_log(x) for x in blob]
    return blob
