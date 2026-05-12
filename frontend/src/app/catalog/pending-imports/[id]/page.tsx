'use client';

/**
 * ASTRA — Pending Catalog Import — Review Page (TDD-CAT-002 §4.4)
 * ================================================================
 * Handles BOTH STEP-derived AND ICD-derived imports — they share the
 * same `pending_catalog_imports` table. The page is intentionally
 * minimal: a key-value editor for `extracted_data`, an Approve button
 * that promotes via the existing /catalog/pending-imports/{id}/approve
 * endpoint, and a Reject modal.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft, CheckCircle2, ChevronDown, Download, Loader2, ShieldCheck,
  XCircle,
} from 'lucide-react';
import clsx from 'clsx';

import { catalogAPI } from '@/lib/catalog-api';
import { formatApiError } from '@/lib/errors';
import type {
  PendingCatalogImport,
  Supplier,
  SupplierDocument,
} from '@/lib/catalog-types';

// React-hooks rule: ALL hooks before any conditional `return`. The few
// fields below are derived from `pendingImport`, which may be null
// during load — every read uses optional chaining.

type Confidence = 'high' | 'medium' | 'low';

const CONF_PILL: Record<Confidence | 'unknown', { bg: string; text: string; label: string }> = {
  high:    { bg: 'rgba(16,185,129,0.15)', text: '#10B981', label: 'High' },
  medium:  { bg: 'rgba(245,158,11,0.18)', text: '#F59E0B', label: 'Medium' },
  low:     { bg: 'rgba(239,68,68,0.20)',  text: '#F87171', label: 'Low' },
  unknown: { bg: 'rgba(100,116,139,0.18)', text: '#94A3B8', label: '—' },
};

// Fields surfaced as primary editor rows. Anything in `extracted_data`
// not listed here still appears under "Additional fields" below.
const PRIMARY_FIELDS: { key: string; label: string }[] = [
  { key: 'manufacturer',         label: 'Manufacturer' },
  { key: 'part_number',          label: 'Part Number (MPN)' },
  { key: 'name',                 label: 'Name' },
  { key: 'part_class',           label: 'Part Class' },
  { key: 'part_subtype',         label: 'Part Subtype' },
  { key: 'material_class',       label: 'Material Class' },
  { key: 'material_name',        label: 'Material Name' },
  { key: 'native_units',         label: 'Native Units' },
  { key: 'bbox_x_mm',            label: 'BBox X (mm)' },
  { key: 'bbox_y_mm',            label: 'BBox Y (mm)' },
  { key: 'bbox_z_mm',            label: 'BBox Z (mm)' },
  { key: 'volume_mm3',           label: 'Volume (mm³)' },
  { key: 'mass_kg',              label: 'Mass (kg)' },
  { key: 'cad_authoring_tool',   label: 'CAD Authoring Tool' },
  { key: 'schema',               label: 'STEP Schema' },
  { key: 'is_assembly',          label: 'Is Assembly' },
];

interface ExtractionLog {
  warnings?: string[];
  parser_version?: string;
  confidence_per_field?: Record<string, Confidence>;
  supplier_was_auto_created?: boolean;
}


export default function PendingImportReviewPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = Number(params?.id);

  // ── State ──
  const [pendingImport, setPendingImport] = useState<PendingCatalogImport | null>(null);
  const [supplier, setSupplier] = useState<Supplier | null>(null);
  const [sourceDoc, setSourceDoc] = useState<SupplierDocument | null>(null);
  const [edits, setEdits] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState<'approve' | 'reject' | 'save' | null>(null);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [warningsOpen, setWarningsOpen] = useState(false);

  // ── Loaders ──
  const refresh = useCallback(async () => {
    if (!Number.isFinite(id) || id <= 0) {
      setError('Invalid pending import id');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError('');
    try {
      const r = await catalogAPI.getPendingImport(id);
      setPendingImport(r.data);
      setEdits({});
      // Best-effort fetch of related supplier + source document
      try {
        const [supRes, docRes] = await Promise.all([
          catalogAPI.getSupplier(r.data.supplier_id),
          catalogAPI.getDocument(r.data.source_document_id),
        ]);
        setSupplier(supRes.data);
        setSourceDoc(docRes.data);
      } catch {
        // Non-fatal — banner falls back to the IDs.
      }
    } catch (e) {
      setError(formatApiError(e, 'Failed to load pending import'));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { refresh(); }, [refresh]);

  // ── Derived state (hooks before early return) ──
  const extracted = useMemo<Record<string, unknown>>(
    () => (pendingImport?.extracted_data as Record<string, unknown>) || {},
    [pendingImport?.extracted_data],
  );

  const merged = useMemo<Record<string, unknown>>(
    () => ({ ...extracted, ...edits }),
    [extracted, edits],
  );

  const confidenceMap = useMemo<Record<string, Confidence>>(() => {
    const log = (sourceDoc?.extraction_log as ExtractionLog | null) || null;
    return log?.confidence_per_field || {};
  }, [sourceDoc?.extraction_log]);

  const warnings = useMemo<string[]>(() => {
    const log = (sourceDoc?.extraction_log as ExtractionLog | null) || null;
    if (log?.warnings && Array.isArray(log.warnings)) return log.warnings;
    const piWarn = pendingImport?.extraction_warnings as { warnings?: string[] } | null;
    if (piWarn?.warnings && Array.isArray(piWarn.warnings)) return piWarn.warnings;
    return [];
  }, [sourceDoc?.extraction_log, pendingImport?.extraction_warnings]);

  const supplierWasAutoCreated = useMemo<boolean>(() => {
    const log = (sourceDoc?.extraction_log as ExtractionLog | null) || null;
    if (log?.supplier_was_auto_created) return true;
    const piWarn = pendingImport?.extraction_warnings as { supplier_was_auto_created?: boolean } | null;
    return Boolean(piWarn?.supplier_was_auto_created);
  }, [sourceDoc?.extraction_log, pendingImport?.extraction_warnings]);

  const additionalKeys = useMemo<string[]>(() => {
    const primary = new Set(PRIMARY_FIELDS.map((f) => f.key));
    primary.add('supplier');         // shown via the banner
    primary.add('original_filename'); // shown in source-doc panel
    primary.add('cad_translator');   // less-useful sibling of cad_authoring_tool
    primary.add('product_name');     // duplicates `name` for STEP imports
    primary.add('step_entity_id');   // internal
    return Object.keys(merged).filter((k) => !primary.has(k));
  }, [merged]);

  // ── Actions ──
  const setField = (key: string, raw: string) => {
    setEdits((prev) => ({ ...prev, [key]: raw === '' ? null : raw }));
  };

  const onSave = async () => {
    if (!pendingImport || Object.keys(edits).length === 0) return;
    setBusy('save');
    setError('');
    try {
      await catalogAPI.updatePendingImport(pendingImport.id, {
        extracted_data: merged,
      });
      await refresh();
    } catch (e) {
      setError(formatApiError(e, 'Save failed'));
    } finally {
      setBusy(null);
    }
  };

  const onApprove = async () => {
    if (!pendingImport) return;
    setBusy('approve');
    setError('');
    try {
      // If there are unsaved edits, persist first so the approve handler
      // re-validates the merged data, not the stale snapshot.
      if (Object.keys(edits).length > 0) {
        await catalogAPI.updatePendingImport(pendingImport.id, {
          extracted_data: merged,
        });
      }
      const r = await catalogAPI.approvePendingImport(pendingImport.id);
      router.push(`/catalog/parts/${r.data.id}`);
    } catch (e) {
      setError(formatApiError(e, 'Approve failed'));
      setBusy(null);
    }
  };

  const onReject = async () => {
    if (!pendingImport) return;
    setBusy('reject');
    setError('');
    try {
      await catalogAPI.rejectPendingImport(pendingImport.id, rejectReason || undefined);
      router.push('/catalog?tab=pending');
    } catch (e) {
      setError(formatApiError(e, 'Reject failed'));
      setBusy(null);
    }
  };

  // ── Loading / error fallback (after hooks) ──
  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-blue-500" aria-label="Loading" />
      </div>
    );
  }
  if (!pendingImport) {
    return (
      <div className="mx-auto max-w-3xl">
        <button
          type="button"
          onClick={() => router.push('/catalog')}
          className="mb-4 flex items-center gap-2 text-sm text-slate-500 hover:text-slate-200"
        >
          <ArrowLeft className="h-4 w-4" /> Back to Catalog
        </button>
        <div role="alert" className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
          {error || 'Pending import not found'}
        </div>
      </div>
    );
  }

  const isPending = pendingImport.status === 'pending';
  const supplierBanner = supplier && supplier.is_in_house
    ? { tone: 'emerald', label: `Linked to in-house supplier ${supplier.name}.` }
    : supplierWasAutoCreated
      ? { tone: 'blue', label: `Auto-created and linked to new supplier ${supplier?.name ?? '?'}.` }
      : { tone: 'blue', label: `Linked to supplier ${supplier?.name ?? `#${pendingImport.supplier_id}`}.` };

  return (
    <div className="mx-auto max-w-5xl">
      {/* ── Top bar ── */}
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => router.push('/catalog?tab=pending')}
            aria-label="Back to pending imports"
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-astra-border text-slate-400 transition hover:text-slate-200"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div>
            <p className="text-[11px] uppercase tracking-wider text-slate-500">
              Catalog · Pending Imports
            </p>
            <h1 className="text-xl font-bold tracking-tight text-slate-100">
              Pending Import #{pendingImport.id}
            </h1>
          </div>
          <span
            className={clsx(
              'rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider',
              pendingImport.status === 'pending' && 'bg-amber-500/15 text-amber-400',
              pendingImport.status === 'approved' && 'bg-emerald-500/15 text-emerald-400',
              pendingImport.status === 'rejected' && 'bg-red-500/15 text-red-400',
              pendingImport.status === 'superseded' && 'bg-slate-500/15 text-slate-400',
            )}
          >
            {pendingImport.status}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setRejectOpen(true)}
            disabled={!isPending || busy !== null}
            className="flex items-center gap-1.5 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs font-semibold text-red-300 hover:bg-red-500/20 disabled:opacity-40"
          >
            <XCircle className="h-3.5 w-3.5" aria-hidden="true" /> Reject
          </button>
          <button
            type="button"
            onClick={onApprove}
            disabled={!isPending || busy !== null}
            className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-blue-600 to-violet-600 px-3 py-2 text-xs font-semibold text-white hover:from-blue-500 hover:to-violet-500 disabled:opacity-40"
          >
            {busy === 'approve'
              ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              : <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />}
            Approve & Create Part
          </button>
        </div>
      </div>

      {/* ── Supplier banner ── */}
      <div
        className={clsx(
          'mb-4 rounded-xl border px-4 py-2.5 text-xs flex items-center gap-2',
          supplierBanner.tone === 'emerald'
            ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
            : 'border-blue-500/30 bg-blue-500/10 text-blue-200',
        )}
      >
        <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
        <span>{supplierBanner.label}</span>
      </div>

      {error && (
        <div role="alert" className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
          {error}
        </div>
      )}

      {/* ── Extracted-data editor ── */}
      <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-bold text-slate-100">Extracted data</h2>
          <button
            type="button"
            onClick={onSave}
            disabled={!isPending || busy !== null || Object.keys(edits).length === 0}
            className="rounded-lg border border-astra-border px-3 py-1.5 text-[11px] font-semibold text-slate-300 hover:border-blue-500/30 disabled:opacity-40"
          >
            {busy === 'save' ? 'Saving…' : 'Save edits'}
          </button>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          {PRIMARY_FIELDS.map(({ key, label }) => {
            const conf = (confidenceMap[key] || 'unknown') as Confidence | 'unknown';
            const pill = CONF_PILL[conf];
            const value = merged[key];
            const display = value === null || value === undefined
              ? ''
              : typeof value === 'boolean'
                ? String(value)
                : typeof value === 'object'
                  ? JSON.stringify(value)
                  : String(value);
            return (
              <div key={key} className="rounded-lg border border-astra-border bg-astra-bg p-3">
                <div className="mb-1.5 flex items-center justify-between">
                  <label htmlFor={`pi-${key}`} className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                    {label}
                  </label>
                  <span
                    className="rounded-full px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide"
                    style={{ background: pill.bg, color: pill.text }}
                  >
                    {pill.label}
                  </span>
                </div>
                <input
                  id={`pi-${key}`}
                  type="text"
                  value={display}
                  onChange={(e) => setField(key, e.target.value)}
                  disabled={!isPending}
                  className="w-full rounded border border-astra-border bg-astra-surface-alt px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-blue-500/50 disabled:opacity-60"
                />
              </div>
            );
          })}
        </div>

        {additionalKeys.length > 0 && (
          <details className="mt-4">
            <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-wide text-slate-500 hover:text-slate-300">
              Additional fields ({additionalKeys.length})
            </summary>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              {additionalKeys.map((key) => {
                const value = merged[key];
                const display = value === null || value === undefined
                  ? ''
                  : typeof value === 'object'
                    ? JSON.stringify(value)
                    : String(value);
                return (
                  <div key={key} className="rounded-lg border border-astra-border bg-astra-bg p-3">
                    <label htmlFor={`pi-add-${key}`} className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                      {key}
                    </label>
                    <input
                      id={`pi-add-${key}`}
                      type="text"
                      value={display}
                      onChange={(e) => setField(key, e.target.value)}
                      disabled={!isPending}
                      className="w-full rounded border border-astra-border bg-astra-surface-alt px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-blue-500/50 disabled:opacity-60"
                    />
                  </div>
                );
              })}
            </div>
          </details>
        )}
      </div>

      {/* ── Source document ── */}
      {sourceDoc && (
        <div className="mt-4 rounded-xl border border-astra-border bg-astra-surface p-5">
          <h3 className="mb-3 text-sm font-bold text-slate-100">Source document</h3>
          <dl className="grid gap-2 text-xs sm:grid-cols-2">
            <div>
              <dt className="text-[10px] uppercase text-slate-500">Filename</dt>
              <dd className="text-slate-200 truncate">{sourceDoc.title}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase text-slate-500">Size</dt>
              <dd className="text-slate-200">{sourceDoc.file_size_bytes.toLocaleString()} bytes</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase text-slate-500">SHA-256</dt>
              <dd className="font-mono text-slate-300">{sourceDoc.sha256.slice(0, 16)}…</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase text-slate-500">MIME</dt>
              <dd className="text-slate-300">{sourceDoc.mime_type}</dd>
            </div>
          </dl>
          <a
            href={`/api/v1/catalog/documents/${sourceDoc.id}/file`}
            className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-astra-border px-3 py-1.5 text-[11px] font-semibold text-slate-300 hover:border-blue-500/30"
          >
            <Download className="h-3.5 w-3.5" aria-hidden="true" /> Download original
          </a>
        </div>
      )}

      {/* ── Extraction warnings ── */}
      {warnings.length > 0 && (
        <div className="mt-4 rounded-xl border border-astra-border bg-astra-surface p-5">
          <button
            type="button"
            onClick={() => setWarningsOpen((v) => !v)}
            className="flex w-full items-center justify-between text-left"
            aria-expanded={warningsOpen}
          >
            <h3 className="text-sm font-bold text-slate-100">
              Extraction warnings ({warnings.length})
            </h3>
            <ChevronDown
              className={clsx('h-4 w-4 text-slate-500 transition-transform', warningsOpen && 'rotate-180')}
              aria-hidden="true"
            />
          </button>
          {warningsOpen && (
            <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-amber-300">
              {warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          )}
        </div>
      )}

      {/* ── Reject modal ── */}
      {rejectOpen && (
        <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="rounded-xl border border-astra-border bg-astra-surface p-5 max-w-md mx-4 w-full">
            <h2 className="text-sm font-bold text-slate-100">Reject pending import</h2>
            <p className="mt-1 text-xs text-slate-400">
              Optional: tell the audit log why this import was rejected.
            </p>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              rows={3}
              maxLength={2000}
              placeholder="e.g. wrong file uploaded; supplier name corrupted in filename"
              className="mt-3 w-full rounded-lg border border-astra-border bg-astra-surface-alt px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-blue-500/50"
            />
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => { setRejectOpen(false); setRejectReason(''); }}
                disabled={busy !== null}
                className="rounded-lg border border-astra-border px-3 py-1.5 text-[11px] font-semibold text-slate-300 hover:border-blue-500/30"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={onReject}
                disabled={busy !== null}
                className="flex items-center gap-1.5 rounded-lg bg-red-600 px-3 py-1.5 text-[11px] font-semibold text-white hover:bg-red-500 disabled:opacity-50"
              >
                {busy === 'reject' ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : null}
                Reject
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
