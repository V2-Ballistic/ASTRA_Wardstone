'use client';
import { useEffect, useState, use } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { partsLibraryAPI } from '@/lib/parts-api';
import type { ConfidenceLevel, PendingPartsImportResponse } from '@/lib/parts-types';
import { PART_TYPE_LABELS } from '@/lib/parts-types';

const CONFIDENCE_COLORS: Record<ConfidenceLevel, string> = {
  high: 'bg-green-100 text-green-800',
  medium: 'bg-amber-100 text-amber-800',
  low: 'bg-red-100 text-red-800',
};

export default function PendingImportDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const router = useRouter();
  const { id } = use(params);
  const importId = parseInt(id, 10);

  const [imp, setImp] = useState<PendingPartsImportResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [edited, setEdited] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [showReject, setShowReject] = useState(false);

  useEffect(() => {
    if (Number.isNaN(importId)) return;
    setLoading(true);
    partsLibraryAPI
      .getPendingImport(importId)
      .then((res) => {
        setImp(res.data);
        const initial: Record<string, string> = {};
        Object.entries(res.data.proposed_data).forEach(([k, v]) => {
          initial[k] = v == null ? '' : String(v);
        });
        setEdited(initial);
        setError(null);
      })
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load'))
      .finally(() => setLoading(false));
  }, [importId]);

  if (loading) return <div className="container mx-auto p-6 text-sm">Loading…</div>;
  if (error) return <div className="container mx-auto p-6 text-sm text-red-700">{error}</div>;
  if (!imp) return null;

  const fieldOrder = [
    'name', 'part_type', 'description',
    'manufacturer_part_number', 'manufacturer_name',
    'thread_size', 'thread_standard', 'nominal_diameter_mm', 'nominal_length_mm',
    'bounding_box_x_mm', 'bounding_box_y_mm', 'bounding_box_z_mm',
    'volume_mm3', 'mass_nominal_g',
    'material_name', 'material_class',
    'torque_nominal_nm', 'torque_min_nm', 'torque_max_nm',
    'locking_feature',
  ];
  const knownKeys = new Set(fieldOrder);
  const extraKeys = Object.keys(imp.proposed_data).filter((k) => !knownKeys.has(k));
  const allKeys = [...fieldOrder, ...extraKeys];

  const onApprove = async () => {
    if (!imp) return;
    if (!edited.name?.trim()) {
      setError('Name is required.');
      return;
    }
    if (!edited.part_type?.trim()) {
      setError('Part type is required.');
      return;
    }
    setSubmitting(true);
    try {
      // Build override dict only with fields that differ from proposed_data
      const overrides: Record<string, unknown> = {};
      Object.entries(edited).forEach(([k, v]) => {
        const original = imp.proposed_data[k];
        const originalStr = original == null ? '' : String(original);
        if (v !== originalStr && v.trim() !== '') {
          overrides[k] = v;
        }
      });
      const res = await partsLibraryAPI.approveImport(imp.id, overrides);
      router.push(`/parts-library/${res.data.id}`);
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: { detail?: string } | string } } };
      const detail = ax?.response?.data?.detail;
      const message = typeof detail === 'string'
        ? detail
        : (detail as { detail?: string })?.detail || 'Approval failed';
      setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  const onReject = async () => {
    if (!rejectReason.trim()) return;
    setSubmitting(true);
    try {
      await partsLibraryAPI.rejectImport(imp.id, rejectReason);
      router.push('/parts-library/pending-imports');
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } } };
      setError(ax?.response?.data?.detail || 'Reject failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="container mx-auto p-6">
      <Link
        href="/parts-library/pending-imports"
        className="text-xs text-blue-600 hover:underline"
      >
        ← Pending Imports
      </Link>
      <div className="flex justify-between items-start mt-2 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Review Import #{imp.id}
          </h1>
          <p className="text-sm text-gray-500">Status: {imp.status}</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowReject(true)}
            disabled={submitting || imp.status !== 'pending' && imp.status !== 'under_review'}
            className="px-3 py-1.5 text-sm border border-red-300 text-red-700 rounded hover:bg-red-50 disabled:opacity-50"
          >
            Reject
          </button>
          <button
            onClick={onApprove}
            disabled={submitting || (imp.status !== 'pending' && imp.status !== 'under_review')}
            className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded disabled:opacity-50"
          >
            {submitting ? 'Approving...' : 'Approve and Assign WPN'}
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 rounded text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-6">
        <div className="border border-dashed border-gray-300 dark:border-gray-700 rounded p-8 text-center text-sm text-gray-500">
          3D preview available after Phase 4 (pythonOCC tessellation).
          {imp.parser_version && (
            <p className="mt-2 text-xs">Parser version: {imp.parser_version}</p>
          )}
        </div>

        <div className="space-y-2">
          <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
            Extracted Fields
          </h2>
          {allKeys.map((key) => {
            const conf = imp.confidence_scores?.[key];
            const isLow = imp.low_confidence_fields?.includes(key);
            const isRequired = key === 'name' || key === 'part_type';
            return (
              <div key={key} className="grid grid-cols-3 gap-2 items-center">
                <label className="text-xs text-gray-500 dark:text-gray-400 col-span-1">
                  {key}{isRequired && <span className="text-red-500">*</span>}
                </label>
                <div className="col-span-2 flex items-center gap-2">
                  {key === 'part_type' ? (
                    <select
                      value={edited[key] || ''}
                      onChange={(e) =>
                        setEdited((prev) => ({ ...prev, [key]: e.target.value }))
                      }
                      className={
                        `flex-1 px-2 py-1 text-sm border rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-white ` +
                        (isLow ? 'border-amber-400' : 'border-gray-300 dark:border-gray-600')
                      }
                    >
                      <option value="">— select —</option>
                      {Object.entries(PART_TYPE_LABELS).map(([k, v]) => (
                        <option key={k} value={k}>{v}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="text"
                      value={edited[key] || ''}
                      onChange={(e) =>
                        setEdited((prev) => ({ ...prev, [key]: e.target.value }))
                      }
                      className={
                        `flex-1 px-2 py-1 text-sm border rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-white ` +
                        (isLow ? 'border-amber-400' : 'border-gray-300 dark:border-gray-600')
                      }
                    />
                  )}
                  {conf && (
                    <span className={`text-xs px-2 py-0.5 rounded ${CONFIDENCE_COLORS[conf]}`}>
                      {conf}
                    </span>
                  )}
                </div>
              </div>
            );
          })}

          {imp.extraction_log && (
            <details className="mt-4 text-xs text-gray-500">
              <summary className="cursor-pointer">Extraction log</summary>
              <pre className="mt-1 p-2 bg-gray-50 dark:bg-gray-800 rounded whitespace-pre-wrap text-[10px]">
                {imp.extraction_log}
              </pre>
            </details>
          )}
        </div>
      </div>

      {showReject && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
            <h2 className="text-lg font-semibold mb-2 text-gray-900 dark:text-white">
              Reject this import?
            </h2>
            <p className="text-sm text-gray-500 mb-3">Provide a reason for the audit log:</p>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              className="w-full p-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
              rows={4}
              placeholder="e.g. Geometry does not match the drawing"
            />
            <div className="mt-3 flex justify-end gap-2">
              <button
                onClick={() => setShowReject(false)}
                className="px-3 py-1.5 text-sm rounded border border-gray-300 dark:border-gray-600"
              >
                Cancel
              </button>
              <button
                onClick={onReject}
                disabled={submitting || !rejectReason.trim()}
                className="px-3 py-1.5 text-sm bg-red-600 text-white rounded disabled:opacity-50"
              >
                {submitting ? 'Rejecting…' : 'Confirm reject'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
