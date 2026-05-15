// ASTRA — Parts Library & Mechanical Joints — TypeScript types
// Generated to match backend Pydantic schemas in app/schemas/parts_library.py

export type PartType =
  | 'fastener' | 'washer' | 'insert' | 'bracket' | 'enclosure'
  | 'seal' | 'bearing' | 'hinge_latch' | 'thermal_interface'
  | 'pcb_mechanical' | 'custom';

export type PartStatus =
  | 'draft' | 'under_review' | 'approved' | 'superseded' | 'obsolete';

export type MaterialClass =
  | 'aluminum' | 'titanium' | 'steel' | 'stainless_steel'
  | 'nickel_alloy' | 'polymer' | 'composite' | 'ceramic' | 'other';

export type ThreadStandard =
  | 'iso_metric' | 'unc' | 'unf' | 'npt' | 'bspp' | 'an_nas_ms' | 'custom';

export type LockingFeature =
  | 'none' | 'nylok' | 'prevailing_torque' | 'safety_wire'
  | 'loctite' | 'castellated' | 'lockwire_hole';

export type QualificationStatus =
  | 'unqualified' | 'qual_testing' | 'qualified'
  | 'flight_proven' | 'demanufactured';

export type JointType =
  | 'bolted' | 'riveted' | 'press_fit' | 'adhesive' | 'weld'
  | 'seal' | 'alignment_pin' | 'thermal_bond' | 'spring_clip';

export type JointStatus = 'draft' | 'active' | 'superseded';
export type ConfidenceLevel = 'high' | 'medium' | 'low';

export type PendingPartsStatus =
  | 'pending' | 'under_review' | 'approved' | 'rejected';

export type AssemblyParseJobStatus =
  | 'queued' | 'running' | 'complete' | 'failed';

// Numeric fields arrive from backend as strings (Decimal serialization)
export interface LibraryPartSummary {
  id: number;
  wardstone_part_number: string;
  revision: string;
  part_type: PartType;
  name: string;
  status: PartStatus;
  manufacturer_name: string | null;
  manufacturer_part_number: string | null;
  material_name: string | null;
  material_class: MaterialClass | null;
  mass_nominal_g: string | null;
  approved_at: string | null;
}

export interface LibraryPartResponse {
  id: number;
  wardstone_part_number: string;
  revision: string;
  part_type: PartType;
  name: string;
  description: string | null;
  manufacturer_part_number: string | null;
  manufacturer_name: string | null;
  cage_code: string | null;
  nsn: string | null;
  drawing_number: string | null;
  drawing_revision: string | null;
  heritage: string | null;
  status: PartStatus;
  superseded_by_id: number | null;
  bounding_box_x_mm: string | null;
  bounding_box_y_mm: string | null;
  bounding_box_z_mm: string | null;
  volume_mm3: string | null;
  surface_area_mm2: string | null;
  thread_size: string | null;
  thread_standard: ThreadStandard | null;
  nominal_diameter_mm: string | null;
  nominal_length_mm: string | null;
  head_type: string | null;
  drive_type: string | null;
  hole_pattern_count: number | null;
  hole_pattern_dia_mm: string | null;
  hole_pattern_pcd_mm: string | null;
  material_name: string | null;
  material_standard: string | null;
  material_class: MaterialClass | null;
  density_g_cm3: string | null;
  yield_strength_mpa: string | null;
  ultimate_strength_mpa: string | null;
  elastic_modulus_gpa: string | null;
  hardness: string | null;
  thermal_conductivity_wm: string | null;
  cte_um_m_c: string | null;
  corrosion_protection: string | null;
  flammability_class: string | null;
  outgassing_tml_pct: string | null;
  outgassing_cvcm_pct: string | null;
  mass_nominal_g: string | null;
  mass_max_g: string | null;
  proof_load_n: string | null;
  clamp_load_n: string | null;
  torque_nominal_nm: string | null;
  torque_min_nm: string | null;
  torque_max_nm: string | null;
  torque_lubricated_nm: string | null;
  locking_feature: LockingFeature | null;
  safety_wire_holes: boolean | null;
  shear_strength_n: string | null;
  bearing_load_n: string | null;
  compression_set_pct: string | null;
  sealing_pressure_max_bar: string | null;
  temperature_min_c: string | null;
  temperature_max_c: string | null;
  unit_cost_usd: string | null;
  lead_time_weeks: number | null;
  min_order_qty: number | null;
  preferred_supplier_id: number | null;
  supplier_part_number: string | null;
  qualification_status: QualificationStatus | null;
  qualification_basis: string | null;
  shelf_life_months: number | null;
  date_of_manufacture: string | null;
  restricted_use: boolean;
  restriction_notes: string | null;
  step_file_id: number | null;
  step_file_checksum: string | null;
  approved_by_id: number | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
  created_by_id: number | null;
}

export interface LibraryPartCreate {
  part_type: PartType;
  name: string;
  description?: string;
  manufacturer_part_number?: string;
  manufacturer_name?: string;
  material_name?: string;
  material_class?: MaterialClass;
  thread_size?: string;
  thread_standard?: ThreadStandard;
  nominal_diameter_mm?: string;
  nominal_length_mm?: string;
  torque_nominal_nm?: string;
  mass_nominal_g?: string;
  locking_feature?: LockingFeature;
  unit_cost_usd?: string;
  lead_time_weeks?: number;
  qualification_status?: QualificationStatus;
}

