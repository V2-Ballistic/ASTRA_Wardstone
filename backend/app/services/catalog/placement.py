"""
ASTRA — Catalog Placement Service
==================================
File: backend/app/services/catalog/placement.py   ← NEW (Phase 2, ASTRA-TDD-INTF-002)

Implements spec §14: instantiate a CatalogPart into a Project as a Unit
(+ Connectors + Pins). The catalog entry is the source-of-truth for
physics specs (mass, power, env envelope, signal type/direction); the
project-side rows carry the "where & when this physical instance lives"
fields (designation, location_zone, serial_number, asset_tag).

Public API
----------
``place_catalog_part(...)``      Place an existing CatalogPart into a Project.
``place_brand_new_part(...)``    Create a NEW global CatalogPart and place it
                                 in one transaction (admin / req_eng+ flow).
``is_part_in_use(...)``          Returns True if any project Unit references
                                 the given catalog_part_id. Used by the
                                 catalog-part DELETE handler.

All public callers receive a fully populated, refreshed Unit (with its
project-side Connectors and Pins). Atomicity is honoured with a single
nested ``db.begin_nested()`` transaction so a failure anywhere in the
process rolls every newly-created row back.

Spec references
---------------
- §6 RBAC      — admin bypass for RESTRICTED parts; req_eng+ to place; admin
                 to brand-new-create at the catalog level.
- §14          — the placement algorithm (validate → create unit →
                 clone connectors → clone pins → audit).
- Anomaly #11  — placement is intended to also create
                 ``RequirementSourceLink`` rows tagged
                 ``template_id="legacy_import"`` once the source-link layer
                 is wired (Phase 5/7). Phase 2 deliberately does NOT create
                 those rows — the listener / template engine arrives later.
"""

from __future__ import annotations

import logging
from typing import Iterable, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import User, UserRole
from app.models.catalog import (
    CatalogConnector,
    CatalogPart,
    CatalogPin,
    LifecycleStatus,
    SignalDirection as CatalogSignalDirection,
    SignalType as CatalogSignalType,
    Supplier,
)
from app.models.interface import (
    Connector,
    ConnectorGender as ProjectConnectorGender,
    ConnectorType as ProjectConnectorType,
    Pin,
    PinDirection as ProjectPinDirection,
    SignalType as ProjectSignalType,
    System,
    Unit,
    UnitStatus,
    UnitType as ProjectUnitType,
)

logger = logging.getLogger("astra.catalog.placement")


# ══════════════════════════════════════════════════════════════
#  Enum mapping helpers (catalog perspective → project perspective)
# ══════════════════════════════════════════════════════════════

# CatalogPart.part_class values that already mean "LRU-class hardware unit"
# map cleanly to one of the existing project-side UnitType members.
_PART_CLASS_TO_UNIT_TYPE: dict[str, ProjectUnitType] = {
    "processor": ProjectUnitType.PROCESSOR,
    "sensor": ProjectUnitType.SENSOR,
    "actuator": ProjectUnitType.ACTUATOR,
    # Anything else (power_supply, radio, antenna, harness, connector_only,
    # compute_module, power_distribution, interface_card, display, other)
    # falls through to LRU as the safe generic.
}


def _map_part_class_to_unit_type(part_class) -> ProjectUnitType:
    raw = part_class.value if hasattr(part_class, "value") else str(part_class)
    return _PART_CLASS_TO_UNIT_TYPE.get(raw, ProjectUnitType.LRU)


_GENDER_MAP: dict[str, ProjectConnectorGender] = {
    "male": ProjectConnectorGender.MALE_PIN,
    "female": ProjectConnectorGender.FEMALE_SOCKET,
    "hermaphroditic": ProjectConnectorGender.HERMAPHRODITIC,
    "unknown": ProjectConnectorGender.GENDERLESS,
}


