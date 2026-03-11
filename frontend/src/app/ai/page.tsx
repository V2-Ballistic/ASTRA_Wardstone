/**
 * ASTRA — AI Analytics Dashboard
 * =================================
 * File: frontend/src/app/ai/page.tsx   ← NEW
 *
 * Dashboard showing:
 *   - AI suggestion acceptance rate over time
 *   - Duplicate groups visualization
 *   - Pending suggestions bulk management
 *   - Embedding coverage stats
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Sparkles, Loader2, RefreshCw, AlertTriangle, CheckCircle,
  XCircle, Clock, Network, Copy, FlaskConical, BarChart3,
  ArrowRight, ChevronRight, Zap,
} from 'lucide-react';
import { aiAPI, type AIStats, type DuplicateGroup, type ProjectDuplicatesResponse } from '@/lib/ai-api';
import { projectsAPI } from '@/lib/api';

export default function AIAnalyticsPage() {
  const [stats, setStats] = useState<AIStats | null>(null);
  const [duplicates, setDuplicates] = useState<ProjectDuplicatesResponse | null>(null);
  const [projects, setProjects] = useState<any[]>([]);
  const [selectedProject, setSelectedProject] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [reindexing, setReindexing] = useState(false);
  const [scanningDups, setScanningDups] = useState(false);
  const [error, setError] = useState('');

  // Load projects
  useEffect(() => {
    projectsAPI.list().then((res) => {
      setProjects(res.data);
      if (res.data.length > 0) {
        setSelectedProject(res.data[0].id);
      }
    }).catch(() => {});
  }, []);

  // Load stats
  const loadStats = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    try {
      const res = await aiAPI.getStats(selectedProject);
      setStats(res.data);
    } catch {
      setError('Failed to load AI stats');
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => { loadStats(); }, [loadStats]);

  // Scan duplicates
  const scanDuplicates = async () => {
    if (!selectedProject) return;
    setScanningDups(true);
    try {
      const res = await aiAPI.getDuplicates(selectedProject);
      setDuplicates(res.data);
    } catch {
      setError('Duplicate scan failed');
    } finally {
      setScanningDups(false);
    }
  };

  // Reindex
  const handleReindex = async () => {
    if (!selectedProject) return;
    setReindexing(true);
    try {
      await aiAPI.reindex(selectedProject, false);
      await loadStats();
    } catch {
      setError('Reindex failed');
    } finally {
      setReindexing(false);
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-500">
            <Sparkles className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">AI Semantic Analysis</h1>
            <p className="text-xs text-slate-400">
              Embedding-based duplicate detection, trace suggestions & verification
            </p>
          </div>
        </div>

        {/* Project selector */}
        <div className="flex items-center gap-3">
          <select
            value={selectedProject || ''}
            onChange={(e) => setSelectedProject(Number(e.target.value))}
            className="rounded-lg border border-astra-border bg-astra-surface px-3 py-1.5 text-sm text-slate-200"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          <button
            onClick={handleReindex}
            disabled={reindexing}
            className="flex items-center gap-1.5 rounded-lg border border-violet-500/30 bg-violet-500/10 px-3 py-1.5 text-xs font-semibold text-violet-400 transition hover:bg-violet-500/20 disabled:opacity-50"
          >
            {reindexing ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
            {reindexing ? 'Indexing…' : 'Reindex'}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-2 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* AI Status Banner */}
      {stats && !stats.ai_available && (
        <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 px-5 py-4">
          <div className="flex items-center gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-400" />
            <div>
              <h3 className="text-sm font-semibold text-amber-300">Embedding Provider Not Configured</h3>
              <p className="mt-0.5 text-xs text-amber-400/70">
                Set <code className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px]">EMBEDDING_PROVIDER=local</code> or
                <code className="ml-1 rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px]">EMBEDDING_PROVIDER=openai</code> to enable
                semantic analysis features.
              </p>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-violet-400" />
        </div>
      ) : stats ? (
        <>
          {/* Stats Cards */}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard
              icon={<Zap className="h-4 w-4 text-violet-400" />}
              label="Embeddings"
              value={stats.total_embeddings}
              sub={stats.model_version || 'none'}
            />
            <StatCard
              icon={<Sparkles className="h-4 w-4 text-blue-400" />}
              label="Total Suggestions"
              value={stats.total_suggestions}
              sub={`${stats.pending_suggestions} pending`}
            />
            <StatCard
              icon={<CheckCircle className="h-4 w-4 text-emerald-400" />}
              label="Accepted"
              value={stats.accepted_suggestions}
              sub={`${stats.acceptance_rate}% rate`}
            />
            <StatCard
              icon={<XCircle className="h-4 w-4 text-red-400" />}
              label="Rejected"
              value={stats.rejected_suggestions}
              sub={`of ${stats.accepted_suggestions + stats.rejected_suggestions} resolved`}
            />
          </div>

          {/* Suggestion Breakdown */}
          <div className="grid gap-4 md:grid-cols-2">
            {/* By Type */}
            <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
              <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-200">
                <BarChart3 className="h-4 w-4 text-blue-400" />
                Suggestions by Type
              </h3>
              <div className="space-y-3">
                {Object.entries(stats.suggestions_by_type).map(([type, count]) => (
                  <SuggestionBar key={type} type={type} count={count} total={stats.total_suggestions} />
                ))}
                {Object.keys(stats.suggestions_by_type).length === 0 && (
                  <p className="text-xs text-slate-500">No suggestions generated yet.</p>
                )}
              </div>
            </div>

            {/* Acceptance Ring */}
            <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
              <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-200">
                <CheckCircle className="h-4 w-4 text-emerald-400" />
                Acceptance Rate
              </h3>
              <div className="flex items-center justify-center py-4">
                <AcceptanceRing rate={stats.acceptance_rate} />
              </div>
              <p className="text-center text-xs text-slate-500">
                {stats.accepted_suggestions} accepted / {stats.rejected_suggestions} rejected
              </p>
            </div>
          </div>

          {/* Duplicate Scanner */}
          <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-200">
                <Copy className="h-4 w-4 text-amber-400" />
                Duplicate Detection
              </h3>
              <button
                onClick={scanDuplicates}
                disabled={scanningDups || !stats.ai_available}
                className="flex items-center gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs font-semibold text-amber-400 transition hover:bg-amber-500/20 disabled:opacity-50"
              >
                {scanningDups ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                {scanningDups ? 'Scanning…' : 'Scan for Duplicates'}
              </button>
            </div>

            {duplicates ? (
              duplicates.duplicate_groups.length === 0 ? (
                <div className="flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-4 py-3">
                  <CheckCircle className="h-4 w-4 text-emerald-400" />
                  <span className="text-sm text-emerald-300">
                    No duplicates found across {duplicates.total_requirements} requirements
                    (threshold: {Math.round(duplicates.threshold * 100)}%)
                  </span>
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-xs text-slate-400">
                    Found {duplicates.duplicate_groups.length} duplicate group{duplicates.duplicate_groups.length !== 1 ? 's' : ''} across{' '}
                    {duplicates.total_requirements} requirements
                  </p>
                  {duplicates.duplicate_groups.map((group) => (
                    <DuplicateGroupCard key={group.group_id} group={group} />
                  ))}
                </div>
              )
            ) : (
              <p className="text-xs text-slate-500">
                Click "Scan for Duplicates" to analyze all requirements in this project.
              </p>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}


// ── Sub-components ──

function StatCard({ icon, label, value, sub }: {
  icon: React.ReactNode; label: string; value: number; sub: string;
}) {
  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
      <div className="flex items-center gap-2">
        {icon}
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{label}</span>
      </div>
      <div className="mt-2 text-2xl font-bold text-white">{value.toLocaleString()}</div>
      <div className="mt-0.5 text-[11px] text-slate-500">{sub}</div>
    </div>
  );
}

function SuggestionBar({ type, count, total }: { type: string; count: number; total: number }) {
  const pct = total > 0 ? (count / total) * 100 : 0;
  const labels: Record<string, string> = {
    duplicate: 'Duplicates',
    trace_link: 'Trace Links',
    verification: 'Verification',
  };
  const colors: Record<string, string> = {
    duplicate: 'bg-amber-500',
    trace_link: 'bg-violet-500',
    verification: 'bg-emerald-500',
  };
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-slate-300">{labels[type] || type}</span>
        <span className="font-mono text-slate-400">{count}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-700/40">
        <div
          className={`h-full rounded-full transition-all ${colors[type] || 'bg-blue-500'}`}
          style={{ width: `${Math.max(pct, 2)}%` }}
        />
      </div>
    </div>
  );
}

function AcceptanceRing({ rate }: { rate: number }) {
  const radius = 50;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (rate / 100) * circumference;
  const color = rate >= 70 ? '#10B981' : rate >= 40 ? '#F59E0B' : '#EF4444';

  return (
    <div className="relative" style={{ width: 130, height: 130 }}>
      <svg width={130} height={130} className="-rotate-90">
        <circle cx={65} cy={65} r={radius} fill="none" stroke="rgba(100,116,139,0.15)" strokeWidth={8} />
        <circle
          cx={65} cy={65} r={radius} fill="none" stroke={color}
          strokeWidth={8} strokeDasharray={circumference} strokeDashoffset={offset}
          strokeLinecap="round" className="transition-all duration-700"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-bold" style={{ color }}>{rate}%</span>
        <span className="text-[10px] text-slate-500">acceptance</span>
      </div>
    </div>
  );
}

function DuplicateGroupCard({ group }: { group: DuplicateGroup }) {
  return (
    <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
      <div className="mb-2 flex items-center gap-2 text-xs">
        <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
        <span className="font-semibold text-amber-300">
          Group #{group.group_id}
        </span>
        <span className="text-amber-400/70">
          — {group.requirements.length} requirements, max similarity {Math.round(group.max_similarity * 100)}%
        </span>
      </div>
      <div className="space-y-1.5">
        {group.requirements.map((req) => (
          <div key={req.requirement_id} className="flex items-center gap-2 text-[11px]">
            <span className="font-mono font-semibold text-blue-400">{req.req_id}</span>
            <ArrowRight className="h-3 w-3 text-slate-600" />
            <span className="truncate text-slate-400">{req.statement}</span>
            <span className="shrink-0 rounded-full bg-amber-500/15 px-1.5 py-0 text-[9px] font-bold text-amber-400">
              {Math.round(req.similarity_score * 100)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
