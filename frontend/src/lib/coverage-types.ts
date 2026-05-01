// ══════════════════════════════════════════════════════════════
//  ASTRA — Source Coverage — TypeScript types
//  Mirror of backend/app/schemas/coverage.py.
//
//  File: frontend/src/lib/coverage-types.ts
//  Phase 6 — ASTRA-TDD-INTF-002
// ══════════════════════════════════════════════════════════════

import type { SourceEntityType } from './req-sync-types';

export type CoverageSeverity = 'ok' | 'warning' | 'error';

export type RequirementLevel = 'L1' | 'L2' | 'L3' | 'L4' | 'L5';

export interface LevelSeveritySummary {
  total: number;
  ok: number;
  warning: number;
  error: number;
}

export interface CoverageReportResponse {
  project_id: number;
  summary: Record<string, LevelSeveritySummary>;
  computed_at: string;
  used_materialized_view: boolean;
  exception_count: number;
}

export interface OrphanRequirementResponse {
  requirement_id: number;
  req_text: string;
  title: string;
  level: RequirementLevel | string;
  severity: CoverageSeverity;
  parent_id: number | null;
  parent_traced: boolean;
  suggested_source_type: SourceEntityType | null;
  has_active_exception: boolean;
}

export interface OrphanListResponse {
  project_id: number;
  total: number;
  items: OrphanRequirementResponse[];
}

export interface CoverageException {
  id: number;
  project_id: number;
  requirement_id: number;
  reason: string;
  is_active: boolean;
  expires_at: string | null;
  created_at: string;
  created_by_id: number;
  approved_by_id: number | null;
  approved_at: string | null;
}

export interface CoverageExceptionListResponse {
  total: number;
  items: CoverageException[];
}

export interface CoverageExceptionCreate {
  project_id: number;
  requirement_id: number;
  reason: string;
  expires_at?: string | null;
}

export interface CosignRequest {
  notes?: string | null;
}
