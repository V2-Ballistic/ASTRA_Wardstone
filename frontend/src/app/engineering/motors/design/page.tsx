'use client';

/**
 * ASTRA — Motor Design Page (spec §5.3 — "the very nice part")
 * ==============================================================
 * File: frontend/src/app/engineering/motors/design/page.tsx
 *
 * Parametric internal-ballistics design: propellant / grain / nozzle
 * groups (SI inputs, sensible defaults prefilled) → live plots via a
 * 400 ms-debounced POST :previewDesign on every edit. Solver 422
 * details render inline; Save (role-gated) POSTs :design and shows
 * the HAROLD-assigned WPN before navigating to the new motor.
 *
 * Revision mode: /engineering/motors/design?wpn=<WPN> prefills from
 * that motor's design-origin revision (when one exists) and saves via
 * POST {wpn}/revisions:from-design instead.
 *
 * Input field names mirror backend MotorDesignInputs EXACTLY
 * (extra="forbid" on the backend — no improvised keys).
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import {
  AlertTriangle, ChevronLeft, FlaskConical, Loader2, PencilRuler, Save,
} from 'lucide-react';
import clsx from 'clsx';

import { engineeringAPI } from '@/lib/engineering-api';
import {
  type DesignPreviewResponse,
  type MotorDesignInputs,
  type MotorIngestResponse,
  type MotorRevisionSummary,
  fmtImpulse,
  fmtKg,
  fmtMPa,
  fmtSeconds,
  fmtThrust,
} from '@/lib/engineering-types';
import { formatApiError } from '@/lib/errors';
import { useHasRole } from '@/lib/auth';
import CurvePlot from '@/components/engineering/CurvePlot';
import { MotorClassBadge } from '@/components/engineering/QualityTierBadge';

// ══════════════════════════════════════
//  Form state ⇄ MotorDesignInputs
// ══════════════════════════════════════

interface FormState {
  // propellant
  density_kgpm3: string;
  a: string;
  n: string;
  k: string;
  Tc_K: string;
  cstar_mps: string;
  sigma_p: string;
  molar_mass_kgpmol: string;
  // grain (BATES)
  od_m: string;
  core_d_m: string;
  length_m: string;
  segment_count: string;
  inhibited_ends: string;
  // nozzle
  throat_d_m: string;
  exit_d_m: string;
  expansion_ratio: string;
  ambient_pressure_pa: string;
  // sim
  web_step_m: string;
  grain_temp_K: string;
}

/** Sensible APCP-ish defaults so the page renders a live motor
 *  immediately (spec §5.3 UX). */
const DEFAULT_FORM: FormState = {
  density_kgpm3: '1750',
  a: '3.5e-5',
  n: '0.36',
  k: '1.2',
  Tc_K: '',
  cstar_mps: '1520',
  sigma_p: '0.001',
  molar_mass_kgpmol: '',
  od_m: '0.075',
  core_d_m: '0.025',
  length_m: '0.12',
  segment_count: '4',
  inhibited_ends: '0',
  throat_d_m: '0.012',
  exit_d_m: '',
  expansion_ratio: '8',
  ambient_pressure_pa: '101325',
  web_step_m: '0.0001',
  grain_temp_K: '294.15',
};

function num(s: string): number | undefined {
  if (!s.trim()) return undefined;
  const v = Number(s);
  return Number.isFinite(v) ? v : undefined;
}

