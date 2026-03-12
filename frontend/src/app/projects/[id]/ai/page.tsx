'use client';

/**
 * ASTRA — AI Analysis Hub (Project-Scoped)
 * File: frontend/src/app/projects/[id]/ai/page.tsx
 */

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Sparkles, Loader2, RefreshCw, AlertTriangle, CheckCircle, XCircle, Clock, Network, Copy, FlaskConical, BarChart3, ChevronRight, Zap, Wand2 } from 'lucide-react';
import { projectsAPI } from '@/lib/api';

let aiAPI: any = null;
try { aiAPI = require('@/lib/ai-api').aiAPI; } catch {}

export default function AIHubPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);
  const p = `/projects/${projectId}`;

  const [projectCode, setProjectCode] = useState('');
  const [stats, setStats] = useState<any>(null);
  const [duplicates, setDuplicates] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [reindexing, setReindexing] = useState(false);
  const [scanningDups, setScanningDups] = useState(false);

  useEffect(() => {
    projectsAPI.get(projectId).then(r => setProjectCode(r.data?.code || '')).catch(() => {});
  }, [projectId]);

  const loadStats = useCallback(async () => {
    if (!aiAPI) { setLoading(false); return; }
    setLoading(true);
    try { const res = await aiAPI.getStats(projectId); setStats(res.data); } catch {}
    setLoading(false);
  }, [projectId]);

  useEffect(() => { loadStats(); }, [loadStats]);

  const scanDuplicates = async () => {
    if (!aiAPI) return;
    setScanningDups(true);
    try { const res = await aiAPI.getDuplicates(projectId); setDuplicates(res.data); } catch {}
    setScanningDups(false);
  };

  const handleReindex = async () => {
    if (!aiAPI) return;
    setReindexing(true);
    try { await aiAPI.reindex(projectId, false); await loadStats(); } catch {}
    setReindexing(false);
  };

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-500">
              <Sparkles className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">AI Analysis Hub</h1>
              <p className="text-xs text-slate-400">{projectCode} · Semantic analysis, duplicates, and suggestions</p>
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={handleReindex} disabled={reindexing} className="flex items-center gap-1.5 rounded-lg border border-violet-500/30 bg-violet-500/10 px-3 py-1.5 text-xs font-semibold text-violet-400 hover:bg-violet-500/20 disabled:opacity-50">
            {reindexing ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />} {reindexing ? 'Indexing…' : 'Reindex'}
          </button>
        </div>
      </div>

      {!aiAPI && (
        <div className="mb-6 rounded-xl border border-amber-500/20 bg-amber-500/5 px-5 py-4">
          <div className="flex items-center gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-400" />
            <div>
              <h3 className="text-sm font-semibold text-amber-300">Embedding Provider Not Configured</h3>
              <p className="mt-0.5 text-xs text-amber-400/70">Set EMBEDDING_PROVIDER in your .env file to enable AI features.</p>
            </div>
          </div>
        </div>
      )}

      {loading ? <div className="flex items-center justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-violet-400" /></div> : (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {/* Stats cards */}
          {stats && (
            <>
              <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
                <h3 className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-2">Embeddings</h3>
                <div className="text-2xl font-bold text-violet-400">{stats.total_embeddings}</div>
                <div className="text-[10px] text-slate-500 mt-1">Provider: {stats.embedding_provider || 'none'}</div>
              </div>
              <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
                <h3 className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-2">Suggestions</h3>
                <div className="text-2xl font-bold text-blue-400">{stats.total_suggestions}</div>
                <div className="flex gap-3 mt-1 text-[10px]">
                  <span className="text-emerald-400">{stats.accepted_suggestions} accepted</span>
                  <span className="text-red-400">{stats.rejected_suggestions} rejected</span>
                  <span className="text-amber-400">{stats.pending_suggestions} pending</span>
                </div>
              </div>
              <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
                <h3 className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-2">Acceptance Rate</h3>
                <div className="text-2xl font-bold text-emerald-400">{stats.acceptance_rate}%</div>
              </div>
            </>
          )}

          {/* Action cards */}
          <button onClick={scanDuplicates} disabled={scanningDups}
            className="rounded-xl border border-astra-border bg-astra-surface p-5 text-left transition hover:border-violet-500/30">
            <div className="flex items-center gap-2 mb-2"><Copy className="h-4 w-4 text-amber-400" /><h3 className="text-sm font-bold text-slate-200">Scan Duplicates</h3></div>
            <p className="text-xs text-slate-500">Find near-duplicate requirements using semantic similarity.</p>
            {scanningDups && <Loader2 className="mt-2 h-4 w-4 animate-spin text-violet-400" />}
          </button>

          <button onClick={() => router.push(`${p}/traceability`)}
            className="rounded-xl border border-astra-border bg-astra-surface p-5 text-left transition hover:border-blue-500/30">
            <div className="flex items-center gap-2 mb-2"><Network className="h-4 w-4 text-blue-400" /><h3 className="text-sm font-bold text-slate-200">Trace Suggestions</h3></div>
            <p className="text-xs text-slate-500">View AI-suggested trace links on the Traceability page.</p>
          </button>

          <button onClick={() => router.push(`${p}/verification`)}
            className="rounded-xl border border-astra-border bg-astra-surface p-5 text-left transition hover:border-emerald-500/30">
            <div className="flex items-center gap-2 mb-2"><FlaskConical className="h-4 w-4 text-emerald-400" /><h3 className="text-sm font-bold text-slate-200">Verification Methods</h3></div>
            <p className="text-xs text-slate-500">AI can suggest test/analysis/inspection/demonstration methods for unverified requirements.</p>
          </button>
        </div>
      )}

      {/* Duplicate results */}
      {duplicates && (
        <div className="mt-6 rounded-xl border border-astra-border bg-astra-surface p-5">
          <h3 className="text-sm font-bold text-slate-200 mb-3">Duplicate Groups ({duplicates.duplicate_groups?.length || 0})</h3>
          {(duplicates.duplicate_groups || []).length === 0 ? (
            <p className="text-xs text-slate-500">No duplicates found. Your requirements are distinct.</p>
          ) : (
            <div className="space-y-3">
              {duplicates.duplicate_groups.map((group: any, gi: number) => (
                <div key={gi} className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                  <div className="text-[10px] font-semibold text-amber-400 mb-2">Group {gi + 1} · {(group.max_similarity * 100).toFixed(0)}% similarity</div>
                  {group.requirements?.map((r: any, ri: number) => (
                    <div key={ri} className="flex items-center gap-2 text-xs py-1">
                      <span className="font-mono text-blue-400">{r.req_id}</span>
                      <span className="flex-1 truncate text-slate-300">{r.title || r.statement?.substring(0, 60)}</span>
                      <span className="text-amber-400">{(r.similarity_score * 100).toFixed(0)}%</span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
