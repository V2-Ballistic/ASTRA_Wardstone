'use client';

/**
 * ASTRA — Catalog Part Delete Modal (CLEANUP-002 Phase 4, AD-7 + AD-8)
 * =====================================================================
 * File: frontend/src/components/catalog/CatalogPartDeleteModal.tsx
 *
 * Self-contained modal for the list-page delete-with-usage-check flow.
 * On open it fetches GET /catalog/parts/{id}/usage-report and renders
 * the project breakdown. Delete is hard-disabled when not deletable
 * so the user can't even attempt a 409. If the state has drifted
 * between the report fetch and the delete click, the 409 path
 * overwrites the local report with the server's snapshot and keeps
 * the modal open.
 *
 * The catalog-part detail page has its own inline modal that reuses
 * already-fetched state; this component exists so list pages (the
 * catalog parts tab + future per-card surfaces) don't have to
 * duplicate the usage-report + 409 plumbing.
 */

import { useCallback, useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { catalogAPI } from '@/lib/catalog-api';
import { formatApiError, parseStructuredApiError } from '@/lib/errors';
import type { CatalogPartUsageReport } from '@/lib/catalog-types';

interface CatalogPartDeleteModalProps {
  open: boolean;
  partId: number;
  /** Label shown in the modal title (typically WPN or part_number). */
  partLabel: string;
  onClose: () => void;
  /** Called after a successful delete so the parent can refresh. */
  onDeleted: () => void;
}

export default function CatalogPartDeleteModal({
  open, partId, partLabel, onClose, onDeleted,
}: CatalogPartDeleteModalProps) {
  const [report, setReport] = useState<CatalogPartUsageReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState('');

  const fetchReport = useCallback(() => {
    setLoading(true);
    setError('');
    catalogAPI.getPartUsageReport(partId)
      .then((r) => setReport(r.data))
      .catch((e) => setError(formatApiError(e, 'Failed to load usage report')))
      .finally(() => setLoading(false));
  }, [partId]);

  useEffect(() => {
    if (!open) {
      setReport(null);
      setError('');
      setDeleting(false);
      return;
    }
    fetchReport();
  }, [open, fetchReport]);

  const handleDelete = async () => {
    setDeleting(true);
    setError('');
    try {
      await catalogAPI.deletePart(partId);
      onDeleted();
    } catch (e: unknown) {
      const structured = parseStructuredApiError(e);
      if (
        structured?.code === 'part_in_use'
        && typeof structured.usage === 'object'
        && structured.usage !== null
      ) {
        setReport(structured.usage as CatalogPartUsageReport);
        setError(
          typeof structured.message === 'string'
            ? structured.message
            : 'Cannot delete — part is in use.',
        );
      } else {
        setError(formatApiError(e, 'Failed to delete catalog part'));
      }
    } finally {
      setDeleting(false);
    }
  };

  if (!open) return null;

  const canDelete = report?.deletable === true;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={`catalog-part-delete-${partId}-title`}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={() => !deleting && onClose()}
    >
      <div
        className="w-full max-w-lg rounded-2xl border border-astra-border bg-astra-surface p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3
          id={`catalog-part-delete-${partId}-title`}
          className="text-sm font-bold text-slate-100"
        >
          Delete catalog part &ldquo;{partLabel}&rdquo;?
        </h3>

        {loading && (
          <div className="mt-3 flex items-center gap-2 text-xs text-slate-400">
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            Checking downstream references…
          </div>
        )}

        {!loading && report && canDelete && (
          <p className="mt-2 text-xs text-slate-400">
            This part has no downstream references. It will be soft-deleted
            (the row stays for audit, but it disappears from the catalog).
          </p>
        )}

        {!loading && report && !canDelete && (
          <>
            <p className="mt-2 text-xs text-amber-300">
              Cannot delete — this part is referenced by{' '}
              <strong>{report.total_references}</strong>{' '}
              {report.total_references === 1 ? 'entity' : 'entities'}
              {report.projects.length > 0
                ? ` across ${report.projects.length} project${report.projects.length === 1 ? '' : 's'}`
                : ''}
              . Remove the references first, then retry.
            </p>

            {report.projects.length > 0 && (
              <div className="mt-3 max-h-64 overflow-auto rounded-lg border border-astra-border">
                <table className="w-full text-[11px]">
                  <thead className="bg-astra-surface-alt text-slate-500">
                    <tr>
                      <th className="px-2 py-1 text-left font-semibold">Project</th>
                      <th className="px-2 py-1 text-right font-semibold">BOM lines</th>
                      <th className="px-2 py-1 text-right font-semibold">Joints</th>
                      <th className="px-2 py-1 text-right font-semibold">Units</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.projects.map((p) => (
                      <tr key={p.project_id} className="border-t border-astra-border/40">
                        <td className="px-2 py-1 text-slate-300">
                          {p.project_code ? <span className="font-mono mr-1">{p.project_code}</span> : null}
                          {p.project_name || `project ${p.project_id}`}
                        </td>
                        <td className="px-2 py-1 text-right text-slate-300">{p.project_part_count}</td>
                        <td className="px-2 py-1 text-right text-slate-300">{p.mechanical_joint_count}</td>
                        <td className="px-2 py-1 text-right text-slate-300">{p.unit_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

          </>
        )}

        {error && (
          <div role="alert" className="mt-3 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-[11px] text-red-400">
            {error}
          </div>
        )}

        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={deleting}
            className="rounded-lg border border-astra-border px-4 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200 disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={deleting || loading || !canDelete}
            className="flex items-center gap-1.5 rounded-lg bg-red-500 px-4 py-2 text-xs font-semibold text-white outline-none focus:ring-2 focus:ring-red-500/40 hover:bg-red-600 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {deleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : null}
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}
