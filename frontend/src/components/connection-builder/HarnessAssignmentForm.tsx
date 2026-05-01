'use client';

/**
 * ASTRA — Harness Assignment Form (INTF-002 Phase 4)
 * ====================================================
 * File: frontend/src/components/connection-builder/HarnessAssignmentForm.tsx
 *
 * Step 4 of the Connection Builder wizard. Captures harness-level metadata
 * (name, cable type, length, jacket color, shield type) before the commit
 * call. Pure controlled-component — no API calls.
 */

import { useState } from 'react';
import { Cable } from 'lucide-react';
import type { CbHarnessMetadata } from '@/lib/interface-types';

export interface HarnessAssignmentFormProps {
  initial?: Partial<CbHarnessMetadata>;
  onChange: (data: CbHarnessMetadata) => void;
}

const CABLE_TYPE_PRESETS = [
  'MIL-C-27500-22SD2T23',
  'MIL-DTL-22759/16-22-9',
  'MIL-DTL-83729',
  'BELDEN 9501',
  'AMP CO/AX',
  'Custom',
];

const JACKET_COLORS = [
  'black', 'gray', 'white', 'red', 'blue', 'green', 'yellow', 'orange',
];

const SHIELD_TYPES = [
  '', 'unshielded', 'foil', 'braid', 'foil_braid', 'spiral', 'served',
];

export default function HarnessAssignmentForm({
  initial,
  onChange,
}: HarnessAssignmentFormProps) {
  const [data, setData] = useState<CbHarnessMetadata>({
    name: initial?.name ?? '',
    cable_type: initial?.cable_type ?? '',
    overall_length_m: initial?.overall_length_m,
    jacket_color: initial?.jacket_color ?? '',
    shield_type: initial?.shield_type ?? '',
    description: initial?.description ?? '',
  });

  function update<K extends keyof CbHarnessMetadata>(
    key: K, value: CbHarnessMetadata[K],
  ) {
    const next = { ...data, [key]: value };
    setData(next);
    onChange(next);
  }

  return (
    <div className="space-y-3 rounded-lg border border-astra-border bg-astra-bg-3 p-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
        <Cable className="h-4 w-4 text-blue-400" />
        Harness metadata
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {/* ── name (required) ── */}
        <div>
          <label className="mb-1 block text-xs text-slate-400">
            Name <span className="text-rose-400">*</span>
          </label>
          <input
            type="text"
            required
            value={data.name}
            onChange={(e) => update('name', e.target.value)}
            placeholder="e.g. Radar↔C2 Power+Data Bundle"
            className="w-full rounded border border-astra-border bg-astra-bg-2 px-2 py-1.5 text-sm text-slate-100"
          />
        </div>

        {/* ── cable_type ── */}
        <div>
          <label className="mb-1 block text-xs text-slate-400">Cable type</label>
          <input
            type="text"
            value={data.cable_type ?? ''}
            list="cb-cable-types"
            onChange={(e) => update('cable_type', e.target.value)}
            placeholder="MIL-C-27500-22SD2T23"
            className="w-full rounded border border-astra-border bg-astra-bg-2 px-2 py-1.5 text-sm text-slate-100"
          />
          <datalist id="cb-cable-types">
            {CABLE_TYPE_PRESETS.map((p) => (
              <option key={p} value={p} />
            ))}
          </datalist>
        </div>

        {/* ── length ── */}
        <div>
          <label className="mb-1 block text-xs text-slate-400">
            Overall length (m)
          </label>
          <input
            type="number"
            step="0.1"
            min="0"
            value={data.overall_length_m ?? ''}
            onChange={(e) =>
              update(
                'overall_length_m',
                e.target.value === '' ? undefined : Number(e.target.value),
              )
            }
            placeholder="e.g. 1.5"
            className="w-full rounded border border-astra-border bg-astra-bg-2 px-2 py-1.5 text-sm text-slate-100"
          />
        </div>

        {/* ── jacket color ── */}
        <div>
          <label className="mb-1 block text-xs text-slate-400">Jacket color</label>
          <select
            value={data.jacket_color ?? ''}
            onChange={(e) => update('jacket_color', e.target.value)}
            className="w-full rounded border border-astra-border bg-astra-bg-2 px-2 py-1.5 text-sm text-slate-100"
          >
            <option value="">(unspecified)</option>
            {JACKET_COLORS.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>

        {/* ── shield ── */}
        <div>
          <label className="mb-1 block text-xs text-slate-400">Shield type</label>
          <select
            value={data.shield_type ?? ''}
            onChange={(e) => update('shield_type', e.target.value)}
            className="w-full rounded border border-astra-border bg-astra-bg-2 px-2 py-1.5 text-sm text-slate-100"
          >
            {SHIELD_TYPES.map((s) => (
              <option key={s} value={s}>{s || '(unspecified)'}</option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label className="mb-1 block text-xs text-slate-400">Description</label>
        <textarea
          rows={2}
          value={data.description ?? ''}
          onChange={(e) => update('description', e.target.value)}
          placeholder="Optional notes…"
          className="w-full rounded border border-astra-border bg-astra-bg-2 px-2 py-1.5 text-sm text-slate-100"
        />
      </div>
    </div>
  );
}
