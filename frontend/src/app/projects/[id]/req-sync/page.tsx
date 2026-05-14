'use client';

/**
 * ASTRA — Reactive Requirement Sync — Review queue
 * ==================================================
 * File: frontend/src/app/projects/[id]/req-sync/page.tsx
 * Phase 5 — ASTRA-TDD-INTF-002
 *
 * Three-pane layout per spec §12.6:
 *   - Left:   filterable list of pending proposals
 *   - Center: selected proposal — old vs new statement diff
 *   - Right:  actions (accept, reject, jump to req) + sources panel
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  Loader2, RefreshCw, Check, X, Lock, ExternalLink, AlertTriangle,
  CheckCheck, Filter, ChevronRight,
} from 'lucide-react';
import clsx from 'clsx';

import { reqSyncAPI } from '@/lib/req-sync-api';
import { formatApiError } from '@/lib/errors';
import type {
  RequirementSyncProposal,
  RequirementSyncProposalDetail,
  SourceEntityType,
  SyncProposalStatus,
  RequirementSourceLink,
} from '@/lib/req-sync-types';

const ENTITY_TYPE_LABELS: Record<SourceEntityType, string> = {
  system: 'System',
  unit: 'Unit',
  connector: 'Connector',
  pin: 'Pin',
  interface: 'Interface',
  wire_harness: 'Wire Harness',
  wire: 'Wire',
  bus_definition: 'Bus',
  message_definition: 'Message',
  message_field: 'Message Field',
  unit_env_spec: 'Env Spec',
  catalog_part: 'Catalog Part',
  requirement: 'Requirement',
};

const STATUS_BADGE: Record<SyncProposalStatus, string> = {
  pending: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  accepted: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  rejected: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
  auto_applied: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
  superseded: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
};

export default function ReqSyncPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);

  const [proposals, setProposals] = useState<RequirementSyncProposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<RequirementSyncProposalDetail | null>(null);
  const [sources, setSources] = useState<RequirementSourceLink[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState<SyncProposalStatus>('pending');
  const [entityFilter, setEntityFilter] = useState<SourceEntityType | ''>('');
  const [batchSelected, setBatchSelected] = useState<Set<number>>(new Set());
  const [rejectNotes, setRejectNotes] = useState('');

  const fetchProposals = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await reqSyncAPI.listProposals({
        project_id: projectId,
        status: statusFilter,
        trigger_entity_type: entityFilter || undefined,
        limit: 200,
      });
      setProposals(r.data.items ?? []);
    } catch (e: any) {
      setError(formatApiError(e, 'Failed to load proposals'));
    } finally {
      setLoading(false);
    }
  }, [projectId, statusFilter, entityFilter]);

  useEffect(() => { fetchProposals(); }, [fetchProposals]);

  const openDetail = async (p: RequirementSyncProposal) => {
    setBusy(true);
    setError(null);
    try {
      const r = await reqSyncAPI.getProposal(p.id);
      setSelected(r.data);
      const s = await reqSyncAPI.getRequirementSources(p.requirement_id);
      setSources(s.data.items ?? []);
    } catch (e: any) {
      setError(formatApiError(e, 'Failed to open proposal'));
    } finally {
      setBusy(false);
    }
  };

  const accept = async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      await reqSyncAPI.acceptProposal(selected.id);
      await fetchProposals();
      setSelected(null);
    } catch (e: any) {
      setError(formatApiError(e, 'Failed to accept'));
    } finally {
      setBusy(false);
    }
  };

  const reject = async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      await reqSyncAPI.rejectProposal(selected.id, {
        reviewer_notes: rejectNotes || undefined,
      });
      setRejectNotes('');
      await fetchProposals();
      setSelected(null);
    } catch (e: any) {
      setError(formatApiError(e, 'Failed to reject'));
    } finally {
      setBusy(false);
    }
  };

  const bulkAccept = async () => {
    if (batchSelected.size === 0) return;
    setBusy(true);
    setError(null);
    try {
      await reqSyncAPI.bulkAccept({
        proposal_ids: Array.from(batchSelected),
      });
      setBatchSelected(new Set());
      await fetchProposals();
    } catch (e: any) {
      setError(formatApiError(e, 'Bulk accept failed'));
    } finally {
      setBusy(false);
    }
  };

  const toggleBatch = (id: number) => {
    setBatchSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const jumpToReq = (reqId: number) => {
    router.push(`/projects/${projectId}/requirements/${reqId}`);
  };

  const filtered = useMemo(() => proposals, [proposals]);

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-astra-border bg-astra-surface px-6 py-4">
        <div>
          <h1 className="text-lg font-bold text-slate-100">Sync Proposals</h1>
          <p className="text-xs text-slate-500">
            Auto-generated requirements affected by source-data edits.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchProposals}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-md border border-astra-border px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-astra-surface-alt disabled:opacity-50"
          >
            <RefreshCw className={clsx('h-3.5 w-3.5', loading && 'animate-spin')} />
            Refresh
          </button>
          {batchSelected.size > 0 && (
            <button
              onClick={bulkAccept}
              disabled={busy}
              className="flex items-center gap-1.5 rounded-md bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-600 disabled:opacity-50"
            >
              <CheckCheck className="h-3.5 w-3.5" />
              Accept {batchSelected.size}
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="border-b border-rose-500/30 bg-rose-500/10 px-6 py-2 text-xs text-rose-300">
          <AlertTriangle className="mr-1.5 inline h-3.5 w-3.5" />
          {error}
        </div>
      )}

      {/* Three-pane body */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── Left pane: list + filters ── */}
        <div className="flex w-80 flex-col border-r border-astra-border bg-astra-surface">
          <div className="border-b border-astra-border p-3 space-y-2">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              <Filter className="h-3.5 w-3.5" /> Filters
            </div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as SyncProposalStatus)}
              className="w-full rounded-md border border-astra-border bg-astra-surface-alt px-2 py-1.5 text-xs text-slate-200"
            >
              <option value="pending">Pending</option>
              <option value="accepted">Accepted</option>
              <option value="rejected">Rejected</option>
              <option value="auto_applied">Auto-applied</option>
              <option value="superseded">Superseded</option>
            </select>
            <select
              value={entityFilter}
              onChange={(e) => setEntityFilter(e.target.value as SourceEntityType | '')}
              className="w-full rounded-md border border-astra-border bg-astra-surface-alt px-2 py-1.5 text-xs text-slate-200"
            >
              <option value="">All trigger types</option>
              {Object.entries(ENTITY_TYPE_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center p-10 text-slate-500">
                <Loader2 className="h-5 w-5 animate-spin" />
              </div>
            ) : filtered.length === 0 ? (
              <div className="p-6 text-center text-xs text-slate-500">
                No proposals match these filters.
              </div>
            ) : (
              <ul className="divide-y divide-astra-border">
                {filtered.map(p => (
                  <li
                    key={p.id}
                    className={clsx(
                      'group flex cursor-pointer items-start gap-2 px-3 py-2 hover:bg-astra-surface-alt',
                      selected?.id === p.id && 'bg-blue-500/10',
                    )}
                    onClick={() => openDetail(p)}
                  >
                    {statusFilter === 'pending' && (
                      <input
                        type="checkbox"
                        checked={batchSelected.has(p.id)}
                        onChange={(e) => { e.stopPropagation(); toggleBatch(p.id); }}
                        onClick={(e) => e.stopPropagation()}
                        className="mt-0.5 h-3.5 w-3.5 rounded border-astra-border"
                        aria-label={`Select proposal ${p.id}`}
                      />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="truncate text-xs font-semibold text-slate-200">
                          REQ #{p.requirement_id}
                        </span>
                        <span className={clsx(
                          'rounded-full border px-1.5 py-0.5 text-[9px] font-bold uppercase',
                          STATUS_BADGE[p.status],
                        )}>
                          {p.status.replace('_', ' ')}
                        </span>
                      </div>
                      <div className="mt-0.5 truncate text-[11px] text-slate-400">
                        {ENTITY_TYPE_LABELS[p.triggered_by_entity_type]} #{p.triggered_by_entity_id} · {p.trigger_event}
                      </div>
                      <div className="mt-0.5 text-[10px] text-slate-600">
                        {new Date(p.created_at).toLocaleString()}
                      </div>
                    </div>
                    <ChevronRight className="mt-1 h-3.5 w-3.5 text-slate-600 group-hover:text-slate-400" />
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* ── Center pane: diff ── */}
        <div className="flex flex-1 flex-col overflow-hidden bg-astra-bg">
          {!selected ? (
            <div className="flex flex-1 items-center justify-center text-sm text-slate-500">
              Select a proposal to review.
            </div>
          ) : (
            <>
              <div className="border-b border-astra-border bg-astra-surface px-6 py-3">
                <div className="flex items-center gap-3">
                  <h2 className="text-sm font-bold text-slate-100">
                    {selected.requirement_req_id ?? `REQ #${selected.requirement_id}`} — {selected.requirement_title}
                  </h2>
                  <span className={clsx(
                    'rounded-full border px-1.5 py-0.5 text-[9px] font-bold uppercase',
                    STATUS_BADGE[selected.status],
                  )}>
                    {selected.status.replace('_', ' ')}
                  </span>
                </div>
                <div className="mt-1 text-xs text-slate-400">
                  Triggered by <strong className="text-slate-300">
                    {ENTITY_TYPE_LABELS[selected.triggered_by_entity_type]} #{selected.triggered_by_entity_id}
                  </strong> ({selected.trigger_event}) · proposal type {selected.proposal_type}
                </div>
              </div>
              <div className="grid flex-1 grid-cols-2 gap-4 overflow-y-auto p-6">
                <div>
                  <div className="mb-2 text-[10px] font-bold uppercase tracking-widest text-slate-500">Old statement</div>
                  <pre className="whitespace-pre-wrap rounded-md border border-rose-500/20 bg-rose-500/5 p-3 text-xs text-slate-200">
                    {selected.old_statement || '(empty)'}
                  </pre>
                </div>
                <div>
                  <div className="mb-2 text-[10px] font-bold uppercase tracking-widest text-slate-500">New statement</div>
                  <pre className="whitespace-pre-wrap rounded-md border border-emerald-500/20 bg-emerald-500/5 p-3 text-xs text-slate-200">
                    {selected.new_statement ?? '(deleted source — review)'}
                  </pre>
                </div>
                {Object.keys(selected.field_diffs ?? {}).length > 0 && (
                  <div className="col-span-2">
                    <div className="mb-2 text-[10px] font-bold uppercase tracking-widest text-slate-500">Field diffs</div>
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-astra-border text-left text-[10px] uppercase tracking-wider text-slate-500">
                          <th className="py-1 pr-3">Field</th>
                          <th className="py-1 pr-3">Old</th>
                          <th className="py-1">New</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(selected.field_diffs).map(([k, v]) => (
                          <tr key={k} className="border-b border-astra-border/40">
                            <td className="py-1 pr-3 font-mono text-slate-400">{k}</td>
                            <td className="py-1 pr-3 text-rose-300">{String(v?.old ?? '')}</td>
                            <td className="py-1 text-emerald-300">{String(v?.new ?? '')}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* ── Right pane: actions + sources ── */}
        <div className="flex w-72 flex-col border-l border-astra-border bg-astra-surface p-3 overflow-y-auto">
          {!selected ? (
            <div className="text-xs text-slate-500">No proposal selected.</div>
          ) : (
            <>
              <div className="space-y-2">
                {selected.status === 'pending' && (
                  <>
                    <button
                      onClick={accept}
                      disabled={busy}
                      className="flex w-full items-center justify-center gap-1.5 rounded-md bg-emerald-500 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-600 disabled:opacity-50"
                    >
                      <Check className="h-3.5 w-3.5" /> Accept
                    </button>
                    <textarea
                      value={rejectNotes}
                      onChange={(e) => setRejectNotes(e.target.value)}
                      placeholder="Optional rejection notes…"
                      rows={2}
                      className="w-full rounded-md border border-astra-border bg-astra-surface-alt px-2 py-1.5 text-xs text-slate-200"
                    />
                    <button
                      onClick={reject}
                      disabled={busy}
                      className="flex w-full items-center justify-center gap-1.5 rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs font-semibold text-rose-300 hover:bg-rose-500/20 disabled:opacity-50"
                    >
                      <X className="h-3.5 w-3.5" /> Reject
                    </button>
                  </>
                )}
                <button
                  onClick={() => jumpToReq(selected.requirement_id)}
                  className="flex w-full items-center justify-center gap-1.5 rounded-md border border-astra-border px-3 py-2 text-xs font-medium text-slate-300 hover:bg-astra-surface-alt"
                >
                  <ExternalLink className="h-3.5 w-3.5" /> Open requirement
                </button>
              </div>

              <div className="mt-6">
                <div className="mb-2 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-slate-500">
                  <Lock className="h-3 w-3" /> Source links
                </div>
                {sources.length === 0 ? (
                  <div className="text-xs text-slate-500">No source links.</div>
                ) : (
                  <ul className="space-y-1.5 text-xs">
                    {sources.map(s => (
                      <li key={s.id} className="rounded-md border border-astra-border bg-astra-surface-alt p-2">
                        <div className="font-semibold text-slate-200">
                          {ENTITY_TYPE_LABELS[s.source_entity_type]} #{s.source_entity_id}
                        </div>
                        <div className="text-[10px] text-slate-500 font-mono">
                          tpl: {s.template_id} · role: {s.role}
                        </div>
                        <div className="text-[10px] text-slate-600">
                          last sync: {s.last_synced_at ? new Date(s.last_synced_at).toLocaleString() : '—'}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
