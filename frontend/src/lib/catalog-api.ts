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
  CatalogPartMassUpdateResult,
  CatalogPartPlacementRequest,
  CatalogPartUsage,
  CatalogPartUsageReport,
  CatalogPartVariantRequest,
  PartClass,
  LifecycleStatus,
  PendingCatalogImport,
  PendingCatalogImportUpdate,
  PendingImportStatus,
  StepUploadResponse,
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

  // CADPORT-TDD-ASTRA-BRIDGE-001 Phase 2: source CAD files.
  listPartSourceFiles: (id: number) =>
    api.get<Array<{
      kind: 'sldprt' | 'sldasm' | 'step';
      filename: string;
      size_bytes: number;
      sha256: string;
      mime_type: string;
      download_url: string;
    }>>(`${BASE}/parts/${id}/source-files`),

  updatePart: (id: number, data: Partial<CatalogPartCreatePayload>) =>
    api.patch<CatalogPartDetail>(`${BASE}/parts/${id}`, data),

  /**
   * CADPORT-TDD-STEP-001 §7.1.3: PATCH the mass on a STEP-sourced or
   * material-derived part. ``mass_kg = null`` clears mass + inertia
   * back to the geometric-only ("cad") state. SolidWorks-imported
   * rows return 409 — their mass is owned upstream by CADPORT.
   */
  updatePartMass: (id: number, mass_kg: number | null) =>
    api.patch<CatalogPartMassUpdateResult>(`${BASE}/parts/${id}/mass`, { mass_kg }),

  // CADPORT-TDD-LIFECYCLE-001 Phase 2: edit supplier + name on
  // existing parts, with propagation to CADPORT.
  updatePartSupplier: (
    id: number,
    body: { supplier_id?: number | null; proposed_supplier_name?: string | null },
  ) =>
    api.patch<CatalogPartDetail>(`${BASE}/parts/${id}/supplier`, body),

  updatePartName: (id: number, display_name: string) =>
    api.patch<CatalogPartDetail>(`${BASE}/parts/${id}/name`, { display_name }),

  /**
   * Delete a catalog part. CLEANUP-002 Phase 4 (AD-7): default path
   * is soft-delete and 409s with a structured usage report when any
   * downstream entity (project_parts, mechanical_joints transitively,
   * units, catalog_connectors, variant children) references this
   * part. Pre-flight `getPartUsageReport` to decide if Delete should
   * even be offered.
   *
   * The legacy `admin_force=true` escape still hard-deletes via the
   * existing FK cascade/RESTRICT behavior — leave it false for normal
   * UI deletes; admin tooling can override.
   */
  deletePart: (id: number, adminForce = false) =>
    api.delete<{
      status: string; id: number;
      soft_delete?: boolean;
      units_unlinked?: number;
      admin_force?: boolean;
    }>(
      `${BASE}/parts/${id}`,
      { params: { admin_force: adminForce } },
    ),

  /** Returns the list of project units that have this catalog part placed. */
  getPartUsage: (id: number) =>
    api.get<CatalogPartUsage[]>(`${BASE}/parts/${id}/usage`),

  /**
   * CLEANUP-002 Phase 4 (AD-8). Returns the comprehensive usage
   * report — project breakdown plus non-project-scoped counts
   * (catalog_connectors, variant children). `deletable` is the
   * single bit the UI consults to enable/disable Delete.
   */
  getPartUsageReport: (id: number) =>
    api.get<CatalogPartUsageReport>(`${BASE}/parts/${id}/usage-report`),

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

  /**
   * CLEANUP-002 Phase 4 (AD-6). Hard-deletes a pending import row.
   * Backend also drops the linked supplier_document blob iff no
   * other pending import references it and no live catalog_part was
   * sourced from it; `supplier_document_deleted` in the response
   * reports whether that cascade fired.
   */
  deletePendingImport: (id: number) =>
    api.delete<{
      deleted: boolean;
      id: number;
      supplier_document_deleted: boolean;
    }>(`${BASE}/pending-imports/${id}`),

  // ══════════════════════════════════════
  //  Phase 7 — ICD ingestion endpoints
  // ══════════════════════════════════════

  /**
   * Trigger ICD extraction for an UPLOADED supplier document. Returns
   * 202 + {job_id, status, started_at}; clients poll
   * `getDocument(doc_id)` for `extraction_status` to hit `pending_review`
   * (then navigate to `/catalog/documents/[id]/review`) or `failed`.
   */
  triggerExtraction: (docId: number) =>
    api.post<{ job_id: number; status: string; started_at: string }>(
      `${BASE}/documents/${docId}/extract`,
    ),

  /**
   * Approve a PendingCatalogImport. Atomic on the backend — Supplier
   * (if new), CatalogPart, CatalogConnectors, CatalogPins all created or
   * none. Returns the new CatalogPartDetail so the UI can navigate to it.
   */
  approvePendingImport: (id: number) =>
    api.post<CatalogPartDetail>(`${BASE}/pending-imports/${id}/approve`),

  /**
   * Reject a PendingCatalogImport. The source SupplierDocument moves to
   * REJECTED; no catalog data is created. Optional reason is stored on
   * the pending row for audit.
   */
  rejectPendingImport: (id: number, reason?: string) =>
    api.post<PendingCatalogImport>(
      `${BASE}/pending-imports/${id}/reject`,
      { reason: reason || null },
    ),

  // ══════════════════════════════════════
  //  TDD-CAT-002 — STEP file upload
  // ══════════════════════════════════════

  /**
   * Upload a STEP file. The backend parser runs inline:
   *   - SHA-256 dedup across ALL suppliers (409 on duplicate)
   *   - vendor auto-detect from filename
   *   - supplier auto-create on first vendor sighting
   *   - returns the new pending_import_id for the review page
   *
   * Note: the shared axios instance sets a default
   * `Content-Type: application/json`. Axios only auto-fills the
   * multipart boundary when *no* Content-Type is in effect; with the
   * JSON default in place, FormData would be serialised as JSON and
   * the backend would 422 with `body.file required`. We pass
   * `multipart/form-data` here so axios replaces it with the correctly
   * bounded form-data header.
   */
  uploadStep: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return api.post<StepUploadResponse>(`${BASE}/upload-step`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
};
