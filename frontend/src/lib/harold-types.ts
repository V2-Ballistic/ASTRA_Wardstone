// ════════════════════════════════════════════════════════════════
//  ASTRA — HAROLD V2 integration TypeScript types
//  Mirrors backend Pydantic schemas in app/schemas/harold.py.
//
//  File: frontend/src/lib/harold-types.ts
// ════════════════════════════════════════════════════════════════
//
// Discriminated-union pattern
// ---------------------------
// Every HAROLD-proxy endpoint returns HTTP 200 with one of two shapes:
//   { harold_available: true,  data: T }
//   { harold_available: false, reason: string }
//
// Callers narrow via `result.harold_available` and never have to
// parse HTTP status codes. /heartbeat is the one exception — it
// always returns a flat shape so the UI can read `enabled` +
// `reachable` directly on mount.

// ── Discriminated-union envelope ─────────────────────────────────
export type HaroldResult<T> =
  | { harold_available: true; data: T }
  | { harold_available: false; reason: string };

// ── Heartbeat (flat shape) ───────────────────────────────────────
export interface HaroldHeartbeat {
  enabled: boolean;
  reachable: boolean;
  base_url: string;
  response_time_ms?: number | null;
  version?: string | null;
  reason?: string | null;
}

// ── System codes ─────────────────────────────────────────────────
export interface HaroldSystemCode {
  code: string;          // "FH", "MH", ...
  name: string;
  description: string;
  category?: string | null;
}

export interface SystemCodesPayload {
  codes: HaroldSystemCode[];
  total: number;
}

// ── WPN suggestion ───────────────────────────────────────────────
export interface WpnSuggestion {
  suggested_wpn: string;
  system_code: string;
  next_index: number;
  existing_count: number;
  source: 'harold' | 'fallback';
  reason?: string | null;
}

// ── WPN validation ───────────────────────────────────────────────
export interface WpnParsedFields {
  sys: string;
  num: number;
  rev: string;
}

export interface WpnValidationResult {
  wpn: string;
  is_valid_format: boolean;
  is_issued: boolean;
  errors: string[];
  warnings: string[];
  parsed?: WpnParsedFields | null;
  ledger_entry?: Record<string, unknown> | null;
}

// ── Filename validation ──────────────────────────────────────────
export interface FilenameValidationResult {
  filename: string;
  base_name: string;
  extension: string;
  is_wardstone_format: boolean;
  extracted_wpn?: string | null;
  wpn_validation?: WpnValidationResult | null;
}

// ── Reconcile (manual Sync with HAROLD) ──────────────────────────
export interface ReconcileResult {
  reconciled: boolean;
  wpn: string;
  prior_wpn?: string | null;
  branch: 'issue_specific_ok' | 'issue_specific_collision_reissued' | 'noop' | string;
  message?: string | null;
}

// ── Client-side WPN format check (AD-12) ─────────────────────────
//
// `WS-<SYS>-P<NNNNNN>-<REV>` where:
//   * SYS  : 2 uppercase letters
//   * NUM  : exactly 6 digits
//   * REV  : ASME 20-letter alphabet (excludes I, O, Q, S, X, Z)
//
// This is a soft pre-flight only — HAROLD V2 is authoritative via
// POST /harold/validate.
export const WPN_PATTERN = /^WS-[A-Z]{2}-P[0-9]{6}-[ABCDEFGHJKLMNPRTUVWY]$/;

export function looksLikeWardstoneWpn(value: string): boolean {
  return WPN_PATTERN.test(value.trim());
}
