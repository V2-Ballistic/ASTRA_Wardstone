// ══════════════════════════════════════════════════════════════
//  ASTRA — Reactive Requirement Sync — TypeScript types
//  Mirror of backend/app/schemas/req_sync.py + the Phase-5
//  endpoint payloads in backend/app/routers/req_sync.py.
//
//  File: frontend/src/lib/req-sync-types.ts
//  Phase 5 — ASTRA-TDD-INTF-002
// ══════════════════════════════════════════════════════════════

export type SourceEntityType =
  | 'system'
  | 'unit'
  | 'connector'
  | 'pin'
  | 'interface'
  | 'wire_harness'
  | 'wire'
  | 'bus_definition'
  | 'message_definition'
  | 'message_field'
  | 'unit_env_spec'
  | 'catalog_part'
  | 'requirement';

export type SyncProposalStatus =
  | 'pending'
  | 'accepted'
  | 'rejected'
  | 'auto_applied'
  | 'superseded';

export type SyncProposalType =
  | 'update_statement'
  | 'obsolete'
  | 'regenerate';

export interface FieldDiff {
  old: string | null;
  new: string | null;
}

export interface RequirementSyncProposal {
  id: number;
  requirement_id: number;
  triggered_by_entity_type: SourceEntityType;
  triggered_by_entity_id: number;
  trigger_event: string;
  old_statement: string;
  new_statement: string | null;
  old_rationale: string | null;
  new_rationale: string | null;
  field_diffs: Record<string, FieldDiff>;
  proposal_type: SyncProposalType;
  status: SyncProposalStatus;
  auto_applied: boolean;
  created_at: string;
  reviewed_at: string | null;
  reviewed_by_id: number | null;
  reviewer_notes: string | null;
}

export interface RequirementSyncProposalDetail extends RequirementSyncProposal {
  requirement_req_id: string | null;
  requirement_title: string | null;
  requirement_status: string | null;
  requirement_level: string | null;
  project_id: number | null;
}

export interface SyncProposalListResponse {
  total: number;
  items: RequirementSyncProposal[];
}

export interface RequirementSourceLink {
  id: number;
  requirement_id: number;
  source_entity_type: SourceEntityType;
  source_entity_id: number;
  template_id: string;
  template_inputs: Record<string, unknown>;
  role: string;
  last_synced_at: string;
}

export interface SourceLinksResponse {
  requirement_id: number;
  items: RequirementSourceLink[];
}

export interface BulkAcceptRequest {
  proposal_ids: number[];
  reviewer_notes?: string;
}

export interface BulkProposalActionResult {
  proposal_id: number;
  success: boolean;
  error?: string | null;
}

export interface BulkProposalActionResponse {
  total: number;
  succeeded: number;
  failed: number;
  results: BulkProposalActionResult[];
}

export interface RequirementSyncLockRequest {
  reason?: string;
}

export interface RequirementSyncLockResponse {
  requirement_id: number;
  sync_locked: boolean;
  sync_locked_by_id?: number | null;
  sync_locked_at?: string | null;
  sync_locked_reason?: string | null;
}