/** Build the exact backend payload, or a human-readable problem. */
function buildInputs(f: FormState): { inputs?: MotorDesignInputs; problem?: string } {
  const required: [string, string][] = [
    [f.density_kgpm3, 'propellant density'],
    [f.a, 'burn-rate coefficient a'],
    [f.n, 'burn-rate exponent n'],
    [f.k, 'ratio of specific heats k'],
    [f.od_m, 'grain OD'],
    [f.core_d_m, 'grain core diameter'],
    [f.length_m, 'segment length'],
    [f.segment_count, 'segment count'],
    [f.throat_d_m, 'nozzle throat diameter'],
  ];
  for (const [v, label] of required) {
    if (num(v) === undefined) return { problem: `${label} is required (numeric)` };
  }

  const cstar = num(f.cstar_mps);
  const tc = num(f.Tc_K);
  const molar = num(f.molar_mass_kgpmol);
  if (cstar === undefined && (tc === undefined || molar === undefined)) {
    return { problem: 'propellant needs c* OR (Tc AND molar mass)' };
  }
  const exitD = num(f.exit_d_m);
  const eps = num(f.expansion_ratio);
  if (exitD === undefined && eps === undefined) {
    return { problem: 'nozzle needs an exit diameter OR an expansion ratio' };
  }

  const inputs: MotorDesignInputs = {
    propellant: {
      density_kgpm3: num(f.density_kgpm3)!,
      a: num(f.a)!,
      n: num(f.n)!,
      k: num(f.k)!,
      sigma_p: num(f.sigma_p) ?? 0,
      ...(cstar !== undefined ? { cstar_mps: cstar } : {}),
      ...(tc !== undefined ? { Tc_K: tc } : {}),
      ...(molar !== undefined ? { molar_mass_kgpmol: molar } : {}),
    },
    grain: {
      type: 'BATES',
      od_m: num(f.od_m)!,
      core_d_m: num(f.core_d_m)!,
      length_m: num(f.length_m)!,
      segment_count: Math.max(1, Math.round(num(f.segment_count) ?? 1)),
      inhibited_ends: Math.min(2, Math.max(0, Math.round(num(f.inhibited_ends) ?? 0))),
    },
    nozzle: {
      throat_d_m: num(f.throat_d_m)!,
      ...(exitD !== undefined ? { exit_d_m: exitD } : {}),
      ...(eps !== undefined ? { expansion_ratio: eps } : {}),
      ambient_pressure_pa: num(f.ambient_pressure_pa) ?? 101325,
    },
    sim: {
      web_step_m: num(f.web_step_m) ?? 1e-4,
      grain_temp_K: num(f.grain_temp_K) ?? 294.15,
    },
  };
  return { inputs };
}

function inputsToForm(di: MotorDesignInputs): FormState {
  const s = (v: number | null | undefined) => (v === null || v === undefined ? '' : String(v));
  return {
    density_kgpm3: s(di.propellant?.density_kgpm3),
    a: s(di.propellant?.a),
    n: s(di.propellant?.n),
    k: s(di.propellant?.k),
    Tc_K: s(di.propellant?.Tc_K),
    cstar_mps: s(di.propellant?.cstar_mps),
    sigma_p: s(di.propellant?.sigma_p ?? 0),
    molar_mass_kgpmol: s(di.propellant?.molar_mass_kgpmol),
    od_m: s(di.grain?.od_m),
    core_d_m: s(di.grain?.core_d_m),
    length_m: s(di.grain?.length_m),
    segment_count: s(di.grain?.segment_count),
    inhibited_ends: s(di.grain?.inhibited_ends),
    throat_d_m: s(di.nozzle?.throat_d_m),
    exit_d_m: s(di.nozzle?.exit_d_m),
    expansion_ratio: s(di.nozzle?.expansion_ratio),
    ambient_pressure_pa: s(di.nozzle?.ambient_pressure_pa ?? 101325),
    web_step_m: s(di.sim?.web_step_m ?? 1e-4),
    grain_temp_K: s(di.sim?.grain_temp_K ?? 294.15),
  };
}

// ══════════════════════════════════════
//  Small form building blocks
// ══════════════════════════════════════

function FieldGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="rounded-xl border border-astra-border bg-astra-surface p-3">
      <legend className="px-1 text-[10px] font-bold uppercase tracking-widest text-slate-500">
        {title}
      </legend>
      <div className="grid grid-cols-2 gap-2.5">{children}</div>
    </fieldset>
  );
}

function NumField({ id, label, unit, value, onChange, placeholder }: {
  id: string;
  label: string;
  unit?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-0.5 block text-[10px] font-semibold text-slate-400">
        {label}{unit && <span className="ml-1 font-normal text-slate-600">({unit})</span>}
      </label>
      <input
        id={id}
        type="text"
        inputMode="decimal"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-astra-border bg-astra-bg px-2.5 py-1.5 font-mono text-xs text-slate-200 outline-none focus:border-blue-500/50"
      />
    </div>
  );
}

function SpecCell({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className="font-mono text-sm font-semibold tabular-nums text-slate-200">{value}</div>
    </div>
  );
}

// ══════════════════════════════════════
//  Page
// ══════════════════════════════════════

