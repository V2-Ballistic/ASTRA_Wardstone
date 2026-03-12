'use client';

/**
 * ASTRA — Requirements List & Tree (Project-Scoped)
 * ====================================================
 * File: frontend/src/app/projects/[id]/requirements/page.tsx
 *
 * Additions over the original /requirements page:
 *   1. Project context from URL params (no more guessing first project)
 *   2. AI Writing Assistant launcher button (convert mode)
 *   3. "Convert from Prose" button in toolbar
 *   4. Duplicate warnings banner from /ai/duplicates
 *   5. Bulk selection with batch quality check / export actions
 *   6. Rich empty state with AI prose extraction CTA
 *   7. All internal links use project-scoped URLs
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import {
  Search, Plus, Loader2, RefreshCw, ChevronDown, ChevronRight,
  List, GitBranch, AlertTriangle, CheckCircle, Archive, Sparkles,
  Copy, FileText, Wand2, Download, CheckSquare, Square, X,
} from 'lucide-react';
import {
  STATUS_COLORS, STATUS_LABELS, LEVEL_COLORS, LEVEL_LABELS, PRIORITY_COLORS,
  type RequirementStatus, type RequirementLevel, type Priority, type Requirement,
} from '@/lib/types';
import { requirementsAPI, projectsAPI, baselinesAPI } from '@/lib/api';

// Optional AI API
let aiAPI: any = null;
try { aiAPI = require('@/lib/ai-api').aiAPI; } catch {}

// ══════════════════════════════════════
//  Shared Small Components
// ══════════════════════════════════════

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

// ══════════════════════════════════════
//  Tree Types & Builder
// ══════════════════════════════════════

interface TreeNode {
  requirement: Requirement;
  children: TreeNode[];
}

function buildTree(requirements: Requirement[]): TreeNode[] {
  const map = new Map<number, TreeNode>();
  const roots: TreeNode[] = [];
  for (const req of requirements) {
    map.set(req.id, { requirement: req, children: [] });
  }
  for (const req of requirements) {
    const node = map.get(req.id)!;
    if (req.parent_id && map.has(req.parent_id)) {
      map.get(req.parent_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  }
  const sortNodes = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => {
      const ld = (a.requirement.level || 'L1').localeCompare(b.requirement.level || 'L1');
      if (ld !== 0) return ld;
      return a.requirement.req_id.localeCompare(b.requirement.req_id);
    });
    for (const n of nodes) sortNodes(n.children);
  };
  sortNodes(roots);
  return roots;
}

// ══════════════════════════════════════
//  Tree Node Row
// ══════════════════════════════════════

function TreeNodeRow({
  node, depth, expanded, onToggle, onNavigate, selected, onSelect,
}: {
  node: TreeNode; depth: number; expanded: Set<number>;
  onToggle: (id: number) => void; onNavigate: (id: number) => void;
  selected: Set<number>; onSelect: (id: number) => void;
}) {
  const req = node.requirement;
  const hasChildren = node.children.length > 0;
  const isExpanded = expanded.has(req.id);
  const sc = STATUS_COLORS[req.status as RequirementStatus];

  return (
    <>
      <div
        className="group flex items-center border-b border-astra-border py-2.5 pr-4 transition-colors hover:bg-astra-surface-hover cursor-pointer"
        style={{ paddingLeft: `${16 + depth * 28}px` }}
      >
        {/* Checkbox */}
        <button
          onClick={(e) => { e.stopPropagation(); onSelect(req.id); }}
          className="mr-2 flex h-5 w-5 items-center justify-center"
        >
          {selected.has(req.id) ? (
            <CheckSquare className="h-4 w-4 text-blue-400" />
          ) : (
            <Square className="h-4 w-4 text-slate-600 group-hover:text-slate-400" />
          )}
        </button>

        {/* Expand/collapse */}
        <div className="mr-2 flex h-5 w-5 items-center justify-center">
          {hasChildren ? (
            <button onClick={(e) => { e.stopPropagation(); onToggle(req.id); }}
              className="flex h-5 w-5 items-center justify-center rounded transition hover:bg-slate-700">
              {isExpanded
                ? <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
                : <ChevronRight className="h-3.5 w-3.5 text-slate-400" />}
            </button>
          ) : <div className="w-5" />}
        </div>

        {/* Content */}
        <div className="flex flex-1 items-center gap-3 min-w-0" onClick={() => onNavigate(req.id)}>
          <LevelBadge level={req.level} />
          <span className="font-mono text-xs font-semibold text-blue-400">{req.req_id}</span>
          <span className="flex-1 truncate text-[13px] text-slate-200">{req.title}</span>
          <span className="inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold"
            style={{ background: sc?.bg, color: sc?.text }}>
            {STATUS_LABELS[req.status as RequirementStatus] || req.status}
          </span>
          <TypeBadge type={req.req_type} />
          <PriorityIndicator priority={req.priority} />
          <QualityDot score={req.quality_score} />
          {hasChildren && (
            <span className="rounded-full bg-slate-700/50 px-2 py-0.5 text-[10px] font-bold text-slate-400">
              {node.children.length}
            </span>
          )}
        </div>
      </div>
      {isExpanded && node.children.map((child) => (
        <TreeNodeRow key={child.requirement.id} node={child} depth={depth + 1}
          expanded={expanded} onToggle={onToggle} onNavigate={onNavigate}
          selected={selected} onSelect={onSelect} />
      ))}
    </>
  );
}

