/**
 * ASTRA — AI Embedding Features API Client
 * ============================================
 * File: frontend/src/lib/ai-api.ts   ← NEW
 *
 * API calls for duplicate detection, trace suggestions,
 * verification suggestions, feedback, and analytics.
 */

import api from './api';

export interface SimilarRequirement {
  requirement_id: number;
  req_id: string;
  title: string;
  statement: string;
  similarity_score: number;
  explanation: string;
}

export interface DuplicateGroup {
  group_id: number;
  requirements: SimilarRequirement[];
  max_similarity: number;
  avg_similarity: number;
}

export interface DuplicateCheckResponse {
  is_likely_duplicate: boolean;
  similar_requirements: SimilarRequirement[];
  ai_available: boolean;
}

export interface ProjectDuplicatesResponse {
  project_id: number;
  total_requirements: number;
  duplicate_groups: DuplicateGroup[];
  threshold: number;
  ai_available: boolean;
}

export interface TraceSuggestion {
  suggestion_id?: number;
  source_id: number;
  source_type: string;
  target_id: number;
  target_type: string;
  target_req_id: string;
  target_title: string;
  suggested_link_type: string;
  confidence: number;
  explanation: string;
  status: string;
}

export interface TraceSuggestionsResponse {
  requirement_id: number;
  req_id: string;
  suggestions: TraceSuggestion[];
  ai_available: boolean;
}

export interface VerificationSuggestion {
  requirement_id: number;
  req_id: string;
  suggested_method: string;
  method_rationale: string;
  suggested_criteria: string;
  success_conditions: string[];
  confidence: number;
  ai_available: boolean;
}

export interface AIStats {
  ai_available: boolean;
  embedding_provider: string;
  model_version: string;
  total_embeddings: number;
  total_suggestions: number;
  pending_suggestions: number;
  accepted_suggestions: number;
  rejected_suggestions: number;
  acceptance_rate: number;
  suggestions_by_type: Record<string, number>;
  feedback_stats: Record<string, any>;
}

// ── API Calls ──

export const aiAPI = {
  // Duplicate detection
  getDuplicates: (projectId: number, threshold?: number) =>
    api.get<ProjectDuplicatesResponse>('/ai/duplicates', {
      params: { project_id: projectId, threshold },
    }),

  checkDuplicate: (statement: string, projectId: number, title?: string) =>
    api.post<DuplicateCheckResponse>('/ai/check-duplicate', {
      statement,
      project_id: projectId,
      title: title || '',
    }),

  // Trace suggestions
  getTraceSuggestions: (requirementId: number, projectId?: number) =>
    api.get<TraceSuggestionsResponse>('/ai/trace-suggestions', {
      params: { requirement_id: requirementId, project_id: projectId },
    }),

  // Verification suggestions
  getVerificationSuggestion: (requirementId: number) =>
    api.get<VerificationSuggestion>('/ai/verification-suggestion', {
      params: { requirement_id: requirementId },
    }),

  // Feedback
  submitFeedback: (suggestionId: number, action: 'accepted' | 'rejected' | 'dismissed', comment?: string) =>
    api.post('/ai/feedback', {
      suggestion_id: suggestionId,
      action,
      comment: comment || '',
    }),

  // Reindex
  reindex: (projectId: number, force?: boolean) =>
    api.post('/ai/reindex', { project_id: projectId, force: force || false }),

  // Stats
  getStats: (projectId?: number) =>
    api.get<AIStats>('/ai/stats', { params: { project_id: projectId } }),
};
