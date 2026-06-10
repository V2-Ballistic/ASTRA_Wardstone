'use client';

/**
 * ASTRA — CADPORT pending-import summary section.
 * CADPORT-TDD-ASTRA-BRIDGE-001 Phase 1.
 *
 * Renders inside the standard pending-imports detail page when the
 * row's ``source_kind === 'cadport'``. Shows the CADPORT extraction
 * essentials (display name, source filename, mass/volume/density,
 * content hash, leaf_count) plus the editable supplier picker. The
 * existing approve button on the detail page calls the unchanged
 * ``/pending-imports/{id}/approve`` endpoint, which now branches on
 * ``source_kind`` and runs ``_approve_cadport_pending_import``.
 */

import { useState } from 'react';
import { Box, Layers, Loader2, Save } from 'lucide-react';

import { catalogAPI } from '@/lib/catalog-api';
import { formatApiError } from '@/lib/errors';
import type { PendingCatalogImport } from '@/lib/catalog-types';


type CadportExtracted = {
  display_name?: string;
  source_filename?: string;
  cadport_part_id?: string;
  content_hash?: string;
  internal_part_number?: string | null;
  material?: string | null;
  mass_kg?: number | null;
  volume_m3?: number | null;
  surface_area_m2?: number | null;
  density_kg_m3?: number | null;
  source_format?: string;
  mass_source?: string;
  leaf_count?: number | null;
  yaml_filename?: string | null;
};

