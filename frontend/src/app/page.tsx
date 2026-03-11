'use client';

import { useState, useEffect } from 'react';
import { FileText, Network, CheckCircle, AlertTriangle, Loader2, RefreshCw } from 'lucide-react';
import { dashboardAPI, traceabilityAPI, projectsAPI } from '@/lib/api';

interface DashboardStats {
  total_requirements: number;
  by_status: Record<string, number>;
  by_type: Record<string, number>;
  verified_count: number;
  avg_quality_score: number;
  total_trace_links: number;
  orphan_count: number;
  recent_activity: Array<{
    req_id: string;
    field: string;
    description: string;
    user: string;
    timestamp: string | null;
  }>;
}

interface CoverageStats {
  total: number;
  with_source: number;
  with_source_pct: number;
  with_tests: number;
  with_tests_pct: number;
  orphans: number;
  orphan_pct: number;
}

interface Project {
  id: number;
  code: string;
  name: string;
}

const STATUS_DISPLAY: Record<string, { label: string; color: string }> = {
  draft: { label: 'Draft', color: '#F59E0B' },
  under_review: { label: 'Under Review', color: '#A78BFA' },
  approved: { label: 'Approved', color: '#3B82F6' },
  baselined: { label: 'Baselined', color: '#10B981' },
  implemented: { label: 'Implemented', color: '#06B6D4' },
  verified: { label: 'Verified', color: '#34D399' },
  validated: { label: 'Validated', color: '#22D3EE' },
  deferred: { label: 'Deferred', color: '#6B7280' },
  deleted: { label: 'Deleted', color: '#EF4444' },
};

function StatCard({ label, value, sub, color, icon: Icon }: any) {
  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{label}</div>
          <div className="mt-2 text-3xl font-bold" style={{ color: color || '#F1F5F9' }}>{value}</div>
          {sub && <div className="mt-1.5 text-xs text-slate-500">{sub}</div>}
        </div>
        {Icon && <Icon className="h-5 w-5 opacity-40" style={{ color }} />}
      </div>
    </div>
  );
}

function ActivityItem({ action, user, time, color }: any) {
  return (
    <div className="flex items-center gap-3 border-b border-astra-border py-3 last:border-0">
      <div className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: color }} />
      <div className="flex-1">
        <div className="text-[13px] text-slate-200">{action}</div>
        <div className="text-[11px] text-slate-500">{user}</div>
      </div>
      <div className="whitespace-nowrap text-[11px] text-slate-500">{time}</div>
    </div>
  );
}

