"""TDD-CAT-002 — STEP upload + supplier auto-create + approve flow.

Covers the full ingest pipeline through the new
``POST /catalog/upload-step`` endpoint plus the existing
``POST /catalog/pending-imports/{id}/approve`` handler.

Synthetic STEP files are used so the suite passes without an external
fixture; the validation against the real McMaster file lives in
``test_step_parser.py::test_mcmaster_socket_head_screw``.
"""

from __future__ import annotations

import io
import textwrap
from pathlib import Path

import pytest

from app.models.catalog import (
    CatalogPart,
    PartClass,
    PendingCatalogImport,
    PendingImportStatus,
    Supplier,
    SupplierAlias,
    SupplierDocument,
)


# ─────────────────────────────────────────────────────────────────
#  STEP file payloads
# ─────────────────────────────────────────────────────────────────

MCMASTER_SHCS_STEP = textwrap.dedent("""\
ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('STEP AP214'),'1');
FILE_NAME(
    '92196A196_18-8 Stainless Steel Socket Head Screw',
    '2026-05-01T12:00:00',
    ('Mason'),
    ('Wardstone'),
    'SwSTEP 2.0',
    'SolidWorks 2025',
    '');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));
ENDSEC;
DATA;
#1 = APPLICATION_PROTOCOL_DEFINITION('international standard','automotive_design',2000,#2);
#10 = PRODUCT('92196A196','18-8 Stainless Steel Socket Head Cap Screw, M3-0.5 x 8mm','',(#11));
#20 = PRODUCT_RELATED_PRODUCT_CATEGORY('part',$,(#10));
#30 = LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.0254),#31);
#100 = CARTESIAN_POINT('NONE',(0.0,0.0,0.0));
#101 = CARTESIAN_POINT('NONE',(0.118,0.0,0.0));
#102 = CARTESIAN_POINT('NONE',(0.118,0.118,0.314));
ENDSEC;
END-ISO-10303-21;
""")

MCMASTER_HEX_BOLT_STEP = textwrap.dedent("""\
ISO-10303-21;
HEADER;
FILE_NAME(
    '90115A123_316_Stainless_Steel_Hex_Bolt',
    '2026-05-02T12:00:00',
    ('Mason'),
    ('Wardstone'),
    'SwSTEP 2.0',
    'SolidWorks 2025',
    '');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN'));
ENDSEC;
DATA;
#10 = PRODUCT('90115A123','316 Stainless Steel Hex Bolt M6 x 20mm','',(#11));
#20 = PRODUCT_RELATED_PRODUCT_CATEGORY('part',$,(#10));
#30 = LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.0254),#31);
#100 = CARTESIAN_POINT('NONE',(0,0,0));
#101 = CARTESIAN_POINT('NONE',(0.236,0.236,0.787));
ENDSEC;
END-ISO-10303-21;
""")

INHOUSE_BRACKET_STEP = textwrap.dedent("""\
ISO-10303-21;
HEADER;
FILE_NAME(
    'Custom_Mounting_Bracket_v2',
    '2026-05-03T12:00:00',
    ('Mason'),
    ('Wardstone'),
    'SwSTEP 2.0',
    'SolidWorks 2025',
    '');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN'));
ENDSEC;
DATA;
#10 = PRODUCT('CMB-V2','Custom mounting bracket','',(#11));
#20 = PRODUCT_RELATED_PRODUCT_CATEGORY('part',$,(#10));
#30 = LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.001),#31);
#100 = CARTESIAN_POINT('NONE',(0,0,0));
#101 = CARTESIAN_POINT('NONE',(50,80,12));
ENDSEC;
END-ISO-10303-21;
""")


# ─────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────

def _seed_wardstone(db, user) -> Supplier:
    """Migration 0029 seeds Wardstone in production. The conftest uses
    Base.metadata.create_all (no migration), so we seed manually here."""
    sup = db.query(Supplier).filter(Supplier.name == "Wardstone").first()
    if sup is not None:
        return sup
    sup = Supplier(
        name="Wardstone",
        short_name="WS",
        country="US",
        is_active=True,
        is_in_house=True,
        created_by_id=user.id,
    )
    db.add(sup)
    db.flush()
    for alias in ("Wardstone", "WardStone", "WARDSTONE", "Ward Stone", "WS"):
        db.add(SupplierAlias(supplier_id=sup.id, alias=alias))
    db.commit()
    db.refresh(sup)
    return sup


def _upload_step(client, auth_headers, *, content: str, filename: str):
    files = {"file": (filename, io.BytesIO(content.encode("iso-8859-1")), "model/step")}
    return client.post("/api/v1/catalog/upload-step", files=files, headers=auth_headers)


# ─────────────────────────────────────────────────────────────────
#  Tests
# ─────────────────────────────────────────────────────────────────

