'use client';

/**
 * ASTRA — Verification & Validation Dashboard
 * File: frontend/src/app/projects/[id]/verification/page.tsx
 */

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  Loader2, CheckSquare, AlertTriangle, Sparkles, Plus,
  RefreshCw, ChevronRight, FlaskConical, Eye, FileText,
  Search, Shield, CheckCircle, XCircle, Clock,
} from 'lucide-react';
import clsx from 'clsx';
import { requirementsAPI, projectsAPI } from '@/lib/api';
import api from '@/lib/api';
import { STATUS_COLORS, STATUS_LABELS, LEVEL_COLORS, type RequirementLevel, type RequirementStatus } from '@/lib/types';

let aiAPI: any = null;
try { aiAPI = require('@/lib/ai-api').aiAPI; } catch {}

const METHOD_ICONS: Record<string, any> = { test: FlaskConical, analysis: FileText, inspection: Eye, demonstration: Shield };
const METHOD_COLORS: Record<string, string> = { test: '#3B82F6', analysis: '#8B5CF6', inspection: '#F59E0B', demonstration: '#10B981' };
const STATUS_CFG: Record<string, { color: string; bg: string; icon: any }> = {
  planned: { color: '#6B7280', bg: '#6B728015', icon: Clock },
  in_progress: { color: '#F59E0B', bg: '#F59E0B15', icon: Loader2 },
  pass: { color: '#10B981', bg: '#10B98115', icon: CheckCircle },
  fail: { color: '#EF4444', bg: '#EF444415', icon: XCircle },
};

