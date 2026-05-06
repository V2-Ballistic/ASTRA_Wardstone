// ══════════════════════════════════════
//  ASTRA — Shared TypeScript Types
//  Mirrors backend Pydantic schemas
// ══════════════════════════════════════

export interface User {
  id: number;
  username: string;
  email: string;
  full_name: string;
  role: string;
  department?: string;
  is_active: boolean;
  created_at: string;
}

export interface Project {
  id: number;
  code: string;
  name: string;
  description?: string;
  owner_id: number;
  status: string;
  created_at: string;
}

export interface Requirement {
  id: number;
  req_id: string;
  title: string;
  statement: string;
  rationale?: string;
  req_type: RequirementType;
  priority: Priority;
  status: RequirementStatus;
  level: RequirementLevel;
  version: number;
  quality_score: number;
  project_id: number;
  parent_id?: number;
  owner_id: number;
  source_artifact_id?: number;
  created_at: string;
  updated_at: string;
}

export interface RequirementDetail extends Requirement {
  owner?: User;
  children: Requirement[];
  trace_count: number;
  verification_status?: string;
}

export interface SourceArtifact {
  id: number;
  artifact_id: string;
  title: string;
  artifact_type: ArtifactType;
  description?: string;
  file_path?: string;
  source_date?: string;
  participants: string[];
  project_id: number;
  created_at: string;
}

export interface TraceLink {
  id: number;
  source_type: string;
  source_id: number;
  target_type: string;
  target_id: number;
  link_type: TraceLinkType;
  description?: string;
  status: string;
  created_at: string;
}

export interface Verification {
  id: number;
  requirement_id: number;
  method: VerificationMethod;
  status: VerificationStatus;
  responsible_id?: number;
  evidence?: string;
  criteria?: string;
  completed_at?: string;
  created_at: string;
}

export interface QualityCheckResult {
  score: number;
  passed: boolean;
  warnings: string[];
  suggestions: string[];
}

// ── F-092: typed dashboard / coverage / baseline / audit responses ──
//
// These mirror the shapes the backend returns for the listed
// endpoints. Pre-fix the corresponding pages used `useState<any>(null)`
// and bled un-validated `res.data` into JSX. With these types in
// place TS catches contract drift between backend and frontend at
// compile time.

export interface DashboardStats {
  total_requirements: number;
  by_status: Record<string, number>;
  by_type: Record<string, number>;
  by_level: Record<string, number>;
  verified_count: number;
  avg_quality_score: number;
  total_trace_links: number;
  orphan_count: number;
  recent_activity: Array<{
    req_id: string;
    field: string;
    old_value: string | null;
    new_value: string | null;
    description: string;
    user: string;
    timestamp: string | null;
  }>;
}

export interface CoverageReport {
  // The router computes the same coverage three different ways for
  // backward compatibility with consumers (landing page, traceability
  // page, sidebar). All fields below are part of the documented
  // payload — see backend/app/routers/projects.py::get_coverage.
  total_requirements: number;
  total?: number;                // alias used by traceability page
  with_source: number;
  with_source_pct: number;
  with_children: number;
  with_children_pct: number;
  with_verification: number;
  with_verification_pct: number;
  orphans: number;
  orphan_pct: number;
  // Legacy keys consumed by projects/[id]/page.tsx:
  forward_coverage: number;      // == with_source_pct
  backward_coverage: number;     // == with_children_pct
  verification_coverage: number; // == with_verification_pct
}

export interface BaselineDetail {
  id: number;
  name: string;
  description: string;
  project_id: number;
  requirements_count: number;
  created_by: string;
  created_at: string | null;
  // The detail-fetch payload bundles the snapshot rows alongside the
  // header. Modeled loosely (Record<string, unknown>) because the
  // snapshot row schema mixes typed fields and free-form columns;
  // tightening it further is a follow-up.
  requirements?: Array<Record<string, unknown>>;
}

export interface BaselineCompareResult {
  baseline_a?: BaselineDetail;
  baseline_b?: BaselineDetail;
  added?: Array<Record<string, unknown>>;
  removed?: Array<Record<string, unknown>>;
  modified?: Array<Record<string, unknown>>;
  // The compare endpoint returns a free-form `summary` block too;
  // typed loosely until the response shape is locked down.
  summary?: Record<string, unknown>;
}

export interface AuditChainVerifyResult {
  is_valid: boolean;
  verified_count?: number;
  total_records?: number;
  error?: string;
  // Server returns the offending record as `first_invalid: { sequence_number, reason }`
  // (or null when the chain is valid). Modeled loosely so the page can
  // read `.first_invalid?.sequence_number` without ceremony.
  first_invalid?: { sequence_number?: number; reason?: string } | null;
}

// ── Enums ──

export type RequirementType =
  | 'functional' | 'performance' | 'interface' | 'environmental'
  | 'constraint' | 'safety' | 'security' | 'reliability'
  | 'maintainability' | 'derived';

