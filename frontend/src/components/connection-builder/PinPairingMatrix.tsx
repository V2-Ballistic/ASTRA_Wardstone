'use client';

/**
 * ASTRA — Pin Pairing Matrix (INTF-002 Phase 4)
 * ===============================================
 * File: frontend/src/components/connection-builder/PinPairingMatrix.tsx
 *
 * Visualises the AutoWireResult as a per-row table of source pins with
 * status badges + per-cell direction-conflict UI per spec §15.1:
 *   - green = matched (proposed wire)
 *   - yellow = ambiguous (multiple targets matched the same name)
 *   - red = direction conflict (Check #2 failed)
 *   - gray = unmatched (no target candidate)
 *
 * For direction-conflict rows the user gets three actions:
 *   - Override (admin only — disabled for non-admins)
 *   - Mark target as input
 *   - Skip
 */

import { useMemo, useState } from 'react';
import {
  Check, AlertTriangle, ChevronRight, X, ShieldOff, ArrowDownToLine, SkipForward,
  HelpCircle,
} from 'lucide-react';
import clsx from 'clsx';

import type {
  AutoWireResult,
  CbProposedWire,
  CbDirectionConflict,
  CbAmbiguousMatch,
  CbPinSummary,
} from '@/lib/interface-types';

// ══════════════════════════════════════════════════════════════
//  Props
// ══════════════════════════════════════════════════════════════

export interface PinPairingMatrixProps {
  result: AutoWireResult;
  /** Toggle per-pin acceptance for the commit step. */
  acceptedPinIds: Set<number>;
  onToggleAccept: (sourcePinId: number) => void;
  /** Whether the current user has admin role (controls Override action). */
  isAdmin: boolean;
  /** Called when the user picks an action on a direction-conflict cell. */
  onConflictAction?: (
    conflict: CbDirectionConflict,
    action: 'override' | 'mark_target_input' | 'skip',
  ) => void;
}

type RowStatus = 'matched' | 'ambiguous' | 'conflict' | 'unmatched';

interface MatrixRow {
  status: RowStatus;
  source_pin: CbPinSummary;
  target_pin?: CbPinSummary;
  proposed?: CbProposedWire;
  ambiguous?: CbAmbiguousMatch;
  conflict?: CbDirectionConflict;
}

// ══════════════════════════════════════════════════════════════
//  Helpers
// ══════════════════════════════════════════════════════════════

const STATUS_COLOR: Record<RowStatus, string> = {
  matched:    'bg-emerald-500/10 border-emerald-500/30 text-emerald-300',
  ambiguous:  'bg-amber-500/10 border-amber-500/30 text-amber-300',
  conflict:   'bg-rose-500/10 border-rose-500/30 text-rose-300',
  unmatched:  'bg-slate-500/10 border-slate-600/30 text-slate-400',
};

const STATUS_LABEL: Record<RowStatus, string> = {
  matched: 'Matched',
  ambiguous: 'Ambiguous',
  conflict: 'Direction conflict',
  unmatched: 'No match',
};

// ══════════════════════════════════════════════════════════════
//  Component
// ══════════════════════════════════════════════════════════════

