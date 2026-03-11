'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Shield, ShieldCheck, ShieldAlert, Download, RefreshCw,
  Search, Filter, ChevronLeft, ChevronRight, Loader2, Clock,
  User as UserIcon, FileText, AlertTriangle, CheckCircle,
} from 'lucide-react';
import api from '@/lib/api';

interface AuditEntry {
  id: number;
  sequence_number: number;
  timestamp: string;
  event_type: string;
  entity_type: string;
  entity_id: number;
  project_id: number | null;
  user_id: number;
  username: string | null;
  user_full_name: string | null;
  user_ip: string;
  action_detail: Record<string, any>;
  record_hash: string;
}

interface VerifyResult {
  total_records: number;
  verified_count: number;
  is_valid: boolean;
  first_invalid: { sequence_number: number; reason: string } | null;
}

const EVENT_COLORS: Record<string, string> = {
  created: '#10B981', updated: '#3B82F6', deleted: '#EF4444',
  restored: '#8B5CF6', cloned: '#F59E0B', added: '#10B981', removed: '#EF4444',
  deactivated: '#EF4444',
};

function eventColor(eventType: string): string {
  for (const [key, color] of Object.entries(EVENT_COLORS)) {
    if (eventType.includes(key)) return color;
  }
  return '#6B7280';
}

