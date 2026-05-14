'use client';

/**
 * ASTRA — AddUnitModal (TDD-SYSARCH-002 §4 Phase 4)
 * ===================================================
 * Centerpiece is the CatalogPartPicker at the top — selecting a part
 * auto-fills name, manufacturer, part_number, unit_type. Each field is
 * still editable so the user can override.
 *
 * Wires `useFormAutosave` keyed by project + chosen system so the
 * draft survives a session timeout.
 */

import { useEffect, useMemo, useState } from 'react';
import { Loader2, X } from 'lucide-react';

import { interfaceAPI } from '@/lib/interface-api';
import { formatApiError } from '@/lib/errors';
import type { System, UnitStatus, UnitType } from '@/lib/interface-types';
import type { CatalogPart, PartClass } from '@/lib/catalog-types';
import { useFormAutosave } from '@/lib/autosave';
import RestorePromptBanner from '@/components/RestorePromptBanner';
import CatalogPartPicker from '@/components/catalog/CatalogPartPicker';


// Catalog part classes that map onto electrical/electronic units. The
// new mechanical CAT-002 values (fastener_screw, washer, …) are
// intentionally NOT here — those are not Units; they're project parts
// (TDD-PROJPARTS-001).
const ALLOWED_PART_CLASSES: PartClass[] = [
  'processor', 'sensor', 'power_supply', 'radio', 'antenna', 'actuator',
  'display', 'harness', 'connector_only', 'compute_module',
  'power_distribution', 'interface_card', 'other',
];

// Map a CatalogPart.part_class onto a sensible default Unit.unit_type.
// User can override after the auto-fill.
const PART_CLASS_TO_UNIT_TYPE: Partial<Record<PartClass, UnitType>> = {
  processor: 'processor',
  sensor: 'sensor',
  power_supply: 'power_supply',
  power_distribution: 'power_supply',
  radio: 'transceiver',
  antenna: 'antenna',
  actuator: 'actuator',
  display: 'custom',
  harness: 'cable_assembly',
  connector_only: 'connector_assembly',
  compute_module: 'processor',
  interface_card: 'cca',
  other: 'custom',
};

const UNIT_TYPES: UnitType[] = [
  'lru', 'wru', 'sru', 'cca', 'pcb', 'backplane', 'chassis',
  'sensor', 'actuator', 'motor', 'processor', 'fpga', 'asic',
  'power_supply', 'power_converter', 'battery', 'solar_panel',
  'transmitter', 'receiver', 'transceiver', 'antenna', 'cable_assembly',
  'connector_assembly', 'custom',
];

const UNIT_STATUSES: UnitStatus[] = [
  'concept', 'preliminary_design', 'detailed_design', 'prototype',
  'engineering_model', 'qualification_unit', 'flight_unit',
  'production', 'installed', 'qualified', 'accepted', 'operational',
  'failed', 'obsolete',
];


export interface AddUnitModalProps {
  open: boolean;
  projectId: number;
  systems: System[];
  /** Pre-fills the system dropdown when a system was already chosen
   *  in the page (e.g. user clicked Add Unit from System Detail). */
  defaultSystemId?: number | null;
  onClose: () => void;
  onCreated: (unit: { id: number }) => void;
}


interface DraftState {
  catalog_part_id: number | null;
  system_id: number | null;
  designation: string;
  name: string;
  unit_type: UnitType;
  manufacturer: string;
  part_number: string;
  location_zone: string;
  status: UnitStatus;
}


function makeEmptyDraft(defaultSystemId: number | null): DraftState {
  return {
    catalog_part_id: null,
    system_id: defaultSystemId,
    designation: '',
    name: '',
    unit_type: 'lru',
    manufacturer: '',
    part_number: '',
    location_zone: '',
    status: 'concept',
  };
}


