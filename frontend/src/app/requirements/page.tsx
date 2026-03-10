'use client';

import { useState } from 'react';
import { Search, Plus, Link2, Check, AlertTriangle } from 'lucide-react';
import { STATUS_COLORS, STATUS_LABELS, type RequirementStatus } from '@/lib/types';

const SAMPLE_REQS = [
  { id: 'FR-AUTH-001', title: 'Structured Requirement Form', type: 'Functional', priority: 'High', status: 'approved' as RequirementStatus, owner: 'J. Martinez', traces: 3, verified: true, quality: 94 },
  { id: 'FR-AUTH-002', title: 'Auto-Generate Hierarchical IDs', type: 'Functional', priority: 'High', status: 'baselined' as RequirementStatus, owner: 'K. Chen', traces: 2, verified: true, quality: 100 },
  { id: 'FR-PRST-001', title: 'Source Artifact Management', type: 'Functional', priority: 'High', status: 'approved' as RequirementStatus, owner: 'J. Martinez', traces: 5, verified: false, quality: 87 },
  { id: 'FR-PRST-002', title: 'Backward Traceability Links', type: 'Functional', priority: 'High', status: 'under_review' as RequirementStatus, owner: 'R. Patel', traces: 4, verified: false, quality: 91 },
  { id: 'FR-QUAL-001', title: 'NASA Appendix C Editorial Checks', type: 'Functional', priority: 'High', status: 'draft' as RequirementStatus, owner: 'A. Nowak', traces: 1, verified: false, quality: 78 },
  { id: 'FR-QUAL-002', title: 'Prohibited Terms Detection', type: 'Functional', priority: 'High', status: 'draft' as RequirementStatus, owner: 'A. Nowak', traces: 1, verified: false, quality: 72 },
  { id: 'FR-VIS-001', title: 'Interactive Traceability Graph', type: 'Functional', priority: 'High', status: 'under_review' as RequirementStatus, owner: 'S. Kim', traces: 3, verified: false, quality: 85 },
  { id: 'FR-CHNG-001', title: 'Automated Impact Analysis', type: 'Functional', priority: 'High', status: 'approved' as RequirementStatus, owner: 'R. Patel', traces: 6, verified: false, quality: 96 },
  { id: 'PR-PERF-001', title: 'Page Load Under 2 Seconds', type: 'Performance', priority: 'High', status: 'baselined' as RequirementStatus, owner: 'K. Chen', traces: 2, verified: true, quality: 100 },
  { id: 'SR-SEC-001', title: 'User Authentication (bcrypt + LDAP)', type: 'Security', priority: 'High', status: 'approved' as RequirementStatus, owner: 'M. Torres', traces: 3, verified: false, quality: 92 },
  { id: 'IR-INT-001', title: 'RESTful API over HTTPS', type: 'Interface', priority: 'High', status: 'baselined' as RequirementStatus, owner: 'K. Chen', traces: 4, verified: true, quality: 100 },
  { id: 'ER-ENV-001', title: 'Internal Linux Server Deployment', type: 'Environmental', priority: 'High', status: 'approved' as RequirementStatus, owner: 'M. Torres', traces: 2, verified: false, quality: 88 },
];

function QualityDot({ score }: { score: number }) {
  const color = score >= 90 ? '#10B981' : score >= 75 ? '#F59E0B' : '#EF4444';
  return (
    <div className="flex items-center gap-1.5">
      <div className="h-2 w-2 rounded-full" style={{ background: color, boxShadow: `0 0 6px ${color}66` }} />
      <span className="font-mono text-xs font-semibold" style={{ color }}>{score}</span>
    </div>
  );
}

