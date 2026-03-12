'use client';

/**
 * ASTRA — Impact Analysis Page
 * File: frontend/src/app/projects/[id]/impact/page.tsx
 */

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Loader2, Zap, AlertTriangle, CheckCircle, XCircle, ChevronRight, RefreshCw, Search, Network } from 'lucide-react';
import clsx from 'clsx';
import { requirementsAPI, projectsAPI } from '@/lib/api';
import api from '@/lib/api';

const RISK_COLORS: Record<string, { color: string; bg: string }> = {
  low: { color: '#10B981', bg: '#10B98115' },
  medium: { color: '#F59E0B', bg: '#F59E0B15' },
  high: { color: '#EF4444', bg: '#EF444415' },
  critical: { color: '#DC2626', bg: '#DC262615' },
};

export default function ImpactAnalysisPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);

  const [projectCode, setProjectCode] = useState('');
  const [requirements, setRequirements] = useState<any[]>([]);
  const [highImpact, setHighImpact] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedReqId, setSelectedReqId] = useState<number | null>(null);
  const [changeDesc, setChangeDesc] = useState('');
  const [report, setReport] = useState<any>(null);
  const [analyzing, setAnalyzing] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    setLoading(true);
    Promise.all([
      projectsAPI.get(projectId).catch(() => null),
      requirementsAPI.list(projectId, { limit: 200 }),
      api.get('/impact/project-risk', { params: { project_id: projectId } }).catch(() => null),
    ]).then(([projRes, reqsRes, riskRes]) => {
      setProjectCode(projRes?.data?.code || '');
      setRequirements(Array.isArray(reqsRes?.data) ? reqsRes.data : []);
      setHighImpact(riskRes?.data?.high_impact_requirements || []);
    }).catch(() => {}).finally(() => setLoading(false));
  }, [projectId]);

  const runAnalysis = async () => {
    if (!selectedReqId) return;
    setAnalyzing(true); setReport(null);
    try {
      const res = await api.get('/impact/analyze', { params: { requirement_id: selectedReqId, change_description: changeDesc || 'General change analysis' } });
      setReport(res.data);
    } catch {}
    setAnalyzing(false);
  };

  if (loading) return <div className="flex min-h-[60vh] items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-blue-500" /></div>;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-bold tracking-tight">Impact Analysis</h1>
        <p className="mt-0.5 text-sm text-slate-500">{projectCode} · Dependency exploration and what-if analysis</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2 mb-6">
        {/* High-Impact Requirements */}
        <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
          <h3 className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            <Zap className="h-3.5 w-3.5 text-amber-400" /> High-Impact Requirements
          </h3>
          {highImpact.length > 0 ? (
            <div className="space-y-2">
              {highImpact.slice(0, 10).map((item: any) => (
                <button key={item.requirement_id || item.id} onClick={() => { setSelectedReqId(item.requirement_id || item.id); }}
                  className="flex w-full items-center gap-3 rounded-lg p-2.5 text-left transition hover:bg-astra-surface-hover">
                  <span className="font-mono text-xs font-semibold text-blue-400">{item.req_id}</span>
                  <span className="flex-1 truncate text-xs text-slate-300">{item.title}</span>
                  <span className="text-xs font-semibold text-amber-400">fan-out: {item.fan_out || item.downstream_count || '?'}</span>
                </button>
              ))}
            </div>
          ) : (
            <p className="py-4 text-center text-xs text-slate-500">No high-impact data available. Run analysis on specific requirements.</p>
          )}
        </div>

        {/* Run Analysis */}
        <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
          <h3 className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            <Network className="h-3.5 w-3.5 text-blue-400" /> Run Impact Analysis
          </h3>
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">Requirement</label>
              <select value={selectedReqId || ''} onChange={(e) => setSelectedReqId(Number(e.target.value))}
                className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-sm text-slate-200 outline-none">
                <option value="">Select requirement…</option>
                {requirements.map(r => <option key={r.id} value={r.id}>{r.req_id} — {r.title}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">Change Description</label>
              <input value={changeDesc} onChange={(e) => setChangeDesc(e.target.value)} placeholder="Describe the proposed change…"
                className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <button onClick={runAnalysis} disabled={!selectedReqId || analyzing}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-500 py-2.5 text-xs font-semibold text-white hover:bg-blue-600 disabled:opacity-50">
              {analyzing ? <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Analyzing…</> : <><Zap className="h-3.5 w-3.5" /> Analyze Impact</>}
            </button>
          </div>
        </div>
      </div>

      {/* Results */}
      {report && (
        <div className="rounded-xl border border-astra-border bg-astra-surface p-5 space-y-4">
          <div className="flex items-center gap-3">
            <span className={clsx('rounded-full px-3 py-1 text-xs font-bold')} style={{ background: RISK_COLORS[report.risk_level]?.bg, color: RISK_COLORS[report.risk_level]?.color }}>
              {report.risk_level?.toUpperCase()} RISK
            </span>
            <span className="text-xs text-slate-400">{report.total_direct || 0} direct · {report.total_indirect || 0} indirect · {report.total_affected || 0} total affected</span>
          </div>
          {report.ai_summary && <p className="text-xs text-slate-300 leading-relaxed">{report.ai_summary}</p>}
          {report.risk_factors?.length > 0 && (
            <div>
              <h4 className="text-[10px] font-semibold uppercase text-slate-500 mb-1">Risk Factors</h4>
              {report.risk_factors.map((f: string, i: number) => (
                <div key={i} className="flex items-start gap-2 text-xs text-amber-300"><AlertTriangle className="h-3 w-3 mt-0.5 flex-shrink-0" /> {f}</div>
              ))}
            </div>
          )}
          {report.direct_impacts?.length > 0 && (
            <div>
              <h4 className="text-[10px] font-semibold uppercase text-slate-500 mb-1">Direct Impacts ({report.direct_impacts.length})</h4>
              <div className="space-y-1">{report.direct_impacts.map((imp: any, i: number) => (
                <div key={i} className="flex items-center gap-2 text-xs text-slate-300">
                  <div className="h-1.5 w-1.5 rounded-full bg-red-400" />
                  <span className="font-mono text-blue-400">{imp.entity_identifier}</span> — {imp.entity_title || imp.impact_description || imp.entity_type}
                </div>
              ))}</div>
            </div>
          )}
          {report.affected_verifications?.length > 0 && (
            <div>
              <h4 className="text-[10px] font-semibold uppercase text-slate-500 mb-1">Affected Verifications ({report.affected_verifications.length})</h4>
              <div className="space-y-1">{report.affected_verifications.map((v: any, i: number) => (
                <div key={i} className="flex items-center gap-2 text-xs text-slate-300">
                  <div className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                  {v.requirement_identifier} ({v.method}) — {v.needs_rerun ? 'Needs re-run' : v.current_status}
                </div>
              ))}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
