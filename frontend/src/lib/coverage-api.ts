// ══════════════════════════════════════════════════════════════
//  ASTRA — Source Coverage — API client
//  Typed Axios calls for /api/v1/coverage/*.
//
//  File: frontend/src/lib/coverage-api.ts
//  Phase 6 — ASTRA-TDD-INTF-002
// ══════════════════════════════════════════════════════════════

import api from './api';
import type {
  CosignRequest,
  CoverageException,
  CoverageExceptionCreate,
  CoverageExceptionListResponse,
  CoverageReportResponse,
  CoverageSeverity,
  OrphanListResponse,
} from './coverage-types';

const BASE = '/coverage';

export const coverageAPI = {

  getReport: (projectId: number, opts?: { live?: boolean }) =>
    api.get<CoverageReportResponse>(`${BASE}/source/${projectId}`, {
      params: opts?.live ? { live: true } : undefined,
    }),

  getOrphans: (projectId: number, opts?: {
    severity?: CoverageSeverity;
    level?: string;
    limit?: number;
    offset?: number;
    live?: boolean;
  }) =>
    api.get<OrphanListResponse>(`${BASE}/source/${projectId}/orphans`, {
      params: opts,
    }),

  fileException: (body: CoverageExceptionCreate) =>
    api.post<CoverageException>(`${BASE}/exception`, body),

  listExceptions: (projectId: number, opts?: {
    active_only?: boolean;
    limit?: number;
    offset?: number;
  }) =>
    api.get<CoverageExceptionListResponse>(`${BASE}/exceptions/${projectId}`, {
      params: opts,
    }),

  cosignException: (id: number, body?: CosignRequest) =>
    api.post<CoverageException>(`${BASE}/exceptions/${id}/cosign`, body ?? {}),

  // Sidebar badge: total error + warning across the project. Hits the same
  // /coverage/source endpoint as the dashboard so we don't pay for an extra
  // round-trip.
  badgeCount: async (projectId: number): Promise<number> => {
    try {
      const r = await api.get<CoverageReportResponse>(
        `${BASE}/source/${projectId}`,
      );
      const summary = r.data.summary ?? {};
      return Object.values(summary).reduce(
        (acc, s) => acc + (s.warning ?? 0) + (s.error ?? 0),
        0,
      );
    } catch {
      return 0;
    }
  },
};

export default coverageAPI;
