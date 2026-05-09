// ══════════════════════════════════════════════════════════════
//  ASTRA — Supplier Catalog TypeScript Types
//  Mirrors backend Pydantic schemas in schemas/catalog.py
//
//  File: frontend/src/lib/catalog-types.ts
//  Path: C:\Users\Mason\Documents\ASTRA\frontend\src\lib\catalog-types.ts
//  Phase 3 — ASTRA-TDD-INTF-002
//
//  Naming-collision note
//  ---------------------
//  The existing `interface-types.ts` already exports `ConnectorGender`,
//  `SignalType`, and a few other names with project-side semantics. The
//  catalog-side enums use a `Catalog` prefix so callers can import both
//  (a project-side ConnectorGender uses values like 'male_pin'; the
//  catalog-side CatalogConnectorGender uses 'male'/'female'/'hermaphroditic').
// ══════════════════════════════════════════════════════════════

// ── Enums (literal unions; F-123 — no `| string` collapse) ──

export type PartClass =
  // ── Existing electrical / electronic values (INTF-002) ──
  | 'processor'
  | 'sensor'
  | 'power_supply'
  | 'radio'
  | 'antenna'
  | 'actuator'
  | 'display'
  | 'harness'
  | 'connector_only'
  | 'compute_module'
  | 'power_distribution'
  | 'interface_card'
  | 'other'
  // ── TDD-CAT-002: mechanical / structural values ──
  | 'fastener_screw'
  | 'fastener_bolt'
  | 'nut'
  | 'washer'
  | 'bracket'
  | 'housing'
  | 'enclosure'
  | 'seal_o_ring'
  | 'bearing'
  | 'spring'
  | 'structural_member'
  | 'mechanical_other';

export type LRUClass =
  | 'lru'
  | 'sru'
  | 'wra'
  | 'subassembly'
  | 'component';

export type LifecycleStatus =
  | 'active'
  | 'preferred'
  | 'obsolete'
  | 'eol_announced'
  | 'nrnd'
  | 'restricted';

export type CatalogConnectorGender =
  | 'male'
  | 'female'
  | 'hermaphroditic'
  | 'unknown';

export type CatalogSignalType =
  | 'power'
  | 'ground'
  | 'digital'
  | 'analog'
  | 'diff_pair'
  | 'rf'
  | 'discrete'
  | 'no_connect'
  | 'reserved'
  | 'unknown';

export type CatalogSignalDirection =
  | 'input'
  | 'output'
  | 'bidirectional'
  | 'power'
  | 'ground'
  | 'unknown';

export type SupplierDocumentType =
  | 'icd'
  | 'datasheet'
  | 'spec_sheet'
  | 'drawing'
  | 'app_note'
  | 'user_manual'
  | 'other';

export type ExtractionStatus =
  | 'uploaded'
  | 'extracting'
  | 'pending_review'
  | 'approved'
  | 'rejected'
  | 'failed';

export type PendingImportStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'superseded';


// ══════════════════════════════════════════════════════════════
//  Supplier
// ══════════════════════════════════════════════════════════════

/**
 * Mirrors `SupplierResponse` in backend/app/schemas/catalog.py.
 *
 * `catalog_part_count` and `document_count` are computed by the router.
 */
export interface Supplier {
  id: number;
  name: string;
  short_name?: string | null;
  cage_code?: string | null;
  duns?: string | null;
  website?: string | null;
  address?: string | null;
  country?: string | null;
  primary_contact?: string | null;
  primary_email?: string | null;
  notes?: string | null;
  is_active: boolean;
  /** TDD-CAT-002 — Wardstone is the in-house default for STEP files
   *  with no detected vendor. */
  is_in_house?: boolean;
  created_at: string;
  updated_at: string;
  created_by_id: number;
  catalog_part_count: number;
  document_count: number;
}


/** TDD-CAT-002 — one row of supplier_aliases. */
export interface SupplierAlias {
  id: number;
  supplier_id: number;
  alias: string;
  created_at: string;
}

/**
 * Detail shape used by the supplier-detail page. Currently the backend
 * returns the same `SupplierResponse` for both list and detail; this
 * alias exists so future enrichment (e.g. eager documents/parts) can
 * be added without breaking call sites.
 */
export interface SupplierDetail extends Supplier {
  // Reserved for future eager-loaded relationships.
}


// ══════════════════════════════════════════════════════════════
//  SupplierDocument
// ══════════════════════════════════════════════════════════════

