'use client';

/**
 * ASTRA — Connection Builder Wizard (INTF-002 Phase 4 — spec §15)
 * =================================================================
 * File: frontend/src/components/connection-builder/ConnectionBuilder.tsx
 *
 * Four-step wizard:
 *   1. Pick source unit
 *   2. Pick target unit
 *   3. Auto-suggest (calls cb_auto_suggest, surfaces AutoWireResult)
 *   4. Review & commit (HarnessAssignmentForm + cb_commit)
 *
 * Direction-conflict UI per spec §15.1 lives in <PinPairingMatrix>.
 * LRU-validation banner per spec §15.2 lives at the top of the wizard.
 */

import { useEffect, useMemo, useState } from 'react';
import {
  ChevronRight, ChevronLeft, Loader2, AlertTriangle, Check, Cable,
  GitBranch, Package, Sparkles,
} from 'lucide-react';
import clsx from 'clsx';

import { interfaceAPI } from '@/lib/interface-api';
import { formatApiError } from '@/lib/errors';
import type {
  UnitSummary, AutoWireResult, CbHarnessMetadata,
  CbStartResponse,
} from '@/lib/interface-types';
import { useAuth } from '@/lib/auth';

import PinPairingMatrix from './PinPairingMatrix';
import HarnessAssignmentForm from './HarnessAssignmentForm';

// ══════════════════════════════════════════════════════════════
//  Props + step type
// ══════════════════════════════════════════════════════════════

export interface ConnectionBuilderProps {
  projectId: number;
  /** Optional pre-pick for source unit. */
  initialSourceUnitId?: number;
  /** Optional pre-pick for target unit. */
  initialTargetUnitId?: number;
  /** Called after a successful commit; receives the new harness id. */
  onCommitted?: (harnessId: number, interfaceId: number) => void;
  /** Optional cancel/exit hook. */
  onCancel?: () => void;
}

type Step = 'pick_source' | 'pick_target' | 'auto_suggest' | 'review_commit';

const STEP_ORDER: Step[] = ['pick_source', 'pick_target', 'auto_suggest', 'review_commit'];
const STEP_LABEL: Record<Step, string> = {
  pick_source: 'Pick Source',
  pick_target: 'Pick Target',
  auto_suggest: 'Auto-suggest',
  review_commit: 'Review & Commit',
};

// ══════════════════════════════════════════════════════════════
//  Component
// ══════════════════════════════════════════════════════════════