def _map_gender(catalog_gender) -> ProjectConnectorGender:
    if catalog_gender is None:
        return ProjectConnectorGender.GENDERLESS
    raw = catalog_gender.value if hasattr(catalog_gender, "value") else str(catalog_gender)
    return _GENDER_MAP.get(raw, ProjectConnectorGender.GENDERLESS)


# Catalog SignalType → project SignalType mapping. Catalog values are broad
# vendor-perspective categories; project values are finer-grained engineering
# enums. The mapping picks a sensible "least surprising" project-side member
# for each catalog category. Anything unmapped becomes CUSTOM.
_SIGNAL_TYPE_MAP: dict[str, ProjectSignalType] = {
    "power":      ProjectSignalType.POWER_PRIMARY,
    "ground":     ProjectSignalType.SIGNAL_GROUND,
    "digital":    ProjectSignalType.SIGNAL_DIGITAL_SINGLE,
    "analog":     ProjectSignalType.SIGNAL_ANALOG_SINGLE,
    "diff_pair":  ProjectSignalType.SIGNAL_DIGITAL_DIFFERENTIAL,
    "rf":         ProjectSignalType.RF_SIGNAL,
    "discrete":   ProjectSignalType.DISCRETE_BIDIRECTIONAL,
    "no_connect": ProjectSignalType.NO_CONNECT,
    "reserved":   ProjectSignalType.RESERVED,
    "unknown":    ProjectSignalType.CUSTOM,
}


def _map_signal_type(catalog_signal_type) -> ProjectSignalType:
    if catalog_signal_type is None:
        return ProjectSignalType.CUSTOM
    raw = catalog_signal_type.value if hasattr(catalog_signal_type, "value") else str(catalog_signal_type)
    return _SIGNAL_TYPE_MAP.get(raw, ProjectSignalType.CUSTOM)


_DIRECTION_MAP: dict[str, ProjectPinDirection] = {
    "input":         ProjectPinDirection.INPUT,
    "output":        ProjectPinDirection.OUTPUT,
    "bidirectional": ProjectPinDirection.BIDIRECTIONAL,
    "power":         ProjectPinDirection.POWER_SOURCE,
    "ground":        ProjectPinDirection.GROUND,
    "unknown":       ProjectPinDirection.PASSIVE,
}


def _map_direction(catalog_direction) -> ProjectPinDirection:
    if catalog_direction is None:
        return ProjectPinDirection.PASSIVE
    raw = catalog_direction.value if hasattr(catalog_direction, "value") else str(catalog_direction)
    return _DIRECTION_MAP.get(raw, ProjectPinDirection.PASSIVE)


def _user_is_admin(user: User) -> bool:
    try:
        role = UserRole(user.role) if isinstance(user.role, str) else user.role
    except ValueError:
        return False
    return role == UserRole.ADMIN


