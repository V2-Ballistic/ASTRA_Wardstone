// ══════════════════════════════════════════════════════════════
//  ASTRA — Reactive Requirement Sync — API client
//  Typed Axios calls for /api/v1/req-sync/*.
//
//  File: frontend/src/lib/req-sync-api.ts
//  Phase 5 — ASTRA-TDD-INTF-002
// ══════════════════════════════════════════════════════════════

import api from './api';
import type {
  BulkAcceptRequest,
  BulkProposalActionResponse,
  RequirementSyncLockRequest,
  RequirementSyncLockResponse,
  RequirementSyncProposal,
  RequirementSyncProposalDetail,
  SourceLinksResponse,
  SyncProposalListResponse,
  SyncProposalStatus,
  SourceEntityType,
} from './req-sync-types';

const BASE = '/req-sync';

export const reqSyncAPI = {

  listProposals: (params: {
    project_id: number;
    status?: SyncProposalStatus;
    trigger_entity_type?: SourceEntityType;
    limit?: number;
    offset?: number;
  }) =>
    api.get<SyncProposalListResponse>(`${BASE}/proposals`, { params }),

  getProposal: (id: number) =>
    api.get<RequirementSyncProposalDetail>(`${BASE}/proposals/${id}`),

  acceptProposal: (
    id: number,
    body?: { reviewer_notes?: string },
    adminForce = false,
  ) =>
    api.post<RequirementSyncProposalDetail>(
      `${BASE}/proposals/${id}/accept`,
      body ?? {},
      { params: { admin_force: adminForce } },
    ),

  rejectProposal: (id: number, body?: { reviewer_notes?: string }) =>
    api.post<RequirementSyncProposalDetail>(
      `${BASE}/proposals/${id}/reject`,
      body ?? {},
    ),

  bulkAccept: (body: BulkAcceptRequest) =>
    api.post<BulkProposalActionResponse>(
      `${BASE}/proposals/bulk-accept`,
      body,
    ),

  lockRequirement: (reqId: number, body?: RequirementSyncLockRequest) =>
    api.post<RequirementSyncLockResponse>(
      `${BASE}/requirements/${reqId}/lock`,
      body ?? {},
    ),

  unlockRequirement: (reqId: number) =>
    api.post<RequirementSyncLockResponse>(
      `${BASE}/requirements/${reqId}/unlock`,
    ),

  getRequirementSources: (reqId: number) =>
    api.get<SourceLinksResponse>(`${BASE}/requirements/${reqId}/sources`),

  pendingCount: async (projectId: number): Promise<number> => {
    try {
      const r = await api.get<SyncProposalListResponse>(`${BASE}/proposals`, {
        params: { project_id: projectId, status: 'pending', limit: 1 },
      });
      return r.data.total ?? 0;
    } catch {
      return 0;
    }
  },
};

export default reqSyncAPI;
