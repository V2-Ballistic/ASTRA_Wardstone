"""ASTRA Catalog: PATCH /parts/{id}/mass tests.

CADPORT-TDD-STEP-001 §7.3. Covers:

  * positive mass → inertia scales by ratio, mass_source flips to
    'user_override', step_material_key cleared, audit logged.
  * null mass → mass + inertia cleared, mass_source back to 'cad'.
  * SolidWorks-imported rows (source_format='sldprt', mass_source='cad')
    → 409 Conflict.
  * stakeholder role → 403.
  * assembly cascade — part-mass edit re-rolls every assembly that
    lists the part as a non-suppressed component.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.models.catalog import (
    CadportAssembly,
    CadportAssemblyComponent,
    CatalogPart,
    LRUClass,
    LifecycleStatus,
    PartClass,
    Supplier,
)
from app.routers import catalog as catalog_router
from tests.conftest import make_user


@pytest.fixture(autouse=True)
def patch_supplier_doc_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(catalog_router, "SUPPLIER_DOC_DIR", tmp_path / "supplier_docs")


@pytest.fixture()
def supplier(db_session, test_user) -> Supplier:
    s = Supplier(
        name="Wardstone Aerospace",
        short_name="WS",
        is_active=True,
        created_by_id=test_user.id,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


def _step_part(
    db_session, test_user, supplier, *, mass_kg: float = 2.7
) -> CatalogPart:
    """Sample STEP-sourced row at Al 6061-T6 density."""
    part = CatalogPart(
        supplier_id=supplier.id,
        part_number=f"WS-{uuid.uuid4().hex[:6]}",
        revision=None,
        name="Cube 100mm (STEP)",
        part_class=PartClass.MECHANICAL_OTHER,
        lru_classification=LRUClass.COMPONENT,
        lifecycle_status=LifecycleStatus.ACTIVE,
        mass_kg=mass_kg,
        material_name="al_6061_t6",
        volume_m3=1.0e-3,
        surface_area_m2=0.06,
        density_kg_m3=2700.0,
        center_of_mass_x=0.05,
        center_of_mass_y=0.05,
        center_of_mass_z=0.05,
        ixx=0.0045, iyy=0.0045, izz=0.0045,
        ixy=0.0, ixz=0.0, iyz=0.0,
        source_format="step",
        step_material_key="al_6061_t6",
        mass_source="material",
        inertia_revised_via_uniform_scaling=False,
        cadport_part_id=uuid.uuid4(),
        content_hash="sha256:dummy",
        created_by_id=test_user.id,
    )
    db_session.add(part)
    db_session.commit()
    db_session.refresh(part)
    return part


def _sldprt_part(db_session, test_user, supplier) -> CatalogPart:
    """Sample SolidWorks-imported row — should reject mass edits."""
    part = CatalogPart(
        supplier_id=supplier.id,
        part_number=f"WS-{uuid.uuid4().hex[:6]}",
        revision=None,
        name="Bracket Left (SLDPRT)",
        part_class=PartClass.MECHANICAL_OTHER,
        lru_classification=LRUClass.COMPONENT,
        lifecycle_status=LifecycleStatus.ACTIVE,
        mass_kg=1.0,
        material_name="Steel_AISI_4130",
        volume_m3=1.0e-4,
        density_kg_m3=10000.0,
        center_of_mass_x=0.0,
        center_of_mass_y=0.0,
        center_of_mass_z=0.0,
        ixx=1.0, iyy=1.0, izz=1.0,
        ixy=0.0, ixz=0.0, iyz=0.0,
        source_format="sldprt",
        step_material_key=None,
        mass_source="cad",
        inertia_revised_via_uniform_scaling=False,
        cadport_part_id=uuid.uuid4(),
        content_hash="sha256:sw",
        created_by_id=test_user.id,
    )
    db_session.add(part)
    db_session.commit()
    db_session.refresh(part)
    return part


# ── PATCH mass: positive float ──────────────────────────────────────────


class TestPatchMassPositive:

    def test_mass_doubles_inertia_doubles(self, client, db_session, test_user, supplier):
        part = _step_part(db_session, test_user, supplier, mass_kg=2.7)
        _, headers = make_user(db_session, "requirements_engineer", "re_user1")
        resp = client.patch(
            f"/api/v1/catalog/parts/{part.id}/mass",
            json={"mass_kg": 5.4},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["mass_kg"] == pytest.approx(5.4, rel=1e-9)
        # I_new = I_old * (5.4 / 2.7) = 2x.
        assert body["inertia"]["ixx"] == pytest.approx(0.009, rel=1e-9)
        assert body["inertia"]["iyy"] == pytest.approx(0.009, rel=1e-9)
        assert body["inertia"]["izz"] == pytest.approx(0.009, rel=1e-9)
        # Off-diagonals stay zero (scaled from zero).
        assert body["inertia"]["ixy"] == pytest.approx(0.0, abs=1e-12)
        assert body["mass_source"] == "user_override"
        assert body["inertia_revised_via_uniform_scaling"] is True
        # CG untouched.
        assert body["center_of_mass"]["x"] == pytest.approx(0.05, rel=1e-9)
        assert body["center_of_mass"]["y"] == pytest.approx(0.05, rel=1e-9)
        assert body["center_of_mass"]["z"] == pytest.approx(0.05, rel=1e-9)
        # density refreshes to match new mass / volume = 5.4 / 1e-3.
        assert body["density_kg_m3"] == pytest.approx(5400.0, rel=1e-9)
        # Persisted row reflects the change + step_material_key cleared.
        db_session.refresh(part)
        assert float(part.mass_kg) == pytest.approx(5.4, rel=1e-9)
        assert part.mass_source == "user_override"
        assert part.step_material_key is None
        assert part.inertia_revised_via_uniform_scaling is True

    def test_rejects_zero_and_negative(self, client, db_session, test_user, supplier):
        part = _step_part(db_session, test_user, supplier)
        _, headers = make_user(db_session, "requirements_engineer", "re_user2")
        for bad in (0.0, -1.0):
            resp = client.patch(
                f"/api/v1/catalog/parts/{part.id}/mass",
                json={"mass_kg": bad},
                headers=headers,
            )
            assert resp.status_code == 400, resp.text


# ── PATCH mass: null clears ─────────────────────────────────────────────


class TestPatchMassClear:

    def test_clear_resets_mass_and_inertia(self, client, db_session, test_user, supplier):
        part = _step_part(db_session, test_user, supplier, mass_kg=2.7)
        _, headers = make_user(db_session, "requirements_engineer", "re_user3")
        resp = client.patch(
            f"/api/v1/catalog/parts/{part.id}/mass",
            json={"mass_kg": None},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["mass_kg"] is None
        assert body["inertia"]["ixx"] is None
        assert body["inertia"]["iyy"] is None
        assert body["inertia"]["izz"] is None
        assert body["mass_source"] == "cad"
        assert body["inertia_revised_via_uniform_scaling"] is False
        # Geometry preserved (CG + volume + surface area unchanged).
        assert body["center_of_mass"]["x"] == pytest.approx(0.05, rel=1e-9)
        db_session.refresh(part)
        assert part.mass_kg is None
        assert part.ixx is None and part.iyy is None and part.izz is None
        assert part.mass_source == "cad"
        assert part.step_material_key is None
        assert float(part.volume_m3) == pytest.approx(1.0e-3, rel=1e-9)


# ── PATCH mass: SolidWorks rows refuse ─────────────────────────────────


class TestPatchMassSldprtRefused:

    def test_sldprt_cad_row_returns_409(self, client, db_session, test_user, supplier):
        part = _sldprt_part(db_session, test_user, supplier)
        _, headers = make_user(db_session, "requirements_engineer", "re_user4")
        resp = client.patch(
            f"/api/v1/catalog/parts/{part.id}/mass",
            json={"mass_kg": 2.0},
            headers=headers,
        )
        assert resp.status_code == 409, resp.text
        detail = resp.json()["detail"]
        assert "SolidWorks" in detail and "CADPORT" in detail


# ── PATCH mass: RBAC ───────────────────────────────────────────────────


class TestPatchMassRBAC:

    def test_stakeholder_cannot_edit_mass(self, client, db_session, test_user, supplier):
        part = _step_part(db_session, test_user, supplier)
        _, headers = make_user(db_session, "stakeholder", "stake_user1")
        resp = client.patch(
            f"/api/v1/catalog/parts/{part.id}/mass",
            json={"mass_kg": 2.0},
            headers=headers,
        )
        assert resp.status_code == 403, resp.text

    def test_admin_can_edit_mass(self, client, db_session, test_user, supplier):
        part = _step_part(db_session, test_user, supplier)
        _, headers = make_user(db_session, "admin", "admin_mass1")
        resp = client.patch(
            f"/api/v1/catalog/parts/{part.id}/mass",
            json={"mass_kg": 2.7},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text


# ── Assembly re-rollup cascade ─────────────────────────────────────────


class TestAssemblyRerollupCascade:

    def test_mass_edit_cascades_to_assembly(
        self, client, db_session, test_user, test_project, supplier
    ):
        # Two cubes, both 100mm, both Al 6061-T6 (2.7 kg each).
        a = _step_part(db_session, test_user, supplier, mass_kg=2.7)
        b = _step_part(db_session, test_user, supplier, mass_kg=2.7)
        # Build a 2-component assembly: a at origin, b at +100mm in x.
        assembly = CadportAssembly(
            assembly_id=uuid.uuid4(),
            project_id=test_project.id,
            display_name="two-cube",
            source_file="two_cubes.step",
            content_hash="sha256:asm",
            total_mass_kg=5.4,
            center_of_mass_x=0.075,  # midpoint approx
            center_of_mass_y=0.05,
            center_of_mass_z=0.05,
            ixx=0.018, iyy=0.018, izz=0.018,
            ixy=0.0, ixz=0.0, iyz=0.0,
            component_count=2,
            solidworks_version="n/a",
            inertia_revised_via_uniform_scaling=False,
        )
        db_session.add(assembly)
        db_session.flush()
        # Cube A: identity transform (sits at origin per its own CG).
        identity = [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
        # Cube B: translated +100mm in x = +0.1 m.
        shifted = [
            [1.0, 0.0, 0.0, 0.1],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
        db_session.add(
            CadportAssemblyComponent(
                assembly_id=assembly.id,
                catalog_part_id=a.id,
                cadport_part_id=a.cadport_part_id,
                instance_name="cube-a",
                quantity=1,
                transform_json=json.dumps(identity),
                suppressed=False,
            )
        )
        db_session.add(
            CadportAssemblyComponent(
                assembly_id=assembly.id,
                catalog_part_id=b.id,
                cadport_part_id=b.cadport_part_id,
                instance_name="cube-b",
                quantity=1,
                transform_json=json.dumps(shifted),
                suppressed=False,
            )
        )
        db_session.commit()

        _, headers = make_user(db_session, "requirements_engineer", "re_cascade")
        # Double the mass of cube-a only.
        resp = client.patch(
            f"/api/v1/catalog/parts/{a.id}/mass",
            json={"mass_kg": 5.4},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Cascade reports the rolled-up assembly.
        rolled = body["assemblies_rerolled"]
        assert len(rolled) == 1
        rolled_one = rolled[0]
        assert rolled_one["assembly_pk"] == assembly.id
        # Assembly mass = cube-a (5.4) + cube-b (2.7) = 8.1 kg.
        assert rolled_one["total_mass_kg"] == pytest.approx(8.1, rel=1e-6)
        # Assembly inertia involves a mass-scaled component → flag True.
        assert rolled_one["inertia_revised_via_uniform_scaling"] is True
        # Persisted assembly row picks up the rollup.
        db_session.refresh(assembly)
        assert float(assembly.total_mass_kg) == pytest.approx(8.1, rel=1e-6)
        assert assembly.inertia_revised_via_uniform_scaling is True