def _floatify(value) -> Optional[float]:
    """Numeric → float for project-side Float columns; None passes through."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ══════════════════════════════════════════════════════════════
#  Public API
# ══════════════════════════════════════════════════════════════

def is_part_in_use(db: Session, catalog_part_id: int) -> bool:
    """
    Return True if any Unit in the database references the given CatalogPart.

    Used by the catalog-part DELETE handler to refuse the operation unless
    the caller passes ``?admin_force=true``.
    """
    return (
        db.query(Unit.id)
        .filter(Unit.catalog_part_id == catalog_part_id)
        .first()
        is not None
    )


def place_catalog_part(
    db: Session,
    *,
    catalog_part_id: int,
    project_id: int,
    system_id: int,
    designation: str,
    user: User,
    designation_override: Optional[str] = None,
    location_zone: Optional[str] = None,
    serial_number: Optional[str] = None,
    asset_tag: Optional[str] = None,
    admin_force: bool = False,
) -> Unit:
    """
    Place a CatalogPart into a project as a Unit (+ Connectors + Pins).

    Atomic: any failure rolls every newly-created row back. Audit emit is
    the caller's responsibility (the router wraps this with the
    ``catalog.part_placed`` event so the audit row is part of the same
    HTTP-level commit boundary).

    Raises
    ------
    HTTPException(404)  CatalogPart, supplier, system, or project missing
    HTTPException(409)  Designation collides within the target project
    HTTPException(403)  Caller is non-admin and the part is RESTRICTED
                         (and admin_force was not passed by an admin)
    HTTPException(400)  Part is OBSOLETE and the caller didn't admin_force
    """
    catalog_part = (
        db.query(CatalogPart)
        .filter(CatalogPart.id == catalog_part_id)
        .first()
    )
    if catalog_part is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CatalogPart {catalog_part_id} not found",
        )

    # Lifecycle gating per spec §14 step 1 + RBAC matrix.
    is_admin = _user_is_admin(user)
    lifecycle_value = (
        catalog_part.lifecycle_status.value
        if hasattr(catalog_part.lifecycle_status, "value")
        else str(catalog_part.lifecycle_status)
    )
    if lifecycle_value == LifecycleStatus.RESTRICTED.value and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"CatalogPart {catalog_part_id} is RESTRICTED — admin role "
                "required to place it in a project."
            ),
        )
    if lifecycle_value == LifecycleStatus.OBSOLETE.value and not (is_admin and admin_force):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"CatalogPart {catalog_part_id} is OBSOLETE. Admin must pass "
                "admin_force=true to place it anyway."
            ),
        )

    # Supplier active-check.
    supplier = (
        db.query(Supplier)
        .filter(Supplier.id == catalog_part.supplier_id)
        .first()
    )
    if supplier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier {catalog_part.supplier_id} (parent of catalog part) not found",
        )
    if not supplier.is_active and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Supplier '{supplier.name}' is inactive. Admin can still place; "
                "other roles must wait for the supplier to be reactivated."
            ),
        )

    # System exists and belongs to the requested project.
    system = (
        db.query(System)
        .filter(System.id == system_id, System.project_id == project_id)
        .first()
    )
    if system is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"System {system_id} not found in project {project_id}",
        )

    # Designation must be unique within the project.
    final_designation = designation_override or designation
    existing = (
        db.query(Unit.id)
        .filter(Unit.project_id == project_id, Unit.designation == final_designation)
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Designation '{final_designation}' already exists in project "
                f"{project_id}"
            ),
        )

    # Generate a project-unique unit_id tag using the existing serializer.
    from app.services.id_sequence import next_human_id
    unit_id_tag = next_human_id(
        db, project_id=project_id, prefix="UNIT",
        source_model=Unit, id_field="unit_id",
    )

    # ── Build the Unit ──
    unit = Unit(
        unit_id=unit_id_tag,
        name=catalog_part.name,
        designation=final_designation,
        description=catalog_part.description or "",
        part_number=catalog_part.part_number,
        manufacturer=supplier.name,
        cage_code=supplier.cage_code,
        drawing_number=None,
        revision=catalog_part.revision,
        unit_type=_map_part_class_to_unit_type(catalog_part.part_class),
        status=UnitStatus.CONCEPT,
        # Physical / electrical / environmental — copied from the catalog
        # so reports/analyses against the project Unit get the spec values
        # without needing to JOIN through catalog_part_id every read.
        mass_kg=_floatify(catalog_part.mass_kg),
        dimensions_l_mm=_floatify(catalog_part.dim_length_mm),
        dimensions_w_mm=_floatify(catalog_part.dim_width_mm),
        dimensions_h_mm=_floatify(catalog_part.dim_height_mm),
        power_watts_nominal=_floatify(catalog_part.power_watts_nominal),
        power_watts_peak=_floatify(catalog_part.power_watts_peak),
        voltage_input_min=_floatify(catalog_part.voltage_input_min_v),
        voltage_input_max=_floatify(catalog_part.voltage_input_max_v),
        temp_operating_min_c=_floatify(catalog_part.temp_operating_min_c),
        temp_operating_max_c=_floatify(catalog_part.temp_operating_max_c),
        temp_storage_min_c=_floatify(catalog_part.temp_storage_min_c),
        temp_storage_max_c=_floatify(catalog_part.temp_storage_max_c),
        vibration_random_grms=_floatify(catalog_part.vibration_random_grms),
        shock_mechanical_g=_floatify(catalog_part.shock_mechanical_g),
        humidity_max_pct=_floatify(catalog_part.humidity_max_pct),
        altitude_operating_max_m=_floatify(catalog_part.altitude_max_m),
        emi_ce102_limit_dbua=_floatify(catalog_part.emi_ce102_limit_dbua),
        emi_rs103_limit_vm=_floatify(catalog_part.emi_rs103_limit_vm),
        esd_hbm_v=_floatify(catalog_part.esd_hbm_v),
        # FKs
        system_id=system_id,
        project_id=project_id,
        catalog_part_id=catalog_part.id,
        location_zone=location_zone,
        serial_number=serial_number,
        asset_tag=asset_tag,
    )

    # ── Atomic clone of the catalog connector + pin tree into the project ──
    # We let the ORM flush each row so subsequent rows can reference the
    # generated PKs. SAVEPOINT ensures the whole operation rolls back as a
    # single unit if anything below fails.
    with db.begin_nested():
        db.add(unit)
        db.flush()

        catalog_connectors: List[CatalogConnector] = (
            db.query(CatalogConnector)
            .filter(CatalogConnector.catalog_part_id == catalog_part.id)
            .order_by(CatalogConnector.position)
            .all()
        )

        for cat_conn in catalog_connectors:
            project_conn = Connector(
                connector_id=None,  # auto-assigned later if needed
                designator=cat_conn.reference,
                name=cat_conn.description or cat_conn.reference,
                description=cat_conn.description or "",
                # The ConnectorType project enum is a closed set — there's
                # no clean catalog → project map for free-text vendor strings.
                # Default to CUSTOM and stash the raw string in the custom
                # field so it survives reads.
                connector_type=ProjectConnectorType.CUSTOM,
                connector_type_custom=cat_conn.connector_type,
                gender=_map_gender(cat_conn.gender),
                shell_size=cat_conn.shell_size,
                insert_arrangement=cat_conn.insert_arrangement,
                total_contacts=cat_conn.pin_count or 0,
                keying=cat_conn.keying,
                manufacturer_part_number=cat_conn.mating_part_number,
                connector_manufacturer=supplier.name,
                notes=cat_conn.notes or "",
                unit_id=unit.id,
                project_id=project_id,
            )
            db.add(project_conn)
            db.flush()

            catalog_pins: List[CatalogPin] = (
                db.query(CatalogPin)
                .filter(CatalogPin.catalog_connector_id == cat_conn.id)
                .order_by(CatalogPin.pin_position)
                .all()
            )

            for cat_pin in catalog_pins:
                project_pin = Pin(
                    pin_number=cat_pin.pin_position,
                    pin_label=cat_pin.mfr_pin_name,
                    signal_name=cat_pin.mfr_pin_name,
                    signal_type=_map_signal_type(cat_pin.mfr_signal_type),
                    direction=_map_direction(cat_pin.mfr_direction),
                    voltage_min=_floatify(cat_pin.mfr_voltage_min_v),
                    voltage_max=_floatify(cat_pin.mfr_voltage_max_v),
                    current_max_amps=(
                        float(cat_pin.mfr_current_max_ma) / 1000.0
                        if cat_pin.mfr_current_max_ma is not None
                        else None
                    ),
                    impedance_ohms=_floatify(cat_pin.mfr_impedance_ohm),
                    description=cat_pin.mfr_signal_function or "",
                    notes=cat_pin.notes or "",
                    connector_id=project_conn.id,
                    catalog_pin_id=cat_pin.id,
                    # Catalog-aligned dual-name fields.
                    mfr_pin_name=cat_pin.mfr_pin_name,
                    internal_signal_name=cat_pin.mfr_pin_name,  # default — user-editable
                    direction_override=None,                    # falls back to catalog at read time
                    function_override=None,
                )
                db.add(project_pin)

    db.flush()
    db.refresh(unit)
    logger.info(
        "Placed CatalogPart %s into project %s as Unit %s (designation=%s)",
        catalog_part.id, project_id, unit.id, final_designation,
    )
    return unit


def place_brand_new_part(
    db: Session,
    *,
    user: User,
    supplier_id: Optional[int] = None,
    new_supplier: Optional[dict] = None,
    catalog_part_data: dict,
    connectors_data: Optional[List[dict]] = None,
    placement: Optional[dict] = None,
) -> Tuple[CatalogPart, Optional[Unit]]:
    """
    Two-step transaction: create a brand-new CatalogPart (and optionally a new
    Supplier) and, if *placement* is supplied, instantiate it into a project
    in the same atomic boundary.

    Parameters
    ----------
    user             The acting user. Must be admin or req_eng+ at the router.
    supplier_id      Existing supplier id; mutually exclusive with new_supplier.
    new_supplier     Dict of fields for a new Supplier row.
    catalog_part_data
                     Dict of CatalogPart fields (NOT including supplier_id —
                     that's set from supplier_id / new_supplier resolution).
    connectors_data  Optional list of dicts. Each dict has connector fields
                     plus an optional ``pins`` list of pin-field dicts.
    placement        Optional dict with placement parameters
                     (project_id, system_id, designation, etc.) — when
                     supplied, the new part is also placed.

    Returns
    -------
    (CatalogPart, Optional[Unit])  The created CatalogPart and the placed
                                    Unit (None if placement was not requested).

    Raises
    ------
    HTTPException(400)  Both supplier_id and new_supplier provided, or neither.
    HTTPException(404)  supplier_id refers to a missing Supplier.
    HTTPException(409)  CatalogPart unique constraint collision.
    Any HTTPException raised by ``place_catalog_part`` if placement fails.
    """
    if (supplier_id is None) == (new_supplier is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide exactly one of supplier_id or new_supplier",
        )

    with db.begin_nested():
        # ── Resolve / create supplier ──
        if new_supplier is not None:
            supplier = Supplier(
                created_by_id=user.id,
                **new_supplier,
            )
            db.add(supplier)
            db.flush()
        else:
            supplier = (
                db.query(Supplier)
                .filter(Supplier.id == supplier_id)
                .first()
            )
            if supplier is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Supplier {supplier_id} not found",
                )

        # ── Create the CatalogPart ──
        part_kwargs = dict(catalog_part_data)
        part_kwargs["supplier_id"] = supplier.id
        part_kwargs["created_by_id"] = user.id

        # Strip nested connectors so SQLAlchemy's __init__ doesn't choke.
        nested_connectors = part_kwargs.pop("connectors", None) or connectors_data or []

        part = CatalogPart(**part_kwargs)
        db.add(part)
        db.flush()

        # ── Create connectors + pins ──
        for c_data in nested_connectors:
            c_kwargs = dict(c_data)
            pins_data = c_kwargs.pop("pins", None) or []
            connector = CatalogConnector(catalog_part_id=part.id, **c_kwargs)
            db.add(connector)
            db.flush()
            for p_data in pins_data:
                pin = CatalogPin(catalog_connector_id=connector.id, **p_data)
                db.add(pin)
            # Auto-set pin_count if not supplied explicitly.
            if not connector.pin_count:
                connector.pin_count = len(pins_data)

    db.flush()
    db.refresh(part)

    placed_unit: Optional[Unit] = None
    if placement is not None:
        placed_unit = place_catalog_part(
            db,
            catalog_part_id=part.id,
            project_id=placement["project_id"],
            system_id=placement["system_id"],
            designation=placement["designation"],
            user=user,
            designation_override=placement.get("designation_override"),
            location_zone=placement.get("location_zone"),
            serial_number=placement.get("serial_number"),
            asset_tag=placement.get("asset_tag"),
            admin_force=placement.get("admin_force", False),
        )

    return part, placed_unit
