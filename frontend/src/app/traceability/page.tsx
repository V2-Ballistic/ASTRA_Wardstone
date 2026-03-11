'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import {
  Loader2, RefreshCw, Grid3X3, GitBranch, AlertTriangle, CheckCircle,
  FileText, Shield, Link2, ChevronRight
} from 'lucide-react';
import { traceabilityAPI, projectsAPI } from '@/lib/api';
import {
  STATUS_COLORS, STATUS_LABELS, LEVEL_COLORS,
  type RequirementStatus, type RequirementLevel
} from '@/lib/types';

const LEVEL_NODE_COLORS: Record<string, string> = {
  L1: '#EF4444', L2: '#F59E0B', L3: '#3B82F6', L4: '#8B5CF6', L5: '#6B7280',
};

const LINK_TYPE_COLORS: Record<string, string> = {
  parent_child: '#3B82F6',
  satisfaction: '#10B981',
  evolution: '#8B5CF6',
  dependency: '#F59E0B',
  rationale: '#06B6D4',
  contribution: '#14B8A6',
  verification: '#10B981',
  decomposition: '#3B82F6',
};

// ── Coverage bar ──
function CoverageBar({ label, value, pct, total, color }: { label: string; value: number; pct: number; total: number; color: string }) {
  return (
    <div className="flex-1">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[11px] text-slate-400">{label}</span>
        <span className="text-[11px] font-bold" style={{ color }}>{value}/{total} ({pct}%)</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-astra-surface-alt">
        <div className="h-full rounded-full transition-all duration-700" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

// ── Matrix cell ──
function MatrixCell({ count, hasItems }: { count: number; hasItems: boolean }) {
  if (hasItems) {
    return (
      <div className="flex items-center justify-center">
        <span className="rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-[11px] font-bold text-emerald-400">{count}</span>
      </div>
    );
  }
  return (
    <div className="flex items-center justify-center">
      <span className="rounded-full bg-red-500/10 px-2.5 py-0.5 text-[11px] font-bold text-red-400/60">0</span>
    </div>
  );
}

// ── D3 Graph component ──
function ForceGraph({ nodes, edges, onNodeClick }: {
  nodes: any[]; edges: any[]; onNodeClick: (id: number) => void;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [selectedNode, setSelectedNode] = useState<number | null>(null);
  const [positions, setPositions] = useState<Record<number, { x: number; y: number }>>({});
  const [dragging, setDragging] = useState<number | null>(null);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });

  // Simple force simulation using requestAnimationFrame
  useEffect(() => {
    if (nodes.length === 0) return;

    const W = 900, H = 500;
    const pos: Record<number, { x: number; y: number; vx: number; vy: number }> = {};

    // Initialize positions in a level-based layout
    const levelGroups: Record<string, any[]> = {};
    nodes.forEach(n => {
      if (!levelGroups[n.level]) levelGroups[n.level] = [];
      levelGroups[n.level].push(n);
    });

    const levels = ['L1', 'L2', 'L3', 'L4', 'L5'];
    levels.forEach((level, li) => {
      const group = levelGroups[level] || [];
      const xBase = 100 + li * ((W - 200) / Math.max(levels.length - 1, 1));
      group.forEach((n, ni) => {
        const yBase = 80 + ni * (Math.max(H - 160, 100) / Math.max(group.length, 1));
        pos[n.id] = {
          x: xBase + (Math.random() - 0.5) * 40,
          y: yBase + (Math.random() - 0.5) * 30,
          vx: 0, vy: 0,
        };
      });
    });

    // Simple force simulation (50 iterations)
    const nodeIds = new Set(nodes.map(n => n.id));
    for (let iter = 0; iter < 60; iter++) {
      const alpha = 0.3 * (1 - iter / 60);

      // Repulsion between all nodes
      const nodeArr = Object.keys(pos).map(Number);
      for (let i = 0; i < nodeArr.length; i++) {
        for (let j = i + 1; j < nodeArr.length; j++) {
          const a = pos[nodeArr[i]], b = pos[nodeArr[j]];
          let dx = b.x - a.x, dy = b.y - a.y;
          let dist = Math.sqrt(dx * dx + dy * dy) || 1;
          if (dist < 120) {
            const force = (120 - dist) * 0.15 * alpha;
            const fx = (dx / dist) * force, fy = (dy / dist) * force;
            a.vx -= fx; a.vy -= fy;
            b.vx += fx; b.vy += fy;
          }
        }
      }

      // Attraction along edges
      edges.forEach(e => {
        if (pos[e.source] && pos[e.target]) {
          const a = pos[e.source], b = pos[e.target];
          let dx = b.x - a.x, dy = b.y - a.y;
          let dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = (dist - 150) * 0.02 * alpha;
          const fx = (dx / dist) * force, fy = (dy / dist) * force;
          a.vx += fx; a.vy += fy;
          b.vx -= fx; b.vy -= fy;
        }
      });

      // Apply velocity and clamp
      nodeArr.forEach(id => {
        const p = pos[id];
        p.x += p.vx; p.y += p.vy;
        p.vx *= 0.8; p.vy *= 0.8;
        p.x = Math.max(30, Math.min(W - 30, p.x));
        p.y = Math.max(30, Math.min(H - 30, p.y));
      });
    }

    const result: Record<number, { x: number; y: number }> = {};
    Object.entries(pos).forEach(([id, p]) => { result[Number(id)] = { x: p.x, y: p.y }; });
    setPositions(result);
  }, [nodes, edges]);

  const handleMouseDown = (id: number, e: React.MouseEvent) => {
    e.preventDefault();
    const p = positions[id];
    if (!p) return;
    setDragging(id);
    setDragOffset({ x: e.clientX - p.x, y: e.clientY - p.y });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (dragging === null) return;
    const svgRect = svgRef.current?.getBoundingClientRect();
    if (!svgRect) return;
    const x = e.clientX - svgRect.left;
    const y = e.clientY - svgRect.top;
    setPositions(prev => ({ ...prev, [dragging]: { x: Math.max(30, Math.min(870, x)), y: Math.max(30, Math.min(470, y)) } }));
  };

  const handleMouseUp = () => setDragging(null);

  const handleNodeClick = (id: number) => {
    if (dragging !== null) return;
    setSelectedNode(prev => prev === id ? null : id);
  };

  const connectedIds = new Set<number>();
  if (selectedNode !== null) {
    connectedIds.add(selectedNode);
    edges.forEach(e => {
      if (e.source === selectedNode) connectedIds.add(e.target);
      if (e.target === selectedNode) connectedIds.add(e.source);
    });
    // Also parent/child
    nodes.forEach(n => {
      if (n.parent_id === selectedNode) connectedIds.add(n.id);
      if (n.id === selectedNode && n.parent_id) connectedIds.add(n.parent_id);
    });
  }

  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface overflow-hidden">
      <svg ref={svgRef} width="100%" height="500" viewBox="0 0 900 500"
        className="cursor-grab active:cursor-grabbing"
        onMouseMove={handleMouseMove} onMouseUp={handleMouseUp} onMouseLeave={handleMouseUp}>
        {/* Background grid */}
        <defs>
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(100,116,139,0.06)" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width="900" height="500" fill="url(#grid)" />

        {/* Edges */}
        {edges.map((e, i) => {
          const s = positions[e.source], t = positions[e.target];
          if (!s || !t) return null;
          const isHighlighted = selectedNode === null || (connectedIds.has(e.source) && connectedIds.has(e.target));
          const color = LINK_TYPE_COLORS[e.link_type] || '#475569';
          return (
            <line key={i} x1={s.x} y1={s.y} x2={t.x} y2={t.y}
              stroke={color} strokeWidth={isHighlighted ? 2 : 1}
              strokeOpacity={isHighlighted ? 0.7 : 0.15}
              strokeDasharray={e.link_type === 'parent_child' ? 'none' : '4 3'} />
          );
        })}

        {/* Nodes */}
        {nodes.map(n => {
          const p = positions[n.id];
          if (!p) return null;
          const color = LEVEL_NODE_COLORS[n.level] || '#6B7280';
          const isHighlighted = selectedNode === null || connectedIds.has(n.id);
          const isSelected = selectedNode === n.id;
          const radius = isSelected ? 22 : 16;
          return (
            <g key={n.id}
              onMouseDown={(e) => handleMouseDown(n.id, e)}
              onClick={() => handleNodeClick(n.id)}
              className="cursor-pointer">
              {/* Glow for selected */}
              {isSelected && <circle cx={p.x} cy={p.y} r={30} fill={color} fillOpacity={0.15} />}
              {/* Node circle */}
              <circle cx={p.x} cy={p.y} r={radius}
                fill={`${color}${isHighlighted ? '30' : '10'}`}
                stroke={color} strokeWidth={isSelected ? 3 : 1.5}
                strokeOpacity={isHighlighted ? 1 : 0.3} />
              {/* Level label */}
              <text x={p.x} y={p.y - 2} textAnchor="middle" fill={color}
                fontSize="9" fontWeight="700" fontFamily="monospace"
                opacity={isHighlighted ? 1 : 0.3}>
                {n.level}
              </text>
              {/* Req ID below */}
              <text x={p.x} y={p.y + 8} textAnchor="middle" fill={isHighlighted ? '#E2E8F0' : '#475569'}
                fontSize="7" fontWeight="600" fontFamily="monospace">
                {n.req_id.length > 12 ? n.req_id.substring(0, 12) : n.req_id}
              </text>
              {/* Title tooltip on hover */}
              <title>{n.req_id}: {n.title}</title>
            </g>
          );
        })}

        {/* Legend */}
        {['L1', 'L2', 'L3', 'L4', 'L5'].map((level, i) => (
          <g key={level} transform={`translate(20, ${20 + i * 22})`}>
            <circle cx={6} cy={6} r={6} fill={LEVEL_NODE_COLORS[level] + '30'} stroke={LEVEL_NODE_COLORS[level]} strokeWidth={1.5} />
            <text x={18} y={10} fill="#94A3B8" fontSize="10" fontWeight="600">{level}</text>
          </g>
        ))}

        {/* Link type legend */}
        {Object.entries(LINK_TYPE_COLORS).slice(0, 4).map(([type, color], i) => (
          <g key={type} transform={`translate(770, ${20 + i * 20})`}>
            <line x1={0} y1={6} x2={20} y2={6} stroke={color} strokeWidth={2} strokeDasharray={type === 'parent_child' ? 'none' : '4 3'} />
            <text x={26} y={10} fill="#94A3B8" fontSize="9">{type.replace('_', ' ')}</text>
          </g>
        ))}
      </svg>

      {/* Info bar */}
      {selectedNode !== null && (() => {
        const n = nodes.find(x => x.id === selectedNode);
        if (!n) return null;
        const connectionCount = connectedIds.size - 1;
        return (
          <div className="border-t border-astra-border px-4 py-3 flex items-center gap-3">
            <span className="rounded-full px-2 py-0.5 text-[10px] font-bold" style={{ background: `${LEVEL_NODE_COLORS[n.level]}20`, color: LEVEL_NODE_COLORS[n.level] }}>{n.level}</span>
            <span className="font-mono text-xs font-semibold text-blue-400">{n.req_id}</span>
            <span className="flex-1 truncate text-sm text-slate-300">{n.title}</span>
            <span className="text-xs text-slate-500">{connectionCount} connection{connectionCount !== 1 ? 's' : ''}</span>
            <button onClick={() => onNodeClick(n.id)} className="flex items-center gap-1 text-xs font-semibold text-blue-400 hover:text-blue-300">
              Open <ChevronRight className="h-3 w-3" />
            </button>
          </div>
        );
      })()}
    </div>
  );
}

// ══════════════════════════════════════
//  Main Page
// ══════════════════════════════════════
export default function TraceabilityPage() {
  const router = useRouter();
  const [projectId, setProjectId] = useState<number | null>(null);
  const [projectCode, setProjectCode] = useState('');
  const [viewMode, setViewMode] = useState<'matrix' | 'graph'>('matrix');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [matrixData, setMatrixData] = useState<any[]>([]);
  const [coverage, setCoverage] = useState<any>(null);
  const [graphData, setGraphData] = useState<{ nodes: any[]; edges: any[] }>({ nodes: [], edges: [] });

  useEffect(() => {
    projectsAPI.list().then(res => {
      if (res.data.length > 0) { setProjectId(res.data[0].id); setProjectCode(res.data[0].code); }
    });
  }, []);

  const fetchData = useCallback(async () => {
    if (!projectId) return;
    setLoading(true); setError('');
    try {
      const [matRes, covRes, graphRes] = await Promise.all([
        traceabilityAPI.getMatrix(projectId),
        traceabilityAPI.getCoverage(projectId),
        traceabilityAPI.getGraph(projectId),
      ]);
      setMatrixData(matRes.data.matrix || []);
      setCoverage(covRes.data);
      setGraphData(graphRes.data || { nodes: [], edges: [] });
    } catch (e: any) { setError(e.response?.data?.detail || 'Failed to load traceability data'); }
    finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading) return <div className="flex min-h-[60vh] items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-blue-500" /></div>;

  const total = coverage?.total || 0;

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Traceability Matrix</h1>
          <p className="mt-1 text-sm text-slate-500">{projectCode} · Requirements verification traceability</p>
        </div>
        <button onClick={fetchData} className="rounded-full border border-astra-border p-2 text-slate-400 transition hover:text-slate-200">
          <RefreshCw className="h-3.5 w-3.5" />
        </button>
      </div>

      {error && <div className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">{error}</div>}

      {/* Coverage Summary */}
      {coverage && total > 0 && (
        <div className="mb-6 rounded-xl border border-astra-border bg-astra-surface p-5">
          <h3 className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            <Shield className="h-3.5 w-3.5 text-blue-400" /> Traceability Coverage
          </h3>
          <div className="flex gap-6">
            <CoverageBar label="With Source Artifacts" value={coverage.with_source} pct={coverage.with_source_pct} total={total} color="#10B981" />
            <CoverageBar label="With Children" value={coverage.with_children} pct={coverage.with_children_pct} total={total} color="#3B82F6" />
            <CoverageBar label="With Verification" value={coverage.with_verification} pct={coverage.with_verification_pct} total={total} color="#8B5CF6" />
            <CoverageBar label="Orphans (no links)" value={coverage.orphans} pct={coverage.orphan_pct} total={total} color="#EF4444" />
          </div>
        </div>
      )}

      {/* View toggle */}
      <div className="mb-4 flex items-center gap-3">
        <div className="flex rounded-lg border border-astra-border overflow-hidden">
          <button onClick={() => setViewMode('matrix')}
            className={`flex items-center gap-1.5 px-4 py-2 text-xs font-semibold transition ${
              viewMode === 'matrix' ? 'bg-blue-500 text-white' : 'bg-astra-surface text-slate-400 hover:text-slate-200'
            }`}>
            <Grid3X3 className="h-3.5 w-3.5" /> Matrix
          </button>
          <button onClick={() => setViewMode('graph')}
            className={`flex items-center gap-1.5 px-4 py-2 text-xs font-semibold transition ${
              viewMode === 'graph' ? 'bg-blue-500 text-white' : 'bg-astra-surface text-slate-400 hover:text-slate-200'
            }`}>
            <GitBranch className="h-3.5 w-3.5" /> Graph
          </button>
        </div>
        <span className="text-[11px] text-slate-500">{total} requirements · {graphData.edges.length} links</span>
      </div>

      {/* ── Matrix View ── */}
      {viewMode === 'matrix' && (
        matrixData.length === 0 ? (
          <div className="rounded-xl border border-astra-border bg-astra-surface py-16 text-center">
            <FileText className="mx-auto h-10 w-10 text-slate-600 mb-3" />
            <div className="text-sm text-slate-500">No requirements to show</div>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-astra-border bg-astra-surface">
            <table className="w-full">
              <thead>
                <tr className="border-b border-astra-border bg-astra-surface-alt">
                  <th className="px-4 py-2.5 text-left text-[10px] font-bold uppercase tracking-wider text-slate-500 w-[100px]">ID</th>
                  <th className="px-2 py-2.5 text-left text-[10px] font-bold uppercase tracking-wider text-slate-500 w-[35px]">Lvl</th>
                  <th className="px-4 py-2.5 text-left text-[10px] font-bold uppercase tracking-wider text-slate-500">Title</th>
                  <th className="px-4 py-2.5 text-center text-[10px] font-bold uppercase tracking-wider text-slate-500 w-[90px]">Status</th>
                  <th className="px-4 py-2.5 text-center text-[10px] font-bold uppercase tracking-wider text-emerald-500 w-[100px]">
                    <div className="flex items-center justify-center gap-1"><FileText className="h-3 w-3" /> Sources</div>
                  </th>
                  <th className="px-4 py-2.5 text-center text-[10px] font-bold uppercase tracking-wider text-blue-400 w-[100px]">
                    <div className="flex items-center justify-center gap-1"><GitBranch className="h-3 w-3" /> Children</div>
                  </th>
                  <th className="px-4 py-2.5 text-center text-[10px] font-bold uppercase tracking-wider text-violet-400 w-[100px]">
                    <div className="flex items-center justify-center gap-1"><Shield className="h-3 w-3" /> V&amp;V</div>
                  </th>
                  <th className="px-4 py-2.5 text-center text-[10px] font-bold uppercase tracking-wider text-slate-500 w-[70px]">Links</th>
                </tr>
              </thead>
              <tbody>
                {matrixData.map((row, i) => {
                  const sc = STATUS_COLORS[row.status as RequirementStatus];
                  const lvl = (row.level || 'L1') as RequirementLevel;
                  const hasAllTraces = row.source_artifact_count > 0 && row.children_count > 0 && row.verification_count > 0;
                  const hasNoTraces = row.source_artifact_count === 0 && row.children_count === 0 && row.verification_count === 0;
                  return (
                    <tr key={row.id}
                      onClick={() => router.push(`/requirements/${row.id}`)}
                      className={`border-b border-astra-border transition-colors hover:bg-astra-surface-hover cursor-pointer ${
                        hasNoTraces ? 'bg-red-500/[0.03]' : hasAllTraces ? 'bg-emerald-500/[0.02]' : ''
                      }`}>
                      <td className="px-4 py-2.5">
                        <span className="font-mono text-xs font-semibold text-blue-400">{row.req_id}</span>
                      </td>
                      <td className="px-2 py-2.5">
                        <span className="rounded-full px-1.5 py-0.5 text-[9px] font-bold"
                          style={{ background: `${LEVEL_COLORS[lvl]}20`, color: LEVEL_COLORS[lvl] }}>{lvl}</span>
                      </td>
                      <td className="px-4 py-2.5">
                        <span className="text-[13px] text-slate-200 truncate block max-w-[300px]">{row.title}</span>
                      </td>
                      <td className="px-4 py-2.5 text-center">
                        <span className="inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold"
                          style={{ background: sc?.bg, color: sc?.text }}>{STATUS_LABELS[row.status as RequirementStatus] || row.status}</span>
                      </td>
                      <td className="px-4 py-2.5"><MatrixCell count={row.source_artifact_count} hasItems={row.source_artifact_count > 0} /></td>
                      <td className="px-4 py-2.5"><MatrixCell count={row.children_count} hasItems={row.children_count > 0} /></td>
                      <td className="px-4 py-2.5"><MatrixCell count={row.verification_count} hasItems={row.verification_count > 0} /></td>
                      <td className="px-4 py-2.5 text-center">
                        <span className="text-xs font-semibold text-slate-400">{row.total_links}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {/* Summary footer */}
            <div className="border-t border-astra-border px-4 py-3 flex items-center gap-6 bg-astra-surface-alt">
              <span className="text-[11px] text-slate-500">{matrixData.length} requirements</span>
              <div className="flex items-center gap-1.5">
                <div className="h-2 w-2 rounded-full bg-emerald-400" />
                <span className="text-[11px] text-slate-500">{matrixData.filter(r => r.source_artifact_count > 0 && r.children_count > 0 && r.verification_count > 0).length} fully traced</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="h-2 w-2 rounded-full bg-red-400" />
                <span className="text-[11px] text-slate-500">{matrixData.filter(r => r.source_artifact_count === 0 && r.children_count === 0 && r.verification_count === 0).length} no traces</span>
              </div>
            </div>
          </div>
        )
      )}

      {/* ── Graph View ── */}
      {viewMode === 'graph' && (
        graphData.nodes.length === 0 ? (
          <div className="rounded-xl border border-astra-border bg-astra-surface py-16 text-center">
            <GitBranch className="mx-auto h-10 w-10 text-slate-600 mb-3" />
            <div className="text-sm text-slate-500">No requirements to graph</div>
          </div>
        ) : (
          <div>
            <div className="mb-2 text-[11px] text-slate-500">
              Click a node to highlight its connections. Drag nodes to rearrange. Click the Open button to view details.
            </div>
            <ForceGraph
              nodes={graphData.nodes}
              edges={graphData.edges}
              onNodeClick={(id) => router.push(`/requirements/${id}`)}
            />
          </div>
        )
      )}
    </div>
  );
}
