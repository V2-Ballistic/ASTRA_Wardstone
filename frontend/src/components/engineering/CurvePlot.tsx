'use client';

/**
 * ASTRA — CurvePlot (Engineering UI shared plot)
 * ================================================
 * File: frontend/src/components/engineering/CurvePlot.tsx
 *
 * The ONE reusable line chart for the Engineering area (spec §5/§6):
 * motor thrust/Pc/mass curves, design-page live previews, aero
 * coefficient slices. d3 is used for scales/shape/ticks; the SVG is
 * rendered by React (matches the codebase's responsive-SVG pattern in
 * traceability/ForceGraph).
 *
 * Features:
 *   - responsive width (ResizeObserver on the container)
 *   - axes + grid lines in astra dark-theme colors
 *   - hover crosshair with per-series readout
 *   - multi-series with legend (overlays, e.g. temperature-grid thrust)
 *   - point decimation for the 1 kHz motor artifact grids
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import * as d3 from 'd3';
import clsx from 'clsx';

export interface CurveSeries {
  label: string;
  x: number[];
  y: number[];
  color?: string;
  dashed?: boolean;
}

export interface CurvePlotProps {
  title: string;
  series: CurveSeries[];
  xLabel: string;
  yLabel: string;
  /** Plot height in px (default 220). Width is responsive. */
  height?: number;
  /** Hover-readout formatter for y values (default d3 '.5~g'). */
  yFormat?: (v: number) => string;
  /** Hover-readout formatter for x values (default d3 '.4~g'). */
  xFormat?: (v: number) => string;
  className?: string;
}

