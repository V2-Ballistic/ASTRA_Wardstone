'use client';

/**
 * ASTRA — Project Dashboard (Command Center) — Polished
 * ========================================================
 * File: frontend/src/app/projects/[id]/page.tsx
 *
 * Polish items:
 *   - Level bars use by_level from dashboard stats API (not client-side)
 *   - Coverage bars with threshold coloring (green/yellow/red) + animation
 *   - Stat cards with sub-labels and click navigation
 *   - Quality histogram with 5 buckets (0-20, 20-40, 40-60, 60-80, 80-100)
 *   - Recent activity with relative timestamps, user initials, action colors
 */

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  Loader2, LayoutDashboard, Database, FileText, CheckCircle,
  AlertTriangle, Network, Sparkles, Plus, Archive, FileBarChart,
  ChevronRight, Clock, Shield, RefreshCw, Zap, Settings,
  CheckSquare, Circle, Search, Copy, Eye,
} from 'lucide-react';
import clsx from 'clsx';
import { projectsAPI, dashboardAPI, traceabilityAPI, requirementsAPI, devAPI, baselinesAPI } from '@/lib/api';
import {
  LEVEL_COLORS, LEVEL_LABELS, STATUS_COLORS, STATUS_LABELS,
  type RequirementLevel, type RequirementStatus,
} from '@/lib/types';

// Optional AI API
let aiAPI: any = null;
try { aiAPI = require('@/lib/ai-api').aiAPI; } catch {}

// ══════════════════════════════════════
//  Helpers
// ══════════════════════════════════════

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const now = Date.now();
  const then = new Date(iso).getTime();
  const diff = now - then;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function coverageColor(pct: number): string {
  if (pct >= 80) return '#10B981';
  if (pct >= 50) return '#F59E0B';
  return '#EF4444';
}

function userInitials(name: string | null | undefined): string {
  if (!name || name === 'System') return 'SY';
  return name.split(' ').map((w) => w[0]).join('').toUpperCase().slice(0, 2);
}

const ACTION_COLORS: Record<string, { color: string; bg: string; label: string }> = {
  created: { color: '#10B981', bg: '#10B98118', label: 'Created' },
  status: { color: '#3B82F6', bg: '#3B82F618', label: 'Updated' },
  updated: { color: '#3B82F6', bg: '#3B82F618', label: 'Updated' },
  deleted: { color: '#EF4444', bg: '#EF444418', label: 'Deleted' },
  title: { color: '#8B5CF6', bg: '#8B5CF618', label: 'Renamed' },
  statement: { color: '#F59E0B', bg: '#F59E0B18', label: 'Edited' },
  quality_score: { color: '#06B6D4', bg: '#06B6D418', label: 'Scored' },
};

// ══════════════════════════════════════
//  Sub-components
// ══════════════════════════════════════

function StatCard({ label, value, icon: Icon, color, sub, onClick }: {
  label: string; value: string | number; icon: any; color: string;
  sub?: string; onClick?: () => void;
}) {
  const Wrapper = onClick ? 'button' : 'div';
  return (
    <Wrapper
      onClick={onClick}
      className={clsx(
        'rounded-xl border border-astra-border bg-astra-surface p-4 text-left transition',
        onClick && 'hover:border-blue-500/30 hover:shadow-lg hover:shadow-blue-500/5 cursor-pointer'
      )}
    >
      <div className="flex items-center gap-2 text-slate-500">
        <Icon className="h-4 w-4" style={{ color }} />
        <span className="text-[10px] font-semibold uppercase tracking-widest">{label}</span>
      </div>
      <div className="mt-2 text-2xl font-bold" style={{ color }}>{value}</div>
      {sub && <div className="mt-0.5 text-[10px] text-slate-500">{sub}</div>}
    </Wrapper>
  );
}

function LevelBar({ level, count, total }: {
  level: RequirementLevel; count: number; total: number;
}) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  const color = LEVEL_COLORS[level];
  const label = LEVEL_LABELS[level];
  return (
    <div className="flex items-center gap-3">
      <span className="w-6 text-right text-xs font-bold" style={{ color }}>{level}</span>
      <div className="flex-1">
        <div className="h-4 overflow-hidden rounded-full bg-astra-surface-alt">
          <div
            className="h-full rounded-full transition-all duration-700 ease-out"
            style={{ width: `${Math.max(pct, count > 0 ? 3 : 0)}%`, background: color }}
          />
        </div>
      </div>
      <span className="w-8 text-right text-xs font-semibold text-slate-300">{count}</span>
      <span className="w-20 text-right text-[10px] text-slate-500">{pct}% · {label.split('—')[1]?.trim()}</span>
    </div>
  );
}

