'use client';

/**
 * ASTRA — New Catalog Part Page
 * ===============================
 * File: frontend/src/app/catalog/parts/new/page.tsx
 *
 * Manual create-part form spanning identity, physical, electrical,
 * environmental, and lifecycle sections. On success, navigates to the
 * new part's detail page.
 *
 * Phase 3 — ASTRA-TDD-INTF-002.
 */

import { useState, useEffect, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  ChevronLeft, Cpu, Loader2, Plus, AlertTriangle, Globe,
} from 'lucide-react';

import { catalogAPI } from '@/lib/catalog-api';
import {
  type Supplier,
  type PartClass,
  type LRUClass,
  type LifecycleStatus,
  PART_CLASS_LABELS,
  LRU_CLASS_LABELS,
  LIFECYCLE_COLORS,
} from '@/lib/catalog-types';

const PART_CLASSES: PartClass[] = [
  'processor', 'sensor', 'power_supply', 'radio', 'antenna', 'actuator',
  'display', 'harness', 'connector_only', 'compute_module',
  'power_distribution', 'interface_card', 'other',
];
const LRU_CLASSES: LRUClass[] = ['lru', 'sru', 'wra', 'subassembly', 'component'];
const LIFECYCLE_STATUSES: LifecycleStatus[] = [
  'active', 'preferred', 'obsolete', 'eol_announced', 'nrnd', 'restricted',
];