export interface SupplierDocument {
  id: number;
  supplier_id: number;
  title: string;
  document_type: SupplierDocumentType;
  revision?: string | null;
  document_number?: string | null;
  /** ISO-8601 date string (YYYY-MM-DD) or null. */
  publication_date?: string | null;
  file_path: string;
  file_size_bytes: number;
  sha256: string;
  mime_type: string;
  page_count?: number | null;
  extraction_status: ExtractionStatus;
  extraction_log?: Record<string, unknown> | null;
  extraction_at?: string | null;
  uploaded_at: string;
  uploaded_by_id: number;
}


// ══════════════════════════════════════════════════════════════
//  CatalogPin
// ══════════════════════════════════════════════════════════════

export interface CatalogPin {
  id: number;
  catalog_connector_id: number;
  pin_position: string;
  mfr_pin_name: string;
  mfr_signal_function?: string | null;
  mfr_signal_type?: CatalogSignalType | null;
  mfr_direction?: CatalogSignalDirection | null;
  /** Decimal serialised as string by Pydantic — parse with parseFloat() if needed. */
  mfr_voltage_min_v?: string | null;
  mfr_voltage_max_v?: string | null;
  mfr_current_max_ma?: string | null;
  mfr_impedance_ohm?: string | null;
  mfr_protocol_hint?: string | null;
  mfr_is_paired_with?: string | null;
  is_no_connect: boolean;
  is_reserved: boolean;
  is_chassis_ground: boolean;
  notes?: string | null;
}

export interface CatalogPinCreate {
  pin_position: string;
  mfr_pin_name: string;
  mfr_signal_function?: string | null;
  mfr_signal_type?: CatalogSignalType | null;
  mfr_direction?: CatalogSignalDirection | null;
  mfr_voltage_min_v?: string | number | null;
  mfr_voltage_max_v?: string | number | null;
  mfr_current_max_ma?: string | number | null;
  mfr_impedance_ohm?: string | number | null;
  mfr_protocol_hint?: string | null;
  mfr_is_paired_with?: string | null;
  is_no_connect?: boolean;
  is_reserved?: boolean;
  is_chassis_ground?: boolean;
  notes?: string | null;
}


// ══════════════════════════════════════════════════════════════
//  CatalogConnector
// ══════════════════════════════════════════════════════════════

export interface CatalogConnector {
  id: number;
  catalog_part_id: number;
  reference: string;
  position: number;
  description?: string | null;
  connector_type?: string | null;
  shell_size?: string | null;
  insert_arrangement?: string | null;
  gender?: CatalogConnectorGender | null;
  pin_count: number;
  keying?: string | null;
  mating_part_number?: string | null;
  notes?: string | null;
  pins: CatalogPin[];
}

export interface CatalogConnectorCreate {
  reference: string;
  position?: number;
  description?: string | null;
  connector_type?: string | null;
  shell_size?: string | null;
  insert_arrangement?: string | null;
  gender?: CatalogConnectorGender | null;
  pin_count?: number;
  keying?: string | null;
  mating_part_number?: string | null;
  notes?: string | null;
  pins?: CatalogPinCreate[];
}


// ══════════════════════════════════════════════════════════════
//  CatalogPart
// ══════════════════════════════════════════════════════════════

/**
 * Summary row returned by GET /catalog/parts (list view).
 * Mirrors `CatalogPartSummary` in backend/app/schemas/catalog.py.
 */
export interface CatalogPart {
  id: number;
  supplier_id: number;
  supplier_name?: string | null;
  part_number: string;
  revision?: string | null;
  name: string;
  designation?: string | null;
  part_class: PartClass;
  lru_classification: LRUClass;
  lifecycle_status: LifecycleStatus;
  /** Decimal serialised as string. */
  mass_kg?: string | null;
  power_watts_nominal?: string | null;
  used_in_project_count: number;
  // ── TDD-CAT-002 (chip-render only — full CAD on detail) ──
  part_subtype?: string | null;
  material_class?: string | null;
}

/**
 * Detail shape returned by GET /catalog/parts/{id}. Eagerly loads
 * connectors+pins; mirrors `CatalogPartResponse`.
 */