function CoverageRow({ label, pct, color }: {
  label: string; pct: number; color?: string;
}) {
  const barColor = color || coverageColor(pct);
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[11px] text-slate-400">{label}</span>
        <span className="text-[11px] font-bold" style={{ color: barColor }}>{pct.toFixed(0)}%</span>
      </div>
      <div className="h-2.5 overflow-hidden rounded-full bg-astra-surface-alt">
        <div
          className="h-full rounded-full transition-all duration-1000 ease-out"
          style={{ width: `${Math.min(pct, 100)}%`, background: barColor }}
        />
      </div>
    </div>
  );
}

function QualityRing({ score, size = 100 }: { score: number; size?: number }) {
  const r = (size - 12) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;
  const color = score >= 80 ? '#10B981' : score >= 60 ? '#F59E0B' : '#EF4444';
  return (
    <div className="relative flex-shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#1E293B" strokeWidth={6} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={6}
          strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
          className="transition-all duration-1000 ease-out"
          transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-lg font-bold" style={{ color }}>{score.toFixed(0)}</span>
        <span className="text-[9px] text-slate-500">avg</span>
      </div>
    </div>
  );
}

function QualityHistogram({ scores }: { scores: number[] }) {
  const buckets = [
    { label: '0–20', min: 0, max: 20, color: '#EF4444' },
    { label: '20–40', min: 20, max: 40, color: '#F97316' },
    { label: '40–60', min: 40, max: 60, color: '#F59E0B' },
    { label: '60–80', min: 60, max: 80, color: '#3B82F6' },
    { label: '80–100', min: 80, max: 101, color: '#10B981' },
  ];
  const counts = buckets.map((b) => scores.filter((s) => s >= b.min && s < b.max).length);
  const maxCount = Math.max(...counts, 1);

  return (
    <div className="flex items-end gap-1.5" style={{ height: 64 }}>
      {buckets.map((b, i) => (
        <div key={b.label} className="flex flex-1 flex-col items-center gap-1">
          <span className="text-[9px] font-bold text-slate-400">{counts[i]}</span>
          <div
            className="w-full rounded-t-sm transition-all duration-700 ease-out"
            style={{
              height: `${Math.max((counts[i] / maxCount) * 48, counts[i] > 0 ? 4 : 0)}px`,
              background: b.color,
              opacity: counts[i] > 0 ? 1 : 0.2,
            }}
          />
          <span className="text-[8px] text-slate-600">{b.label}</span>
        </div>
      ))}
    </div>
  );
}

function ActivityItem({ item }: { item: any }) {
  const field = item.field || 'updated';
  const actionCfg = ACTION_COLORS[field] || ACTION_COLORS['updated'];
  const initials = userInitials(item.user);

  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-astra-border/50 last:border-0">
      {/* User avatar */}
      <div
        className="mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full text-[9px] font-bold"
        style={{ background: `${actionCfg.color}18`, color: actionCfg.color }}
      >
        {initials}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs text-slate-300">
          <span className="font-mono text-blue-400">{item.req_id}</span>
          {' '}
          <span
            className="rounded-full px-1.5 py-0.5 text-[9px] font-semibold"
            style={{ background: actionCfg.bg, color: actionCfg.color }}
          >
            {actionCfg.label}
          </span>
          {' '}
          <span className="text-slate-400">{item.description}</span>
        </p>
        <p className="mt-0.5 text-[10px] text-slate-600">
          {item.user} · {relativeTime(item.timestamp)}
        </p>
      </div>
    </div>
  );
}