const SERIES_COLORS = ['#3B82F6', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899', '#06B6D4'];
const MARGIN = { top: 10, right: 14, bottom: 34, left: 58 };
/** Cap rendered points per series — the motor artifact is 1 kHz. */
const MAX_POINTS = 1500;

const GRID = '#1E293B'; // astra-border
const AXIS_TEXT = '#64748B'; // slate-500
const CROSSHAIR = '#475569';

function decimate(s: CurveSeries): { x: number[]; y: number[] } {
  const n = Math.min(s.x.length, s.y.length);
  if (n <= MAX_POINTS) return { x: s.x.slice(0, n), y: s.y.slice(0, n) };
  const stride = Math.ceil(n / MAX_POINTS);
  const x: number[] = [];
  const y: number[] = [];
  for (let i = 0; i < n; i += stride) {
    x.push(s.x[i]);
    y.push(s.y[i]);
  }
  // Always keep the final sample (burnout tail matters).
  if (x[x.length - 1] !== s.x[n - 1]) {
    x.push(s.x[n - 1]);
    y.push(s.y[n - 1]);
  }
  return { x, y };
}

export default function CurvePlot({
  title,
  series,
  xLabel,
  yLabel,
  height = 220,
  yFormat,
  xFormat,
  className,
}: CurvePlotProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [hoverX, setHoverX] = useState<number | null>(null);

  // ── responsive width ──
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect?.width;
      if (w && w > 80) setWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const plotted = useMemo(
    () => series
      .filter((s) => s.x.length > 1 && s.y.length > 1)
      .map((s, i) => ({
        label: s.label,
        color: s.color || SERIES_COLORS[i % SERIES_COLORS.length],
        dashed: s.dashed || false,
        ...decimate(s),
      })),
    [series],
  );

  const innerW = Math.max(40, width - MARGIN.left - MARGIN.right);
  const innerH = Math.max(40, height - MARGIN.top - MARGIN.bottom);

  const { xScale, yScale } = useMemo(() => {
    const allX = plotted.flatMap((s) => s.x).filter(Number.isFinite);
    const allY = plotted.flatMap((s) => s.y).filter(Number.isFinite);
    const xExt = allX.length ? (d3.extent(allX) as [number, number]) : [0, 1];
    const yExt = allY.length ? (d3.extent(allY) as [number, number]) : [0, 1];
    // Include 0 in y when the data lives on one side of it — physical
    // series (thrust, Pc, mass) read better anchored at zero.
    const yLo = Math.min(yExt[0], 0);
    const yHi = yExt[1] === yLo ? yLo + 1 : yExt[1];
    return {
      xScale: d3.scaleLinear().domain(xExt).range([0, innerW]).nice(),
      yScale: d3.scaleLinear().domain([yLo, yHi]).range([innerH, 0]).nice(),
    };
  }, [plotted, innerW, innerH]);

  const fmtTickY = useMemo(() => d3.format('.3~s'), []);
  const fmtTickX = useMemo(() => d3.format('.3~g'), []);
  const fmtHoverY = useMemo(() => yFormat || d3.format('.5~g'), [yFormat]);
  const fmtHoverX = useMemo(() => xFormat || d3.format('.4~g'), [xFormat]);

  const paths = useMemo(() => {
    const line = d3.line<[number, number]>()
      .x((d) => xScale(d[0]))
      .y((d) => yScale(d[1]))
      .defined((d) => Number.isFinite(d[0]) && Number.isFinite(d[1]));
    return plotted.map((s) => {
      const pts: [number, number][] = s.x.map((xv, i) => [xv, s.y[i]]);
      return { ...s, d: line(pts) || '' };
    });
  }, [plotted, xScale, yScale]);

  // ── hover crosshair readout ──
  const hover = useMemo(() => {
    if (hoverX === null || plotted.length === 0) return null;
    const xv = xScale.invert(hoverX);
    const readings = plotted.map((s) => {
      const idx = Math.max(0, Math.min(s.x.length - 1, d3.bisectCenter(s.x, xv)));
      return { label: s.label, color: s.color, x: s.x[idx], y: s.y[idx] };
    });
    return { xv, px: xScale(readings[0]?.x ?? xv), readings };
  }, [hoverX, plotted, xScale]);

  const xTicks = xScale.ticks(6);
  const yTicks = yScale.ticks(5);
  const empty = plotted.length === 0;

  return (
    <div
      ref={containerRef}
      className={clsx(
        'relative rounded-xl border border-astra-border bg-astra-surface p-3',
        className,
      )}
    >
      <div className="mb-1 flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold text-slate-300">{title}</h3>
        {plotted.length > 1 && (
          <div className="flex flex-wrap items-center gap-2.5" aria-hidden="true">
            {plotted.map((s) => (
              <span key={s.label} className="flex items-center gap-1 text-[10px] text-slate-400">
                <span
                  className="inline-block h-0.5 w-3.5 rounded"
                  style={{
                    background: s.dashed
                      ? `repeating-linear-gradient(90deg, ${s.color} 0 3px, transparent 3px 5px)`
                      : s.color,
                  }}
                />
                {s.label}
              </span>
            ))}
          </div>
        )}
      </div>

      {empty ? (
        <div
          className="flex items-center justify-center text-xs text-slate-500"
          style={{ height }}
        >
          No data to plot
        </div>
      ) : (
        <svg
          width="100%"
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
          role="img"
          aria-label={`${title}: ${yLabel} versus ${xLabel}`}
          onMouseMove={(e) => {
            const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
            const px = ((e.clientX - rect.left) / rect.width) * width - MARGIN.left;
            setHoverX(px >= 0 && px <= innerW ? px : null);
          }}
          onMouseLeave={() => setHoverX(null)}
        >
          <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
            {/* grid */}
            {yTicks.map((t) => (
              <line key={`gy${t}`} x1={0} x2={innerW} y1={yScale(t)} y2={yScale(t)}
                stroke={GRID} strokeWidth={1} />
            ))}
            {xTicks.map((t) => (
              <line key={`gx${t}`} x1={xScale(t)} x2={xScale(t)} y1={0} y2={innerH}
                stroke={GRID} strokeWidth={1} />
            ))}

            {/* axes */}
            <line x1={0} x2={innerW} y1={innerH} y2={innerH} stroke={CROSSHAIR} strokeWidth={1} />
            <line x1={0} x2={0} y1={0} y2={innerH} stroke={CROSSHAIR} strokeWidth={1} />
            {xTicks.map((t) => (
              <text key={`tx${t}`} x={xScale(t)} y={innerH + 14} textAnchor="middle"
                fontSize={9} fill={AXIS_TEXT}>
                {fmtTickX(t)}
              </text>
            ))}
            {yTicks.map((t) => (
              <text key={`ty${t}`} x={-6} y={yScale(t) + 3} textAnchor="end"
                fontSize={9} fill={AXIS_TEXT}>
                {fmtTickY(t)}
              </text>
            ))}
            <text x={innerW / 2} y={innerH + 28} textAnchor="middle" fontSize={10}
              fill={AXIS_TEXT} fontWeight={600}>
              {xLabel}
            </text>
            <text
              transform={`translate(${-MARGIN.left + 12},${innerH / 2}) rotate(-90)`}
              textAnchor="middle" fontSize={10} fill={AXIS_TEXT} fontWeight={600}
            >
              {yLabel}
            </text>

            {/* series */}
            {paths.map((s) => (
              <path key={s.label} d={s.d} fill="none" stroke={s.color}
                strokeWidth={1.5} strokeDasharray={s.dashed ? '4 3' : undefined}
                vectorEffect="non-scaling-stroke" />
            ))}

            {/* crosshair */}
            {hover && (
              <g pointerEvents="none">
                <line x1={hover.px} x2={hover.px} y1={0} y2={innerH}
                  stroke={CROSSHAIR} strokeWidth={1} strokeDasharray="3 3" />
                {hover.readings.map((r) => (
                  <circle key={r.label} cx={xScale(r.x)} cy={yScale(r.y)} r={3}
                    fill={r.color} stroke="#0B0F19" strokeWidth={1} />
                ))}
              </g>
            )}
          </g>
        </svg>
      )}

      {/* hover readout */}
      {hover && !empty && (
        <div
          className="pointer-events-none absolute top-8 z-10 rounded-lg border border-astra-border bg-astra-bg/95 px-2.5 py-1.5 text-[10px] shadow-lg"
          style={{
            left: Math.min(
              Math.max(MARGIN.left + hover.px + 10, 4),
              Math.max(width - 150, 4),
            ),
          }}
        >
          <div className="font-mono font-semibold text-slate-300">
            {xLabel}: {fmtHoverX(hover.xv)}
          </div>
          {hover.readings.map((r) => (
            <div key={r.label} className="flex items-center gap-1.5 font-mono text-slate-400">
              <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: r.color }} />
              {r.label}: <span className="text-slate-200">{fmtHoverY(r.y)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
