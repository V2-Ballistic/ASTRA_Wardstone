import api from './api';
import type {
  AssemblyParseJobResponse, JointType, JointStatus, ConfidenceLevel,
  LibraryPartCreate, LibraryPartResponse, LibraryPartSummary,
  MaterialClass, MechanicalJointCreate, MechanicalJointResponse,
  PartType, PartStatus, PendingPartsImportResponse,
  PendingPartsStatus, ProjectPartCreate, ProjectPartResponse,
} from './parts-types';

// ── Parts Library (global) ────────────────────────────────────

export const partsLibraryAPI = {
  list: (params?: {
    part_type?: PartType;
    status?: PartStatus;
    material_class?: MaterialClass;
    search?: string;
    limit?: number;
    offset?: number;
  }) => api.get<LibraryPartSummary[]>('/parts-library/', { params }),

  get: (id: number) =>
    api.get<LibraryPartResponse>(`/parts-library/${id}`),

  create: (data: LibraryPartCreate) =>
    api.post<LibraryPartResponse>('/parts-library/', data),

  update: (id: number, data: Partial<LibraryPartCreate>) =>
    api.patch<LibraryPartResponse>(`/parts-library/${id}`, data),

  uploadStep: (file: File, onProgress?: (pct: number) => void) => {
    const form = new FormData();
    form.append('file', file);
    return api.post<{
      duplicate: boolean;
      pending_import_id?: number;
      existing_part_id?: number;
      existing_wpn?: string;
      message: string;
    }>('/parts-library/upload-step', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => {
        if (onProgress && e.total) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      },
    });
  },

  listPendingImports: (params?: { status?: PendingPartsStatus }) =>
    api.get<PendingPartsImportResponse[]>('/parts-library/pending-imports/', {
      params,
    }),

  getPendingImport: (id: number) =>
    api.get<PendingPartsImportResponse>(`/parts-library/pending-imports/${id}`),

  approveImport: (
    id: number,
    overrides: Record<string, unknown> = {},
    supplier_id?: number,
  ) =>
    api.post<LibraryPartResponse>(
      `/parts-library/pending-imports/${id}/approve`,
      { overrides, supplier_id },
    ),

  rejectImport: (id: number, reason: string) =>
    api.post(`/parts-library/pending-imports/${id}/reject`, { reason }),
};

// ── Project Parts (project-scoped) ─────────────────────────────

export const projectPartsAPI = {
  list: (projectId: number, params?: { limit?: number; offset?: number }) =>
    api.get<ProjectPartResponse[]>(`/projects/${projectId}/parts/`, { params }),

  add: (projectId: number, data: ProjectPartCreate) =>
    api.post<ProjectPartResponse>(`/projects/${projectId}/parts/`, data),

  update: (
    projectId: number,
    id: number,
    data: { quantity?: number; designation?: string; notes?: string },
  ) =>
    api.patch<ProjectPartResponse>(
      `/projects/${projectId}/parts/${id}`, data,
    ),

  remove: (projectId: number, id: number, force = false) =>
    api.delete(`/projects/${projectId}/parts/${id}`, {
      params: force ? { force: true } : undefined,
    }),

  listUnassigned: (projectId: number) =>
    api.get<ProjectPartResponse[]>(`/projects/${projectId}/parts/unassigned`),
};

// ── System Part Assignments ────────────────────────────────────

export const systemPartsAPI = {
  list: (projectId: number, systemId: number) =>
    api.get<unknown[]>(`/projects/${projectId}/systems/${systemId}/parts/`),
  assign: (
    projectId: number,
    systemId: number,
    data: { project_part_id: number; position_order?: number },
  ) =>
    api.post(`/projects/${projectId}/systems/${systemId}/parts/`, data),
  remove: (projectId: number, systemId: number, assignmentId: number) =>
    api.delete(
      `/projects/${projectId}/systems/${systemId}/parts/${assignmentId}`,
    ),
  reorder: (
    projectId: number,
    systemId: number,
    assignmentId: number,
    position_order: number,
  ) =>
    api.patch(
      `/projects/${projectId}/systems/${systemId}/parts/${assignmentId}`,
      { position_order },
    ),
};

// ── Mechanical Joints ──────────────────────────────────────────

export const mechanicalJointsAPI = {
  list: (
    projectId: number,
    params?: {
      joint_type?: JointType;
      status?: JointStatus;
      confidence?: ConfidenceLevel;
      part_id?: number;
      limit?: number;
      offset?: number;
    },
  ) =>
    api.get<MechanicalJointResponse[]>(
      `/projects/${projectId}/mechanical-joints/`, { params },
    ),

  get: (projectId: number, jointId: string) =>
    api.get<MechanicalJointResponse>(
      `/projects/${projectId}/mechanical-joints/${jointId}`,
    ),

  create: (projectId: number, data: MechanicalJointCreate) =>
    api.post<MechanicalJointResponse>(
      `/projects/${projectId}/mechanical-joints/`, data,
    ),

  update: (
    projectId: number,
    jointId: string,
    data: Partial<MechanicalJointCreate>,
  ) =>
    api.patch<MechanicalJointResponse>(
      `/projects/${projectId}/mechanical-joints/${jointId}`, data,
    ),

  approve: (projectId: number, jointId: string) =>
    api.post<MechanicalJointResponse>(
      `/projects/${projectId}/mechanical-joints/${jointId}/approve`,
    ),

  delete: (projectId: number, jointId: string, force = false) =>
    api.delete(
      `/projects/${projectId}/mechanical-joints/${jointId}`,
      { params: force ? { force: true } : undefined },
    ),

  uploadAssembly: (
    projectId: number,
    file: File,
    onProgress?: (pct: number) => void,
  ) => {
    const form = new FormData();
    form.append('file', file);
    return api.post<{ job_id: number; status: string }>(
      `/projects/${projectId}/mechanical-joints/upload-assembly`,
      form,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (onProgress && e.total) {
            onProgress(Math.round((e.loaded / e.total) * 100));
          }
        },
      },
    );
  },

  getParseStatus: (projectId: number, jobId: number) =>
    api.get<AssemblyParseJobResponse>(
      `/projects/${projectId}/mechanical-joints/assembly-parse-status/${jobId}`,
    ),
};
