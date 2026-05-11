// ════════════════════════════════════════════════════════════════
//  ASTRA — Project Parts (BOM) API client
//  Wraps /api/v1/projects/{project_id}/parts/* endpoints introduced
//  by TDD-PROJPARTS-001 (Path C).
//
//  File: frontend/src/lib/projparts-api.ts
// ════════════════════════════════════════════════════════════════

import api from './api';
import type {
  BomStats,
  ProjectPartBom,
  ProjectPartBomCreate,
  ProjectPartBomListParams,
  ProjectPartBomUpdate,
} from './projparts-types';

export const projectPartsBomAPI = {
  list: (projectId: number, params?: ProjectPartBomListParams) =>
    api.get<ProjectPartBom[]>(
      `/projects/${projectId}/parts/`, { params },
    ),

  stats: (projectId: number) =>
    api.get<BomStats>(`/projects/${projectId}/parts/stats`),

  unassigned: (projectId: number) =>
    api.get<ProjectPartBom[]>(`/projects/${projectId}/parts/unassigned`),

  create: (projectId: number, data: ProjectPartBomCreate) =>
    api.post<ProjectPartBom>(`/projects/${projectId}/parts/`, data),

  update: (projectId: number, id: number, data: ProjectPartBomUpdate) =>
    api.patch<ProjectPartBom>(`/projects/${projectId}/parts/${id}`, data),

  remove: (projectId: number, id: number, force = false) =>
    api.delete(
      `/projects/${projectId}/parts/${id}`,
      { params: force ? { force: true } : undefined },
    ),
};
