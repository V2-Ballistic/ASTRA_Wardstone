'use client';

/**
 * ASTRA — Source Coverage dashboard
 * ====================================
 * File: frontend/src/app/projects/[id]/coverage/page.tsx
 * Phase 6 — ASTRA-TDD-INTF-002
 *
 * Per spec §13.7. Three sections:
 *   1. Top: traffic-light per level (L1..L5)
 *   2. Sortable orphan table (req | level | severity | suggestion | actions)
 *   3. Coverage exception list at the bottom
 */

import { useEffect, useMemo, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import {
  Loader2, RefreshCw, AlertTriangle, AlertCircle, CheckCircle2,
  ShieldCheck, FileText, X, Filter,
} from 'lucide-react';
import clsx from 'clsx';

import { coverageAPI } from '@/lib/coverage-api';
import { formatApiError } from '@/lib/errors';
import type {
  CoverageException,
  CoverageReportResponse,
  CoverageSeverity,
  LevelSeveritySummary,
  OrphanRequirementResponse,
} from '@/lib/coverage-types';

const LEVELS: ('L0' | 'L1' | 'L2' | 'L3' | 'L4' | 'L5')[] = ['L0', 'L1', 'L2', 'L3', 'L4', 'L5'];

function levelColor(s: LevelSeveritySummary | undefined): {
  fg: string; bg: string; border: string; label: string;
} {
  if (!s || s.total === 0) return {
    fg: 'text-slate-500', bg: 'bg-slate-800/40', border: 'border-slate-700',
    label: 'no requirements',
  };
  if (s.error > 0) return {
    fg: 'text-red-300', bg: 'bg-red-500/10', border: 'border-red-500/40',
    label: `${s.error} error${s.error === 1 ? '' : 's'}`,
  };
  if (s.warning > 0) return {
    fg: 'text-amber-300', bg: 'bg-amber-500/10', border: 'border-amber-500/40',
    label: `${s.warning} warning${s.warning === 1 ? '' : 's'}`,
  };
  return {
    fg: 'text-emerald-300', bg: 'bg-emerald-500/10', border: 'border-emerald-500/40',
    label: 'all covered',
  };
}

function severityChip(sev: CoverageSeverity) {
  if (sev === 'error') return (
    <span className="inline-flex items-center gap-1 rounded-full bg-red-500/15 px-2 py-0.5 text-xs font-semibold text-red-300">
      <AlertCircle className="h-3 w-3" /> error
    </span>
  );
  if (sev === 'warning') return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-xs font-semibold text-amber-300">
      <AlertTriangle className="h-3 w-3" /> warning
    </span>
  );
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs font-semibold text-emerald-300">
      <CheckCircle2 className="h-3 w-3" /> ok
    </span>
  );
}


// ══════════════════════════════════════════════════════════════
//  Exception filing modal
// ══════════════════════════════════════════════════════════════

