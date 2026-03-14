'use client';

/**
 * ASTRA — Audit Log (Project-Scoped)
 * File: frontend/src/app/projects/[id]/audit/page.tsx
 *
 * Fixes:
 *   - API path: /audit/ → /audit/log
 *   - Added Export Audit Package button (ZIP + CSV)
 *   - Added chain verification button
 */

import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import {
  Shield, Loader2, RefreshCw, ChevronLeft, ChevronRight,
  Filter, Download, PackageCheck, CheckCircle, AlertTriangle,
} from 'lucide-react';
import api from '@/lib/api';
import { projectsAPI } from '@/lib/api';

export default function AuditLogPage() {
  const params = useParams();
  const projectId = Number(params.id);

  const [projectCode, setProjectCode] = useState('');
  const [entries, setEntries] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [entityType, setEntityType] = useState('');
  const [eventType, setEventType] = useState('');
  const [verifyResult, setVerifyResult] = useState<any>(null);
  const [verifying, setVerifying] = useState(false);
  const [exporting, setExporting] = useState(false);

  const limit = 50;

  useEffect(() => {
    projectsAPI.get(projectId).then(r => setProjectCode(r.data?.code || '')).catch(() => {});
  }, [projectId]);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const p: any = { skip: page * limit, limit, project_id: projectId };
      if (entityType) p.entity_type = entityType;
      if (eventType) p.event_type = eventType;
      const res = await api.get('/audit/log', { params });
      setEntries(res.data?.items || []);
      setTotal(res.data?.total || 0);
    } catch {}
    setLoading(false);
  }, [projectId, page, entityType, eventType]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  const handleVerifyChain = async () => {
    setVerifying(true);
    try {
      const res = await api.get('/audit/verify', { params: { project_id: projectId } });
      setVerifyResult(res.data);
    } catch {
      setVerifyResult({ is_valid: false, error: 'Verification request failed' });
    }
    setVerifying(false);
  };

  const handleExportCSV = async () => {
    setExporting(true);
    try {
      const res = await api.get('/audit/export', {
        params: { project_id: projectId, format: 'csv' },
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `ASTRA_Audit_Log_${projectCode || projectId}.csv`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch {}
    setExporting(false);
  };

  const handleExportJSON = async () => {
    setExporting(true);
    try {
      const res = await api.get('/audit/export', {
        params: { project_id: projectId, format: 'json' },
      });
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ASTRA_Audit_Log_${projectCode || projectId}.json`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch {}
    setExporting(false);
  };

  const handleExportAuditPackage = async () => {
    setExporting(true);
    try {
      const res = await api.get('/audit/package', {
        params: { project_id: projectId },
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `ASTRA_Audit_Package_${projectCode || projectId}.zip`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch {
      // Fallback to CSV if package endpoint not available
      await handleExportCSV();
    }
    setExporting(false);
  };

  const inputClass = 'rounded-lg border border-astra-border bg-astra-surface px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-blue-500/50';

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Audit Log</h1>
          <p className="mt-0.5 text-sm text-slate-500">{projectCode} · Security and change audit trail</p>
        </div>
        <div className="flex items-center gap-2">
          {/* Verify Chain */}
          <button onClick={handleVerifyChain} disabled={verifying}
            className="flex items-center gap-1.5 rounded-lg border border-astra-border px-3 py-2 text-xs text-slate-400 hover:text-slate-200 disabled:opacity-50">
            {verifying ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Shield className="h-3.5 w-3.5" />}
            Verify Chain
          </button>
          {/* Export dropdown */}
          <div className="relative group">
            <button disabled={exporting}
              className="flex items-center gap-1.5 rounded-lg bg-blue-500 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-600 disabled:opacity-50">
              {exporting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
              Export
            </button>
            <div className="absolute right-0 top-full z-20 mt-1 hidden w-52 rounded-lg border border-astra-border bg-astra-surface shadow-xl group-hover:block">
              <button onClick={handleExportAuditPackage}
                className="flex w-full items-center gap-2 px-4 py-2.5 text-xs text-slate-300 hover:bg-astra-surface-hover rounded-t-lg">
                <PackageCheck className="h-3.5 w-3.5 text-emerald-400" /> Full Audit Package (ZIP)
              </button>
              <button onClick={handleExportCSV}
                className="flex w-full items-center gap-2 px-4 py-2.5 text-xs text-slate-300 hover:bg-astra-surface-hover">
                <Download className="h-3.5 w-3.5 text-blue-400" /> Export CSV
              </button>
              <button onClick={handleExportJSON}
                className="flex w-full items-center gap-2 px-4 py-2.5 text-xs text-slate-300 hover:bg-astra-surface-hover rounded-b-lg">
                <Download className="h-3.5 w-3.5 text-violet-400" /> Export JSON
              </button>
            </div>
          </div>
          {/* Refresh */}
          <button onClick={fetchLogs} className="rounded-full border border-astra-border p-2 text-slate-400 hover:text-slate-200">
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Chain Verification Banner */}
      {verifyResult && (
        <div className={`mb-4 flex items-center gap-3 rounded-xl border px-4 py-3 ${
          verifyResult.is_valid
            ? 'border-emerald-500/20 bg-emerald-500/5'
            : 'border-red-500/20 bg-red-500/5'
        }`}>
          {verifyResult.is_valid
            ? <CheckCircle className="h-4 w-4 text-emerald-400 flex-shrink-0" />
            : <AlertTriangle className="h-4 w-4 text-red-400 flex-shrink-0" />
          }
          <span className={`text-xs ${verifyResult.is_valid ? 'text-emerald-300' : 'text-red-300'}`}>
            {verifyResult.is_valid
              ? `Hash chain verified: ${verifyResult.verified_count} records, no tampering detected.`
              : `Chain integrity failure at sequence ${verifyResult.first_invalid?.sequence_number || '?'}: ${verifyResult.first_invalid?.reason || verifyResult.error || 'Unknown error'}`
            }
          </span>
          <button onClick={() => setVerifyResult(null)} className="ml-auto text-slate-500 hover:text-slate-300 text-xs">Dismiss</button>
        </div>
      )}

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Filter className="h-3.5 w-3.5 text-slate-500" />
          <input value={entityType} onChange={(e) => { setEntityType(e.target.value); setPage(0); }}
            placeholder="Entity type" className={inputClass + ' w-32'} />
          <input value={eventType} onChange={(e) => { setEventType(e.target.value); setPage(0); }}
            placeholder="Event type" className={inputClass + ' w-40'} />
          <button onClick={() => { setEntityType(''); setEventType(''); setPage(0); }}
            className="rounded-lg border border-astra-border px-3 py-1.5 text-[11px] text-slate-400 hover:text-slate-200">Clear</button>
        </div>
        <span className="ml-auto text-xs text-slate-500">{total} records</span>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
        {loading ? (
          <div className="flex items-center justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-blue-500" /></div>
        ) : entries.length === 0 ? (
          <div className="py-16 text-center text-sm text-slate-500">No audit records found</div>
        ) : (
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-astra-border text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                <th className="px-4 py-3 w-8">#</th>
                <th className="px-4 py-3">Timestamp</th>
                <th className="px-4 py-3">Event</th>
                <th className="px-4 py-3">Entity</th>
                <th className="px-4 py-3">User</th>
                <th className="px-4 py-3">Details</th>
                <th className="px-4 py-3 w-24">Hash</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e, i) => (
                <tr key={e.id || i} className="border-b border-astra-border/50 hover:bg-astra-surface-hover">
                  <td className="px-4 py-2.5 text-slate-600 font-mono text-[10px]">{e.sequence_number || e.id}</td>
                  <td className="px-4 py-2.5 text-slate-400 whitespace-nowrap">
                    {e.timestamp ? new Date(e.timestamp).toLocaleString() : '—'}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className="rounded-full bg-blue-500/10 px-2 py-0.5 text-[10px] font-semibold text-blue-400">
                      {e.event_type}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-slate-300">{e.entity_type}:{e.entity_id}</td>
                  <td className="px-4 py-2.5 text-slate-300">{e.user_full_name || e.username || e.user_id || '—'}</td>
                  <td className="px-4 py-2.5 text-slate-500 max-w-[250px]">
                    {e.action_detail ? (
                      <span className="truncate block" title={typeof e.action_detail === 'object' ? JSON.stringify(e.action_detail) : e.action_detail}>
                        {typeof e.action_detail === 'object' ? JSON.stringify(e.action_detail).substring(0, 80) + '…' : String(e.action_detail).substring(0, 80)}
                      </span>
                    ) : '—'}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-[10px] text-slate-600">{e.record_hash || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {total > limit && (
        <div className="mt-3 flex items-center justify-center gap-3">
          <button onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0}
            className="rounded-lg border border-astra-border p-1.5 text-slate-400 disabled:opacity-30">
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
          <span className="text-xs text-slate-500">Page {page + 1} of {Math.ceil(total / limit)}</span>
          <button onClick={() => setPage(page + 1)} disabled={(page + 1) * limit >= total}
            className="rounded-lg border border-astra-border p-1.5 text-slate-400 disabled:opacity-30">
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
    </div>
  );
}
