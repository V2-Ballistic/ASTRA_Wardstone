'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  Search, Plus, Loader2, RefreshCw, ChevronDown, ChevronRight,
  List, GitBranch, AlertTriangle, CheckCircle, Archive
} from 'lucide-react';
import {
  STATUS_COLORS, STATUS_LABELS, LEVEL_COLORS, LEVEL_LABELS, PRIORITY_COLORS,
  type RequirementStatus, type RequirementLevel, type Priority, type Requirement
} from '@/lib/types';
import { requirementsAPI, projectsAPI, baselinesAPI } from '@/lib/api';

// ── Shared small components ──

function QualityDot({ score }: { score: number }) {
  const color = score >= 90 ? '#10B981' : score >= 75 ? '#F59E0B' : '#EF4444';
  return (
    <div className="flex items-center gap-1.5">
      <div className="h-2 w-2 rounded-full" style={{ background: color, boxShadow: `0 0 6px ${color}66` }} />
      <span className="font-mono text-xs font-semibold" style={{ color }}>{score}</span>
    </div>
  );
}

function TypeBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    functional: '#3B82F6', performance: '#F59E0B', security: '#EF4444',
    interface: '#8B5CF6', environmental: '#10B981', constraint: '#6B7280',
    safety: '#F97316', reliability: '#06B6D4', maintainability: '#14B8A6', derived: '#A78BFA',
  };
  const color = colors[type] || '#6B7280';
  return (
    <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
      style={{ background: `${color}20`, color }}>
      {type.charAt(0).toUpperCase() + type.slice(1)}
    </span>
  );
}

function PriorityIndicator({ priority }: { priority: string }) {
  const color = PRIORITY_COLORS[priority as Priority] || '#6B7280';
  return (
    <div className="flex items-center gap-1">
      <div className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
      <span className="text-[11px] capitalize" style={{ color }}>{priority}</span>
    </div>
  );
}

function LevelBadge({ level }: { level: string }) {
  const lvl = (level || 'L1') as RequirementLevel;
  return (
    <span className="rounded-full px-1.5 py-0.5 text-center text-[9px] font-bold"
      style={{ background: `${LEVEL_COLORS[lvl]}20`, color: LEVEL_COLORS[lvl] }}>
      {lvl}
    </span>
  );
}

// ── Tree types ──

interface TreeNode {
  requirement: Requirement;
  children: TreeNode[];
}

function buildTree(requirements: Requirement[]): TreeNode[] {
  const map = new Map<number, TreeNode>();
  const roots: TreeNode[] = [];

  // Create nodes
  for (const req of requirements) {
    map.set(req.id, { requirement: req, children: [] });
  }

  // Build hierarchy
  for (const req of requirements) {
    const node = map.get(req.id)!;
    if (req.parent_id && map.has(req.parent_id)) {
      map.get(req.parent_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  }

  // Sort children by level then req_id
  const sortNodes = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => {
      const levelDiff = (a.requirement.level || 'L1').localeCompare(b.requirement.level || 'L1');
      if (levelDiff !== 0) return levelDiff;
      return a.requirement.req_id.localeCompare(b.requirement.req_id);
    });
    for (const node of nodes) sortNodes(node.children);
  };
  sortNodes(roots);

  return roots;
}

// ── Tree Node Component ──

