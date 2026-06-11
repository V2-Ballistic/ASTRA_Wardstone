'use client';

/**
 * ASTRA — Configuration Builder (spec §8 UX)
 * ============================================
 * File: frontend/src/app/engineering/configurations/new/page.tsx
 *
 * Two modes:
 *   - New configuration  → POST /engineering/configs (HAROLD allocates
 *     the CFG WPN; the user never types one)
 *   - New revision       → ?from={wpn}&rev={rev} prefills the builder
 *     from that revision and submits to POST /configs/{wpn}/revisions
 *
 * Sections: name/description · components assembler (catalog picker —
 * only parts WITH a WPN are addable; role taxonomy dropdown; optional
 * 4×4 placement) · aero binding (deck + revision) · stage map (motor +
 * revision, ignition time, thrust axis) · optional top-assembly WPN +
 * baseline id.
 *
 * Save-time validation failures (422) arrive as a STRUCTURED
 * {message, errors:[{code,...}]} detail — each error renders as a
 * friendly line naming the affected WPNs.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import {
  AlertTriangle, Boxes, ChevronLeft, Flame, Grid3X3, Loader2, Plus,
  Save, Trash2, Wind,
} from 'lucide-react';
import clsx from 'clsx';

import { engineeringAPI } from '@/lib/engineering-api';
import {
  COMPONENT_ROLES,
  type AeroDeckDetail,
  type AeroDeckSummary,
  type ComponentRole,
  type ConfigComponentIn,
  type ConfigCreateBody,
  type ConfigStageIn,
  type ConfigValidationErrorItem,
  type MotorListItem,
} from '@/lib/engineering-types';
import { formatApiError } from '@/lib/errors';
import { useHasRole } from '@/lib/auth';
import CatalogPartPicker from '@/components/catalog/CatalogPartPicker';
import { ConfigRoleBadge } from '@/components/engineering/QualityTierBadge';
import type { CatalogPart } from '@/lib/catalog-types';

// ══════════════════════════════════════
//  Form row models (string-typed inputs)
// ══════════════════════════════════════

const IDENTITY_4X4: string[][] = [
  ['1', '0', '0', '0'],
  ['0', '1', '0', '0'],
  ['0', '0', '1', '0'],
  ['0', '0', '0', '1'],
];

interface ComponentRow {
  key: number;
  wpn: string;
  name: string;
  role: ComponentRole;
  rev: string;
  hasPlacement: boolean;
  placement: string[][];
  notes: string;
}

interface StageRow {
  key: number;
  stageNum: string;
  motorWpn: string;
  motorRevLetter: string;
  ignitionTime_s: string;
  thrustAxis: [string, string, string];
}

let rowSeq = 0;
const nextKey = () => ++rowSeq;

function placementToStrings(p?: number[][] | null): string[][] {
  if (!p || p.length !== 4) return IDENTITY_4X4.map((r) => [...r]);
  return p.map((row) => row.slice(0, 4).map((v) => String(v)));
}

/** Friendly titles for the §8 save-time validation error codes. */
const ERROR_TITLES: Record<string, string> = {
  unknown_component_wpn: 'Unknown component WPN',
  multiple_oml_components: 'More than one OML component',
  missing_oml_component: 'OML component required',
  unknown_aero_deck: 'Unknown aero deck revision',
  oml_aero_mismatch: 'Aero deck / OML mismatch',
  unknown_motor: 'Unknown motor revision',
  rollup_not_computable: 'Mass roll-up not computable',
  bad_placement: 'Invalid placement matrix',
  empty_bom: 'No components',
};

/** WPNs an error names, for the mono chips next to the message. */
function errorWpns(e: ConfigValidationErrorItem): string[] {
  const out: string[] = [];
  if (e.wpn) out.push(e.wpn);
  if (Array.isArray(e.wpns)) out.push(...e.wpns);
  if (e.motorWpn) out.push(e.motorWpn);
  if (e.deck_oml_wpn) out.push(e.deck_oml_wpn);
  if (e.component_oml_wpn) out.push(e.component_oml_wpn);
  return Array.from(new Set(out));
}