function formatTimeAgo(timestamp: string | null): string {
  if (!timestamp) return '';
  const diff = Date.now() - new Date(timestamp).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function activityColor(field: string): string {
  if (field === 'created') return '#3B82F6';
  if (field === 'status') return '#10B981';
  if (field === 'quality_score') return '#F59E0B';
  return '#8B5CF6';
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [coverage, setCoverage] = useState<CoverageStats | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchData = async () => {
    setLoading(true);
    setError('');
    try {
      // Get first project
      const projRes = await projectsAPI.list();
      const projects = projRes.data;
      if (!projects.length) {
        setError('No projects found. Seed the database first via POST /api/v1/dev/seed');
        setLoading(false);
        return;
      }
      const proj = projects[0];
      setProject(proj);

      // Fetch stats and coverage in parallel
      const [statsRes, coverageRes] = await Promise.all([
        dashboardAPI.getStats(proj.id),
        traceabilityAPI.getCoverage(proj.id).catch(() => ({ data: null })),
      ]);

      setStats(statsRes.data);
      setCoverage(coverageRes.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4">
        <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-6 py-4 text-sm text-red-400">
          {error}
        </div>
        <button onClick={fetchData}
          className="flex items-center gap-2 rounded-lg bg-blue-500 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-600">
          <RefreshCw className="h-4 w-4" /> Retry
        </button>
      </div>
    );
  }

  if (!stats || !project) return null;

  const verifiedPct = stats.total_requirements > 0
    ? Math.round((stats.verified_count / stats.total_requirements) * 100)
    : 0;

  const statusEntries = Object.entries(stats.by_status).map(([key, count]) => ({
    status: STATUS_DISPLAY[key]?.label || key,
    count,
    pct: stats.total_requirements > 0 ? Math.round((count / stats.total_requirements) * 100) : 0,
    color: STATUS_DISPLAY[key]?.color || '#6B7280',
  }));

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Project Dashboard</h1>
          <p className="mt-1 text-sm text-slate-500">{project.code} · ASTRA Systems Engineering Platform</p>
        </div>
        <div className="flex gap-2">
          <button onClick={fetchData} className="rounded-full border border-astra-border p-2 text-slate-400 transition hover:text-slate-200">
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
          <span className="rounded-full bg-violet-500/15 px-3 py-1 text-[11px] font-semibold text-violet-400">
            {stats.total_requirements} Requirements
          </span>
        </div>
      </div>

      {/* Stats */}
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total Requirements" value={stats.total_requirements} sub={`${project.code} Project`} icon={FileText} />
        <StatCard label="Verification" value={`${verifiedPct}%`} color="#F59E0B" sub={`${stats.verified_count} of ${stats.total_requirements} verified`} icon={CheckCircle} />
        <StatCard label="Quality Score" value={stats.avg_quality_score} color="#10B981" sub="Average across all reqs" />
        <StatCard label="Open Issues" value={stats.orphan_count} color="#EF4444" sub="Orphans (no trace links)" icon={AlertTriangle} />
      </div>

      {/* Main content grid */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        {/* Activity Feed */}
        <div className="rounded-xl border border-astra-border bg-astra-surface p-5 xl:col-span-2">
          <h2 className="mb-4 text-sm font-bold text-slate-200">Recent Activity</h2>
          {stats.recent_activity.length === 0 ? (
            <div className="py-8 text-center text-sm text-slate-500">No activity yet</div>
          ) : (
            stats.recent_activity.slice(0, 8).map((a, i) => (
              <ActivityItem
                key={i}
                action={a.description}
                user={a.user}
                time={formatTimeAgo(a.timestamp)}
                color={activityColor(a.field)}
              />
            ))
          )}
        </div>

        {/* By Status */}
        <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
          <h2 className="mb-4 text-sm font-bold text-slate-200">By Status</h2>
          {statusEntries.map((s) => (
            <div key={s.status} className="mb-3">
              <div className="mb-1 flex justify-between">
                <span className="text-xs text-slate-400">{s.status}</span>
                <span className="text-xs font-semibold text-slate-400">{s.count}</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-astra-surface-alt">
                <div className="h-full rounded-full transition-all duration-700" style={{ width: `${s.pct}%`, background: s.color }} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Traceability Coverage */}
      {coverage && coverage.total > 0 && (
        <div className="mt-6 rounded-xl border border-astra-border bg-astra-surface p-5">
          <h2 className="mb-4 text-sm font-bold text-slate-200">Traceability Coverage</h2>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {[
              { label: 'With Source Artifacts', value: coverage.with_source_pct, color: '#10B981' },
              { label: 'With Test Cases', value: coverage.with_tests_pct, color: '#F59E0B' },
              { label: 'Orphans', value: coverage.orphan_pct, color: '#EF4444' },
              { label: 'Trace Links Total', value: stats.total_trace_links, color: '#3B82F6', raw: true },
            ].map((m) => (
              <div key={m.label}>
                <div className="mb-1 flex justify-between">
                  <span className="text-xs text-slate-500">{m.label}</span>
                  <span className="text-xs font-bold" style={{ color: m.color }}>
                    {m.raw ? m.value : `${m.value}%`}
                  </span>
                </div>
                {!m.raw && (
                  <div className="h-2 overflow-hidden rounded-full bg-astra-surface-alt">
                    <div className="h-full rounded-full transition-all duration-700" style={{ width: `${m.value}%`, background: m.color }} />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