function TreeNodeRow({
  node,
  depth,
  expanded,
  onToggle,
  onNavigate,
}: {
  node: TreeNode;
  depth: number;
  expanded: Set<number>;
  onToggle: (id: number) => void;
  onNavigate: (id: number) => void;
}) {
  const req = node.requirement;
  const hasChildren = node.children.length > 0;
  const isExpanded = expanded.has(req.id);
  const lvl = (req.level || 'L1') as RequirementLevel;
  const sc = STATUS_COLORS[req.status as RequirementStatus];
  const levelNum = parseInt(lvl.replace('L', ''));

  // Coverage warning: if this is L1-L4 and has no children, flag it
  const isMissingChildren = levelNum < 5 && !hasChildren && req.status !== 'deleted' && req.status !== 'deferred';

  return (
    <>
      <div
        onClick={() => onNavigate(req.id)}
        className="group flex items-center border-b border-astra-border py-2.5 pr-4 transition-colors hover:bg-astra-surface-hover cursor-pointer"
        style={{ paddingLeft: `${16 + depth * 28}px` }}
      >
        {/* Expand/collapse or spacer */}
        <div className="mr-2 flex h-5 w-5 items-center justify-center">
          {hasChildren ? (
            <button onClick={(e) => { e.stopPropagation(); onToggle(req.id); }}
              className="flex h-5 w-5 items-center justify-center rounded transition hover:bg-slate-700">
              {isExpanded
                ? <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
                : <ChevronRight className="h-3.5 w-3.5 text-slate-400" />}
            </button>
          ) : (
            <div className="h-1.5 w-1.5 rounded-full bg-slate-600" />
          )}
        </div>

        {/* Tree line connector */}
        {depth > 0 && (
          <div className="mr-2 flex items-center">
            <div className="h-px w-3" style={{ background: LEVEL_COLORS[lvl] + '40' }} />
          </div>
        )}

        {/* Level badge */}
        <div className="mr-2.5">
          <LevelBadge level={req.level} />
        </div>

        {/* Req ID */}
        <span className="mr-3 font-mono text-xs font-semibold text-blue-400 whitespace-nowrap">{req.req_id}</span>

        {/* Title + statement */}
        <div className="mr-3 min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-[13px] font-medium text-slate-200">{req.title}</span>
            {isMissingChildren && (
              <span className="flex items-center gap-0.5 rounded-full bg-amber-500/10 px-1.5 py-0.5 text-[9px] font-bold text-amber-400 whitespace-nowrap">
                <AlertTriangle className="h-2.5 w-2.5" /> No children
              </span>
            )}
          </div>
          <div className="mt-0.5 truncate text-[11px] text-slate-500">{req.statement}</div>
        </div>

        {/* Status */}
        <span className="mr-3 inline-flex w-fit whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px] font-semibold"
          style={{ background: sc?.bg, color: sc?.text }}>
          {STATUS_LABELS[req.status as RequirementStatus] || req.status}
        </span>

        {/* Type */}
        <div className="mr-3">
          <TypeBadge type={req.req_type} />
        </div>

        {/* Priority */}
        <div className="mr-3">
          <PriorityIndicator priority={req.priority} />
        </div>

        {/* Quality */}
        <QualityDot score={req.quality_score} />

        {/* Children count */}
        {hasChildren && (
          <span className="ml-3 rounded-full bg-slate-700/50 px-2 py-0.5 text-[10px] font-bold text-slate-400">
            {node.children.length}
          </span>
        )}
      </div>

      {/* Render children if expanded */}
      {isExpanded && node.children.map((child) => (
        <TreeNodeRow
          key={child.requirement.id}
          node={child}
          depth={depth + 1}
          expanded={expanded}
          onToggle={onToggle}
          onNavigate={onNavigate}
        />
      ))}
    </>
  );
}

// ── Level Summary Bar ──

function LevelSummary({ requirements }: { requirements: Requirement[] }) {
  const levels = ['L1', 'L2', 'L3', 'L4', 'L5'] as RequirementLevel[];
  const counts = levels.map(l => ({
    level: l,
    count: requirements.filter(r => (r.level || 'L1') === l).length,
  }));
  const total = requirements.length || 1;

  return (
    <div className="mb-6 rounded-xl border border-astra-border bg-astra-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Decomposition Coverage</h3>
        <span className="text-[11px] text-slate-500">{requirements.length} total requirements</span>
      </div>
      <div className="flex gap-2">
        {counts.map(({ level, count }) => {
          const pct = Math.round((count / total) * 100);
          return (
            <div key={level} className="flex-1">
              <div className="mb-1 flex items-center justify-between">
                <span className="text-[11px] font-bold" style={{ color: LEVEL_COLORS[level] }}>{level}</span>
                <span className="text-[11px] font-semibold text-slate-400">{count}</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-astra-surface-alt">
                <div className="h-full rounded-full transition-all duration-500"
                  style={{ width: `${pct}%`, background: LEVEL_COLORS[level] }} />
              </div>
              <div className="mt-0.5 text-center text-[9px] text-slate-500">{LEVEL_LABELS[level].split(' — ')[1]}</div>
            </div>
          );
        })}
      </div>

      {/* Orphan warning */}
      {(() => {
        const orphanCount = requirements.filter(r => {
          const lvlNum = parseInt((r.level || 'L1').replace('L', ''));
          return lvlNum > 1 && !r.parent_id;
        }).length;
        if (orphanCount === 0) return null;
        return (
          <div className="mt-3 flex items-center gap-2 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2">
            <AlertTriangle className="h-3.5 w-3.5 text-amber-400 shrink-0" />
            <span className="text-xs text-amber-300">
              {orphanCount} requirement{orphanCount !== 1 ? 's' : ''} below L1 with no parent — link them to establish traceability
            </span>
          </div>
        );
      })()}
    </div>
  );
}

