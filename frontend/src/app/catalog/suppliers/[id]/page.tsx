'use client';

/**
 * ASTRA — Supplier Detail Page
 * ==============================
 * File: frontend/src/app/catalog/suppliers/[id]/page.tsx
 *
 * Sections:
 *   - Supplier metadata (with edit / delete actions)
 *   - Documents list (with upload control)
 *   - Catalog parts list (filtered by this supplier)
 *
 * RBAC gating: write/delete buttons are visible to req_eng+ users; the
 * backend re-checks and 403s if the role doesn't match.
 *
 * Phase 3 — ASTRA-TDD-INTF-002.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ChevronLeft, Building2, Loader2, Plus, AlertTriangle, FileText,
  Upload, Trash2, Edit3, Cpu, Download, X, Check,
} from 'lucide-react';
import clsx from 'clsx';

import { catalogAPI } from '@/lib/catalog-api';
import { formatApiError } from '@/lib/errors';
import {
  type Supplier,
  type SupplierDocument,
  type SupplierDocumentType,
  type CatalogPart,
  DOCUMENT_TYPE_LABELS,
  EXTRACTION_STATUS_LABELS,
  PART_CLASS_LABELS,
  LIFECYCLE_COLORS,
} from '@/lib/catalog-types';
import { useAuth } from '@/lib/auth';
import ConfirmDialog from '@/components/ConfirmDialog';

const DOCUMENT_TYPES: SupplierDocumentType[] = [
  'icd', 'datasheet', 'spec_sheet', 'drawing', 'app_note', 'user_manual', 'other',
];

const WRITE_ROLES = new Set(['admin', 'project_manager', 'requirements_engineer']);

// ══════════════════════════════════════
//  Upload Document Modal
// ══════════════════════════════════════

function UploadDocumentModal({ supplierId, onClose, onUploaded }: {
  supplierId: number;
  onClose: () => void;
  onUploaded: (d: SupplierDocument) => void;
}) {
  const [title, setTitle] = useState('');
  const [docType, setDocType] = useState<SupplierDocumentType>('datasheet');
  const [revision, setRevision] = useState('');
  const [docNumber, setDocNumber] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);

  const canSubmit = title.trim().length > 0 && file !== null;

  const handleUpload = async () => {
    if (!file || !title.trim()) return;
    setSubmitting(true);
    setError('');
    try {
      const r = await catalogAPI.uploadDocument(supplierId, file, docType, title.trim(), {
        revision: revision.trim() || undefined,
        document_number: docNumber.trim() || undefined,
      });
      onUploaded(r.data);
      onClose();
    } catch (e: unknown) {
      setError(formatApiError(e, 'Failed to upload document'));
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-labelledby="upload-doc-title"
        className="w-full max-w-md rounded-2xl border border-astra-border bg-astra-surface p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 id="upload-doc-title" className="text-sm font-bold text-slate-100">Upload Document</h3>
          <button type="button" onClick={onClose} aria-label="Close upload dialog" className="text-slate-400 hover:text-slate-200">
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        {error && (
          <div role="alert" className="mb-3 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
            <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" /> {error}
          </div>
        )}

        <div className="space-y-3">
          <div>
            <label htmlFor="up-title" className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">
              Title<span className="text-red-400 ml-0.5">*</span>
            </label>
            <input id="up-title" value={title} onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. HG2120 IMU Datasheet"
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="up-type" className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">Type</label>
              <select id="up-type" value={docType} onChange={(e) => setDocType(e.target.value as SupplierDocumentType)}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50">
                {DOCUMENT_TYPES.map((t) => <option key={t} value={t}>{DOCUMENT_TYPE_LABELS[t]}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="up-rev" className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">Revision</label>
              <input id="up-rev" value={revision} onChange={(e) => setRevision(e.target.value)}
                placeholder="e.g. C"
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
          </div>
          <div>
            <label htmlFor="up-docnum" className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">Document Number</label>
            <input id="up-docnum" value={docNumber} onChange={(e) => setDocNumber(e.target.value)}
              placeholder="optional"
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
          </div>
          <div>
            <label htmlFor="up-file" className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">
              File<span className="text-red-400 ml-0.5">*</span>
            </label>
            <input
              ref={fileInput}
              id="up-file"
              type="file"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-xs text-slate-300 file:mr-3 file:rounded-lg file:border-0 file:bg-blue-600 file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-white hover:file:bg-blue-500"
            />
            {file && <div className="mt-1 text-[10px] text-slate-500">{file.name} · {(file.size / 1024).toFixed(1)} KB</div>}
          </div>
        </div>

        <div className="mt-5 flex items-center justify-end gap-2">
          <button type="button" onClick={onClose}
            className="rounded-lg border border-astra-border px-4 py-2 text-xs text-slate-400 hover:text-slate-200">
            Cancel
          </button>
          <button type="button" disabled={!canSubmit || submitting} onClick={handleUpload}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed">
            {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Upload className="h-3.5 w-3.5" aria-hidden="true" />}
            Upload
          </button>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  Page
// ══════════════════════════════════════

export default function SupplierDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { user } = useAuth();
  const supplierId = Number(params?.id);

  const [supplier, setSupplier] = useState<Supplier | null>(null);
  const [documents, setDocuments] = useState<SupplierDocument[]>([]);
  const [parts, setParts] = useState<CatalogPart[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showUpload, setShowUpload] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmDeleteDocId, setConfirmDeleteDocId] = useState<number | null>(null);

  const canWrite = user ? WRITE_ROLES.has(user.role) : false;
  const canDelete = user?.role === 'admin';

  const refresh = useCallback(() => {
    if (!Number.isFinite(supplierId)) return;
    setLoading(true);
    Promise.all([
      catalogAPI.getSupplier(supplierId),
      catalogAPI.listParts({ supplier_id: supplierId, limit: 200 }),
    ])
      .then(([sRes, pRes]) => {
        setSupplier(sRes.data);
        setParts(pRes.data);
      })
      .catch((e) => setError(formatApiError(e, 'Failed to load supplier')))
      .finally(() => setLoading(false));
  }, [supplierId]);

  // Documents endpoint isn't a single GET — we keep the list local and
  // append on upload / remove on delete. Initial load via parts uses the
  // supplier's `document_count` as a hint, but the actual rows come from
  // the upload responses or — long term — a future GET /suppliers/{id}/documents
  // endpoint. For now the list is empty until the user uploads or until
  // we add a list endpoint. We surface `document_count` from the supplier
  // response so the user knows how many exist server-side.

  useEffect(() => { refresh(); }, [refresh]);

  const handleDeleteSupplier = async () => {
    setConfirmDelete(false);
    try {
      await catalogAPI.deleteSupplier(supplierId);
      router.push('/catalog');
    } catch (e: unknown) {
      setError(formatApiError(e, 'Failed to delete supplier'));
    }
  };

  const handleDeleteDocument = async () => {
    if (confirmDeleteDocId === null) return;
    const docId = confirmDeleteDocId;
    setConfirmDeleteDocId(null);
    try {
      await catalogAPI.deleteDocument(docId);
      setDocuments((d) => d.filter((x) => x.id !== docId));
    } catch (e: unknown) {
      setError(formatApiError(e, 'Failed to delete document'));
    }
  };

  const handleDownload = async (doc: SupplierDocument) => {
    try {
      const r = await catalogAPI.downloadDocumentFile(doc.id);
      const url = URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = doc.title;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      setError(formatApiError(e, 'Failed to download document'));
    }
  };

  if (loading && !supplier) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-blue-500" aria-label="Loading supplier" />
      </div>
    );
  }

  if (!supplier) {
    return (
      <div>
        <button type="button" onClick={() => router.push('/catalog')} className="mb-3 flex items-center gap-1 text-xs text-slate-400 hover:text-blue-300">
          <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" /> Back to Catalog
        </button>
        <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {error || 'Supplier not found'}
        </div>
      </div>
    );
  }

  return (
    <div>
      <button type="button" onClick={() => router.push('/catalog')} className="mb-4 flex items-center gap-1 text-xs text-slate-400 hover:text-blue-300">
        <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" /> Back to Catalog
      </button>

      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
            <Building2 className="h-6 w-6 text-blue-400" aria-hidden="true" />
            {supplier.name}
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500">
            {supplier.short_name && <span>{supplier.short_name}</span>}
            {supplier.cage_code && <span>CAGE: <span className="font-mono text-slate-300">{supplier.cage_code}</span></span>}
            {supplier.duns && <span>DUNS: <span className="font-mono text-slate-300">{supplier.duns}</span></span>}
            {supplier.country && <span>{supplier.country}</span>}
            {supplier.is_active
              ? <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 font-semibold text-emerald-400">Active</span>
              : <span className="rounded-full bg-slate-500/15 px-2 py-0.5 font-semibold text-slate-400">Inactive</span>
            }
          </div>
        </div>
        <div className="flex items-center gap-2">
          {canDelete && (
            <button type="button" onClick={() => setConfirmDelete(true)}
              className="flex items-center gap-1 rounded-lg border border-red-500/30 px-3 py-1.5 text-xs text-red-400 hover:bg-red-500/10">
              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" /> Delete
            </button>
          )}
        </div>
      </div>

      {error && (
        <div role="alert" className="mb-3 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" /> {error}
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        {/* Metadata */}
        <section className="rounded-xl border border-astra-border bg-astra-surface p-4 lg:col-span-1">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">Contact &amp; Notes</h2>
          <dl className="space-y-2 text-xs">
            <div>
              <dt className="text-[10px] uppercase tracking-wider text-slate-500">Primary Contact</dt>
              <dd className="text-slate-200">{supplier.primary_contact || '—'}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-wider text-slate-500">Primary Email</dt>
              <dd className="text-slate-200">{supplier.primary_email || '—'}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-wider text-slate-500">Website</dt>
              <dd>
                {supplier.website
                  ? <a href={supplier.website} target="_blank" rel="noreferrer" className="text-blue-400 hover:text-blue-300 break-all">{supplier.website}</a>
                  : <span className="text-slate-500">—</span>
                }
              </dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-wider text-slate-500">Address</dt>
              <dd className="whitespace-pre-line text-slate-300">{supplier.address || '—'}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-wider text-slate-500">Notes</dt>
              <dd className="whitespace-pre-line text-slate-300">{supplier.notes || '—'}</dd>
            </div>
          </dl>
        </section>

        {/* Documents */}
        <section className="rounded-xl border border-astra-border bg-astra-surface p-4 lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-2">
              <FileText className="h-3.5 w-3.5" aria-hidden="true" />
              Documents <span className="text-slate-600">({supplier.document_count} on server)</span>
            </h2>
            {canWrite && (
              <button type="button" onClick={() => setShowUpload(true)}
                className="flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500">
                <Upload className="h-3.5 w-3.5" aria-hidden="true" /> Upload
              </button>
            )}
          </div>
          {documents.length === 0 ? (
            <div className="py-6 text-center text-xs text-slate-500">
              No documents in this session yet. Use <strong className="text-slate-300">Upload</strong> to add an ICD,
              datasheet, drawing, or other supplier artifact.
            </div>
          ) : (
            <ul className="divide-y divide-astra-border">
              {documents.map((d) => (
                <li key={d.id} className="flex items-start justify-between gap-3 py-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <FileText className="h-3.5 w-3.5 text-blue-400 flex-shrink-0" aria-hidden="true" />
                      <span className="text-xs font-semibold text-slate-200 truncate">{d.title}</span>
                    </div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] text-slate-500">
                      <span>{DOCUMENT_TYPE_LABELS[d.document_type]}</span>
                      {d.revision && <span>rev {d.revision}</span>}
                      {d.document_number && <span className="font-mono">{d.document_number}</span>}
                      <span>{(d.file_size_bytes / 1024).toFixed(1)} KB</span>
                      <span>{EXTRACTION_STATUS_LABELS[d.extraction_status]}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <button type="button" onClick={() => handleDownload(d)} aria-label={`Download ${d.title}`}
                      className="rounded p-1 text-slate-400 hover:bg-astra-surface-alt hover:text-blue-300">
                      <Download className="h-3.5 w-3.5" aria-hidden="true" />
                    </button>
                    {canDelete && (
                      <button type="button" onClick={() => setConfirmDeleteDocId(d.id)} aria-label={`Delete ${d.title}`}
                        className="rounded p-1 text-slate-400 hover:bg-red-500/10 hover:text-red-400">
                        <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Parts */}
        <section className="rounded-xl border border-astra-border bg-astra-surface p-4 lg:col-span-3">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-2">
              <Cpu className="h-3.5 w-3.5" aria-hidden="true" />
              Catalog Parts <span className="text-slate-600">({parts.length})</span>
            </h2>
            {canWrite && (
              <button type="button" onClick={() => router.push(`/catalog/parts/new?supplier_id=${supplierId}`)}
                className="flex items-center gap-1 rounded-lg border border-astra-border px-3 py-1.5 text-xs font-semibold text-blue-300 hover:bg-blue-500/10">
                <Plus className="h-3.5 w-3.5" aria-hidden="true" /> New Part
              </button>
            )}
          </div>
          {parts.length === 0 ? (
            <div className="py-6 text-center text-xs text-slate-500">
              No catalog parts for this supplier yet.
            </div>
          ) : (
            <table className="w-full text-xs">
              <thead className="text-slate-500">
                <tr className="border-b border-astra-border">
                  <th className="px-2 py-2 text-left font-semibold">Part Number</th>
                  <th className="px-2 py-2 text-left font-semibold">Name</th>
                  <th className="px-2 py-2 text-left font-semibold">Class</th>
                  <th className="px-2 py-2 text-left font-semibold">Lifecycle</th>
                  <th className="px-2 py-2 text-right font-semibold">Used</th>
                </tr>
              </thead>
              <tbody>
                {parts.map((p) => {
                  const lc = LIFECYCLE_COLORS[p.lifecycle_status];
                  return (
                    <tr key={p.id}
                      className="border-b border-astra-border/50 hover:bg-astra-surface-alt cursor-pointer"
                      onClick={() => router.push(`/catalog/parts/${p.id}`)}
                    >
                      <td className="px-2 py-2 font-bold text-slate-200">{p.part_number}{p.revision && <span className="ml-1 text-[10px] text-slate-500">rev {p.revision}</span>}</td>
                      <td className="px-2 py-2 text-slate-300">{p.name}</td>
                      <td className="px-2 py-2 text-slate-400">{PART_CLASS_LABELS[p.part_class]}</td>
                      <td className="px-2 py-2">
                        <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold" style={{ background: lc.bg, color: lc.text }}>
                          {lc.label}
                        </span>
                      </td>
                      <td className="px-2 py-2 text-right text-slate-300">{p.used_in_project_count}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>
      </div>

      {showUpload && canWrite && (
        <UploadDocumentModal
          supplierId={supplierId}
          onClose={() => setShowUpload(false)}
          onUploaded={(d) => setDocuments((prev) => [d, ...prev])}
        />
      )}

      <ConfirmDialog
        open={confirmDelete}
        title={`Delete supplier "${supplier.name}"?`}
        message={
          parts.length > 0
            ? `This supplier has ${parts.length} catalog part${parts.length !== 1 ? 's' : ''}. Deletion will fail unless an admin force-cascades.`
            : 'This action cannot be undone.'
        }
        confirmLabel="Delete"
        destructive
        onCancel={() => setConfirmDelete(false)}
        onConfirm={handleDeleteSupplier}
      />

      <ConfirmDialog
        open={confirmDeleteDocId !== null}
        title="Delete this document?"
        message="The file and its metadata will be permanently removed."
        confirmLabel="Delete"
        destructive
        onCancel={() => setConfirmDeleteDocId(null)}
        onConfirm={handleDeleteDocument}
      />
    </div>
  );
}
