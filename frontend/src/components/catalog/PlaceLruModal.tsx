'use client';

/**
 * ASTRA — Place LRU Modal (spec §14)
 * ====================================
 * File: frontend/src/components/catalog/PlaceLruModal.tsx
 *
 * Three-tab modal for placing a unit into a project:
 *
 *   Tab 1: From Catalog   — pick an existing CatalogPart, fill project-side
 *                            fields, call POST /catalog/parts/{id}/place
 *   Tab 2: Brand New      — create a NEW global CatalogPart, then place it
 *                            in one round-trip (audit-trail aware)
 *   Tab 3: Upload ICD     — disabled in Phase 3, enabled in Phase 7
 *                            (the tab button is rendered with cursor-not-allowed,
 *                             aria-disabled="true", and a tooltip explaining the
 *                             phase gate so the UX is consistent for Phase 7)
 *
 * Project-scoped: the placement call requires `project_member_required` on
 * the backend, so non-members get 403 (handled gracefully).
 *
 * Phase 3 — ASTRA-TDD-INTF-002.
 */

import { useEffect, useState, useCallback, useRef } from 'react';
import {
  X, Plus, Search, AlertTriangle, Loader2, Cpu, Box, Building2,
  FileUp, Check, Globe, ChevronRight,
} from 'lucide-react';
import clsx from 'clsx';

import { catalogAPI } from '@/lib/catalog-api';
import { interfaceAPI } from '@/lib/interface-api';
import type {
  CatalogPart,
  Supplier,
  PartClass,
  LRUClass,
  LifecycleStatus,
} from '@/lib/catalog-types';
import {
  LIFECYCLE_COLORS,
  PART_CLASS_LABELS,
  LRU_CLASS_LABELS,
} from '@/lib/catalog-types';
import type { System, Unit } from '@/lib/interface-types';

// ══════════════════════════════════════════════════════════════
//  Types
// ══════════════════════════════════════════════════════════════

type TabKey = 'catalog' | 'brand_new' | 'upload_icd';

export interface PlaceLruModalProps {
  /** Project the placement targets — needed for the membership-gated POST. */
  projectId: number;
  /**
   * Optional default system to pre-select. If not supplied the user picks
   * from the project's systems list (we fetch them on mount).
   */
  defaultSystemId?: number;
  open: boolean;
  onClose: () => void;
  /**
   * Called after a successful placement. Receives the new Unit so the
   * caller can navigate or refresh. The modal closes itself first.
   */
  onPlaced?: (unit: Unit) => void;
}

// ══════════════════════════════════════════════════════════════
//  Small UI primitives
// ══════════════════════════════════════════════════════════════

const PART_CLASSES: PartClass[] = [
  'processor', 'sensor', 'power_supply', 'radio', 'antenna', 'actuator',
  'display', 'harness', 'connector_only', 'compute_module',
  'power_distribution', 'interface_card', 'other',
];

const LRU_CLASSES: LRUClass[] = ['lru', 'sru', 'wra', 'subassembly', 'component'];

const LIFECYCLE_STATUSES: LifecycleStatus[] = [
  'active', 'preferred', 'obsolete', 'eol_announced', 'nrnd', 'restricted',
];

