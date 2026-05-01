// ══════════════════════════════════════════════════════════════
//  ASTRA — Supplier Catalog API Client
//  Typed Axios calls for /api/v1/catalog/* endpoints (Phase 2 backend).
//
//  File: frontend/src/lib/catalog-api.ts
//  Path: C:\Users\Mason\Documents\ASTRA\frontend\src\lib\catalog-api.ts
//  Phase 3 — ASTRA-TDD-INTF-002
// ══════════════════════════════════════════════════════════════

import api from './api';
import type {
  Supplier,
  SupplierDocument,
  SupplierDocumentType,
  CatalogPart,
  CatalogPartDetail,
  CatalogPartCreatePayload,
  CatalogPartPlacementRequest,
  CatalogPartUsage,
  CatalogPartVariantRequest,
  PartClass,
  LifecycleStatus,
  PendingCatalogImport,
  PendingCatalogImportUpdate,
  PendingImportStatus,
} from './catalog-types';
import type { Unit } from './interface-types';

const BASE = '/catalog';

export const catalogAPI = {

  // ══════════════════════════════════════
  //  §9.1 Suppliers
  // ══════════════════════════════════════

  listSuppliers: (params?: {
    q?: string;
    is_active?: boolean;
    skip?: number;
    limit?: number;
  }) =>
    api.get<Supplier[]>(`${BASE}/suppliers`, { params }),

  createSupplier: (data: Partial<Supplier>) =>
    api.post<Supplier>(`${BASE}/suppliers`, data),

  getSupplier: (id: number) =>
    api.get<Supplier>(`${BASE}/suppliers/${id}`),

  updateSupplier: (id: number, data: Partial<Supplier>) =>
    api.patch<Supplier>(`${BASE}/suppliers/${id}`, data),

  /**
   * Hard-delete a supplier. Pass `admin_force=true` to cascade-delete its
   * catalog parts as well — the backend will 409 otherwise when parts exist.
   */
  deleteSupplier: (id: number, adminForce = false) =>
    api.delete<{ status: string; id: number; parts_dropped: number }>(
      `${BASE}/suppliers/${id}`,
      { params: { admin_force: adminForce } },
    ),

  // ══════════════════════════════════════
  //  §9.2 Supplier Documents
  // ══════════════════════════════════════

  /**
   * Multipart upload. Returns the new document's metadata. The backend does
   * NOT trigger extraction in Phase 2 — `extraction_status` lands as
   * `'uploaded'`. Phase 7 wires the AI ingestion path.
   *
   * Per-supplier SHA-256 dedup: re-uploading the same file under the same
   * supplier 409s; uploading under a different supplier is allowed.
   */
  uploadDocument: (
    supplierId: number,
    file: File,
    documentType: SupplierDocumentType,
    title: string,
    extras?: { revision?: string; document_number?: string },
  ) => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('title', title);
    fd.append('document_type', documentType);
    if (extras?.revision) fd.append('revision', extras.revision);
    if (extras?.document_number) fd.append('document_number', extras.document_number);
    return api.post<SupplierDocument>(
      `${BASE}/suppliers/${supplierId}/documents/upload`,
      fd,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
  },

  getDocument: (docId: number) =>
    api.get<SupplierDocument>(`${BASE}/documents/${docId}`),

  /** Streams the raw file. Use the response.data with FileSaver or a Blob URL. */
  downloadDocumentFile: (docId: number) =>
    api.get(`${BASE}/documents/${docId}/file`, { responseType: 'blob' }),

  deleteDocument: (docId: number) =>
    api.delete<{ status: string; id: number }>(`${BASE}/documents/${docId}`),

  // ══════════════════════════════════════
  //  §9.3 Catalog Parts
  // ══════════════════════════════════════

  listParts: (params?: {
    q?: string;
    supplier_id?: number;
    part_class?: PartClass;
    lifecycle_status?: LifecycleStatus;
    skip?: number;
    limit?: number;
  }) =>
    api.get<CatalogPart[]>(`${BASE}/parts`, { params }),

  createPart: (data: CatalogPartCreatePayload) =>
    api.post<CatalogPartDetail>(`${BASE}/parts`, data),

  getPart: (id: number) =>
    api.get<CatalogPartDetail>(`${BASE}/parts/${id}`),

  updatePart: (id: number, data: Partial<CatalogPartCreatePayload>) =>
    api.patch<CatalogPartDetail>(`${BASE}/parts/${id}`, data),

  /**
   * Hard-delete a catalog part. Pass `admin_force=true` to NULL out
   * `catalog_part_id` on any project units that reference it — the backend
   * 409s otherwise when the part is in use.
   */
  deletePart: (id: number, adminForce = false) =>
    api.delete<{ status: string; id: number; units_unlinked: number }>(
      `${BASE}/parts/${id}`,
      { params: { admin_force: adminForce } },
    ),

  /** Returns the list of project units that have this catalog part placed. */
  getPartUsage: (id: number) =>
    api.get<CatalogPartUsage[]>(`${BASE}/parts/${id}/usage`),

  /**
   * Place an existing catalog part into a project as a Unit. The placement
   * also clones the part's connectors+pins onto the new project Unit.
   *
   * Backend RBAC: req_eng+ AND project_member. Non-members get 403; the
   * caller should surface a friendly error and offer to request access.
   */
  placePart: (catalogPartId: number, data: CatalogPartPlacementRequest) =>
    api.post<Unit>(`${BASE}/parts/${catalogPartId}/place`, data),

  /**
   * Clone an existing catalog part as a new variant (sets parent_part_id +
   * variant_label on the child). When `copy_connectors=true` the connector
   * tree is also cloned.
   */
  createVariant: (parentId: number, data: CatalogPartVariantRequest) =>
    api.post<CatalogPartDetail>(`${BASE}/parts/${parentId}/variant`, data),

  // ══════════════════════════════════════
  //  §9.4 Pending Imports (READ + EDIT only in Phase 2)
  // ══════════════════════════════════════

  listPendingImports: (params?: {
    status?: PendingImportStatus;
    supplier_id?: number;
    skip?: number;
    limit?: number;
  }) =>
    api.get<PendingCatalogImport[]>(`${BASE}/pending-imports`, { params }),

  getPendingImport: (id: number) =>
    api.get<PendingCatalogImport>(`${BASE}/pending-imports/${id}`),

  updatePendingImport: (id: number, data: PendingCatalogImportUpdate) =>
    api.patch<PendingCatalogImport>(`${BASE}/pending-imports/${id}`, data),

  // ══════════════════════════════════════
  //  Phase 7 stubs — approve / reject pending imports
  //  Wired to a clear "coming soon" so Tab 3 of <PlaceLruModal> can call
  //  through without compile-error coupling later.
  // ══════════════════════════════════════

  approvePendingImport: (_id: number): Promise<never> => {
    throw new Error('Pending import approval ships in Phase 7 (ICD ingestion).');
  },

  rejectPendingImport: (_id: number, _reason: string): Promise<never> => {
    throw new Error('Pending import rejection ships in Phase 7 (ICD ingestion).');
  },
};
