/**
 * ASTRA — Impact Analysis API Client
 * =====================================
 * File: frontend/src/lib/impact-api.ts   ← NEW
 *
 * TypeScript types + API calls for impact analysis, dependency
 * chains, what-if previews, and impact report history.
 */

import api from './api';

// ── Types ──

export interface ImpactItem {
  entity_type: string;
  entity_id: number;
  entity_identifier: string;
  entity_title: string;
  impact_level: 'direct' | 'indirect';
  hop_count: number;
  relationship_path: string[];
  link_types_involved: string[];
  current_status: string;
  ai_explanation: string;
}

export interface AffectedVerification {
  verification_id: number;
  requirement_id: number;
  requirement_identifier: string;
  method: string;
  current_status: string;
  needs_rerun: boolean;
  reason: string;
}

export interface AffectedBaseline {
  baseline_id: number;
  baseline_name: string;
  created_at?: string;
  requirements_count: number;
  reason: string;
}

export interface ImpactReport {
  changed_requirement: Record<string, any>;
  change_description: string;
  direct_impacts: ImpactItem[];
  indirect_impacts: ImpactItem[];
  affected_verifications: AffectedVerification[];
  affected_baselines: AffectedBaseline[];
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  risk_factors: string[];
  ai_summary: string;
  ai_available: boolean;
  dependency_depth: number;
  total_affected: number;
  total_direct: number;
  total_indirect: number;
  analyzed_at?: string;
  analysis_duration_ms: number;
}

export interface DependencyNode {
  entity_type: string;
  entity_id: number;
  identifier: string;
  title: string;
  status: string;
  level: string;
  hop_count: number;
  link_type: string;
  link_direction: string;
  children: DependencyNode[];
}

export interface DependencyTree {
  root_requirement: Record<string, any>;
  upstream: DependencyNode[];
  downstream: DependencyNode[];
  total_upstream: number;
  total_downstream: number;
  max_depth_up: number;
  max_depth_down: number;
}

export interface WhatIfPreview {
  requirement_id: number;
  requirement_identifier: string;
  action: 'delete' | 'modify';
  total_affected: number;
  direct_count: number;
  indirect_count: number;
  orphaned_count: number;
  verification_rerun_count: number;
  baseline_impact_count: number;
  affected_items: ImpactItem[];
  orphaned_requirements: Record<string, any>[];
  verifications_affected: AffectedVerification[];
  baselines_affected: AffectedBaseline[];
  risk_level: string;
  ai_summary: string;
  ai_available: boolean;
  requires_change_request: boolean;
  recommendation: string;
}

export interface StoredImpactReport {
  id: number;
  requirement_id: number;
  requirement_identifier: string;
  change_description: string;
  report_json: Record<string, any>;
  risk_level: string;
  total_affected: number;
  created_by_id?: number;
  created_at?: string;
}

// ── API Calls ──

export const impactAPI = {
  /** Run full impact analysis */
  analyze: (requirementId: number, changeDescription?: string) =>
    api.get<ImpactReport>('/impact/analyze', {
      params: {
        requirement_id: requirementId,
        change_description: changeDescription || '',
      },
    }),

  /** Get dependency chain for visualization */
  getDependencies: (requirementId: number, direction?: string) =>
    api.get<DependencyTree>('/impact/dependencies', {
      params: {
        requirement_id: requirementId,
        direction: direction || 'both',
      },
    }),

  /** Preview impact before performing action */
  whatIf: (requirementId: number, action: 'delete' | 'modify') =>
    api.get<WhatIfPreview>('/impact/what-if', {
      params: { requirement_id: requirementId, action },
    }),

  /** Get past impact reports */
  getHistory: (requirementId: number, limit?: number) =>
    api.get<StoredImpactReport[]>('/impact/history', {
      params: { requirement_id: requirementId, limit: limit || 10 },
    }),

  /** Project-level risk overview */
  getProjectRisk: (projectId: number) =>
    api.get('/impact/project-risk', {
      params: { project_id: projectId },
    }),
};
