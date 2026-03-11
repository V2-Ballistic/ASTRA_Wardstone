/**
 * ASTRA — Impact Analysis Panel
 * ================================
 * File: frontend/src/components/impact/ImpactAnalysisPanel.tsx   ← NEW
 *
 * Full impact analysis tab for the requirement detail page.
 * Contains:
 *   - "Run Impact Analysis" trigger
 *   - AI summary card
 *   - Risk level indicator
 *   - Interactive dependency graph (SVG)
 *   - Affected entities lists (direct / indirect)
 *   - Affected verifications & baselines
 */

'use client';

import { useState, useCallback } from 'react';
import {
  Zap, Loader2, AlertTriangle, CheckCircle, XCircle,
  ChevronRight, Network, FlaskConical, Archive, Shield,
  ArrowUpRight, ArrowDownRight, Info, Clock,
} from 'lucide-react';
import {
  impactAPI,
  type ImpactReport,
  type DependencyTree,
  type ImpactItem,
} from '@/lib/impact-api';

interface ImpactAnalysisPanelProps {
  requirementId: number;
  projectId: number;
  onNavigate?: (entityType: string, entityId: number) => void;
}

const RISK_CONFIG: Record<string, { color: string; bg: string; border: string; icon: any; label: string }> = {
  low:      { color: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/30', icon: CheckCircle, label: 'Low Risk' },
  medium:   { color: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/30', icon: AlertTriangle, label: 'Medium Risk' },
  high:     { color: 'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/30', icon: AlertTriangle, label: 'High Risk' },
  critical: { color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/30', icon: XCircle, label: 'Critical Risk' },
};

export default function ImpactAnalysisPanel({
  requirementId,
  projectId,
  onNavigate,
}: ImpactAnalysisPanelProps) {
  const [loading, setLoading] = useState(false);
  const [loadingDeps, setLoadingDeps] = useState(false);
  const [report, setReport] = useState<ImpactReport | null>(null);
  const [deps, setDeps] = useState<DependencyTree | null>(null);
  const [changeDesc, setChangeDesc] = useState('');
  const [error, setError] = useState('');
  const [activeSection, setActiveSection] = useState<'graph' | 'items' | 'verifications'>('graph');

  const runAnalysis = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [reportRes, depsRes] = await Promise.all([
        impactAPI.analyze(requirementId, changeDesc),
        impactAPI.getDependencies(requirementId),
      ]);
      setReport(reportRes.data);
      setDeps(depsRes.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Impact analysis failed');
    } finally {
      setLoading(false);
    }
  }, [requirementId, changeDesc]);

  const loadDependencies = useCallback(async () => {
    setLoadingDeps(true);
    try {
      const res = await impactAPI.getDependencies(requirementId);
      setDeps(res.data);
    } catch {
      /* non-critical */
    } finally {
      setLoadingDeps(false);
    }
  }, [requirementId]);

  return (
    <div className="space-y-4">
      {/* ── Trigger Bar ── */}
      <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-slate-500">
              Change Description (optional)
            </label>
            <input
              type="text"
              value={changeDesc}
              onChange={(e) => setChangeDesc(e.target.value)}
              placeholder="e.g., Updating response time threshold from 10s to 5s"
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:border-blue-500/50 focus:outline-none"
            />
          </div>
          <button
            onClick={runAnalysis}
            disabled={loading}
            className="flex shrink-0 items-center gap-2 rounded-lg bg-gradient-to-r from-blue-600 to-violet-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-blue-500/20 transition hover:shadow-blue-500/30 disabled:opacity-50"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Zap className="h-4 w-4" />
            )}
            {loading ? 'Analyzing…' : 'Run Impact Analysis'}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-2 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* ── Quick Dependencies (no full analysis needed) ── */}
      {!report && !loading && (
        <button
          onClick={loadDependencies}
          disabled={loadingDeps}
          className="flex items-center gap-2 text-xs text-blue-400 transition hover:text-blue-300"
        >
          {loadingDeps ? <Loader2 className="h-3 w-3 animate-spin" /> : <Network className="h-3 w-3" />}
          {loadingDeps ? 'Loading…' : 'Load Dependency Tree'}
        </button>
      )}

      {/* ── Results ── */}
      {report && (
        <>
          {/* Risk + Summary Header */}
          <RiskSummaryCard report={report} />

          {/* Metric Cards */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <MetricCard label="Direct" value={report.total_direct} color="text-orange-400" />
            <MetricCard label="Indirect" value={report.total_indirect} color="text-amber-400" />
            <MetricCard label="Verifications" value={report.affected_verifications.length} color="text-violet-400" />
            <MetricCard label="Baselines" value={report.affected_baselines.length} color="text-sky-400" />
          </div>

          {/* Section Tabs */}
          <div className="flex gap-1 rounded-lg border border-astra-border bg-astra-surface p-1">
            {(['graph', 'items', 'verifications'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveSection(tab)}
                className={`flex-1 rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                  activeSection === tab
                    ? 'bg-blue-500/15 text-blue-400'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {tab === 'graph' ? 'Dependency Graph' : tab === 'items' ? 'Affected Items' : 'Verifications & Baselines'}
              </button>
            ))}
          </div>

          {/* Section Content */}
          {activeSection === 'graph' && deps && (
            <DependencyGraphView tree={deps} changedReqId={report.changed_requirement.req_id} onNavigate={onNavigate} />
          )}

          {activeSection === 'items' && (
            <AffectedItemsList
              direct={report.direct_impacts}
              indirect={report.indirect_impacts}
              onNavigate={onNavigate}
            />
          )}

          {activeSection === 'verifications' && (
            <VerificationBaselineView
              verifications={report.affected_verifications}
              baselines={report.affected_baselines}
            />
          )}

          {/* Analysis metadata */}
          <div className="flex items-center gap-4 text-[10px] text-slate-600">
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {report.analysis_duration_ms}ms
            </span>
            <span>Depth: {report.dependency_depth} hops</span>
            {report.analyzed_at && (
              <span>{new Date(report.analyzed_at).toLocaleString()}</span>
            )}
            {!report.ai_available && (
              <span className="text-amber-500">AI summary unavailable</span>
            )}
          </div>
        </>
      )}

      {/* Dependency tree without full analysis */}
      {!report && deps && (
        <DependencyGraphView tree={deps} onNavigate={onNavigate} />
      )}
    </div>
  );
}


// ══════════════════════════════════════
//  Sub-components
// ══════════════════════════════════════

function RiskSummaryCard({ report }: { report: ImpactReport }) {
  const risk = RISK_CONFIG[report.risk_level] || RISK_CONFIG.low;
  const RiskIcon = risk.icon;

  return (
    <div className={`rounded-xl border ${risk.border} ${risk.bg} p-4`}>
      <div className="flex items-start gap-3">
        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${risk.bg}`}>
          <RiskIcon className={`h-5 w-5 ${risk.color}`} />
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className={`text-sm font-bold ${risk.color}`}>{risk.label}</span>
            <span className="text-[10px] text-slate-500">
              {report.total_affected} affected · {report.dependency_depth} levels deep
            </span>
          </div>
          <p className="mt-1.5 text-[12px] leading-relaxed text-slate-300">
            {report.ai_summary}
          </p>
          {report.risk_factors.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {report.risk_factors.map((factor, i) => (
                <span key={i} className="rounded-full border border-slate-700/50 bg-slate-800/40 px-2 py-0.5 text-[9px] text-slate-400">
                  {factor}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MetricCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="rounded-lg border border-astra-border bg-astra-surface p-3 text-center">
      <div className={`text-xl font-bold ${color}`}>{value}</div>
      <div className="text-[10px] text-slate-500">{label}</div>
    </div>
  );
}


// ══════════════════════════════════════
//  Interactive Dependency Graph (SVG)
// ══════════════════════════════════════

function DependencyGraphView({
  tree,
  changedReqId,
  onNavigate,
}: {
  tree: DependencyTree;
  changedReqId?: string;
  onNavigate?: (entityType: string, entityId: number) => void;
}) {
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  // Layout constants
  const NODE_W = 160;
  const NODE_H = 48;
  const H_GAP = 40;
  const V_GAP = 24;
  const ROOT_X = 400;
  const ROOT_Y = 40;

  // Position calculation
  const upCount = tree.upstream.length;
  const downCount = tree.downstream.length;
  const totalHeight = Math.max(upCount, downCount, 1) * (NODE_H + V_GAP) + ROOT_Y + NODE_H + 40;
  const svgWidth = ROOT_X + NODE_W + H_GAP + NODE_W + 40;

  const rootNode = tree.root_requirement;
  const rootId = `root-${rootNode.id}`;

  // Position upstream nodes on the left
  const upNodes = tree.upstream.map((node, i) => ({
    ...node,
    x: ROOT_X - H_GAP - NODE_W,
    y: ROOT_Y + (i * (NODE_H + V_GAP)),
    key: `up-${node.entity_type}-${node.entity_id}`,
  }));

  // Position downstream nodes on the right
  const downNodes = tree.downstream.map((node, i) => ({
    ...node,
    x: ROOT_X + NODE_W + H_GAP,
    y: ROOT_Y + (i * (NODE_H + V_GAP)),
    key: `dn-${node.entity_type}-${node.entity_id}`,
  }));

  // Root position (vertically centered)
  const maxNodes = Math.max(upCount, downCount, 1);
  const rootY = ROOT_Y + ((maxNodes - 1) * (NODE_H + V_GAP)) / 2;

  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-200">
        <Network className="h-4 w-4 text-blue-400" />
        Dependency Graph
        <span className="text-[10px] font-normal text-slate-500">
          {upCount} upstream · {downCount} downstream
        </span>
      </h3>

      <div className="overflow-x-auto">
        <svg
          width={Math.max(svgWidth, 600)}
          height={Math.max(totalHeight, 120)}
          className="mx-auto"
        >
          {/* Direction labels */}
          <text x={ROOT_X - H_GAP - NODE_W / 2} y={16} textAnchor="middle" className="fill-slate-600 text-[10px]">
            ← UPSTREAM (traces to)
          </text>
          <text x={ROOT_X + NODE_W + H_GAP + NODE_W / 2} y={16} textAnchor="middle" className="fill-slate-600 text-[10px]">
            DOWNSTREAM (traces from) →
          </text>

          {/* Connection lines — upstream to root */}
          {upNodes.map((node) => (
            <line
              key={`line-${node.key}`}
              x1={node.x + NODE_W}
              y1={node.y + NODE_H / 2}
              x2={ROOT_X}
              y2={rootY + NODE_H / 2}
              stroke={hoveredNode === node.key ? '#60a5fa' : '#334155'}
              strokeWidth={hoveredNode === node.key ? 2 : 1}
              strokeDasharray={node.hop_count > 1 ? '4 4' : undefined}
              className="transition-all"
            />
          ))}

          {/* Connection lines — root to downstream */}
          {downNodes.map((node) => (
            <line
              key={`line-${node.key}`}
              x1={ROOT_X + NODE_W}
              y1={rootY + NODE_H / 2}
              x2={node.x}
              y2={node.y + NODE_H / 2}
              stroke={hoveredNode === node.key ? '#f59e0b' : '#334155'}
              strokeWidth={hoveredNode === node.key ? 2 : 1}
              strokeDasharray={node.hop_count > 1 ? '4 4' : undefined}
              className="transition-all"
            />
          ))}

          {/* Root node — highlighted red */}
          <g
            transform={`translate(${ROOT_X}, ${rootY})`}
            className="cursor-pointer"
          >
            <rect
              width={NODE_W} height={NODE_H} rx={8}
              fill="#1e1b4b" stroke="#ef4444" strokeWidth={2}
              className="transition-all"
            />
            <text x={NODE_W / 2} y={18} textAnchor="middle" className="fill-red-400 text-[10px] font-bold">
              {rootNode.req_id || changedReqId || 'ROOT'}
            </text>
            <text x={NODE_W / 2} y={34} textAnchor="middle" className="fill-slate-400 text-[9px]">
              {(rootNode.title || '').substring(0, 22)}{(rootNode.title || '').length > 22 ? '…' : ''}
            </text>
          </g>

          {/* Upstream nodes — blue/violet tones */}
          {upNodes.map((node) => (
            <g
              key={node.key}
              transform={`translate(${node.x}, ${node.y})`}
              onMouseEnter={() => setHoveredNode(node.key)}
              onMouseLeave={() => setHoveredNode(null)}
              onClick={() => onNavigate?.(node.entity_type, node.entity_id)}
              className="cursor-pointer"
            >
              <rect
                width={NODE_W} height={NODE_H} rx={8}
                fill={hoveredNode === node.key ? '#1e293b' : '#0f172a'}
                stroke={node.hop_count === 1 ? '#3b82f6' : '#6366f1'}
                strokeWidth={hoveredNode === node.key ? 2 : 1}
                className="transition-all"
              />
              <text x={NODE_W / 2} y={18} textAnchor="middle" className="fill-blue-400 text-[10px] font-bold">
                {node.identifier}
              </text>
              <text x={NODE_W / 2} y={34} textAnchor="middle" className="fill-slate-500 text-[9px]">
                {node.title.substring(0, 22)}{node.title.length > 22 ? '…' : ''}
              </text>
            </g>
          ))}

          {/* Downstream nodes — orange/amber tones */}
          {downNodes.map((node) => (
            <g
              key={node.key}
              transform={`translate(${node.x}, ${node.y})`}
              onMouseEnter={() => setHoveredNode(node.key)}
              onMouseLeave={() => setHoveredNode(null)}
              onClick={() => onNavigate?.(node.entity_type, node.entity_id)}
              className="cursor-pointer"
            >
              <rect
                width={NODE_W} height={NODE_H} rx={8}
                fill={hoveredNode === node.key ? '#1e293b' : '#0f172a'}
                stroke={node.hop_count === 1 ? '#f59e0b' : '#fbbf24'}
                strokeWidth={hoveredNode === node.key ? 2 : 1}
                strokeDasharray={node.hop_count > 1 ? '4 2' : undefined}
                className="transition-all"
              />
              <text x={NODE_W / 2} y={18} textAnchor="middle"
                className={`text-[10px] font-bold ${node.entity_type === 'verification' ? 'fill-violet-400' : 'fill-amber-400'}`}>
                {node.identifier}
              </text>
              <text x={NODE_W / 2} y={34} textAnchor="middle" className="fill-slate-500 text-[9px]">
                {node.title.substring(0, 22)}{node.title.length > 22 ? '…' : ''}
              </text>
            </g>
          ))}
        </svg>
      </div>

      {/* Legend */}
      <div className="mt-3 flex flex-wrap items-center gap-4 text-[10px] text-slate-500">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded-sm border-2 border-red-500 bg-red-500/20" />
          Changed
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded-sm border-2 border-orange-400" />
          Direct impact
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded-sm border border-dashed border-amber-400" />
          Indirect impact
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded-sm border-2 border-blue-500" />
          Upstream
        </span>
      </div>
    </div>
  );
}


// ══════════════════════════════════════
//  Affected Items List
// ══════════════════════════════════════

function AffectedItemsList({
  direct,
  indirect,
  onNavigate,
}: {
  direct: ImpactItem[];
  indirect: ImpactItem[];
  onNavigate?: (entityType: string, entityId: number) => void;
}) {
  return (
    <div className="space-y-3">
      {/* Direct */}
      {direct.length > 0 && (
        <div className="rounded-xl border border-orange-500/20 bg-orange-500/5 p-3">
          <h4 className="mb-2 flex items-center gap-2 text-xs font-bold text-orange-400">
            <ArrowDownRight className="h-3.5 w-3.5" />
            Direct Impacts ({direct.length})
          </h4>
          <div className="space-y-1.5">
            {direct.map((item) => (
              <ImpactItemRow key={`${item.entity_type}-${item.entity_id}`} item={item} onNavigate={onNavigate} />
            ))}
          </div>
        </div>
      )}

      {/* Indirect */}
      {indirect.length > 0 && (
        <div className="rounded-xl border border-amber-500/10 bg-amber-500/5 p-3">
          <h4 className="mb-2 flex items-center gap-2 text-xs font-bold text-amber-400">
            <ArrowUpRight className="h-3.5 w-3.5" />
            Indirect Impacts ({indirect.length})
          </h4>
          <div className="space-y-1.5">
            {indirect.map((item) => (
              <ImpactItemRow key={`${item.entity_type}-${item.entity_id}`} item={item} onNavigate={onNavigate} />
            ))}
          </div>
        </div>
      )}

      {direct.length === 0 && indirect.length === 0 && (
        <div className="flex items-center gap-2 py-6 text-center text-sm text-slate-500">
          <CheckCircle className="h-4 w-4 text-emerald-500" />
          No downstream impacts detected. This requirement is a leaf node.
        </div>
      )}
    </div>
  );
}

function ImpactItemRow({
  item,
  onNavigate,
}: {
  item: ImpactItem;
  onNavigate?: (entityType: string, entityId: number) => void;
}) {
  const typeIcons: Record<string, any> = {
    requirement: Shield,
    verification: FlaskConical,
    source_artifact: Archive,
  };
  const Icon = typeIcons[item.entity_type] || Info;

  return (
    <div
      onClick={() => onNavigate?.(item.entity_type, item.entity_id)}
      className="flex items-center gap-2.5 rounded-lg border border-slate-700/30 bg-slate-800/20 px-3 py-2 transition hover:bg-slate-800/40 cursor-pointer"
    >
      <Icon className="h-3.5 w-3.5 shrink-0 text-slate-500" />
      <span className="font-mono text-[11px] font-semibold text-blue-400">
        {item.entity_identifier}
      </span>
      <span className="min-w-0 flex-1 truncate text-[11px] text-slate-400">
        {item.entity_title}
      </span>
      <span className="shrink-0 rounded-full bg-slate-700/40 px-1.5 py-0.5 text-[9px] text-slate-500">
        {item.hop_count} hop{item.hop_count !== 1 ? 's' : ''}
      </span>
      {item.relationship_path.length > 0 && (
        <ChevronRight className="h-3 w-3 shrink-0 text-slate-600" />
      )}
    </div>
  );
}


// ══════════════════════════════════════
//  Verifications & Baselines
// ══════════════════════════════════════

function VerificationBaselineView({
  verifications,
  baselines,
}: {
  verifications: ImpactReport['affected_verifications'];
  baselines: ImpactReport['affected_baselines'];
}) {
  return (
    <div className="space-y-4">
      {/* Verifications */}
      <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
        <h4 className="mb-3 flex items-center gap-2 text-xs font-bold text-violet-400">
          <FlaskConical className="h-3.5 w-3.5" />
          Affected Verifications ({verifications.length})
        </h4>
        {verifications.length === 0 ? (
          <p className="text-[11px] text-slate-500">No verifications affected.</p>
        ) : (
          <div className="space-y-2">
            {verifications.map((v) => (
              <div key={v.verification_id} className="flex items-center gap-3 rounded-lg border border-slate-700/30 bg-slate-800/20 px-3 py-2">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[11px] font-semibold text-violet-400">
                      VER-{String(v.verification_id).padStart(3, '0')}
                    </span>
                    <span className="rounded-full bg-slate-700/40 px-1.5 py-0.5 text-[9px] text-slate-400">
                      {v.method}
                    </span>
                    <span className={`rounded-full px-1.5 py-0.5 text-[9px] font-semibold ${
                      v.current_status === 'pass' ? 'bg-emerald-500/15 text-emerald-400' :
                      v.current_status === 'fail' ? 'bg-red-500/15 text-red-400' :
                      'bg-slate-500/15 text-slate-400'
                    }`}>
                      {v.current_status}
                    </span>
                  </div>
                  <p className="mt-0.5 text-[10px] text-slate-500">{v.reason}</p>
                </div>
                {v.needs_rerun && (
                  <span className="shrink-0 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[9px] font-bold text-amber-400">
                    NEEDS RE-RUN
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Baselines */}
      <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
        <h4 className="mb-3 flex items-center gap-2 text-xs font-bold text-sky-400">
          <Archive className="h-3.5 w-3.5" />
          Affected Baselines ({baselines.length})
        </h4>
        {baselines.length === 0 ? (
          <p className="text-[11px] text-slate-500">No baselines affected.</p>
        ) : (
          <div className="space-y-2">
            {baselines.map((b) => (
              <div key={b.baseline_id} className="flex items-center gap-3 rounded-lg border border-slate-700/30 bg-slate-800/20 px-3 py-2">
                <Archive className="h-3.5 w-3.5 shrink-0 text-sky-400" />
                <div className="flex-1">
                  <span className="text-[11px] font-semibold text-slate-200">{b.baseline_name}</span>
                  <span className="ml-2 text-[10px] text-slate-500">
                    {b.requirements_count} reqs
                    {b.created_at && ` · ${new Date(b.created_at).toLocaleDateString()}`}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
