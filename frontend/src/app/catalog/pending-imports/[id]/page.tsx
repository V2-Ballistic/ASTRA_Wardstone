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
  XCircle, Hash, AlertTriangle, Trash2,
} from 'lucide-react';
import ConfirmDialog from '@/components/ConfirmDialog';
import clsx from 'clsx';

import { catalogAPI } from '@/lib/catalog-api';
import { haroldAPI } from '@/lib/harold-api';
import { formatApiError } from '@/lib/errors';
import {
  WPN_PATTERN,
  looksLikeWardstoneWpn,
  type WpnValidationResult,
} from '@/lib/harold-types';
import type {
  PendingCatalogImport,
  Supplier,
  SupplierDocument,
} from '@/lib/catalog-types';
import { CadportPendingSummary } from './CadportPendingSummary';

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
  const [busy, setBusy] = useState<'approve' | 'reject' | 'save' | 'delete' | null>(null);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [warningsOpen, setWarningsOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  // ── WPN section state ──
  // ``wpnInput`` is what the operator typed (drives extracted_data.user_supplied_wpn).
  // Empty = "let the backend auto-allocate" (AD-11 fall-through path).
  // ``wpnValidation`` is the most recent /harold/validate result.
  const [wpnInput, setWpnInput] = useState('');
  const [wpnValidating, setWpnValidating] = useState(false);
  const [wpnValidation, setWpnValidation] = useState<WpnValidationResult | null>(null);
  const [wpnValidationError, setWpnValidationError] = useState<string | null>(null);

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
      const ext = (r.data.extracted_data as Record<string, unknown>) || {};
      const seedWpn = (ext.user_supplied_wpn ?? '') as string;
      setWpnInput(typeof seedWpn === 'string' ? seedWpn : '');
      setWpnValidation(null);
      setWpnValidationError(null);
      // Best-effort fetch of related supplier + source document.
      // CADPORT-TDD-ASTRA-BRIDGE-001 Phase 1: supplier_id is nullable
      // for CADPORT-created pending rows (the supplier is materialized
      // at approve time); fetching only fires when it's set.
      try {
        const docRes = await catalogAPI.getDocument(r.data.source_document_id);
        setSourceDoc(docRes.data);
        if (r.data.supplier_id != null) {
          const supRes = await catalogAPI.getSupplier(r.data.supplier_id);
          setSupplier(supRes.data);
        } else {
          setSupplier(null);
        }
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
    // HAROLD WPN metadata is surfaced in its own dedicated section.
    primary.add('proposed_wpn');
    primary.add('wpn_source');
    primary.add('wpn_system_code');
    primary.add('wpn_suggestion_reason');
    primary.add('filename_wpn');
    primary.add('user_supplied_wpn');
    return Object.keys(merged).filter((k) => !primary.has(k));
  }, [merged]);

  // ── WPN derived facts (from upload-time HAROLD suggest/filename calls) ──
  const proposedWpn   = typeof merged.proposed_wpn          === 'string' ? merged.proposed_wpn          : null;
  const wpnSource     = typeof merged.wpn_source            === 'string' ? merged.wpn_source            : null;
  const wpnSystemCode = typeof merged.wpn_system_code       === 'string' ? merged.wpn_system_code       : null;
  const wpnReason     = typeof merged.wpn_suggestion_reason === 'string' ? merged.wpn_suggestion_reason : null;
  const filenameWpn   = typeof merged.filename_wpn          === 'string' ? merged.filename_wpn          : null;

  // ── Actions ──
  const setField = (key: string, raw: string) => {
    setEdits((prev) => ({ ...prev, [key]: raw === '' ? null : raw }));
  };

  // Whenever the operator types in the WPN box, mirror the value into
  // ``edits.user_supplied_wpn`` so it persists alongside the rest of
  // the merged extracted_data on save/approve. Empty string → null
  // (AD-11 auto-allocate path).
  const onWpnInputChange = (raw: string) => {
    const upper = raw.toUpperCase();
    setWpnInput(upper);
    setEdits((prev) => ({
      ...prev,
      user_supplied_wpn: upper.trim() === '' ? null : upper.trim(),
    }));
    // Clear stale validation; user must blur to re-run.
    if (wpnValidation || wpnValidationError) {
      setWpnValidation(null);
      setWpnValidationError(null);
    }
  };

  // On blur — if the input looks like a Wardstone WPN, ask HAROLD.
  // Empty input is intentionally NOT validated (auto-allocate path).
  const onWpnBlur = async () => {
    const v = wpnInput.trim();
    if (!v) {
      setWpnValidation(null);
      setWpnValidationError(null);
      return;
    }
    setWpnValidating(true);
    setWpnValidationError(null);
    try {
      const r = await haroldAPI.validate(v);
      if (r.data.harold_available) {
        setWpnValidation(r.data.data);
      } else {
        setWpnValidation(null);
        setWpnValidationError(r.data.reason || 'HAROLD unavailable');
      }
    } catch (e) {
      setWpnValidation(null);
      setWpnValidationError(formatApiError(e, 'WPN validation failed'));
    } finally {
      setWpnValidating(false);
    }
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

  // CLEANUP-002 Phase 4 (AD-6) — hard-delete the pending import.
  // Distinct from Reject: Reject keeps the row at status=rejected for
  // audit; Delete removes it entirely and cascade-removes the linked
  // supplier_document iff no other live reference holds it.
  const onDelete = async () => {
    if (!pendingImport) return;
    setBusy('delete');
    setError('');
    try {
      await catalogAPI.deletePendingImport(pendingImport.id);
      router.push('/catalog/pending-imports');
    } catch (e) {
      setError(formatApiError(e, 'Delete failed'));
      setBusy(null);
      setDeleteOpen(false);
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
  const supplierBanner =
    pendingImport.supplier_id == null
      ? {
          tone: 'blue' as const,
          label:
            pendingImport.proposed_supplier_name
              ? `Proposed supplier: "${pendingImport.proposed_supplier_name}" — will be created on approval.`
              : 'No supplier set yet — pick one before approving.',
        }
      : supplier && supplier.is_in_house
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
          {/* CLEANUP-002 Phase 4 (AD-6) — hard-delete is available
              regardless of status (pending/rejected/etc.). Audit row
              is emitted server-side. */}
          <button
            type="button"
            onClick={() => setDeleteOpen(true)}
            disabled={busy !== null}
            title="Hard-delete this pending import"
            className="flex items-center gap-1.5 rounded-lg border border-slate-500/30 bg-slate-500/10 px-3 py-2 text-xs font-semibold text-slate-300 hover:bg-red-500/20 hover:text-red-300 disabled:opacity-40"
          >
            {busy === 'delete'
              ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              : <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />}
            Delete
          </button>
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

      {/* CADPORT-TDD-ASTRA-BRIDGE-001 Phase 1: CADPORT extraction
          summary + editable proposed-supplier-name field. Only renders
          when the row came from the CADPORT bridge — leaves the PDF
          flow's UI untouched. */}
      {pendingImport.source_kind === 'cadport' && (
        <CadportPendingSummary
          row={pendingImport}
          onSupplierUpdated={refresh}
          setError={setError}
        />
      )}

      {error && (
        <div role="alert" className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
          {error}
        </div>
      )}

      {/* ── HAROLD WPN section (TDD-HAROLD-INT-002 Phase 4) ──
            Surfaces the proposed WPN minted at upload time and lets the
            operator override it. Empty input → backend auto-allocates
            on approve (AD-11 fall-through). A typed value drives the
            issue-specific path. */}
      <div className="mb-4 rounded-xl border border-astra-border bg-astra-surface p-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-bold text-slate-100">
            <Hash className="h-3.5 w-3.5 text-blue-400" aria-hidden="true" />
            Wardstone Part Number (WPN)
          </h2>
          <div className="flex items-center gap-1.5">
            {wpnSystemCode && (
              <span className="rounded-full bg-slate-700/40 px-2 py-0.5 font-mono text-[10px] font-semibold text-slate-200">
                {wpnSystemCode}
              </span>
            )}
            {wpnSource && (
              <span
                className={clsx(
                  'rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider',
                  wpnSource === 'harold'      && 'bg-emerald-500/15 text-emerald-300',
                  wpnSource === 'fallback'    && 'bg-amber-500/15  text-amber-300',
                  wpnSource === 'unavailable' && 'bg-slate-500/15  text-slate-400',
                )}
              >
                {wpnSource}
              </span>
            )}
          </div>
        </div>

        {(proposedWpn || filenameWpn) && (
          <p className="mb-2 text-[11px] text-slate-400">
            {proposedWpn && (
              <>Suggested:{' '}
                <span className="font-mono text-slate-200">{proposedWpn}</span>
                {wpnReason && <span className="text-slate-500"> · {wpnReason}</span>}
              </>
            )}
            {filenameWpn && (
              <>{proposedWpn ? ' · ' : ''}
                Filename: <span className="font-mono text-slate-200">{filenameWpn}</span>
              </>
            )}
          </p>
        )}

        <label htmlFor="pi-wpn" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          Override / commit WPN
        </label>
        <div className="flex items-center gap-2">
          <input
            id="pi-wpn"
            type="text"
            value={wpnInput}
            onChange={(e) => onWpnInputChange(e.target.value)}
            onBlur={onWpnBlur}
            disabled={!isPending}
            placeholder={proposedWpn || 'WS-XX-PNNNNNN-A'}
            className="w-72 rounded-lg border border-astra-border bg-astra-bg px-3 py-2 font-mono text-sm tracking-wider text-slate-200 outline-none focus:border-blue-500/50 disabled:opacity-60"
            spellCheck={false}
            pattern={WPN_PATTERN.source}
          />
          {wpnValidating && <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-400" aria-label="Validating" />}
          {!wpnValidating && wpnInput.trim() !== '' && !looksLikeWardstoneWpn(wpnInput) && (
            <span className="flex items-center gap-1 text-[11px] text-amber-300">
              <AlertTriangle className="h-3 w-3" aria-hidden="true" /> Format check failed
            </span>
          )}
        </div>

        <p className="mt-1.5 text-[11px] text-slate-500">
          Leave blank to auto-allocate on approve (HAROLD if reachable, fallback otherwise).
          A typed value commits to the issue-specific path.
        </p>

        {wpnValidation && (
          <div className="mt-3 rounded-lg border border-astra-border bg-astra-bg p-3 text-xs">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-slate-200">{wpnValidation.wpn}</span>
              <span className={clsx(
                'rounded-full px-2 py-0.5 text-[10px] font-semibold',
                wpnValidation.is_valid_format
                  ? 'bg-emerald-500/15 text-emerald-300'
                  : 'bg-red-500/15 text-red-400',
              )}>
                {wpnValidation.is_valid_format ? 'format ok' : 'bad format'}
              </span>
              <span className={clsx(
                'rounded-full px-2 py-0.5 text-[10px] font-semibold',
                wpnValidation.is_issued
                  ? 'bg-amber-500/15 text-amber-300'
                  : 'bg-slate-500/15 text-slate-400',
              )}>
                {wpnValidation.is_issued ? 'already issued' : 'free'}
              </span>
            </div>
            {wpnValidation.errors.length > 0 && (
              <ul className="mt-2 list-disc space-y-0.5 pl-5 text-[11px] text-red-400">
                {wpnValidation.errors.map((m, i) => <li key={i}>{m}</li>)}
              </ul>
            )}
            {wpnValidation.warnings.length > 0 && (
              <ul className="mt-2 list-disc space-y-0.5 pl-5 text-[11px] text-amber-300">
                {wpnValidation.warnings.map((m, i) => <li key={i}>{m}</li>)}
              </ul>
            )}
          </div>
        )}

        {wpnValidationError && (
          <p className="mt-2 text-[11px] text-slate-400">
            HAROLD validate skipped: <span className="text-slate-500">{wpnValidationError}</span>
          </p>
        )}
      </div>

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

      {/* ── Delete confirmation (CLEANUP-002 Phase 4) ── */}
      <ConfirmDialog
        open={deleteOpen}
        title={`Hard-delete pending import #${pendingImport.id}?`}
        message="The row is removed permanently. The linked supplier_document is also deleted if no other pending import or live catalog_part references it. This action cannot be undone."
        confirmLabel={busy === 'delete' ? 'Deleting…' : 'Delete'}
        destructive
        onCancel={() => { if (busy !== 'delete') setDeleteOpen(false); }}
        onConfirm={onDelete}
      />

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
