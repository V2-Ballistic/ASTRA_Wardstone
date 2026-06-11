'use client';

/**
 * ASTRA — Validity-envelope heatmap (Aero detail, spec §6 UX)
 * =============================================================
 * File: frontend/src/components/engineering/EnvelopeHeatmap.tsx
 *
 * Mach × α coverage grid built from the REAL deck breakpoints: one
 * cell per (mach, alpha) breakpoint node, shaded by the fraction of
 * coefficient tables that hold a finite value at that node on the
 * β≈0 / δ≈0 plane. Fully covered cells render solid cyan; partially
 * covered cells dim proportionally; empty nodes stay dark. Matches
 * the astra dark theme (same palette family as CurvePlot).
 */

import { useMemo } from 'react';
import type { AeroDeckArtifact } from '@/lib/engineering-types';

const CELL = 26;
const GAP = 2;
const MARGIN = { top: 8, right: 8, bottom: 40, left: 52 };
const AXIS_TEXT = '#64748B'; // slate-500
const EMPTY_FILL = '#0F172A';
const EMPTY_STROKE = '#1E293B'; // astra-border
const COVERED = '34, 211, 238'; // cyan-400 rgb

function closestIndex(values: number[], target: number): number {
  let best = 0;
  for (let i = 1; i < values.length; i++) {
    if (Math.abs(values[i] - target) < Math.abs(values[best] - target)) best = i;
  }
  return best;
}

export default function EnvelopeHeatmap({
  artifact,
  className,
}: {
  artifact: AeroDeckArtifact;
  className?: string;
}) {
  const grid = useMemo(() => {
    const bp = artifact.breakpoints;
    if (!bp?.mach?.length || !bp?.alpha_deg?.length) return null;
    const tables = Object.entries(artifact.tables ?? {});
    if (tables.length === 0) return null;

    const ib = closestIndex(bp.beta_deg ?? [0], 0);
    const idl = closestIndex(bp.delta_deg ?? [0], 0);

    // coverage[ai][mi] ∈ [0,1] — fraction of tables with a finite
    // value at this (mach, alpha) node.
    const coverage: number[][] = bp.alpha_deg.map((_, ai) =>
      bp.mach.map((__, mi) => {
        let hit = 0;
        for (const [, table] of tables) {
          const v = table?.[mi]?.[ai]?.[ib]?.[idl];
          if (typeof v === 'number' && Number.isFinite(v)) hit += 1;
        }
        return hit / tables.length;
      }));

    return {
      mach: bp.mach,
      alpha: bp.alpha_deg,
      coverage,
      tableCount: tables.length,
      beta: (bp.beta_deg ?? [0])[ib],
      delta: (bp.delta_deg ?? [0])[idl],
    };
  }, [artifact]);

  if (!grid) {
    return (
      <div className="rounded-xl border border-astra-border bg-astra-surface py-10 text-center text-xs text-slate-500">
        No breakpoint grid to visualize.
      </div>
    );
  }

  const cols = grid.mach.length;
  const rows = grid.alpha.length;
  const width = MARGIN.left + cols * (CELL + GAP) + MARGIN.right;
  const height = MARGIN.top + rows * (CELL + GAP) + MARGIN.bottom;
  // Skip some axis labels when the grid is dense.
  const machStep = Math.max(1, Math.ceil(cols / 14));
  const alphaStep = Math.max(1, Math.ceil(rows / 12));

  return (
    <div className={className}>
      <div className="overflow-x-auto rounded-xl border border-astra-border bg-astra-surface p-3">
        <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-xs font-semibold text-slate-300">
            Validity envelope — Mach × α coverage
          </h3>
          <span className="text-[10px] text-slate-500">
            β = {grid.beta}°, δ = {grid.delta}° plane ·{' '}
            {grid.tableCount} coefficient table{grid.tableCount === 1 ? '' : 's'}
          </span>
        </div>
        <svg
          width={width}
          height={height}
          role="img"
          aria-label={`Mach by alpha coverage grid: ${cols} Mach breakpoints by ${rows} alpha breakpoints`}
        >
          <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
            {grid.alpha.map((a, ai) =>
              grid.mach.map((m, mi) => {
                const frac = grid.coverage[ai][mi];
                return (
                  <rect
                    key={`${ai}-${mi}`}
                    x={mi * (CELL + GAP)}
                    y={(rows - 1 - ai) * (CELL + GAP)}
                    width={CELL}
                    height={CELL}
                    rx={3}
                    fill={frac > 0 ? `rgba(${COVERED},${0.12 + 0.68 * frac})` : EMPTY_FILL}
                    stroke={frac > 0 ? `rgba(${COVERED},0.45)` : EMPTY_STROKE}
                    strokeWidth={1}
                  >
                    <title>
                      {`Mach ${m}, α ${a}° — ${Math.round(frac * grid.tableCount)}/${grid.tableCount} tables`}
                    </title>
                  </rect>
                );
              }))}

            {/* α axis (rows, increasing upward) */}
            {grid.alpha.map((a, ai) => (
              ai % alphaStep === 0 ? (
                <text
                  key={`a${ai}`}
                  x={-6}
                  y={(rows - 1 - ai) * (CELL + GAP) + CELL / 2 + 3}
                  textAnchor="end"
                  fontSize={9}
                  fill={AXIS_TEXT}
                >
                  {a}°
                </text>
              ) : null
            ))}
            {/* Mach axis (cols) */}
            {grid.mach.map((m, mi) => (
              mi % machStep === 0 ? (
                <text
                  key={`m${mi}`}
                  x={mi * (CELL + GAP) + CELL / 2}
                  y={rows * (CELL + GAP) + 12}
                  textAnchor="middle"
                  fontSize={9}
                  fill={AXIS_TEXT}
                >
                  {m}
                </text>
              ) : null
            ))}
            <text
              x={(cols * (CELL + GAP)) / 2}
              y={rows * (CELL + GAP) + 28}
              textAnchor="middle"
              fontSize={10}
              fontWeight={600}
              fill={AXIS_TEXT}
            >
              Mach
            </text>
            <text
              transform={`translate(${-MARGIN.left + 12},${(rows * (CELL + GAP)) / 2}) rotate(-90)`}
              textAnchor="middle"
              fontSize={10}
              fontWeight={600}
              fill={AXIS_TEXT}
            >
              α (deg)
            </text>
          </g>
        </svg>
        <div className="mt-1.5 flex items-center gap-3 text-[10px] text-slate-500">
          <span className="flex items-center gap-1">
            <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: `rgba(${COVERED},0.8)` }} />
            all tables
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: `rgba(${COVERED},0.3)` }} />
            partial
          </span>
          <span className="flex items-center gap-1">
            <span
              className="inline-block h-2.5 w-2.5 rounded-sm border"
              style={{ background: EMPTY_FILL, borderColor: EMPTY_STROKE }}
            />
            no data
          </span>
        </div>
      </div>
    </div>
  );
}