export function CadportPendingSummary({
  row,
  onSupplierUpdated,
  setError,
}: {
  row: PendingCatalogImport;
  onSupplierUpdated: () => Promise<void>;
  setError: (e: string) => void;
}) {
  const ext = (row.extracted_data || {}) as CadportExtracted;
  const [proposed, setProposed] = useState(row.proposed_supplier_name ?? '');
  const [supplierId, setSupplierId] = useState<number | null>(row.supplier_id ?? null);
  const [saving, setSaving] = useState(false);

  const dirty =
    (proposed.trim() || null) !== (row.proposed_supplier_name ?? null) ||
    supplierId !== (row.supplier_id ?? null);

  const handleSave = async () => {
    setSaving(true);
    setError('');
    try {
      // Exactly-one rule: if proposed has a value, clear supplier_id;
      // if supplier_id is set, clear proposed. The operator picks one.
      const payload: Record<string, unknown> = {};
      const trimmed = proposed.trim();
      if (trimmed) {
        payload.proposed_supplier_name = trimmed;
        payload.supplier_id = null;
      } else if (supplierId != null) {
        payload.supplier_id = supplierId;
        payload.proposed_supplier_name = null;
      } else {
        setError('Pick an existing supplier or type a proposed name before saving.');
        setSaving(false);
        return;
      }
      await catalogAPI.updatePendingImport(row.id, payload as never);
      await onSupplierUpdated();
    } catch (e) {
      setError(formatApiError(e, 'Failed to save supplier choice'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="mb-4 rounded-xl border border-astra-border bg-astra-surface p-5">
      <div className="mb-3 flex items-center gap-2">
        <Box className="h-3.5 w-3.5 text-blue-400" aria-hidden="true" />
        <h2 className="text-sm font-bold text-slate-100">
          CADPORT extraction
        </h2>
        <span className="rounded-full bg-slate-700/40 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-slate-300">
          {ext.source_format || 'step'}
        </span>
        {(ext.leaf_count ?? 0) > 1 && (
          <span className="flex items-center gap-1 rounded-full bg-slate-700/40 px-2 py-0.5 font-mono text-[10px] text-slate-300">
            <Layers className="h-3 w-3" /> {ext.leaf_count} leaves
          </span>
        )}
      </div>

      <div className="mb-4 grid gap-3 lg:grid-cols-2">
        <Field label="Display name" value={ext.display_name ?? '—'} mono />
        <Field label="Source filename" value={ext.source_filename ?? '—'} mono />
        <Field label="WPN (proposed)" value={ext.internal_part_number ?? '—'} mono />
        <Field label="Material" value={ext.material ?? '—'} />
        <Field label="Mass (kg)" value={fmtNum(ext.mass_kg)} mono />
        <Field label="Volume (m³)" value={fmtSci(ext.volume_m3)} mono />
        <Field label="Density (kg/m³)" value={fmtNum(ext.density_kg_m3, 1)} mono />
        <Field label="Surface area (m²)" value={fmtNum(ext.surface_area_m2, 4)} mono />
        <Field
          label="Content hash"
          value={ext.content_hash ?? '—'}
          mono
          truncate
        />
        <Field label="cadport_part_id" value={ext.cadport_part_id ?? '—'} mono truncate />
      </div>

      <div className="rounded-lg border border-astra-border bg-astra-bg/60 p-4">
        <div className="mb-2 text-xs font-semibold text-slate-200">
          Proposed supplier (editable before approve)
        </div>
        <p className="mb-3 text-[11px] text-slate-400">
          Either pick an existing supplier id or type a new supplier name —
          the supplier row is materialized (or reused, case-insensitive)
          when you click Approve. Operator can change this before approving.
        </p>
        <div className="flex flex-col gap-2 lg:flex-row">
          <div className="flex-1">
            <label className="mb-1 block text-[10px] uppercase tracking-wider text-slate-500">
              Existing supplier id
            </label>
            <input
              type="number"
              min="0"
              value={supplierId ?? ''}
              onChange={(e) => {
                const v = e.target.value;
                setSupplierId(v === '' ? null : Number(v));
              }}
              className="w-full rounded-md border border-astra-border bg-astra-bg px-3 py-2 font-mono text-xs text-slate-100 focus:border-blue-500 focus:outline-none"
              placeholder="3"
            />
          </div>
          <div className="flex items-end px-2 text-[10px] uppercase text-slate-500">
            or
          </div>
          <div className="flex-[2]">
            <label className="mb-1 block text-[10px] uppercase tracking-wider text-slate-500">
              Proposed supplier name (create-on-approval)
            </label>
            <input
              type="text"
              value={proposed}
              onChange={(e) => setProposed(e.target.value)}
              className="w-full rounded-md border border-astra-border bg-astra-bg px-3 py-2 text-xs text-slate-100 focus:border-blue-500 focus:outline-none"
              placeholder="VectorNav"
            />
          </div>
          <div className="flex items-end">
            <button
              type="button"
              onClick={handleSave}
              disabled={saving || !dirty}
              className="flex items-center gap-1.5 rounded-md bg-blue-600 px-3 py-2 text-xs font-medium text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
              Save
            </button>
          </div>
        </div>
        <div className="mt-3 text-[10px] text-slate-500">
          Current: {row.supplier_id != null
            ? `existing supplier #${row.supplier_id}`
            : row.proposed_supplier_name
              ? `proposed "${row.proposed_supplier_name}" (will be created on approval)`
              : 'not set'}
        </div>
      </div>
    </section>
  );
}


function Field({
  label, value, mono, truncate,
}: { label: string; value: string; mono?: boolean; truncate?: boolean }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div
        className={[
          'text-xs text-slate-100',
          mono ? 'font-mono' : '',
          truncate ? 'truncate' : '',
        ].join(' ')}
        title={truncate ? value : undefined}
      >
        {value}
      </div>
    </div>
  );
}

function fmtNum(v: number | null | undefined, decimals = 3): string {
  if (v == null) return '—';
  const n = Number(v);
  if (!Number.isFinite(n)) return '—';
  return n.toFixed(decimals);
}

function fmtSci(v: number | null | undefined): string {
  if (v == null) return '—';
  const n = Number(v);
  if (!Number.isFinite(n)) return '—';
  return n.toExponential(4);
}
