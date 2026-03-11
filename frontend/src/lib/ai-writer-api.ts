/**
 * ASTRA — AI Writing Assistant API Client
 * ==========================================
 * File: frontend/src/lib/ai-writer-api.ts   ← NEW
 * Path: C:\Users\Mason\Documents\ASTRA\frontend\src\lib\ai-writer-api.ts
 */

import api from './api';

// ── Types ──

export interface GeneratedRequirement {
  title: string;
  statement: string;
  rationale: string;
  req_type: string;
  priority: string;
  level: string;
  confidence: number;
  source_fragment: string;
  notes: string;
}

export interface ProseConvertResponse {
  requirements: GeneratedRequirement[];
  total_extracted: number;
  source_type: string;
  ai_available: boolean;
  model_used: string;
  warnings: string[];
}

export interface RewriteSuggestion {
  rewritten_statement: string;
  changes_made: string[];
  quality_delta: string;
  explanation: string;
}

export interface ImproveResponse {
  original_statement: string;
  suggestions: RewriteSuggestion[];
  ai_available: boolean;
  model_used: string;
}

export interface DecomposeResponse {
  parent_statement: string;
  parent_level: string;
  target_level: string;
  sub_requirements: GeneratedRequirement[];
  decomposition_rationale: string;
  ai_available: boolean;
  model_used: string;
}

export interface VerificationStep {
  step_number: number;
  action: string;
  expected_result: string;
  pass_criteria: string;
}

export interface VerificationCriteria {
  requirement_statement: string;
  method: string;
  method_justification: string;
  preconditions: string[];
  steps: VerificationStep[];
  pass_fail_criteria: string;
  data_to_record: string[];
  estimated_duration: string;
  required_resources: string[];
  ai_available: boolean;
  model_used: string;
}

export interface GenerateRationaleResponse {
  rationale: string;
  alternatives_considered: string[];
  ai_available: boolean;
  model_used: string;
}

export interface SummarizeChangesResponse {
  summary: string;
  key_impacts: string[];
  recommendation: string;
  ai_available: boolean;
  model_used: string;
}

// ── API Calls ──

export const aiWriterAPI = {
  /** Convert free-form prose to structured requirements */
  convertProse: (prose: string, opts?: {
    project_context?: string; target_level?: string; domain_hint?: string;
  }) =>
    api.post<ProseConvertResponse>('/ai/writer/convert-prose', {
      prose,
      project_context: opts?.project_context || '',
      target_level: opts?.target_level || 'L1',
      domain_hint: opts?.domain_hint || '',
    }),

  /** Improve a requirement statement */
  improve: (statement: string, opts?: {
    title?: string; rationale?: string; issues?: string[]; domain_context?: string;
  }) =>
    api.post<ImproveResponse>('/ai/writer/improve', {
      statement,
      title: opts?.title || '',
      rationale: opts?.rationale || '',
      issues: opts?.issues || [],
      domain_context: opts?.domain_context || '',
    }),

  /** Decompose requirement into sub-requirements */
  decompose: (statement: string, opts?: {
    title?: string; current_level?: string; target_level?: string;
    req_type?: string; project_context?: string;
  }) =>
    api.post<DecomposeResponse>('/ai/writer/decompose', {
      statement,
      title: opts?.title || '',
      current_level: opts?.current_level || 'L1',
      target_level: opts?.target_level || '',
      req_type: opts?.req_type || 'functional',
      project_context: opts?.project_context || '',
    }),

  /** Generate verification criteria */
  generateVerification: (statement: string, method: string, opts?: {
    title?: string; domain_context?: string;
  }) =>
    api.post<VerificationCriteria>('/ai/writer/generate-verification', {
      statement,
      method,
      title: opts?.title || '',
      domain_context: opts?.domain_context || '',
    }),

  /** Generate rationale */
  generateRationale: (statement: string, opts?: {
    title?: string; req_type?: string; project_context?: string;
  }) =>
    api.post<GenerateRationaleResponse>('/ai/writer/generate-rationale', {
      statement,
      title: opts?.title || '',
      req_type: opts?.req_type || 'functional',
      project_context: opts?.project_context || '',
    }),

  /** Summarize changes for review board */
  summarizeChanges: (changes: Array<Record<string, any>>, opts?: {
    project_name?: string; board_type?: string;
  }) =>
    api.post<SummarizeChangesResponse>('/ai/writer/summarize-changes', {
      changes,
      project_name: opts?.project_name || '',
      board_type: opts?.board_type || 'CCB',
    }),

  /** Check if writing assistant is available */
  getStatus: () => api.get('/ai/writer/status'),
};
