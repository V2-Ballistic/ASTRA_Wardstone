// ════════════════════════════════════════════════════════════════
//  ASTRA — Project Parts (BOM) TypeScript types
//  Mirrors backend Pydantic schemas in app/schemas/parts_library.py
//  for the Path C BOM surface introduced by TDD-PROJPARTS-001.
//
//  File: frontend/src/lib/projparts-types.ts
// ════════════════════════════════════════════════════════════════
//
// Distinction from `parts-types.ts`
// ---------------------------------
// The legacy `ProjectPartResponse` in parts-types.ts assumed a
// non-null `library_part` (the fastener/mechanical-joint flow). Path
// C lets a BOM line reference *either* a library_part (legacy) or a
// catalog_part (canonical) or both, so the BOM-side types here keep
// both nullable. The mechanical-interfaces page continues to use the
// legacy shape — don't mix them.
//
// Wire shape note
// ---------------
// `quantity` and `catalog_part_summary.mass_kg` arrive as JSON
// strings (Pydantic v2 default Decimal serialization, e.g. "8.0000").
// Convert with `Number(quantity)` or `parseFloat` at the render site.

import type { PartClass, LifecycleStatus } from './catalog-types';

// ── Enums ──────────────────────────────────────────────────────

export type BomStatus =
  | 'planned'
  | 'released'
  | 'procured'
  | 'received'
  | 'installed'
  | 'verified'
  | 'obsolete';

export const BOM_STATUS_VALUES: BomStatus[] = [
  'planned', 'released', 'procured', 'received',
  'installed', 'verified', 'obsolete',
];

// ── Nested summaries ───────────────────────────────────────────

export interface ProjectPartCatalogSummary {
  id: number;
  part_number: string;
  name: string;
  part_class: PartClass;
  lifecycle_status: LifecycleStatus;
  revision: string | null;
  supplier_name: string | null;
  mass_kg: string | null;
}

export interface ProjectPartUnitSummary {
  id: number;
  unit_id: string;
  name: string;
  designation: string;
  system_id: number;
}

// Slim LibraryPartSummary (BOM page only uses these few fields).
export interface ProjectPartLibrarySummary {
  id: number;
  wardstone_part_number: string;
  name: string;
  part_type: string;
}

// ── Row payload (full response from POST/PATCH/list) ───────────

export interface ProjectPartBom {
  id: number;
  project_id: number;
  library_part_id: number | null;
  catalog_part_id: number | null;
  quantity: string;           // Decimal → JSON string
  quantity_unit: string;
  designation: string | null;
  bom_position: string | null;
  parent_bom_id: number | null;
  status: BomStatus;
  unit_id: number | null;
  location_zone: string | null;
  installation_notes: string | null;
  procurement_notes: string | null;
  notes: string | null;
  added_at: string;
  updated_at: string | null;

  library_part: ProjectPartLibrarySummary | null;
  catalog_part_summary: ProjectPartCatalogSummary | null;
  linked_unit: ProjectPartUnitSummary | null;
  parent_designation: string | null;

  // Resolved from SystemPartAssignment when present.
  system_id: number | null;
}

// ── Create / Update payloads ───────────────────────────────────

export interface ProjectPartBomCreate {
  // At least one of library_part_id / catalog_part_id is required
  // (enforced server-side; the picker UI always supplies catalog).
  library_part_id?: number;
  catalog_part_id?: number;
  quantity?: number | string;
  quantity_unit?: string;
  designation?: string;
  bom_position?: string;
  parent_bom_id?: number;
  status?: BomStatus;
  unit_id?: number;
  location_zone?: string;
  installation_notes?: string;
  procurement_notes?: string;
  notes?: string;
}

export interface ProjectPartBomUpdate {
  catalog_part_id?: number;
  quantity?: number | string;
  quantity_unit?: string;
  designation?: string | null;
  bom_position?: string | null;
  parent_bom_id?: number | null;
  status?: BomStatus;
  unit_id?: number | null;
  location_zone?: string | null;
  installation_notes?: string | null;
  procurement_notes?: string | null;
  notes?: string | null;
}

// ── Stats (BOM dashboard stat strip) ──────────────────────────

export interface BomStats {
  total: number;
  by_status: Partial<Record<BomStatus, number>>;
  by_part_class: Partial<Record<PartClass, number>>;
}

// ── Filter shape for list() ────────────────────────────────────

export interface ProjectPartBomListParams {
  part_class?: PartClass;
  status?: BomStatus;
  parent_bom_id?: number;
  search?: string;
  limit?: number;
  offset?: number;
}

// ── UI helper maps ─────────────────────────────────────────────

export const BOM_STATUS_LABELS: Record<BomStatus, string> = {
  planned:   'Planned',
  released:  'Released',
  procured:  'Procured',
  received:  'Received',
  installed: 'Installed',
  verified:  'Verified',
  obsolete:  'Obsolete',
};

export const BOM_STATUS_COLORS: Record<BomStatus, string> = {
  planned:   'bg-slate-700/40 text-slate-200 border-slate-500/30',
  released:  'bg-sky-700/30   text-sky-200    border-sky-500/30',
  procured:  'bg-indigo-700/30 text-indigo-200 border-indigo-500/30',
  received:  'bg-amber-700/30  text-amber-200  border-amber-500/30',
  installed: 'bg-emerald-700/30 text-emerald-200 border-emerald-500/30',
  verified:  'bg-green-700/30  text-green-200   border-green-500/30',
  obsolete:  'bg-red-700/30    text-red-200     border-red-500/30',
};

/**
 * The BOM page's `part_class` chip filter is a curated subset of the
 * full catalog PartClass — every catalog class is selectable but they
 * are grouped so chips don't sprawl. Consumers can iterate this list
 * to render the filter row in a stable order.
 */
export const BOM_FILTER_CLASSES: PartClass[] = [
  'processor', 'compute_module', 'sensor', 'radio', 'antenna',
  'power_supply', 'power_distribution', 'interface_card', 'display',
  'actuator', 'harness', 'connector_only',
  'fastener_screw', 'fastener_bolt', 'nut', 'washer',
  'bracket', 'housing', 'enclosure', 'seal_o_ring',
  'bearing', 'spring', 'structural_member',
  'mechanical_other', 'other',
];
