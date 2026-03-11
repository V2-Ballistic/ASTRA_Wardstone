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

// ── Enums ──

export type RequirementType =
  | 'functional' | 'performance' | 'interface' | 'environmental'
  | 'constraint' | 'safety' | 'security' | 'reliability'
  | 'maintainability' | 'derived';

export type Priority = 'critical' | 'high' | 'medium' | 'low';

export type RequirementLevel = 'L1' | 'L2' | 'L3' | 'L4' | 'L5';

export type RequirementStatus =
  | 'draft' | 'under_review' | 'approved' | 'baselined'
  | 'implemented' | 'verified' | 'validated' | 'deferred' | 'deleted';

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
};

export const TYPE_PREFIXES: Record<RequirementType, string> = {
  functional: 'FR', performance: 'PR', interface: 'IR',
  environmental: 'ER', constraint: 'CR', safety: 'SAF',
  security: 'SR', reliability: 'RL', maintainability: 'MR',
  derived: 'DR',
};

export const LEVEL_LABELS: Record<RequirementLevel, string> = {
  L1: 'L1 — System',
  L2: 'L2 — Subsystem',
  L3: 'L3 — Component',
  L4: 'L4 — Sub-component',
  L5: 'L5 — Detail',
};

export const LEVEL_COLORS: Record<RequirementLevel, string> = {
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