export default function VerificationPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);
  const p = `/projects/${projectId}`;

  const [requirements, setRequirements] = useState<any[]>([]);
  const [verifications, setVerifications] = useState<any[]>([]);
  const [projectCode, setProjectCode] = useState('');
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [showAddForm, setShowAddForm] = useState(false);

  // Add form state
  const [addReqId, setAddReqId] = useState<number | null>(null);
  const [addMethod, setAddMethod] = useState('test');
  const [addCriteria, setAddCriteria] = useState('');
  const [saving, setSaving] = useState(false);

  const fetchData = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [projRes, reqsRes] = await Promise.all([
        projectsAPI.get(projectId).catch(() => null),
        requirementsAPI.list(projectId, { limit: 1000 }),
      ]);
      const reqs = Array.isArray(reqsRes.data) ? reqsRes.data : [];
      setRequirements(reqs);
      setProjectCode(projRes?.data?.code || '');

      // Fetch verifications for all requirements
      const allVerifs: any[] = [];
      for (const req of reqs) {
        try {
          const vRes = await api.get('/requirements/' + req.id);
          if (vRes.data?.verifications) allVerifs.push(...vRes.data.verifications.map((v: any) => ({ ...v, req_id: req.req_id, req_title: req.title, req_level: req.level })));
        } catch {}
      }
      setVerifications(allVerifs);
    } catch {}
    setLoading(false);
  }, [projectId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleAdd = async () => {
    if (!addReqId) return;
    setSaving(true);
    try {
      await api.post('/requirements/' + addReqId + '/verifications', { requirement_id: addReqId, method: addMethod, criteria: addCriteria });
      setShowAddForm(false); setAddCriteria(''); setAddReqId(null);
      await fetchData();
    } catch {}
    setSaving(false);
  };

  // Stats
  const counts = { planned: 0, in_progress: 0, pass: 0, fail: 0 };
  verifications.forEach(v => { const s = v.status?.value || v.status || 'planned'; counts[s as keyof typeof counts] = (counts[s as keyof typeof counts] || 0) + 1; });
  const reqsWithoutVerif = requirements.filter(r => !verifications.some(v => v.requirement_id === r.id));

  // Filter
  const filtered = verifications.filter(v => {
    const s = v.status?.value || v.status || 'planned';
    if (statusFilter !== 'all' && s !== statusFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      if (!(v.req_id || '').toLowerCase().includes(q) && !(v.req_title || '').toLowerCase().includes(q) && !(v.criteria || '').toLowerCase().includes(q)) return false;
    }
    return true;
  });

  if (loading) return <div className="flex min-h-[60vh] items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-blue-500" /></div>;

  return (
    <div>
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Verification & Validation</h1>
          <p className="mt-0.5 text-sm text-slate-500">{projectCode} · V&V status and test mapping</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setShowAddForm(true)} className="flex items-center gap-1.5 rounded-lg bg-blue-500 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-600">
            <Plus className="h-3.5 w-3.5" /> Add Verification
          </button>
          <button onClick={fetchData} className="rounded-full border border-astra-border p-2 text-slate-400 hover:text-slate-200"><RefreshCw className="h-3.5 w-3.5" /></button>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 mb-6">
        {Object.entries(counts).map(([key, val]) => {
          const cfg = STATUS_CFG[key];
          const Icon = cfg?.icon || Clock;
          return (
            <button key={key} onClick={() => setStatusFilter(statusFilter === key ? 'all' : key)}
              className={clsx('rounded-xl border p-4 text-left transition', statusFilter === key ? 'border-blue-500/30 bg-blue-500/5' : 'border-astra-border bg-astra-surface hover:border-blue-500/20')}>
              <div className="flex items-center gap-2"><Icon className="h-4 w-4" style={{ color: cfg?.color }} /><span className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">{key.replace('_', ' ')}</span></div>
              <div className="mt-2 text-2xl font-bold" style={{ color: cfg?.color }}>{val}</div>
            </button>
          );
        })}
      </div>

      {/* Warning: reqs without verification */}
      {reqsWithoutVerif.length > 0 && (
        <div className="mb-4 flex items-center gap-3 rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3">
          <AlertTriangle className="h-4 w-4 text-amber-400 flex-shrink-0" />
          <span className="flex-1 text-xs text-amber-300">{reqsWithoutVerif.length} requirement{reqsWithoutVerif.length !== 1 ? 's' : ''} without verification assigned</span>
          <button onClick={() => router.push(`${p}/ai`)} className="flex items-center gap-1 text-[11px] font-semibold text-violet-400 hover:text-violet-300">
            <Sparkles className="h-3 w-3" /> Auto-suggest methods
          </button>
        </div>
      )}

      {/* Search + filter */}
      <div className="mb-4 flex items-center gap-3">
        <div className="flex flex-1 items-center gap-2 rounded-lg border border-astra-border bg-astra-surface px-3 py-2" style={{ maxWidth: 320 }}>
          <Search className="h-4 w-4 text-slate-500" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search verifications..." className="flex-1 bg-transparent text-[13px] text-slate-200 outline-none placeholder:text-slate-600" />
        </div>
        <span className="text-[11px] text-slate-500">{filtered.length} of {verifications.length} verifications</span>
      </div>

      {/* Verification table */}
      <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
        <div className="grid grid-cols-[100px_1fr_90px_80px_1fr_60px] border-b border-astra-border bg-astra-surface-alt px-4 py-2.5 text-[10px] font-bold uppercase tracking-wider text-slate-500">
          <span>Req ID</span><span>Title</span><span>Method</span><span>Status</span><span>Criteria</span><span></span>
        </div>
        {filtered.length === 0 ? (
          <div className="py-16 text-center text-sm text-slate-500">{verifications.length === 0 ? 'No verifications yet. Add one or use AI to auto-suggest.' : 'No matches for your filter.'}</div>
        ) : filtered.map((v, i) => {
          const method = v.method?.value || v.method || 'test';
          const status = v.status?.value || v.status || 'planned';
          const cfg = STATUS_CFG[status]; const mc = METHOD_COLORS[method] || '#6B7280';
          return (
            <div key={v.id || i} className="grid grid-cols-[100px_1fr_90px_80px_1fr_60px] items-center border-b border-astra-border/50 px-4 py-3 hover:bg-astra-surface-hover">
              <span className="font-mono text-xs font-semibold text-blue-400">{v.req_id}</span>
              <span className="text-xs text-slate-300 truncate pr-2">{v.req_title}</span>
              <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize" style={{ background: `${mc}20`, color: mc }}>{method}</span>
              <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize" style={{ background: cfg?.bg, color: cfg?.color }}>{status.replace('_', ' ')}</span>
              <span className="text-[11px] text-slate-400 truncate">{v.criteria || '—'}</span>
              <button onClick={() => router.push(`/requirements/${v.requirement_id}`)} className="text-slate-500 hover:text-blue-400"><ChevronRight className="h-3.5 w-3.5" /></button>
            </div>
          );
        })}
      </div>

      {/* Add Verification Modal */}
      {showAddForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-astra-border bg-astra-surface p-6 shadow-2xl">
            <h3 className="text-sm font-bold text-slate-100 mb-4">Add Verification</h3>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">Requirement</label>
                <select value={addReqId || ''} onChange={(e) => setAddReqId(Number(e.target.value))} className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-sm text-slate-200 outline-none">
                  <option value="">Select…</option>
                  {requirements.map(r => <option key={r.id} value={r.id}>{r.req_id} — {r.title}</option>)}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">Method</label>
                <div className="flex gap-2">
                  {['test', 'analysis', 'inspection', 'demonstration'].map(m => (
                    <button key={m} onClick={() => setAddMethod(m)} className={clsx('flex-1 rounded-lg py-2 text-[11px] font-bold capitalize transition', addMethod === m ? 'text-white' : 'border border-astra-border text-slate-400')} style={addMethod === m ? { background: METHOD_COLORS[m] } : {}}>{m}</button>
                  ))}
                </div>
              </div>
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">Pass/Fail Criteria</label>
                <textarea value={addCriteria} onChange={(e) => setAddCriteria(e.target.value)} rows={3} placeholder="Describe how to verify…" className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
              </div>
            </div>
            <div className="mt-4 flex justify-between">
              <button onClick={() => setShowAddForm(false)} className="rounded-lg border border-astra-border px-4 py-2 text-xs text-slate-400 hover:text-slate-200">Cancel</button>
              <button onClick={handleAdd} disabled={!addReqId || saving} className="rounded-lg bg-blue-500 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-600 disabled:opacity-50">{saving ? 'Saving…' : 'Add Verification'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
