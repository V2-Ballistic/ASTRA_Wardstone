'use client';

/**
 * ASTRA — Auto-Grow Ambiguity Resolution Modal
 * ============================================
 * File: frontend/src/components/AutoGrowAmbiguityModal.tsx
 *
 * Sequential modal for resolving auto-grow ambiguities. Shown when the
 * backend's /interfaces/auto-grow call returns a non-empty `ambiguities`
 * list, meaning one or more proposed wires would land between two LRUs
 * that already belong to different harnesses.
 *
 * Per Mason's spec:
 *   - One modal per ambiguity, sequential (not a single big list)
 *   - Any decision changes the state for subsequent decisions. Specifically,
 *     after the user resolves ambiguity N, we resubmit the whole batch with
 *     the accumulated decisions. The engine re-classifies every remaining
 *     pair based on the post-decision state and may no longer find some of
 *     them ambiguous at all (e.g., if the user merged A into B, later pairs
 *     that were A↔C may now be C-within-B as "extend harness" cases, no
 *     longer ambiguous).
 *   - Option C: when new_harness isn't in `valid_actions`, it's shown greyed
 *     out with the engine's explanation as a tooltip.
 *
 * Usage:
 *   const modal = useAmbiguityModal(); // hook-less, just state
 *
 *   // When an auto-grow call returns ambiguities:
 *   modal.start({
 *     projectId: 2,
 *     pairs: [...the original pairs...],
 *     ambiguities: res.data.ambiguities,
 *     onDone: (finalResult) => { ...refresh UI... },
 *   });
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import {
  AlertTriangle, X, ArrowRight, Check, Layers, Cable, Loader2,
  ChevronRight,
} from 'lucide-react';
import clsx from 'clsx';
import { interfaceAPI } from '@/lib/interface-api';
import type {
  AutoGrowAmbiguity, AmbiguityDecision, AutoGrowPair, AutoGrowResult,
} from '@/lib/interface-types';

// ══════════════════════════════════════════════════════════════
//  Types
// ══════════════════════════════════════════════════════════════

/** All the state needed to drive the modal. Owner (page) keeps this in
 *  useState and spreads into <AmbiguityModal {...state} />. */
export interface AmbiguityModalState {
  open: boolean;
  /** The project the auto-grow is happening in. Needed for resubmissions. */
  projectId: number;
  /** Original pairs submitted — re-sent with each decision batch so the
   *  engine can re-classify the still-unresolved ones. */
  pairs: AutoGrowPair[];
  /** Ambiguities still to resolve. First entry is shown. */
  pending: AutoGrowAmbiguity[];
  /** Decisions accumulated so far (one per original pair_index). */
  decisions: AmbiguityDecision[];
  /** Non-fatal error from the most recent submission. */
  error: string | null;
  /** True while the backend call is in flight. */
  submitting: boolean;
  /** Callback when the last ambiguity is resolved and the batch fully
   *  commits. Receives the final AutoGrowResult. */
  onDone: ((result: AutoGrowResult) => void) | null;
  /** Callback when the user closes the modal without finishing — UI
   *  should treat the batch as cancelled. */
  onCancelled: (() => void) | null;
}

export const initialAmbiguityState: AmbiguityModalState = {
  open: false,
  projectId: 0,
  pairs: [],
  pending: [],
  decisions: [],
  error: null,
  submitting: false,
  onDone: null,
  onCancelled: null,
};

// ══════════════════════════════════════════════════════════════
//  Hook — encapsulates the state machine
// ══════════════════════════════════════════════════════════════

/**
 * Hook that owns the modal's state and exposes handlers.
 *
 * The flow:
 *   1. Page calls `start({projectId, pairs, ambiguities, onDone})` when
 *      an initial auto-grow call came back with ambiguities.
 *   2. Modal renders ambiguities[0]. User picks a decision.
 *   3. Hook appends that decision to `decisions`, resubmits the whole
 *      batch to /interfaces/auto-grow. The backend re-classifies and
 *      either commits (empty ambiguities) or returns a new, possibly
 *      smaller ambiguity list.
 *   4. Repeat until empty or user cancels.
 */
