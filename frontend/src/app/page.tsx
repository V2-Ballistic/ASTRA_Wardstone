/**
 * ASTRA — Project Dashboard
 * ============================
 * File: frontend/src/app/page.tsx
 *
 * Landing page showing all projects with stats summaries.
 * Users can click into a project or create a new one.
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  Loader2, RefreshCw, Plus, FolderOpen, FileText, CheckCircle,
  AlertTriangle, Network, ChevronRight, Rocket, Clock, Shield,
  BarChart3, Sparkles,
} from 'lucide-react';
import { projectsAPI, dashboardAPI, traceabilityAPI, requirementsAPI } from '@/lib/api';

/* ── Types ── */

interface Project {
  id: number;
  code: string;
  name: string;
  description?: string;
  status: string;
  created_at: string;
  updated_at?: string;
}

interface ProjectWithStats extends Project {
  stats?: {
    total_requirements: number;
    verified_count: number;
    avg_quality_score: number;
    orphan_count: number;
    by_status: Record<string, number>;
  };
  coverage?: {
    forward_coverage: number;
    backward_coverage: number;
    verification_coverage: number;
  };
  loading?: boolean;
}

/* ── Status badge helper ── */

const PROJECT_STATUS: Record<string, { label: string; color: string; bg: string }> = {
  active:   { label: 'Active',   color: '#10B981', bg: '#10B98118' },
  archived: { label: 'Archived', color: '#6B7280', bg: '#6B728018' },
  draft:    { label: 'Draft',    color: '#F59E0B', bg: '#F59E0B18' },
  on_hold:  { label: 'On Hold',  color: '#EF4444', bg: '#EF444418' },
};

/* ── Micro-stat pill ── */

function MicroStat({ icon: Icon, value, label, color = '#94A3B8' }: {
  icon: any; value: string | number; label: string; color?: string;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <Icon className="h-3 w-3" style={{ color }} />
      <span className="text-xs font-bold" style={{ color }}>{value}</span>
      <span className="text-[10px] text-slate-600">{label}</span>
    </div>
  );
}

/* ── Coverage mini-bar ── */