export type Priority = 'critical' | 'high' | 'medium' | 'low';

export type RequirementLevel = 'L0' | 'L1' | 'L2' | 'L3' | 'L4' | 'L5';

export type RequirementStatus =
  | 'draft' | 'under_review' | 'approved' | 'baselined'
  | 'implemented' | 'verified' | 'validated' | 'deferred' | 'deleted'
  // Backend has two more values that the FE filters off this view:
  | 'pending_review' | 'auto_generated';

export type ArtifactType =
  | 'interview' | 'meeting' | 'decision' | 'standard'
  | 'legacy' | 'email' | 'multimedia' | 'document';

export type TraceLinkType =
  | 'satisfaction' | 'evolution' | 'dependency'
  | 'rationale' | 'contribution' | 'verification' | 'decomposition';

export type VerificationMethod = 'test' | 'analysis' | 'inspection' | 'demonstration';
export type VerificationStatus = 'planned' | 'in_progress' | 'pass' | 'fail';

// ── UI Constants ──

export const STATUS_LABELS: Record<RequirementStatus, string> = {
  draft: 'Draft',
  under_review: 'Under Review',
  approved: 'Approved',
  baselined: 'Baselined',
  implemented: 'Implemented',
  verified: 'Verified',
  validated: 'Validated',
  deferred: 'Deferred',
  deleted: 'Deleted',
  pending_review: 'Pending Review',
  auto_generated: 'Auto-generated',
};

export const STATUS_COLORS: Record<RequirementStatus, { bg: string; text: string }> = {
  draft: { bg: 'rgba(245,158,11,0.15)', text: '#F59E0B' },
  under_review: { bg: 'rgba(139,92,246,0.15)', text: '#A78BFA' },
  approved: { bg: 'rgba(59,130,246,0.12)', text: '#3B82F6' },
  baselined: { bg: 'rgba(16,185,129,0.15)', text: '#10B981' },
  implemented: { bg: 'rgba(6,182,212,0.15)', text: '#22D3EE' },
  verified: { bg: 'rgba(16,185,129,0.15)', text: '#10B981' },
  validated: { bg: 'rgba(16,185,129,0.25)', text: '#34D399' },
  deferred: { bg: 'rgba(239,68,68,0.15)', text: '#EF4444' },
  deleted: { bg: 'rgba(100,116,139,0.15)', text: '#64748B' },
  pending_review: { bg: 'rgba(139,92,246,0.10)', text: '#A78BFA' },
  auto_generated: { bg: 'rgba(168,85,247,0.10)', text: '#A855F7' },
};

export const TYPE_PREFIXES: Record<RequirementType, string> = {
  functional: 'FR', performance: 'PR', interface: 'IR',
  environmental: 'ER', constraint: 'CR', safety: 'SAF',
  security: 'SR', reliability: 'RL', maintainability: 'MR',
  derived: 'DR',
};

export const LEVEL_LABELS: Record<RequirementLevel, string> = {
  L0: 'L0 — Customer / Contractual',
  L1: 'L1 — System',
  L2: 'L2 — Subsystem',
  L3: 'L3 — Component',
  L4: 'L4 — Sub-component',
  L5: 'L5 — Detail',
};

export const LEVEL_COLORS: Record<RequirementLevel, string> = {
  L0: '#DC2626',
  L1: '#EF4444',
  L2: '#F59E0B',
  L3: '#3B82F6',
  L4: '#8B5CF6',
  L5: '#6B7280',
};

export const PRIORITY_COLORS: Record<Priority, string> = {
  critical: '#EF4444',
  high: '#F59E0B',
  medium: '#3B82F6',
  low: '#6B7280',
};

// ── Source artifact display constants (ASTRA-TDD-ARTIFACTS-001) ──

export const ARTIFACT_TYPE_LABELS: Record<ArtifactType, string> = {
  document: 'Document (MRD, SOW, Spec)',
  standard: 'Standard / Specification',
  interview: 'Interview / Meeting Notes',
  meeting: 'Meeting Minutes',
  decision: 'Decision Record',
  legacy: 'Legacy System Reference',
  email: 'Email Correspondence',
  multimedia: 'Multimedia / Recording',
};

export const ARTIFACT_TYPE_ICONS: Record<ArtifactType, string> = {
  document: '📄',
  standard: '📐',
  interview: '🎤',
  meeting: '👥',
  decision: '✅',
  legacy: '🗃️',
  email: '📧',
  multimedia: '🎬',
};

export const ARTIFACT_TYPE_COLORS: Record<ArtifactType, string> = {
  document: '#3B82F6',
  standard: '#8B5CF6',
  interview: '#10B981',
  meeting: '#06B6D4',
  decision: '#F59E0B',
  legacy: '#6B7280',
  email: '#EC4899',
  multimedia: '#EF4444',
};

export interface SourceArtifactWithStats extends SourceArtifact {
  l0_requirement_count: number;
  total_requirement_count: number;
}