export default function MotorDesignPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const revisionWpn = searchParams?.get('wpn') || null;
  const canWrite = useHasRole('admin', 'project_manager', 'requirements_engineer');

  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [name, setName] = useState('');
  const [notes, setNotes] = useState('');

  const [preview, setPreview] = useState<DesignPreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState('');

  const [prefillNote, setPrefillNote] = useState('');
  const [prefillLoading, setPrefillLoading] = useState(false);

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [saved, setSaved] = useState<MotorIngestResponse | null>(null);

  const set = useCallback((key: keyof FormState) => (v: string) => {
    setForm((prev) => ({ ...prev, [key]: v }));
  }, []);

  const built = useMemo(() => buildInputs(form), [form]);

  // ── Revision mode: prefill from the existing motor's design inputs ──
  useEffect(() => {
    if (!revisionWpn) return;
    let cancelled = false;
    setPrefillLoading(true);
    engineeringAPI.getMotor(revisionWpn)
      .then(async (mRes) => {
        const m = mRes.data;
        const active = m.active_revision_id != null
          ? m.revisions.find((r) => r.id === m.active_revision_id)
          : undefined;
        const ordered: MotorRevisionSummary[] = [
          ...(active ? [active] : []),
          ...[...m.revisions].reverse(),
        ];
        const designRev = ordered.find((r) => r.origin === 'design');
        if (!designRev) {
          if (!cancelled) {
            setPrefillNote(
              `${m.wpn} has no design-origin revision (origin is CSV) — starting from defaults.`,
            );
          }
          return;
        }
        const det = await engineeringAPI.getMotorRevision(revisionWpn, designRev.rev_letter);
        if (cancelled) return;
        if (det.data.design_inputs) {
          setForm(inputsToForm(det.data.design_inputs));
          setPrefillNote(`Prefilled from revision ${designRev.rev_letter} of ${m.wpn}.`);
        }
      })
      .catch((e) => {
        if (!cancelled) setPrefillNote(formatApiError(e, 'Could not prefill from the existing motor'));
      })
      .finally(() => { if (!cancelled) setPrefillLoading(false); });
    return () => { cancelled = true; };
  }, [revisionWpn]);

  // ── Live preview: debounced 400 ms solver run on every edit ──
  useEffect(() => {
    if (!built.inputs) {
      setPreviewError(built.problem || 'Incomplete inputs');
      return;
    }
    const inputs = built.inputs;
    let cancelled = false;
    const handle = setTimeout(() => {
      setPreviewLoading(true);
      engineeringAPI.previewMotorDesign(inputs)
        .then((r) => {
          if (cancelled) return;
          setPreview(r.data);
          setPreviewError('');
        })
        .catch((e) => {
          // Solver 422 detail (e.g. "core_d_m must be < od_m") inline.
          if (!cancelled) setPreviewError(formatApiError(e, 'Solver rejected the design'));
        })
        .finally(() => { if (!cancelled) setPreviewLoading(false); });
    }, 400);
    return () => { cancelled = true; clearTimeout(handle); };
  }, [built]);

  const handleSave = useCallback(async () => {
    if (!built.inputs || saving) return;
    if (!revisionWpn && !name.trim()) {
      setSaveError('A display name is required (HAROLD owns the WPN, you own the name).');
      return;
    }
    setSaveError('');
    setSaving(true);
    try {
      const r = revisionWpn
        ? await engineeringAPI.addMotorRevisionFromDesign(revisionWpn, {
            inputs: built.inputs,
            notes: notes.trim() || undefined,
          })
        : await engineeringAPI.createMotorDesign({
            name: name.trim(),
            inputs: built.inputs,
            notes: notes.trim() || undefined,
          });
      setSaved(r.data);
      const target = `/engineering/motors/${encodeURIComponent(r.data.motor.wpn)}`;
      setTimeout(() => router.push(target), 1400);
    } catch (e) {
      setSaveError(formatApiError(e, 'Failed to save the design'));
    } finally {
      setSaving(false);
    }
  }, [built, name, notes, revisionWpn, router, saving]);

  const backHref = revisionWpn
    ? `/engineering/motors/${encodeURIComponent(revisionWpn)}`
    : '/engineering';

  return (
    <div>
      <Link href={backHref} className="mb-4 inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200">
        <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
        {revisionWpn ? `Motor ${revisionWpn}` : 'Engineering / Motors'}
      </Link>

      <div className="mb-6">
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-slate-100">
          <PencilRuler className="h-6 w-6 text-blue-400" aria-hidden="true" />
          {revisionWpn ? 'New design revision' : 'Design a motor'}
          {revisionWpn && (
            <span className="font-mono text-lg tracking-wider text-slate-400">{revisionWpn}</span>
          )}
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          BATES internal-ballistics solver — the plots re-solve as you type.
          Nothing is named or persisted until you save.
        </p>
      </div>

      {prefillLoading && (
        <div className="mb-3 flex items-center gap-2 text-xs text-slate-400">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" aria-hidden="true" />
          Loading existing design inputs…
        </div>
      )}
      {prefillNote && !prefillLoading && (
        <div role="status" className="mb-3 rounded-lg border border-blue-500/20 bg-blue-500/10 px-3 py-2 text-xs text-blue-300">
          {prefillNote}
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[400px,1fr]">
        {/* ── Left: parameter form ── */}
        <div className="space-y-4">
          <FieldGroup title="Propellant — r = a·Pcⁿ">
            <NumField id="f-density" label="Density" unit="kg/m³"
              value={form.density_kgpm3} onChange={set('density_kgpm3')} />
            <NumField id="f-a" label="Burn-rate coeff a" unit="m/(s·Paⁿ)"
              value={form.a} onChange={set('a')} />
            <NumField id="f-n" label="Exponent n" unit="0<n<1"
              value={form.n} onChange={set('n')} />
            <NumField id="f-k" label="γ (k)" value={form.k} onChange={set('k')} />
            <NumField id="f-cstar" label="c*" unit="m/s"
              value={form.cstar_mps} onChange={set('cstar_mps')}
              placeholder="or Tc + M below" />
            <NumField id="f-sigmap" label="σp temp sensitivity" unit="1/K"
              value={form.sigma_p} onChange={set('sigma_p')} />
            <NumField id="f-tc" label="Tc combustion temp" unit="K"
              value={form.Tc_K} onChange={set('Tc_K')} placeholder="optional" />
            <NumField id="f-molar" label="Exhaust molar mass" unit="kg/mol"
              value={form.molar_mass_kgpmol} onChange={set('molar_mass_kgpmol')}
              placeholder="optional" />
          </FieldGroup>

          <FieldGroup title="Grain — BATES stack">
            <NumField id="f-od" label="Outer diameter" unit="m"
              value={form.od_m} onChange={set('od_m')} />
            <NumField id="f-core" label="Core diameter" unit="m"
              value={form.core_d_m} onChange={set('core_d_m')} />
            <NumField id="f-len" label="Segment length" unit="m"
              value={form.length_m} onChange={set('length_m')} />
            <NumField id="f-segs" label="Segment count"
              value={form.segment_count} onChange={set('segment_count')} />
            <NumField id="f-inhib" label="Inhibited ends / segment" unit="0–2"
              value={form.inhibited_ends} onChange={set('inhibited_ends')} />
          </FieldGroup>

          <FieldGroup title="Nozzle">
            <NumField id="f-throat" label="Throat diameter" unit="m"
              value={form.throat_d_m} onChange={set('throat_d_m')} />
            <NumField id="f-exitd" label="Exit diameter" unit="m"
              value={form.exit_d_m} onChange={set('exit_d_m')}
              placeholder="or ε →" />
            <NumField id="f-eps" label="Expansion ratio ε" unit="Ae/At"
              value={form.expansion_ratio} onChange={set('expansion_ratio')} />
            <NumField id="f-amb" label="Ambient pressure" unit="Pa"
              value={form.ambient_pressure_pa} onChange={set('ambient_pressure_pa')} />
          </FieldGroup>

          <FieldGroup title="Simulation">
            <NumField id="f-web" label="Web-march step" unit="m"
              value={form.web_step_m} onChange={set('web_step_m')} />
            <NumField id="f-gtemp" label="Grain soak temp" unit="K"
              value={form.grain_temp_K} onChange={set('grain_temp_K')} />
          </FieldGroup>

          {/* ── Save ── */}
          <div className="rounded-xl border border-astra-border bg-astra-surface p-3">
            {!revisionWpn && (
              <div className="mb-2.5">
                <label htmlFor="f-name" className="mb-0.5 block text-[10px] font-semibold text-slate-400">
                  Display name <span className="font-normal text-slate-600">(HAROLD assigns the WPN)</span>
                </label>
                <input
                  id="f-name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. WS01 Sustainer"
                  className="w-full rounded-lg border border-astra-border bg-astra-bg px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-blue-500/50"
                />
              </div>
            )}
            <div className="mb-2.5">
              <label htmlFor="f-notes" className="mb-0.5 block text-[10px] font-semibold text-slate-400">
                Notes <span className="font-normal text-slate-600">(optional)</span>
              </label>
              <textarea
                id="f-notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-blue-500/50"
              />
            </div>

            {saveError && (
              <div role="alert" className="mb-2.5 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
                <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {saveError}
              </div>
            )}
            {saved && (
              <div role="status" className="mb-2.5 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-400">
                Named <span className="font-mono font-bold text-emerald-300">{saved.wpn}</span> by
                HAROLD — opening the motor…
              </div>
            )}

            {canWrite ? (
              <button
                type="button"
                onClick={handleSave}
                disabled={saving || !built.inputs || !!saved}
                className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
              >
                {saving
                  ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                  : <Save className="h-3.5 w-3.5" aria-hidden="true" />}
                {saving
                  ? 'Saving — HAROLD is naming it…'
                  : revisionWpn ? 'Save as next revision' : 'Save design'}
              </button>
            ) : (
              <p className="text-center text-[11px] text-slate-500">
                Saving requires admin, project manager, or requirements engineer role.
              </p>
            )}
          </div>
        </div>

        {/* ── Right: live preview ── */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-1.5 text-sm font-semibold text-slate-200">
              <FlaskConical className="h-4 w-4 text-slate-400" aria-hidden="true" />
              Live preview
            </h2>
            {previewLoading && (
              <span className="flex items-center gap-1.5 text-[11px] text-slate-500">
                <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" aria-hidden="true" />
                solving…
              </span>
            )}
          </div>

          {previewError && (
            <div role="alert" className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
              <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {previewError}
            </div>
          )}

          {preview ? (
            <>
              {/* spec sheet */}
              <div className={clsx(
                'grid grid-cols-2 gap-4 rounded-xl border border-astra-border bg-astra-surface p-4 sm:grid-cols-4 lg:grid-cols-7',
                previewError && 'opacity-50',
              )}>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-slate-500">Class</div>
                  <div className="mt-0.5"><MotorClassBadge letter={preview.motor_class} /></div>
                </div>
                <SpecCell label="Total impulse" value={fmtImpulse(preview.total_impulse_ns)} />
                <SpecCell label="Peak thrust" value={fmtThrust(preview.peak_thrust_n)} />
                <SpecCell label="Isp" value={`${preview.isp_s.toFixed(1)} s`} />
                <SpecCell label="Burn time" value={fmtSeconds(preview.burn_time_s)} />
                <SpecCell label="Max Pc" value={fmtMPa(preview.max_pchamber_pa)} />
                <SpecCell label="Prop mass" value={fmtKg(preview.prop_mass_init_kg)} />
              </div>

              {preview.warnings.length > 0 && (
                <div role="status" className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-400">
                  <ul className="list-inside list-disc space-y-0.5">
                    {preview.warnings.map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                </div>
              )}

              <div className={clsx('grid grid-cols-1 gap-4 2xl:grid-cols-2', previewError && 'opacity-50')}>
                <CurvePlot
                  title="Thrust vs time"
                  series={[{ label: 'Thrust', x: preview.time_s, y: preview.thrust_n, color: '#3B82F6' }]}
                  xLabel="t (s)" yLabel="Thrust (N)"
                  className="2xl:col-span-2" height={240}
                />
                <CurvePlot
                  title="Chamber pressure vs time"
                  series={[{
                    label: 'Pc',
                    x: preview.time_s,
                    y: preview.pchamber_pa.map((p) => p / 1e6),
                    color: '#10B981',
                  }]}
                  xLabel="t (s)" yLabel="Pc (MPa)"
                />
                <CurvePlot
                  title="Propellant mass vs time"
                  series={[{
                    label: 'mass',
                    x: preview.time_s,
                    y: preview.prop_mass_rem_kg,
                    color: '#F59E0B',
                  }]}
                  xLabel="t (s)" yLabel="mass (kg)"
                />
              </div>
            </>
          ) : !previewError ? (
            <div className="flex items-center justify-center rounded-xl border border-astra-border bg-astra-surface py-20">
              <Loader2 className="h-5 w-5 animate-spin text-blue-500" aria-label="Solving design" />
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