function AIInsightsCard({ projectId, aiStats, onNavigate }: {
  projectId: number; aiStats: any; onNavigate: (path: string) => void;
}) {
  const dupCount = aiStats?.suggestions_by_type?.duplicate || 0;
  const traceCount = aiStats?.suggestions_by_type?.trace_link || 0;
  const pendingCount = aiStats?.pending_suggestions || 0;

  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
      <h3 className="mb-4 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        <Sparkles className="h-3.5 w-3.5 text-violet-400" />
        AI Insights
      </h3>

      {aiStats && (dupCount > 0 || traceCount > 0 || pendingCount > 0) ? (
        <div className="space-y-2">
          {dupCount > 0 && (
            <button onClick={() => onNavigate(`/projects/${projectId}/ai`)}
              className="flex w-full items-center gap-3 rounded-lg p-2 text-left transition hover:bg-astra-surface-hover">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-500/10">
                <Copy className="h-4 w-4 text-amber-400" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-semibold text-slate-200">{dupCount} duplicate{dupCount !== 1 ? 's' : ''}</div>
                <div className="text-[10px] text-slate-500">Potential redundancies detected</div>
              </div>
              <ChevronRight className="h-3.5 w-3.5 text-slate-600" />
            </button>
          )}
          {traceCount > 0 && (
            <button onClick={() => onNavigate(`/projects/${projectId}/traceability`)}
              className="flex w-full items-center gap-3 rounded-lg p-2 text-left transition hover:bg-astra-surface-hover">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500/10">
                <Network className="h-4 w-4 text-blue-400" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-semibold text-slate-200">{traceCount} trace suggestion{traceCount !== 1 ? 's' : ''}</div>
                <div className="text-[10px] text-slate-500">Missing links identified by AI</div>
              </div>
              <ChevronRight className="h-3.5 w-3.5 text-slate-600" />
            </button>
          )}
          {pendingCount > 0 && pendingCount !== traceCount && (
            <button onClick={() => onNavigate(`/projects/${projectId}/ai`)}
              className="flex w-full items-center gap-3 rounded-lg p-2 text-left transition hover:bg-astra-surface-hover">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-500/10">
                <Eye className="h-4 w-4 text-violet-400" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-semibold text-slate-200">{pendingCount} pending suggestion{pendingCount !== 1 ? 's' : ''}</div>
                <div className="text-[10px] text-slate-500">Awaiting review</div>
              </div>
              <ChevronRight className="h-3.5 w-3.5 text-slate-600" />
            </button>
          )}
        </div>
      ) : (
        <div className="py-3 text-center text-xs text-slate-500">
          No AI insights yet. Run analysis from the AI tools page.
        </div>
      )}

      <button onClick={() => onNavigate(`/projects/${projectId}/ai`)}
        className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg border border-violet-500/20 bg-violet-500/5 py-2 text-[11px] font-semibold text-violet-400 transition hover:bg-violet-500/10">
        View All AI Tools <ChevronRight className="h-3 w-3" />
      </button>
    </div>
  );
}