function FileExceptionModal({
  open, onClose, projectId, requirement, onFiled,
}: {
  open: boolean;
  onClose: () => void;
  projectId: number;
  requirement: OrphanRequirementResponse | null;
  onFiled: () => void;
}) {
  const [reason, setReason] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) { setReason(''); setExpiresAt(''); setError(null); }
  }, [open]);

  const submit = useCallback(async () => {
    if (!requirement) return;
    if (!reason.trim()) { setError('Reason is required.'); return; }
    setBusy(true); setError(null);
    try {
      await coverageAPI.fileException({
        project_id: projectId,
        requirement_id: requirement.requirement_id,
        reason: reason.trim(),
        expires_at: expiresAt || null,
      });
      onFiled();
      onClose();
    } catch (e: unknown) {
      setError(formatApiError(e, 'Failed to file exception'));
    } finally {
      setBusy(false);
    }
  }, [requirement, reason, expiresAt, projectId, onFiled, onClose]);

  if (!open || !requirement) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-lg rounded-xl border border-astra-border bg-astra-surface p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h3 className="text-lg font-bold text-slate-200">File Coverage Exception</h3>
            <p className="text-xs text-slate-500 mt-1">
              {requirement.req_text} — {requirement.title}
            </p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="space-y-3">
          <label className="block">
            <span className="text-xs font-semibold text-slate-400">Reason (required)</span>
            <textarea
              value={reason}
              onChange={e => setReason(e.target.value)}
              rows={4}
              className="mt-1 w-full rounded-lg border border-astra-border bg-astra-surface-alt p-2 text-sm text-slate-200"
              placeholder="Why does this requirement intentionally lack architectural source linkage?"
            />
          </label>
          <label className="block">
            <span className="text-xs font-semibold text-slate-400">
              Expires at (optional)
            </span>
            <input
              type="datetime-local"
              value={expiresAt}
              onChange={e => setExpiresAt(e.target.value)}
              className="mt-1 w-full rounded-lg border border-astra-border bg-astra-surface-alt p-2 text-sm text-slate-200"
            />
          </label>
          <div className="rounded-lg bg-amber-500/10 border border-amber-500/30 p-2 text-xs text-amber-300">
            Filing creates an exception in the warning state. An admin must
            co-sign for the orphan to count toward coverage.
          </div>
          {error && (
            <div className="rounded-lg bg-red-500/10 border border-red-500/30 p-2 text-xs text-red-300">
              {error}
            </div>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <button
              onClick={onClose}
              className="rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-400 hover:text-slate-200"
            >Cancel</button>
            <button
              onClick={submit}
              disabled={busy}
              className="rounded-lg bg-blue-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-600 disabled:opacity-50"
            >
              {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : 'File'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}


// ══════════════════════════════════════════════════════════════
//  Main page
// ══════════════════════════════════════════════════════════════

type SortField = 'req_text' | 'level' | 'severity';

export default function CoveragePage() {
  const params = useParams<{ id: string }>();
  const projectId = parseInt(params.id, 10);

  const [report, setReport] = useState<CoverageReportResponse | null>(null);
  const [orphans, setOrphans] = useState<OrphanRequirementResponse[]>([]);
  const [exceptions, setExceptions] = useState<CoverageException[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [severityFilter, setSeverityFilter] =
    useState<CoverageSeverity | ''>('');
  const [levelFilter, setLevelFilter] = useState<string>('');
  const [sortField, setSortField] = useState<SortField>('severity');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [filing, setFiling] = useState<OrphanRequirementResponse | null>(null);
  const [cosigning, setCosigning] = useState<number | null>(null);

  const reload = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [r, o, ex] = await Promise.all([
        coverageAPI.getReport(projectId),
        coverageAPI.getOrphans(projectId, { limit: 200 }),
        coverageAPI.listExceptions(projectId, { active_only: true, limit: 200 }),
      ]);
      setReport(r.data);
      setOrphans(o.data.items);
      setExceptions(ex.data.items);
    } catch (e: unknown) {
      setError(formatApiError(e, 'Failed to load coverage data'));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { reload(); }, [reload]);

  const filtered = useMemo(() => {
    let rows = orphans;
    if (severityFilter) rows = rows.filter(o => o.severity === severityFilter);
    if (levelFilter)    rows = rows.filter(o => o.level === levelFilter);
    const dir = sortDir === 'asc' ? 1 : -1;
    const sevRank: Record<CoverageSeverity, number> =
      { error: 2, warning: 1, ok: 0 };
    return [...rows].sort((a, b) => {
      if (sortField === 'severity') {
        return (sevRank[a.severity] - sevRank[b.severity]) * dir;
      }
      if (sortField === 'level') {
        return a.level.localeCompare(b.level) * dir;
      }
      return a.req_text.localeCompare(b.req_text) * dir;
    });
  }, [orphans, severityFilter, levelFilter, sortField, sortDir]);

  const onSort = (f: SortField) => {
    if (sortField === f) setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    else { setSortField(f); setSortDir('desc'); }
  };

  const cosign = async (id: number) => {
    setCosigning(id);
    try {
      await coverageAPI.cosignException(id);
      await reload();
    } finally {
      setCosigning(null);
    }
  };

  if (loading) return (
    <div className="flex h-screen items-center justify-center text-slate-400">
      <Loader2 className="h-6 w-6 animate-spin mr-2" /> Loading coverage…
    </div>
  );

  if (error) return (
    <div className="p-6">
      <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-red-300">
        {error}
      </div>
    </div>
  );

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-200">Source Coverage</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Per-requirement architectural source linkage{' '}
            {report?.used_materialized_view ? (
              <span className="text-emerald-400">(materialized view)</span>
            ) : (
              <span className="text-amber-400">(live computation)</span>
            )}
            {report?.computed_at && (
              <span className="ml-1">
                • computed {new Date(report.computed_at).toLocaleString()}
              </span>
            )}
          </p>
        </div>
        <button
          onClick={reload}
          className="inline-flex items-center gap-2 rounded-lg bg-astra-surface-alt px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-astra-border"
        >
          <RefreshCw className="h-3 w-3" /> Refresh
        </button>
      </div>

      {/* Traffic light per level */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {LEVELS.map(lvl => {
          const s = report?.summary?.[lvl];
          const c = levelColor(s);
          return (
            <button
              key={lvl}
              onClick={() => setLevelFilter(levelFilter === lvl ? '' : lvl)}
              className={clsx(
                'rounded-xl border p-4 text-left transition',
                c.bg, c.border,
                levelFilter === lvl && 'ring-2 ring-blue-400',
              )}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-bold text-slate-300">{lvl}</span>
                <span className={clsx('text-xs font-semibold', c.fg)}>
                  {c.label}
                </span>
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-bold text-slate-200">
                  {s?.total ?? 0}
                </span>
                <span className="text-xs text-slate-500">
                  total
                </span>
              </div>
              {s && (s.error > 0 || s.warning > 0) && (
                <div className="mt-2 text-xs text-slate-400">
                  {s.ok} ok • {s.warning} warning • {s.error} error
                </div>
              )}
            </button>
          );
        })}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <Filter className="h-4 w-4 text-slate-500" />
        <select
          value={severityFilter}
          onChange={e => setSeverityFilter(e.target.value as CoverageSeverity | '')}
          className="rounded-lg border border-astra-border bg-astra-surface-alt px-2 py-1 text-xs text-slate-300"
        >
          <option value="">All severities</option>
          <option value="error">Error</option>
          <option value="warning">Warning</option>
        </select>
        <select
          value={levelFilter}
          onChange={e => setLevelFilter(e.target.value)}
          className="rounded-lg border border-astra-border bg-astra-surface-alt px-2 py-1 text-xs text-slate-300"
        >
          <option value="">All levels</option>
          {LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
        </select>
        <span className="text-xs text-slate-500 ml-auto">
          Showing {filtered.length} of {orphans.length} orphans
        </span>
      </div>

      {/* Orphan table */}
      <div className="rounded-xl border border-astra-border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-astra-surface-alt text-xs uppercase text-slate-500">
            <tr>
              <th
                className="px-3 py-2 text-left cursor-pointer hover:text-slate-300"
                onClick={() => onSort('req_text')}
              >Requirement</th>
              <th
                className="px-3 py-2 text-left cursor-pointer hover:text-slate-300"
                onClick={() => onSort('level')}
              >Level</th>
              <th
                className="px-3 py-2 text-left cursor-pointer hover:text-slate-300"
                onClick={() => onSort('severity')}
              >Severity</th>
              <th className="px-3 py-2 text-left">Suggested Source</th>
              <th className="px-3 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-xs text-slate-500">
                  No orphans match the current filters. Coverage looks good.
                </td>
              </tr>
            )}
            {filtered.map(o => (
              <tr key={o.requirement_id} className="border-t border-astra-border hover:bg-astra-surface-alt/40">
                <td className="px-3 py-2">
                  <div className="font-mono text-xs text-blue-400">
                    {o.req_text}
                  </div>
                  <div className="text-xs text-slate-400 truncate max-w-md">
                    {o.title}
                  </div>
                </td>
                <td className="px-3 py-2 text-xs font-semibold text-slate-300">
                  {o.level}
                </td>
                <td className="px-3 py-2">{severityChip(o.severity)}</td>
                <td className="px-3 py-2 text-xs text-slate-400">
                  {o.suggested_source_type ? (
                    <span className="rounded-full bg-blue-500/10 px-2 py-0.5 text-blue-300">
                      {o.suggested_source_type.replace(/_/g, ' ')}
                    </span>
                  ) : (
                    <span className="text-slate-600">—</span>
                  )}
                  {o.has_active_exception && (
                    <span className="ml-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-amber-300">
                      exception filed
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-right">
                  <button
                    onClick={() => setFiling(o)}
                    className="inline-flex items-center gap-1 rounded-lg bg-astra-surface-alt px-2 py-1 text-xs font-semibold text-slate-300 hover:bg-astra-border"
                  >
                    <FileText className="h-3 w-3" /> File exception
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Exception list */}
      <div>
        <h2 className="text-sm font-bold text-slate-300 mb-2">
          Coverage Exceptions ({exceptions.length})
        </h2>
        <div className="rounded-xl border border-astra-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-astra-surface-alt text-xs uppercase text-slate-500">
              <tr>
                <th className="px-3 py-2 text-left">Req ID</th>
                <th className="px-3 py-2 text-left">Reason</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-left">Expires</th>
                <th className="px-3 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {exceptions.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-3 py-6 text-center text-xs text-slate-500">
                    No active coverage exceptions filed.
                  </td>
                </tr>
              )}
              {exceptions.map(ex => (
                <tr key={ex.id} className="border-t border-astra-border">
                  <td className="px-3 py-2 font-mono text-xs text-blue-400">
                    #{ex.requirement_id}
                  </td>
                  <td className="px-3 py-2 text-xs text-slate-300 max-w-md truncate">
                    {ex.reason}
                  </td>
                  <td className="px-3 py-2 text-xs">
                    {ex.approved_by_id ? (
                      <span className="inline-flex items-center gap-1 text-emerald-300">
                        <ShieldCheck className="h-3 w-3" /> cosigned
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-amber-300">
                        <AlertTriangle className="h-3 w-3" /> awaiting cosign
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs text-slate-500">
                    {ex.expires_at
                      ? new Date(ex.expires_at).toLocaleDateString()
                      : 'never'}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {!ex.approved_by_id && (
                      <button
                        onClick={() => cosign(ex.id)}
                        disabled={cosigning === ex.id}
                        className="inline-flex items-center gap-1 rounded-lg bg-emerald-500/15 px-2 py-1 text-xs font-semibold text-emerald-300 hover:bg-emerald-500/25 disabled:opacity-50"
                      >
                        {cosigning === ex.id ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <ShieldCheck className="h-3 w-3" />
                        )}
                        Cosign
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <FileExceptionModal
        open={filing !== null}
        onClose={() => setFiling(null)}
        projectId={projectId}
        requirement={filing}
        onFiled={reload}
      />
    </div>
  );
}
