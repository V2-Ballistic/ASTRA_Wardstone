'use client';

/**
 * ASTRA — Edit Mass modal for catalog parts.
 * CADPORT-TDD-STEP-001 §7.2.
 *
 * Opens on a part-detail page next to the displayed mass when the row
 * is STEP-sourced or material-derived. SolidWorks-imported rows
 * (source_format='sldprt', mass_source='cad') don't get the affordance
 * — their mass is owned upstream by SW. The backend returns 409 if
 * one of those slips through.
 *
 * Three actions:
 *   * Save & Recalculate — sets a new positive mass and triggers the
 *     linear inertia scaling identity on the server. CG stays the same
 *     (it's geometric). Any assemblies that contain the part also
 *     re-roll up.
 *   * Clear mass — sends mass_kg=null, returning the row to the
 *     geometric-only state ("back to skip").
 *   * Cancel — closes without saving.
 *
 * Pattern: plain JSX overlay + useState — matches the modal style
 * used elsewhere in the catalog UI (no Dialog primitive, no toast
 * library; inline error alerts).
 */

import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Calculator, Loader2, X } from 'lucide-react';

import { catalogAPI } from '@/lib/catalog-api';
import { formatApiError } from '@/lib/errors';
import type {
  CatalogPartDetail,
  CatalogPartMassUpdateResult,
} from '@/lib/catalog-types';

type Props = {
  part: CatalogPartDetail;
  onClose: () => void;
  onSaved: (result: CatalogPartMassUpdateResult) => void;
};

function massSourceLabel(part: CatalogPartDetail): string {
  const ms = part.mass_source ?? 'cad';
  if (ms === 'material') {
    return part.step_material_key
      ? `computed from material: ${part.step_material_key}`
      : 'computed from material';
  }
  if (ms === 'user_override') {
    return 'user override';
  }
  return part.source_format === 'step' ? 'no mass set' : 'from SolidWorks';
}

function fmtMass(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === '') return '—';
  const n = typeof v === 'string' ? Number(v) : v;
  if (Number.isNaN(n)) return '—';
  return `${n.toFixed(3)} kg`;
}

export function EditMassModal({ part, onClose, onSaved }: Props) {
  const initial = useMemo(() => {
    if (part.mass_kg === null || part.mass_kg === undefined || part.mass_kg === '') {
      return '';
    }
    const n = typeof part.mass_kg === 'string' ? Number(part.mass_kg) : part.mass_kg;
    return Number.isFinite(n) ? String(n) : '';
  }, [part.mass_kg]);
  const [value, setValue] = useState(initial);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [confirmClear, setConfirmClear] = useState(false);

  // ESC closes when not submitting.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !submitting) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, submitting]);

  const handleSave = async () => {
    const n = Number(value);
    if (!Number.isFinite(n) || n <= 0) {
      setError('Enter a positive mass in kilograms.');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const r = await catalogAPI.updatePartMass(part.id, n);
      onSaved(r.data);
      onClose();
    } catch (e) {
      setError(formatApiError(e, 'Failed to update mass'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleClear = async () => {
    if (!confirmClear) {
      setConfirmClear(true);
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const r = await catalogAPI.updatePartMass(part.id, null);
      onSaved(r.data);
      onClose();
    } catch (e) {
      setError(formatApiError(e, 'Failed to clear mass'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={() => !submitting && onClose()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="edit-mass-title"
    >
      <section
        className="w-full max-w-md rounded-xl border border-astra-border bg-astra-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-astra-border px-4 py-3">
          <div className="flex flex-col">
            <span id="edit-mass-title" className="text-sm font-semibold text-slate-100">
              Edit mass for {part.part_number}
            </span>
            <span className="font-mono text-[10px] uppercase tracking-wider text-slate-500">
              CADPORT-TDD-STEP-001 §7.2
            </span>
          </div>
          <button
            type="button"
            onClick={() => !submitting && onClose()}
            disabled={submitting}
            className="text-slate-500 hover:text-slate-300 disabled:cursor-not-allowed"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="space-y-3 px-4 py-4 text-xs text-slate-300">
          <div className="rounded-lg border border-astra-border bg-astra-bg p-3">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">
              Current mass
            </div>
            <div className="mt-1 font-mono text-slate-100">{fmtMass(part.mass_kg)}</div>
            <div className="mt-0.5 font-mono text-[10px] text-slate-500">
              ({massSourceLabel(part)})
            </div>
          </div>

          <label className="block">
            <span className="mb-1 block text-[10px] uppercase tracking-wider text-slate-500">
              New mass (kilograms)
            </span>
            <input
              type="number"
              min="0"
              step="any"
              value={value}
              onChange={(e) => {
                setValue(e.target.value);
                setError('');
                setConfirmClear(false);
              }}
              disabled={submitting}
              autoFocus
              className="w-full rounded-md border border-astra-border bg-astra-bg px-3 py-2 font-mono text-sm text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="kg"
            />
          </label>

          <div className="rounded-lg border border-blue-500/20 bg-blue-500/5 px-3 py-2 text-[11px] text-slate-300">
            <div className="mb-1 flex items-center gap-1 font-semibold text-blue-400">
              <Calculator className="h-3 w-3" aria-hidden="true" />
              When you save
            </div>
            <ul className="list-inside list-disc space-y-0.5 text-slate-400">
              <li>The part&apos;s inertia tensor is recomputed (mass-scaled against the geometry).</li>
              <li>The CG stays the same — it&apos;s geometric.</li>
              <li>Any assemblies that contain this part re-roll up.</li>
              <li>Mass source becomes <span className="font-mono">user_override</span> (the material link is dropped).</li>
            </ul>
          </div>

          {error && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400"
            >
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
              <span>{error}</span>
            </div>
          )}

          {confirmClear && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-300">
              Clear mass? This drops mass, inertia, and the material link
              and resets mass_source to <span className="font-mono">cad</span>.
              Geometry is preserved. Click Clear mass again to confirm.
            </div>
          )}
        </div>

        <footer className="flex justify-end gap-2 border-t border-astra-border bg-astra-bg/60 px-4 py-3">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded-md border border-astra-border px-3 py-1.5 text-xs text-slate-300 hover:bg-astra-bg disabled:cursor-not-allowed disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleClear}
            disabled={submitting}
            className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-300 hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {confirmClear ? 'Confirm Clear' : 'Clear mass'}
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={submitting || !value}
            className="flex items-center gap-1.5 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting && <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />}
            Save &amp; Recalculate
          </button>
        </footer>
      </section>
    </div>
  );
}

export function shouldShowEditMass(part: CatalogPartDetail): boolean {
  const sf = part.source_format ?? 'sldprt';
  const ms = part.mass_source ?? 'cad';
  if (sf === 'step') return true;
  if (ms === 'material' || ms === 'user_override') return true;
  return false;
}