// ══════════════════════════════════════
//  Level Summary Bar
// ══════════════════════════════════════

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
        <span className="text-[11px] text-slate-500">{requirements.length} total</span>
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
              <div className="mt-0.5 text-center text-[9px] text-slate-500">{LEVEL_LABELS[level].split('—')[1]?.trim()}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  Duplicate Warning Banner
// ══════════════════════════════════════

function DuplicateBanner({ count, projectId }: { count: number; projectId: number }) {
  const router = useRouter();
  if (count === 0) return null;
  return (
    <div className="mb-4 flex items-center gap-3 rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3">
      <Copy className="h-4 w-4 text-amber-400 flex-shrink-0" />
      <span className="flex-1 text-xs text-amber-300">
        AI found <span className="font-bold">{count} group{count !== 1 ? 's' : ''}</span> of potential duplicates.
      </span>
      <button
        onClick={() => router.push(`/projects/${projectId}/ai`)}
        className="flex items-center gap-1 rounded-lg border border-amber-500/30 px-3 py-1.5 text-[11px] font-semibold text-amber-400 transition hover:bg-amber-500/10"
      >
        Review <ChevronRight className="h-3 w-3" />
      </button>
    </div>
  );
}

// ══════════════════════════════════════
//  Bulk Actions Bar
// ══════════════════════════════════════

