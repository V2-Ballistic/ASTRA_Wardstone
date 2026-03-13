'use client';

/**
 * ASTRA — Baselines (Project-Scoped)
 * File: frontend/src/app/projects/[id]/baselines/page.tsx
 *
 * Fixed: snapshot fields use plain names (req_id, title, level)
 *        not _snapshot suffixed names
 */

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Archive, Clock, Loader2, RefreshCw, Plus, ArrowLeftRight, ChevronRight, Trash2, X, GitBranch, FileText, CheckCircle, AlertTriangle, Minus, Edit3 } from 'lucide-react';
import clsx from 'clsx';
import { baselinesAPI, projectsAPI } from '@/lib/api';
import { STATUS_COLORS, STATUS_LABELS, LEVEL_COLORS, type RequirementStatus, type RequirementLevel } from '@/lib/types';

export default function BaselinesPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);

  const [projectCode, setProjectCode] = useState('');
  const [baselines, setBaselines] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<'list' | 'detail' | 'compare'>('list');
  const [selected, setSelected] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [compareA, setCompareA] = useState<number | null>(null);
  const [compareB, setCompareB] = useState<number | null>(null);
  const [compareResult, setCompareResult] = useState<any>(null);
  const [comparing, setComparing] = useState(false);

  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [creating, setCreating] = useState(false);

  useEffect(() => { projectsAPI.get(projectId).then(r => setProjectCode(r.data?.code || '')).catch(() => {}); }, [projectId]);

  const fetchBaselines = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try { const res = await baselinesAPI.list(projectId); setBaselines(res.data?.baselines || res.data || []); } catch {}
    setLoading(false);
  }, [projectId]);

  useEffect(() => { fetchBaselines(); }, [fetchBaselines]);

  const openDetail = async (id: number) => {
    setDetailLoading(true); setView('detail');
    try { const res = await baselinesAPI.get(id); setSelected(res.data); } catch { setView('list'); }
    setDetailLoading(false);
  };

  const runCompare = async () => {
    if (!compareA || !compareB) return;
    setComparing(true); setView('compare');
    try { const res = await baselinesAPI.compare(compareA, compareB); setCompareResult(res.data); } catch { setView('list'); }
    setComparing(false);
  };

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try { await baselinesAPI.create({ name: newName, description: newDesc, project_id: projectId }); setShowCreate(false); setNewName(''); setNewDesc(''); await fetchBaselines(); } catch {}
    setCreating(false);
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this baseline?')) return;
    try { await baselinesAPI.delete(id); await fetchBaselines(); setView('list'); } catch {}
  };

  // Helper: get field from snapshot row (handles both plain and _snapshot suffixed names)
  const sf = (r: any, field: string) => r[field] || r[`${field}_snapshot`] || '';

  const formatDate = (iso: string) => iso ? new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—';

  if (loading) return <div className="flex min-h-[60vh] items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-blue-500" /></div>;

  return (
    <div>
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Baselines</h1>
          <p className="mt-0.5 text-sm text-slate-500">{projectCode} · Snapshots and change control</p>
        </div>
        <div className="flex gap-2">
          {view !== 'list' && <button onClick={() => setView('list')} className="rounded-lg border border-astra-border px-3 py-2 text-xs text-slate-400 hover:text-slate-200">← Back</button>}
          <button onClick={() => setShowCreate(true)} className="flex items-center gap-1.5 rounded-lg bg-blue-500 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-600"><Plus className="h-3.5 w-3.5" /> Create Baseline</button>
          <button onClick={fetchBaselines} className="rounded-full border border-astra-border p-2 text-slate-400 hover:text-slate-200"><RefreshCw className="h-3.5 w-3.5" /></button>
        </div>
      </div>

      {/* List view */}
      {view === 'list' && (
        <>
          {baselines.length === 0 ? (
            <div className="rounded-xl border border-dashed border-astra-border-light bg-astra-surface-alt py-16 text-center">
              <Archive className="mx-auto mb-3 h-8 w-8 text-slate-600" />
              <h3 className="text-sm font-semibold text-slate-300 mb-1">No Baselines Yet</h3>
              <p className="text-xs text-slate-500">Create a baseline to snapshot your current requirements state.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {baselines.map((bl) => (
                <div key={bl.id} className="flex items-center gap-4 rounded-xl border border-astra-border bg-astra-surface p-4 transition hover:border-blue-500/20">
                  <Archive className="h-5 w-5 text-blue-400 flex-shrink-0" />
                  <div className="flex-1 min-w-0 cursor-pointer" onClick={() => openDetail(bl.id)}>
                    <div className="text-sm font-bold text-slate-200">{bl.name}</div>
                    <div className="text-xs text-slate-500">{bl.requirements_count || 0} requirements · {formatDate(bl.created_at)}</div>
                    {bl.description && <p className="mt-0.5 text-[11px] text-slate-500 truncate">{bl.description}</p>}
                  </div>
                  <div className="flex gap-1.5">
                    <button onClick={() => setCompareA(bl.id)} className="rounded-lg border border-astra-border px-2 py-1 text-[10px] text-slate-400 hover:text-slate-200">
                      {compareA === bl.id ? 'A ✓' : 'Set A'}
                    </button>
                    <button onClick={() => setCompareB(bl.id)} className="rounded-lg border border-astra-border px-2 py-1 text-[10px] text-slate-400 hover:text-slate-200">
                      {compareB === bl.id ? 'B ✓' : 'Set B'}
                    </button>
                    <button onClick={() => handleDelete(bl.id)} className="rounded-lg border border-red-500/20 p-1 text-red-400/50 hover:text-red-400"><Trash2 className="h-3 w-3" /></button>
                  </div>
                </div>
              ))}
              {compareA && compareB && compareA !== compareB && (
                <button onClick={runCompare} className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-500 py-2.5 text-xs font-semibold text-white hover:bg-blue-600">
                  <ArrowLeftRight className="h-3.5 w-3.5" /> Compare A vs B
                </button>
              )}
            </div>
          )}
        </>
      )}

      {/* Detail view */}
      {view === 'detail' && (
        detailLoading ? <div className="flex items-center justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-blue-500" /></div> : selected ? (
          <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
            <h2 className="text-base font-bold text-slate-100 mb-1">{selected.name}</h2>
            <p className="text-xs text-slate-500 mb-4">{selected.requirements_count || selected.requirements?.length || 0} requirements · {formatDate(selected.created_at)}</p>
            {selected.requirements?.length > 0 && (
              <div className="overflow-hidden rounded-lg border border-astra-border">
                {selected.requirements.map((r: any, i: number) => {
                  const lvl = (sf(r, 'level') || 'L1') as RequirementLevel;
                  const st = (sf(r, 'status') || 'draft') as RequirementStatus;
                  const sc = STATUS_COLORS[st];
                  return (
                    <div key={i} className="flex items-center gap-3 border-b border-astra-border/50 px-4 py-2.5 last:border-0">
                      <span className="rounded-full px-1.5 py-0.5 text-[9px] font-bold" style={{ background: `${LEVEL_COLORS[lvl]}20`, color: LEVEL_COLORS[lvl] }}>{lvl}</span>
                      <span className="font-mono text-xs font-semibold text-blue-400">{sf(r, 'req_id')}</span>
                      <span className="flex-1 truncate text-xs text-slate-300">{sf(r, 'title')}</span>
                      <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold" style={{ background: sc?.bg, color: sc?.text }}>
                        {STATUS_LABELS[st] || st}
                      </span>
                      <span className="text-[10px] font-mono" style={{ color: (r.quality_score || 0) >= 80 ? '#10B981' : '#F59E0B' }}>
                        {r.quality_score || '—'}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ) : null
      )}

      {/* Compare view */}
      {view === 'compare' && (
        comparing ? <div className="flex items-center justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-blue-500" /></div> : compareResult ? (
          <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
            <h2 className="text-base font-bold text-slate-100 mb-3">Baseline Comparison</h2>
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3 text-center">
                <Plus className="mx-auto h-4 w-4 text-emerald-400 mb-1" />
                <div className="text-lg font-bold text-emerald-400">{compareResult.summary?.added ?? compareResult.added?.length ?? 0}</div>
                <div className="text-[10px] text-slate-500">Added</div>
              </div>
              <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3 text-center">
                <Minus className="mx-auto h-4 w-4 text-red-400 mb-1" />
                <div className="text-lg font-bold text-red-400">{compareResult.summary?.removed ?? compareResult.removed?.length ?? 0}</div>
                <div className="text-[10px] text-slate-500">Removed</div>
              </div>
              <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-center">
                <Edit3 className="mx-auto h-4 w-4 text-amber-400 mb-1" />
                <div className="text-lg font-bold text-amber-400">{compareResult.summary?.modified ?? compareResult.modified?.length ?? 0}</div>
                <div className="text-[10px] text-slate-500">Changed</div>
              </div>
            </div>
            {compareResult.added?.length > 0 && (
              <div className="mb-3">
                <h4 className="text-[10px] font-semibold uppercase text-emerald-400 mb-1">Added</h4>
                {compareResult.added.map((r: any, i: number) => (
                  <div key={i} className="text-xs text-slate-300 py-0.5">
                    <span className="font-mono text-blue-400">{sf(r, 'req_id')}</span> {sf(r, 'title')}
                  </div>
                ))}
              </div>
            )}
            {compareResult.removed?.length > 0 && (
              <div className="mb-3">
                <h4 className="text-[10px] font-semibold uppercase text-red-400 mb-1">Removed</h4>
                {compareResult.removed.map((r: any, i: number) => (
                  <div key={i} className="text-xs text-slate-300 py-0.5 line-through opacity-60">
                    <span className="font-mono text-blue-400">{sf(r, 'req_id')}</span> {sf(r, 'title')}
                  </div>
                ))}
              </div>
            )}
            {(compareResult.modified?.length > 0) && (
              <div>
                <h4 className="text-[10px] font-semibold uppercase text-amber-400 mb-1">Changed</h4>
                {compareResult.modified.map((r: any, i: number) => (
                  <div key={i} className="text-xs text-slate-300 py-0.5">
                    <span className="font-mono text-blue-400">{r.req_id}</span> {r.title}{' '}
                    <span className="text-[10px] text-amber-400">
                      {Array.isArray(r.changes) ? r.changes.map((c: any) => typeof c === 'string' ? c : c.field).join(', ') : ''}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : null
      )}

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-astra-border bg-astra-surface p-6 shadow-2xl">
            <h3 className="text-sm font-bold text-slate-100 mb-4">Create Baseline</h3>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">Name</label>
                <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="e.g. SRR Baseline v1.0"
                  className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
              </div>
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">Description</label>
                <textarea value={newDesc} onChange={(e) => setNewDesc(e.target.value)} rows={2} placeholder="Optional description…"
                  className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
              </div>
            </div>
            <div className="mt-4 flex justify-between">
              <button onClick={() => setShowCreate(false)} className="rounded-lg border border-astra-border px-4 py-2 text-xs text-slate-400 hover:text-slate-200">Cancel</button>
              <button onClick={handleCreate} disabled={!newName.trim() || creating}
                className="rounded-lg bg-blue-500 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-600 disabled:opacity-50">
                {creating ? 'Creating…' : 'Create Baseline'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