export interface CatalogPartDetail extends CatalogPart {
  description?: string | null;
  // Physical
  dim_length_mm?: string | null;
  dim_width_mm?: string | null;
  dim_height_mm?: string | null;
  // Power
  power_watts_peak?: string | null;
  voltage_input_min_v?: string | null;
  voltage_input_max_v?: string | null;
  // Environmental
  temp_operating_min_c?: string | null;
  temp_operating_max_c?: string | null;
  temp_storage_min_c?: string | null;
  temp_storage_max_c?: string | null;
  vibration_random_grms?: string | null;
  shock_mechanical_g?: string | null;
  humidity_max_pct?: string | null;
  altitude_max_m?: string | null;
  emi_ce102_limit_dbua?: string | null;
  emi_rs103_limit_vm?: string | null;
  esd_hbm_v?: string | null;
  // Compliance
  mil_std_810_tested: boolean;
  mil_std_461_tested: boolean;
  rohs_compliant: boolean;
  itar_controlled: boolean;
  export_classification?: string | null;
  // Lifecycle
  /** ISO-8601 date string. */
  eol_date?: string | null;
  // Variant tree
  parent_part_id?: number | null;
  variant_label?: string | null;
  // Source
  source_document_id?: number | null;
  source_page_refs?: Record<string, unknown> | null;
  notes?: string | null;
  image_path?: string | null;
  // ── TDD-CAT-002 detail fields ──
  material_name?: string | null;
  bbox_x_mm?: string | null;
  bbox_y_mm?: string | null;
  bbox_z_mm?: string | null;
  volume_mm3?: string | null;
  cad_step_path?: string | null;
  cad_preview_path?: string | null;
  cad_authoring_tool?: string | null;
  native_units?: string | null;
  deleted_at?: string | null;
  created_at: string;
  updated_at: string;
  created_by_id: number;
  connectors: CatalogConnector[];
}


/** TDD-CAT-002 — body returned by POST /catalog/upload-step. */
export interface StepUploadResponse {
  pending_import_id: number;
  supplier_document_id: number;
  detected_supplier_id: number;
  detected_supplier_name: string;
  supplier_was_created: boolean;
  extraction_confidence: number;
  warnings: string[];
}

/**
 * Body of POST /catalog/parts. The caller may include nested
 * `connectors` (each with nested `pins`) for an atomic create.
 */
export interface CatalogPartCreatePayload {
  supplier_id: number;
  part_number: string;
  revision?: string | null;
  name: string;
  designation?: string | null;
  description?: string | null;
  part_class: PartClass;
  lru_classification?: LRUClass;
  // Physical
  mass_kg?: string | number | null;
  dim_length_mm?: string | number | null;
  dim_width_mm?: string | number | null;
  dim_height_mm?: string | number | null;
  // Power
  power_watts_nominal?: string | number | null;
  power_watts_peak?: string | number | null;
  voltage_input_min_v?: string | number | null;
  voltage_input_max_v?: string | number | null;
  // Environmental
  temp_operating_min_c?: string | number | null;
  temp_operating_max_c?: string | number | null;
  temp_storage_min_c?: string | number | null;
  temp_storage_max_c?: string | number | null;
  vibration_random_grms?: string | number | null;
  shock_mechanical_g?: string | number | null;
  humidity_max_pct?: string | number | null;
  altitude_max_m?: string | number | null;
  emi_ce102_limit_dbua?: string | number | null;
  emi_rs103_limit_vm?: string | number | null;
  esd_hbm_v?: string | number | null;
  // Compliance
  mil_std_810_tested?: boolean;
  mil_std_461_tested?: boolean;
  rohs_compliant?: boolean;
  itar_controlled?: boolean;
  export_classification?: string | null;
  // Lifecycle
  lifecycle_status?: LifecycleStatus;
  eol_date?: string | null;
  // Variant
  parent_part_id?: number | null;
  variant_label?: string | null;
  // Source
  source_document_id?: number | null;
  source_page_refs?: Record<string, unknown> | null;
  notes?: string | null;
  image_path?: string | null;
  connectors?: CatalogConnectorCreate[];
}

/**
 * Body of POST /catalog/parts/{id}/place — places an existing catalog part
 * into a project as a Unit. Mirrors `CatalogPartPlacementRequest`.
 */
export interface CatalogPartPlacementRequest {
  project_id: number;
  system_id: number;
  unit_id_tag: string;
  designation_override?: string | null;
  location_zone?: string | null;
  serial_number?: string | null;
  asset_tag?: string | null;
  /** Required when placing parts whose lifecycle_status is RESTRICTED. */
  admin_force?: boolean;
}

/**
 * One row of GET /catalog/parts/{id}/usage — a placed Unit instance.
 * Mirrors `CatalogPartUsageRow`.
 */
export interface CatalogPartUsage {
  unit_id: number;
  project_id: number;
  project_code?: string | null;
  system_id: number;
  designation: string;
  location_zone?: string | null;
  serial_number?: string | null;
}

/**
 * Body of POST /catalog/parts/{id}/variant — clones the parent part
 * with a new variant_label and (optionally) connectors+pins.
 */