export default function NewCatalogPartPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const presetSupplier = searchParams?.get('supplier_id');

  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [supplierId, setSupplierId] = useState<number | null>(presetSupplier ? Number(presetSupplier) : null);
  const [partNumber, setPartNumber] = useState('');
  const [revision, setRevision] = useState('');
  const [name, setName] = useState('');
  const [designation, setDesignation] = useState('');
  const [description, setDescription] = useState('');
  const [partClass, setPartClass] = useState<PartClass>('other');
  const [lruClass, setLruClass] = useState<LRUClass>('lru');
  const [lifecycle, setLifecycle] = useState<LifecycleStatus>('active');

  // Physical
  const [massKg, setMassKg] = useState('');
  const [dimL, setDimL] = useState('');
  const [dimW, setDimW] = useState('');
  const [dimH, setDimH] = useState('');
  // Power
  const [powerNominal, setPowerNominal] = useState('');
  const [powerPeak, setPowerPeak] = useState('');
  const [vMin, setVMin] = useState('');
  const [vMax, setVMax] = useState('');
  // Environmental
  const [tOpMin, setTOpMin] = useState('');
  const [tOpMax, setTOpMax] = useState('');
  const [tStMin, setTStMin] = useState('');
  const [tStMax, setTStMax] = useState('');
  const [vibG, setVibG] = useState('');
  const [shockG, setShockG] = useState('');
  const [humidity, setHumidity] = useState('');
  const [altitude, setAltitude] = useState('');
  // Compliance
  const [mil810, setMil810] = useState(false);
  const [mil461, setMil461] = useState(false);
  const [rohs, setRohs] = useState(false);
  const [itar, setItar] = useState(false);
  const [exportClass, setExportClass] = useState('');
  // Lifecycle
  const [eolDate, setEolDate] = useState('');
  const [notes, setNotes] = useState('');

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    catalogAPI.listSuppliers({ limit: 200 })
      .then((r) => setSuppliers(r.data))
      .catch((e) => setError(e?.response?.data?.detail || 'Failed to load suppliers'));
  }, []);

  const canSave = supplierId !== null && partNumber.trim().length > 0 && name.trim().length > 0;

  const num = (s: string): number | undefined => {
    if (!s.trim()) return undefined;
    const n = Number(s);
    return Number.isFinite(n) ? n : undefined;
  };

  const handleSave = async () => {
    if (!canSave || supplierId === null) return;
    setSaving(true);
    setError('');
    try {
      const r = await catalogAPI.createPart({
        supplier_id: supplierId,
        part_number: partNumber.trim(),
        revision: revision.trim() || undefined,
        name: name.trim(),
        designation: designation.trim() || undefined,
        description: description.trim() || undefined,
        part_class: partClass,
        lru_classification: lruClass,
        lifecycle_status: lifecycle,
        mass_kg: num(massKg),
        dim_length_mm: num(dimL),
        dim_width_mm: num(dimW),
        dim_height_mm: num(dimH),
        power_watts_nominal: num(powerNominal),
        power_watts_peak: num(powerPeak),
        voltage_input_min_v: num(vMin),
        voltage_input_max_v: num(vMax),
        temp_operating_min_c: num(tOpMin),
        temp_operating_max_c: num(tOpMax),
        temp_storage_min_c: num(tStMin),
        temp_storage_max_c: num(tStMax),
        vibration_random_grms: num(vibG),
        shock_mechanical_g: num(shockG),
        humidity_max_pct: num(humidity),
        altitude_max_m: num(altitude),
        mil_std_810_tested: mil810,
        mil_std_461_tested: mil461,
        rohs_compliant: rohs,
        itar_controlled: itar,
        export_classification: exportClass.trim() || undefined,
        eol_date: eolDate || undefined,
        notes: notes.trim() || undefined,
      });
      router.push(`/catalog/parts/${r.data.id}`);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setError(err?.response?.data?.detail || 'Failed to create catalog part');
      setSaving(false);
    }
  };

  return (
    <div>
      <button type="button" onClick={() => router.push('/catalog')} className="mb-4 flex items-center gap-1 text-xs text-slate-400 hover:text-blue-300">
        <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" /> Back to Catalog
      </button>

      <h1 className="mb-1 text-xl font-bold text-slate-100 flex items-center gap-2">
        <Cpu className="h-5 w-5 text-blue-400" aria-hidden="true" />
        New Catalog Part
      </h1>
      <p className="mb-5 text-xs text-slate-500 flex items-center gap-1.5">
        <Globe className="h-3 w-3" aria-hidden="true" />
        Catalog parts are global. They become available to every project.
      </p>

      {error && (
        <div role="alert" className="mb-3 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" /> {error}
        </div>
      )}

      <div className="max-w-5xl space-y-5">
        <Section title="Identity">
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <Label htmlFor="np-supplier" required>Supplier</Label>
              <select id="np-supplier" value={supplierId ?? ''}
                onChange={(e) => setSupplierId(e.target.value ? Number(e.target.value) : null)}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50">
                <option value="">Choose a supplier…</option>
                {suppliers.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}{s.cage_code ? ` (${s.cage_code})` : ''}</option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="np-pn" required>Part Number</Label>
              <Input id="np-pn" value={partNumber} onChange={setPartNumber} placeholder="e.g. HG2120BA01" />
            </div>
            <div>
              <Label htmlFor="np-rev">Revision</Label>
              <Input id="np-rev" value={revision} onChange={setRevision} placeholder="e.g. C" />
            </div>
            <div className="col-span-2">
              <Label htmlFor="np-name" required>Name</Label>
              <Input id="np-name" value={name} onChange={setName} placeholder="e.g. Inertial Measurement Unit" />
            </div>
            <div>
              <Label htmlFor="np-desig">Designation</Label>
              <Input id="np-desig" value={designation} onChange={setDesignation} placeholder="e.g. IMU" />
            </div>
            <div>
              <Label htmlFor="np-class" required>Part Class</Label>
              <select id="np-class" value={partClass} onChange={(e) => setPartClass(e.target.value as PartClass)}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50">
                {PART_CLASSES.map((c) => <option key={c} value={c}>{PART_CLASS_LABELS[c]}</option>)}
              </select>
            </div>
            <div>
              <Label htmlFor="np-lru" required>LRU Classification</Label>
              <select id="np-lru" value={lruClass} onChange={(e) => setLruClass(e.target.value as LRUClass)}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50">
                {LRU_CLASSES.map((c) => <option key={c} value={c}>{LRU_CLASS_LABELS[c]}</option>)}
              </select>
            </div>
            <div>
              <Label htmlFor="np-lifecycle">Lifecycle</Label>
              <select id="np-lifecycle" value={lifecycle} onChange={(e) => setLifecycle(e.target.value as LifecycleStatus)}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50">
                {LIFECYCLE_STATUSES.map((s) => <option key={s} value={s}>{LIFECYCLE_COLORS[s].label}</option>)}
              </select>
            </div>
            <div className="col-span-2">
              <Label htmlFor="np-desc">Description</Label>
              <textarea id="np-desc" rows={3} value={description} onChange={(e) => setDescription(e.target.value)}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50 resize-none" />
            </div>
          </div>
        </Section>

        <Section title="Physical">
          <div className="grid grid-cols-4 gap-3">
            <Field id="np-mass" label="Mass (kg)"   value={massKg} onChange={setMassKg} />
            <Field id="np-diml" label="L (mm)"      value={dimL} onChange={setDimL} />
            <Field id="np-dimw" label="W (mm)"      value={dimW} onChange={setDimW} />
            <Field id="np-dimh" label="H (mm)"      value={dimH} onChange={setDimH} />
          </div>
        </Section>

        <Section title="Power &amp; Voltage">
          <div className="grid grid-cols-4 gap-3">
            <Field id="np-pn-w"   label="Nominal (W)"   value={powerNominal} onChange={setPowerNominal} />
            <Field id="np-pp-w"   label="Peak (W)"      value={powerPeak} onChange={setPowerPeak} />
            <Field id="np-vmin"   label="V In Min"      value={vMin} onChange={setVMin} />
            <Field id="np-vmax"   label="V In Max"      value={vMax} onChange={setVMax} />
          </div>
        </Section>

        <Section title="Environmental Envelope">
          <div className="grid grid-cols-4 gap-3">
            <Field id="np-topmin" label="Op Temp Min (°C)"  value={tOpMin} onChange={setTOpMin} />
            <Field id="np-topmax" label="Op Temp Max (°C)"  value={tOpMax} onChange={setTOpMax} />
            <Field id="np-tstmin" label="Storage Min (°C)"  value={tStMin} onChange={setTStMin} />
            <Field id="np-tstmax" label="Storage Max (°C)"  value={tStMax} onChange={setTStMax} />
            <Field id="np-vib"    label="Vibration (Grms)"  value={vibG} onChange={setVibG} />
            <Field id="np-shock"  label="Shock (g)"         value={shockG} onChange={setShockG} />
            <Field id="np-hum"    label="Humidity Max (%)"  value={humidity} onChange={setHumidity} />
            <Field id="np-alt"    label="Altitude Max (m)"  value={altitude} onChange={setAltitude} />
          </div>
        </Section>

        <Section title="Compliance">
          <div className="grid grid-cols-2 gap-3">
            <Toggle id="np-mil810" checked={mil810} onChange={setMil810} label="MIL-STD-810 Tested" />
            <Toggle id="np-mil461" checked={mil461} onChange={setMil461} label="MIL-STD-461 Tested" />
            <Toggle id="np-rohs"   checked={rohs}   onChange={setRohs}   label="RoHS Compliant" />
            <Toggle id="np-itar"   checked={itar}   onChange={setItar}   label="ITAR Controlled" />
            <div className="col-span-2">
              <Label htmlFor="np-export">Export Classification</Label>
              <Input id="np-export" value={exportClass} onChange={setExportClass} placeholder="e.g. EAR99" />
            </div>
          </div>
        </Section>

        <Section title="Lifecycle &amp; Notes">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="np-eol">EOL Date</Label>
              <input id="np-eol" type="date" value={eolDate} onChange={(e) => setEolDate(e.target.value)}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
          </div>
          <div className="mt-3">
            <Label htmlFor="np-notes">Notes</Label>
            <textarea id="np-notes" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)}
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50 resize-none" />
          </div>
        </Section>

        <div className="flex items-center justify-end gap-2 border-t border-astra-border pt-4">
          <button type="button" onClick={() => router.push('/catalog')}
            className="rounded-lg border border-astra-border px-4 py-2 text-xs text-slate-400 hover:text-slate-200">
            Cancel
          </button>
          <button type="button" onClick={handleSave} disabled={!canSave || saving}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed">
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Plus className="h-3.5 w-3.5" aria-hidden="true" />}
            Create Part
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Local helpers ──