/** Extract the structured 422 error list, or null for plain errors. */
function parseValidationErrors(err: unknown): ConfigValidationErrorItem[] | null {
  const detail = (err as {
    response?: { data?: { detail?: unknown } };
  })?.response?.data?.detail;
  if (
    detail
    && typeof detail === 'object'
    && !Array.isArray(detail)
    && Array.isArray((detail as { errors?: unknown }).errors)
  ) {
    return (detail as { errors: ConfigValidationErrorItem[] }).errors;
  }
  return null;
}

const inputCls =
  'w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50 disabled:opacity-50';
const smallInputCls =
  'rounded-lg border border-astra-border bg-astra-bg px-2 py-1.5 font-mono text-xs text-slate-200 outline-none focus:border-blue-500/50 disabled:opacity-50';
const labelCls =
  'mb-1 block text-[11px] font-semibold uppercase tracking-wider text-slate-500';

function SectionCard({
  title, icon, children,
}: {
  title: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-4 rounded-xl border border-astra-border bg-astra-surface p-4">
      <h2 className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-slate-200">
        {icon}
        {title}
      </h2>
      {children}
    </section>
  );
}

// ══════════════════════════════════════
//  Page
// ══════════════════════════════════════

export default function ConfigurationBuilderPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const fromWpn = searchParams?.get('from') || null;
  const fromRev = searchParams?.get('rev') || null;
  const revisionMode = Boolean(fromWpn && fromRev);
  const canWrite = useHasRole('admin', 'project_manager', 'requirements_engineer');

  // ── identity / metadata ──
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [topAssemblyWpn, setTopAssemblyWpn] = useState('');
  const [baselineId, setBaselineId] = useState('');

  // ── components ──
  const [components, setComponents] = useState<ComponentRow[]>([]);
  const [pickerWarning, setPickerWarning] = useState('');

  // ── aero binding ──
  const [decks, setDecks] = useState<AeroDeckSummary[]>([]);
  const [decksError, setDecksError] = useState('');
  const [aeroWpn, setAeroWpn] = useState('');
  const [aeroRev, setAeroRev] = useState('');
  const [deckDetail, setDeckDetail] = useState<AeroDeckDetail | null>(null);
  const [deckLoading, setDeckLoading] = useState(false);

  // ── stage map ──
  const [motors, setMotors] = useState<MotorListItem[]>([]);
  const [motorsError, setMotorsError] = useState('');
  const [stages, setStages] = useState<StageRow[]>([]);
  const motorRevsRef = useRef<Record<string, string[]>>({});
  const [motorRevs, setMotorRevs] = useState<Record<string, string[]>>({});

  // ── prefill (revision mode) ──
  const [prefillLoading, setPrefillLoading] = useState(revisionMode);
  const [prefillError, setPrefillError] = useState('');

  // ── save ──
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [validationErrors, setValidationErrors] = useState<ConfigValidationErrorItem[]>([]);
  const [formError, setFormError] = useState('');

  // ── reference data: aero decks + motors (once) ──
  useEffect(() => {
    engineeringAPI.listAeroDecks({ limit: 200 })
      .then((r) => setDecks(r.data))
      .catch((e) => setDecksError(formatApiError(e, 'Failed to load aero decks')));
    engineeringAPI.listMotors({ limit: 200 })
      .then((r) => setMotors(r.data))
      .catch((e) => setMotorsError(formatApiError(e, 'Failed to load motors')));
  }, []);

  // ── deck revisions for the selected aero deck ──
  useEffect(() => {
    if (!aeroWpn) {
      setDeckDetail(null);
      return;
    }
    let cancelled = false;
    setDeckLoading(true);
    engineeringAPI.getAeroDeck(aeroWpn)
      .then((r) => {
        if (cancelled) return;
        setDeckDetail(r.data);
        setAeroRev((prev) => {
          const letters = r.data.revisions.map((x) => x.rev_letter);
          if (prev && letters.includes(prev)) return prev;
          return r.data.current_rev || letters[letters.length - 1] || '';
        });
      })
      .catch((e) => {
        if (!cancelled) setDecksError(formatApiError(e, 'Failed to load aero deck revisions'));
      })
      .finally(() => { if (!cancelled) setDeckLoading(false); });
    return () => { cancelled = true; };
  }, [aeroWpn]);

  // ── motor revision letters, fetched on demand + cached ──
  const ensureMotorRevs = useCallback((wpn: string) => {
    if (!wpn || motorRevsRef.current[wpn]) return;
    motorRevsRef.current[wpn] = []; // sentinel: fetch in flight
    engineeringAPI.getMotor(wpn)
      .then((r) => {
        const letters = r.data.revisions.map((x) => x.rev_letter);
        motorRevsRef.current[wpn] = letters;
        setMotorRevs((prev) => ({ ...prev, [wpn]: letters }));
        // Default any stage rows pointing at this motor with no rev.
        setStages((prev) => prev.map((s) => (
          s.motorWpn === wpn && !s.motorRevLetter
            ? { ...s, motorRevLetter: r.data.revisions.length
                ? r.data.revisions[r.data.revisions.length - 1].rev_letter
                : '' }
            : s
        )));
      })
      .catch(() => { delete motorRevsRef.current[wpn]; });
  }, []);

  // ── prefill from an existing revision (new-revision mode) ──
  useEffect(() => {
    if (!revisionMode || !fromWpn || !fromRev) return;
    let cancelled = false;
    setPrefillLoading(true);
    engineeringAPI.getConfigRevision(fromWpn, fromRev)
      .then((r) => {
        if (cancelled) return;
        const d = r.data;
        setName(d.config_name);
        setDescription(d.description || '');
        setTopAssemblyWpn(d.top_assembly_wpn || '');
        setBaselineId(d.astra_baseline_id != null ? String(d.astra_baseline_id) : '');
        setComponents(d.components.map((c) => ({
          key: nextKey(),
          wpn: c.wpn,
          name: c.name || '',
          role: (COMPONENT_ROLES as string[]).includes(c.role as string)
            ? c.role as ComponentRole : 'other',
          rev: c.rev || '',
          hasPlacement: Boolean(c.placement),
          placement: placementToStrings(c.placement),
          notes: c.notes || '',
        })));
        if (d.aero_binding) {
          setAeroWpn(d.aero_binding.wpn);
          setAeroRev(d.aero_binding.rev_letter);
        }
        setStages(d.stage_map.map((s) => ({
          key: nextKey(),
          stageNum: String(s.stageNum),
          motorWpn: s.motorWpn,
          motorRevLetter: s.motorRevLetter,
          ignitionTime_s: String(s.ignitionTime_s),
          thrustAxis: [
            String(s.thrustAxis_B?.[0] ?? 1),
            String(s.thrustAxis_B?.[1] ?? 0),
            String(s.thrustAxis_B?.[2] ?? 0),
          ],
        })));
        d.stage_map.forEach((s) => ensureMotorRevs(s.motorWpn));
        setPrefillError('');
      })
      .catch((e) => {
        if (!cancelled) {
          setPrefillError(formatApiError(e, `Failed to prefill from ${fromWpn} rev ${fromRev}`));
        }
      })
      .finally(() => { if (!cancelled) setPrefillLoading(false); });
    return () => { cancelled = true; };
  }, [ensureMotorRevs, fromRev, fromWpn, revisionMode]);

  // ── components assembler handlers ──
  const addPart = useCallback((part: CatalogPart | null) => {
    if (!part) return;
    if (!part.internal_part_number) {
      setPickerWarning(
        `${part.part_number} (${part.name}) has no WPN (internal_part_number) — `
        + 'only HAROLD-named catalog parts can join a configuration.',
      );
      return;
    }
    setPickerWarning('');
    const wpn = part.internal_part_number;
    setComponents((prev) => [...prev, {
      key: nextKey(),
      wpn,
      name: part.name,
      role: (COMPONENT_ROLES as string[]).includes(part.role || '')
        ? part.role as ComponentRole : 'other',
      rev: '',
      hasPlacement: false,
      placement: IDENTITY_4X4.map((r) => [...r]),
      notes: '',
    }]);
  }, []);

  const updateComponent = useCallback((key: number, patch: Partial<ComponentRow>) => {
    setComponents((prev) => prev.map((c) => (c.key === key ? { ...c, ...patch } : c)));
  }, []);

  const setPlacementCell = useCallback((key: number, i: number, j: number, v: string) => {
    setComponents((prev) => prev.map((c) => {
      if (c.key !== key) return c;
      const placement = c.placement.map((row) => [...row]);
      placement[i][j] = v;
      return { ...c, placement };
    }));
  }, []);

  const removeComponent = useCallback((key: number) => {
    setComponents((prev) => prev.filter((c) => c.key !== key));
  }, []);

  // ── stage map handlers ──
  const addStage = useCallback(() => {
    setStages((prev) => [...prev, {
      key: nextKey(),
      stageNum: String(prev.length + 1),
      motorWpn: '',
      motorRevLetter: '',
      ignitionTime_s: '0',
      thrustAxis: ['1', '0', '0'],
    }]);
  }, []);

  const updateStage = useCallback((key: number, patch: Partial<StageRow>) => {
    setStages((prev) => prev.map((s) => (s.key === key ? { ...s, ...patch } : s)));
  }, []);

  const removeStage = useCallback((key: number) => {
    setStages((prev) => prev.filter((s) => s.key !== key));
  }, []);

  // ── build + submit ──
  const buildBody = useCallback((): ConfigCreateBody | string => {
    if (!revisionMode && !name.trim()) return 'A configuration name is required.';
    if (components.length === 0) return 'Add at least one component.';

    const comps: ConfigComponentIn[] = [];
    for (const c of components) {
      let placement: number[][] | undefined;
      if (c.hasPlacement) {
        placement = [];
        for (const row of c.placement) {
          const parsed = row.map((v) => Number(v));
          if (parsed.some((v) => !Number.isFinite(v))) {
            return `Component ${c.wpn}: every placement cell must be a number.`;
          }
          placement.push(parsed);
        }
      }
      comps.push({
        role: c.role,
        wpn: c.wpn,
        rev: c.rev.trim() || undefined,
        name: c.name.trim() || undefined,
        placement,
        notes: c.notes.trim() || undefined,
      });
    }

    const stageMap: ConfigStageIn[] = [];
    for (const s of stages) {
      const stageNum = Number(s.stageNum);
      if (!Number.isInteger(stageNum) || stageNum < 1) {
        return 'Every stage number must be a positive integer.';
      }
      if (!s.motorWpn) return `Stage ${s.stageNum}: pick a motor.`;
      if (!s.motorRevLetter) return `Stage ${s.stageNum}: pick a motor revision.`;
      const ignition = Number(s.ignitionTime_s);
      if (!Number.isFinite(ignition)) {
        return `Stage ${s.stageNum}: ignition time must be a number.`;
      }
      const axis = s.thrustAxis.map((v) => Number(v));
      if (axis.some((v) => !Number.isFinite(v))) {
        return `Stage ${s.stageNum}: thrust axis must be three numbers.`;
      }
      stageMap.push({
        stageNum,
        motorWpn: s.motorWpn,
        motorRevLetter: s.motorRevLetter,
        ignitionTime_s: ignition,
        thrustAxis_B: axis,
      });
    }

    let astraBaselineId: number | undefined;
    if (baselineId.trim()) {
      const parsed = Number(baselineId.trim());
      if (!Number.isInteger(parsed)) return 'Baseline id must be an integer.';
      astraBaselineId = parsed;
    }

    return {
      name: name.trim(),
      description: description.trim() || undefined,
      components: comps,
      aero_binding: aeroWpn && aeroRev ? { wpn: aeroWpn, rev_letter: aeroRev } : undefined,
      stage_map: stageMap,
      top_assembly_wpn: topAssemblyWpn.trim() || undefined,
      astra_baseline_id: astraBaselineId,
    };
  }, [aeroRev, aeroWpn, baselineId, components, description, name, revisionMode, stages, topAssemblyWpn]);

  const handleSave = useCallback(async () => {
    setSaveError('');
    setValidationErrors([]);
    setFormError('');
    const body = buildBody();
    if (typeof body === 'string') {
      setFormError(body);
      return;
    }
    setSaving(true);
    try {
      const r = revisionMode && fromWpn
        ? await engineeringAPI.createConfigRevision(fromWpn, {
            description: body.description,
            components: body.components,
            aero_binding: body.aero_binding,
            stage_map: body.stage_map,
            top_assembly_wpn: body.top_assembly_wpn,
            astra_baseline_id: body.astra_baseline_id,
          })
        : await engineeringAPI.createConfig(body);
      // Success — the detail page shows the HAROLD-assigned CFG WPN.
      router.push(`/engineering/configurations/${encodeURIComponent(r.data.config_wpn)}`);
    } catch (e) {
      const structured = parseValidationErrors(e);
      if (structured) {
        setValidationErrors(structured);
        setSaveError('Save-time validation failed — fix the findings below and retry.');
      } else {
        // HAROLD outages arrive as 503 with a string detail.
        setSaveError(formatApiError(e, 'Failed to save configuration'));
      }
      setSaving(false);
    }
  }, [buildBody, fromWpn, revisionMode, router]);

  // ── derived ──
  const omlCount = useMemo(
    () => components.filter((c) => c.role === 'oml').length,
    [components],
  );

  // ── render ──
  if (!canWrite) {
    return (
      <div>
        <Link href="/engineering?tab=configurations" className="mb-4 inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200">
          <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" /> Engineering / Configurations
        </Link>
        <div role="alert" className="flex items-center gap-2 rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-400">
          <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
          Building configurations requires the admin, project_manager, or
          requirements_engineer role.
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* ── Breadcrumb ── */}
      <Link
        href={revisionMode && fromWpn
          ? `/engineering/configurations/${encodeURIComponent(fromWpn)}`
          : '/engineering?tab=configurations'}
        className="mb-4 inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200"
      >
        <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
        {revisionMode && fromWpn ? `Configuration ${fromWpn}` : 'Engineering / Configurations'}
      </Link>

      {/* ── Header ── */}
      <div className="mb-6">
        <h1 className="flex flex-wrap items-center gap-2.5 text-2xl font-bold tracking-tight text-slate-100">
          <Boxes className="h-6 w-6 text-blue-400" aria-hidden="true" />
          {revisionMode ? 'New configuration revision' : 'New configuration'}
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          {revisionMode ? (
            <>
              Based on <span className="font-mono text-slate-300">{fromWpn}</span>{' '}
              rev <span className="font-mono text-slate-300">{fromRev}</span> — HAROLD
              issues the next -REV on save. Revisions are immutable.
            </>
          ) : (
            'Assemble catalog components, an aero deck binding, and a stage map. HAROLD allocates the CFG WPN on save — you never type one.'
          )}
        </p>
      </div>

      {prefillLoading ? (
        <div className="flex items-center justify-center rounded-xl border border-astra-border bg-astra-surface py-16">
          <Loader2 className="h-5 w-5 animate-spin text-blue-500" aria-label="Prefilling from existing revision" />
        </div>
      ) : (
        <>
          {prefillError && (
            <div role="alert" className="mb-4 flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
              <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {prefillError}
            </div>
          )}

          {/* ── Identity ── */}
          <SectionCard title="Identity">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label htmlFor="cfg-name" className={labelCls}>Name</label>
                <input
                  id="cfg-name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={revisionMode}
                  placeholder="e.g. Block 1 flight vehicle"
                  className={inputCls}
                />
                {revisionMode && (
                  <p className="mt-1 text-[10px] text-slate-500">
                    Identity is fixed — a new revision keeps the configuration name.
                  </p>
                )}
              </div>
              <div>
                <label htmlFor="cfg-desc" className={labelCls}>Description (optional)</label>
                <input
                  id="cfg-desc"
                  type="text"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="What changed / what this configuration is for"
                  className={inputCls}
                />
              </div>
              <div>
                <label htmlFor="cfg-top-assembly" className={labelCls}>Top assembly WPN (optional)</label>
                <input
                  id="cfg-top-assembly"
                  type="text"
                  value={topAssemblyWpn}
                  onChange={(e) => setTopAssemblyWpn(e.target.value)}
                  placeholder="CADPORT top-level assembly WPN"
                  className={clsx(inputCls, 'font-mono')}
                />
              </div>
              <div>
                <label htmlFor="cfg-baseline" className={labelCls}>ASTRA baseline id (optional)</label>
                <input
                  id="cfg-baseline"
                  type="text"
                  inputMode="numeric"
                  value={baselineId}
                  onChange={(e) => setBaselineId(e.target.value)}
                  placeholder="e.g. 12"
                  className={clsx(inputCls, 'font-mono')}
                />
              </div>
            </div>
          </SectionCard>

          {/* ── Components assembler ── */}
          <SectionCard
            title={`Components (${components.length})`}
            icon={<Boxes className="h-4 w-4 text-blue-400" aria-hidden="true" />}
          >
            <div className="mb-3 max-w-xl">
              <CatalogPartPicker
                value={null}
                onChange={addPart}
                label="Add a catalog part"
                placeholder="Search the catalog and add a component…"
              />
              <p className="mt-1 text-[10px] text-slate-500">
                Only parts with a WPN (internal_part_number) can join a configuration.
                The roll-up needs mass + CG on every component.
              </p>
            </div>

            {pickerWarning && (
              <div role="alert" className="mb-3 flex items-center gap-2 rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-400">
                <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {pickerWarning}
              </div>
            )}

            {omlCount > 1 && (
              <div role="alert" className="mb-3 flex items-center gap-2 rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-400">
                <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
                At most one component may have the role &lsquo;oml&rsquo; — the save will be rejected.
              </div>
            )}

            {components.length === 0 ? (
              <div className="rounded-lg border border-dashed border-astra-border-light py-8 text-center text-xs text-slate-500">
                No components yet — pick catalog parts above to build the BOM.
              </div>
            ) : (
              <ul className="space-y-2" aria-label="Configuration components">
                {components.map((c) => (
                  <li key={c.key} className="rounded-lg border border-astra-border bg-astra-bg p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <ConfigRoleBadge role={c.role} />
                      <span className="font-mono text-xs font-bold tracking-wider text-slate-100">{c.wpn}</span>
                      <span className="truncate text-xs text-slate-400">{c.name}</span>
                      <div className="ml-auto flex items-center gap-1.5">
                        <label htmlFor={`role-${c.key}`} className="sr-only">
                          Role for {c.wpn}
                        </label>
                        <select
                          id={`role-${c.key}`}
                          value={c.role}
                          onChange={(e) => updateComponent(c.key, { role: e.target.value as ComponentRole })}
                          className={smallInputCls}
                        >
                          {COMPONENT_ROLES.map((r) => (
                            <option key={r} value={r}>{r}</option>
                          ))}
                        </select>
                        <label htmlFor={`rev-${c.key}`} className="sr-only">
                          Revision for {c.wpn}
                        </label>
                        <input
                          id={`rev-${c.key}`}
                          type="text"
                          value={c.rev}
                          onChange={(e) => updateComponent(c.key, { rev: e.target.value })}
                          placeholder="rev"
                          className={clsx(smallInputCls, 'w-16')}
                        />
                        <button
                          type="button"
                          onClick={() => updateComponent(c.key, { hasPlacement: !c.hasPlacement })}
                          aria-pressed={c.hasPlacement}
                          className={clsx(
                            'flex items-center gap-1 rounded-lg border px-2 py-1.5 text-[10px] font-semibold',
                            c.hasPlacement
                              ? 'border-violet-500/40 bg-violet-500/10 text-violet-300'
                              : 'border-astra-border text-slate-400 hover:text-slate-200',
                          )}
                        >
                          <Grid3X3 className="h-3 w-3" aria-hidden="true" /> Placement
                        </button>
                        <button
                          type="button"
                          onClick={() => removeComponent(c.key)}
                          aria-label={`Remove component ${c.wpn}`}
                          className="rounded-lg border border-astra-border p-1.5 text-slate-500 hover:border-red-500/40 hover:text-red-400"
                        >
                          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                      </div>
                    </div>

                    {c.hasPlacement && (
                      <div className="mt-2 border-t border-astra-border pt-2">
                        <div className="mb-1 text-[10px] uppercase tracking-wider text-slate-500">
                          4×4 placement (row-major homogeneous matrix, CADPORT transform_m convention — default identity)
                        </div>
                        <div className="grid w-fit grid-cols-4 gap-1" role="group" aria-label={`Placement matrix for ${c.wpn}`}>
                          {c.placement.map((row, i) =>
                            row.map((v, j) => (
                              <input
                                key={`${i}-${j}`}
                                type="text"
                                inputMode="decimal"
                                value={v}
                                onChange={(e) => setPlacementCell(c.key, i, j, e.target.value)}
                                aria-label={`Placement row ${i + 1} column ${j + 1}`}
                                className={clsx(smallInputCls, 'w-20 text-right')}
                              />
                            )))}
                        </div>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>

          {/* ── Aero binding ── */}
          <SectionCard
            title="Aero binding (optional)"
            icon={<Wind className="h-4 w-4 text-cyan-400" aria-hidden="true" />}
          >
            {decksError && (
              <div role="alert" className="mb-3 flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
                <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {decksError}
              </div>
            )}
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-[260px]">
                <label htmlFor="aero-deck" className={labelCls}>Aero deck</label>
                <select
                  id="aero-deck"
                  value={aeroWpn}
                  onChange={(e) => { setAeroWpn(e.target.value); setAeroRev(''); }}
                  className={inputCls}
                >
                  <option value="">None — no aero deck bound</option>
                  {decks.map((d) => (
                    <option key={d.id} value={d.wpn}>
                      {d.wpn} — {d.name}
                    </option>
                  ))}
                </select>
              </div>
              {aeroWpn && (
                <div>
                  <label htmlFor="aero-rev" className={labelCls}>Revision</label>
                  <div className="flex items-center gap-2">
                    <select
                      id="aero-rev"
                      value={aeroRev}
                      onChange={(e) => setAeroRev(e.target.value)}
                      disabled={deckLoading || !deckDetail}
                      className={clsx(inputCls, 'w-28 font-mono')}
                    >
                      {(deckDetail?.revisions ?? []).map((r) => (
                        <option key={r.id} value={r.rev_letter}>{r.rev_letter}</option>
                      ))}
                    </select>
                    {deckLoading && <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" aria-label="Loading deck revisions" />}
                  </div>
                </div>
              )}
            </div>
            {aeroWpn && omlCount === 0 && (
              <p className="mt-2 flex items-center gap-1.5 text-[11px] text-amber-400">
                <AlertTriangle className="h-3 w-3 flex-shrink-0" aria-hidden="true" />
                Binding an aero deck requires exactly one component with the role &lsquo;oml&rsquo;.
              </p>
            )}
          </SectionCard>

          {/* ── Stage map ── */}
          <SectionCard
            title={`Stage map (${stages.length})`}
            icon={<Flame className="h-4 w-4 text-orange-400" aria-hidden="true" />}
          >
            {motorsError && (
              <div role="alert" className="mb-3 flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
                <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {motorsError}
              </div>
            )}

            {stages.length === 0 ? (
              <div className="mb-3 rounded-lg border border-dashed border-astra-border-light py-6 text-center text-xs text-slate-500">
                No stages — single inert stack, or add propulsion stages below.
              </div>
            ) : (
              <ul className="mb-3 space-y-2" aria-label="Stage map rows">
                {stages.map((s) => (
                  <li key={s.key} className="flex flex-wrap items-end gap-3 rounded-lg border border-astra-border bg-astra-bg p-3">
                    <div>
                      <label htmlFor={`stage-num-${s.key}`} className={labelCls}>Stage #</label>
                      <input
                        id={`stage-num-${s.key}`}
                        type="text"
                        inputMode="numeric"
                        value={s.stageNum}
                        onChange={(e) => updateStage(s.key, { stageNum: e.target.value })}
                        className={clsx(smallInputCls, 'w-16 text-center')}
                      />
                    </div>
                    <div className="min-w-[220px]">
                      <label htmlFor={`stage-motor-${s.key}`} className={labelCls}>Motor</label>
                      <select
                        id={`stage-motor-${s.key}`}
                        value={s.motorWpn}
                        onChange={(e) => {
                          const w = e.target.value;
                          const cached = motorRevs[w];
                          updateStage(s.key, {
                            motorWpn: w,
                            // Default to the latest cached revision; the
                            // ensureMotorRevs fetch fills it otherwise.
                            motorRevLetter: cached?.length ? cached[cached.length - 1] : '',
                          });
                          ensureMotorRevs(w);
                        }}
                        className={clsx(inputCls, 'py-1.5 text-xs')}
                      >
                        <option value="">Pick a motor…</option>
                        {motors.map((m) => (
                          <option key={m.id} value={m.wpn}>{m.wpn} — {m.name}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label htmlFor={`stage-rev-${s.key}`} className={labelCls}>Rev</label>
                      <select
                        id={`stage-rev-${s.key}`}
                        value={s.motorRevLetter}
                        onChange={(e) => updateStage(s.key, { motorRevLetter: e.target.value })}
                        disabled={!s.motorWpn}
                        className={clsx(smallInputCls, 'w-20 py-2')}
                      >
                        <option value="">—</option>
                        {(motorRevs[s.motorWpn] ?? []).map((letter) => (
                          <option key={letter} value={letter}>{letter}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label htmlFor={`stage-ign-${s.key}`} className={labelCls}>Ignition (s)</label>
                      <input
                        id={`stage-ign-${s.key}`}
                        type="text"
                        inputMode="decimal"
                        value={s.ignitionTime_s}
                        onChange={(e) => updateStage(s.key, { ignitionTime_s: e.target.value })}
                        className={clsx(smallInputCls, 'w-20 text-right')}
                      />
                    </div>
                    <div>
                      <div className={labelCls}>Thrust axis (B)</div>
                      <div className="flex gap-1" role="group" aria-label={`Thrust axis for stage ${s.stageNum}`}>
                        {(['x', 'y', 'z'] as const).map((ax, i) => (
                          <input
                            key={ax}
                            type="text"
                            inputMode="decimal"
                            value={s.thrustAxis[i]}
                            onChange={(e) => {
                              const thrustAxis = [...s.thrustAxis] as [string, string, string];
                              thrustAxis[i] = e.target.value;
                              updateStage(s.key, { thrustAxis });
                            }}
                            aria-label={`Thrust axis ${ax} for stage ${s.stageNum}`}
                            className={clsx(smallInputCls, 'w-16 text-right')}
                          />
                        ))}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => removeStage(s.key)}
                      aria-label={`Remove stage ${s.stageNum}`}
                      className="ml-auto rounded-lg border border-astra-border p-1.5 text-slate-500 hover:border-red-500/40 hover:text-red-400"
                    >
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <button
              type="button"
              onClick={addStage}
              className="flex items-center gap-1.5 rounded-lg border border-astra-border px-3 py-2 text-xs font-semibold text-slate-300 hover:border-blue-500/30 hover:text-slate-100"
            >
              <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add stage
            </button>
          </SectionCard>

          {/* ── Errors + save ── */}
          {formError && (
            <div role="alert" className="mb-3 flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
              <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {formError}
            </div>
          )}

          {saveError && (
            <div role="alert" className="mb-3 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
              <div className="flex items-center gap-2 font-semibold">
                <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {saveError}
              </div>
              {validationErrors.length > 0 && (
                <ul className="mt-2 space-y-1.5">
                  {validationErrors.map((e, i) => (
                    <li key={i} className="rounded-lg bg-red-500/10 px-2.5 py-1.5">
                      <span className="font-semibold text-red-300">
                        {ERROR_TITLES[e.code] || e.code}
                      </span>
                      {errorWpns(e).map((w) => (
                        <span key={w} className="ml-2 rounded bg-red-500/15 px-1.5 py-0.5 font-mono text-[10px] text-red-200">
                          {w}
                        </span>
                      ))}
                      {e.stageNum !== undefined && (
                        <span className="ml-2 text-[10px] text-red-300/80">stage {e.stageNum}</span>
                      )}
                      {e.message && (
                        <div className="mt-0.5 text-red-400/90">{e.message}</div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <div className="mb-10 flex items-center gap-3">
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2.5 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
            >
              {saving
                ? <><Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> Saving — HAROLD is naming it…</>
                : <><Save className="h-3.5 w-3.5" aria-hidden="true" /> {revisionMode ? 'Save new revision' : 'Save configuration'}</>}
            </button>
            <span className="text-[11px] text-slate-500">
              Validation runs server-side before HAROLD allocates a WPN — an
              invalid configuration never burns a ledger index.
            </span>
          </div>
        </>
      )}
    </div>
  );
}
