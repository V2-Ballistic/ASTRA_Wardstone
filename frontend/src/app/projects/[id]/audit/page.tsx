'use client';

/**
 * ASTRA — Audit Log (Project-Scoped)
 * File: frontend/src/app/projects/[id]/audit/page.tsx
 */

import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { Shield, Loader2, RefreshCw, Search, ChevronLeft, ChevronRight, Filter } from 'lucide-react';
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

  const limit = 50;

  useEffect(() => { projectsAPI.get(projectId).then(r => setProjectCode(r.data?.code || '')).catch(() => {}); }, [projectId]);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params: any = { skip: page * limit, limit, project_id: projectId };
      if (entityType) params.entity_type = entityType;
      if (eventType) params.event_type = eventType;
      const res = await api.get('/audit/', { params });
      setEntries(res.data?.entries || res.data?.items || []);
      setTotal(res.data?.total || 0);
    } catch {}
    setLoading(false);
  }, [projectId, page, entityType, eventType]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  const inputClass = 'rounded-lg border border-astra-border bg-astra-surface px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-blue-500/50';

  return (
    <div>
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Audit Log</h1>
          <p className="mt-0.5 text-sm text-slate-500">{projectCode} · Security and change audit trail</p>
        </div>
        <button onClick={fetchLogs} className="rounded-full border border-astra-border p-2 text-slate-400 hover:text-slate-200"><RefreshCw className="h-3.5 w-3.5" /></button>
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Filter className="h-3.5 w-3.5 text-slate-500" />
          <input value={entityType} onChange={(e) => { setEntityType(e.target.value); setPage(0); }} placeholder="Entity type" className={inputClass + ' w-32'} />
          <input value={eventType} onChange={(e) => { setEventType(e.target.value); setPage(0); }} placeholder="Event type" className={inputClass + ' w-40'} />
          <button onClick={() => { setEntityType(''); setEventType(''); setPage(0); }} className="rounded-lg border border-astra-border px-3 py-1.5 text-[11px] text-slate-400 hover:text-slate-200">Clear</button>
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
                <th className="px-4 py-3">Timestamp</th>
                <th className="px-4 py-3">Event</th>
                <th className="px-4 py-3">Entity</th>
                <th className="px-4 py-3">User</th>
                <th className="px-4 py-3">Details</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e, i) => (
                <tr key={e.id || i} className="border-b border-astra-border/50 hover:bg-astra-surface-hover">
                  <td className="px-4 py-2.5 text-slate-400 whitespace-nowrap">{e.timestamp ? new Date(e.timestamp).toLocaleString() : '—'}</td>
                  <td className="px-4 py-2.5"><span className="rounded-full bg-blue-500/10 px-2 py-0.5 text-[10px] font-semibold text-blue-400">{e.event_type}</span></td>
                  <td className="px-4 py-2.5 text-slate-300">{e.entity_type}:{e.entity_id}</td>
                  <td className="px-4 py-2.5 text-slate-300">{e.user_full_name || e.user_id || '—'}</td>
                  <td className="px-4 py-2.5 text-slate-500 truncate max-w-[200px]">{typeof e.details === 'object' ? JSON.stringify(e.details).substring(0, 80) : e.details || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {total > limit && (
        <div className="mt-3 flex items-center justify-center gap-3">
          <button onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0} className="rounded-lg border border-astra-border p-1.5 text-slate-400 disabled:opacity-30"><ChevronLeft className="h-3.5 w-3.5" /></button>
          <span className="text-xs text-slate-500">Page {page + 1} of {Math.ceil(total / limit)}</span>
          <button onClick={() => setPage(page + 1)} disabled={(page + 1) * limit >= total} className="rounded-lg border border-astra-border p-1.5 text-slate-400 disabled:opacity-30"><ChevronRight className="h-3.5 w-3.5" /></button>
        </div>
      )}
    </div>
  );
}