export default function AuditPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const limit = 30;

  // Filters
  const [entityType, setEntityType] = useState('');
  const [eventType, setEventType] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  // Verify
  const [verifyResult, setVerifyResult] = useState<VerifyResult | null>(null);
  const [verifying, setVerifying] = useState(false);

  const fetchLog = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, any> = { skip: page * limit, limit };
      if (entityType) params.entity_type = entityType;
      if (eventType) params.event_type = eventType;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      const res = await api.get('/audit/log', { params });
      setEntries(res.data.items || []);
      setTotal(res.data.total || 0);
    } catch {
      setEntries([]);
    }
    setLoading(false);
  }, [page, entityType, eventType, dateFrom, dateTo]);

  useEffect(() => { fetchLog(); }, [fetchLog]);

  const runVerify = async () => {
    setVerifying(true);
    try {
      const res = await api.get('/audit/verify');
      setVerifyResult(res.data);
    } catch {
      setVerifyResult(null);
    }
    setVerifying(false);
  };

  const doExport = async (format: 'json' | 'csv') => {
    try {
      const res = await api.get('/audit/export', {
        params: { format },
        responseType: format === 'csv' ? 'blob' : 'json',
      });
      if (format === 'csv') {
        const url = window.URL.createObjectURL(new Blob([res.data]));
        const a = document.createElement('a');
        a.href = url;
        a.download = 'astra_audit_log.csv';
        a.click();
      } else {
        const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'astra_audit_log.json';
        a.click();
      }
    } catch { /* ignore */ }
  };

  const totalPages = Math.ceil(total / limit);

  const inputClass =
    'rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-1.5 text-xs text-slate-200 outline-none focus:border-blue-500/50';

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Audit Log</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            NIST 800-53 AU — Tamper-evident cryptographic audit trail
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Chain status badge */}
          {verifyResult && (
            <div className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-bold ${
              verifyResult.is_valid
                ? 'bg-emerald-500/15 text-emerald-400'
                : 'bg-red-500/15 text-red-400'
            }`}>
              {verifyResult.is_valid
                ? <><ShieldCheck className="h-3.5 w-3.5" /> Chain Valid · {verifyResult.verified_count} records</>
                : <><ShieldAlert className="h-3.5 w-3.5" /> TAMPER DETECTED at #{verifyResult.first_invalid?.sequence_number}</>
              }
            </div>
          )}

          <button
            onClick={runVerify}
            disabled={verifying}
            className="flex items-center gap-1.5 rounded-lg border border-astra-border bg-astra-surface px-3 py-1.5 text-xs font-semibold text-emerald-400 transition hover:bg-emerald-500/10"
          >
            {verifying ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Shield className="h-3.5 w-3.5" />}
            Verify Integrity
          </button>

          <button
            onClick={() => doExport('csv')}
            className="flex items-center gap-1.5 rounded-lg border border-astra-border bg-astra-surface px-3 py-1.5 text-xs font-semibold text-slate-300 transition hover:bg-astra-surface-hover"
          >
            <Download className="h-3.5 w-3.5" /> CSV
          </button>
          <button
            onClick={() => doExport('json')}
            className="flex items-center gap-1.5 rounded-lg border border-astra-border bg-astra-surface px-3 py-1.5 text-xs font-semibold text-slate-300 transition hover:bg-astra-surface-hover"
          >
            <Download className="h-3.5 w-3.5" /> JSON
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-xl border border-astra-border bg-astra-surface p-4">
        <div>
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">Entity Type</label>
          <select value={entityType} onChange={e => { setEntityType(e.target.value); setPage(0); }}
            className={inputClass + ' w-36'}>
            <option value="">All</option>
            <option value="requirement">Requirement</option>
            <option value="trace_link">Trace Link</option>
            <option value="baseline">Baseline</option>
            <option value="project">Project</option>
            <option value="user">User</option>
            <option value="source_artifact">Artifact</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">Event Type</label>
          <input value={eventType} onChange={e => { setEventType(e.target.value); setPage(0); }}
            className={inputClass + ' w-44'} placeholder="e.g. requirement.updated" />
        </div>
        <div>
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">From</label>
          <input type="date" value={dateFrom}
            onChange={e => { setDateFrom(e.target.value); setPage(0); }}
            className={inputClass + ' w-36'} />
        </div>
        <div>
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">To</label>
          <input type="date" value={dateTo}
            onChange={e => { setDateTo(e.target.value); setPage(0); }}
            className={inputClass + ' w-36'} />
        </div>
        <button onClick={() => { setEntityType(''); setEventType(''); setDateFrom(''); setDateTo(''); setPage(0); }}
          className="rounded-lg border border-astra-border px-3 py-1.5 text-[11px] font-semibold text-slate-400 transition hover:text-slate-200">
          Clear
        </button>
        <div className="ml-auto text-xs text-slate-500">
          {total.toLocaleString()} record{total !== 1 ? 's' : ''}
        </div>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
          </div>
        ) : entries.length === 0 ? (
          <div className="py-16 text-center text-sm text-slate-500">No audit records found</div>
        ) : (
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-astra-border text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                <th className="px-4 py-3">Seq</th>
                <th className="px-4 py-3">Timestamp</th>
                <th className="px-4 py-3">Event</th>
                <th className="px-4 py-3">Entity</th>
                <th className="px-4 py-3">User</th>
                <th className="px-4 py-3">IP</th>
                <th className="px-4 py-3">Details</th>
                <th className="px-4 py-3">Hash</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(e => (
                <tr key={e.id} className="border-b border-astra-border/50 transition hover:bg-astra-surface-hover">
                  <td className="px-4 py-2.5 font-mono text-slate-400">#{e.sequence_number}</td>
                  <td className="px-4 py-2.5 text-slate-400 whitespace-nowrap">
                    {e.timestamp ? new Date(e.timestamp).toLocaleString() : ''}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold"
                      style={{ background: eventColor(e.event_type) + '20', color: eventColor(e.event_type) }}>
                      {e.event_type}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-slate-300">
                    <span className="font-semibold">{e.entity_type}</span>
                    <span className="text-slate-500"> #{e.entity_id}</span>
                  </td>
                  <td className="px-4 py-2.5 text-slate-300">{e.user_full_name || e.username || `#${e.user_id}`}</td>
                  <td className="px-4 py-2.5 font-mono text-slate-500">{e.user_ip || '—'}</td>
                  <td className="max-w-[200px] truncate px-4 py-2.5 text-slate-500">
                    {e.action_detail ? JSON.stringify(e.action_detail).slice(0, 80) : '—'}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-slate-600">{e.record_hash}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-between">
          <button disabled={page === 0} onClick={() => setPage(p => p - 1)}
            className="flex items-center gap-1 rounded-lg border border-astra-border px-3 py-1.5 text-xs font-semibold text-slate-400 transition hover:text-slate-200 disabled:opacity-30">
            <ChevronLeft className="h-3.5 w-3.5" /> Previous
          </button>
          <span className="text-xs text-slate-500">
            Page {page + 1} of {totalPages}
          </span>
          <button disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}
            className="flex items-center gap-1 rounded-lg border border-astra-border px-3 py-1.5 text-xs font-semibold text-slate-400 transition hover:text-slate-200 disabled:opacity-30">
            Next <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Integrity detail panel */}
      {verifyResult && !verifyResult.is_valid && verifyResult.first_invalid && (
        <div className="mt-6 rounded-xl border border-red-500/30 bg-red-500/5 p-5">
          <div className="mb-2 flex items-center gap-2 text-sm font-bold text-red-400">
            <AlertTriangle className="h-4 w-4" /> Chain Integrity Violation Detected
          </div>
          <p className="text-xs text-red-300/80 leading-relaxed">
            The hash chain broke at <strong>sequence #{verifyResult.first_invalid.sequence_number}</strong>.
            Reason: {verifyResult.first_invalid.reason}.
            This means one or more audit records may have been tampered with after creation.
            This constitutes a NIST 800-53 AU-9 violation that should be investigated immediately.
          </p>
        </div>
      )}
    </div>
  );
}