function OnboardingChecklist({ checks }: { checks: { label: string; done: boolean; href?: string }[] }) {
  const completed = checks.filter((c) => c.done).length;
  const router = useRouter();

  return (
    <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 p-5">
      <div className="flex items-center gap-2 mb-3">
        <Sparkles className="h-4 w-4 text-blue-400" />
        <h3 className="text-sm font-bold text-slate-200">Getting Started</h3>
        <span className="ml-auto text-[10px] font-semibold text-blue-400">
          {completed}/{checks.length} complete
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-astra-surface-alt mb-4">
        <div className="h-full rounded-full bg-blue-500 transition-all duration-500"
          style={{ width: `${(completed / checks.length) * 100}%` }} />
      </div>
      <div className="space-y-2">
        {checks.map((check) => (
          <button key={check.label}
            onClick={() => check.href && router.push(check.href)}
            className={clsx(
              'flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-xs transition',
              check.done ? 'text-slate-500' : 'text-slate-300 hover:bg-astra-surface-hover'
            )}>
            {check.done
              ? <CheckCircle className="h-4 w-4 text-emerald-400 flex-shrink-0" />
              : <Circle className="h-4 w-4 text-slate-600 flex-shrink-0" />}
            <span className={check.done ? 'line-through' : 'font-medium'}>{check.label}</span>
            {!check.done && check.href && <ChevronRight className="h-3 w-3 ml-auto text-slate-600" />}
          </button>
        ))}
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  Main Page
// ══════════════════════════════════════

export default function ProjectDashboard() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);

  const [project, setProject] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [coverage, setCoverage] = useState<any>(null);
  const [requirements, setRequirements] = useState<any[]>([]);
  const [baselines, setBaselines] = useState<any[]>([]);
  const [aiStats, setAiStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [seeding, setSeeding] = useState(false);
  const [seedResult, setSeedResult] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError('');
    try {
      const [projRes, statsRes, covRes, reqsRes, blRes] = await Promise.all([
        projectsAPI.get(projectId).catch(() => null),
        dashboardAPI.getStats(projectId).catch(() => null),
        traceabilityAPI.getCoverage(projectId).catch(() => null),
        requirementsAPI.list(projectId, { limit: 200 }).catch(() => null),
        baselinesAPI.list(projectId).catch(() => null),
      ]);
      setProject(projRes?.data || null);
      setStats(statsRes?.data || null);
      setCoverage(covRes?.data || null);
      setRequirements(Array.isArray(reqsRes?.data) ? reqsRes.data : []);
      setBaselines(blRes?.data?.baselines || blRes?.data || []);

      if (aiAPI) {
        aiAPI.getStats(projectId)
          .then((res: any) => setAiStats(res.data))
          .catch(() => setAiStats(null));
      }
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Failed to load dashboard');
    }
    setLoading(false);
  }, [projectId]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleSeed = async () => {
    setSeeding(true);
    setSeedResult(null);
    try {
      const res = await devAPI.seedProject(projectId);
      setSeedResult(
        `Seeded: ${res.data.requirements_created} requirements, ` +
        `${res.data.trace_links_created} trace links, ` +
        `${res.data.verifications_created} verifications`
      );
      await fetchAll();
    } catch (e: any) {
      setSeedResult(e.response?.data?.detail || e.response?.data?.status || 'Seed failed');
    }
    setSeeding(false);
  };

  // ── Derived data ──
  // Use by_level from stats API if available, else compute client-side
  const byLevel: Record<string, number> = stats?.by_level || {};
  if (!stats?.by_level) {
    requirements.forEach((r: any) => {
      const lv = r.level?.value || r.level || 'L1';
      byLevel[lv] = (byLevel[lv] || 0) + 1;
    });
  }

  const qualityScores = requirements.map((r: any) => r.quality_score || 0).filter((s: number) => s > 0);
  const qualityMin = qualityScores.length > 0 ? Math.min(...qualityScores) : 0;
  const qualityMax = qualityScores.length > 0 ? Math.max(...qualityScores) : 0;
  const qualityAbove90 = qualityScores.filter((s: number) => s >= 90).length;

  const totalReqs = stats?.total_requirements || 0;
  const p = `/projects/${projectId}`;

  const checks = [
    { label: 'Create project', done: true },
    { label: 'Add first requirement', done: totalReqs > 0, href: `${p}/requirements` },
    { label: 'Run quality check', done: (stats?.avg_quality_score || 0) > 0, href: `${p}/ai` },
    { label: 'Create trace links', done: (stats?.total_trace_links || 0) > 0, href: `${p}/traceability` },
    { label: 'Assign verifications', done: (stats?.verified_count || 0) > 0, href: `${p}/verification` },
    { label: 'Create baseline', done: Array.isArray(baselines) && baselines.length > 0, href: `${p}/baselines` },
  ];

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
          <span className="text-sm text-slate-500">Loading dashboard…</span>
        </div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <p className="text-sm text-slate-500">Project not found</p>
      </div>
    );
  }

  const hasData = totalReqs > 0;

  return (
    <div>
      {/* ══════════════════════════════════════
          1. Project Header
          ══════════════════════════════════════ */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold tracking-tight">{project.name}</h1>
            <span className="rounded-full bg-blue-500/10 px-2.5 py-0.5 text-[10px] font-bold text-blue-400">
              {project.code}
            </span>
          </div>
          {project.description && (
            <p className="mt-1 text-sm text-slate-500 max-w-xl">{project.description}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={fetchAll} className="rounded-full border border-astra-border p-2 text-slate-400 transition hover:text-slate-200">
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
          <button onClick={() => router.push(`${p}/settings`)}
            className="rounded-full border border-astra-border p-2 text-slate-400 transition hover:text-slate-200">
            <Settings className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* ══════════════════════════════════════
          Onboarding (empty project)
          ══════════════════════════════════════ */}
      {!hasData && (
        <div className="grid gap-6 lg:grid-cols-2 mb-6">
          <div className="rounded-xl border border-astra-border bg-astra-surface p-6 text-center">
            <Database className="mx-auto h-10 w-10 text-slate-600 mb-3" />
            <h3 className="text-sm font-bold text-slate-200 mb-1">No Requirements Yet</h3>
            <p className="text-xs text-slate-500 mb-4">
              Seed sample data to explore ASTRA's features, or start adding requirements manually.
            </p>
            <button onClick={handleSeed} disabled={seeding}
              className="rounded-lg bg-blue-500 px-4 py-2 text-xs font-semibold text-white transition hover:bg-blue-600 disabled:opacity-50">
              {seeding
                ? <span className="flex items-center gap-2"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Seeding…</span>
                : 'Seed Project Data'}
            </button>
            {seedResult && <p className="mt-3 text-xs text-emerald-400">{seedResult}</p>}
          </div>
          <OnboardingChecklist checks={checks} />
        </div>
      )}

      {/* ══════════════════════════════════════
          2. Stat Cards
          ══════════════════════════════════════ */}
      {stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 mb-6">
          <StatCard
            label="Total" value={totalReqs}
            icon={FileText} color="#3B82F6"
            sub={`${totalReqs} requirement${totalReqs !== 1 ? 's' : ''}`}
            onClick={() => router.push(`${p}/requirements`)}
          />
          <StatCard
            label="Draft" value={stats.by_status?.draft || 0}
            icon={Clock} color="#F59E0B"
            sub={totalReqs > 0 ? `${Math.round(((stats.by_status?.draft || 0) / totalReqs) * 100)}% of total` : undefined}
            onClick={() => router.push(`${p}/requirements`)}
          />
          <StatCard
            label="Approved" value={(stats.by_status?.approved || 0) + (stats.by_status?.baselined || 0)}
            icon={CheckCircle} color="#10B981"
            sub={totalReqs > 0 ? `${Math.round((((stats.by_status?.approved || 0) + (stats.by_status?.baselined || 0)) / totalReqs) * 100)}% approved` : undefined}
            onClick={() => router.push(`${p}/requirements`)}
          />
          <StatCard
            label="Verified" value={stats.verified_count}
            icon={Shield} color="#8B5CF6"
            sub={totalReqs > 0 ? `${Math.round((stats.verified_count / totalReqs) * 100)}% coverage` : undefined}
            onClick={() => router.push(`${p}/verification`)}
          />
        </div>
      )}

      {/* ══════════════════════════════════════
          3–6. Main Grid
          ══════════════════════════════════════ */}
      {hasData && (
        <div className="grid gap-6 lg:grid-cols-2 mb-6">

          {/* ── 3. Requirements by Level ── */}
          <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                <FileText className="h-3.5 w-3.5 text-blue-400" />
                Requirements by Level
              </h3>
              <span className="text-[10px] font-bold text-slate-400">{totalReqs} total</span>
            </div>
            <div className="space-y-2.5">
              {(['L1', 'L2', 'L3', 'L4', 'L5'] as RequirementLevel[]).map((lv) => (
                <LevelBar key={lv} level={lv} count={byLevel[lv] || 0} total={totalReqs} />
              ))}
            </div>
            {(stats?.orphan_count > 0) && (
              <div className="mt-4 flex items-center gap-2 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2">
                <AlertTriangle className="h-3.5 w-3.5 text-amber-400 flex-shrink-0" />
                <span className="text-[11px] text-amber-300">
                  {stats.orphan_count} orphan{stats.orphan_count !== 1 ? 's' : ''} with no trace links
                </span>
              </div>
            )}
          </div>

          {/* ── 4. Coverage Panel ── */}
          <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
            <h3 className="mb-4 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              <Network className="h-3.5 w-3.5 text-blue-400" />
              Coverage
            </h3>
            {coverage ? (
              <div className="space-y-4">
                <CoverageRow label="Forward (Source Artifacts)" pct={coverage.forward_coverage ?? coverage.with_source_pct ?? 0} />
                <CoverageRow label="Backward (Children)" pct={coverage.backward_coverage ?? coverage.with_children_pct ?? 0} />
                <CoverageRow label="V&V (Verification)" pct={coverage.verification_coverage ?? coverage.with_verification_pct ?? 0} />
                {(coverage.orphans > 0 || coverage.orphan_pct > 0) && (
                  <div className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2">
                    <AlertTriangle className="h-3.5 w-3.5 text-red-400" />
                    <span className="text-[11px] text-red-400">
                      {coverage.orphans || 0} orphan{(coverage.orphans || 0) !== 1 ? 's' : ''} ({(coverage.orphan_pct || 0).toFixed(0)}%)
                    </span>
                  </div>
                )}
              </div>
            ) : (
              <div className="py-6 text-center text-xs text-slate-500">No coverage data yet</div>
            )}
          </div>

          {/* ── 5. Quality Distribution ── */}
          <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
            <h3 className="mb-4 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              <Sparkles className="h-3.5 w-3.5 text-blue-400" />
              Quality Distribution
            </h3>
            {stats && stats.avg_quality_score > 0 ? (
              <div className="space-y-4">
                <div className="flex items-center gap-6">
                  <QualityRing score={stats.avg_quality_score} size={110} />
                  <div className="flex-1 space-y-3">
                    <QualityHistogram scores={qualityScores} />
                    <div className="flex gap-4 pt-1 text-[10px] text-slate-500">
                      <span>Min: <span className="font-bold text-slate-300">{qualityMin.toFixed(0)}</span></span>
                      <span>Max: <span className="font-bold text-slate-300">{qualityMax.toFixed(0)}</span></span>
                      <span>≥90: <span className="font-bold text-emerald-400">{qualityAbove90}</span></span>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="py-6 text-center text-xs text-slate-500">No quality data yet</div>
            )}
          </div>

          {/* ── 6. AI Insights ── */}
          <AIInsightsCard
            projectId={projectId}
            aiStats={aiStats}
            onNavigate={(path) => router.push(path)}
          />
        </div>
      )}

      {/* ══════════════════════════════════════
          7. Recent Activity + Status Breakdown
          ══════════════════════════════════════ */}
      {hasData && (
        <div className="grid gap-6 lg:grid-cols-3 mb-6">
          {/* Activity feed (2/3) */}
          <div className="lg:col-span-2 rounded-xl border border-astra-border bg-astra-surface p-5">
            <h3 className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              <Clock className="h-3.5 w-3.5 text-blue-400" />
              Recent Activity
            </h3>
            {stats?.recent_activity && stats.recent_activity.length > 0 ? (
              <div className="max-h-72 overflow-y-auto">
                {stats.recent_activity.slice(0, 10).map((item: any, i: number) => (
                  <ActivityItem key={i} item={item} />
                ))}
              </div>
            ) : (
              <div className="py-6 text-center text-xs text-slate-500">No activity recorded yet</div>
            )}
          </div>

          {/* Status breakdown (1/3) */}
          <div className="space-y-6">
            {stats && Object.keys(stats.by_status || {}).length > 0 && (
              <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
                <h3 className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                  <CheckSquare className="h-3.5 w-3.5 text-blue-400" />
                  Status Breakdown
                </h3>
                <div className="space-y-2">
                  {Object.entries(stats.by_status as Record<string, number>)
                    .sort(([, a], [, b]) => (b as number) - (a as number))
                    .map(([key, count]) => {
                      const sc = STATUS_COLORS[key as RequirementStatus];
                      const label = STATUS_LABELS[key as RequirementStatus] || key;
                      const pct = totalReqs > 0 ? Math.round(((count as number) / totalReqs) * 100) : 0;
                      return (
                        <div key={key} className="flex items-center gap-2">
                          <span className="w-20 text-[11px] font-medium text-slate-400 truncate">{label}</span>
                          <div className="flex-1 h-2 rounded-full bg-astra-surface-alt overflow-hidden">
                            <div className="h-full rounded-full transition-all duration-700" style={{ width: `${pct}%`, background: sc?.text || '#6B7280' }} />
                          </div>
                          <span className="w-6 text-right text-[11px] font-bold" style={{ color: sc?.text || '#6B7280' }}>{count as number}</span>
                        </div>
                      );
                    })}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════
          8. Quick Actions
          ══════════════════════════════════════ */}
      {hasData && (
        <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mr-2">
              Quick Actions
            </span>
            <button onClick={() => router.push(`${p}/requirements`)}
              className="flex items-center gap-2 rounded-lg bg-blue-500 px-4 py-2 text-xs font-semibold text-white transition hover:bg-blue-600">
              <Plus className="h-3.5 w-3.5" /> New Requirement
            </button>
            <button onClick={() => router.push(`${p}/ai`)}
              className="flex items-center gap-2 rounded-lg border border-astra-border px-4 py-2 text-xs font-semibold text-slate-300 transition hover:border-blue-500/30 hover:text-white">
              <Sparkles className="h-3.5 w-3.5 text-violet-400" /> AI: Convert Prose
            </button>
            <button onClick={() => router.push(`${p}/reports`)}
              className="flex items-center gap-2 rounded-lg border border-astra-border px-4 py-2 text-xs font-semibold text-slate-300 transition hover:border-blue-500/30 hover:text-white">
              <FileBarChart className="h-3.5 w-3.5 text-slate-400" /> Generate Report
            </button>
            <button onClick={() => router.push(`${p}/baselines`)}
              className="flex items-center gap-2 rounded-lg border border-astra-border px-4 py-2 text-xs font-semibold text-slate-300 transition hover:border-blue-500/30 hover:text-white">
              <Archive className="h-3.5 w-3.5 text-slate-400" /> Create Baseline
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
