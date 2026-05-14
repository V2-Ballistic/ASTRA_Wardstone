'use client';

/**
 * ASTRA — SystemArchGraph (TDD-SYSARCH-002 §5)
 * ==============================================
 * Pure-TypeScript force-directed cluster graph for the System
 * Architecture page. No D3 dependency; the simulation is a small
 * fixed-iteration loop (gravity + Coulomb-style repulsion + spring
 * attraction toward parent system).
 *
 * Layout
 * ------
 *   - Systems = rounded-rect container nodes (~220×120 px). Border
 *     tinted by system_type's color hint.
 *   - Units   = circle nodes (radius 18) gravitating toward their
 *     parent system's center.
 *   - Edges:
 *       contains    : faint grey line (system → unit)
 *       parent_of   : thicker line (system → child system)
 *       connects_to : colored line (unit → unit, from Interface or
 *                     WireHarness; signal_type colour when present)
 *
 * Interaction
 * -----------
 *   - Pan: mouse-drag on empty canvas → translate <g transform>.
 *   - Zoom: wheel → adjust SVG viewBox.
 *   - Click vs drag: track mousedown position; if mouseup within 5 px
 *     treat as click. Click on system → /system/<id>; click on unit
 *     → /unit/<id>.
 *   - Hover on a unit shows a tooltip: designation, parent system,
 *     catalog WPN (if linked).
 *
 * Hooks rule
 * ----------
 * Every useState / useEffect / useMemo / useCallback / useRef call
 * lives ABOVE any early `return` per React's rules-of-hooks (and the
 * SYSARCH-002 prompt §7). Optional chaining for null-safe field reads.
 */

import {
  useCallback, useEffect, useMemo, useRef, useState,
} from 'react';
import { useRouter } from 'next/navigation';
import {
  Loader2, Network, Plus, RotateCcw, ZoomIn, ZoomOut,
} from 'lucide-react';

import { sysarchAPI } from '@/lib/sysarch-api';
import { formatApiError } from '@/lib/errors';
import type {
  SystemArchGraphEdge,
  SystemArchGraphNode,
  SystemArchGraphResponse,
} from '@/lib/sysarch-types';


// ─────────────────────────────────────────────────────────────────
//  Geometry constants
// ─────────────────────────────────────────────────────────────────

const VIEW_W = 1280;
const VIEW_H = 720;

const SYSTEM_W = 220;
const SYSTEM_H = 120;
const UNIT_R = 18;

// Iteration budget for the initial layout pass. The prompt notes ~50
// nodes is comfortable, ~150 starts to lag — see gotcha §1. SMDS and
// DEF-MOD1 are well below that.
const SIM_ITERATIONS = 150;

// Click vs drag threshold — pixels. Below this in cumulative move,
// treat the mouseup as a click; above it, treat as a pan finish.
const CLICK_DRAG_PX = 5;


// ─────────────────────────────────────────────────────────────────
//  Internal layout types
// ─────────────────────────────────────────────────────────────────

interface SimSystem {
  id: number;
  src: SystemArchGraphNode;
  x: number;
  y: number;
}

interface SimUnit {
  id: number;
  src: SystemArchGraphNode;
  parent_system_id: number | null;
  x: number;
  y: number;
}


function computeInitialLayout(
  systems: SystemArchGraphNode[],
  units: SystemArchGraphNode[],
): { sysSim: SimSystem[]; unitSim: SimUnit[] } {
  // Lay systems out in a grid, biased toward the canvas center.
  const cols = Math.max(1, Math.ceil(Math.sqrt(systems.length)));
  const colSpacing = SYSTEM_W + 80;
  const rowSpacing = SYSTEM_H + 80;
  const totalW = cols * colSpacing;
  const totalH = Math.ceil(systems.length / cols) * rowSpacing;
  const offsetX = VIEW_W / 2 - totalW / 2 + colSpacing / 2;
  const offsetY = VIEW_H / 2 - totalH / 2 + rowSpacing / 2;

  const sysSim: SimSystem[] = systems.map((s, i) => ({
    id: s.id,
    src: s,
    x: offsetX + (i % cols) * colSpacing,
    y: offsetY + Math.floor(i / cols) * rowSpacing,
  }));

  const sysById = new Map<number, SimSystem>();
  for (const s of sysSim) sysById.set(s.id, s);

  // Place units around their parent system's center on a small ring.
  // The simulation will spread them out further.
  const groupedByParent = new Map<number | null, SystemArchGraphNode[]>();
  for (const u of units) {
    const key = u.parent_id ?? null;
    if (!groupedByParent.has(key)) groupedByParent.set(key, []);
    groupedByParent.get(key)!.push(u);
  }

  const unitSim: SimUnit[] = [];
  for (const [parentId, group] of groupedByParent.entries()) {
    const parent = parentId == null ? null : sysById.get(parentId) ?? null;
    const cx = parent ? parent.x : VIEW_W / 2;
    const cy = parent ? parent.y : VIEW_H / 2;
    const ring = Math.max(50, Math.min(group.length * 6, 90));
    group.forEach((u, i) => {
      const a = (i / group.length) * 2 * Math.PI;
      unitSim.push({
        id: u.id,
        src: u,
        parent_system_id: parentId,
        x: cx + Math.cos(a) * ring,
        y: cy + Math.sin(a) * ring,
      });
    });
  }

  return { sysSim, unitSim };
}