function Section({ title, children }: { title: React.ReactNode; children: React.ReactNode }) {
  return (
    <fieldset className="rounded-xl border border-astra-border bg-astra-surface p-4">
      <legend className="px-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
        {title}
      </legend>
      {children}
    </fieldset>
  );
}

function Label({ htmlFor, children, required }: {
  htmlFor: string; children: React.ReactNode; required?: boolean;
}) {
  return (
    <label htmlFor={htmlFor} className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">
      {children}{required && <span className="text-red-400 ml-0.5">*</span>}
    </label>
  );
}

function Input({ id, value, onChange, placeholder, type = 'text' }: {
  id: string; value: string; onChange: (v: string) => void; placeholder?: string; type?: string;
}) {
  return (
    <input id={id} type={type} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
      className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
  );
}

function Field({ id, label, value, onChange }: {
  id: string; label: string; value: string; onChange: (v: string) => void;
}) {
  return (
    <div>
      <Label htmlFor={id}>{label}</Label>
      <input id={id} type="number" inputMode="decimal" step="any" value={value} onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
    </div>
  );
}

function Toggle({ id, checked, onChange, label }: {
  id: string; checked: boolean; onChange: (v: boolean) => void; label: string;
}) {
  return (
    <label htmlFor={id} className="flex items-center gap-2 text-xs text-slate-300">
      <input id={id} type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)}
        className="rounded border-astra-border bg-astra-bg" />
      {label}
    </label>
  );
}
