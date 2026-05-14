// ════════════════════════════════════════════════════════════════
//  ASTRA — HAROLD V2 API client
//  Wraps the /api/v1/harold/* proxy endpoints (Phase 3 of
//  TDD-HAROLD-INT-002). All HAROLD calls go through the ASTRA
//  backend (AD-4) — the browser never crosses origins to V2.
//
//  File: frontend/src/lib/harold-api.ts
// ════════════════════════════════════════════════════════════════

import api from './api';
import type {
  FilenameValidationResult,
  HaroldHeartbeat,
  HaroldResult,
  ReconcileResult,
  SystemCodesPayload,
  WpnSuggestion,
  WpnValidationResult,
} from './harold-types';

export const haroldAPI = {
  // Flat shape — used on mount to decide whether HAROLD-aware UI
  // affordances should render at all (enabled + reachable).
  heartbeat: () =>
    api.get<HaroldHeartbeat>('/harold/heartbeat'),

  systemCodes: () =>
    api.get<HaroldResult<SystemCodesPayload>>('/harold/system-codes'),

  // AD-6 part_class → system_code → next-available WPN. ``hint`` is
  // an optional filename / free-text passed to the V2 suggester.
  suggest: (part_class: string, hint?: string) =>
    api.post<HaroldResult<WpnSuggestion>>('/harold/suggest', {
      part_class,
      hint: hint ?? null,
    }),

  // Format + ledger lookup. ``is_valid_format=false`` is a NORMAL
  // result — only network failures hit the unavailable path.
  validate: (wpn: string) =>
    api.post<HaroldResult<WpnValidationResult>>('/harold/validate', { wpn }),

  // Filename parse + optional HAROLD lookup. Always returns the
  // structural parse; ``wpn_validation`` is populated only when the
  // filename contains a Wardstone-format WPN AND HAROLD is reachable.
  validateFilename: (filename: string) =>
    api.post<HaroldResult<FilenameValidationResult>>(
      '/harold/validate-filename',
      { filename },
    ),

  // Manual "Sync with HAROLD" trigger for a catalog part whose
  // wpn_pending_sync flag is True (fallback WPN was minted while
  // HAROLD was unreachable).
  reconcile: (part_id: number) =>
    api.post<HaroldResult<ReconcileResult>>(
      `/harold/parts/${part_id}/reconcile`,
    ),
};