function runSimulation(
  sysSim: SimSystem[],
  unitSim: SimUnit[],
  edges: SystemArchGraphEdge[],
  iterations: number,
) {
  const sysById = new Map<number, SimSystem>();
  for (const s of sysSim) sysById.set(s.id, s);
  const unitById = new Map<number, SimUnit>();
  for (const u of unitSim) unitById.set(u.id, u);

  // Pre-compute a connects_to list for the unit-unit attractive force.
  const unitConnects: Array<[SimUnit, SimUnit]> = [];
  for (const e of edges) {
    if (e.edge_type !== 'connects_to') continue;
    const a = unitById.get(e.source);
    const b = unitById.get(e.target);
    if (a && b) unitConnects.push([a, b]);
  }

  // Pre-compute system parent edges — a soft pull keeps child systems
  // closer to their parent.
  const sysParentEdges: Array<[SimSystem, SimSystem]> = [];
  for (const s of sysSim) {
    const parentId = s.src.parent_id;
    if (parentId == null) continue;
    const parent = sysById.get(parentId);
    if (parent) sysParentEdges.push([parent, s]);
  }

  const cx = VIEW_W / 2;
  const cy = VIEW_H / 2;

  for (let iter = 0; iter < iterations; iter++) {
    // 1. Repulsion between all systems (Coulomb).
    for (let i = 0; i < sysSim.length; i++) {
      for (let j = i + 1; j < sysSim.length; j++) {
        const a = sysSim[i];
        const b = sysSim[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const dist2 = dx * dx + dy * dy + 1;
        // Repulsion is stronger at very close range; cap to prevent
        // single-tick teleports.
        const force = Math.min(60000 / dist2, 30);
        const dist = Math.sqrt(dist2);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        a.x += fx;
        a.y += fy;
        b.x -= fx;
        b.y -= fy;
      }
    }

    // 2. Repulsion between units (lighter — they cluster by system).
    for (let i = 0; i < unitSim.length; i++) {
      for (let j = i + 1; j < unitSim.length; j++) {
        const a = unitSim[i];
        const b = unitSim[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const dist2 = dx * dx + dy * dy + 1;
        const force = Math.min(2000 / dist2, 6);
        const dist = Math.sqrt(dist2);
        a.x += (dx / dist) * force;
        a.y += (dy / dist) * force;
        b.x -= (dx / dist) * force;
        b.y -= (dy / dist) * force;
      }
    }

    // 3. Attractive force: each unit toward its parent system.
    for (const u of unitSim) {
      if (u.parent_system_id == null) continue;
      const parent = sysById.get(u.parent_system_id);
      if (!parent) continue;
      const dx = parent.x - u.x;
      const dy = parent.y - u.y;
      // Gentle spring; coefficient tuned by eye for ~6-unit clusters.
      u.x += dx * 0.04;
      u.y += dy * 0.04;
    }

    // 4. Attractive force: connects_to between units.
    for (const [a, b] of unitConnects) {
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      a.x += dx * 0.01;
      a.y += dy * 0.01;
      b.x -= dx * 0.01;
      b.y -= dy * 0.01;
    }

    // 5. Soft pull from child systems toward their parent system.
    for (const [parent, child] of sysParentEdges) {
      const dx = parent.x - child.x;
      const dy = parent.y - child.y;
      child.x += dx * 0.01;
      child.y += dy * 0.01;
    }

    // 6. Mild gravity toward the canvas center keeps the layout from
    //    flying off into the corners.
    for (const s of sysSim) {
      s.x += (cx - s.x) * 0.005;
      s.y += (cy - s.y) * 0.005;
    }
    for (const u of unitSim) {
      u.x += (cx - u.x) * 0.002;
      u.y += (cy - u.y) * 0.002;
    }
  }
}


// ─────────────────────────────────────────────────────────────────
//  Component
// ─────────────────────────────────────────────────────────────────

export interface SystemArchGraphProps {
  projectId: number;
  /** Empty-state CTA target — the page-level handler switches to the
   *  Systems tab so the modal naturally opens from the next click. */
  onAddSystem: () => void;
}


interface ViewState {
  // Pan offset applied via <g transform="translate">.
  panX: number;
  panY: number;
  // Zoom factor; viewBox width/height are VIEW_W/VIEW_H ÷ zoom.
  zoom: number;
}


interface HoverInfo {
  unitId: number;
  x: number;
  y: number;
  label: string;
  systemName: string;
  wpn?: string | null;
}


export default function SystemArchGraph({ projectId, onAddSystem }: SystemArchGraphProps) {
  const router = useRouter();

  // ── Data fetch ──
  const [graph, setGraph] = useState<SystemArchGraphResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ── View state (pan / zoom) ──
  const [view, setView] = useState<ViewState>({ panX: 0, panY: 0, zoom: 1 });

  // ── Drag tracking ──
  const dragRef = useRef<{
    active: boolean;
    startX: number;
    startY: number;
    startPanX: number;
    startPanY: number;
    moved: number;
  }>({
    active: false,
    startX: 0,
    startY: 0,
    startPanX: 0,
    startPanY: 0,
    moved: 0,
  });

  // ── Hover ──
  const [hover, setHover] = useState<HoverInfo | null>(null);

  // ── Refs to the SVG for screen→viewBox math ──
  const svgRef = useRef<SVGSVGElement | null>(null);

  // ── Fetch graph on mount / project change ──
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    sysarchAPI.getGraph(projectId)
      .then((r) => { if (!cancelled) setGraph(r.data); })
      .catch((e) => {
        if (cancelled) return;
        const detail = formatApiError(e, 'Failed to load graph');
        setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [projectId]);

  // ── Compute layout once per data change ──
  const layout = useMemo(() => {
    if (!graph) return null;
    const { sysSim, unitSim } = computeInitialLayout(graph.systems, graph.units);
    runSimulation(sysSim, unitSim, graph.edges, SIM_ITERATIONS);
    const sysById = new Map<number, SimSystem>();
    for (const s of sysSim) sysById.set(s.id, s);
    const unitById = new Map<number, SimUnit>();
    for (const u of unitSim) unitById.set(u.id, u);
    return { sysSim, unitSim, sysById, unitById };
  }, [graph]);

  const systemNameById = useMemo(() => {
    const out = new Map<number, string>();
    for (const s of graph?.systems ?? []) {
      out.set(s.id, s.label);
    }
    return out;
  }, [graph]);

  // ── Pan / zoom handlers ──
  const onWheel = useCallback((e: React.WheelEvent<SVGSVGElement>) => {
    e.preventDefault();
    setView((v) => {
      const next = e.deltaY < 0 ? v.zoom * 1.1 : v.zoom / 1.1;
      return { ...v, zoom: Math.max(0.3, Math.min(4, next)) };
    });
  }, []);

  const onMouseDown = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    dragRef.current = {
      active: true,
      startX: e.clientX,
      startY: e.clientY,
      startPanX: view.panX,
      startPanY: view.panY,
      moved: 0,
    };
  }, [view.panX, view.panY]);

  const onMouseMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (!dragRef.current.active) return;
    const dx = e.clientX - dragRef.current.startX;
    const dy = e.clientY - dragRef.current.startY;
    dragRef.current.moved = Math.max(dragRef.current.moved, Math.hypot(dx, dy));
    setView((v) => ({ ...v, panX: dragRef.current.startPanX + dx, panY: dragRef.current.startPanY + dy }));
  }, []);

  const onMouseUp = useCallback(() => {
    dragRef.current.active = false;
  }, []);

  const onResetView = useCallback(() => {
    setView({ panX: 0, panY: 0, zoom: 1 });
  }, []);

  const onZoomIn = useCallback(() => {
    setView((v) => ({ ...v, zoom: Math.min(4, v.zoom * 1.2) }));
  }, []);
  const onZoomOut = useCallback(() => {
    setView((v) => ({ ...v, zoom: Math.max(0.3, v.zoom / 1.2) }));
  }, []);

  // Click vs drag: only navigate on a quick mouseup (within threshold).
  const handleSystemClick = useCallback((id: number) => {
    if (dragRef.current.moved > CLICK_DRAG_PX) return;
    router.push(`/projects/${projectId}/system-architecture/system/${id}`);
  }, [projectId, router]);

  const handleUnitClick = useCallback((id: number) => {
    if (dragRef.current.moved > CLICK_DRAG_PX) return;
    router.push(`/projects/${projectId}/system-architecture/unit/${id}`);
  }, [projectId, router]);

  // ── Early returns AFTER all hooks ──
  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-5 w-5 animate-spin text-blue-500" aria-label="Loading graph" />
      </div>
    );
  }
  if (error) {
    return (
      <div role="alert" className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
        {error}
      </div>
    );
  }
  if (!graph || graph.systems.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-astra-border bg-astra-surface px-6 py-16 text-center">
        <Network className="mx-auto mb-3 h-10 w-10 text-slate-600" aria-hidden="true" />
        <p className="mb-2 text-sm text-slate-300">
          Define your first system to start building the architecture.
        </p>
        <p className="mb-5 text-xs text-slate-500">
          Systems become container nodes; the units inside each system render as
          circles, and Interface / WireHarness rows draw the connection edges.
        </p>
        <button
          type="button"
          onClick={onAddSystem}
          className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-br from-blue-500 to-violet-500 px-3 py-1.5 text-xs font-semibold text-white hover:shadow-lg"
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add System
        </button>
      </div>
    );
  }

  // viewBox: zoom mutates the visible area; pan is applied via <g>.
  const vbW = VIEW_W / view.zoom;
  const vbH = VIEW_H / view.zoom;
  const vbX = (VIEW_W - vbW) / 2;
  const vbY = (VIEW_H - vbH) / 2;

  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface p-2">
      {/* Top-bar controls */}
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onZoomIn}
            aria-label="Zoom in"
            className="rounded border border-astra-border p-1.5 text-slate-400 hover:bg-astra-surface-alt hover:text-slate-200"
          >
            <ZoomIn className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={onZoomOut}
            aria-label="Zoom out"
            className="rounded border border-astra-border p-1.5 text-slate-400 hover:bg-astra-surface-alt hover:text-slate-200"
          >
            <ZoomOut className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={onResetView}
            aria-label="Reset view"
            className="flex items-center gap-1 rounded border border-astra-border px-2 py-1 text-[10px] text-slate-400 hover:bg-astra-surface-alt hover:text-slate-200"
          >
            <RotateCcw className="h-3 w-3" aria-hidden="true" />
            Reset
          </button>
        </div>
        <div className="flex items-center gap-3 text-[10px] text-slate-500">
          <span><span className="inline-block h-2 w-2 rounded-full bg-slate-500" aria-hidden="true" /> contains</span>
          <span><span className="inline-block h-2 w-2 rounded-full bg-blue-400" aria-hidden="true" /> connects</span>
          <span><span className="inline-block h-2 w-2 rounded-full bg-violet-400" aria-hidden="true" /> hierarchy</span>
        </div>
      </div>

      <div className="relative" style={{ aspectRatio: `${VIEW_W} / ${VIEW_H}` }}>
        <svg
          ref={svgRef}
          viewBox={`${vbX} ${vbY} ${vbW} ${vbH}`}
          width="100%"
          height="100%"
          onWheel={onWheel}
          onMouseDown={onMouseDown}
          onMouseMove={onMouseMove}
          onMouseUp={onMouseUp}
          onMouseLeave={onMouseUp}
          style={{ cursor: dragRef.current.active ? 'grabbing' : 'grab', userSelect: 'none' }}
        >
          <g transform={`translate(${view.panX},${view.panY})`}>
            {/* Edges first so they sit under the nodes */}
            {graph.edges.map((e, idx) => {
              const src =
                e.source_type === 'system'
                  ? layout?.sysById.get(e.source)
                  : layout?.unitById.get(e.source);
              const dst =
                e.target_type === 'system'
                  ? layout?.sysById.get(e.target)
                  : layout?.unitById.get(e.target);
              if (!src || !dst) return null;
              const stroke =
                e.color_hint
                || (e.edge_type === 'parent_of' ? '#A78BFA' : e.edge_type === 'connects_to' ? '#3B82F6' : '#475569');
              const strokeWidth =
                e.edge_type === 'parent_of' ? 2.5 : e.edge_type === 'connects_to' ? 1.5 : 1;
              return (
                <line
                  key={`e-${idx}`}
                  x1={src.x}
                  y1={src.y}
                  x2={dst.x}
                  y2={dst.y}
                  stroke={stroke}
                  strokeWidth={strokeWidth}
                  opacity={e.edge_type === 'contains' ? 0.4 : 0.8}
                />
              );
            })}

            {/* System rectangles */}
            {layout?.sysSim.map((s) => {
              const tint = s.src.color_hint || '#3B82F6';
              const x = s.x - SYSTEM_W / 2;
              const y = s.y - SYSTEM_H / 2;
              return (
                <g
                  key={`sys-${s.id}`}
                  onClick={() => handleSystemClick(s.id)}
                  style={{ cursor: 'pointer' }}
                >
                  <rect
                    x={x}
                    y={y}
                    width={SYSTEM_W}
                    height={SYSTEM_H}
                    rx={12}
                    ry={12}
                    fill="rgba(15,23,42,0.6)"
                    stroke={tint}
                    strokeWidth={2}
                    pointerEvents="all"
                  />
                  <text
                    x={s.x}
                    y={y + 22}
                    textAnchor="middle"
                    fill={tint}
                    fontSize={13}
                    fontWeight={700}
                    pointerEvents="none"
                  >
                    {s.src.label}
                  </text>
                  {s.src.badge && (
                    <text
                      x={s.x}
                      y={y + 38}
                      textAnchor="middle"
                      fill="#94A3B8"
                      fontSize={10}
                      fontFamily="monospace"
                      pointerEvents="none"
                    >
                      {s.src.badge}
                    </text>
                  )}
                </g>
              );
            })}

            {/* Unit circles (drawn on top of system rectangles) */}
            {layout?.unitSim.map((u) => {
              const tint = u.src.color_hint || '#3B82F6';
              return (
                <g
                  key={`u-${u.id}`}
                  onClick={() => handleUnitClick(u.id)}
                  onMouseEnter={() => setHover({
                    unitId: u.id,
                    x: u.x,
                    y: u.y,
                    label: u.src.label,
                    systemName: (u.parent_system_id != null && systemNameById.get(u.parent_system_id)) || '',
                    wpn: u.src.catalog_part_wpn,
                  })}
                  onMouseLeave={() => setHover((h) => (h?.unitId === u.id ? null : h))}
                  style={{ cursor: 'pointer' }}
                >
                  <circle
                    cx={u.x}
                    cy={u.y}
                    r={UNIT_R}
                    fill="#0F172A"
                    stroke={tint}
                    strokeWidth={2}
                    pointerEvents="all"
                  />
                  <text
                    x={u.x}
                    y={u.y + 4}
                    textAnchor="middle"
                    fill="#E2E8F0"
                    fontSize={9}
                    fontFamily="monospace"
                    pointerEvents="none"
                  >
                    {u.src.label.slice(0, 6)}
                  </text>
                  {u.src.catalog_part_wpn && (
                    <circle
                      cx={u.x + UNIT_R - 4}
                      cy={u.y - UNIT_R + 4}
                      r={4}
                      fill="#10B981"
                      pointerEvents="none"
                    >
                      <title>Linked: {u.src.catalog_part_wpn}</title>
                    </circle>
                  )}
                </g>
              );
            })}
          </g>
        </svg>

        {/* Hover tooltip — placed in a sibling div so HTML wraps properly */}
        {hover && (
          <div
            className="pointer-events-none absolute z-10 max-w-[220px] rounded border border-astra-border bg-astra-surface-alt px-2 py-1 text-[11px] text-slate-200 shadow-lg"
            style={{
              left: `${(((hover.x + view.panX) - vbX) / vbW) * 100}%`,
              top: `${(((hover.y + view.panY) - vbY) / vbH) * 100}%`,
              transform: 'translate(8px, 8px)',
            }}
          >
            <div className="font-mono text-[11px] text-slate-100">{hover.label}</div>
            {hover.systemName && (
              <div className="text-[10px] text-slate-400">in {hover.systemName}</div>
            )}
            {hover.wpn && (
              <div className="text-[10px] text-emerald-400">WPN {hover.wpn}</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