export default function AddUnitModal({
  open, projectId, systems, defaultSystemId = null, onClose, onCreated,
}: AddUnitModalProps) {
  const [draft, setDraft] = useState<DraftState>(makeEmptyDraft(defaultSystemId));
  const [pickedPart, setPickedPart] = useState<CatalogPart | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const storageKey = `astra:autosave:unit-new:project-${projectId}:system-${draft.system_id ?? 'none'}`;
  const memoDraft = useMemo(() => draft, [draft]);
  const {
    hasDraft, draftAge, restoreDraft, clearDraft,
  } = useFormAutosave<DraftState>(storageKey, memoDraft);

  useEffect(() => {
    if (!open) {
      setError(null);
      setSubmitting(false);
    }
  }, [open]);

  // When the parent's defaultSystemId changes (e.g. user navigates with
  // a system in scope) seed the draft if the user hasn't typed yet.
  useEffect(() => {
    if (open && defaultSystemId != null && draft.system_id == null && !draft.designation) {
      setDraft((d) => ({ ...d, system_id: defaultSystemId }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, defaultSystemId]);

  const onPickCatalogPart = (cp: CatalogPart | null) => {
    setPickedPart(cp);
    if (cp == null) {
      setDraft((d) => ({ ...d, catalog_part_id: null }));
      return;
    }
    const unitType = PART_CLASS_TO_UNIT_TYPE[cp.part_class] || 'custom';
    setDraft((d) => ({
      ...d,
      catalog_part_id: cp.id,
      // Fill empty fields; preserve user overrides.
      name: d.name || cp.name,
      manufacturer: d.manufacturer || (cp.supplier_name || ''),
      part_number: d.part_number || cp.part_number,
      unit_type: d.unit_type === 'lru' ? unitType : d.unit_type,
    }));
  };

  const submit = async () => {
    if (!draft.system_id) {
      setError('System is required.');
      return;
    }
    if (!draft.designation.trim()) {
      setError('Designation is required.');
      return;
    }
    if (!draft.name.trim()) {
      setError('Name is required.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const r = await interfaceAPI.createUnit(projectId, {
        system_id: draft.system_id,
        designation: draft.designation.trim(),
        name: draft.name.trim(),
        unit_type: draft.unit_type,
        manufacturer: draft.manufacturer.trim() || 'Unknown',
        part_number: draft.part_number.trim() || draft.designation.trim(),
        status: draft.status,
        location_zone: draft.location_zone.trim() || undefined,
        catalog_part_id: draft.catalog_part_id ?? undefined,
      });
      clearDraft();
      setDraft(makeEmptyDraft(defaultSystemId));
      setPickedPart(null);
      onCreated(r.data as { id: number });
      onClose();
    } catch (e: unknown) {
      setError(formatApiError(e, 'Create failed'));
    } finally {
      setSubmitting(false);
    }
  };

  const onRestore = () => {
    const v = restoreDraft();
    if (v) setDraft(v);
  };

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-unit-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-xl rounded-xl border border-astra-border bg-astra-surface p-5 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 id="add-unit-title" className="text-base font-bold text-slate-100">
            Add Unit
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            aria-label="Close"
            className="rounded p-1 text-slate-400 hover:bg-astra-surface-alt hover:text-slate-200"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {hasDraft && draftAge !== null && (
          <RestorePromptBanner
            ageMs={draftAge}
            onRestore={onRestore}
            onDiscard={clearDraft}
          />
        )}

        {error && (
          <div role="alert" className="mb-3 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
            {error}
          </div>
        )}

        <div className="space-y-3">
          <CatalogPartPicker
            label="Catalog part"
            value={pickedPart}
            onChange={onPickCatalogPart}
            allowedClasses={ALLOWED_PART_CLASSES}
            placeholder="Pick a catalog part (optional — auto-fills below)"
            disabled={submitting}
          />

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="unit-system" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                System <span className="text-red-400">*</span>
              </label>
              <select
                id="unit-system"
                value={draft.system_id == null ? '' : String(draft.system_id)}
                onChange={(e) => setDraft({
                  ...draft,
                  system_id: e.target.value === '' ? null : Number(e.target.value),
                })}
                className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
              >
                <option value="">— pick a system —</option>
                {systems.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}{s.abbreviation ? ` (${s.abbreviation})` : ''}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="unit-designation" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Designation <span className="text-red-400">*</span>
              </label>
              <input
                id="unit-designation"
                type="text"
                value={draft.designation}
                onChange={(e) => setDraft({ ...draft, designation: e.target.value })}
                placeholder="RSP-100"
                className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
              />
            </div>
          </div>

          <div>
            <label htmlFor="unit-name" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Name <span className="text-red-400">*</span>
            </label>
            <input
              id="unit-name"
              type="text"
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              placeholder="Radio Signal Processor"
              className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="unit-type" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Unit type
              </label>
              <select
                id="unit-type"
                value={draft.unit_type}
                onChange={(e) => setDraft({ ...draft, unit_type: e.target.value as UnitType })}
                className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
              >
                {UNIT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="unit-status" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Status
              </label>
              <select
                id="unit-status"
                value={draft.status}
                onChange={(e) => setDraft({ ...draft, status: e.target.value as UnitStatus })}
                className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
              >
                {UNIT_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="unit-mfg" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Manufacturer
              </label>
              <input
                id="unit-mfg"
                type="text"
                value={draft.manufacturer}
                onChange={(e) => setDraft({ ...draft, manufacturer: e.target.value })}
                placeholder="(auto from catalog)"
                className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
              />
            </div>
            <div>
              <label htmlFor="unit-pn" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Part number (MPN)
              </label>
              <input
                id="unit-pn"
                type="text"
                value={draft.part_number}
                onChange={(e) => setDraft({ ...draft, part_number: e.target.value })}
                placeholder="(auto from catalog)"
                className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
              />
            </div>
          </div>

          <div>
            <label htmlFor="unit-zone" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Location zone
            </label>
            <input
              id="unit-zone"
              type="text"
              value={draft.location_zone}
              onChange={(e) => setDraft({ ...draft, location_zone: e.target.value })}
              placeholder="Avionics bay 2"
              className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
            />
          </div>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded border border-astra-border px-3 py-1.5 text-xs text-slate-300 hover:bg-astra-surface-alt"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={submitting || !draft.designation.trim() || !draft.name.trim() || !draft.system_id}
            className="flex items-center gap-1.5 rounded bg-gradient-to-br from-blue-500 to-violet-500 px-3 py-1.5 text-xs font-semibold text-white hover:shadow-lg disabled:opacity-50"
          >
            {submitting && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
            Add Unit
          </button>
        </div>
      </div>
    </div>
  );
}