export default function PinPairingMatrix({
  result, acceptedPinIds, onToggleAccept, isAdmin, onConflictAction,
}: PinPairingMatrixProps) {
  const [expandedSource, setExpandedSource] = useState<number | null>(null);

  /**
   * Flatten the AutoWireResult into a unified per-source-pin row list. Each
   * source pin appears in exactly one of {proposed, ambiguous, conflict,
   * unmatched_source} so we can render them in a single table.
   */
  const rows = useMemo<MatrixRow[]>(() => {
    const out: MatrixRow[] = [];
    for (const pw of result.proposed_wires) {
      out.push({
        status: 'matched',
        source_pin: pw.source_pin,
        target_pin: pw.target_pin,
        proposed: pw,
      });
    }
    for (const am of result.ambiguous) {
      out.push({
        status: 'ambiguous',
        source_pin: am.source_pin,
        ambiguous: am,
      });
    }
    for (const dc of result.direction_conflicts) {
      out.push({
        status: 'conflict',
        source_pin: dc.source_pin,
        target_pin: dc.target_pin,
        conflict: dc,
      });
    }
    for (const sp of result.unmatched_source) {
      out.push({
        status: 'unmatched',
        source_pin: sp,
      });
    }
    return out.sort((a, b) =>
      (a.source_pin.connector_designator + a.source_pin.pin_number).localeCompare(
        b.source_pin.connector_designator + b.source_pin.pin_number,
      ),
    );
  }, [result]);

  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-astra-border bg-astra-bg-3 p-8 text-center text-sm text-slate-400">
        No source pins to evaluate. Make sure the source unit has connectors and
        pins with internal_signal_name populated.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-astra-border bg-astra-bg-3">
      <table className="w-full text-xs" role="grid" aria-label="Pin pairing matrix">
        <thead className="bg-astra-bg-4 text-slate-400">
          <tr>
            <th className="px-3 py-2 text-left">Accept</th>
            <th className="px-3 py-2 text-left">Source pin</th>
            <th className="px-3 py-2 text-left">Signal</th>
            <th className="px-3 py-2 text-left">→ Target pin</th>
            <th className="px-3 py-2 text-left">Status</th>
            <th className="px-3 py-2 text-left">Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => {
            const accepted = acceptedPinIds.has(row.source_pin.id);
            const acceptable = row.status === 'matched';
            return (
              <tr
                key={`${row.source_pin.id}-${idx}`}
                className={clsx(
                  'border-t border-astra-border',
                  STATUS_COLOR[row.status],
                )}
              >
                <td className="px-3 py-2 align-top">
                  <input
                    type="checkbox"
                    aria-label={`Accept wire from ${row.source_pin.pin_number}`}
                    checked={accepted}
                    disabled={!acceptable}
                    onChange={() => onToggleAccept(row.source_pin.id)}
                    className="h-4 w-4 cursor-pointer accent-emerald-500 disabled:cursor-not-allowed disabled:opacity-30"
                  />
                </td>
                <td className="px-3 py-2 align-top font-mono text-slate-200">
                  {row.source_pin.connector_designator}-{row.source_pin.pin_number}
                  <div className="text-[10px] text-slate-500">
                    {row.source_pin.direction}
                  </div>
                </td>
                <td className="px-3 py-2 align-top text-slate-200">
                  {row.source_pin.internal_signal_name || '—'}
                </td>
                <td className="px-3 py-2 align-top font-mono text-slate-200">
                  {row.target_pin ? (
                    <>
                      {row.target_pin.connector_designator}-{row.target_pin.pin_number}
                      <div className="text-[10px] text-slate-500">
                        {row.target_pin.direction}
                      </div>
                    </>
                  ) : row.ambiguous ? (
                    <button
                      type="button"
                      onClick={() => setExpandedSource(
                        expandedSource === row.source_pin.id ? null : row.source_pin.id
                      )}
                      className="underline decoration-dashed decoration-amber-400/50"
                    >
                      {row.ambiguous.candidates.length} candidates
                    </button>
                  ) : (
                    '—'
                  )}
                </td>
                <td className="px-3 py-2 align-top">
                  <span className="inline-flex items-center gap-1 font-semibold">
                    {row.status === 'matched' && <Check className="h-3.5 w-3.5" />}
                    {row.status === 'ambiguous' && <HelpCircle className="h-3.5 w-3.5" />}
                    {row.status === 'conflict' && <AlertTriangle className="h-3.5 w-3.5" />}
                    {row.status === 'unmatched' && <X className="h-3.5 w-3.5" />}
                    {STATUS_LABEL[row.status]}
                    {row.proposed?.warning && (
                      <span
                        title={row.proposed.warning}
                        className="ml-1 cursor-help text-amber-400"
                        aria-label={row.proposed.warning}
                      >
                        ⚠
                      </span>
                    )}
                  </span>
                  {row.conflict && (
                    <div
                      className="mt-1 max-w-md text-[11px] text-rose-200"
                      role="tooltip"
                    >
                      {row.conflict.reason}
                    </div>
                  )}
                </td>
                <td className="px-3 py-2 align-top">
                  {row.conflict && (
                    <div className="flex flex-wrap items-center gap-1">
                      <button
                        type="button"
                        disabled={!isAdmin}
                        onClick={() =>
                          onConflictAction?.(row.conflict!, 'override')
                        }
                        title={
                          isAdmin
                            ? 'Override (admin)'
                            : 'Override requires admin role'
                        }
                        className={clsx(
                          'inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[11px]',
                          isAdmin
                            ? 'border-rose-500/40 text-rose-300 hover:bg-rose-500/10'
                            : 'cursor-not-allowed border-slate-700 text-slate-600',
                        )}
                      >
                        <ShieldOff className="h-3 w-3" />
                        Override
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          onConflictAction?.(row.conflict!, 'mark_target_input')
                        }
                        className="inline-flex items-center gap-1 rounded border border-blue-500/40 px-2 py-0.5 text-[11px] text-blue-300 hover:bg-blue-500/10"
                      >
                        <ArrowDownToLine className="h-3 w-3" />
                        Mark target input
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          onConflictAction?.(row.conflict!, 'skip')
                        }
                        className="inline-flex items-center gap-1 rounded border border-slate-600 px-2 py-0.5 text-[11px] text-slate-400 hover:bg-slate-700/30"
                      >
                        <SkipForward className="h-3 w-3" />
                        Skip
                      </button>
                    </div>
                  )}
                  {row.proposed && (
                    <div className="text-[10px] text-slate-400">
                      {row.proposed.suggestion.gauge.toUpperCase()} ·{' '}
                      {row.proposed.suggestion.color}
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* Expanded ambiguous-candidates panel */}
      {expandedSource !== null && (
        <div className="border-t border-astra-border bg-astra-bg-4 p-3 text-xs text-slate-300">
          <div className="mb-2 font-semibold text-amber-300">Ambiguous candidates</div>
          {(() => {
            const am = result.ambiguous.find(a => a.source_pin.id === expandedSource);
            if (!am) return null;
            return (
              <ul className="space-y-1">
                {am.candidates.map((c) => (
                  <li key={c.id} className="font-mono">
                    {c.connector_designator}-{c.pin_number} ({c.direction}, {c.signal_type})
                  </li>
                ))}
              </ul>
            );
          })()}
        </div>
      )}
    </div>
  );
}
