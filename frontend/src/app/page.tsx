'use client';

import { FileText, Network, CheckCircle, AlertTriangle } from 'lucide-react';

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

export default function DashboardPage() {
  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Project Dashboard</h1>
          <p className="mt-1 text-sm text-slate-500">PROJ-ALPHA · ASTRA Systems Engineering Platform</p>
        </div>
        <div className="flex gap-2">
          <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-[11px] font-semibold text-emerald-400">v1.0 Baseline</span>
          <span className="rounded-full bg-violet-500/15 px-3 py-1 text-[11px] font-semibold text-violet-400">67 Requirements</span>
        </div>
      </div>

      {/* Stats */}
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total Requirements" value={67} sub="SRS v1.0 Baseline" icon={FileText} />
        <StatCard label="Verification" value="6%" color="#F59E0B" sub="4 of 67 verified" icon={CheckCircle} />
        <StatCard label="Quality Score" value={90} color="#10B981" sub="NASA App. C Compliant" />
        <StatCard label="Open Issues" value={16} color="#EF4444" sub="Orphans + Dead-ends" icon={AlertTriangle} />
      </div>

      {/* Main content grid */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        {/* Activity Feed */}
        <div className="rounded-xl border border-astra-border bg-astra-surface p-5 xl:col-span-2">
          <h2 className="mb-4 text-sm font-bold text-slate-200">Recent Activity</h2>
          <ActivityItem action="FR-CHNG-001 approved" user="R. Patel" time="2 min ago" color="#10B981" />
          <ActivityItem action="FR-QUAL-002 flagged: prohibited term" user="System" time="15 min ago" color="#F59E0B" />
          <ActivityItem action="New trace link: FR-PRST-002 → Interview #4" user="J. Martinez" time="1 hr ago" color="#3B82F6" />
          <ActivityItem action="Baseline v0.9 created" user="K. Chen" time="3 hrs ago" color="#8B5CF6" />
          <ActivityItem action="PR-PERF-001 verified: PASS" user="K. Chen" time="5 hrs ago" color="#10B981" />
        </div>

        {/* By Status */}
        <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
          <h2 className="mb-4 text-sm font-bold text-slate-200">By Status</h2>
          {[
            { status: 'Draft', count: 12, pct: 18, color: '#F59E0B' },
            { status: 'Under Review', count: 8, pct: 12, color: '#A78BFA' },
            { status: 'Approved', count: 22, pct: 33, color: '#3B82F6' },
            { status: 'Baselined', count: 21, pct: 31, color: '#10B981' },
            { status: 'Verified', count: 4, pct: 6, color: '#34D399' },
          ].map((s) => (
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
      <div className="mt-6 rounded-xl border border-astra-border bg-astra-surface p-5">
        <h2 className="mb-4 text-sm font-bold text-slate-200">Traceability Coverage</h2>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {[
            { label: 'With Source Artifacts', value: 83, color: '#10B981' },
            { label: 'With Test Cases', value: 42, color: '#F59E0B' },
            { label: 'With Design Links', value: 67, color: '#3B82F6' },
            { label: 'Fully Traced (E2E)', value: 33, color: '#EF4444' },
          ].map((m) => (
            <div key={m.label}>
              <div className="mb-1 flex justify-between">
                <span className="text-xs text-slate-500">{m.label}</span>
                <span className="text-xs font-bold" style={{ color: m.color }}>{m.value}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-astra-surface-alt">
                <div className="h-full rounded-full transition-all duration-700" style={{ width: `${m.value}%`, background: m.color }} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