export function useAmbiguityModal() {
  const [state, setState] = useState<AmbiguityModalState>(initialAmbiguityState);
  // F-128: a ref mirrors `state` so async handlers can read the
  // latest snapshot without smuggling values through setState
  // closures. Pre-fix `resolveCurrent` ran setState three times in
  // a row — once to optimistically update, once as a no-op
  // "trick to get the most recent decisions list," and a third
  // captured `latestXXX` closure variables — then a `setTimeout(0)`
  // hack tried to ensure the flush happened before the API call.
  // The ref makes that all unnecessary: read state synchronously
  // from `stateRef.current`, compute the new payload, do one
  // setState, fire the API call.
  const stateRef = useRef<AmbiguityModalState>(state);
  useEffect(() => { stateRef.current = state; }, [state]);

  /** Start a new ambiguity flow. Called from the page after the first
   *  auto-grow call returned ambiguities. */
  const start = useCallback((params: {
    projectId: number;
    pairs: AutoGrowPair[];
    ambiguities: AutoGrowAmbiguity[];
    onDone?: (result: AutoGrowResult) => void;
    onCancelled?: () => void;
  }) => {
    setState({
      open: true,
      projectId: params.projectId,
      pairs: params.pairs,
      pending: params.ambiguities,
      decisions: [],
      error: null,
      submitting: false,
      onDone: params.onDone || null,
      onCancelled: params.onCancelled || null,
    });
  }, []);

  /** Resolve the current ambiguity with the given action. */
  const resolveCurrent = useCallback(async (action: AmbiguityDecision['action'], newHarnessName?: string) => {
    // F-128: snapshot, compute, set once, then call. No closure
    // smuggling, no setTimeout(0), no triple-setState.
    const snap = stateRef.current;
    if (snap.pending.length === 0) return;
    const current = snap.pending[0];
    const newDecisions: AmbiguityDecision[] = [
      ...snap.decisions.filter(d => d.pair_index !== current.pair_index),
      {
        pair_index: current.pair_index,
        action,
        new_harness_name: newHarnessName,
      },
    ];
    const projectId = snap.projectId;
    const pairs = snap.pairs;
    const onDone = snap.onDone;

    setState(s => ({ ...s, decisions: newDecisions, submitting: true, error: null }));

    try {
      const res = await interfaceAPI.autoGrow({
        project_id: projectId,
        pairs,
        decisions: newDecisions,
      });
      const result: AutoGrowResult = res.data;

      if (result.ambiguities && result.ambiguities.length > 0) {
        // Still more to resolve. Update pending to the new list — the
        // backend returns the CURRENT set of unresolved ambiguities, which
        // may be smaller than before if the previous decision collapsed
        // some cases (e.g., a merge resolves more than just its own pair).
        setState(s => ({
          ...s,
          pending: result.ambiguities,
          submitting: false,
        }));
      } else {
        // Done — close modal and notify caller.
        setState(initialAmbiguityState);
        if (onDone) onDone(result);
      }
    } catch (err: any) {
      setState(s => ({
        ...s,
        submitting: false,
        error:
          err?.response?.data?.detail ||
          err?.message ||
          'Failed to submit decision',
      }));
    }
  }, []);

  /** User closed the modal without finishing. All decisions so far are
   *  discarded; nothing was committed (each resubmission only commits
   *  when ambiguities is empty). */
  const cancel = useCallback(() => {
    setState(s => {
      if (s.onCancelled) s.onCancelled();
      return initialAmbiguityState;
    });
  }, []);

  return { state, start, resolveCurrent, cancel };
}

// ══════════════════════════════════════════════════════════════
//  Modal component
// ══════════════════════════════════════════════════════════════

interface AmbiguityModalProps {
  state: AmbiguityModalState;
  onResolve: (action: AmbiguityDecision['action'], newHarnessName?: string) => void;
  onCancel: () => void;
}