export interface CatalogPartVariantRequest {
  variant_label: string;
  revision?: string | null;
  name?: string | null;
  designation?: string | null;
  notes?: string | null;
  copy_connectors?: boolean;
}


// ══════════════════════════════════════════════════════════════
//  PendingCatalogImport
// ══════════════════════════════════════════════════════════════

export interface PendingCatalogImport {
  id: number;
  source_document_id: number;
  supplier_id: number;
  extracted_data: Record<string, unknown>;
  extraction_warnings?: Record<string, unknown> | null;
  /** Decimal serialised as string. */
  extraction_confidence?: string | null;
  status: PendingImportStatus;
  committed_catalog_part_id?: number | null;
  rejection_reason?: string | null;
  reviewer_notes?: string | null;
  created_at: string;
  reviewed_at?: string | null;
  reviewed_by_id?: number | null;
}

export interface PendingCatalogImportUpdate {
  extracted_data?: Record<string, unknown>;
  extraction_warnings?: Record<string, unknown>;
  extraction_confidence?: string | number;
  rejection_reason?: string;
  reviewer_notes?: string;
}


// ══════════════════════════════════════════════════════════════
//  UI helpers
// ══════════════════════════════════════════════════════════════

/**
 * Lifecycle-status pill colour. Pair with a text label so the
 * signalling is not colour-only (a11y carry-forward).
 */
export const LIFECYCLE_COLORS: Record<LifecycleStatus, { bg: string; text: string; label: string }> = {
  active:        { bg: 'rgba(16,185,129,0.15)', text: '#10B981', label: 'Active' },
  preferred:     { bg: 'rgba(59,130,246,0.18)', text: '#60A5FA', label: 'Preferred' },
  obsolete:      { bg: 'rgba(100,116,139,0.18)', text: '#94A3B8', label: 'Obsolete' },
  eol_announced: { bg: 'rgba(245,158,11,0.18)', text: '#F59E0B', label: 'EOL Announced' },
  nrnd:          { bg: 'rgba(245,158,11,0.18)', text: '#F59E0B', label: 'NRND' },
  restricted:    { bg: 'rgba(239,68,68,0.20)',  text: '#F87171', label: 'Restricted' },
};

/** Human-readable label for a `PartClass` value. */
export const PART_CLASS_LABELS: Record<PartClass, string> = {
  processor:           'Processor',
  sensor:              'Sensor',
  power_supply:        'Power Supply',
  radio:               'Radio',
  antenna:             'Antenna',
  actuator:            'Actuator',
  display:             'Display',
  harness:             'Harness',
  connector_only:      'Connector (Only)',
  compute_module:      'Compute Module',
  power_distribution:  'Power Distribution',
  interface_card:      'Interface Card',
  other:               'Other',
  // TDD-CAT-002 mechanical / structural values
  fastener_screw:      'Fastener — Screw',
  fastener_bolt:       'Fastener — Bolt',
  nut:                 'Nut',
  washer:              'Washer',
  bracket:             'Bracket',
  housing:             'Housing',
  enclosure:           'Enclosure',
  seal_o_ring:         'Seal / O-Ring',
  bearing:             'Bearing',
  spring:              'Spring',
  structural_member:   'Structural Member',
  mechanical_other:    'Mechanical (Other)',
};

/** Human-readable label for an `LRUClass` value. */
export const LRU_CLASS_LABELS: Record<LRUClass, string> = {
  lru:         'LRU',
  sru:         'SRU',
  wra:         'WRA',
  subassembly: 'Subassembly',
  component:   'Component',
};

/** Human-readable label for a `SupplierDocumentType` value. */
export const DOCUMENT_TYPE_LABELS: Record<SupplierDocumentType, string> = {
  icd:         'ICD',
  datasheet:   'Datasheet',
  spec_sheet:  'Spec Sheet',
  drawing:     'Drawing',
  app_note:    'App Note',
  user_manual: 'User Manual',
  other:       'Other',
};

/** Human-readable label for an `ExtractionStatus` value. */
export const EXTRACTION_STATUS_LABELS: Record<ExtractionStatus, string> = {
  uploaded:       'Uploaded',
  extracting:     'Extracting',
  pending_review: 'Pending Review',
  approved:       'Approved',
  rejected:       'Rejected',
  failed:         'Failed',
};

/** Human-readable label for a `PendingImportStatus` value. */
export const PENDING_IMPORT_STATUS_LABELS: Record<PendingImportStatus, string> = {
  pending:    'Pending',
  approved:   'Approved',
  rejected:   'Rejected',
  superseded: 'Superseded',
};
