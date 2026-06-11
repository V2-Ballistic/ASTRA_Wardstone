// ══════════════════════════════════════════════════════════════
//  ASTRA — Engineering domain types (Motors + Aero)
//
//  File: frontend/src/lib/engineering-types.ts
//  ASTRA_CONFIG_ECOSYSTEM_BUILD_SPEC §4/§5/§6 — Engineering UI area.
//
//  Field names mirror the backend as-built schemas EXACTLY:
//    backend/app/schemas/engineering_motor.py
//    backend/app/schemas/engineering_aero.py
//    backend/app/services/engineering/motor_artifact.py (artifact keys)
//    backend/app/services/engineering/aero_deck.py      (deck keys)
// ══════════════════════════════════════════════════════════════

// ──────────────────────────────────────────────
//  Motors — §5.3 design inputs (solver schema)
// ──────────────────────────────────────────────

/** Saint-Robert propellant: r = a · Pc^n (SI). */
export interface PropellantInputs {
  density_kgpm3: number;
  a: number;
  n: number;
  k: number;
  Tc_K?: number | null;
  cstar_mps?: number | null;
  sigma_p?: number;
  molar_mass_kgpmol?: number | null;
}

/** BATES grain stack — multi-segment is first-class. */
export interface GrainInputs {
  type: string; // 'BATES'
  od_m: number;
  core_d_m: number;
  length_m: number;
  segment_count: number;
  inhibited_ends: number; // 0 | 1 | 2
}

export interface NozzleInputs {
  throat_d_m: number;
  exit_d_m?: number | null;
  expansion_ratio?: number | null;
  ambient_pressure_pa?: number;
}

export interface SimInputs {
  web_step_m?: number;
  grain_temp_K?: number;
}

/** Complete solver input set. Backend is `extra="forbid"` — send
 *  ONLY these keys. */
export interface MotorDesignInputs {
  propellant: PropellantInputs;
  grain: GrainInputs;
  nozzle: NozzleInputs;
  sim?: SimInputs;
}

// ──────────────────────────────────────────────
//  Motors — responses
// ──────────────────────────────────────────────

export type QualityTier = 'excellent' | 'good' | 'workable';
export type MotorOrigin = 'design' | 'csv';

export interface MotorRevisionSummary {
  id: number;
  wpn: string;
  rev_letter: string;
  origin: MotorOrigin | string;
  total_impulse_ns?: number | null;
  peak_thrust_n?: number | null;
  burn_time_s?: number | null;
  isp_s?: number | null;
  quality_tier: string;
  artifact_sha256: string;
  created_utc?: string | null;
  notes?: string | null;
}

export interface MotorRevisionDetail extends MotorRevisionSummary {
  design_inputs?: MotorDesignInputs | null;
  source_csv_filename?: string | null;
  source_csv_sha256?: string | null;
  defaulted_fields?: string[] | null;
  warnings?: string[] | null;
}

export interface MotorListItem {
  id: number;
  wpn: string;
  name: string;
  motor_class?: string | null;
  total_impulse_ns?: number | null;
  quality_tier?: string | null;
  current_rev_letter?: string | null;
  updated_at?: string | null;
}

export interface MotorResponse {
  id: number;
  wpn: string;
  base_index: number;
  system_code: string;
  name: string;
  motor_class?: string | null;
  active_revision_id?: number | null;
  catalog_part_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  revisions: MotorRevisionSummary[];
}

export interface MotorSummarySheet {
  wpn: string;
  name: string;
  motor_class?: string | null;
  rev_letter?: string | null;
  origin?: string | null;
  quality_tier?: string | null;
  total_impulse_ns?: number | null;
  peak_thrust_n?: number | null;
  burn_time_s?: number | null;
  isp_s?: number | null;
  prop_mass_init_kg?: number | null;
  revision_count: number;
}

export interface MotorIngestResponse {
  motor: MotorResponse;
  wpn: string;
  rev_letter: string;
  quality_tier: string;
  recommended_fidelity: string;
  warnings: string[];
  defaulted_fields: string[];
  precheck?: Record<string, unknown> | null;
}

export interface DesignPreviewResponse {
  time_s: number[];
  thrust_n: number[];
  pchamber_pa: number[];
  mdot_kgps: number[];
  prop_mass_rem_kg: number[];
  total_impulse_ns: number;
  peak_thrust_n: number;
  burn_time_s: number;
  isp_s: number;
  prop_mass_init_kg: number;
  motor_class: string;
  max_pchamber_pa: number;
  warnings: string[];
}

/** The §5.4 normalized `*.motor.json` artifact — keys verbatim from
 *  motor_artifact.build_artifact(). */
export interface MotorArtifact {
  schema: string;
  MotorTime_s: number[];
  Thrust_N: number[];
  Mdot_kgps: number[];
  PropMassRem_kg: number[];
  PropMassInit_kg: number;
  Pchamber_Pa: number[];
  PropCGOffset_m_B: number[];
  PropInertiaAxial_kgm2: number[];
  PropInertiaTransverse_kgm2: number[];
  GrainStackLength_m: number;
  BurnTime_s: number;
  Ts_s: number;
  AreaExit_m2: number;
  AreaThroat_m2: number;
  GrainTempGrid_K: number[]; // [cold, nominal, hot]
  Thrust_N_byTgrain: number[][]; // 3 rows
  Mdot_kgps_byTgrain: number[][]; // 3 rows
  TotalImpulse_Ns: number;
  PeakThrust_N: number;
  Isp_s: number;
  qualityTier: string;
  defaultedFields: string[];
  provenance: {
    origin: MotorOrigin | string;
    author?: string;
    createdUtc?: string;
    wpn?: string;
    csvSha256?: string;
    designInputs?: MotorDesignInputs;
  };
}