export function AutoGrowAmbiguityModal({ state, onResolve, onCancel }: AmbiguityModalProps) {
  // Picked action (radio button state) for the current ambiguity
  const [picked, setPicked] = useState<AmbiguityDecision['action']>('merge_into_a');
  const [newHarnessName, setNewHarnessName] = useState('');

  // Reset local state when the displayed ambiguity changes
  useEffect(() => {
    if (state.pending.length > 0) {
      const current = state.pending[0];
      // Default to the first valid action (usually merge_into_a)
      const firstValid = (current.valid_actions || []).find(a => a !== 'cancel') as AmbiguityDecision['action'];
      setPicked(firstValid || 'cancel');
      // Pre-fill name with a reasonable default (A+B descriptor)
      setNewHarnessName(
        `${current.from_lru_unit_designation}-${current.to_lru_unit_designation} direct`
      );
    }
  }, [state.pending]);

  // Close on Escape
  useEffect(() => {
    if (!state.open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !state.submitting) onCancel();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [state.open, state.submitting, onCancel]);

  if (!state.open || state.pending.length === 0) return null;

  const current = state.pending[0];
  const resolvedCount = state.decisions.length;
  const totalCount = resolvedCount + state.pending.length;
  const validActions = current.valid_actions || [];
  const newHarnessAllowed = validActions.includes('new_harness');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="w-full max-w-2xl rounded-xl border border-amber-500/30 bg-astra-surface shadow-2xl">
        {/* ── Header ── */}
        <div className="flex items-start justify-between gap-4 px-5 py-4 border-b border-astra-border">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-400 flex-shrink-0 mt-0.5" />
            <div>
              <h3 className="text-sm font-bold text-slate-100">
                Resolve Harness Ambiguity
              </h3>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Decision {resolvedCount + 1} of {totalCount} —{' '}
                connecting pins between{' '}
                <span className="font-mono text-cyan-400">{current.from_lru_unit_designation}</span>
                {' '}and{' '}
                <span className="font-mono text-cyan-400">{current.to_lru_unit_designation}</span>
              </p>
            </div>
          </div>
          <button onClick={onCancel} disabled={state.submitting}
            className="rounded p-1 text-slate-500 hover:text-slate-200 disabled:opacity-40">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* ── Body ── */}
        <div className="px-5 py-4">
          {/* Plain-English explanation */}
          <p className="text-[13px] text-slate-300 leading-relaxed mb-4">
            This wire would connect two LRUs that are already on different harnesses.
            What should happen?
          </p>

          {/* Harness A / Harness B comparison cards */}
          <div className="grid grid-cols-2 gap-3 mb-4">
            <HarnessCard
              label="Harness A"
              name={current.harness_a_name}
              id={current.harness_a_id}
              wireCount={current.harness_a_wire_count}
              endpointCount={current.harness_a_endpoint_count}
              lrus={current.harness_a_lru_designations}
            />
            <HarnessCard
              label="Harness B"
              name={current.harness_b_name}
              id={current.harness_b_id}
              wireCount={current.harness_b_wire_count}
              endpointCount={current.harness_b_endpoint_count}
              lrus={current.harness_b_lru_designations}
            />
          </div>

          {/* Action picker */}
          <div className="space-y-2 mb-4">
            <ActionRadio
              id="merge_into_a"
              picked={picked}
              onPick={setPicked}
              label="Merge Harness B into Harness A"
              description={`All wires + endpoints from "${current.harness_b_name}" fold into "${current.harness_a_name}". B is deleted.`}
              disabled={!validActions.includes('merge_into_a')}
            />
            <ActionRadio
              id="merge_into_b"
              picked={picked}
              onPick={setPicked}
              label="Merge Harness A into Harness B"
              description={`All wires + endpoints from "${current.harness_a_name}" fold into "${current.harness_b_name}". A is deleted.`}
              disabled={!validActions.includes('merge_into_b')}
            />
            <ActionRadio
              id="new_harness"
              picked={picked}
              onPick={setPicked}
              label="Create a new harness for this wire"
              description={
                newHarnessAllowed
                  ? 'Keep both existing harnesses untouched. This wire goes on a separate new harness.'
                  : (current.new_harness_disallowed_reason ||
                     'Not available — both connectors are already on other harnesses.')
              }
              disabled={!newHarnessAllowed}
              greyedReason={!newHarnessAllowed ? (current.new_harness_disallowed_reason ?? undefined) : undefined}
            />
            {/* Name input shown only when new_harness is picked + allowed */}
            {picked === 'new_harness' && newHarnessAllowed && (
              <div className="ml-7 rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
                <label className="block text-[10px] uppercase tracking-wider text-slate-500 mb-1.5 font-semibold">
                  Harness Name
                </label>
                <input
                  type="text"
                  value={newHarnessName}
                  onChange={e => setNewHarnessName(e.target.value)}
                  className="w-full rounded-md border border-astra-border bg-astra-bg px-3 py-1.5 text-sm text-slate-100 outline-none focus:border-blue-500/50"
                  placeholder="e.g. FCC-IMU Direct"
                />
              </div>
            )}
            <ActionRadio
              id="cancel"
              picked={picked}
              onPick={setPicked}
              label="Skip this wire"
              description="Don't create a wire for this pair. Other pairs in the batch still proceed normally."
              disabled={false}
              muted
            />
          </div>

          {/* Error banner (e.g., backend rejected the decision) */}
          {state.error && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 mb-4">
              <p className="text-[11px] text-red-400 flex items-start gap-2">
                <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" />
                <span>{state.error}</span>
              </p>
            </div>
          )}
        </div>

        {/* ── Footer ── */}
        <div className="flex items-center justify-between px-5 py-3 border-t border-astra-border bg-astra-surface-alt/50">
          <span className="text-[11px] text-slate-500">
            {state.pending.length > 1
              ? `${state.pending.length - 1} more after this`
              : 'Last one'}
          </span>
          <div className="flex gap-2">
            <button
              onClick={onCancel}
              disabled={state.submitting}
              className="rounded-lg border border-astra-border px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-astra-surface-alt disabled:opacity-40">
              Cancel Batch
            </button>
            <button
              onClick={() => onResolve(picked, picked === 'new_harness' ? newHarnessName : undefined)}
              disabled={state.submitting}
              className="flex items-center gap-1.5 rounded-lg bg-amber-500 px-4 py-1.5 text-xs font-semibold text-slate-950 hover:bg-amber-400 disabled:opacity-40">
              {state.submitting ? (
                <><Loader2 className="h-3 w-3 animate-spin" /> Submitting…</>
              ) : (
                <>Apply & Continue <ChevronRight className="h-3 w-3" /></>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
//  Sub-components
// ══════════════════════════════════════════════════════════════

function HarnessCard({ label, name, id, wireCount, endpointCount, lrus }: {
  label: string;
  name: string;
  id: number;
  wireCount: number;
  endpointCount: number;
  lrus: string[];
}) {
  return (
    <div className="rounded-lg border border-astra-border bg-astra-bg p-3">
      <div className="flex items-center gap-2 mb-1.5">
        <Cable className="h-3.5 w-3.5 text-emerald-400" />
        <span className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
          {label}
        </span>
      </div>
      <p className="text-[13px] font-semibold text-slate-100 truncate" title={name}>
        {name}
      </p>
      <p className="text-[10px] font-mono text-slate-600 mb-2">id: {id}</p>
      <div className="flex items-center gap-3 text-[11px] text-slate-400">
        <span>{wireCount} wire{wireCount === 1 ? '' : 's'}</span>
        <span className="text-slate-700">·</span>
        <span>{endpointCount} endpoint{endpointCount === 1 ? '' : 's'}</span>
      </div>
      {lrus.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {lrus.map(lru => (
            <span
              key={lru}
              className="rounded-full bg-astra-surface-alt px-2 py-0.5 text-[10px] font-mono text-cyan-300">
              {lru}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function ActionRadio({
  id, picked, onPick, label, description, disabled, muted, greyedReason,
}: {
  id: AmbiguityDecision['action'];
  picked: AmbiguityDecision['action'];
  onPick: (a: AmbiguityDecision['action']) => void;
  label: string;
  description: string;
  disabled: boolean;
  muted?: boolean;
  greyedReason?: string;
}) {
  const selected = picked === id;
  return (
    <label
      // Tooltip via title attribute shows the disallowed reason on hover.
      // Keeps implementation simple — no popover machinery for a rare case.
      title={disabled && greyedReason ? greyedReason : undefined}
      className={clsx(
        'flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition',
        selected && !disabled
          ? 'border-amber-500/50 bg-amber-500/5'
          : 'border-astra-border bg-astra-surface-alt hover:border-slate-600',
        disabled && 'cursor-not-allowed opacity-40 hover:border-astra-border',
        muted && !selected && 'opacity-75',
      )}>
      <input
        type="radio"
        checked={selected}
        disabled={disabled}
        onChange={() => !disabled && onPick(id)}
        className="mt-0.5 accent-amber-500"
      />
      <div className="flex-1 min-w-0">
        <div className="text-[12px] font-semibold text-slate-100">{label}</div>
        <div className="text-[11px] text-slate-400 leading-relaxed mt-0.5">{description}</div>
      </div>
    </label>
  );
}
