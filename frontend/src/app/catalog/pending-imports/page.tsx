'use client';

/**
 * ASTRA — Catalog Pending Imports (list page)
 * ============================================
 * File: frontend/src/app/catalog/pending-imports/page.tsx
 *
 * CLEANUP-002 Phase 3 created this list page at /catalog/pending-imports
 * so the parts-library/pending-imports → catalog/pending-imports 308
 * redirect lands somewhere real.
 *
 * CLEANUP-002 Phase 4 (AD-6) adds an inline Delete action per row.
 * Hard-deletes the pending import; the linked supplier_document is
 * cascade-deleted iff no other live reference remains (server-side
 * decision; the response carries `supplier_document_deleted` for the
 * toast).
 */

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, Loader2, Trash2 } from 'lucide-react';

import { catalogAPI } from '@/lib/catalog-api';
import { formatApiError } from '@/lib/errors';
import {
  type PendingCatalogImport,
  PENDING_IMPORT_STATUS_LABELS,
} from '@/lib/catalog-types';
import ConfirmDialog from '@/components/ConfirmDialog';

export default function CatalogPendingImportsListPage() {
  const [imports, setImports] = useState<PendingCatalogImport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PendingCatalogImport | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    catalogAPI
      .listPendingImports()
      .then((res) => {
        setImports(res.data);
        setError(null);
      })
      .catch((err) => {
        setError(formatApiError(err, 'Failed to load pending imports'));
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const onConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    setError(null);
    try {
      const r = await catalogAPI.deletePendingImport(deleteTarget.id);
      setDeleteTarget(null);
      setFlash(
        r.data.supplier_document_deleted
          ? `Deleted pending import #${r.data.id} and its supplier document (no other references).`
          : `Deleted pending import #${r.data.id}.`,
      );
      refresh();
    } catch (err) {
      setError(formatApiError(err, 'Failed to delete pending import'));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="container mx-auto p-6">
      <div className="mb-6">
        <Link href="/catalog" className="text-xs text-blue-400 hover:underline">
          ← Catalog
        </Link>
        <h1 className="mt-2 text-2xl font-bold text-slate-100">
          Pending STEP Imports
        </h1>
        <p className="text-sm text-slate-500">
          STEP files awaiting review and approval.
        </p>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </div>
      )}

      {flash && (
        <div role="status" className="mb-3 rounded border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
          {flash}
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 rounded border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-400">
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" /> {error}
        </div>
      )}

      {!loading && !error && imports.length === 0 && (
        <div className="rounded border border-dashed border-astra-border p-8 text-center text-sm text-slate-500">
          No pending imports.
        </div>
      )}

      {!loading && imports.length > 0 && (
        <div className="overflow-auto rounded border border-astra-border">
          <table className="w-full text-sm">
            <thead className="bg-astra-surface text-xs uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-3 py-2 text-left">ID</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-left">Proposed name</th>
                <th className="px-3 py-2 text-left">Part number</th>
                <th className="px-3 py-2 text-left">Created</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-astra-border">
              {imports.map((p) => {
                const data = p.extracted_data ?? {};
                const proposedName = (data.name as string) || '—';
                const partNumber = (data.part_number as string) || '—';
                return (
                  <tr key={p.id} className="text-slate-200 hover:bg-astra-surface/60">
                    <td className="px-3 py-2 font-mono text-xs">{p.id}</td>
                    <td className="px-3 py-2 text-xs">
                      {PENDING_IMPORT_STATUS_LABELS[p.status] ?? p.status}
                    </td>
                    <td className="px-3 py-2">{proposedName}</td>
                    <td className="px-3 py-2 font-mono text-xs">{partNumber}</td>
                    <td className="px-3 py-2 text-xs">
                      {new Date(p.created_at).toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          type="button"
                          aria-label={`Delete pending import ${p.id}`}
                          onClick={() => setDeleteTarget(p)}
                          className="rounded p-1 text-slate-500 hover:bg-red-500/10 hover:text-red-400"
                        >
                          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                        <Link
                          href={`/catalog/pending-imports/${p.id}`}
                          className="text-xs text-blue-400 hover:underline"
                        >
                          Review →
                        </Link>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        title={`Delete pending import #${deleteTarget?.id ?? ''}?`}
        message={
          deleteTarget
            ? 'Hard-delete this pending import. The linked supplier_document will also be removed if no other pending import or live catalog_part references it. This action cannot be undone.'
            : ''
        }
        confirmLabel={deleting ? 'Deleting…' : 'Delete'}
        destructive
        onCancel={() => { if (!deleting) setDeleteTarget(null); }}
        onConfirm={onConfirmDelete}
      />
    </div>
  );
}