// ──────────────────────────────────────────────
//  Aero — responses
// ──────────────────────────────────────────────

export interface AeroEnvelope {
  mach_min?: number | null;
  mach_max?: number | null;
  alpha_min_deg?: number | null;
  alpha_max_deg?: number | null;
}

export interface AeroDeckRevisionSummary {
  id: number;
  wpn: string;
  rev_letter: string;
  deck_sha256: string;
  source_filenames: string[];
  mach_min?: number | null;
  mach_max?: number | null;
  alpha_min_deg?: number | null;
  alpha_max_deg?: number | null;
  sref_m2?: number | null;
  lref_m?: number | null;
  warnings: string[];
  defaulted_fields: string[];
  notes?: string | null;
  created_utc?: string | null;
}

export interface AeroDeckRevisionDetail extends AeroDeckRevisionSummary {
  source_sha256s: string[];
  deck: AeroDeckArtifact;
}

export interface AeroDeckSummary {
  id: number;
  wpn: string;
  name: string;
  oml_wpn?: string | null;
  system_code: string;
  current_rev?: string | null;
  revision_count: number;
  mach_min?: number | null;
  mach_max?: number | null;
  alpha_min_deg?: number | null;
  alpha_max_deg?: number | null;
  updated_at?: string | null;
}

export interface AeroDeckDetail extends AeroDeckSummary {
  base_index?: number | null;
  created_at?: string | null;
  revisions: AeroDeckRevisionSummary[];
}

export interface AeroIngestResponse {
  deck_id: number;
  deck_wpn: string;
  wpn: string; // FULL HAROLD-issued WPN of the created revision
  rev_letter: string;
  name: string;
  deck_sha256: string;
  is_new_deck: boolean;
  envelope: AeroEnvelope;
  warnings: string[];
  defaulted_fields: string[];
}

export interface AeroPreviewResponse {
  wpn: string;
  rev_letter: string;
  mach: number;
  alpha_deg: number;
  beta_deg: number;
  delta_deg: number;
  values: Record<string, number>;
}

/** The normalized `*.aero.json` deck — keys verbatim from
 *  aero_deck.merge_decks(). Tables are nested mach × alpha × beta ×
 *  delta lists. */
export interface AeroDeckArtifact {
  schema: string;
  omlWpn?: string | null;
  Sref_m2: number;
  Lref_m: number;
  refPoint_m_B: number[];
  frame: string;
  axes: string[];
  breakpoints: {
    mach: number[];
    alpha_deg: number[];
    beta_deg: number[];
    delta_deg: number[];
  };
  tables: Record<string, number[][][][]>;
  derived: {
    CNalpha_per_deg?: (number | null)[];
    Cmalpha_per_deg?: (number | null)[];
    alpha_ref_deg?: number;
    staticMargin_proxy?: (number | null)[];
    [k: string]: unknown;
  };
  validityEnvelope: {
    machRange: number[];
    alphaRange_deg: number[];
    betaRange_deg: number[];
  };
  units: Record<string, string>;
  provenance: {
    sourceFiles: { filename: string; sha256: string }[];
    ingestUtc?: string | null;
    author?: string | null;
    wpn?: string | null;
  };
  extensions?: Record<string, unknown> | null;
}

// ──────────────────────────────────────────────
//  Display helpers (shared by tabs / detail pages)
// ──────────────────────────────────────────────

/** Quality tier pill colors — excellent=emerald, good=blue,
 *  workable=amber (spec §5 UX). */
export const TIER_COLORS: Record<string, { bg: string; text: string; label: string }> = {
  excellent: { bg: 'rgba(16,185,129,0.15)', text: '#34D399', label: 'Excellent' },
  good:      { bg: 'rgba(59,130,246,0.15)', text: '#60A5FA', label: 'Good' },
  workable:  { bg: 'rgba(245,158,11,0.15)', text: '#FBBF24', label: 'Workable' },
};

/** Total impulse: N·s below 1 kN·s, kN·s above (spec §5 list UX). */
export function fmtImpulse(ns?: number | null): string {
  if (ns === null || ns === undefined || Number.isNaN(ns)) return '—';
  if (Math.abs(ns) >= 1000) {
    const kns = ns / 1000;
    return `${kns >= 100 ? kns.toFixed(0) : kns.toFixed(1)} kN·s`;
  }
  return `${ns >= 100 ? ns.toFixed(0) : ns.toFixed(1)} N·s`;
}

export function fmtThrust(n?: number | null): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  if (Math.abs(n) >= 10000) return `${(n / 1000).toFixed(1)} kN`;
  return `${n >= 100 ? n.toFixed(0) : n.toFixed(1)} N`;
}

export function fmtSeconds(s?: number | null): string {
  if (s === null || s === undefined || Number.isNaN(s)) return '—';
  return `${s.toFixed(2)} s`;
}

export function fmtKg(kg?: number | null): string {
  if (kg === null || kg === undefined || Number.isNaN(kg)) return '—';
  return `${kg >= 100 ? kg.toFixed(1) : kg.toFixed(3)} kg`;
}

export function fmtMPa(pa?: number | null): string {
  if (pa === null || pa === undefined || Number.isNaN(pa)) return '—';
  return `${(pa / 1e6).toFixed(2)} MPa`;
}

/** Envelope range, e.g. "0.3–2.0". */
export function fmtRange(
  min?: number | null,
  max?: number | null,
  digits = 1,
  unit = '',
): string {
  if (min === null || min === undefined || max === null || max === undefined) return '—';
  return `${min.toFixed(digits)}–${max.toFixed(digits)}${unit}`;
}

export function fmtDateTime(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString();
}
