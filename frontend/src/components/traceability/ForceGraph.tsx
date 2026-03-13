'use client';

/**
 * ASTRA — Interactive Force-Directed Traceability Graph
 * =======================================================
 * File: frontend/src/components/traceability/ForceGraph.tsx
 *
 * Features:
 *   - Custom force simulation (no D3 dependency)
 *   - Level-based vertical layout (L1 top → L5 bottom)
 *   - Draggable nodes with spring physics
 *   - Pan & zoom (scroll wheel + buttons)
 *   - Hover tooltip with req_id, title, level, status
 *   - Click to select → highlights connected subgraph
 *   - Directional arrow markers on edges
 *   - Edge color/style by link_type
 *   - Level color legend + link type legend
 *   - Responsive SVG container
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';

// ── Color maps ──

const LEVEL_COLORS: Record<string, string> = {
  L1: '#EF4444', L2: '#F59E0B', L3: '#3B82F6', L4: '#8B5CF6', L5: '#6B7280',
};

const LEVEL_LABELS: Record<string, string> = {
  L1: 'System', L2: 'Subsystem', L3: 'Component', L4: 'Sub-component', L5: 'Detail',
};

const LINK_COLORS: Record<string, string> = {
  parent_child: '#3B82F6',
  decomposition: '#3B82F6',
  satisfaction: '#10B981',
  dependency: '#F59E0B',
  evolution: '#8B5CF6',
  rationale: '#06B6D4',
  contribution: '#14B8A6',
  verification: '#10B981',
};

const LINK_LABELS: Record<string, string> = {
  parent_child: 'Parent / Child',
  decomposition: 'Decomposition',
  satisfaction: 'Satisfaction',
  dependency: 'Dependency',
  evolution: 'Evolution',
  rationale: 'Rationale',
  contribution: 'Contribution',
  verification: 'Verification',
};

const STATUS_COLORS: Record<string, string> = {
  draft: '#F59E0B', under_review: '#A78BFA', approved: '#3B82F6',
  baselined: '#10B981', verified: '#10B981', deleted: '#64748B',
};

// ── Types ──

interface GraphNode {
  id: number;
  req_id: string;
  title: string;
  level: string;
  status: string;
  parent_id?: number;
  quality_score?: number;
}

interface GraphEdge {
  source: number;
  target: number;
  source_type?: string;
  target_type?: string;
  link_type: string;
}

interface ForceGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick: (id: number) => void;
}

// ── Constants ──

const W = 960;
const H = 560;

// ══════════════════════════════════════
//  Component
// ══════════════════════════════════════

export default function ForceGraph({ nodes, edges, onNodeClick }: ForceGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Graph state
  const [positions, setPositions] = useState<Record<number, { x: number; y: number }>>({});
  const [selectedNode, setSelectedNode] = useState<number | null>(null);
  const [hoveredNode, setHoveredNode] = useState<number | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  // Drag state
  const [dragging, setDragging] = useState<number | null>(null);
  const draggingRef = useRef<number | null>(null);

  // Pan & zoom state
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const panStart = useRef({ x: 0, y: 0, panX: 0, panY: 0 });

  // ── Force simulation ──
  useEffect(() => {
    if (nodes.length === 0) return;

    const pos: Record<number, { x: number; y: number; vx: number; vy: number }> = {};

    // Group nodes by level for vertical layout
    const levelGroups: Record<string, GraphNode[]> = {};
    nodes.forEach((n) => {
      const lv = n.level || 'L1';
      if (!levelGroups[lv]) levelGroups[lv] = [];
      levelGroups[lv].push(n);
    });

    // L1 at top, L5 at bottom — vertical layout
    const levels = ['L1', 'L2', 'L3', 'L4', 'L5'];
    const usedLevels = levels.filter((l) => levelGroups[l]?.length > 0);

    usedLevels.forEach((level, li) => {
      const group = levelGroups[level] || [];
      const yBase = 60 + li * ((H - 120) / Math.max(usedLevels.length - 1, 1));
      const xSpacing = (W - 120) / Math.max(group.length + 1, 2);
      group.forEach((n, ni) => {
        pos[n.id] = {
          x: 60 + (ni + 1) * xSpacing + (Math.random() - 0.5) * 30,
          y: yBase + (Math.random() - 0.5) * 20,
          vx: 0,
          vy: 0,
        };
      });
    });

    // Run force simulation (60 iterations)
    const nodeIds = new Set(nodes.map((n) => n.id));
    const nodeArr = Object.keys(pos).map(Number);

    for (let iter = 0; iter < 60; iter++) {
      const alpha = 0.3 * (1 - iter / 60);

      // Repulsion between all nodes
      for (let i = 0; i < nodeArr.length; i++) {
        for (let j = i + 1; j < nodeArr.length; j++) {
          const a = pos[nodeArr[i]];
          const b = pos[nodeArr[j]];
          let dx = b.x - a.x;
          let dy = b.y - a.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          if (dist < 120) {
            const force = (120 - dist) * 0.15 * alpha;
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;
            a.vx -= fx;
            a.vy -= fy;
            b.vx += fx;
            b.vy += fy;
          }
        }
      }

      // Attraction along edges
      edges.forEach((e) => {
        if (pos[e.source] && pos[e.target]) {
          const a = pos[e.source];
          const b = pos[e.target];
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = (dist - 150) * 0.02 * alpha;
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          a.vx += fx;
          a.vy += fy;
          b.vx -= fx;
          b.vy -= fy;
        }
      });

      // Apply velocity and clamp
      nodeArr.forEach((id) => {
        const p = pos[id];
        p.x += p.vx;
        p.y += p.vy;
        p.vx *= 0.8;
        p.vy *= 0.8;
        p.x = Math.max(40, Math.min(W - 40, p.x));
        p.y = Math.max(40, Math.min(H - 40, p.y));
      });
    }

    const result: Record<number, { x: number; y: number }> = {};
    Object.entries(pos).forEach(([id, p]) => {
      result[Number(id)] = { x: p.x, y: p.y };
    });
    setPositions(result);
  }, [nodes, edges]);

  // ── Drag handlers ──
  const handleMouseDown = useCallback(
    (id: number, e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragging(id);
      draggingRef.current = id;
    },
    []
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      // Tooltip tracking
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        setTooltipPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
      }

      // Node dragging
      if (draggingRef.current !== null) {
        const svgRect = svgRef.current?.getBoundingClientRect();
        if (!svgRect) return;
        const x = (e.clientX - svgRect.left - pan.x) / zoom;
        const y = (e.clientY - svgRect.top - pan.y) / zoom;
        setPositions((prev) => ({
          ...prev,
          [draggingRef.current!]: {
            x: Math.max(40, Math.min(W - 40, x)),
            y: Math.max(40, Math.min(H - 40, y)),
          },
        }));
        return;
      }

      // Panning
      if (isPanning) {
        const dx = e.clientX - panStart.current.x;
        const dy = e.clientY - panStart.current.y;
        setPan({
          x: panStart.current.panX + dx,
          y: panStart.current.panY + dy,
        });
      }
    },
    [zoom, pan, isPanning]
  );

  const handleMouseUp = useCallback(() => {
    setDragging(null);
    draggingRef.current = null;
    setIsPanning(false);
  }, []);

  // Pan start (on SVG background click)
  const handleSvgMouseDown = useCallback(
    (e: React.MouseEvent) => {
      // Only start pan if clicking background (not a node)
      if ((e.target as Element).tagName === 'rect' || (e.target as Element).tagName === 'svg') {
        setIsPanning(true);
        panStart.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y };
      }
    },
    [pan]
  );

  // Zoom with scroll wheel
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    setZoom((z) => Math.max(0.3, Math.min(3, z - e.deltaY * 0.001)));
  }, []);

  // ── Node click ──
  const handleNodeClick = useCallback(
    (id: number) => {
      if (draggingRef.current !== null) return;
      setSelectedNode((prev) => (prev === id ? null : id));
    },
    []
  );

  // ── Zoom controls ──
  const zoomIn = () => setZoom((z) => Math.min(3, z + 0.2));
  const zoomOut = () => setZoom((z) => Math.max(0.3, z - 0.2));
  const resetView = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  // ── Connected subgraph for highlighting ──
  const connectedIds = new Set<number>();
  if (selectedNode !== null) {
    connectedIds.add(selectedNode);
    edges.forEach((e) => {
      if (e.source === selectedNode) connectedIds.add(e.target);
      if (e.target === selectedNode) connectedIds.add(e.source);
    });
    nodes.forEach((n) => {
      if (n.parent_id === selectedNode) connectedIds.add(n.id);
      if (n.id === selectedNode && n.parent_id) connectedIds.add(n.parent_id);
    });
  }

  // ── Hovered node data ──
  const hoveredData = hoveredNode !== null ? nodes.find((n) => n.id === hoveredNode) : null;

  // ── Collect unique link types present in edges for legend ──
  const presentLinkTypes = Array.from(new Set(edges.map((e) => e.link_type))).filter(
    (t) => LINK_COLORS[t]
  );

  // ── Empty state ──
  if (nodes.length === 0) {
    return (
      <div className="rounded-xl border border-astra-border bg-astra-surface py-16 text-center">
        <svg className="mx-auto mb-3 h-10 w-10 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343" />
        </svg>
        <div className="text-sm text-slate-500">No requirements to graph</div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="relative rounded-xl border border-astra-border bg-astra-surface overflow-hidden">
      {/* Zoom controls */}
      <div className="absolute right-3 top-3 z-20 flex flex-col gap-1">
        <button
          onClick={zoomIn}
          className="flex h-7 w-7 items-center justify-center rounded-lg border border-astra-border bg-astra-surface text-slate-400 transition hover:text-slate-200 hover:border-blue-500/30"
          title="Zoom in"
        >
          <ZoomIn className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={zoomOut}
          className="flex h-7 w-7 items-center justify-center rounded-lg border border-astra-border bg-astra-surface text-slate-400 transition hover:text-slate-200 hover:border-blue-500/30"
          title="Zoom out"
        >
          <ZoomOut className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={resetView}
          className="flex h-7 w-7 items-center justify-center rounded-lg border border-astra-border bg-astra-surface text-slate-400 transition hover:text-slate-200 hover:border-blue-500/30"
          title="Reset view"
        >
          <Maximize2 className="h-3.5 w-3.5" />
        </button>
        <div className="mt-1 text-center text-[9px] font-mono text-slate-600">
          {Math.round(zoom * 100)}%
        </div>
      </div>

      {/* Hint bar */}
      <div className="absolute left-3 top-3 z-10 text-[10px] text-slate-600">
        Click node to highlight · Drag to move · Scroll to zoom · Double-click to open
      </div>

      {/* SVG Canvas */}
      <svg
        ref={svgRef}
        width="100%"
        height="560"
        viewBox={`0 0 ${W} ${H}`}
        className={isPanning ? 'cursor-grabbing' : 'cursor-grab'}
        onMouseDown={handleSvgMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
      >
        <defs>
          {/* Grid pattern */}
          <pattern id="trace-grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(100,116,139,0.05)" strokeWidth="1" />
          </pattern>

          {/* Arrow markers for each link type */}
          {Object.entries(LINK_COLORS).map(([type, color]) => (
            <marker
              key={`arrow-${type}`}
              id={`arrow-${type}`}
              viewBox="0 0 10 10"
              refX="28"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill={color} fillOpacity="0.6" />
            </marker>
          ))}

          {/* Default arrow */}
          <marker id="arrow-default" viewBox="0 0 10 10" refX="28" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#475569" fillOpacity="0.6" />
          </marker>
        </defs>

        {/* Background */}
        <rect width={W} height={H} fill="url(#trace-grid)" />

        {/* Transform group for pan & zoom */}
        <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
          {/* Edges */}
          {edges.map((e, i) => {
            const s = positions[e.source];
            const t = positions[e.target];
            if (!s || !t) return null;
            const isHighlighted =
              selectedNode === null || (connectedIds.has(e.source) && connectedIds.has(e.target));
            const color = LINK_COLORS[e.link_type] || '#475569';
            const markerId = LINK_COLORS[e.link_type] ? `arrow-${e.link_type}` : 'arrow-default';
            const isDashed = e.link_type !== 'parent_child' && e.link_type !== 'decomposition';

            return (
              <line
                key={`edge-${i}`}
                x1={s.x}
                y1={s.y}
                x2={t.x}
                y2={t.y}
                stroke={color}
                strokeWidth={isHighlighted ? 2 : 1}
                strokeOpacity={isHighlighted ? 0.7 : 0.12}
                strokeDasharray={isDashed ? '5 3' : 'none'}
                markerEnd={`url(#${markerId})`}
              />
            );
          })}

          {/* Nodes */}
          {nodes.map((n) => {
            const p = positions[n.id];
            if (!p) return null;
            const color = LEVEL_COLORS[n.level] || '#6B7280';
            const isHighlighted = selectedNode === null || connectedIds.has(n.id);
            const isSelected = selectedNode === n.id;
            const isHovered = hoveredNode === n.id;
            const radius = isSelected ? 22 : isHovered ? 19 : 16;

            return (
              <g
                key={`node-${n.id}`}
                onMouseDown={(e) => handleMouseDown(n.id, e)}
                onClick={() => handleNodeClick(n.id)}
                onDoubleClick={() => onNodeClick(n.id)}
                onMouseEnter={() => setHoveredNode(n.id)}
                onMouseLeave={() => setHoveredNode(null)}
                className="cursor-pointer"
              >
                {/* Glow for selected */}
                {isSelected && (
                  <circle cx={p.x} cy={p.y} r={32} fill={color} fillOpacity={0.12} />
                )}

                {/* Hover ring */}
                {isHovered && !isSelected && (
                  <circle cx={p.x} cy={p.y} r={24} fill="none" stroke={color} strokeWidth={1} strokeOpacity={0.3} strokeDasharray="3 2" />
                )}

                {/* Node circle */}
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={radius}
                  fill={`${color}${isHighlighted ? '28' : '0A'}`}
                  stroke={color}
                  strokeWidth={isSelected ? 3 : isHovered ? 2 : 1.5}
                  strokeOpacity={isHighlighted ? 1 : 0.25}
                />

                {/* Level label */}
                <text
                  x={p.x}
                  y={p.y - 2}
                  textAnchor="middle"
                  fill={color}
                  fontSize="9"
                  fontWeight="700"
                  fontFamily="monospace"
                  opacity={isHighlighted ? 1 : 0.3}
                  style={{ pointerEvents: 'none' }}
                >
                  {n.level}
                </text>

                {/* Req ID below */}
                <text
                  x={p.x}
                  y={p.y + 8}
                  textAnchor="middle"
                  fill={isHighlighted ? '#E2E8F0' : '#475569'}
                  fontSize="7"
                  fontWeight="600"
                  fontFamily="monospace"
                  style={{ pointerEvents: 'none' }}
                >
                  {n.req_id.length > 12 ? n.req_id.substring(0, 12) : n.req_id}
                </text>

                {/* Quality score indicator (tiny dot) */}
                {n.quality_score != null && n.quality_score > 0 && (
                  <circle
                    cx={p.x + radius - 2}
                    cy={p.y - radius + 2}
                    r={3}
                    fill={n.quality_score >= 80 ? '#10B981' : n.quality_score >= 60 ? '#F59E0B' : '#EF4444'}
                    stroke="#0F172A"
                    strokeWidth={1}
                    style={{ pointerEvents: 'none' }}
                  />
                )}
              </g>
            );
          })}

          {/* Level legend (bottom-left) */}
          {['L1', 'L2', 'L3', 'L4', 'L5'].map((level, i) => (
            <g key={`legend-${level}`} transform={`translate(20, ${H - 130 + i * 22})`}>
              <circle cx={6} cy={6} r={6} fill={LEVEL_COLORS[level] + '30'} stroke={LEVEL_COLORS[level]} strokeWidth={1.5} />
              <text x={18} y={10} fill="#94A3B8" fontSize="10" fontWeight="600">
                {level} — {LEVEL_LABELS[level]}
              </text>
            </g>
          ))}

          {/* Link type legend (bottom-right) */}
          {presentLinkTypes.slice(0, 6).map((type, i) => (
            <g key={`link-legend-${type}`} transform={`translate(${W - 170}, ${H - 130 + i * 20})`}>
              <line
                x1={0}
                y1={6}
                x2={20}
                y2={6}
                stroke={LINK_COLORS[type]}
                strokeWidth={2}
                strokeDasharray={type === 'parent_child' || type === 'decomposition' ? 'none' : '4 3'}
                markerEnd={`url(#arrow-${type})`}
              />
              <text x={28} y={10} fill="#94A3B8" fontSize="9">
                {LINK_LABELS[type] || type.replace(/_/g, ' ')}
              </text>
            </g>
          ))}
        </g>
      </svg>

      {/* Hover tooltip */}
      {hoveredData && draggingRef.current === null && (
        <div
          className="pointer-events-none absolute z-30 rounded-lg border border-astra-border bg-slate-900/95 px-3 py-2 shadow-xl backdrop-blur-sm"
          style={{
            left: Math.min(tooltipPos.x + 16, (containerRef.current?.clientWidth || 800) - 220),
            top: tooltipPos.y - 10,
          }}
        >
          <div className="flex items-center gap-2 mb-1">
            <span
              className="rounded-full px-1.5 py-0.5 text-[9px] font-bold"
              style={{
                background: `${LEVEL_COLORS[hoveredData.level]}20`,
                color: LEVEL_COLORS[hoveredData.level],
              }}
            >
              {hoveredData.level}
            </span>
            <span className="font-mono text-xs font-bold text-blue-400">{hoveredData.req_id}</span>
            <span
              className="rounded-full px-1.5 py-0.5 text-[9px] font-semibold capitalize"
              style={{
                background: `${STATUS_COLORS[hoveredData.status] || '#6B7280'}20`,
                color: STATUS_COLORS[hoveredData.status] || '#6B7280',
              }}
            >
              {hoveredData.status?.replace('_', ' ')}
            </span>
          </div>
          <div className="text-[11px] text-slate-300 max-w-[200px] truncate">{hoveredData.title}</div>
          {hoveredData.quality_score != null && hoveredData.quality_score > 0 && (
            <div className="mt-1 text-[10px] text-slate-500">
              Quality: <span className="font-semibold text-slate-400">{hoveredData.quality_score}</span>
            </div>
          )}
        </div>
      )}

      {/* Selected node info bar */}
      {selectedNode !== null &&
        (() => {
          const n = nodes.find((x) => x.id === selectedNode);
          if (!n) return null;
          const connectionCount = connectedIds.size - 1;
          return (
            <div className="border-t border-astra-border px-4 py-3 flex items-center gap-3 bg-slate-900/50">
              <span
                className="rounded-full px-2 py-0.5 text-[10px] font-bold"
                style={{
                  background: `${LEVEL_COLORS[n.level]}20`,
                  color: LEVEL_COLORS[n.level],
                }}
              >
                {n.level}
              </span>
              <span className="font-mono text-xs font-semibold text-blue-400">{n.req_id}</span>
              <span className="flex-1 truncate text-sm text-slate-300">{n.title}</span>
              <span className="text-xs text-slate-500">
                {connectionCount} connection{connectionCount !== 1 ? 's' : ''}
              </span>
              <button
                onClick={() => onNodeClick(n.id)}
                className="flex items-center gap-1 text-xs font-semibold text-blue-400 hover:text-blue-300"
              >
                Open →
              </button>
            </div>
          );
        })()}
    </div>
  );
}