export default function RequirementsPage() {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');

  const filtered = SAMPLE_REQS.filter(r => {
    const matchesSearch = !search ||
      r.id.toLowerCase().includes(search.toLowerCase()) ||
      r.title.toLowerCase().includes(search.toLowerCase());
    const matchesFilter = filter === 'all' || r.status === filter;
    return matchesSearch && matchesFilter;
  });

  const stats = {
    total: SAMPLE_REQS.length,
    verified: SAMPLE_REQS.filter(r => r.verified).length,
    avgQuality: Math.round(SAMPLE_REQS.reduce((a, r) => a + r.quality, 0) / SAMPLE_REQS.length),
    traces: SAMPLE_REQS.reduce((a, r) => a + r.traces, 0),
  };

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Requirements Management</h1>
          <p className="mt-1 text-sm text-slate-500">PROJ-ALPHA · ASTRA Systems Engineering Platform</p>
        </div>
      </div>

      {/* Stats */}
      <div className="mb-6 grid grid-cols-2 gap-4 xl:grid-cols-4">
        <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
          <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">Total</div>
          <div className="mt-1 text-2xl font-bold text-slate-100">{stats.total}</div>
        </div>
        <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
          <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">Verified</div>
          <div className="mt-1 text-2xl font-bold text-emerald-400">{stats.verified}/{stats.total}</div>
        </div>
        <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
          <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">Avg Quality</div>
          <div className="mt-1 text-2xl font-bold text-emerald-400">{stats.avgQuality}</div>
        </div>
        <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
          <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">Trace Links</div>
          <div className="mt-1 text-2xl font-bold text-blue-400">{stats.traces}</div>
        </div>
      </div>

      {/* Toolbar */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex flex-1 items-center gap-2 rounded-lg border border-astra-border bg-astra-surface px-3 py-2" style={{ maxWidth: 360 }}>
          <Search className="h-4 w-4 text-slate-500" />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by ID, title, or type..."
            className="flex-1 border-0 bg-transparent text-[13px] text-slate-200 outline-none placeholder:text-slate-600" />
        </div>
        <div className="flex gap-1">
          {['all', 'draft', 'under_review', 'approved', 'baselined'].map((f) => (
            <button key={f} onClick={() => setFilter(f)}
              className={`rounded-full px-3.5 py-1.5 text-xs font-semibold transition-all ${
                filter === f
                  ? 'bg-blue-500 text-white'
                  : 'border border-astra-border bg-transparent text-slate-400 hover:border-blue-500/30 hover:text-slate-200'
              }`}>
              {f === 'all' ? 'All' : STATUS_LABELS[f as RequirementStatus] || f}
            </button>
          ))}
        </div>
        <button className="ml-auto flex items-center gap-1.5 rounded-lg bg-blue-500 px-4 py-2 text-[13px] font-semibold text-white transition hover:bg-blue-600">
          <Plus className="h-4 w-4" /> New Requirement
        </button>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
        <div className="grid grid-cols-[120px_1fr_110px_80px_70px_65px_50px] border-b border-astra-border bg-astra-surface-alt px-4 py-2.5 text-[10px] font-bold uppercase tracking-wider text-slate-500">
          <span>ID</span><span>Requirement</span><span>Status</span><span>Type</span><span>Traces</span><span>Quality</span><span>V&V</span>
        </div>
        {filtered.map((req, i) => {
          const sc = STATUS_COLORS[req.status];
          return (
            <div key={req.id}
              className="grid grid-cols-[120px_1fr_110px_80px_70px_65px_50px] items-center border-b border-astra-border px-4 py-3 transition-colors last:border-0 hover:bg-astra-surface-hover cursor-pointer">
              <span className="font-mono text-xs font-semibold text-blue-400">{req.id}</span>
              <div>
                <div className="text-[13px] font-medium text-slate-200">{req.title}</div>
                <div className="mt-0.5 text-[11px] text-slate-500">{req.owner}</div>
              </div>
              <span className="inline-flex w-fit rounded-full px-2.5 py-0.5 text-[11px] font-semibold"
                style={{ background: sc?.bg, color: sc?.text }}>
                {STATUS_LABELS[req.status]}
              </span>
              <span className="text-[11px] text-slate-400">{req.type}</span>
              <div className="flex items-center gap-1">
                <Link2 className="h-3 w-3 text-slate-500" />
                <span className="text-xs text-slate-400">{req.traces}</span>
              </div>
              <QualityDot score={req.quality} />
              <div className="flex justify-center">
                {req.verified ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <span className="text-slate-600">—</span>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
