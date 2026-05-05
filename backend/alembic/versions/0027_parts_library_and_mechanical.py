"""ASTRA-SPEC-PARTS-001: parts library + mechanical joints + 13 new enums

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-01

Creates:
  * 13 PG enum types (part_type, part_status, material_class, etc.)
  * documents table (generic, non-supplier-bound file store)
  * wpn_sequences table (atomic WPN counter, one row per part type code, seeded)
  * library_parts table (global parts master record, ~70 columns)
  * pending_parts_imports table (STEP upload review queue)
  * project_parts table (project ↔ library_part join)
  * system_part_assignments table (system ↔ project_part join)
  * mechanical_joint_sequences table (per-project joint_id counter)
  * assembly_parse_jobs table (background parser tracking)
  * mechanical_joints table (joint between two ProjectParts)
  * library_part_id column on units (optional convenience FK)
  * Adds 'mechanical_joint' to source_entity_type enum

Hand-written per ASTRA-SPEC-PARTS-001 §1.4 — no autogenerate.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── PG ENUM type names + value lists ──
ENUMS: list[tuple[str, list[str]]] = [
    ("part_type", [
        "fastener", "washer", "insert", "bracket", "enclosure", "seal",
        "bearing", "hinge_latch", "thermal_interface", "pcb_mechanical", "custom",
    ]),
    ("part_status", [
        "draft", "under_review", "approved", "superseded", "obsolete",
    ]),
    ("material_class", [
        "aluminum", "titanium", "steel", "stainless_steel", "nickel_alloy",
        "polymer", "composite", "ceramic", "other",
    ]),
    ("thread_standard", [
        "iso_metric", "unc", "unf", "npt", "bspp", "an_nas_ms", "custom",
    ]),
    ("head_type", [
        "socket", "hex", "pan", "flat", "button", "torx", "fillister", "truss",
    ]),
    ("drive_type", [
        "hex_key", "torx", "phillips", "slotted", "spanner", "custom",
    ]),
    ("locking_feature", [
        "none", "nylok", "prevailing_torque", "safety_wire", "loctite",
        "castellated", "lockwire_hole",
    ]),
    ("qualification_status", [
        "unqualified", "qual_testing", "qualified", "flight_proven",
        "demanufactured",
    ]),
    ("pending_parts_status", [
        "pending", "under_review", "approved", "rejected",
    ]),
    ("confidence_level", ["high", "medium", "low"]),
    ("joint_type", [
        "bolted", "riveted", "press_fit", "adhesive", "weld", "seal",
        "alignment_pin", "thermal_bond", "spring_clip",
    ]),
    ("joint_status", ["draft", "active", "superseded"]),
    ("assembly_parse_job_status", ["queued", "running", "complete", "failed"]),
]


def _enum(name: str) -> postgresql.ENUM:
    """Reference an already-created PG enum type without recreating it."""
    return postgresql.ENUM(name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()

    # ─────────────────────────────────────────────────────────────
    # 1. CREATE TYPE: every enum BEFORE any table referencing it
    # ─────────────────────────────────────────────────────────────
    for name, values in ENUMS:
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    # Extend the existing source_entity_type enum (req_sync engine).
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction-block on
    # some PG versions; use COMMIT-then-ALTER pattern via raw SQL with
    # IF NOT EXISTS so the migration is idempotent.
    op.execute(
        "ALTER TYPE source_entity_type ADD VALUE IF NOT EXISTS 'mechanical_joint'"
    )

    # ─────────────────────────────────────────────────────────────
    # 2. documents — generic file store (non-supplier-bound)
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("document_type", sa.String(100), nullable=True),
        sa.Column(
            "uploaded_by_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "uploaded_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_documents_id", "documents", ["id"])
    op.create_index("ix_documents_sha256", "documents", ["sha256"])

    # ─────────────────────────────────────────────────────────────
    # 3. wpn_sequences — atomic WPN counter (seeded with 11 part type codes)
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "wpn_sequences",
        sa.Column("part_type_code", sa.String(8), primary_key=True),
        sa.Column(
            "next_val", sa.Integer(), nullable=False, server_default="1",
        ),
        sa.CheckConstraint("next_val >= 1", name="chk_wpn_next_val_positive"),
    )
    op.bulk_insert(
        sa.table(
            "wpn_sequences",
            sa.column("part_type_code", sa.String),
            sa.column("next_val", sa.Integer),
        ),
        [
            {"part_type_code": "FAST", "next_val": 1},
            {"part_type_code": "WASH", "next_val": 1},
            {"part_type_code": "INSR", "next_val": 1},
            {"part_type_code": "BRKT", "next_val": 1},
            {"part_type_code": "ENCL", "next_val": 1},
            {"part_type_code": "SEAL", "next_val": 1},
            {"part_type_code": "BEAR", "next_val": 1},
            {"part_type_code": "HNGL", "next_val": 1},
            {"part_type_code": "THIF", "next_val": 1},
            {"part_type_code": "PCBM", "next_val": 1},
            {"part_type_code": "CUST", "next_val": 1},
        ],
    )

    # ─────────────────────────────────────────────────────────────
    # 4. library_parts — the global parts master record
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "library_parts",
        sa.Column("id", sa.Integer(), primary_key=True),
        # Identification
        sa.Column("wardstone_part_number", sa.String(32), nullable=False),
        sa.Column("revision", sa.String(2), nullable=False, server_default="00"),
        sa.Column("part_type", _enum("part_type"), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("manufacturer_part_number", sa.String(200), nullable=True),
        sa.Column("manufacturer_name", sa.String(200), nullable=True),
        sa.Column("cage_code", sa.String(10), nullable=True),
        sa.Column("nsn", sa.String(20), nullable=True),
        sa.Column("drawing_number", sa.String(200), nullable=True),
        sa.Column("drawing_revision", sa.String(20), nullable=True),
        sa.Column("heritage", sa.Text(), nullable=True),
        sa.Column(
            "status", _enum("part_status"), nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "superseded_by_id", sa.Integer(),
            sa.ForeignKey("library_parts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Dimensional
        sa.Column("bounding_box_x_mm", sa.Numeric(12, 4), nullable=True),
        sa.Column("bounding_box_y_mm", sa.Numeric(12, 4), nullable=True),
        sa.Column("bounding_box_z_mm", sa.Numeric(12, 4), nullable=True),
        sa.Column("volume_mm3", sa.Numeric(18, 4), nullable=True),
        sa.Column("surface_area_mm2", sa.Numeric(18, 4), nullable=True),
        sa.Column("thread_size", sa.String(50), nullable=True),
        sa.Column("thread_standard", _enum("thread_standard"), nullable=True),
        sa.Column("nominal_diameter_mm", sa.Numeric(12, 4), nullable=True),
        sa.Column("nominal_length_mm", sa.Numeric(12, 4), nullable=True),
        sa.Column("head_type", _enum("head_type"), nullable=True),
        sa.Column("drive_type", _enum("drive_type"), nullable=True),
        sa.Column("nominal_bore_mm", sa.Numeric(12, 4), nullable=True),
        sa.Column("cross_section_dia_mm", sa.Numeric(12, 4), nullable=True),
        sa.Column("flange_diameter_mm", sa.Numeric(12, 4), nullable=True),
        sa.Column("hole_pattern_count", sa.Integer(), nullable=True),
        sa.Column("hole_pattern_dia_mm", sa.Numeric(12, 4), nullable=True),
        sa.Column("hole_pattern_pcd_mm", sa.Numeric(12, 4), nullable=True),
        # Material
        sa.Column("material_name", sa.String(200), nullable=True),
        sa.Column("material_standard", sa.String(200), nullable=True),
        sa.Column("material_class", _enum("material_class"), nullable=True),
        sa.Column("density_g_cm3", sa.Numeric(10, 4), nullable=True),
        sa.Column("yield_strength_mpa", sa.Numeric(10, 2), nullable=True),
        sa.Column("ultimate_strength_mpa", sa.Numeric(10, 2), nullable=True),
        sa.Column("elastic_modulus_gpa", sa.Numeric(10, 2), nullable=True),
        sa.Column("hardness", sa.String(50), nullable=True),
        sa.Column("thermal_conductivity_wm", sa.Numeric(10, 4), nullable=True),
        sa.Column("cte_um_m_c", sa.Numeric(10, 4), nullable=True),
        sa.Column("corrosion_protection", sa.String(200), nullable=True),
        sa.Column("flammability_class", sa.String(100), nullable=True),
        sa.Column("outgassing_tml_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("outgassing_cvcm_pct", sa.Numeric(8, 4), nullable=True),
        # Mechanical performance
        sa.Column("mass_nominal_g", sa.Numeric(12, 4), nullable=True),
        sa.Column("mass_max_g", sa.Numeric(12, 4), nullable=True),
        sa.Column("proof_load_n", sa.Numeric(12, 2), nullable=True),
        sa.Column("clamp_load_n", sa.Numeric(12, 2), nullable=True),
        sa.Column("torque_nominal_nm", sa.Numeric(10, 4), nullable=True),
        sa.Column("torque_min_nm", sa.Numeric(10, 4), nullable=True),
        sa.Column("torque_max_nm", sa.Numeric(10, 4), nullable=True),
        sa.Column("torque_lubricated_nm", sa.Numeric(10, 4), nullable=True),
        sa.Column(
            "locking_feature", _enum("locking_feature"),
            nullable=True, server_default="none",
        ),
        sa.Column("safety_wire_holes", sa.Boolean(), nullable=True),
        sa.Column("shear_strength_n", sa.Numeric(12, 2), nullable=True),
        sa.Column("bearing_load_n", sa.Numeric(12, 2), nullable=True),
        sa.Column("compression_set_pct", sa.Numeric(8, 2), nullable=True),
        sa.Column("sealing_pressure_max_bar", sa.Numeric(10, 3), nullable=True),
        sa.Column("temperature_min_c", sa.Numeric(8, 2), nullable=True),
        sa.Column("temperature_max_c", sa.Numeric(8, 2), nullable=True),
        # Procurement
        sa.Column("unit_cost_usd", sa.Numeric(12, 4), nullable=True),
        sa.Column("lead_time_weeks", sa.Integer(), nullable=True),
        sa.Column("min_order_qty", sa.Integer(), nullable=True),
        sa.Column(
            "preferred_supplier_id", sa.Integer(),
            sa.ForeignKey("suppliers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("supplier_part_number", sa.String(200), nullable=True),
        sa.Column(
            "qualification_status", _enum("qualification_status"),
            nullable=True, server_default="unqualified",
        ),
        sa.Column("qualification_basis", sa.Text(), nullable=True),
        sa.Column("shelf_life_months", sa.Integer(), nullable=True),
        sa.Column("date_of_manufacture", sa.Date(), nullable=True),
        sa.Column(
            "restricted_use", sa.Boolean(), nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("restriction_notes", sa.Text(), nullable=True),
        # STEP traceability
        sa.Column(
            "step_file_id", sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("step_file_checksum", sa.String(64), nullable=True),
        sa.Column("step_entity_id", sa.String(200), nullable=True),
        # Approval
        sa.Column(
            "approved_by_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        # Audit
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "created_by_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        # Constraints
        sa.UniqueConstraint("wardstone_part_number", name="uq_library_part_wpn"),
        sa.CheckConstraint(
            "revision ~ '^[0-9]{2}$'", name="chk_library_part_revision_format",
        ),
        sa.CheckConstraint(
            "hole_pattern_count IS NULL OR hole_pattern_count > 0",
            name="chk_lp_hole_pattern_count_positive",
        ),
        sa.CheckConstraint(
            "density_g_cm3 IS NULL OR density_g_cm3 > 0",
            name="chk_lp_density_positive",
        ),
        sa.CheckConstraint(
            "yield_strength_mpa IS NULL OR yield_strength_mpa >= 0",
            name="chk_lp_yield_nonneg",
        ),
        sa.CheckConstraint(
            "ultimate_strength_mpa IS NULL OR ultimate_strength_mpa >= 0",
            name="chk_lp_uts_nonneg",
        ),
        sa.CheckConstraint(
            "elastic_modulus_gpa IS NULL OR elastic_modulus_gpa > 0",
            name="chk_lp_elastic_positive",
        ),
        sa.CheckConstraint(
            "thermal_conductivity_wm IS NULL OR thermal_conductivity_wm >= 0",
            name="chk_lp_thermal_cond_nonneg",
        ),
        sa.CheckConstraint(
            "outgassing_tml_pct IS NULL OR outgassing_tml_pct >= 0",
            name="chk_lp_outgassing_tml_nonneg",
        ),
        sa.CheckConstraint(
            "outgassing_cvcm_pct IS NULL OR outgassing_cvcm_pct >= 0",
            name="chk_lp_outgassing_cvcm_nonneg",
        ),
        sa.CheckConstraint(
            "mass_nominal_g IS NULL OR mass_nominal_g >= 0",
            name="chk_lp_mass_nominal_nonneg",
        ),
        sa.CheckConstraint(
            "mass_max_g IS NULL OR mass_max_g >= 0",
            name="chk_lp_mass_max_nonneg",
        ),
        sa.CheckConstraint(
            "proof_load_n IS NULL OR proof_load_n >= 0",
            name="chk_lp_proof_load_nonneg",
        ),
        sa.CheckConstraint(
            "clamp_load_n IS NULL OR clamp_load_n >= 0",
            name="chk_lp_clamp_load_nonneg",
        ),
        sa.CheckConstraint(
            "torque_nominal_nm IS NULL OR torque_nominal_nm >= 0",
            name="chk_lp_torque_nom_nonneg",
        ),
        sa.CheckConstraint(
            "torque_min_nm IS NULL OR torque_min_nm >= 0",
            name="chk_lp_torque_min_nonneg",
        ),
        sa.CheckConstraint(
            "torque_max_nm IS NULL OR torque_max_nm >= 0",
            name="chk_lp_torque_max_nonneg",
        ),
        sa.CheckConstraint(
            "torque_lubricated_nm IS NULL OR torque_lubricated_nm >= 0",
            name="chk_lp_torque_lub_nonneg",
        ),
        sa.CheckConstraint(
            "shear_strength_n IS NULL OR shear_strength_n >= 0",
            name="chk_lp_shear_nonneg",
        ),
        sa.CheckConstraint(
            "bearing_load_n IS NULL OR bearing_load_n >= 0",
            name="chk_lp_bearing_load_nonneg",
        ),
        sa.CheckConstraint(
            "compression_set_pct IS NULL OR "
            "(compression_set_pct >= 0 AND compression_set_pct <= 100)",
            name="chk_lp_compression_set_pct",
        ),
        sa.CheckConstraint(
            "sealing_pressure_max_bar IS NULL OR sealing_pressure_max_bar >= 0",
            name="chk_lp_sealing_pressure_nonneg",
        ),
        sa.CheckConstraint(
            "temperature_min_c IS NULL OR temperature_max_c IS NULL OR "
            "temperature_min_c < temperature_max_c",
            name="chk_lp_temp_range",
        ),
        sa.CheckConstraint(
            "torque_min_nm IS NULL OR torque_max_nm IS NULL OR "
            "torque_min_nm <= torque_max_nm",
            name="chk_lp_torque_range",
        ),
        sa.CheckConstraint(
            "mass_nominal_g IS NULL OR mass_max_g IS NULL OR "
            "mass_max_g >= mass_nominal_g",
            name="chk_lp_mass_range",
        ),
        sa.CheckConstraint(
            "unit_cost_usd IS NULL OR unit_cost_usd >= 0",
            name="chk_lp_unit_cost_nonneg",
        ),
        sa.CheckConstraint(
            "lead_time_weeks IS NULL OR lead_time_weeks >= 0",
            name="chk_lp_lead_time_nonneg",
        ),
        sa.CheckConstraint(
            "min_order_qty IS NULL OR min_order_qty >= 1",
            name="chk_lp_min_order_qty_positive",
        ),
        sa.CheckConstraint(
            "shelf_life_months IS NULL OR shelf_life_months > 0",
            name="chk_lp_shelf_life_positive",
        ),
        sa.CheckConstraint(
            "status != 'approved' OR "
            "(approved_by_id IS NOT NULL AND approved_at IS NOT NULL)",
            name="chk_lp_approved_fields",
        ),
    )
    op.create_index("ix_library_parts_id", "library_parts", ["id"])
    op.create_index(
        "ix_library_part_type_status", "library_parts", ["part_type", "status"]
    )
    op.create_index(
        "ix_library_part_step_checksum", "library_parts", ["step_file_checksum"],
        postgresql_where=sa.text("step_file_checksum IS NOT NULL"),
    )
    op.create_index(
        "ix_library_part_mpn", "library_parts", ["manufacturer_part_number"],
        postgresql_where=sa.text("manufacturer_part_number IS NOT NULL"),
    )
    op.create_index(
        "ix_library_parts_part_type", "library_parts", ["part_type"]
    )
    op.create_index(
        "ix_library_parts_status", "library_parts", ["status"]
    )
    op.create_index(
        "ix_library_parts_preferred_supplier_id", "library_parts",
        ["preferred_supplier_id"]
    )

    # ─────────────────────────────────────────────────────────────
    # 5. pending_parts_imports — STEP upload review queue
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "pending_parts_imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "document_id", sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status", _enum("pending_parts_status"),
            nullable=False, server_default="pending",
        ),
        sa.Column(
            "proposed_data", postgresql.JSONB(),
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "confidence_scores", postgresql.JSONB(),
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "low_confidence_fields", postgresql.ARRAY(sa.String()),
            nullable=False, server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column("extraction_log", sa.Text(), nullable=True),
        sa.Column("parser_version", sa.String(32), nullable=True),
        sa.Column(
            "reviewed_by_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column(
            "library_part_id", sa.Integer(),
            sa.ForeignKey("library_parts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "created_by_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_index("ix_pending_parts_imports_id", "pending_parts_imports", ["id"])
    op.create_index(
        "ix_pending_parts_imports_document_id", "pending_parts_imports", ["document_id"]
    )
    op.create_index(
        "ix_pending_parts_imports_status", "pending_parts_imports", ["status"]
    )

    # ─────────────────────────────────────────────────────────────
    # 6. project_parts — project ↔ library_part join
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "project_parts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id", sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "library_part_id", sa.Integer(),
            sa.ForeignKey("library_parts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "quantity", sa.Integer(), nullable=False, server_default="1",
        ),
        sa.Column("designation", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "added_by_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "added_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint(
            "project_id", "library_part_id", name="uq_project_part",
        ),
        sa.CheckConstraint("quantity >= 1", name="chk_pp_quantity_positive"),
    )
    op.create_index("ix_project_parts_id", "project_parts", ["id"])
    op.create_index("ix_project_parts_project", "project_parts", ["project_id"])
    op.create_index("ix_project_parts_library", "project_parts", ["library_part_id"])

    # ─────────────────────────────────────────────────────────────
    # 7. system_part_assignments — system ↔ project_part join
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "system_part_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "system_id", sa.Integer(),
            sa.ForeignKey("systems.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_part_id", sa.Integer(),
            sa.ForeignKey("project_parts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "position_order", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "assigned_by_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "assigned_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint(
            "system_id", "project_part_id", name="uq_system_part_assignment",
        ),
    )
    op.create_index("ix_system_part_assignments_id", "system_part_assignments", ["id"])
    op.create_index("ix_spa_system", "system_part_assignments", ["system_id"])
    op.create_index("ix_spa_ppart", "system_part_assignments", ["project_part_id"])

    # ─────────────────────────────────────────────────────────────
    # 8. mechanical_joint_sequences — per-project joint_id counter
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "mechanical_joint_sequences",
        sa.Column("project_id", sa.Integer(), primary_key=True),
        sa.Column(
            "next_val", sa.Integer(), nullable=False, server_default="1",
        ),
        sa.CheckConstraint("next_val >= 1", name="chk_mjs_next_val_positive"),
    )

    # ─────────────────────────────────────────────────────────────
    # 9. assembly_parse_jobs — background parser tracking
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "assembly_parse_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id", sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id", sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status", _enum("assembly_parse_job_status"),
            nullable=False, server_default="queued",
        ),
        sa.Column("progress_log", sa.Text(), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_by_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=True,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_assembly_parse_jobs_id", "assembly_parse_jobs", ["id"])
    op.create_index("ix_apj_project", "assembly_parse_jobs", ["project_id"])
    op.create_index("ix_apj_status", "assembly_parse_jobs", ["status"])

    # ─────────────────────────────────────────────────────────────
    # 10. mechanical_joints — joint between two ProjectParts
    # ─────────────────────────────────────────────────────────────
    op.create_table(
        "mechanical_joints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("joint_id", sa.String(32), nullable=False),
        sa.Column(
            "project_id", sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("joint_type", _enum("joint_type"), nullable=False),
        sa.Column(
            "part_a_id", sa.Integer(),
            sa.ForeignKey("project_parts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "part_b_id", sa.Integer(),
            sa.ForeignKey("project_parts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "fastener_part_id", sa.Integer(),
            sa.ForeignKey("library_parts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("fastener_count", sa.Integer(), nullable=True),
        sa.Column("torque_nominal_nm", sa.Numeric(10, 4), nullable=True),
        sa.Column("torque_min_nm", sa.Numeric(10, 4), nullable=True),
        sa.Column("torque_max_nm", sa.Numeric(10, 4), nullable=True),
        sa.Column("engagement_length_mm", sa.Numeric(10, 4), nullable=True),
        sa.Column("locking_feature", _enum("locking_feature"), nullable=True),
        sa.Column("hole_pattern_description", sa.String(300), nullable=True),
        sa.Column("mating_surface_flatness_mm", sa.Numeric(10, 4), nullable=True),
        sa.Column("mating_surface_finish_ra", sa.Numeric(10, 4), nullable=True),
        sa.Column(
            "seal_part_id", sa.Integer(),
            sa.ForeignKey("library_parts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("leak_rate_max_scc_s", sa.Numeric(12, 6), nullable=True),
        sa.Column("test_pressure_bar", sa.Numeric(10, 3), nullable=True),
        sa.Column("interface_drawing", sa.String(200), nullable=True),
        sa.Column(
            "source_step_file_id", sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_step_entity", sa.Text(), nullable=True),
        sa.Column("confidence", _enum("confidence_level"), nullable=True),
        sa.Column(
            "status", _enum("joint_status"),
            nullable=False, server_default="draft",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "created_by_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.UniqueConstraint("joint_id", name="uq_mj_joint_id"),
        sa.CheckConstraint("part_a_id != part_b_id", name="chk_mj_parts_different"),
        sa.CheckConstraint(
            "fastener_count IS NULL OR fastener_count > 0",
            name="chk_mj_fastener_count_positive",
        ),
        sa.CheckConstraint(
            "torque_nominal_nm IS NULL OR torque_nominal_nm >= 0",
            name="chk_mj_torque_nom_nonneg",
        ),
        sa.CheckConstraint(
            "torque_min_nm IS NULL OR torque_min_nm >= 0",
            name="chk_mj_torque_min_nonneg",
        ),
        sa.CheckConstraint(
            "torque_max_nm IS NULL OR torque_max_nm >= 0",
            name="chk_mj_torque_max_nonneg",
        ),
        sa.CheckConstraint(
            "torque_min_nm IS NULL OR torque_max_nm IS NULL OR "
            "torque_min_nm <= torque_max_nm",
            name="chk_mj_torque_range",
        ),
        sa.CheckConstraint(
            "engagement_length_mm IS NULL OR engagement_length_mm > 0",
            name="chk_mj_engagement_positive",
        ),
        sa.CheckConstraint(
            "mating_surface_flatness_mm IS NULL OR mating_surface_flatness_mm > 0",
            name="chk_mj_flatness_positive",
        ),
        sa.CheckConstraint(
            "mating_surface_finish_ra IS NULL OR mating_surface_finish_ra > 0",
            name="chk_mj_finish_positive",
        ),
        sa.CheckConstraint(
            "leak_rate_max_scc_s IS NULL OR leak_rate_max_scc_s > 0",
            name="chk_mj_leak_rate_positive",
        ),
        sa.CheckConstraint(
            "test_pressure_bar IS NULL OR test_pressure_bar > 0",
            name="chk_mj_test_pressure_positive",
        ),
    )
    op.create_index("ix_mechanical_joints_id", "mechanical_joints", ["id"])
    op.create_index("ix_mj_project_status", "mechanical_joints", ["project_id", "status"])
    op.create_index("ix_mj_parts", "mechanical_joints", ["part_a_id", "part_b_id"])
    op.create_index("ix_mj_joint_id", "mechanical_joints", ["joint_id"])
    op.create_index("ix_mechanical_joints_part_a", "mechanical_joints", ["part_a_id"])
    op.create_index("ix_mechanical_joints_part_b", "mechanical_joints", ["part_b_id"])
    op.create_index("ix_mechanical_joints_project_id", "mechanical_joints", ["project_id"])
    op.create_index("ix_mechanical_joints_status", "mechanical_joints", ["status"])

    # ─────────────────────────────────────────────────────────────
    # 11. units.library_part_id — optional convenience FK
    # ─────────────────────────────────────────────────────────────
    op.add_column(
        "units",
        sa.Column(
            "library_part_id", sa.Integer(),
            sa.ForeignKey("library_parts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    # Drop in reverse FK dependency order.
    op.drop_column("units", "library_part_id")

    op.drop_index("ix_mechanical_joints_status", table_name="mechanical_joints")
    op.drop_index("ix_mechanical_joints_project_id", table_name="mechanical_joints")
    op.drop_index("ix_mechanical_joints_part_b", table_name="mechanical_joints")
    op.drop_index("ix_mechanical_joints_part_a", table_name="mechanical_joints")
    op.drop_index("ix_mj_joint_id", table_name="mechanical_joints")
    op.drop_index("ix_mj_parts", table_name="mechanical_joints")
    op.drop_index("ix_mj_project_status", table_name="mechanical_joints")
    op.drop_index("ix_mechanical_joints_id", table_name="mechanical_joints")
    op.drop_table("mechanical_joints")

    op.drop_index("ix_apj_status", table_name="assembly_parse_jobs")
    op.drop_index("ix_apj_project", table_name="assembly_parse_jobs")
    op.drop_index("ix_assembly_parse_jobs_id", table_name="assembly_parse_jobs")
    op.drop_table("assembly_parse_jobs")

    op.drop_table("mechanical_joint_sequences")

    op.drop_index("ix_spa_ppart", table_name="system_part_assignments")
    op.drop_index("ix_spa_system", table_name="system_part_assignments")
    op.drop_index("ix_system_part_assignments_id", table_name="system_part_assignments")
    op.drop_table("system_part_assignments")

    op.drop_index("ix_project_parts_library", table_name="project_parts")
    op.drop_index("ix_project_parts_project", table_name="project_parts")
    op.drop_index("ix_project_parts_id", table_name="project_parts")
    op.drop_table("project_parts")

    op.drop_index("ix_pending_parts_imports_status", table_name="pending_parts_imports")
    op.drop_index("ix_pending_parts_imports_document_id", table_name="pending_parts_imports")
    op.drop_index("ix_pending_parts_imports_id", table_name="pending_parts_imports")
    op.drop_table("pending_parts_imports")

    op.drop_index("ix_library_parts_preferred_supplier_id", table_name="library_parts")
    op.drop_index("ix_library_parts_status", table_name="library_parts")
    op.drop_index("ix_library_parts_part_type", table_name="library_parts")
    op.drop_index("ix_library_part_mpn", table_name="library_parts")
    op.drop_index("ix_library_part_step_checksum", table_name="library_parts")
    op.drop_index("ix_library_part_type_status", table_name="library_parts")
    op.drop_index("ix_library_parts_id", table_name="library_parts")
    op.drop_table("library_parts")

    op.drop_table("wpn_sequences")

    op.drop_index("ix_documents_sha256", table_name="documents")
    op.drop_index("ix_documents_id", table_name="documents")
    op.drop_table("documents")

    # Drop new enum types (in reverse to avoid dependency issues).
    bind = op.get_bind()
    for name, _values in reversed(ENUMS):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
    # Cannot remove a value from an enum via ALTER TYPE; leave
    # 'mechanical_joint' on source_entity_type. Idempotent on re-upgrade.