def test_upload_mcmaster_creates_supplier_first_time(
    client, auth_headers, db_session, test_user,
):
    _seed_wardstone(db_session, test_user)
    pre_supplier_count = db_session.query(Supplier).count()

    r = _upload_step(
        client, auth_headers,
        content=MCMASTER_SHCS_STEP,
        filename="92196A196_18-8 Stainless Steel Socket Head Screw.STEP",
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["supplier_was_created"] is True
    assert body["detected_supplier_name"] == "McMaster-Carr"
    assert body["pending_import_id"]
    assert body["supplier_document_id"]
    assert body["extraction_confidence"] > 0

    # Supplier row created
    assert db_session.query(Supplier).count() == pre_supplier_count + 1
    new_sup = db_session.query(Supplier).filter(Supplier.name == "McMaster-Carr").first()
    assert new_sup is not None
    assert new_sup.is_in_house is False

    # Aliases inserted (canonical + 6 from vendor_patterns.json with dedup)
    alias_count = (
        db_session.query(SupplierAlias)
        .filter(SupplierAlias.supplier_id == new_sup.id)
        .count()
    )
    assert alias_count >= 4

    # PendingCatalogImport
    pending = (
        db_session.query(PendingCatalogImport)
        .filter(PendingCatalogImport.id == body["pending_import_id"])
        .first()
    )
    assert pending is not None
    assert pending.status == PendingImportStatus.PENDING
    assert pending.supplier_id == new_sup.id
    ex = pending.extracted_data
    assert ex["manufacturer"] == "McMaster-Carr"
    assert ex["part_number"] == "92196A196"
    assert ex["material_class"] == "stainless_steel"
    assert ex["part_class"] == "fastener_screw"
    assert ex["part_subtype"] == "socket_head_cap_screw"
    assert ex.get("supplier", {}).get("name") == "McMaster-Carr"

    # SupplierDocument
    doc = db_session.query(SupplierDocument).filter(
        SupplierDocument.id == body["supplier_document_id"]
    ).first()
    assert doc is not None
    assert doc.mime_type == "model/step"
    assert doc.supplier_id == new_sup.id


def test_upload_mcmaster_reuses_supplier_second_time(
    client, auth_headers, db_session, test_user,
):
    _seed_wardstone(db_session, test_user)
    r1 = _upload_step(
        client, auth_headers,
        content=MCMASTER_SHCS_STEP,
        filename="92196A196_18-8 Stainless Steel Socket Head Screw.STEP",
    )
    assert r1.status_code == 201, r1.text
    pre_supplier_count = db_session.query(Supplier).count()

    # Different MPN → different filename → different sha256 → must succeed
    # but reuse the McMaster supplier.
    r2 = _upload_step(
        client, auth_headers,
        content=MCMASTER_HEX_BOLT_STEP,
        filename="90115A123_316_Stainless_Steel_Hex_Bolt.STEP",
    )
    assert r2.status_code == 201, r2.text
    body = r2.json()
    assert body["supplier_was_created"] is False
    assert body["detected_supplier_name"] == "McMaster-Carr"

    # Same supplier count — no new row added.
    assert db_session.query(Supplier).count() == pre_supplier_count


def test_upload_inhouse_links_to_wardstone(
    client, auth_headers, db_session, test_user,
):
    ws = _seed_wardstone(db_session, test_user)
    r = _upload_step(
        client, auth_headers,
        content=INHOUSE_BRACKET_STEP,
        filename="Custom_Mounting_Bracket_v2.STEP",
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["supplier_was_created"] is False
    assert body["detected_supplier_id"] == ws.id
    assert body["detected_supplier_name"] == "Wardstone"


def test_upload_dedup_rejects_duplicate_hash(
    client, auth_headers, db_session, test_user,
):
    _seed_wardstone(db_session, test_user)
    r1 = _upload_step(
        client, auth_headers,
        content=MCMASTER_SHCS_STEP,
        filename="92196A196_18-8 Stainless Steel Socket Head Screw.STEP",
    )
    assert r1.status_code == 201, r1.text
    first_pending_id = r1.json()["pending_import_id"]

    r2 = _upload_step(
        client, auth_headers,
        content=MCMASTER_SHCS_STEP,
        filename="92196A196_18-8 Stainless Steel Socket Head Screw.STEP",
    )
    assert r2.status_code == 409, r2.text

    # CLEANUP-002 AD-3: structured 409 detail with actionable link to
    # the existing pending import, not the opaque ID dump that
    # prompted this TDD.
    detail = r2.json()["detail"]
    assert isinstance(detail, dict), detail
    assert detail["code"] == "step_already_uploaded"
    assert "already" in detail["message"]
    assert detail["existing_supplier_document_id"]
    assert detail["existing_pending_import_id"] == first_pending_id
    assert detail["existing_pending_import_url"] == (
        f"/catalog/pending-imports/{first_pending_id}"
    )


def test_upload_after_catalog_part_soft_deleted_succeeds(
    client, auth_headers, db_session, test_user,
):
    """CLEANUP-002 AD-2: re-uploading a STEP whose only downstream
    catalog_part has been soft-deleted should succeed (the
    supplier_document is effectively orphaned)."""
    _seed_wardstone(db_session, test_user)
    r1 = _upload_step(
        client, auth_headers,
        content=MCMASTER_SHCS_STEP,
        filename="92196A196_18-8 Stainless Steel Socket Head Screw.STEP",
    )
    assert r1.status_code == 201, r1.text
    pending_id = r1.json()["pending_import_id"]

    # Approve to produce a catalog_part
    ar = client.post(
        f"/api/v1/catalog/pending-imports/{pending_id}/approve",
        headers=auth_headers,
    )
    assert ar.status_code == 201, ar.text
    part_id = ar.json()["id"]

    # Soft-delete the catalog_part directly in the DB. The DELETE
    # endpoint that does this lives in Phase 4; for this test we
    # exercise just the dedup-side fix.
    from datetime import datetime, timezone
    part = db_session.query(CatalogPart).filter(CatalogPart.id == part_id).first()
    assert part is not None
    part.deleted_at = datetime.now(timezone.utc)
    db_session.commit()

    # Re-upload the same STEP — should succeed since no live
    # downstream state remains (catalog_part soft-deleted; the
    # original pending_import is now APPROVED, not PENDING).
    r2 = _upload_step(
        client, auth_headers,
        content=MCMASTER_SHCS_STEP,
        filename="92196A196_18-8 Stainless Steel Socket Head Screw.STEP",
    )
    assert r2.status_code == 201, r2.text
    new_pending_id = r2.json()["pending_import_id"]
    assert new_pending_id != pending_id


def test_upload_after_approval_blocks_without_pending_url(
    client, auth_headers, db_session, test_user,
):
    """When the supplier_document has a live (non-soft-deleted)
    catalog_part but the original pending_import is APPROVED (not
    PENDING), re-upload still 409s — but with `existing_pending_import_id`
    null since there's no active workflow to link to. The UI falls
    back to a string error in that branch."""
    _seed_wardstone(db_session, test_user)
    r1 = _upload_step(
        client, auth_headers,
        content=MCMASTER_SHCS_STEP,
        filename="92196A196_18-8 Stainless Steel Socket Head Screw.STEP",
    )
    assert r1.status_code == 201, r1.text
    pending_id = r1.json()["pending_import_id"]

    ar = client.post(
        f"/api/v1/catalog/pending-imports/{pending_id}/approve",
        headers=auth_headers,
    )
    assert ar.status_code == 201, ar.text

    # Re-upload — catalog_part is live (not soft-deleted) → still blocked.
    r2 = _upload_step(
        client, auth_headers,
        content=MCMASTER_SHCS_STEP,
        filename="92196A196_18-8 Stainless Steel Socket Head Screw.STEP",
    )
    assert r2.status_code == 409, r2.text
    detail = r2.json()["detail"]
    assert isinstance(detail, dict), detail
    assert detail["code"] == "step_already_uploaded"
    assert detail["existing_supplier_document_id"]
    # No PENDING pending_import remains — the original was approved.
    assert detail["existing_pending_import_id"] is None
    assert detail["existing_pending_import_url"] is None


def test_upload_then_approve_creates_catalog_part(
    client, auth_headers, db_session, test_user,
):
    _seed_wardstone(db_session, test_user)
    r = _upload_step(
        client, auth_headers,
        content=MCMASTER_SHCS_STEP,
        filename="92196A196_18-8 Stainless Steel Socket Head Screw.STEP",
    )
    assert r.status_code == 201, r.text
    pending_id = r.json()["pending_import_id"]

    # Approve via the existing endpoint
    ar = client.post(
        f"/api/v1/catalog/pending-imports/{pending_id}/approve",
        headers=auth_headers,
    )
    assert ar.status_code == 201, ar.text
    body = ar.json()

    # CatalogPart created with the parser-derived fields
    cp = (
        db_session.query(CatalogPart)
        .filter(CatalogPart.id == body["id"])
        .first()
    )
    assert cp is not None
    assert cp.part_number == "92196A196"
    assert cp.part_class == PartClass.FASTENER_SCREW
    assert cp.material_class == "stainless_steel"
    assert cp.part_subtype == "socket_head_cap_screw"
    assert cp.cad_authoring_tool  # populated from FILE_NAME header
    assert cp.native_units == "inch"
    assert cp.bbox_x_mm is not None and float(cp.bbox_x_mm) > 0