function FieldLabel({ htmlFor, children, required }: {
  htmlFor: string; children: React.ReactNode; required?: boolean;
}) {
  return (
    <label
      htmlFor={htmlFor}
      className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block"
    >
      {children}{required && <span className="text-red-400 ml-0.5">*</span>}
    </label>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="mb-3 rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2 text-xs text-red-400 flex items-center gap-2"
    >
      <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}

function LifecyclePill({ status }: { status: LifecycleStatus }) {
  const c = LIFECYCLE_COLORS[status];
  return (
    <span
      className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
      style={{ background: c.bg, color: c.text }}
    >
      {c.label}
    </span>
  );
}

// ══════════════════════════════════════════════════════════════
//  Tab 1 — From Catalog
// ══════════════════════════════════════════════════════════════

interface ProjectPlacementFields {
  systemId: number | null;
  unitIdTag: string;
  designationOverride: string;
  locationZone: string;
  serialNumber: string;
  assetTag: string;
}

const EMPTY_PLACEMENT: ProjectPlacementFields = {
  systemId: null,
  unitIdTag: '',
  designationOverride: '',
  locationZone: '',
  serialNumber: '',
  assetTag: '',
};

function CatalogTab({
  projectId, systems, defaultSystemId, onPlaced, setError,
}: {
  projectId: number;
  systems: System[];
  defaultSystemId?: number;
  onPlaced: (u: Unit) => void;
  setError: (msg: string) => void;
}) {
  const [search, setSearch] = useState('');
  const [partClassFilter, setPartClassFilter] = useState<PartClass | ''>('');
  const [supplierFilter, setSupplierFilter] = useState<number | ''>('');
  const [lifecycleFilter, setLifecycleFilter] = useState<LifecycleStatus | ''>('');

  const [parts, setParts] = useState<CatalogPart[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<CatalogPart | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [placement, setPlacement] = useState<ProjectPlacementFields>({
    ...EMPTY_PLACEMENT,
    systemId: defaultSystemId ?? null,
  });
  const [adminForce, setAdminForce] = useState(false);

  // One-time supplier list for the filter dropdown
  useEffect(() => {
    catalogAPI.listSuppliers({ limit: 200 })
      .then((r) => setSuppliers(r.data))
      .catch(() => setSuppliers([]));
  }, []);

  // Re-fetch parts on filter change. Debounce search by 250ms.
  useEffect(() => {
    setLoading(true);
    const handle = setTimeout(() => {
      catalogAPI.listParts({
        q: search || undefined,
        part_class: partClassFilter || undefined,
        supplier_id: supplierFilter || undefined,
        lifecycle_status: lifecycleFilter || undefined,
        limit: 50,
      }).then((r) => {
        setParts(r.data);
      }).catch((e) => {
        setError(e?.response?.data?.detail || 'Failed to load catalog parts');
      }).finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(handle);
  }, [search, partClassFilter, supplierFilter, lifecycleFilter, setError]);

  const canSubmit =
    selected !== null &&
    placement.systemId !== null &&
    placement.unitIdTag.trim().length > 0;

  const handlePlace = async () => {
    if (!selected || !placement.systemId || !placement.unitIdTag.trim()) return;
    setSubmitting(true);
    setError('');
    try {
      const r = await catalogAPI.placePart(selected.id, {
        project_id: projectId,
        system_id: placement.systemId,
        unit_id_tag: placement.unitIdTag.trim(),
        designation_override: placement.designationOverride.trim() || undefined,
        location_zone: placement.locationZone.trim() || undefined,
        serial_number: placement.serialNumber.trim() || undefined,
        asset_tag: placement.assetTag.trim() || undefined,
        admin_force: adminForce,
      });
      onPlaced(r.data);
    } catch (e: unknown) {
      const err = e as { response?: { status?: number; data?: { detail?: string } } };
      const status = err?.response?.status;
      let msg: string;
      if (status === 403) {
        msg = 'You are not a member of this project. Ask the project manager to add you before placing parts.';
      } else if (status === 409) {
        msg = err?.response?.data?.detail || 'Conflict — duplicate unit_id_tag in this project, or restricted-part placement requires admin_force.';
      } else {
        msg = err?.response?.data?.detail || 'Failed to place catalog part';
      }
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const isRestricted = selected?.lifecycle_status === 'restricted';

  return (
    <div className="grid grid-cols-2 gap-4 min-h-[420px]">
      {/* ── Left: search + part list ── */}
      <div className="flex flex-col gap-2 border-r border-astra-border pr-4">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" aria-hidden="true" />
          <label htmlFor="cat-search" className="sr-only">Search catalog parts</label>
          <input
            id="cat-search"
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search part number, name, designation..."
            className="w-full rounded-lg border border-astra-border bg-astra-bg pl-8 pr-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
          />
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div>
            <label htmlFor="cat-class" className="sr-only">Part class</label>
            <select
              id="cat-class"
              value={partClassFilter}
              onChange={(e) => setPartClassFilter(e.target.value as PartClass | '')}
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-2 py-1.5 text-[11px] text-slate-200 outline-none focus:border-blue-500/50"
            >
              <option value="">All classes</option>
              {PART_CLASSES.map((c) => <option key={c} value={c}>{PART_CLASS_LABELS[c]}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="cat-supplier" className="sr-only">Supplier</label>
            <select
              id="cat-supplier"
              value={supplierFilter}
              onChange={(e) => setSupplierFilter(e.target.value ? Number(e.target.value) : '')}
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-2 py-1.5 text-[11px] text-slate-200 outline-none focus:border-blue-500/50"
            >
              <option value="">All suppliers</option>
              {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="cat-lifecycle" className="sr-only">Lifecycle</label>
            <select
              id="cat-lifecycle"
              value={lifecycleFilter}
              onChange={(e) => setLifecycleFilter(e.target.value as LifecycleStatus | '')}
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-2 py-1.5 text-[11px] text-slate-200 outline-none focus:border-blue-500/50"
            >
              <option value="">Any lifecycle</option>
              {LIFECYCLE_STATUSES.map((s) => <option key={s} value={s}>{LIFECYCLE_COLORS[s].label}</option>)}
            </select>
          </div>
        </div>

        <div className="mt-1 flex-1 overflow-y-auto rounded-lg border border-astra-border bg-astra-bg" style={{ maxHeight: 320 }}>
          {loading ? (
            <div className="flex items-center justify-center py-10 text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" aria-label="Loading" />
            </div>
          ) : parts.length === 0 ? (
            <div className="py-10 text-center text-xs text-slate-500">
              No catalog parts match the current filters.
            </div>
          ) : (
            <ul className="divide-y divide-astra-border">
              {parts.map((p) => {
                const isSel = selected?.id === p.id;
                return (
                  <li key={p.id}>
                    <button
                      type="button"
                      onClick={() => setSelected(p)}
                      className={clsx(
                        'w-full px-3 py-2 text-left transition flex items-start gap-2',
                        isSel ? 'bg-blue-500/10 ring-1 ring-blue-500/40' : 'hover:bg-astra-surface-alt',
                      )}
                      aria-pressed={isSel}
                    >
                      <Cpu className="h-3.5 w-3.5 mt-0.5 text-blue-400 flex-shrink-0" aria-hidden="true" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-slate-100 truncate">{p.part_number}</span>
                          {p.revision && <span className="text-[10px] text-slate-500">rev {p.revision}</span>}
                          <LifecyclePill status={p.lifecycle_status} />
                        </div>
                        <div className="text-[11px] text-slate-400 truncate">{p.name}</div>
                        <div className="mt-0.5 flex items-center gap-2 text-[10px] text-slate-500">
                          <span>{p.supplier_name || '—'}</span>
                          <span>·</span>
                          <span>{PART_CLASS_LABELS[p.part_class]}</span>
                          {p.used_in_project_count > 0 && (
                            <>
                              <span>·</span>
                              <span>placed in {p.used_in_project_count} unit{p.used_in_project_count !== 1 && 's'}</span>
                            </>
                          )}
                        </div>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>

      {/* ── Right: selected preview + project-side fields ── */}
      <div className="flex flex-col gap-3 pl-1">
        {!selected ? (
          <div className="flex h-full items-center justify-center text-center text-xs text-slate-500">
            <div>
              <Box className="h-6 w-6 mx-auto mb-2 text-slate-600" aria-hidden="true" />
              Select a catalog part on the left to see its specs<br />and fill out the project-side fields.
            </div>
          </div>
        ) : (
          <>
            <div className="rounded-lg border border-astra-border bg-astra-surface-alt p-3">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <div className="text-sm font-bold text-slate-100">{selected.part_number}</div>
                  <div className="text-[11px] text-slate-400">{selected.name}</div>
                </div>
                <LifecyclePill status={selected.lifecycle_status} />
              </div>
              <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-slate-400">
                <div><span className="text-slate-500">Supplier:</span> {selected.supplier_name || '—'}</div>
                <div><span className="text-slate-500">Class:</span> {PART_CLASS_LABELS[selected.part_class]}</div>
                <div><span className="text-slate-500">LRU:</span> {LRU_CLASS_LABELS[selected.lru_classification]}</div>
                {selected.mass_kg && <div><span className="text-slate-500">Mass:</span> {selected.mass_kg} kg</div>}
                {selected.power_watts_nominal && <div><span className="text-slate-500">Power:</span> {selected.power_watts_nominal} W</div>}
              </div>
              {isRestricted && (
                <div className="mt-2 rounded-md bg-red-500/10 border border-red-500/20 px-2 py-1 text-[10px] text-red-300 flex items-start gap-1">
                  <AlertTriangle className="h-3 w-3 mt-0.5 flex-shrink-0" aria-hidden="true" />
                  This part is RESTRICTED. Placement requires admin override.
                </div>
              )}
            </div>

            {/* Project-side fields */}
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <FieldLabel htmlFor="cat-system" required>Target System</FieldLabel>
                <select
                  id="cat-system"
                  value={placement.systemId ?? ''}
                  onChange={(e) => setPlacement((p) => ({ ...p, systemId: e.target.value ? Number(e.target.value) : null }))}
                  className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
                >
                  <option value="">Choose a system…</option>
                  {systems.map((s) => (
                    <option key={s.id} value={s.id}>{s.abbreviation || s.name} ({s.system_id})</option>
                  ))}
                </select>
              </div>
              <div>
                <FieldLabel htmlFor="cat-unit-id" required>Unit ID Tag</FieldLabel>
                <input
                  id="cat-unit-id"
                  value={placement.unitIdTag}
                  onChange={(e) => setPlacement((p) => ({ ...p, unitIdTag: e.target.value }))}
                  placeholder="e.g. FCA-001"
                  className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
                />
              </div>
              <div>
                <FieldLabel htmlFor="cat-desig">Designation Override</FieldLabel>
                <input
                  id="cat-desig"
                  value={placement.designationOverride}
                  onChange={(e) => setPlacement((p) => ({ ...p, designationOverride: e.target.value }))}
                  placeholder="(defaults to unit_id_tag)"
                  className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
                />
              </div>
              <div>
                <FieldLabel htmlFor="cat-zone">Location Zone</FieldLabel>
                <input
                  id="cat-zone"
                  value={placement.locationZone}
                  onChange={(e) => setPlacement((p) => ({ ...p, locationZone: e.target.value }))}
                  placeholder="e.g. Bay-2 / Rack-A3"
                  className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
                />
              </div>
              <div>
                <FieldLabel htmlFor="cat-serial">Serial Number</FieldLabel>
                <input
                  id="cat-serial"
                  value={placement.serialNumber}
                  onChange={(e) => setPlacement((p) => ({ ...p, serialNumber: e.target.value }))}
                  placeholder="optional"
                  className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
                />
              </div>
              <div>
                <FieldLabel htmlFor="cat-asset">Asset Tag</FieldLabel>
                <input
                  id="cat-asset"
                  value={placement.assetTag}
                  onChange={(e) => setPlacement((p) => ({ ...p, assetTag: e.target.value }))}
                  placeholder="optional"
                  className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
                />
              </div>
            </div>

            {isRestricted && (
              <label className="flex items-center gap-2 text-[11px] text-amber-300">
                <input
                  type="checkbox"
                  checked={adminForce}
                  onChange={(e) => setAdminForce(e.target.checked)}
                  className="rounded border-astra-border bg-astra-bg"
                />
                Acknowledge restricted placement (admin override)
              </label>
            )}

            <div className="mt-auto flex justify-end pt-2">
              <button
                type="button"
                disabled={!canSubmit || submitting || (isRestricted && !adminForce)}
                onClick={handlePlace}
                className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Check className="h-3.5 w-3.5" aria-hidden="true" />}
                Place into Project
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
//  Tab 2 — Brand New (create CatalogPart + place atomically)
// ══════════════════════════════════════════════════════════════

interface NewPartFields {
  // Supplier-side
  supplierMode: 'existing' | 'new';
  supplierId: number | null;
  newSupplierName: string;
  newSupplierShort: string;
  newSupplierCage: string;
  // Catalog-side
  partNumber: string;
  revision: string;
  name: string;
  designation: string;
  partClass: PartClass;
  lruClass: LRUClass;
  description: string;
  // Optional physics
  massKg: string;
  powerW: string;
  voltageInputMin: string;
  voltageInputMax: string;
  tempOpMinC: string;
  tempOpMaxC: string;
}

const EMPTY_NEW_PART: NewPartFields = {
  supplierMode: 'existing',
  supplierId: null,
  newSupplierName: '',
  newSupplierShort: '',
  newSupplierCage: '',
  partNumber: '',
  revision: '',
  name: '',
  designation: '',
  partClass: 'other',
  lruClass: 'lru',
  description: '',
  massKg: '',
  powerW: '',
  voltageInputMin: '',
  voltageInputMax: '',
  tempOpMinC: '',
  tempOpMaxC: '',
};

function BrandNewTab({
  projectId, systems, defaultSystemId, onPlaced, setError,
}: {
  projectId: number;
  systems: System[];
  defaultSystemId?: number;
  onPlaced: (u: Unit) => void;
  setError: (msg: string) => void;
}) {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState<NewPartFields>(EMPTY_NEW_PART);
  const [placement, setPlacement] = useState<ProjectPlacementFields>({
    ...EMPTY_PLACEMENT,
    systemId: defaultSystemId ?? null,
  });

  useEffect(() => {
    catalogAPI.listSuppliers({ limit: 200 })
      .then((r) => setSuppliers(r.data))
      .catch(() => setSuppliers([]));
  }, []);

  const supplierReady =
    form.supplierMode === 'existing'
      ? form.supplierId !== null
      : form.newSupplierName.trim().length > 0;

  const canSubmit =
    supplierReady &&
    form.partNumber.trim().length > 0 &&
    form.name.trim().length > 0 &&
    placement.systemId !== null &&
    placement.unitIdTag.trim().length > 0;

  const num = (s: string): number | undefined => {
    if (!s.trim()) return undefined;
    const n = Number(s);
    return Number.isFinite(n) ? n : undefined;
  };

  const handleCreate = async () => {
    if (!canSubmit || !placement.systemId) return;
    setSubmitting(true);
    setError('');

    try {
      // Step 1: ensure supplier exists
      let supplierId = form.supplierId;
      if (form.supplierMode === 'new') {
        const s = await catalogAPI.createSupplier({
          name: form.newSupplierName.trim(),
          short_name: form.newSupplierShort.trim() || undefined,
          cage_code: form.newSupplierCage.trim() || undefined,
          is_active: true,
        });
        supplierId = s.data.id;
      }
      if (!supplierId) throw new Error('Supplier could not be resolved');

      // Step 2: create the catalog part
      const part = await catalogAPI.createPart({
        supplier_id: supplierId,
        part_number: form.partNumber.trim(),
        revision: form.revision.trim() || undefined,
        name: form.name.trim(),
        designation: form.designation.trim() || undefined,
        description: form.description.trim() || undefined,
        part_class: form.partClass,
        lru_classification: form.lruClass,
        mass_kg: num(form.massKg),
        power_watts_nominal: num(form.powerW),
        voltage_input_min_v: num(form.voltageInputMin),
        voltage_input_max_v: num(form.voltageInputMax),
        temp_operating_min_c: num(form.tempOpMinC),
        temp_operating_max_c: num(form.tempOpMaxC),
      });

      // Step 3: place it into the project
      const placed = await catalogAPI.placePart(part.data.id, {
        project_id: projectId,
        system_id: placement.systemId,
        unit_id_tag: placement.unitIdTag.trim(),
        designation_override: placement.designationOverride.trim() || undefined,
        location_zone: placement.locationZone.trim() || undefined,
        serial_number: placement.serialNumber.trim() || undefined,
        asset_tag: placement.assetTag.trim() || undefined,
      });
      onPlaced(placed.data);
    } catch (e: unknown) {
      const err = e as { response?: { status?: number; data?: { detail?: string } } };
      const status = err?.response?.status;
      let msg: string;
      if (status === 403) {
        msg = 'You are not a member of this project. Ask the project manager to add you.';
      } else if (status === 409) {
        msg = err?.response?.data?.detail || 'Conflict — supplier name or part_number+revision already exists.';
      } else {
        msg = err?.response?.data?.detail || 'Failed to create and place the new catalog part';
      }
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="grid grid-cols-2 gap-4 min-h-[420px] overflow-y-auto" style={{ maxHeight: 480 }}>
      {/* ── Left: catalog (global) part details ── */}
      <div className="flex flex-col gap-3 border-r border-astra-border pr-4">
        <div className="rounded-lg bg-blue-500/10 border border-blue-500/20 px-3 py-2 text-[11px] text-blue-300 flex items-start gap-2">
          <Globe className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" aria-hidden="true" />
          <div>
            <strong>Heads-up:</strong> The catalog part you create here is global —
            it will be visible to every project on this ASTRA instance. Use the
            "From Catalog" tab if a similar part already exists.
          </div>
        </div>

        <fieldset className="rounded-lg border border-astra-border p-3">
          <legend className="px-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            Supplier
          </legend>
          <div className="flex gap-3 mb-2 text-[11px] text-slate-300">
            <label className="flex items-center gap-1">
              <input
                type="radio"
                name="bn-supplier-mode"
                checked={form.supplierMode === 'existing'}
                onChange={() => setForm((f) => ({ ...f, supplierMode: 'existing' }))}
              />
              Existing
            </label>
            <label className="flex items-center gap-1">
              <input
                type="radio"
                name="bn-supplier-mode"
                checked={form.supplierMode === 'new'}
                onChange={() => setForm((f) => ({ ...f, supplierMode: 'new' }))}
              />
              Create new
            </label>
          </div>
          {form.supplierMode === 'existing' ? (
            <div>
              <FieldLabel htmlFor="bn-supplier-pick" required>Supplier</FieldLabel>
              <select
                id="bn-supplier-pick"
                value={form.supplierId ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, supplierId: e.target.value ? Number(e.target.value) : null }))}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
              >
                <option value="">Choose a supplier…</option>
                {suppliers.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}{s.cage_code ? ` (${s.cage_code})` : ''}</option>
                ))}
              </select>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <div className="col-span-2">
                <FieldLabel htmlFor="bn-newsup-name" required>Supplier Name</FieldLabel>
                <input
                  id="bn-newsup-name"
                  value={form.newSupplierName}
                  onChange={(e) => setForm((f) => ({ ...f, newSupplierName: e.target.value }))}
                  placeholder="e.g. Honeywell Aerospace"
                  className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
                />
              </div>
              <div>
                <FieldLabel htmlFor="bn-newsup-short">Short Name</FieldLabel>
                <input
                  id="bn-newsup-short"
                  value={form.newSupplierShort}
                  onChange={(e) => setForm((f) => ({ ...f, newSupplierShort: e.target.value }))}
                  placeholder="HW"
                  className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
                />
              </div>
              <div>
                <FieldLabel htmlFor="bn-newsup-cage">CAGE Code</FieldLabel>
                <input
                  id="bn-newsup-cage"
                  value={form.newSupplierCage}
                  onChange={(e) => setForm((f) => ({ ...f, newSupplierCage: e.target.value }))}
                  placeholder="55555"
                  className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
                />
              </div>
            </div>
          )}
        </fieldset>

        <fieldset className="rounded-lg border border-astra-border p-3">
          <legend className="px-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            Part Identity
          </legend>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <FieldLabel htmlFor="bn-pn" required>Part Number</FieldLabel>
              <input id="bn-pn" value={form.partNumber}
                onChange={(e) => setForm((f) => ({ ...f, partNumber: e.target.value }))}
                placeholder="e.g. HG2120BA01"
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <div>
              <FieldLabel htmlFor="bn-rev">Revision</FieldLabel>
              <input id="bn-rev" value={form.revision}
                onChange={(e) => setForm((f) => ({ ...f, revision: e.target.value }))}
                placeholder="e.g. C"
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <div>
              <FieldLabel htmlFor="bn-desig">Designation</FieldLabel>
              <input id="bn-desig" value={form.designation}
                onChange={(e) => setForm((f) => ({ ...f, designation: e.target.value }))}
                placeholder="e.g. IMU"
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <div className="col-span-2">
              <FieldLabel htmlFor="bn-name" required>Name</FieldLabel>
              <input id="bn-name" value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="e.g. Inertial Measurement Unit"
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <div>
              <FieldLabel htmlFor="bn-class" required>Part Class</FieldLabel>
              <select id="bn-class" value={form.partClass}
                onChange={(e) => setForm((f) => ({ ...f, partClass: e.target.value as PartClass }))}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50">
                {PART_CLASSES.map((c) => <option key={c} value={c}>{PART_CLASS_LABELS[c]}</option>)}
              </select>
            </div>
            <div>
              <FieldLabel htmlFor="bn-lru" required>LRU Classification</FieldLabel>
              <select id="bn-lru" value={form.lruClass}
                onChange={(e) => setForm((f) => ({ ...f, lruClass: e.target.value as LRUClass }))}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50">
                {LRU_CLASSES.map((c) => <option key={c} value={c}>{LRU_CLASS_LABELS[c]}</option>)}
              </select>
            </div>
          </div>
        </fieldset>

        <fieldset className="rounded-lg border border-astra-border p-3">
          <legend className="px-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            Optional Physics
          </legend>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <FieldLabel htmlFor="bn-mass">Mass (kg)</FieldLabel>
              <input id="bn-mass" type="number" inputMode="decimal" step="0.001" value={form.massKg}
                onChange={(e) => setForm((f) => ({ ...f, massKg: e.target.value }))}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <div>
              <FieldLabel htmlFor="bn-power">Power Nominal (W)</FieldLabel>
              <input id="bn-power" type="number" inputMode="decimal" step="0.01" value={form.powerW}
                onChange={(e) => setForm((f) => ({ ...f, powerW: e.target.value }))}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <div>
              <FieldLabel htmlFor="bn-vmin">V Input Min</FieldLabel>
              <input id="bn-vmin" type="number" inputMode="decimal" step="0.01" value={form.voltageInputMin}
                onChange={(e) => setForm((f) => ({ ...f, voltageInputMin: e.target.value }))}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <div>
              <FieldLabel htmlFor="bn-vmax">V Input Max</FieldLabel>
              <input id="bn-vmax" type="number" inputMode="decimal" step="0.01" value={form.voltageInputMax}
                onChange={(e) => setForm((f) => ({ ...f, voltageInputMax: e.target.value }))}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <div>
              <FieldLabel htmlFor="bn-tmin">Op Temp Min (°C)</FieldLabel>
              <input id="bn-tmin" type="number" inputMode="decimal" step="0.1" value={form.tempOpMinC}
                onChange={(e) => setForm((f) => ({ ...f, tempOpMinC: e.target.value }))}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <div>
              <FieldLabel htmlFor="bn-tmax">Op Temp Max (°C)</FieldLabel>
              <input id="bn-tmax" type="number" inputMode="decimal" step="0.1" value={form.tempOpMaxC}
                onChange={(e) => setForm((f) => ({ ...f, tempOpMaxC: e.target.value }))}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
          </div>
        </fieldset>
      </div>

      {/* ── Right: project-side placement ── */}
      <div className="flex flex-col gap-3 pl-1">
        <fieldset className="rounded-lg border border-astra-border p-3">
          <legend className="px-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            Project Placement
          </legend>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <FieldLabel htmlFor="bn-system" required>Target System</FieldLabel>
              <select id="bn-system"
                value={placement.systemId ?? ''}
                onChange={(e) => setPlacement((p) => ({ ...p, systemId: e.target.value ? Number(e.target.value) : null }))}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50">
                <option value="">Choose a system…</option>
                {systems.map((s) => (
                  <option key={s.id} value={s.id}>{s.abbreviation || s.name} ({s.system_id})</option>
                ))}
              </select>
            </div>
            <div>
              <FieldLabel htmlFor="bn-unit-id" required>Unit ID Tag</FieldLabel>
              <input id="bn-unit-id" value={placement.unitIdTag}
                onChange={(e) => setPlacement((p) => ({ ...p, unitIdTag: e.target.value }))}
                placeholder="e.g. IMU-001"
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <div>
              <FieldLabel htmlFor="bn-overdesig">Designation Override</FieldLabel>
              <input id="bn-overdesig" value={placement.designationOverride}
                onChange={(e) => setPlacement((p) => ({ ...p, designationOverride: e.target.value }))}
                placeholder="(defaults to unit_id_tag)"
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <div>
              <FieldLabel htmlFor="bn-zone">Location Zone</FieldLabel>
              <input id="bn-zone" value={placement.locationZone}
                onChange={(e) => setPlacement((p) => ({ ...p, locationZone: e.target.value }))}
                placeholder="optional"
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <div>
              <FieldLabel htmlFor="bn-serial">Serial Number</FieldLabel>
              <input id="bn-serial" value={placement.serialNumber}
                onChange={(e) => setPlacement((p) => ({ ...p, serialNumber: e.target.value }))}
                placeholder="optional"
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <div className="col-span-2">
              <FieldLabel htmlFor="bn-asset">Asset Tag</FieldLabel>
              <input id="bn-asset" value={placement.assetTag}
                onChange={(e) => setPlacement((p) => ({ ...p, assetTag: e.target.value }))}
                placeholder="optional"
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
          </div>
        </fieldset>

        <div className="mt-auto flex justify-end pt-2">
          <button
            type="button"
            disabled={!canSubmit || submitting}
            onClick={handleCreate}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Plus className="h-3.5 w-3.5" aria-hidden="true" />}
            Create &amp; Place
          </button>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
//  Tab 3 — Upload ICD (disabled in Phase 3)
// ══════════════════════════════════════════════════════════════

const PHASE_7_TOOLTIP = 'Available in Phase 7 — ICD ingestion not yet enabled.';

function UploadIcdTab() {
  return (
    <div className="flex min-h-[420px] flex-col items-center justify-center gap-4 text-center" aria-disabled="true">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-amber-500/10 ring-1 ring-amber-500/30">
        <AlertTriangle className="h-6 w-6 text-amber-400" aria-hidden="true" />
      </div>
      <div>
        <div className="text-sm font-bold text-slate-200">Upload ICD &amp; Auto-Extract</div>
        <p className="mt-1 max-w-sm text-xs text-slate-500">
          {PHASE_7_TOOLTIP}{' '}
          When live, this tab will accept a supplier ICD PDF, run the ASTRA AI
          ingestion pipeline, and let you review the extracted catalog part
          before placing it.
        </p>
      </div>
      <button
        type="button"
        disabled
        aria-disabled="true"
        title={PHASE_7_TOOLTIP}
        className="flex cursor-not-allowed items-center gap-1.5 rounded-lg border border-astra-border bg-astra-surface-alt px-4 py-2 text-xs font-semibold text-slate-500 opacity-50"
      >
        <FileUp className="h-3.5 w-3.5" aria-hidden="true" /> Choose ICD File
      </button>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
//  Main Modal Shell
// ══════════════════════════════════════════════════════════════

export default function PlaceLruModal({
  projectId, defaultSystemId, open, onClose, onPlaced,
}: PlaceLruModalProps) {
  const [tab, setTab] = useState<TabKey>('catalog');
  const [systems, setSystems] = useState<System[]>([]);
  const [error, setError] = useState('');
  const titleId = useRef(`place-lru-${Math.random().toString(36).slice(2, 8)}`);

  // Fetch systems for the picker once when the modal opens.
  useEffect(() => {
    if (!open) return;
    interfaceAPI.listSystems(projectId, 'flat')
      .then((r) => setSystems(r.data))
      .catch((e) => setError(e?.response?.data?.detail || 'Failed to load project systems'));
    return () => { setError(''); };
  }, [open, projectId]);

  // Escape closes
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  // Lock body scroll while open
  useEffect(() => {
    if (open) document.body.style.overflow = 'hidden';
    else document.body.style.overflow = '';
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  const handlePlaced = useCallback((u: Unit) => {
    onPlaced?.(u);
    onClose();
  }, [onPlaced, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      role="presentation"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId.current}
        className="w-full max-w-4xl rounded-2xl border border-astra-border bg-astra-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-astra-border px-5 py-3">
          <div>
            <h2 id={titleId.current} className="text-sm font-bold text-slate-100">
              Place an LRU into this Project
            </h2>
            <p className="text-[11px] text-slate-500 mt-0.5 flex items-center gap-1">
              <Building2 className="h-3 w-3" aria-hidden="true" />
              From the catalog, brand new, or an uploaded ICD.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close place-LRU modal"
            className="rounded-lg p-1.5 text-slate-400 hover:bg-astra-surface-alt hover:text-slate-200"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        {/* Tabs */}
        <div role="tablist" aria-label="Placement source" className="flex gap-1 border-b border-astra-border px-5 pt-3">
          <TabButton id="cat-tab" panelId="cat-panel" active={tab === 'catalog'} onClick={() => setTab('catalog')} icon={<Cpu className="h-3.5 w-3.5" aria-hidden="true" />}>
            From Catalog
          </TabButton>
          <TabButton id="bn-tab" panelId="bn-panel" active={tab === 'brand_new'} onClick={() => setTab('brand_new')} icon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}>
            Brand New
          </TabButton>
          <TabButton
            id="icd-tab"
            panelId="icd-panel"
            active={tab === 'upload_icd'}
            onClick={() => { /* disabled */ }}
            disabled
            tooltip={PHASE_7_TOOLTIP}
            icon={<FileUp className="h-3.5 w-3.5" aria-hidden="true" />}
          >
            Upload ICD
          </TabButton>
        </div>

        {/* Body */}
        <div className="px-5 py-4">
          {error && <ErrorBanner message={error} />}
          {tab === 'catalog' && (
            <div role="tabpanel" id="cat-panel" aria-labelledby="cat-tab">
              <CatalogTab
                projectId={projectId}
                systems={systems}
                defaultSystemId={defaultSystemId}
                onPlaced={handlePlaced}
                setError={setError}
              />
            </div>
          )}
          {tab === 'brand_new' && (
            <div role="tabpanel" id="bn-panel" aria-labelledby="bn-tab">
              <BrandNewTab
                projectId={projectId}
                systems={systems}
                defaultSystemId={defaultSystemId}
                onPlaced={handlePlaced}
                setError={setError}
              />
            </div>
          )}
          {tab === 'upload_icd' && (
            <div role="tabpanel" id="icd-panel" aria-labelledby="icd-tab">
              <UploadIcdTab />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function TabButton({
  id, panelId, active, onClick, disabled, tooltip, icon, children,
}: {
  id: string;
  panelId: string;
  active: boolean;
  onClick: () => void;
  disabled?: boolean;
  tooltip?: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <button
      id={id}
      role="tab"
      aria-controls={panelId}
      aria-selected={active}
      aria-disabled={disabled || undefined}
      title={tooltip}
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={clsx(
        'flex items-center gap-1.5 rounded-t-lg border-b-2 px-4 py-2 text-xs font-semibold transition',
        active
          ? 'border-blue-400 text-blue-300'
          : 'border-transparent text-slate-400 hover:text-slate-200',
        disabled && 'cursor-not-allowed opacity-50 hover:text-slate-400',
      )}
    >
      {icon}
      {children}
      {disabled && <ChevronRight className="h-3 w-3 opacity-60" aria-hidden="true" />}
    </button>
  );
}