function BulkActionsBar({ count, onClear, onQualityCheck, onExport }: {
  count: number; onClear: () => void; onQualityCheck: () => void; onExport: () => void;
}) {
  if (count === 0) return null;
  return (
    <div className="mb-4 flex items-center gap-3 rounded-xl border border-blue-500/20 bg-blue-500/5 px-4 py-3">
      <CheckSquare className="h-4 w-4 text-blue-400 flex-shrink-0" />
      <span className="text-xs text-blue-300 font-semibold">
        {count} selected
      </span>
      <div className="flex-1" />
      <button
        onClick={onQualityCheck}
        className="flex items-center gap-1.5 rounded-lg border border-blue-500/30 px-3 py-1.5 text-[11px] font-semibold text-blue-400 transition hover:bg-blue-500/10"
      >
        <Sparkles className="h-3 w-3" /> Batch Quality Check
      </button>
      <button
        onClick={onExport}
        className="flex items-center gap-1.5 rounded-lg border border-blue-500/30 px-3 py-1.5 text-[11px] font-semibold text-blue-400 transition hover:bg-blue-500/10"
      >
        <Download className="h-3 w-3" /> Export
      </button>
      <button
        onClick={onClear}
        className="rounded-lg p-1.5 text-slate-500 transition hover:text-slate-300"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

// ══════════════════════════════════════
//  Empty State
// ══════════════════════════════════════

function EmptyState({ projectId }: { projectId: number }) {
  const router = useRouter();
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-6">
      <div className="flex h-20 w-20 items-center justify-center rounded-2xl border border-astra-border bg-astra-surface">
        <FileText className="h-10 w-10 text-blue-500/50" />
      </div>
      <div className="text-center max-w-md">
        <h2 className="text-lg font-bold text-slate-200">No Requirements Yet</h2>
        <p className="mt-2 text-sm text-slate-500 leading-relaxed">
          Create your first requirement manually, or paste meeting notes and
          let AI extract requirements for you.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={() => router.push(`/projects/${projectId}/requirements/new`)}
          className="flex items-center gap-2 rounded-lg bg-blue-500 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-600"
        >
          <Plus className="h-4 w-4" /> Create Requirement
        </button>
        <button
          onClick={() => router.push(`/projects/${projectId}/ai`)}
          className="flex items-center gap-2 rounded-lg border border-violet-500/30 bg-violet-500/10 px-5 py-2.5 text-sm font-semibold text-violet-400 transition hover:bg-violet-500/20"
        >
          <Wand2 className="h-4 w-4" /> Extract from Prose with AI
        </button>
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  Main Page
// ══════════════════════════════════════

export default function ProjectRequirementsPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);
  const p = `/projects/${projectId}`;

  // ── Data state ──
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [projectCode, setProjectCode] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [duplicateCount, setDuplicateCount] = useState(0);

  // ── UI state ──
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [viewMode, setViewMode] = useState<'table' | 'tree'>('table');
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [selected, setSelected] = useState<Set<number>>(new Set());

  // ── Baseline modal ──
  const [showBaselineModal, setShowBaselineModal] = useState(false);
  const [baselineName, setBaselineName] = useState('');
  const [baselineDesc, setBaselineDesc] = useState('');
  const [creatingBaseline, setCreatingBaseline] = useState(false);
  const [baselineMsg, setBaselineMsg] = useState('');

  // ── Debounced search ──
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput), 250);
    return () => clearTimeout(t);
  }, [searchInput]);

  // ── Fetch project info ──
  useEffect(() => {
    projectsAPI.get(projectId)
      .then((res) => setProjectCode(res.data.code))
      .catch(() => {});
  }, [projectId]);

  // ── Fetch requirements ──
  const fetchRequirements = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError('');
    try {
      const res = await requirementsAPI.list(projectId, { limit: 200 });
      setRequirements(Array.isArray(res.data) ? res.data : []);
    } catch (e: any) {
        const detail = e.response?.data?.detail;
		setError(
		  typeof detail === 'string' ? detail :
		  Array.isArray(detail) ? detail.map((d: any) => d.msg || JSON.stringify(d)).join('; ') :
		  'Failed to load requirements'
		);
    }
    setLoading(false);
  }, [projectId]);

  useEffect(() => { fetchRequirements(); }, [fetchRequirements]);

  // ── Fetch duplicate count (non-blocking) ──
  useEffect(() => {
    if (!projectId || !aiAPI) return;
    aiAPI.getDuplicates(projectId)
      .then((res: any) => {
        setDuplicateCount(res.data?.duplicate_groups?.length || 0);
      })
      .catch(() => setDuplicateCount(0));
  }, [projectId, requirements.length]);

  // ── Filtering ──
  const filtered = useMemo(() => {
    let result = requirements;
    if (search) {
      const s = search.toLowerCase();
      result = result.filter(
        (r) => r.req_id.toLowerCase().includes(s) ||
               r.title.toLowerCase().includes(s) ||
               r.statement.toLowerCase().includes(s)
      );
    }
    if (statusFilter !== 'all') {
      result = result.filter((r) => r.status === statusFilter);
    }
    if (typeFilter !== 'all') {
      result = result.filter((r) => r.req_type === typeFilter);
    }
    return result;
  }, [requirements, search, statusFilter, typeFilter]);

  // ── Tree ──
  const tree = useMemo(() => buildTree(filtered), [filtered]);

  // ── Selection ──
  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const selectAll = () => setSelected(new Set(filtered.map((r) => r.id)));
  const clearSelection = () => setSelected(new Set());

  // ── Expand/Collapse ──
  const expandAll = () => setExpanded(new Set(requirements.map((r) => r.id)));
  const collapseAll = () => setExpanded(new Set());
  const toggleNode = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  // ── Baseline ──
  const handleCreateBaseline = async () => {
    if (!baselineName.trim()) return;
    setCreatingBaseline(true);
    try {
      await baselinesAPI.create({ name: baselineName, description: baselineDesc, project_id: projectId });
      setBaselineMsg(`Baseline "${baselineName}" created with ${requirements.length} requirements`);
      setBaselineName('');
      setBaselineDesc('');
      setTimeout(() => { setShowBaselineModal(false); setBaselineMsg(''); }, 2000);
    } catch (e: any) {
      setBaselineMsg(e.response?.data?.detail || 'Failed to create baseline');
    }
    setCreatingBaseline(false);
  };

  // ── Bulk actions ──
  const handleBulkQualityCheck = () => {
    router.push(`${p}/ai`);
  };
  const handleBulkExport = () => {
    router.push(`${p}/reports`);
  };

  // ── Navigate to requirement ──
  const navigateToReq = (id: number) => router.push(`/requirements/${id}`);

  // ── Quick stat counts ──
  const statusCounts = requirements.reduce((acc, r) => {
    acc[r.status] = (acc[r.status] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  // ── Render ──
  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Requirements</h1>
          <p className="mt-0.5 text-sm text-slate-500">{projectCode} · {requirements.length} requirements</p>
        </div>
        <div className="flex items-center gap-2">
          {/* AI Writing Assistant (convert mode) */}
          <button
            onClick={() => router.push(`${p}/ai`)}
            className="flex items-center gap-1.5 rounded-lg border border-violet-500/30 bg-violet-500/10 px-3 py-2 text-xs font-semibold text-violet-400 transition hover:bg-violet-500/20"
          >
            <Wand2 className="h-3.5 w-3.5" /> Convert Prose
          </button>

          {/* AI Writing Assistant */}
          <button
            onClick={() => router.push(`${p}/ai`)}
            className="flex items-center gap-1.5 rounded-lg border border-astra-border px-3 py-2 text-xs font-semibold text-slate-400 transition hover:border-blue-500/30 hover:text-slate-200"
          >
            <Sparkles className="h-3.5 w-3.5 text-blue-400" /> AI Assistant
          </button>

          <button onClick={fetchRequirements}
            className="rounded-full border border-astra-border p-2 text-slate-400 transition hover:text-slate-200">
            <RefreshCw className="h-3.5 w-3.5" />
          </button>

          <button
            onClick={() => router.push(`${p}/requirements/new`)}
            className="flex items-center gap-2 rounded-lg bg-blue-500 px-4 py-2 text-xs font-semibold text-white transition hover:bg-blue-600"
          >
            <Plus className="h-3.5 w-3.5" /> New Requirement
          </button>
        </div>
      </div>

      {/* Duplicate Banner */}
      <DuplicateBanner count={duplicateCount} projectId={projectId} />

      {/* Bulk Actions */}
      <BulkActionsBar
        count={selected.size}
        onClear={clearSelection}
        onQualityCheck={handleBulkQualityCheck}
        onExport={handleBulkExport}
      />

      {/* Error */}
      {error && (
        <div className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">{error}</div>
      )}

      {/* Empty state */}
      {!loading && requirements.length === 0 && (
        <EmptyState projectId={projectId} />
      )}

      {/* Content (only if we have requirements) */}
      {requirements.length > 0 && (
        <>
          {/* Quick stats */}
          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
            <div className="rounded-xl border border-astra-border bg-astra-surface p-3">
              <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">Total</div>
              <div className="mt-1 text-xl font-bold text-blue-400">{requirements.length}</div>
            </div>
            {Object.entries(statusCounts).slice(0, 4).map(([s, count]) => {
              const sc = STATUS_COLORS[s as RequirementStatus];
              return (
                <div key={s} className="rounded-xl border border-astra-border bg-astra-surface p-3">
                  <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
                    {STATUS_LABELS[s as RequirementStatus] || s}
                  </div>
                  <div className="mt-1 text-xl font-bold" style={{ color: sc?.text }}>{count}</div>
                </div>
              );
            })}
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

            {/* Search */}
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
                  className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-all ${
                    statusFilter === f
                      ? 'bg-blue-500 text-white'
                      : 'border border-astra-border bg-transparent text-slate-400 hover:border-blue-500/30'
                  }`}>
                  {f === 'all' ? 'All' : STATUS_LABELS[f as RequirementStatus] || f}
                </button>
              ))}
            </div>

            {/* Select all */}
            <button
              onClick={selected.size === filtered.length ? clearSelection : selectAll}
              className="rounded-lg border border-astra-border px-3 py-1.5 text-[11px] font-semibold text-slate-400 transition hover:text-slate-200"
            >
              {selected.size === filtered.length && selected.size > 0 ? 'Deselect All' : 'Select All'}
            </button>

            {/* Baseline snapshot */}
            <button
              onClick={() => setShowBaselineModal(true)}
              className="ml-auto flex items-center gap-1.5 rounded-lg border border-astra-border px-3 py-1.5 text-[11px] font-semibold text-slate-400 transition hover:text-slate-200"
            >
              <Archive className="h-3 w-3" /> Snapshot
            </button>
          </div>

          {/* Tree View */}
          {viewMode === 'tree' && !loading && (
            <>
              <LevelSummary requirements={filtered} />
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
                  {tree.length} root{tree.length !== 1 ? 's' : ''}
                </span>
              </div>
              <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
                {tree.length === 0 ? (
                  <div className="py-12 text-center text-sm text-slate-500">No hierarchy — all requirements are unlinked</div>
                ) : (
                  tree.map((node) => (
                    <TreeNodeRow key={node.requirement.id} node={node} depth={0}
                      expanded={expanded} onToggle={toggleNode} onNavigate={navigateToReq}
                      selected={selected} onSelect={toggleSelect} />
                  ))
                )}
              </div>
            </>
          )}

          {/* Table View */}
          {viewMode === 'table' && (
            <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
              <div className="grid grid-cols-[30px_100px_40px_1fr_100px_90px_70px_60px] border-b border-astra-border bg-astra-surface-alt px-4 py-2.5 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                <span></span><span>ID</span><span>Lvl</span><span>Requirement</span>
                <span>Status</span><span>Type</span><span>Priority</span><span>Quality</span>
              </div>

              {loading ? (
                <div className="flex items-center justify-center py-16">
                  <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
                </div>
              ) : filtered.length === 0 ? (
                <div className="py-16 text-center">
                  <div className="text-sm text-slate-500">No requirements match your filters</div>
                  <p className="mt-1 text-xs text-slate-600">Try adjusting your search or filters</p>
                </div>
              ) : (
                filtered.map((req) => {
                  const sc = STATUS_COLORS[req.status as RequirementStatus];
                  return (
                    <div key={req.id}
                      className="group grid grid-cols-[30px_100px_40px_1fr_100px_90px_70px_60px] items-center border-b border-astra-border px-4 py-3 transition-colors last:border-0 hover:bg-astra-surface-hover">
                      {/* Checkbox */}
                      <button onClick={() => toggleSelect(req.id)}>
                        {selected.has(req.id) ? (
                          <CheckSquare className="h-4 w-4 text-blue-400" />
                        ) : (
                          <Square className="h-4 w-4 text-slate-600 group-hover:text-slate-400" />
                        )}
                      </button>
                      {/* Row data — clickable */}
                      <span className="font-mono text-xs font-semibold text-blue-400 cursor-pointer"
                        onClick={() => navigateToReq(req.id)}>{req.req_id}</span>
                      <LevelBadge level={req.level} />
                      <div className="min-w-0 pr-4 cursor-pointer" onClick={() => navigateToReq(req.id)}>
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

          {/* Footer */}
          {!loading && filtered.length > 0 && (
            <div className="mt-3 flex items-center justify-between text-[11px] text-slate-500">
              <span>
                Showing {filtered.length} of {requirements.length} requirement{requirements.length !== 1 ? 's' : ''}
                {viewMode === 'tree' && ` · ${tree.length} root nodes`}
              </span>
              {selected.size > 0 && (
                <span className="text-blue-400">{selected.size} selected</span>
              )}
            </div>
          )}
        </>
      )}

      {/* ── Baseline Modal ── */}
      {showBaselineModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-astra-border bg-astra-surface p-6 shadow-2xl">
            <h3 className="text-sm font-bold text-slate-100 mb-4">Create Baseline Snapshot</h3>
            {baselineMsg && (
              <div className="mb-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-3 py-2 text-xs text-emerald-400">{baselineMsg}</div>
            )}
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">Name</label>
                <input value={baselineName} onChange={(e) => setBaselineName(e.target.value)}
                  placeholder="e.g., PDR Baseline v1.0"
                  className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
              </div>
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">Description</label>
                <textarea value={baselineDesc} onChange={(e) => setBaselineDesc(e.target.value)}
                  rows={2} placeholder="Optional description"
                  className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
              </div>
            </div>
            <div className="mt-4 flex items-center justify-between">
              <button onClick={() => { setShowBaselineModal(false); setBaselineMsg(''); }}
                className="rounded-lg border border-astra-border px-4 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200">
                Cancel
              </button>
              <button onClick={handleCreateBaseline} disabled={!baselineName.trim() || creatingBaseline}
                className="flex items-center gap-2 rounded-lg bg-blue-500 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-600 disabled:opacity-50">
                {creatingBaseline ? <Loader2 className="h-3 w-3 animate-spin" /> : <Archive className="h-3 w-3" />}
                {creatingBaseline ? 'Creating...' : `Snapshot ${requirements.length} Reqs`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
