'use client';

/**
 * ASTRA — Auto-Requirement Review Dashboard (Full Rewrite)
 * ============================================================
 * File: frontend/src/app/projects/[id]/interfaces/auto-requirements/page.tsx
 *
 * Real approval flow via backend endpoints:
 *   POST /interfaces/auto-requirements/approve { requirement_ids }
 *   POST /interfaces/auto-requirements/reject  { requirement_ids, reason }
 *
 * Features:
 *   - Approve: req → draft, link → approved, auto-creates trace links
 *   - Reject: req → deleted (soft), link → rejected
 *   - Edit & Approve: inline edit statement/title/rationale, then approve
 *   - Bulk select/approve/reject
 *   - Grouped view by source/level/status
 *   - Filter by status, source type, level
 *   - Summary bar with counts
 *
 * API calls:
 *   requirementsAPI.list(projectId, { req_type, limit })
 *   requirementsAPI.update(reqId, data)
 *   interfaceAPI.listReqLinks({ requirement_id })
 *   interfaceAPI.getCoverage(projectId)
 *   api.post('/interfaces/auto-requirements/approve', { requirement_ids })
 *   api.post('/interfaces/auto-requirements/reject', { requirement_ids, reason })
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  Loader2, RefreshCw, ArrowLeft, Check, X, AlertTriangle,
  CheckSquare, Square, ChevronRight, ChevronDown,
  Cable, Zap, Radio, Shield, Thermometer, Cpu, Sparkles,
  Eye, Edit3, Save, CheckCircle, Trash2,
} from 'lucide-react';
import clsx from 'clsx';
import api, { projectsAPI, requirementsAPI } from '@/lib/api';
import { interfaceAPI } from '@/lib/interface-api';
import type { InterfaceRequirementLink, InterfaceCoverageResponse } from '@/lib/interface-types';
import { formatApiError } from '@/lib/errors';

// ══════════════════════════════════════
//  Types
// ══════════════════════════════════════

interface AutoReq {
  link: InterfaceRequirementLink;
  req: {
    id: number; req_id: string; title: string; statement: string;
    rationale?: string; level: string; priority: string; status: string;
    quality_score: number;
  };
}

type GroupBy = 'source' | 'level' | 'status' | 'none';
type FilterStatus = 'all' | 'pending_review' | 'approved' | 'rejected';

// ══════════════════════════════════════
//  Shared UI
// ══════════════════════════════════════

const SOURCE_ICONS: Record<string, any> = {
  bus_connection: Cable, message_definition: Radio, message_field: Radio,
  power_wire: Zap, ground_wire: Shield, discrete_signal: Zap,
  rf_connection: Radio, shield_grounding: Shield,
  harness_overall: Cable, environmental_spec: Thermometer,
  emi_spec: Radio, unit_import: Cpu,
};

const SOURCE_LABELS: Record<string, string> = {
  bus_connection: 'Bus Connection', message_definition: 'Message',
  message_field: 'Message Field', power_wire: 'Power Wire',
  ground_wire: 'Ground Wire', discrete_signal: 'Discrete Signal',
  rf_connection: 'RF Connection', shield_grounding: 'Shield Grounding',
  harness_overall: 'Harness Overall', environmental_spec: 'Environmental',
  emi_spec: 'EMI/EMC', unit_import: 'Unit Import', env_parent: 'Env Parent',
};

const LEVEL_COLORS: Record<string, string> = {
  L0: '#DC2626', L1: '#EF4444', L2: '#F59E0B', L3: '#3B82F6', L4: '#8B5CF6', L5: '#6B7280',
};

function LevelBadge({ level }: { level: string }) {
  const c = LEVEL_COLORS[level] || '#6B7280';
  return <span className="rounded-full px-1.5 py-0.5 text-[9px] font-bold" style={{ background: `${c}20`, color: c }}>{level}</span>;
}

function QDot({ score }: { score: number }) {
  const color = score >= 85 ? '#10B981' : score >= 70 ? '#F59E0B' : '#EF4444';
  return <span className="font-mono text-[10px] font-bold" style={{ color }}>{score.toFixed(0)}</span>;
}

const STATUS_STYLES: Record<string, { bg: string; text: string }> = {
  pending_review: { bg: 'rgba(245,158,11,0.15)', text: '#F59E0B' },
  approved:       { bg: 'rgba(16,185,129,0.15)', text: '#10B981' },
  rejected:       { bg: 'rgba(239,68,68,0.15)',  text: '#EF4444' },
  draft:          { bg: 'rgba(100,116,139,0.15)', text: '#94A3B8' },
};

function StatusPill({ status }: { status: string }) {
  const s = STATUS_STYLES[status] || STATUS_STYLES.draft;
  return <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize" style={{ background: s.bg, color: s.text }}>{status.replace(/_/g, ' ')}</span>;
}

// ══════════════════════════════════════
//  Edit & Approve Inline Form
// ══════════════════════════════════════

function EditApproveForm({ ar, onSaved, onCancel }: {
  ar: AutoReq; onSaved: () => void; onCancel: () => void;
}) {
  const [title, setTitle]       = useState(ar.req.title);
  const [statement, setStatement] = useState(ar.req.statement);
  const [rationale, setRationale] = useState(ar.req.rationale || '');
  const [saving, setSaving]     = useState(false);
  const [error, setError]       = useState('');

  const handleSaveApprove = async () => {
    if (!statement.trim()) { setError('Statement is required'); return; }
    setSaving(true); setError('');
    try {
      // 1. Update the requirement with edits
      await requirementsAPI.update(ar.req.id, { title, statement, rationale: rationale || undefined });
      // 2. Approve it
      await api.post('/interfaces/auto-requirements/approve', { requirement_ids: [ar.req.id] });
      onSaved();
    } catch (e: any) {
      setError(formatApiError(e, 'Failed'));
    }
    setSaving(false);
  };

  return (
    <div className="rounded-xl border border-blue-500/20 bg-astra-surface p-4 space-y-3">
      <h4 className="text-xs font-bold text-slate-400">Edit & Approve — {ar.req.req_id}</h4>
      {error && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
          <AlertTriangle className="h-3.5 w-3.5" /> {error}
        </div>
      )}
      <div>
        <label className="text-[10px] font-semibold text-slate-500 mb-1 block">Title</label>
        <input value={title} onChange={e => setTitle(e.target.value)}
          className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
      </div>
      <div>
        <label className="text-[10px] font-semibold text-slate-500 mb-1 block">Statement</label>
        <textarea value={statement} onChange={e => setStatement(e.target.value)} rows={3}
          className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50 resize-none" />
      </div>
      <div>
        <label className="text-[10px] font-semibold text-slate-500 mb-1 block">Rationale</label>
        <textarea value={rationale} onChange={e => setRationale(e.target.value)} rows={2}
          className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50 resize-none" />
      </div>
      <div className="flex justify-end gap-2">
        <button onClick={onCancel} className="rounded-lg border border-astra-border px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200">Cancel</button>
        <button onClick={handleSaveApprove} disabled={saving}
          className="flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-40">
          {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />} Save & Approve
        </button>
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  Main Page
// ══════════════════════════════════════

export default function AutoRequirementsPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);
  const p = `/projects/${projectId}`;

  const [projectCode, setProjectCode] = useState('');
  const [loading, setLoading]         = useState(true);
  const [autoReqs, setAutoReqs]       = useState<AutoReq[]>([]);
  const [coverage, setCoverage]       = useState<InterfaceCoverageResponse | null>(null);

  // Filters
  const [filterStatus, setFilterStatus] = useState<FilterStatus>('all');
  const [filterSource, setFilterSource] = useState('');
  const [filterLevel, setFilterLevel]   = useState('');
  const [groupBy, setGroupBy]           = useState<GroupBy>('source');
  const [search, setSearch]             = useState('');

  // Selection
  const [selected, setSelected]     = useState<Set<number>>(new Set());
  const [bulkLoading, setBulkLoading] = useState(false);

  // Delete confirmation modal
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Expanded groups
  const [expanded, setExpanded]     = useState<Set<string>>(new Set());

  // Inline edit
  const [editingId, setEditingId]   = useState<number | null>(null);

  // F-090: explicit toast severity. Pre-fix the toast banner inferred
  // severity from `toast.includes('fail')` — fragile and locale-bound.
  // The state now carries an explicit severity field; flash() takes it
  // as a second argument, defaulting to 'info' so a missing call site
  // surfaces as neutral rather than misclassifying.
  type ToastSeverity = 'success' | 'error' | 'info';
  type ToastState = { message: string; severity: ToastSeverity } | null;
  const [toast, setToast] = useState<ToastState>(null);
  const flash = (message: string, severity: ToastSeverity = 'info') => {
    setToast({ message, severity });
    setTimeout(() => setToast(null), 4000);
  };

  // ── Fetch data ──
  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [projRes, covRes] = await Promise.all([
        projectsAPI.get(projectId),
        interfaceAPI.getCoverage(projectId).catch(() => ({ data: null })),
      ]);
      setProjectCode(projRes.data?.code || '');
      setCoverage(covRes.data || null);

      // Fetch interface + environmental requirements.
      // Backend caps `limit` at 200 — going higher returns 422.
      // If you end up with > 200 of either type, this will paginate in the future.
      const [ifaceRes, envRes] = await Promise.all([
        requirementsAPI.list(projectId, { req_type: 'interface', limit: 200 }).catch(() => ({ data: [] })),
        requirementsAPI.list(projectId, { req_type: 'environmental', limit: 200 }).catch(() => ({ data: [] })),
      ]);
      const allReqs = [...(ifaceRes.data || []), ...(envRes.data || [])];

      // Filter to just auto-generated (by rationale) OR pending review —
      // this is the broader set we care about on this dashboard.
      const autoReqCandidates = allReqs.filter((r: any) =>
        r.rationale?.startsWith('Auto-generated') ||
        r.status === 'pending_review' ||
        r.status === 'auto_generated'
      );

      // Helper: build a synthetic link when no row exists in interface_requirement_links.
      // This keeps the dashboard showing the requirement even if the link creation
      // step failed or was never run during auto-generation.
      const synthesizeLink = (req: any): InterfaceRequirementLink => ({
        id: 0,
        entity_type: 'unit',
        entity_id: 0,
        requirement_id: req.id,
        link_type: 'satisfies',
        auto_generated: true,
        status: req.status === 'deleted' ? 'rejected' : 'pending_review',
        auto_req_source: req.req_type === 'environmental' ? 'environmental_spec' : 'wire_connection',
        auto_req_template: req.req_type === 'environmental' ? 'environmental_spec' : 'interface',
      } as InterfaceRequirementLink);

      // Fetch all links in chunks of 5 with a small delay between chunks.
      // The backend rate-limiter 429s under too many parallel requests, and
      // we've seen ~90 reqs on larger projects. 5 × ~18 batches × 100ms ≈ 1.8s
      // instead of a 429 storm that surfaces as fake CORS errors in the browser.
      const CHUNK_SIZE = 5;
      const CHUNK_DELAY_MS = 100;
      const linkResults: PromiseSettledResult<any>[] = [];

      for (let i = 0; i < autoReqCandidates.length; i += CHUNK_SIZE) {
        const chunk = autoReqCandidates.slice(i, i + CHUNK_SIZE);
        const chunkResults = await Promise.allSettled(
          chunk.map((req: any) => interfaceAPI.listReqLinks({ requirement_id: req.id }))
        );
        linkResults.push(...chunkResults);
        if (i + CHUNK_SIZE < autoReqCandidates.length) {
          await new Promise(r => setTimeout(r, CHUNK_DELAY_MS));
        }
      }

      const items: AutoReq[] = autoReqCandidates.map((req: any, i: number) => {
        const r = linkResults[i];
        if (r.status === 'fulfilled') {
          const links = (r.value?.data || []).filter((l: InterfaceRequirementLink) => l.auto_generated);
          if (links.length > 0) return { link: links[0], req };
        }
        // No link found (empty result or call failed) → synthesize one from the req itself
        return { link: synthesizeLink(req), req };
      });

      setAutoReqs(items);
      setExpanded(new Set(items.map(i => i.link.auto_req_template || 'unknown')));
    } catch (err) {
      console.error('[auto-requirements] fetch failed:', err);
    }
    setLoading(false);
  }, [projectId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // ── Filtered / Grouped ──
  // Workflow rule: once a req is approved (link.status='approved') or rejected
  // (link.status='rejected'), it's done with this dashboard — approved ones live
  // on the Requirements page, rejected ones are soft-deleted. Only show pending.
  const filtered = useMemo(() => autoReqs.filter(ar => {
    // Hard workflow filter: hide everything that isn't pending review
    if (ar.link.status !== 'pending_review') return false;
    // Hide soft-deleted requirements too
    if (ar.req.status === 'deleted') return false;
    // User-chosen filter within the pending set (kept for forward compat if
    // you ever reintroduce approved/rejected into this page).
    if (filterStatus !== 'all' && ar.link.status !== filterStatus) return false;
    if (filterSource && ar.link.auto_req_template !== filterSource) return false;
    if (filterLevel && ar.req.level !== filterLevel) return false;
    if (search) {
      const s = search.toLowerCase();
      if (!(ar.req.title?.toLowerCase().includes(s) || ar.req.req_id?.toLowerCase().includes(s) || ar.req.statement?.toLowerCase().includes(s))) return false;
    }
    return true;
  }), [autoReqs, filterStatus, filterSource, filterLevel, search]);

  const grouped = useMemo(() => {
    const map = new Map<string, AutoReq[]>();
    for (const ar of filtered) {
      let key = 'all';
      if (groupBy === 'source') key = ar.link.auto_req_template || 'unknown';
      else if (groupBy === 'level') key = ar.req.level || 'unknown';
      else if (groupBy === 'status') key = ar.link.status;
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(ar);
    }
    return map;
  }, [filtered, groupBy]);

  const sourceTypes = useMemo(() =>
    [...new Set(autoReqs.map(ar => ar.link.auto_req_template).filter(Boolean) as string[])].sort(),
  [autoReqs]);

  // ── Counts ──
  const pendingCount  = autoReqs.filter(ar => ar.link.status === 'pending_review').length;
  const approvedCount = autoReqs.filter(ar => ar.link.status === 'approved').length;
  const rejectedCount = autoReqs.filter(ar => ar.link.status === 'rejected').length;

  // ── Selection ──
  const toggleSelect = (reqId: number) => {
    setSelected(prev => { const n = new Set(prev); n.has(reqId) ? n.delete(reqId) : n.add(reqId); return n; });
  };
  const selectAll = () => setSelected(new Set(filtered.map(ar => ar.req.id)));
  const selectNone = () => setSelected(new Set());
  const selectAllPending = () => setSelected(new Set(filtered.filter(ar => ar.link.status === 'pending_review').map(ar => ar.req.id)));

  // ── Approve single ──
  const approveSingle = async (reqId: number) => {
    try {
      await api.post('/interfaces/auto-requirements/approve', { requirement_ids: [reqId] });
      flash('Requirement approved — trace links created', 'success');
      fetchData();
    } catch (e: any) { flash(formatApiError(e, 'Approve failed'), 'error'); }
  };

  // ── Reject single ──
  const rejectSingle = async (reqId: number) => {
    try {
      await api.post('/interfaces/auto-requirements/reject', { requirement_ids: [reqId] });
      flash('Requirement rejected', 'success');
      fetchData();
    } catch (e: any) { flash(formatApiError(e, 'Reject failed'), 'error'); }
  };

  // ── Bulk approve ──
  const bulkApprove = async () => {
    if (selected.size === 0) return;
    setBulkLoading(true);
    try {
      const res = await api.post('/interfaces/auto-requirements/approve', { requirement_ids: [...selected] });
      flash(`${res.data.approved} approved, ${res.data.trace_links_created} trace links created`, 'success');
      setSelected(new Set());
      fetchData();
    } catch (e: any) { flash(formatApiError(e, 'Bulk approve failed'), 'error'); }
    setBulkLoading(false);
  };

  // ── Bulk reject ──
  const bulkReject = async () => {
    if (selected.size === 0) return;
    setBulkLoading(true);
    try {
      const res = await api.post('/interfaces/auto-requirements/reject', { requirement_ids: [...selected] });
      flash(`${res.data.rejected} rejected`, 'success');
      setSelected(new Set());
      fetchData();
    } catch (e: any) { flash(formatApiError(e, 'Bulk reject failed'), 'error'); }
    setBulkLoading(false);
  };

  // ── Bulk delete (hard action; requires confirmation) ──
  // Unlike reject (which is a workflow state), delete is for cleaning up
  // stale/duplicate auto-generated requirements from the dashboard.
  const bulkDelete = async () => {
    if (selected.size === 0) return;
    setBulkLoading(true);
    setConfirmDelete(false);
    try {
      const res = await api.post('/requirements/bulk-delete', {
        requirement_ids: [...selected],
      });
      const { deleted, skipped_already_deleted, not_found } = res.data || {};
      const parts = [`${deleted} deleted`];
      if (skipped_already_deleted) parts.push(`${skipped_already_deleted} already deleted`);
      if (not_found) parts.push(`${not_found} not found`);
      flash(parts.join(', '), 'success');
      setSelected(new Set());
      fetchData();
    } catch (e: any) {
      flash(formatApiError(e, 'Bulk delete failed'), 'error');
    }
    setBulkLoading(false);
  };

  // ── Toggle group ──
  const toggleGroup = (key: string) => {
    setExpanded(prev => { const n = new Set(prev); n.has(key) ? n.delete(key) : n.add(key); return n; });
  };

  // ══════════════════════════════════════
  //  Render
  // ══════════════════════════════════════

  return (
    <div>
      {/* Back */}
      <button onClick={() => router.push(`${p}/interfaces`)}
        className="mb-4 flex items-center gap-1.5 text-[11px] text-slate-500 hover:text-blue-400 transition">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to Interface Management
      </button>

      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-violet-400" /> Auto-Generated Requirements
          </h1>
          <p className="mt-0.5 text-sm text-slate-500">{projectCode} · Review and approve auto-generated interface requirements</p>
        </div>
        <button onClick={fetchData}
          className="flex items-center gap-1.5 rounded-lg border border-astra-border px-3 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200">
          <RefreshCw className={clsx('h-3.5 w-3.5', loading && 'animate-spin')} /> Refresh
        </button>
      </div>

      {/* Toast — F-090: classes/icon driven by explicit severity, not
          string inspection. */}
      {toast && (
        <div
          role={toast.severity === 'error' ? 'alert' : 'status'}
          className={clsx(
            'mb-4 rounded-lg border px-3 py-2 text-xs flex items-center gap-2',
            toast.severity === 'error' && 'border-red-500/20 bg-red-500/10 text-red-400',
            toast.severity === 'success' && 'border-emerald-500/20 bg-emerald-500/10 text-emerald-400',
            toast.severity === 'info' && 'border-blue-500/20 bg-blue-500/10 text-blue-300',
          )}
        >
          {toast.severity === 'error' ? (
            <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <CheckCircle className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          {toast.message}
        </div>
      )}

      {/* Summary bar */}
      <div className="mb-5 flex gap-4 rounded-xl border border-astra-border bg-astra-surface p-4">
        <div className="text-center px-4">
          <div className="text-2xl font-bold text-slate-200">{autoReqs.length}</div>
          <div className="text-[10px] text-slate-500">Total</div>
        </div>
        <div className="text-center px-4 border-l border-astra-border">
          <div className="text-2xl font-bold text-yellow-400">{pendingCount}</div>
          <div className="text-[10px] text-slate-500">Pending</div>
        </div>
        <div className="text-center px-4 border-l border-astra-border">
          <div className="text-2xl font-bold text-emerald-400">{approvedCount}</div>
          <div className="text-[10px] text-slate-500">Approved</div>
        </div>
        <div className="text-center px-4 border-l border-astra-border">
          <div className="text-2xl font-bold text-red-400">{rejectedCount}</div>
          <div className="text-[10px] text-slate-500">Rejected</div>
        </div>
        <div className="text-center px-4 border-l border-astra-border">
          <div className="text-2xl font-bold text-blue-400">{coverage?.coverage_pct?.toFixed(0) || 0}%</div>
          <div className="text-[10px] text-slate-500">Coverage</div>
        </div>
        <div className="flex-1" />
        <div className="flex items-center gap-2 text-[11px] text-slate-500">
          <span>Group:</span>
          {(['source', 'level', 'status', 'none'] as GroupBy[]).map(g => (
            <button key={g} onClick={() => setGroupBy(g)}
              className={clsx('rounded-lg px-2.5 py-1 text-[10px] font-semibold capitalize transition',
                groupBy === g ? 'bg-blue-500/15 text-blue-400' : 'bg-astra-surface-alt text-slate-500 hover:text-slate-300')}>
              {g}
            </button>
          ))}
        </div>
      </div>

      {/* Filters + Bulk actions */}
      <div className="mb-4 flex items-center gap-2 flex-wrap">
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search requirements..."
          className="flex-1 min-w-[200px] rounded-lg border border-astra-border bg-astra-surface px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value as FilterStatus)}
          className="rounded-lg border border-astra-border bg-astra-surface px-3 py-2 text-sm text-slate-300 outline-none">
          <option value="all">All Status</option>
          <option value="pending_review">Pending</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
        {sourceTypes.length > 0 && (
          <select value={filterSource} onChange={e => setFilterSource(e.target.value)}
            className="rounded-lg border border-astra-border bg-astra-surface px-3 py-2 text-sm text-slate-300 outline-none">
            <option value="">All Sources</option>
            {sourceTypes.map(s => <option key={s} value={s}>{SOURCE_LABELS[s] || s}</option>)}
          </select>
        )}
        <select value={filterLevel} onChange={e => setFilterLevel(e.target.value)}
          className="rounded-lg border border-astra-border bg-astra-surface px-3 py-2 text-sm text-slate-300 outline-none">
          <option value="">All Levels</option>
          {['L3', 'L4', 'L5'].map(l => <option key={l} value={l}>{l}</option>)}
        </select>

        {/* Bulk action bar */}
        <div className="border-l border-astra-border pl-2 flex gap-1">
          <button onClick={selectAllPending}
            className="rounded-lg px-2 py-1.5 text-[10px] font-semibold text-slate-500 hover:text-slate-300 bg-astra-surface-alt">
            Select Pending
          </button>
          <button onClick={selectAll}
            className="rounded-lg px-2 py-1.5 text-[10px] font-semibold text-slate-500 hover:text-slate-300 bg-astra-surface-alt">
            Select All
          </button>
          {selected.size > 0 && (
            <>
              <button onClick={bulkApprove} disabled={bulkLoading}
                className="flex items-center gap-1 rounded-lg bg-emerald-500/15 px-3 py-1.5 text-[10px] font-bold text-emerald-400 hover:bg-emerald-500/25 disabled:opacity-40">
                {bulkLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                Approve ({selected.size})
              </button>
              <button onClick={bulkReject} disabled={bulkLoading}
                className="flex items-center gap-1 rounded-lg bg-red-500/15 px-3 py-1.5 text-[10px] font-bold text-red-400 hover:bg-red-500/25 disabled:opacity-40">
                {bulkLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <X className="h-3 w-3" />}
                Reject ({selected.size})
              </button>
              <button onClick={() => setConfirmDelete(true)} disabled={bulkLoading}
                className="flex items-center gap-1 rounded-lg bg-rose-500/15 px-3 py-1.5 text-[10px] font-bold text-rose-300 hover:bg-rose-500/25 disabled:opacity-40"
                title="Permanently delete the selected requirements (soft delete — audit trail preserved)">
                {bulkLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
                Delete ({selected.size})
              </button>
              <button onClick={selectNone}
                className="rounded-lg px-2 py-1.5 text-[10px] text-slate-500 hover:text-slate-300">
                Clear
              </button>
            </>
          )}
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-blue-500" /></div>
      ) : filtered.length === 0 ? (
        <div className="py-20 text-center">
          <Sparkles className="mx-auto h-10 w-10 text-slate-600 mb-3" />
          <p className="text-sm text-slate-400">
            {autoReqs.length === 0
              ? 'No auto-generated requirements yet. Create wire harnesses or import units with specs to generate.'
              : 'No requirements match your filters.'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {[...grouped.entries()].map(([groupKey, items]) => {
            const isOpen = expanded.has(groupKey) || groupBy === 'none';
            const SourceIcon = SOURCE_ICONS[groupKey] || Sparkles;
            const groupLabel = groupBy === 'source' ? (SOURCE_LABELS[groupKey] || groupKey) :
                               groupBy === 'level' ? groupKey :
                               groupBy === 'status' ? groupKey.replace(/_/g, ' ') : 'All Requirements';

            return (
              <div key={groupKey}>
                {groupBy !== 'none' && (
                  <button onClick={() => toggleGroup(groupKey)}
                    className="mb-2 flex w-full items-center gap-2 text-left">
                    {isOpen ? <ChevronDown className="h-3.5 w-3.5 text-slate-500" /> : <ChevronRight className="h-3.5 w-3.5 text-slate-500" />}
                    <SourceIcon className="h-3.5 w-3.5 text-slate-500" />
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 capitalize">{groupLabel}</span>
                    <span className="rounded-full bg-astra-surface-alt px-1.5 py-0.5 text-[9px] font-bold text-slate-500">{items.length}</span>
                  </button>
                )}

                {isOpen && (
                  <div className="space-y-1 mb-4">
                    {items.map(ar => (
                      <div key={ar.req.id}>
                        {/* Requirement row */}
                        <div className={clsx(
                          'flex items-center gap-3 rounded-xl border px-4 py-2.5 transition',
                          selected.has(ar.req.id) ? 'border-blue-500/30 bg-blue-500/5' : 'border-astra-border bg-astra-surface hover:border-blue-500/15'
                        )}>
                          {/* Checkbox */}
                          <button onClick={() => toggleSelect(ar.req.id)} className="flex-shrink-0">
                            {selected.has(ar.req.id)
                              ? <CheckSquare className="h-4 w-4 text-blue-400" />
                              : <Square className="h-4 w-4 text-slate-600 hover:text-slate-400" />}
                          </button>

                          {/* Req info */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-xs font-bold text-blue-400">{ar.req.req_id}</span>
                              <LevelBadge level={ar.req.level} />
                              <span className="text-[12px] font-medium text-slate-200 truncate">{ar.req.title}</span>
                            </div>
                            <div className="mt-0.5 text-[10px] text-slate-500 truncate">{ar.req.statement.substring(0, 140)}...</div>
                          </div>

                          {/* Source badge */}
                          <span className="rounded-full bg-astra-surface-alt px-2 py-0.5 text-[9px] font-semibold text-slate-400 flex-shrink-0">
                            {SOURCE_LABELS[ar.link.auto_req_template || ''] || ar.link.auto_req_template || '—'}
                          </span>

                          {/* Quality */}
                          <QDot score={ar.req.quality_score} />

                          {/* Status */}
                          <StatusPill status={ar.link.status} />

                          {/* Actions */}
                          <div className="flex items-center gap-1 flex-shrink-0">
                            {ar.link.status === 'pending_review' && (
                              <>
                                <button onClick={() => approveSingle(ar.req.id)}
                                  className="rounded p-1.5 text-emerald-400 hover:bg-emerald-500/10" title="Approve">
                                  <Check className="h-3.5 w-3.5" />
                                </button>
                                <button onClick={() => rejectSingle(ar.req.id)}
                                  className="rounded p-1.5 text-red-400 hover:bg-red-500/10" title="Reject">
                                  <X className="h-3.5 w-3.5" />
                                </button>
                                <button onClick={() => setEditingId(editingId === ar.req.id ? null : ar.req.id)}
                                  className="rounded p-1.5 text-blue-400 hover:bg-blue-500/10" title="Edit & Approve">
                                  <Edit3 className="h-3.5 w-3.5" />
                                </button>
                              </>
                            )}
                            <button onClick={() => router.push(`${p}/requirements/${ar.req.id}`)}
                              className="rounded p-1.5 text-slate-500 hover:text-blue-400" title="View requirement">
                              <Eye className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </div>

                        {/* Edit & Approve inline form */}
                        {editingId === ar.req.id && (
                          <div className="mt-1 mb-2 ml-7">
                            <EditApproveForm ar={ar}
                              onSaved={() => { setEditingId(null); flash('Edited and approved'); fetchData(); }}
                              onCancel={() => setEditingId(null)} />
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Delete confirmation modal */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
             onClick={() => setConfirmDelete(false)}>
          <div className="w-full max-w-md rounded-xl border border-rose-500/30 bg-astra-surface p-5 shadow-2xl"
               onClick={e => e.stopPropagation()}>
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-rose-500/15">
                <Trash2 className="h-5 w-5 text-rose-400" />
              </div>
              <div className="flex-1">
                <h3 className="text-sm font-bold text-slate-100">Delete {selected.size} requirement{selected.size !== 1 ? 's' : ''}?</h3>
                <p className="mt-1 text-xs text-slate-400">
                  The selected requirement{selected.size !== 1 ? 's' : ''} will be soft-deleted.
                  Audit history is preserved, but they will no longer appear in the review dashboard,
                  reports, or traceability views.
                </p>
                <p className="mt-2 text-[11px] text-slate-500">
                  This cannot be undone from the UI. (An admin can restore via the DB if needed.)
                </p>
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => setConfirmDelete(false)}
                className="rounded-lg border border-astra-border px-4 py-1.5 text-xs font-semibold text-slate-300 hover:bg-astra-surface-alt">
                Cancel
              </button>
              <button
                onClick={bulkDelete}
                disabled={bulkLoading}
                className="flex items-center gap-1.5 rounded-lg bg-rose-500/20 px-4 py-1.5 text-xs font-bold text-rose-300 hover:bg-rose-500/30 disabled:opacity-40">
                {bulkLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                Delete {selected.size}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