export default function ConnectionBuilder({
  projectId,
  initialSourceUnitId,
  initialTargetUnitId,
  onCommitted,
  onCancel,
}: ConnectionBuilderProps) {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';

  const [step, setStep] = useState<Step>('pick_source');
  const [units, setUnits] = useState<UnitSummary[]>([]);
  const [unitsLoading, setUnitsLoading] = useState(false);
  const [unitsError, setUnitsError] = useState<string | null>(null);

  const [sourceUnitId, setSourceUnitId] = useState<number | null>(
    initialSourceUnitId ?? null
  );
  const [targetUnitId, setTargetUnitId] = useState<number | null>(
    initialTargetUnitId ?? null
  );

  // Created on entering Step 3 — persists to Step 4 for the commit call.
  const [draftInterface, setDraftInterface] = useState<CbStartResponse | null>(null);
  const [autoResult, setAutoResult] = useState<AutoWireResult | null>(null);
  const [autoLoading, setAutoLoading] = useState(false);
  const [autoError, setAutoError] = useState<string | null>(null);

  const [acceptedPinIds, setAcceptedPinIds] = useState<Set<number>>(new Set());
  const [harnessMeta, setHarnessMeta] = useState<CbHarnessMetadata>({
    name: '', cable_type: '', overall_length_m: undefined,
    jacket_color: '', shield_type: '', description: '',
  });
  const [committing, setCommitting] = useState(false);
  const [commitError, setCommitError] = useState<string | null>(null);

  // ── Fetch units once on mount ──
  useEffect(() => {
    let cancelled = false;
    async function load() {
      setUnitsLoading(true);
      setUnitsError(null);
      try {
        const resp = await interfaceAPI.listUnits(projectId);
        if (cancelled) return;
        setUnits(resp.data);
      } catch (e: any) {
        if (cancelled) return;
        setUnitsError(e?.message ?? 'Failed to load units.');
      } finally {
        if (!cancelled) setUnitsLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [projectId]);

  // ── Derived: source / target unit objects ──
  const srcUnit = useMemo(
    () => units.find((u) => u.id === sourceUnitId) ?? null,
    [units, sourceUnitId],
  );
  const tgtUnit = useMemo(
    () => units.find((u) => u.id === targetUnitId) ?? null,
    [units, targetUnitId],
  );

  // ── Auto-default the harness name once we have both units ──
  useEffect(() => {
    if (srcUnit && tgtUnit && !harnessMeta.name) {
      setHarnessMeta((m) => ({
        ...m,
        name: `${srcUnit.designation} ↔ ${tgtUnit.designation}`,
      }));
    }
  }, [srcUnit, tgtUnit, harnessMeta.name]);

  // ── Pre-accept all "matched" rows when the AutoWireResult arrives ──
  useEffect(() => {
    if (autoResult) {
      setAcceptedPinIds(
        new Set(autoResult.proposed_wires.map((pw) => pw.source_pin.id))
      );
    }
  }, [autoResult]);

  // ── Step transition: when entering Step 3, start the draft + suggest ──
  async function enterAutoSuggestStep() {
    if (sourceUnitId === null || targetUnitId === null) return;
    setStep('auto_suggest');
    setAutoLoading(true);
    setAutoError(null);
    try {
      // Start a new draft Interface
      const start = await interfaceAPI.cbStart({
        project_id: projectId,
        source_unit_id: sourceUnitId,
        target_unit_id: targetUnitId,
      });
      setDraftInterface(start.data);
      // Run auto-wire
      const suggest = await interfaceAPI.cbAutoSuggest(start.data.interface_id);
      setAutoResult(suggest.data);
    } catch (e: any) {
      setAutoError(formatApiError(e, 'Failed to auto-suggest wires.'));
    } finally {
      setAutoLoading(false);
    }
  }

  function toggleAccept(pinId: number) {
    setAcceptedPinIds((prev) => {
      const next = new Set(prev);
      if (next.has(pinId)) next.delete(pinId);
      else next.add(pinId);
      return next;
    });
  }

  async function handleCommit() {
    if (!draftInterface || !autoResult) return;
    if (!harnessMeta.name) {
      setCommitError('Harness name is required.');
      return;
    }
    const acceptedWires = autoResult.proposed_wires
      .filter((pw) => acceptedPinIds.has(pw.source_pin.id))
      .map((pw) => ({
        source_pin_id: pw.source_pin.id,
        target_pin_id: pw.target_pin.id,
        wire_gauge: pw.suggestion.gauge,
        wire_color: pw.suggestion.color,
        wire_type: 'signal_single',
        length_m: harnessMeta.overall_length_m,
      }));
    if (acceptedWires.length === 0) {
      setCommitError('Pick at least one wire to commit.');
      return;
    }
    setCommitting(true);
    setCommitError(null);
    try {
      const resp = await interfaceAPI.cbCommit(draftInterface.interface_id, {
        accepted_wires: acceptedWires,
        harness: harnessMeta,
      });
      onCommitted?.(resp.data.harness_id, draftInterface.interface_id);
    } catch (e: any) {
      setCommitError(formatApiError(e, 'Commit failed.'));
    } finally {
      setCommitting(false);
    }
  }

  function goPrev() {
    const idx = STEP_ORDER.indexOf(step);
    if (idx > 0) setStep(STEP_ORDER[idx - 1]);
  }

  function canGoNext(): boolean {
    if (step === 'pick_source') return sourceUnitId !== null;
    if (step === 'pick_target') return targetUnitId !== null;
    if (step === 'auto_suggest') return autoResult !== null && !autoLoading;
    return false;
  }

  function goNext() {
    if (step === 'pick_source') setStep('pick_target');
    else if (step === 'pick_target') enterAutoSuggestStep();
    else if (step === 'auto_suggest') setStep('review_commit');
  }

  // ══════════════════════════════════════
  //  Render
  // ══════════════════════════════════════

  return (
    <div className="space-y-4">
      {/* Step pill nav */}
      <div className="flex items-center gap-2 text-xs">
        {STEP_ORDER.map((s, i) => (
          <span
            key={s}
            className={clsx(
              'flex items-center gap-1.5 rounded-full border px-3 py-1',
              step === s
                ? 'border-blue-500/60 bg-blue-500/10 text-blue-300'
                : i < STEP_ORDER.indexOf(step)
                ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
                : 'border-astra-border text-slate-500',
            )}
          >
            {i < STEP_ORDER.indexOf(step) ? (
              <Check className="h-3 w-3" />
            ) : (
              <span className="font-mono text-[10px]">{i + 1}</span>
            )}
            {STEP_LABEL[s]}
          </span>
        ))}
      </div>

      {/* LRU-validation banner per spec §15.2 — top of wizard */}
      {autoResult && autoResult.lru_validation_errors.length > 0 && (
        <div
          role="alert"
          className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-200"
        >
          <div className="mb-1 flex items-center gap-1.5 font-semibold">
            <AlertTriangle className="h-3.5 w-3.5" />
            Cannot auto-wire — fix LRU endpoint problems first
          </div>
          <ul className="list-disc space-y-0.5 pl-5">
            {autoResult.lru_validation_errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
          <div className="mt-2 text-[11px] text-rose-300/80">
            Re-pick units or correct cross-project membership before retrying.
          </div>
        </div>
      )}

      {/* ── Step 1: pick source unit ── */}
      {step === 'pick_source' && (
        <UnitPicker
          title="Step 1 — Pick the source unit"
          icon={<Package className="h-4 w-4 text-blue-400" />}
          units={units}
          selectedId={sourceUnitId}
          onSelect={setSourceUnitId}
          excludeId={targetUnitId}
          loading={unitsLoading}
          error={unitsError}
        />
      )}

      {/* ── Step 2: pick target unit ── */}
      {step === 'pick_target' && (
        <UnitPicker
          title="Step 2 — Pick the target unit"
          icon={<Package className="h-4 w-4 text-emerald-400" />}
          units={units}
          selectedId={targetUnitId}
          onSelect={setTargetUnitId}
          excludeId={sourceUnitId}
          loading={unitsLoading}
          error={unitsError}
        />
      )}

      {/* ── Step 3: auto-suggest ── */}
      {step === 'auto_suggest' && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
            <Sparkles className="h-4 w-4 text-amber-400" />
            Step 3 — Auto-suggest wires (three-way validated)
          </div>
          {autoLoading && (
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Running three-way auto-wire on {srcUnit?.designation} ↔{' '}
              {tgtUnit?.designation}…
            </div>
          )}
          {autoError && (
            <div
              role="alert"
              className="rounded border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-300"
            >
              {autoError}
            </div>
          )}
          {autoResult && (
            <>
              <div className="grid grid-cols-2 gap-2 text-xs md:grid-cols-7">
                {Object.entries(autoResult.summary).map(([k, v]) => (
                  <div
                    key={k}
                    className="rounded border border-astra-border bg-astra-bg-3 px-2 py-1.5"
                  >
                    <div className="text-[10px] uppercase text-slate-500">
                      {k.replace(/_/g, ' ')}
                    </div>
                    <div className="text-base font-semibold text-slate-100">{v}</div>
                  </div>
                ))}
              </div>
              <PinPairingMatrix
                result={autoResult}
                acceptedPinIds={acceptedPinIds}
                onToggleAccept={toggleAccept}
                isAdmin={isAdmin}
                onConflictAction={(c, action) => {
                  // Log + toast for now — real "mark target input" lives in the
                  // pin detail page; "skip" + "override" are no-ops at this step
                  // because rows are already excluded from acceptedPinIds.
                  /* eslint-disable no-console */
                  console.info('cb conflict action', action, c);
                }}
              />
            </>
          )}
        </div>
      )}

      {/* ── Step 4: review & commit ── */}
      {step === 'review_commit' && autoResult && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
            <Cable className="h-4 w-4 text-emerald-400" />
            Step 4 — Confirm harness + commit
          </div>
          <div className="rounded border border-astra-border bg-astra-bg-3 p-3 text-xs text-slate-300">
            <span className="font-semibold text-slate-100">{acceptedPinIds.size}</span> wires
            will be created on a new harness between{' '}
            <span className="font-semibold text-blue-300">{srcUnit?.designation}</span>{' '}
            and{' '}
            <span className="font-semibold text-emerald-300">{tgtUnit?.designation}</span>.
          </div>
          <HarnessAssignmentForm
            initial={harnessMeta}
            onChange={setHarnessMeta}
          />
          {commitError && (
            <div
              role="alert"
              className="rounded border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-300"
            >
              {commitError}
            </div>
          )}
        </div>
      )}

      {/* Footer nav */}
      <div className="flex items-center justify-between border-t border-astra-border pt-3">
        <button
          type="button"
          onClick={onCancel}
          className="text-xs text-slate-400 hover:text-slate-200"
        >
          Cancel
        </button>
        <div className="flex items-center gap-2">
          {step !== 'pick_source' && step !== 'auto_suggest' && (
            <button
              type="button"
              onClick={goPrev}
              className="inline-flex items-center gap-1 rounded border border-astra-border px-3 py-1.5 text-xs text-slate-300 hover:bg-astra-bg-3"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              Back
            </button>
          )}
          {step !== 'review_commit' && (
            <button
              type="button"
              onClick={goNext}
              disabled={!canGoNext()}
              className="inline-flex items-center gap-1 rounded bg-blue-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-400 disabled:cursor-not-allowed disabled:bg-slate-700"
            >
              Next
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          )}
          {step === 'review_commit' && (
            <button
              type="button"
              onClick={handleCommit}
              disabled={committing || acceptedPinIds.size === 0 || !harnessMeta.name}
              className="inline-flex items-center gap-1 rounded bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-400 disabled:cursor-not-allowed disabled:bg-slate-700"
            >
              {committing ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Check className="h-3.5 w-3.5" />
              )}
              Commit harness
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
//  Subcomponent — UnitPicker
// ══════════════════════════════════════════════════════════════

interface UnitPickerProps {
  title: string;
  icon: React.ReactNode;
  units: UnitSummary[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  excludeId?: number | null;
  loading: boolean;
  error: string | null;
}

function UnitPicker({
  title, icon, units, selectedId, onSelect, excludeId, loading, error,
}: UnitPickerProps) {
  const filtered = units.filter((u) => u.id !== excludeId);
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
        {icon}
        {title}
      </div>
      {loading && (
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Loading units…
        </div>
      )}
      {error && (
        <div
          role="alert"
          className="rounded border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-300"
        >
          {error}
        </div>
      )}
      {!loading && filtered.length === 0 && (
        <div className="rounded border border-astra-border bg-astra-bg-3 p-4 text-xs text-slate-400">
          No units available. Create one via the Add Unit button on the
          interfaces page.
        </div>
      )}
      <div className="grid grid-cols-1 gap-2 md:grid-cols-2 lg:grid-cols-3">
        {filtered.map((u) => (
          <button
            key={u.id}
            type="button"
            onClick={() => onSelect(u.id)}
            className={clsx(
              'rounded-lg border p-3 text-left text-xs transition',
              selectedId === u.id
                ? 'border-blue-500/60 bg-blue-500/10'
                : 'border-astra-border bg-astra-bg-3 hover:border-astra-border-subtle',
            )}
          >
            <div className="flex items-center gap-1.5">
              <GitBranch className="h-3 w-3 text-slate-500" />
              <span className="font-mono text-[10px] text-slate-500">
                {u.unit_id}
              </span>
            </div>
            <div className="mt-1 font-semibold text-slate-100">{u.name}</div>
            <div className="text-slate-400">{u.designation}</div>
            <div className="mt-1 text-[10px] text-slate-500">
              {u.unit_type} · {u.part_number}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