// Path C / CADPORT-keyed project_parts carry a catalog summary
// instead of a library_part. Either side may be null depending on
// how the row was created (legacy fastener workflow → library_part;
// catalog/CADPORT import → catalog_part_summary).
export interface CatalogPartSummaryLite {
  id: number;
  part_number: string;
  name: string;
  part_class: string | null;
  lifecycle_status: string | null;
  revision: string | null;
  supplier_name: string | null;
  mass_kg: string | number | null;
}

export interface ProjectPartResponse {
  id: number;
  project_id: number;
  library_part_id: number | null;
  catalog_part_id?: number | null;
  quantity: number;
  designation: string | null;
  notes: string | null;
  added_at: string;
  library_part: LibraryPartSummary | null;
  catalog_part_summary?: CatalogPartSummaryLite | null;
  system_id: number | null;
}

export interface ProjectPartCreate {
  library_part_id: number;
  quantity?: number;
  designation?: string;
  notes?: string;
}

export interface MechanicalJointCreate {
  joint_type: JointType;
  part_a_id: number;
  part_b_id: number;
  fastener_part_id?: number;
  fastener_count?: number;
  torque_nominal_nm?: string;
  torque_min_nm?: string;
  torque_max_nm?: string;
  engagement_length_mm?: string;
  locking_feature?: LockingFeature;
  hole_pattern_description?: string;
  mating_surface_flatness_mm?: string;
  mating_surface_finish_ra?: string;
  seal_part_id?: number;
  leak_rate_max_scc_s?: string;
  test_pressure_bar?: string;
  interface_drawing?: string;
  notes?: string;
}

export interface MechanicalJointResponse {
  id: number;
  joint_id: string;
  project_id: number;
  joint_type: JointType;
  part_a_id: number;
  part_b_id: number;
  fastener_part_id: number | null;
  fastener_count: number | null;
  torque_nominal_nm: string | null;
  torque_min_nm: string | null;
  torque_max_nm: string | null;
  engagement_length_mm: string | null;
  locking_feature: LockingFeature | null;
  hole_pattern_description: string | null;
  mating_surface_flatness_mm: string | null;
  mating_surface_finish_ra: string | null;
  seal_part_id: number | null;
  leak_rate_max_scc_s: string | null;
  test_pressure_bar: string | null;
  interface_drawing: string | null;
  source_step_file_id: number | null;
  source_step_entity: string | null;
  confidence: ConfidenceLevel | null;
  status: JointStatus;
  notes: string | null;
  created_at: string;
  updated_at: string;
  created_by_id: number | null;
  fastener_part: LibraryPartSummary | null;
  seal_part: LibraryPartSummary | null;
}

export interface PendingPartsImportResponse {
  id: number;
  document_id: number;
  status: PendingPartsStatus;
  proposed_data: Record<string, unknown>;
  confidence_scores: Record<string, ConfidenceLevel>;
  low_confidence_fields: string[];
  extraction_log: string | null;
  parser_version: string | null;
  library_part_id: number | null;
  rejection_reason: string | null;
  created_at: string;
}

export interface AssemblyParseJobResponse {
  id: number;
  project_id: number;
  document_id: number | null;
  status: AssemblyParseJobStatus;
  progress_log: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string | null;
  completed_at: string | null;
}

// ── UI helper maps ─────────────────────────────────────────────

export const PART_TYPE_LABELS: Record<PartType, string> = {
  fastener: 'Fastener',
  washer: 'Washer',
  insert: 'Insert',
  bracket: 'Bracket',
  enclosure: 'Enclosure',
  seal: 'Seal',
  bearing: 'Bearing',
  hinge_latch: 'Hinge / Latch',
  thermal_interface: 'Thermal Interface',
  pcb_mechanical: 'PCB Mechanical',
  custom: 'Custom',
};

export const PART_TYPE_COLORS: Record<PartType, string> = {
  fastener: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-200',
  washer: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-200',
  insert: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-200',
  bracket: 'bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-200',
  enclosure: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-200',
  seal: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-200',
  bearing: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-200',
  hinge_latch: 'bg-pink-100 text-pink-800 dark:bg-pink-900/30 dark:text-pink-200',
  thermal_interface: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200',
  pcb_mechanical: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-200',
  custom: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-200',
};

export const PART_STATUS_COLORS: Record<PartStatus, string> = {
  draft: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-200',
  under_review: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-200',
  approved: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-200',
  superseded: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-200',
  obsolete: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200',
};

export const JOINT_TYPE_LABELS: Record<JointType, string> = {
  bolted: 'Bolted',
  riveted: 'Riveted',
  press_fit: 'Press Fit',
  adhesive: 'Adhesive',
  weld: 'Weld',
  seal: 'Seal',
  alignment_pin: 'Alignment Pin',
  thermal_bond: 'Thermal Bond',
  spring_clip: 'Spring Clip',
};

export const JOINT_STATUS_COLORS: Record<JointStatus, string> = {
  draft: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-200',
  active: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-200',
  superseded: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-200',
};
