// ══════════════════════════════════════════════════════════════
//  ASTRA — System Architecture TypeScript Types
//
//  File: frontend/src/lib/sysarch-types.ts
//  TDD-SYSARCH-002 Phase 3 — mirrors the backend response models in
//  app/routers/system_architecture.py and the new
//  UnitCatalogPartSummary embedded on UnitResponse.
// ══════════════════════════════════════════════════════════════

export interface SystemArchGraphNode {
  id: number;
  type: 'system' | 'unit';
  label: string;
  parent_id?: number;
  badge?: string;
  status?: string;
  color_hint?: string;
  catalog_part_id?: number;
  catalog_part_wpn?: string;
}

export interface SystemArchGraphEdge {
  source: number;
  target: number;
  source_type: 'system' | 'unit';
  target_type: 'system' | 'unit';
  edge_type: 'contains' | 'parent_of' | 'connects_to';
  label?: string;
  color_hint?: string;
}

export interface SystemArchGraphResponse {
  systems: SystemArchGraphNode[];
  units: SystemArchGraphNode[];
  edges: SystemArchGraphEdge[];
}

// ── Embedded Unit ↔ CatalogPart summary (Phase 2 extension) ──

export interface UnitCatalogPartSummary {
  id: number;
  part_number: string;
  name: string;
  part_class: string;
  part_subtype?: string | null;
  mass_kg?: number | null;
  cad_step_path?: string | null;
  cad_preview_path?: string | null;
  supplier_name?: string | null;
  supplier_is_in_house?: boolean | null;
}