function CoverageBar({ label, pct, color }: { label: string; pct: number; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-16 text-[10px] text-slate-500">{label}</span>
      <div className="h-1.5 flex-1 rounded-full bg-slate-800">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${Math.min(pct, 100)}%`, background: color }}
        />
      </div>
      <span className="w-10 text-right text-[10px] font-semibold" style={{ color }}>
        {pct.toFixed(0)}%
      </span>
    </div>
  );
}

/* ── Timestamp formatter ── */

function formatDate(iso: string | undefined | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function timeAgo(iso: string | undefined | null): string {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(iso);
}

/* ══════════════════════════════════════
   Main Dashboard Page
   ══════════════════════════════════════ */

export default function DashboardPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectWithStats[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  /* ── Fetch all projects, then enrich with stats ── */
  const fetchProjects = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await projectsAPI.list();
      const raw: Project[] = res.data;

      // Set projects immediately (show cards fast)
      const initial: ProjectWithStats[] = raw.map((p) => ({ ...p, loading: true }));
      setProjects(initial);
      setLoading(false);

      // Enrich each project with stats in parallel
      const enriched = await Promise.all(
        raw.map(async (proj) => {
          try {
            const [statsRes, coverageRes] = await Promise.all([
              dashboardAPI.getStats(proj.id).catch(() => null),
              traceabilityAPI.getCoverage(proj.id).catch(() => null),
            ]);
            return {
              ...proj,
              stats: statsRes?.data || undefined,
              coverage: coverageRes?.data || undefined,
              loading: false,
            };
          } catch {
            return { ...proj, loading: false };
          }
        })
      );
      setProjects(enriched);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load projects');
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  /* ── Loading state ── */
  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
          <span className="text-sm text-slate-500">Loading projects…</span>
        </div>
      </div>
    );
  }

  /* ── Error state ── */
  if (error && projects.length === 0) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4">
        <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-6 py-4 text-sm text-red-400">
          {error}
        </div>
        <button
          onClick={fetchProjects}
          className="flex items-center gap-2 rounded-lg bg-blue-500 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-600 transition"
        >
          <RefreshCw className="h-4 w-4" /> Retry
        </button>
      </div>
    );
  }

  /* ── Aggregate quick-stats (across all projects) ── */
  const totalReqs = projects.reduce((sum, p) => sum + (p.stats?.total_requirements || 0), 0);
  const totalOrphans = projects.reduce((sum, p) => sum + (p.stats?.orphan_count || 0), 0);
  const totalVerified = projects.reduce((sum, p) => sum + (p.stats?.verified_count || 0), 0);
  const avgQuality = projects.length > 0
    ? projects.reduce((sum, p) => sum + (p.stats?.avg_quality_score || 0), 0) / projects.filter(p => p.stats).length
    : 0;

  return (
    <div>
      {/* ── Header ── */}
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100">
            Projects
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            ASTRA Systems Engineering Platform
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchProjects}
            className="rounded-full border border-astra-border p-2.5 text-slate-400 transition hover:border-blue-500/30 hover:text-slate-200"
            aria-label="Refresh projects"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
          <button
            onClick={() => router.push('/projects/new')}
            className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-blue-500 to-violet-500 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-blue-500/20 transition hover:shadow-blue-500/40 hover:brightness-110"
          >
            <Plus className="h-4 w-4" />
            Create New Project
          </button>
        </div>
      </div>

      {/* ── Aggregate Stats Row ── */}
      {projects.some((p) => p.stats) && (
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
            <div className="flex items-center gap-2 text-slate-500">
              <FolderOpen className="h-4 w-4" />
              <span className="text-[10px] font-semibold uppercase tracking-widest">Projects</span>
            </div>
            <div className="mt-2 text-2xl font-bold text-slate-100">{projects.length}</div>
          </div>
          <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
            <div className="flex items-center gap-2 text-slate-500">
              <FileText className="h-4 w-4" />
              <span className="text-[10px] font-semibold uppercase tracking-widest">Requirements</span>
            </div>
            <div className="mt-2 text-2xl font-bold text-blue-400">{totalReqs}</div>
          </div>
          <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
            <div className="flex items-center gap-2 text-slate-500">
              <CheckCircle className="h-4 w-4" />
              <span className="text-[10px] font-semibold uppercase tracking-widest">Verified</span>
            </div>
            <div className="mt-2 text-2xl font-bold text-emerald-400">{totalVerified}</div>
          </div>
          <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
            <div className="flex items-center gap-2 text-slate-500">
              <BarChart3 className="h-4 w-4" />
              <span className="text-[10px] font-semibold uppercase tracking-widest">Avg Quality</span>
            </div>
            <div className="mt-2 text-2xl font-bold text-amber-400">
              {avgQuality ? avgQuality.toFixed(1) : '—'}
            </div>
          </div>
        </div>
      )}

      {/* ── Empty State ── */}
      {projects.length === 0 && (
        <div className="flex min-h-[50vh] flex-col items-center justify-center gap-5">
          <div className="flex h-20 w-20 items-center justify-center rounded-2xl border border-astra-border bg-astra-surface">
            <Rocket className="h-10 w-10 text-blue-500/60" />
          </div>
          <div className="text-center">
            <h2 className="text-lg font-bold text-slate-200">No Projects Yet</h2>
            <p className="mt-1 max-w-sm text-sm text-slate-500">
              Create your first project to start tracking requirements,
              building traceability, and managing your systems engineering workflow.
            </p>
          </div>
          <button
            onClick={() => router.push('/projects/new')}
            className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-blue-500 to-violet-500 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-blue-500/20 transition hover:shadow-blue-500/40 hover:brightness-110"
          >
            <Plus className="h-4 w-4" />
            Create New Project
          </button>
        </div>
      )}

      {/* ── Project Cards ── */}
      {projects.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          {projects.map((proj) => {
            const status = PROJECT_STATUS[proj.status] || PROJECT_STATUS.active;
            const hasStats = !!proj.stats;
            const verifiedPct =
              hasStats && proj.stats!.total_requirements > 0
                ? Math.round((proj.stats!.verified_count / proj.stats!.total_requirements) * 100)
                : 0;

            return (
              <button
                key={proj.id}
                onClick={() => router.push(`/projects/${proj.id}`)}
                className="group relative w-full rounded-xl border border-astra-border bg-astra-surface p-5 text-left transition-all hover:border-blue-500/30 hover:shadow-lg hover:shadow-blue-500/5"
              >
                {/* Top row: code badge, name, status, chevron */}
                <div className="flex items-start gap-3">
                  {/* Project icon */}
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500/20 to-violet-500/20 text-sm font-extrabold text-blue-400 ring-1 ring-blue-500/20">
                    {proj.code.slice(0, 2)}
                  </div>

                  {/* Name + description */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-bold text-slate-100 group-hover:text-blue-400 transition truncate">
                        {proj.name}
                      </h3>
                      <span
                        className="shrink-0 rounded-full px-2 py-0.5 text-[9px] font-bold"
                        style={{ background: status.bg, color: status.color }}
                      >
                        {status.label}
                      </span>
                    </div>
                    <p className="mt-0.5 text-xs text-slate-500 font-mono">{proj.code}</p>
                    {proj.description && (
                      <p className="mt-1 text-xs text-slate-500 line-clamp-2 leading-relaxed">
                        {proj.description}
                      </p>
                    )}
                  </div>

                  {/* Arrow */}
                  <ChevronRight className="h-4 w-4 shrink-0 text-slate-600 transition group-hover:translate-x-0.5 group-hover:text-blue-400" />
                </div>

                {/* Stats row */}
                {proj.loading ? (
                  <div className="mt-4 flex items-center gap-2">
                    <Loader2 className="h-3 w-3 animate-spin text-slate-600" />
                    <span className="text-[10px] text-slate-600">Loading stats…</span>
                  </div>
                ) : hasStats ? (
                  <div className="mt-4 space-y-3">
                    {/* Micro stats */}
                    <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
                      <MicroStat
                        icon={FileText}
                        value={proj.stats!.total_requirements}
                        label="requirements"
                        color="#3B82F6"
                      />
                      <MicroStat
                        icon={CheckCircle}
                        value={`${verifiedPct}%`}
                        label="verified"
                        color="#10B981"
                      />
                      <MicroStat
                        icon={Sparkles}
                        value={proj.stats!.avg_quality_score?.toFixed(1) || '—'}
                        label="quality"
                        color="#F59E0B"
                      />
                      {proj.stats!.orphan_count > 0 && (
                        <MicroStat
                          icon={AlertTriangle}
                          value={proj.stats!.orphan_count}
                          label="orphans"
                          color="#EF4444"
                        />
                      )}
                    </div>

                    {/* Coverage bars */}
                    {proj.coverage && (
                      <div className="space-y-1.5">
                        <CoverageBar label="Forward" pct={proj.coverage.forward_coverage} color="#3B82F6" />
                        <CoverageBar label="Backward" pct={proj.coverage.backward_coverage} color="#8B5CF6" />
                        <CoverageBar label="V&V" pct={proj.coverage.verification_coverage} color="#10B981" />
                      </div>
                    )}

                    {/* Status breakdown chips */}
                    {Object.keys(proj.stats!.by_status).length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {Object.entries(proj.stats!.by_status).map(([key, count]) => {
                          if (count === 0) return null;
                          return (
                            <span
                              key={key}
                              className="rounded-full px-2 py-0.5 text-[9px] font-semibold text-slate-400"
                              style={{ background: 'rgba(100,116,139,0.12)' }}
                            >
                              {key.replace('_', ' ')} {count}
                            </span>
                          );
                        })}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="mt-4 text-[10px] text-slate-600 italic">
                    No requirements data yet
                  </div>
                )}

                {/* Footer: dates */}
                <div className="mt-3 flex items-center gap-4 border-t border-astra-border/50 pt-3">
                  <div className="flex items-center gap-1.5 text-[10px] text-slate-600">
                    <Clock className="h-3 w-3" />
                    Created {formatDate(proj.created_at)}
                  </div>
                  {proj.updated_at && (
                    <div className="text-[10px] text-slate-600">
                      Updated {timeAgo(proj.updated_at)}
                    </div>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