// ── Main Page ──

export default function RequirementsPage() {
  const router = useRouter();
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [projectCode, setProjectCode] = useState('');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [viewMode, setViewMode] = useState<'table' | 'tree'>('table');
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  // Baseline modal
  const [showBaselineModal, setShowBaselineModal] = useState(false);
  const [baselineName, setBaselineName] = useState('');
  const [baselineDesc, setBaselineDesc] = useState('');
  const [creatingBaseline, setCreatingBaseline] = useState(false);
  const [baselineMsg, setBaselineMsg] = useState('');

  // Load project on mount
  useEffect(() => {
    projectsAPI.list().then((res) => {
      if (res.data.length > 0) {
        setProjectId(res.data[0].id);
        setProjectCode(res.data[0].code);
      }
    }).catch(() => setError('Failed to load projects'));
  }, []);

  // Fetch requirements
  const fetchRequirements = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError('');
    try {
      const params: any = { limit: 200 };
      if (statusFilter !== 'all') params.status = statusFilter;
      if (typeFilter !== 'all') params.req_type = typeFilter;
      if (search) params.search = search;
      const res = await requirementsAPI.list(projectId, params);
      setRequirements(res.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load requirements');
    } finally {
      setLoading(false);
    }
  }, [projectId, statusFilter, typeFilter, search]);

  useEffect(() => { fetchRequirements(); }, [fetchRequirements]);

  // Debounced search
  const [searchInput, setSearchInput] = useState('');
  useEffect(() => {
    const timer = setTimeout(() => setSearch(searchInput), 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Build tree
  const tree = useMemo(() => buildTree(requirements), [requirements]);

  // Tree expand/collapse
  const toggleNode = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const expandAll = () => {
    setExpanded(new Set(requirements.filter(r => {
      return requirements.some(c => c.parent_id === r.id);
    }).map(r => r.id)));
  };

  const collapseAll = () => setExpanded(new Set());

  const handleCreateBaseline = async () => {
    if (!baselineName.trim() || !projectId) return;
    setCreatingBaseline(true); setBaselineMsg('');
    try {
      await baselinesAPI.create({ name: baselineName.trim(), description: baselineDesc.trim() || undefined, project_id: projectId });
      setBaselineMsg(`Baseline "${baselineName}" created with ${requirements.length} requirements`);
      setBaselineName(''); setBaselineDesc('');
      setTimeout(() => { setShowBaselineModal(false); setBaselineMsg(''); }, 2000);
    } catch (e: any) { setBaselineMsg(e.response?.data?.detail || 'Failed to create baseline'); }
    finally { setCreatingBaseline(false); }
  };

  const stats = {
    total: requirements.length,
    avgQuality: requirements.length > 0
      ? Math.round(requirements.reduce((a, r) => a + (r.quality_score || 0), 0) / requirements.length)
      : 0,
  };

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Requirements Management</h1>
          <p className="mt-1 text-sm text-slate-500">{projectCode} · ASTRA Systems Engineering Platform</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={fetchRequirements} className="rounded-full border border-astra-border p-2 text-slate-400 transition hover:text-slate-200">
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="mb-6 grid grid-cols-2 gap-4 xl:grid-cols-4">
        <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
          <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">Total</div>
          <div className="mt-1 text-2xl font-bold text-slate-100">{stats.total}</div>
        </div>
        <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
          <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">Avg Quality</div>
          <div className="mt-1 text-2xl font-bold text-emerald-400">{stats.avgQuality}</div>
        </div>
        <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
          <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">By Status</div>
          <div className="mt-1 flex gap-1.5 flex-wrap">
            {Object.entries(
              requirements.reduce((acc, r) => {
                const s = r.status as string;
                acc[s] = (acc[s] || 0) + 1;
                return acc;
              }, {} as Record<string, number>)
            ).map(([s, count]) => (
              <span key={s} className="rounded-full px-2 py-0.5 text-[10px] font-bold"
                style={{ background: STATUS_COLORS[s as RequirementStatus]?.bg, color: STATUS_COLORS[s as RequirementStatus]?.text }}>
                {count}
              </span>
            ))}
          </div>
        </div>
        <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
          <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">Types</div>
          <div className="mt-1 text-2xl font-bold text-blue-400">
            {new Set(requirements.map((r) => r.req_type)).size}
          </div>
        </div>
      </div>

      {/* Toolbar */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        {/* View toggle */}
        <div className="flex rounded-lg border border-astra-border overflow-hidden">
          <button onClick={() => setViewMode('table')}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold transition ${
              viewMode === 'table' ? 'bg-blue-500 text-white' : 'bg-astra-surface text-slate-400 hover:text-slate-200'
            }`}>
            <List className="h-3.5 w-3.5" /> Table
          </button>
          <button onClick={() => setViewMode('tree')}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold transition ${
              viewMode === 'tree' ? 'bg-blue-500 text-white' : 'bg-astra-surface text-slate-400 hover:text-slate-200'
            }`}>
            <GitBranch className="h-3.5 w-3.5" /> Tree
          </button>
        </div>

        <div className="flex flex-1 items-center gap-2 rounded-lg border border-astra-border bg-astra-surface px-3 py-2" style={{ maxWidth: 320 }}>
          <Search className="h-4 w-4 text-slate-500" />
          <input value={searchInput} onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search by ID, title, or statement..."
            className="flex-1 border-0 bg-transparent text-[13px] text-slate-200 outline-none placeholder:text-slate-600" />
        </div>

        {/* Status filter */}
        <div className="flex gap-1">
          {['all', 'draft', 'under_review', 'approved', 'baselined'].map((f) => (
            <button key={f} onClick={() => setStatusFilter(f)}
              className={`rounded-full px-3.5 py-1.5 text-xs font-semibold transition-all ${
                statusFilter === f
                  ? 'bg-blue-500 text-white'
                  : 'border border-astra-border bg-transparent text-slate-400 hover:border-blue-500/30 hover:text-slate-200'
              }`}>
              {f === 'all' ? 'All' : STATUS_LABELS[f as RequirementStatus] || f}
            </button>
          ))}
        </div>

        {/* Type filter */}
        <div className="relative">
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}
            className="appearance-none rounded-lg border border-astra-border bg-astra-surface px-3 py-1.5 pr-7 text-xs font-semibold text-slate-400 outline-none transition hover:border-blue-500/30">
            <option value="all">All Types</option>
            <option value="functional">Functional</option>
            <option value="performance">Performance</option>
            <option value="security">Security</option>
            <option value="interface">Interface</option>
            <option value="environmental">Environmental</option>
            <option value="safety">Safety</option>
            <option value="reliability">Reliability</option>
            <option value="constraint">Constraint</option>
          </select>
          <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-3 w-3 -translate-y-1/2 text-slate-500" />
        </div>

        <button onClick={() => setShowBaselineModal(true)}
          className="ml-auto flex items-center gap-1.5 rounded-lg border border-emerald-500/30 px-4 py-2 text-[13px] font-semibold text-emerald-400 transition hover:bg-emerald-500/10">
          <Archive className="h-4 w-4" /> Baseline
        </button>

        <Link href="/requirements/new"
          className="flex items-center gap-1.5 rounded-lg bg-blue-500 px-4 py-2 text-[13px] font-semibold text-white transition hover:bg-blue-600">
          <Plus className="h-4 w-4" /> New Requirement
        </Link>
      </div>

      {/* Baseline Modal */}
      {showBaselineModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => !creatingBaseline && setShowBaselineModal(false)}>
          <div className="w-full max-w-md rounded-xl border border-astra-border bg-astra-surface p-6 shadow-2xl" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-bold text-slate-100 mb-1">Create Baseline Snapshot</h3>
            <p className="text-xs text-slate-500 mb-4">Freezes the current state of all {requirements.length} requirements for milestone review.</p>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">Baseline Name</label>
                <input value={baselineName} onChange={e => setBaselineName(e.target.value)}
                  placeholder="e.g., PDR Baseline v1.0" autoFocus
                  className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2.5 text-sm text-slate-200 outline-none placeholder:text-slate-600 focus:border-blue-500/50" />
              </div>
              <div>
                <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">Description (optional)</label>
                <textarea value={baselineDesc} onChange={e => setBaselineDesc(e.target.value)}
                  placeholder="Notes about this baseline..." rows={2}
                  className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2.5 text-sm text-slate-200 outline-none placeholder:text-slate-600 focus:border-blue-500/50 resize-none" />
              </div>
              {baselineMsg && (
                <div className={`rounded-lg px-3 py-2 text-xs ${baselineMsg.includes('created') ? 'border border-emerald-500/20 bg-emerald-500/10 text-emerald-400' : 'border border-red-500/20 bg-red-500/10 text-red-400'}`}>
                  {baselineMsg}
                </div>
              )}
              <div className="flex gap-2 justify-end pt-1">
                <button onClick={() => setShowBaselineModal(false)} disabled={creatingBaseline}
                  className="rounded-lg border border-astra-border px-4 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200">Cancel</button>
                <button onClick={handleCreateBaseline} disabled={!baselineName.trim() || creatingBaseline}
                  className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-600 disabled:opacity-40">
                  {creatingBaseline ? <Loader2 className="h-3 w-3 animate-spin" /> : <Archive className="h-3 w-3" />}
                  {creatingBaseline ? 'Creating...' : `Snapshot ${requirements.length} Reqs`}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* ── Tree View ── */}
      {viewMode === 'tree' && !loading && requirements.length > 0 && (
        <>
          <LevelSummary requirements={requirements} />

          {/* Expand/Collapse controls */}
          <div className="mb-3 flex items-center gap-2">
            <button onClick={expandAll}
              className="rounded-lg border border-astra-border px-3 py-1.5 text-[11px] font-semibold text-slate-400 transition hover:text-slate-200">
              Expand All
            </button>
            <button onClick={collapseAll}
              className="rounded-lg border border-astra-border px-3 py-1.5 text-[11px] font-semibold text-slate-400 transition hover:text-slate-200">
              Collapse All
            </button>
            <span className="ml-2 text-[11px] text-slate-500">
              {tree.length} root{tree.length !== 1 ? 's' : ''} ·{' '}
              {requirements.filter(r => requirements.some(c => c.parent_id === r.id)).length} with children
            </span>
          </div>

          <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
            {tree.length === 0 ? (
              <div className="py-12 text-center text-sm text-slate-500">No hierarchy — all requirements are unlinked</div>
            ) : (
              tree.map((node) => (
                <TreeNodeRow
                  key={node.requirement.id}
                  node={node}
                  depth={0}
                  expanded={expanded}
                  onToggle={toggleNode}
                  onNavigate={(id) => router.push(`/requirements/${id}`)}
                />
              ))
            )}
          </div>
        </>
      )}

      {/* ── Table View ── */}
      {viewMode === 'table' && (
        <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
          <div className="grid grid-cols-[110px_40px_1fr_110px_100px_80px_65px] border-b border-astra-border bg-astra-surface-alt px-4 py-2.5 text-[10px] font-bold uppercase tracking-wider text-slate-500">
            <span>ID</span><span>Lvl</span><span>Requirement</span><span>Status</span><span>Type</span><span>Priority</span><span>Quality</span>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
            </div>
          ) : requirements.length === 0 ? (
            <div className="py-16 text-center">
              <div className="text-sm text-slate-500">No requirements found</div>
              <p className="mt-1 text-xs text-slate-600">
                {search || statusFilter !== 'all' || typeFilter !== 'all'
                  ? 'Try adjusting your filters'
                  : 'Create your first requirement to get started'}
              </p>
            </div>
          ) : (
            requirements.map((req) => {
              const sc = STATUS_COLORS[req.status as RequirementStatus];
              const lvl = (req.level || 'L1') as RequirementLevel;
              return (
                <div key={req.id}
                  onClick={() => router.push(`/requirements/${req.id}`)}
                  className="grid grid-cols-[110px_40px_1fr_110px_100px_80px_65px] items-center border-b border-astra-border px-4 py-3 transition-colors last:border-0 hover:bg-astra-surface-hover cursor-pointer">
                  <span className="font-mono text-xs font-semibold text-blue-400">{req.req_id}</span>
                  <LevelBadge level={req.level} />
                  <div className="min-w-0 pr-4">
                    <div className="truncate text-[13px] font-medium text-slate-200">{req.title}</div>
                    <div className="mt-0.5 truncate text-[11px] text-slate-500">{req.statement}</div>
                  </div>
                  <span className="inline-flex w-fit rounded-full px-2.5 py-0.5 text-[11px] font-semibold"
                    style={{ background: sc?.bg, color: sc?.text }}>
                    {STATUS_LABELS[req.status as RequirementStatus] || req.status}
                  </span>
                  <TypeBadge type={req.req_type} />
                  <PriorityIndicator priority={req.priority} />
                  <QualityDot score={req.quality_score} />
                </div>
              );
            })
          )}
        </div>
      )}

      {/* Loading state for tree view */}
      {viewMode === 'tree' && loading && (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
        </div>
      )}

      {/* Count footer */}
      {!loading && requirements.length > 0 && (
        <div className="mt-3 text-right text-[11px] text-slate-500">
          Showing {requirements.length} requirement{requirements.length !== 1 ? 's' : ''}
          {viewMode === 'tree' && ` · ${tree.length} root nodes`}
        </div>
      )}
    </div>
  );
}
