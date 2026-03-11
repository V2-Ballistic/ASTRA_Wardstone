'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  Archive, Clock, FileText, Loader2, RefreshCw, GitBranch,
  ArrowLeftRight, ChevronRight, Plus, Minus, Edit3, Trash2, ArrowLeft,
  CheckCircle, AlertTriangle, X
} from 'lucide-react';
import { baselinesAPI, projectsAPI } from '@/lib/api';
import { STATUS_COLORS, STATUS_LABELS, LEVEL_COLORS, type RequirementStatus, type RequirementLevel } from '@/lib/types';

type ViewMode = 'list' | 'detail' | 'compare';

export default function BaselinesPage() {
  const router = useRouter();
  const [projectId, setProjectId] = useState<number | null>(null);
  const [projectCode, setProjectCode] = useState('');
  const [baselines, setBaselines] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // View state
  const [view, setView] = useState<ViewMode>('list');
  const [selectedBaseline, setSelectedBaseline] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Compare state
  const [compareA, setCompareA] = useState<number | null>(null);
  const [compareB, setCompareB] = useState<number | null>(null);
  const [compareResult, setCompareResult] = useState<any>(null);
  const [comparing, setComparing] = useState(false);

  // Load project
  useEffect(() => {
    projectsAPI.list().then(res => {
      if (res.data.length > 0) { setProjectId(res.data[0].id); setProjectCode(res.data[0].code); }
    }).catch(() => setError('Failed to load projects'));
  }, []);

  // Load baselines
  const fetchBaselines = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const res = await baselinesAPI.list(projectId);
      setBaselines(res.data.baselines || []);
    } catch (e: any) { setError(e.response?.data?.detail || 'Failed to load baselines'); }
    finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { fetchBaselines(); }, [fetchBaselines]);

  // Open detail
  const openDetail = async (id: number) => {
    setDetailLoading(true); setView('detail');
    try {
      const res = await baselinesAPI.get(id);
      setSelectedBaseline(res.data);
    } catch (e: any) { setError(e.response?.data?.detail || 'Failed'); setView('list'); }
    finally { setDetailLoading(false); }
  };

  // Compare
  const runCompare = async () => {
    if (!compareA || !compareB) return;
    setComparing(true); setView('compare');
    try {
      const res = await baselinesAPI.compare(compareA, compareB);
      setCompareResult(res.data);
    } catch (e: any) { setError(e.response?.data?.detail || 'Failed'); setView('list'); }
    finally { setComparing(false); }
  };

  const formatDate = (iso: string) => iso ? new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';

  // ── LIST VIEW ──
  if (view === 'list') return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Baselines</h1>
          <p className="mt-1 text-sm text-slate-500">{projectCode} · Frozen requirement snapshots for milestone reviews</p>
        </div>
        <button onClick={fetchBaselines} className="rounded-full border border-astra-border p-2 text-slate-400 transition hover:text-slate-200">
          <RefreshCw className="h-3.5 w-3.5" />
        </button>
      </div>

      {error && <div className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">{error}</div>}

      {/* Compare selector */}
      {baselines.length >= 2 && (
        <div className="mb-6 rounded-xl border border-astra-border bg-astra-surface p-4">
          <h3 className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            <ArrowLeftRight className="h-3.5 w-3.5 text-blue-400" /> Compare Baselines
          </h3>
          <div className="flex items-center gap-3">
            <select value={compareA || ''} onChange={e => setCompareA(Number(e.target.value) || null)}
              className="flex-1 rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-sm text-slate-200 outline-none">
              <option value="">Select baseline A...</option>
              {baselines.map(b => <option key={b.id} value={b.id}>{b.name} ({formatDate(b.created_at)})</option>)}
            </select>
            <span className="text-slate-500 text-sm font-bold">vs</span>
            <select value={compareB || ''} onChange={e => setCompareB(Number(e.target.value) || null)}
              className="flex-1 rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-sm text-slate-200 outline-none">
              <option value="">Select baseline B...</option>
              {baselines.map(b => <option key={b.id} value={b.id}>{b.name} ({formatDate(b.created_at)})</option>)}
            </select>
            <button onClick={runCompare} disabled={!compareA || !compareB || compareA === compareB}
              className="flex items-center gap-1.5 rounded-lg bg-blue-500 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-600 disabled:opacity-40">
              <ArrowLeftRight className="h-3.5 w-3.5" /> Compare
            </button>
          </div>
        </div>
      )}

      {/* Baseline cards */}
      {loading ? (
        <div className="flex items-center justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-blue-500" /></div>
      ) : baselines.length === 0 ? (
        <div className="py-16 text-center">
          <Archive className="mx-auto h-10 w-10 text-slate-600 mb-3" />
          <div className="text-sm text-slate-500">No baselines yet</div>
          <p className="mt-1 text-xs text-slate-600">Create a baseline from the Requirements page to freeze a snapshot</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {baselines.map(b => (
            <div key={b.id} onClick={() => openDetail(b.id)}
              className="rounded-xl border border-astra-border bg-astra-surface p-5 transition hover:border-blue-500/20 cursor-pointer group">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/15">
                    <Archive className="h-4 w-4 text-emerald-400" />
                  </div>
                  <div>
                    <div className="text-sm font-bold text-slate-100 group-hover:text-blue-400 transition">{b.name}</div>
                    <div className="text-[10px] text-slate-500">{formatDate(b.created_at)}</div>
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 text-slate-600 group-hover:text-blue-400 transition" />
              </div>
              {b.description && <p className="text-xs text-slate-400 mb-3 line-clamp-2">{b.description}</p>}
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-1.5">
                  <FileText className="h-3 w-3 text-slate-500" />
                  <span className="text-xs font-semibold text-slate-300">{b.requirements_count}</span>
                  <span className="text-[10px] text-slate-500">requirements</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Clock className="h-3 w-3 text-slate-500" />
                  <span className="text-[10px] text-slate-500">by {b.created_by}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  // ── DETAIL VIEW ──
  if (view === 'detail') return (
    <div>
      <div className="mb-6 flex items-center gap-3">
        <button onClick={() => { setView('list'); setSelectedBaseline(null); }}
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-astra-border text-slate-400 transition hover:text-slate-200">
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="flex-1">
          <h1 className="text-xl font-bold tracking-tight">{selectedBaseline?.name || 'Baseline'}</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            {selectedBaseline ? `${selectedBaseline.requirements_count} frozen requirements · Created ${formatDate(selectedBaseline.created_at)} by ${selectedBaseline.created_by}` : ''}
          </p>
        </div>
        <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-[11px] font-semibold text-emerald-400">
          <Archive className="inline h-3 w-3 mr-1" /> Frozen Snapshot
        </span>
      </div>

      {selectedBaseline?.description && (
        <div className="mb-4 rounded-xl border border-astra-border bg-astra-surface p-4">
          <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-1">Description</div>
          <p className="text-sm text-slate-300">{selectedBaseline.description}</p>
        </div>
      )}

      {detailLoading ? (
        <div className="flex items-center justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-blue-500" /></div>
      ) : selectedBaseline?.requirements ? (
        <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
          <div className="grid grid-cols-[100px_40px_1fr_100px_90px_70px_60px] border-b border-astra-border bg-astra-surface-alt px-4 py-2.5 text-[10px] font-bold uppercase tracking-wider text-slate-500">
            <span>ID</span><span>Lvl</span><span>Title</span><span>Status</span><span>Type</span><span>Priority</span><span>Quality</span>
          </div>
          {selectedBaseline.requirements.map((r: any) => {
            const sc = STATUS_COLORS[r.status as RequirementStatus];
            return (
              <div key={r.id} className="grid grid-cols-[100px_40px_1fr_100px_90px_70px_60px] items-center border-b border-astra-border px-4 py-2.5 last:border-0">
                <span className="font-mono text-xs font-semibold text-blue-400">{r.req_id}</span>
                <span className="rounded-full px-1.5 py-0.5 text-center text-[9px] font-bold"
                  style={{ background: `${LEVEL_COLORS[r.level as RequirementLevel] || '#6B7280'}20`, color: LEVEL_COLORS[r.level as RequirementLevel] || '#6B7280' }}>
                  {r.level}
                </span>
                <div className="min-w-0 pr-4">
                  <div className="truncate text-[13px] text-slate-200">{r.title}</div>
                </div>
                <span className="inline-flex w-fit rounded-full px-2 py-0.5 text-[10px] font-semibold"
                  style={{ background: sc?.bg, color: sc?.text }}>{STATUS_LABELS[r.status as RequirementStatus] || r.status}</span>
                <span className="text-[10px] text-slate-400 capitalize">{r.type}</span>
                <span className="text-[10px] text-slate-400 capitalize">{r.priority}</span>
                <span className="text-xs font-mono font-semibold" style={{ color: (r.quality_score || 0) >= 90 ? '#10B981' : (r.quality_score || 0) >= 70 ? '#F59E0B' : '#EF4444' }}>
                  {r.quality_score || 0}
                </span>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );

  // ── COMPARE VIEW ──
  if (view === 'compare') return (
    <div>
      <div className="mb-6 flex items-center gap-3">
        <button onClick={() => { setView('list'); setCompareResult(null); }}
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-astra-border text-slate-400 transition hover:text-slate-200">
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="flex-1">
          <h1 className="text-xl font-bold tracking-tight">Baseline Comparison</h1>
          {compareResult && (
            <p className="mt-0.5 text-sm text-slate-500">
              {compareResult.baseline_a.name} → {compareResult.baseline_b.name}
            </p>
          )}
        </div>
      </div>

      {comparing ? (
        <div className="flex items-center justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-blue-500" /></div>
      ) : compareResult ? (
        <div>
          {/* Summary cards */}
          <div className="mb-6 grid grid-cols-2 gap-4 xl:grid-cols-4">
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4 text-center">
              <Plus className="mx-auto h-5 w-5 text-emerald-400 mb-1" />
              <div className="text-2xl font-bold text-emerald-400">{compareResult.summary.added}</div>
              <div className="text-[10px] text-slate-500">Added</div>
            </div>
            <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4 text-center">
              <Minus className="mx-auto h-5 w-5 text-red-400 mb-1" />
              <div className="text-2xl font-bold text-red-400">{compareResult.summary.removed}</div>
              <div className="text-[10px] text-slate-500">Removed</div>
            </div>
            <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4 text-center">
              <Edit3 className="mx-auto h-5 w-5 text-amber-400 mb-1" />
              <div className="text-2xl font-bold text-amber-400">{compareResult.summary.modified}</div>
              <div className="text-[10px] text-slate-500">Modified</div>
            </div>
            <div className="rounded-xl border border-astra-border bg-astra-surface p-4 text-center">
              <CheckCircle className="mx-auto h-5 w-5 text-slate-400 mb-1" />
              <div className="text-2xl font-bold text-slate-300">{compareResult.summary.unchanged}</div>
              <div className="text-[10px] text-slate-500">Unchanged</div>
            </div>
          </div>

          {/* Added */}
          {compareResult.added.length > 0 && (
            <div className="mb-4">
              <h3 className="mb-2 flex items-center gap-2 text-sm font-bold text-emerald-400">
                <Plus className="h-4 w-4" /> Added in {compareResult.baseline_b.name}
              </h3>
              <div className="overflow-hidden rounded-xl border border-emerald-500/20 bg-astra-surface">
                {compareResult.added.map((r: any, i: number) => (
                  <div key={i} className="flex items-center gap-3 border-b border-astra-border px-4 py-2.5 last:border-0">
                    <span className="rounded-full px-1.5 py-0.5 text-[9px] font-bold" style={{ background: `${LEVEL_COLORS[r.level as RequirementLevel] || '#6B7280'}20`, color: LEVEL_COLORS[r.level as RequirementLevel] || '#6B7280' }}>{r.level}</span>
                    <span className="font-mono text-xs font-semibold text-emerald-400">{r.req_id}</span>
                    <span className="flex-1 truncate text-sm text-slate-300">{r.title}</span>
                    <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold text-emerald-400">NEW</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Removed */}
          {compareResult.removed.length > 0 && (
            <div className="mb-4">
              <h3 className="mb-2 flex items-center gap-2 text-sm font-bold text-red-400">
                <Minus className="h-4 w-4" /> Removed since {compareResult.baseline_a.name}
              </h3>
              <div className="overflow-hidden rounded-xl border border-red-500/20 bg-astra-surface">
                {compareResult.removed.map((r: any, i: number) => (
                  <div key={i} className="flex items-center gap-3 border-b border-astra-border px-4 py-2.5 last:border-0">
                    <span className="rounded-full px-1.5 py-0.5 text-[9px] font-bold" style={{ background: `${LEVEL_COLORS[r.level as RequirementLevel] || '#6B7280'}20`, color: LEVEL_COLORS[r.level as RequirementLevel] || '#6B7280' }}>{r.level}</span>
                    <span className="font-mono text-xs font-semibold text-red-400 line-through">{r.req_id}</span>
                    <span className="flex-1 truncate text-sm text-slate-400 line-through">{r.title}</span>
                    <span className="rounded-full bg-red-500/15 px-2 py-0.5 text-[10px] font-bold text-red-400">REMOVED</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Modified */}
          {compareResult.modified.length > 0 && (
            <div className="mb-4">
              <h3 className="mb-2 flex items-center gap-2 text-sm font-bold text-amber-400">
                <Edit3 className="h-4 w-4" /> Modified between baselines
              </h3>
              <div className="overflow-hidden rounded-xl border border-amber-500/20 bg-astra-surface">
                {compareResult.modified.map((r: any, i: number) => (
                  <div key={i} className="border-b border-astra-border px-4 py-3 last:border-0">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="font-mono text-xs font-semibold text-amber-400">{r.req_id}</span>
                      <span className="flex-1 truncate text-sm text-slate-200">{r.title}</span>
                      <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold text-amber-400">{r.changes.length} change{r.changes.length !== 1 ? 's' : ''}</span>
                    </div>
                    <div className="ml-4 space-y-1">
                      {r.changes.map((c: any, j: number) => (
                        <div key={j} className="flex items-center gap-2 text-[11px]">
                          <span className="font-semibold text-slate-400 capitalize w-20">{c.field}:</span>
                          {c.baseline_a && <span className="text-red-400/70 line-through">{String(c.baseline_a).substring(0, 60)}{String(c.baseline_a).length > 60 ? '...' : ''}</span>}
                          <span className="text-slate-500">→</span>
                          <span className="text-emerald-400">{String(c.baseline_b).substring(0, 60)}{String(c.baseline_b).length > 60 ? '...' : ''}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* All unchanged */}
          {compareResult.summary.added === 0 && compareResult.summary.removed === 0 && compareResult.summary.modified === 0 && (
            <div className="py-12 text-center">
              <CheckCircle className="mx-auto h-10 w-10 text-emerald-400 mb-3" />
              <div className="text-lg font-bold text-slate-200">No Changes</div>
              <p className="text-sm text-slate-500">These two baselines are identical</p>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );

  return null;
}
