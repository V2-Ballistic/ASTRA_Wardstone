'use client';

/**
 * ASTRA — Auto-Requirement Review Dashboard
 * =============================================
 * File: frontend/src/app/projects/[id]/interfaces/auto-requirements/page.tsx
 * Path: C:\Users\Mason\Documents\ASTRA\frontend\src\app\projects\[id]\interfaces\auto-requirements\page.tsx
 *
 * Displays all auto-generated requirements from the interface module.
 * Features: filter by source/status/level, bulk approve/reject, grouped view.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  Loader2, RefreshCw, ArrowLeft, Check, X, AlertTriangle,
  CheckSquare, Square, ChevronRight, ChevronDown, Filter,
  Cable, Zap, Radio, Shield, Thermometer, Cpu, Sparkles,
  Eye, Edit3,
} from 'lucide-react';
import clsx from 'clsx';
import { projectsAPI, requirementsAPI } from '@/lib/api';
import { interfaceAPI } from '@/lib/interface-api';
import type { InterfaceRequirementLink, InterfaceCoverageResponse } from '@/lib/interface-types';
import { RISK_COLORS } from '@/lib/interface-types';

// ── Types ──
interface AutoReq {
  link: InterfaceRequirementLink;
  req?: {
    id: number; req_id: string; title: string; statement: string;
    level: string; priority: string; status: string; quality_score: number;
  };
}

type GroupBy = 'source' | 'level' | 'status' | 'none';
type FilterStatus = 'all' | 'pending_review' | 'approved' | 'rejected';

// ── Source icon map ──
const SOURCE_ICONS: Record<string, any> = {
  bus_connection: Cable, message_definition: Radio, message_field: Radio,
  power_wire: Zap, ground_wire: Shield, discrete_signal: Zap,
  rf_connection: Radio, shield_grounding: Shield,
  harness_overall: Cable, environmental_spec: Thermometer,
  emi_spec: Radio, unit_import: Cpu,
};
const SOURCE_LABELS: Record<string, string> = {
  bus_connection: 'Bus Connection', message_definition: 'Message', message_field: 'Message Field',
  power_wire: 'Power Wire', ground_wire: 'Ground Wire', discrete_signal: 'Discrete Signal',
  rf_connection: 'RF Connection', shield_grounding: 'Shield Grounding',
  harness_overall: 'Harness Overall', environmental_spec: 'Environmental',
  emi_spec: 'EMI/EMC', unit_import: 'Unit Import',
  env_parent: 'Env Parent',
};

// ── Quality dot ──
function QDot({ score }: { score: number }) {
  const color = score >= 85 ? '#10B981' : score >= 70 ? '#F59E0B' : '#EF4444';
  return <span className="font-mono text-[10px] font-bold" style={{ color }}>{score.toFixed(0)}</span>;
}

// ── Level badge ──
const LEVEL_COLORS: Record<string, string> = { L1: '#EF4444', L2: '#F59E0B', L3: '#3B82F6', L4: '#8B5CF6', L5: '#6B7280' };
function LevelBadge({ level }: { level: string }) {
  const c = LEVEL_COLORS[level] || '#6B7280';
  return <span className="rounded-full px-1.5 py-0.5 text-[9px] font-bold" style={{ background: `${c}20`, color: c }}>{level}</span>;
}

// ── Status pill ──
const STATUS_STYLES: Record<string, { bg: string; text: string }> = {
  pending_review: { bg: 'rgba(245,158,11,0.15)', text: '#F59E0B' },
  approved: { bg: 'rgba(16,185,129,0.15)', text: '#10B981' },
  rejected: { bg: 'rgba(239,68,68,0.15)', text: '#EF4444' },
  draft: { bg: 'rgba(100,116,139,0.15)', text: '#94A3B8' },
};
function StatusPill({ status }: { status: string }) {
  const s = STATUS_STYLES[status] || STATUS_STYLES.draft;
  return <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize" style={{ background: s.bg, color: s.text }}>{status.replace(/_/g, ' ')}</span>;
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
  const [loading, setLoading] = useState(true);
  const [autoReqs, setAutoReqs] = useState<AutoReq[]>([]);
  const [coverage, setCoverage] = useState<InterfaceCoverageResponse | null>(null);

  // Filters
  const [filterStatus, setFilterStatus] = useState<FilterStatus>('all');
  const [filterSource, setFilterSource] = useState('');
  const [filterLevel, setFilterLevel] = useState('');
  const [groupBy, setGroupBy] = useState<GroupBy>('source');
  const [search, setSearch] = useState('');

  // Selection for bulk actions
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkAction, setBulkAction] = useState<string | null>(null);

  // Expanded groups
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [projRes, covRes] = await Promise.all([
        projectsAPI.get(projectId),
        interfaceAPI.getCoverage(projectId).catch(() => ({ data: null })),
      ]);
      setProjectCode(projRes.data?.code || '');
      setCoverage(covRes.data || null);

      // Fetch interface + environmental requirements, then match with links
      const [ifaceRes, envRes] = await Promise.all([
        requirementsAPI.list(projectId, { req_type: 'interface', limit: 500 }).catch(() => ({ data: [] })),
        requirementsAPI.list(projectId, { req_type: 'environmental', limit: 500 }).catch(() => ({ data: [] })),
      ]);
      const allReqs = [...(ifaceRes.data || []), ...(envRes.data || [])];

      // For each requirement, try to find its interface link
      const items: AutoReq[] = [];
      for (const req of allReqs) {
        try {
          const linkRes = await interfaceAPI.listReqLinks({ requirement_id: req.id });
          const autoLinks = (linkRes.data || []).filter((l: InterfaceRequirementLink) => l.auto_generated);
          if (autoLinks.length > 0) {
            items.push({ link: autoLinks[0], req });
          }
        } catch {
          // If link fetch fails, check if rationale indicates auto-generation
          if (req.rationale?.startsWith('Auto-generated')) {
            items.push({
              link: {
                id: 0, entity_type: 'unit', entity_id: 0,
                requirement_id: req.id, link_type: 'satisfies',
                auto_generated: true, status: 'pending_review',
                auto_req_source: req.req_type === 'environmental' ? 'environmental_spec' : 'wire_connection',
                auto_req_template: req.req_type === 'environmental' ? 'environmental_spec' : 'interface',
              } as InterfaceRequirementLink,
              req,
            });
          }
        }
      }
      setAutoReqs(items);
      // Expand all groups by default
      const sources = new Set(items.map(i => i.link.auto_req_template || 'unknown'));
      setExpanded(sources);
    } catch { }
    setLoading(false);
  }, [projectId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Filter
  const filtered = useMemo(() => autoReqs.filter(ar => {
    if (filterStatus !== 'all' && ar.link.status !== filterStatus) return false;
    if (filterSource && ar.link.auto_req_template !== filterSource) return false;
    if (filterLevel && ar.req?.level !== filterLevel) return false;
    if (search) {
      const s = search.toLowerCase();
      if (!(ar.req?.title?.toLowerCase().includes(s) || ar.req?.req_id?.toLowerCase().includes(s) || ar.req?.statement?.toLowerCase().includes(s))) return false;
    }
    return true;
  }), [autoReqs, filterStatus, filterSource, filterLevel, search]);

  // Group
  const grouped = useMemo(() => {
    const map = new Map<string, AutoReq[]>();
    for (const ar of filtered) {
      let key = 'ungrouped';
      if (groupBy === 'source') key = ar.link.auto_req_template || 'unknown';
      else if (groupBy === 'level') key = ar.req?.level || 'unknown';
      else if (groupBy === 'status') key = ar.link.status;
      else key = 'all';
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(ar);
    }
    return map;
  }, [filtered, groupBy]);

  // Source types for filter dropdown
  const sourceTypes = useMemo(() => [...new Set(autoReqs.map(ar => ar.link.auto_req_template).filter(Boolean))].sort(), [autoReqs]);

  // Bulk actions
  const toggleSelect = (id: number) => setSelected(prev => {
    const next = new Set(prev);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });
  const selectAll = () => setSelected(new Set(filtered.map(ar => ar.link.id)));
  const selectNone = () => setSelected(new Set());

  const executeBulk = async (action: string) => {
    if (selected.size === 0) return;
    setBulkAction(action);
    const reqIds = filtered.filter(ar => selected.has(ar.link.id)).map(ar => ar.link.requirement_id);
    try {
      if (action === 'approve') {
        // Update link statuses to approved
        for (const ar of filtered) {
          if (selected.has(ar.link.id)) {
            // Direct status update via link — in real app, use a batch endpoint
            ar.link.status = 'approved';
          }
        }
        setAutoReqs([...autoReqs]);
      } else if (action === 'reject') {
        await interfaceAPI.executeImpact({
          affected_req_ids: reqIds,
          action: 'delete_requirements',
          project_id: projectId,
          change_description: 'Bulk rejected from auto-requirement review',
        });
      } else if (action === 'review') {
        await interfaceAPI.executeImpact({
          affected_req_ids: reqIds,
          action: 'mark_for_review',
          project_id: projectId,
          change_description: 'Sent for review from auto-requirement dashboard',
        });
      }
      setSelected(new Set());
      fetchData();
    } catch { }
    setBulkAction(null);
  };

  const toggleGroup = (key: string) => setExpanded(prev => {
    const next = new Set(prev);
    next.has(key) ? next.delete(key) : next.add(key);
    return next;
  });

  const pendingCount = autoReqs.filter(ar => ar.link.status === 'pending_review').length;
  const approvedCount = autoReqs.filter(ar => ar.link.status === 'approved').length;

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
        <button onClick={fetchData} className="flex items-center gap-1.5 rounded-lg border border-astra-border px-3 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200">
          <RefreshCw className={clsx('h-3.5 w-3.5', loading && 'animate-spin')} /> Refresh
        </button>
      </div>

      {/* Summary bar */}
      <div className="mb-5 flex gap-4 rounded-xl border border-astra-border bg-astra-surface p-4">
        <div className="text-center px-4">
          <div className="text-2xl font-bold text-slate-200">{autoReqs.length}</div>
          <div className="text-[10px] text-slate-500">Total Auto-Reqs</div>
        </div>
        <div className="text-center px-4 border-l border-astra-border">
          <div className="text-2xl font-bold text-yellow-400">{pendingCount}</div>
          <div className="text-[10px] text-slate-500">Pending Review</div>
        </div>
        <div className="text-center px-4 border-l border-astra-border">
          <div className="text-2xl font-bold text-emerald-400">{approvedCount}</div>
          <div className="text-[10px] text-slate-500">Approved</div>
        </div>
        <div className="text-center px-4 border-l border-astra-border">
          <div className="text-2xl font-bold text-blue-400">{coverage?.coverage_pct?.toFixed(0) || 0}%</div>
          <div className="text-[10px] text-slate-500">Coverage</div>
        </div>
        <div className="flex-1" />
        <div className="flex items-center gap-2 text-[11px] text-slate-500">
          <span>Group by:</span>
          {(['source', 'level', 'status', 'none'] as GroupBy[]).map(g => (
            <button key={g} onClick={() => setGroupBy(g)}
              className={clsx('rounded-lg px-2.5 py-1 text-[10px] font-semibold capitalize transition',
                groupBy === g ? 'bg-blue-500/15 text-blue-400' : 'bg-astra-surface-alt text-slate-500 hover:text-slate-300')}>
              {g}
            </button>
          ))}
        </div>
      </div>

      {/* Filters + bulk actions */}
      <div className="mb-4 flex items-center gap-2">
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search requirements..."
          className="flex-1 rounded-lg border border-astra-border bg-astra-surface px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value as FilterStatus)}
          className="rounded-lg border border-astra-border bg-astra-surface px-3 py-2 text-sm text-slate-300 outline-none">
          <option value="all">All Status</option>
          <option value="pending_review">Pending</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
        <select value={filterSource} onChange={e => setFilterSource(e.target.value)}
          className="rounded-lg border border-astra-border bg-astra-surface px-3 py-2 text-sm text-slate-300 outline-none">
          <option value="">All Sources</option>
          {sourceTypes.map(s => <option key={s} value={s}>{SOURCE_LABELS[s!] || s}</option>)}
        </select>
        <select value={filterLevel} onChange={e => setFilterLevel(e.target.value)}
          className="rounded-lg border border-astra-border bg-astra-surface px-3 py-2 text-sm text-slate-300 outline-none">
          <option value="">All Levels</option>
          {['L3', 'L4', 'L5'].map(l => <option key={l} value={l}>{l}</option>)}
        </select>

        <div className="border-l border-astra-border pl-2 flex gap-1">
          <button onClick={selectAll} className="rounded-lg px-2 py-1.5 text-[10px] font-semibold text-slate-500 hover:text-slate-300 bg-astra-surface-alt">
            Select All
          </button>
          {selected.size > 0 && (
            <>
              <button onClick={() => executeBulk('approve')} disabled={!!bulkAction}
                className="flex items-center gap-1 rounded-lg bg-emerald-500/15 px-3 py-1.5 text-[10px] font-bold text-emerald-400 hover:bg-emerald-500/25">
                <Check className="h-3 w-3" /> Approve ({selected.size})
              </button>
              <button onClick={() => executeBulk('reject')} disabled={!!bulkAction}
                className="flex items-center gap-1 rounded-lg bg-red-500/15 px-3 py-1.5 text-[10px] font-bold text-red-400 hover:bg-red-500/25">
                <X className="h-3 w-3" /> Reject ({selected.size})
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
            {autoReqs.length === 0 ? 'No auto-generated requirements yet. Create wire harnesses or import units with specs to generate.' : 'No requirements match your filters.'}
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
                      <div key={ar.link.id}
                        className={clsx('flex items-center gap-3 rounded-xl border px-4 py-2.5 transition',
                          selected.has(ar.link.id) ? 'border-blue-500/30 bg-blue-500/5' : 'border-astra-border bg-astra-surface hover:border-blue-500/15')}>
                        {/* Checkbox */}
                        <button onClick={() => toggleSelect(ar.link.id)} className="flex-shrink-0">
                          {selected.has(ar.link.id) ? (
                            <CheckSquare className="h-4 w-4 text-blue-400" />
                          ) : (
                            <Square className="h-4 w-4 text-slate-600 hover:text-slate-400" />
                          )}
                        </button>

                        {/* Req info */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs font-bold text-blue-400">{ar.req?.req_id || '—'}</span>
                            <LevelBadge level={ar.req?.level || 'L4'} />
                            <span className="text-[12px] font-medium text-slate-200 truncate">{ar.req?.title || 'Unknown'}</span>
                          </div>
                          <div className="mt-0.5 text-[10px] text-slate-500 truncate">
                            {ar.req?.statement?.substring(0, 120) || ''}...
                          </div>
                        </div>

                        {/* Source badge */}
                        <span className="rounded-full bg-astra-surface-alt px-2 py-0.5 text-[9px] font-semibold text-slate-400">
                          {SOURCE_LABELS[ar.link.auto_req_template || ''] || ar.link.auto_req_template}
                        </span>

                        {/* Quality */}
                        <QDot score={ar.req?.quality_score || 0} />

                        {/* Status */}
                        <StatusPill status={ar.link.status} />

                        {/* Actions */}
                        <button onClick={() => router.push(`${p}/requirements/${ar.link.requirement_id}`)}
                          className="rounded p-1 text-slate-500 hover:text-blue-400">
                          <Eye className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
