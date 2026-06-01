'use client';

/**
 * ASTRA — Milestones outline tab (Feature 3).
 *
 * Read-only structured view of the IMP hierarchy for this project:
 *
 *   Event (PDR Completed, target Aug 12)
 *     Accomplishment 1
 *       Criterion A — 3 tasks (% rollup)
 *         AV-DES-02 — Avionics preliminary design  · in progress · 60%
 *         ...
 *
 * Lets a program manager see "what needs to happen before PDR" without
 * opening WRENCH. Dates are editable only in WRENCH (the page surfaces
 * a "Edit in WRENCH →" link).
 *
 * Data comes from two plugin endpoints: `/projects/{id}/imp` (tree)
 * and `/projects/{id}/tasks` (so we can attach tasks to criteria and
 * compute rollup status). Both are proxied via ASTRA.
 */

import { ChevronDown, ChevronRight, CheckCircle2, Circle, AlertTriangle, ExternalLink, Calendar, Loader2 } from 'lucide-react';
import clsx from 'clsx';
import { useEffect, useMemo, useState } from 'react';
import { masterScheduleAPI } from '@/lib/api';

const WRENCH_BASE_URL = process.env.NEXT_PUBLIC_WRENCH_URL || 'http://192.168.1.74:3030';

interface Props {
  projectId: number;
}

function useFetch<T>(fn: () => Promise<T>, deps: any[] = []) {
  const [state, setState] = useState<{ loading: boolean; data: T | null; error: any }>({
    loading: true, data: null, error: null,
  });
  useEffect(() => {
    let cancelled = false;
    setState({ loading: true, data: null, error: null });
    fn().then((data) => { if (!cancelled) setState({ loading: false, data, error: null }); })
        .catch((e) => { if (!cancelled) setState({ loading: false, data: null, error: e }); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

export function MilestoneOutline({ projectId }: Props) {
  // We piggyback on the gantt-data endpoint to get the task list (which
  // includes imp_criterion_id) without adding new ASTRA proxy routes —
  // the IMP tree is a separate fetch.
  const gantt = useFetch<any>(() => masterScheduleAPI.gantt(projectId).then((r) => r.data), [projectId]);
  const imp = useFetch<any>(() => masterScheduleAPI.imp(projectId).then((r) => r.data), [projectId]);

  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const toggle = (k: string) => setExpanded((s) => {
    const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n;
  });

  if (gantt.loading || imp.loading) {
    return <Loader2 className="h-5 w-5 animate-spin text-slate-500" />;
  }
  const ganttData = gantt.data?.data;
  const impData = imp.data?.data;
  if (!ganttData || !impData) {
    return <div className="text-sm text-slate-500">Could not load milestone tree.</div>;
  }
  const events = impData.events ?? [];
  const tasks = ganttData.tasks ?? [];
  const tasksByCriterion = new Map<number, any[]>();
  for (const t of tasks) {
    if (t.imp_criterion_id) {
      const list = tasksByCriterion.get(t.imp_criterion_id) ?? [];
      list.push(t);
      tasksByCriterion.set(t.imp_criterion_id, list);
    }
  }

  return (
    <div className="space-y-3">
      <div className="text-[11px] text-slate-500 flex items-center gap-2">
        Events → Accomplishments → Criteria → Tasks. Edit milestone dates in WRENCH.
        <a href={`${WRENCH_BASE_URL}/master-schedule#project/${projectId}/imp`}
           target="_blank" rel="noopener noreferrer"
           className="inline-flex items-center gap-1 text-blue-400 hover:text-blue-300">
          Edit dates in WRENCH <ExternalLink className="h-3 w-3" />
        </a>
      </div>
      <div className="space-y-2">
        {events.map((ev: any) => {
          const evKey = `ev-${ev.id}`;
          const evOpen = expanded.has(evKey);
          const rollup = computeRollup(ev, tasksByCriterion);
          return (
            <div key={ev.id} className="rounded-xl border border-astra-border bg-astra-surface overflow-hidden">
              <button onClick={() => toggle(evKey)}
                      className="w-full flex items-center gap-3 px-4 py-3 hover:bg-astra-surface-alt text-left">
                {evOpen ? <ChevronDown className="h-3.5 w-3.5 text-slate-400" /> : <ChevronRight className="h-3.5 w-3.5 text-slate-400" />}
                <RollupIcon pct={rollup.pct} size={16} />
                <span className="text-sm font-bold text-slate-200">{ev.name}</span>
                <span className="inline-flex items-center gap-1 text-[11px] text-slate-500">
                  <Calendar className="h-3 w-3" />
                  {ev.target_date ?? 'no target'}
                </span>
                <span className="flex-1" />
                <ProgressPill pct={rollup.pct} />
                <span className="text-[11px] tabular-nums text-slate-400 min-w-[36px] text-right">
                  {rollup.pct}%
                </span>
              </button>
              {evOpen && (
                <div className="border-t border-astra-border/40 px-3 py-2 pl-9 space-y-2">
                  {ev.accomplishments.map((a: any) => {
                    const aKey = `ac-${a.id}`;
                    const aOpen = expanded.has(aKey);
                    const aRollup = computeAccRollup(a, tasksByCriterion);
                    return (
                      <div key={a.id}>
                        <button onClick={() => toggle(aKey)}
                                className="w-full flex items-center gap-2 px-2 py-1.5 hover:bg-astra-surface-alt rounded text-left">
                          {aOpen ? <ChevronDown className="h-3 w-3 text-slate-400" /> : <ChevronRight className="h-3 w-3 text-slate-400" />}
                          <RollupIcon pct={aRollup.pct} size={12} />
                          <span className="text-xs text-slate-300">{a.name}</span>
                          <span className="flex-1" />
                          <ProgressPill pct={aRollup.pct} />
                          <span className="text-[10px] tabular-nums text-slate-500 min-w-[30px] text-right">{aRollup.pct}%</span>
                        </button>
                        {aOpen && (
                          <div className="ml-6 mt-1 space-y-1">
                            {a.criteria.map((c: any) => {
                              const cTasks = tasksByCriterion.get(c.id) ?? [];
                              const pct = cTasks.length
                                ? Math.round(cTasks.reduce((s: number, t: any) => s + t.percent_complete, 0) / cTasks.length)
                                : 0;
                              const cKey = `cr-${c.id}`;
                              const cOpen = expanded.has(cKey);
                              return (
                                <div key={c.id}>
                                  <button onClick={() => toggle(cKey)}
                                          className="w-full flex items-center gap-2 px-2 py-1 hover:bg-astra-surface-alt rounded text-left">
                                    {cOpen ? <ChevronDown className="h-3 w-3 text-slate-400" /> : <ChevronRight className="h-3 w-3 text-slate-400" />}
                                    <RollupIcon pct={pct} size={11} />
                                    <span className="text-[11px] text-slate-400 flex-1">{c.name}</span>
                                    <span className="font-mono text-[10px] text-slate-500">{cTasks.length} task{cTasks.length === 1 ? '' : 's'}</span>
                                    <ProgressPill pct={pct} />
                                  </button>
                                  {cOpen && cTasks.length > 0 && (
                                    <div className="ml-6 mt-1 space-y-0.5">
                                      {cTasks.map((t: any) => (
                                        <div key={t.task_id} className="grid grid-cols-12 gap-2 px-2 py-1 text-[11px] border-l border-astra-border/40 ml-2">
                                          <div className="col-span-2 font-mono text-slate-500 flex items-center gap-1">
                                            {t.is_critical && <span className="w-1 h-1 rounded-full bg-red-500" />}
                                            {t.task_id}
                                          </div>
                                          <div className="col-span-5 text-slate-300">{t.name}</div>
                                          <div className="col-span-2 tabular-nums text-slate-500">{t.start_date ?? '—'} → {t.finish_date ?? '—'}</div>
                                          <div className="col-span-1 text-right tabular-nums">
                                            <span className={t.total_float_days === 0 ? 'text-red-400' : t.total_float_days! < 0 ? 'text-red-500' : 'text-slate-500'}>
                                              {t.total_float_days ?? '—'}d
                                            </span>
                                          </div>
                                          <div className="col-span-2 text-right"><TaskStatusPill status={t.status} /></div>
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function computeRollup(ev: any, tasksByCriterion: Map<number, any[]>) {
  let total = 0, sum = 0;
  for (const a of ev.accomplishments) {
    for (const c of a.criteria) {
      for (const t of tasksByCriterion.get(c.id) ?? []) { total += 1; sum += t.percent_complete; }
    }
  }
  return { pct: total ? Math.round(sum / total) : 0 };
}

function computeAccRollup(a: any, tasksByCriterion: Map<number, any[]>) {
  let total = 0, sum = 0;
  for (const c of a.criteria) {
    for (const t of tasksByCriterion.get(c.id) ?? []) { total += 1; sum += t.percent_complete; }
  }
  return { pct: total ? Math.round(sum / total) : 0 };
}

function RollupIcon({ pct, size = 14 }: { pct: number; size?: number }) {
  if (pct >= 100) return <CheckCircle2 size={size} className="text-emerald-400" />;
  if (pct > 0) return <AlertTriangle size={size} className="text-amber-400" />;
  return <Circle size={size} className="text-slate-600" />;
}

function ProgressPill({ pct }: { pct: number }) {
  return (
    <span className="inline-block bg-astra-surface-alt rounded-full overflow-hidden" style={{ width: 70, height: 6 }}>
      <span className={clsx('block h-full', pct >= 100 ? 'bg-emerald-500' : 'bg-blue-500')}
            style={{ width: `${pct}%` }} />
    </span>
  );
}

function TaskStatusPill({ status }: { status: string }) {
  const map: Record<string, { bg: string; text: string }> = {
    not_started: { bg: 'bg-slate-700/40', text: 'text-slate-400' },
    in_progress: { bg: 'bg-blue-500/15', text: 'text-blue-400' },
    complete: { bg: 'bg-emerald-500/15', text: 'text-emerald-400' },
    at_risk: { bg: 'bg-amber-500/15', text: 'text-amber-400' },
    blocked: { bg: 'bg-red-500/15', text: 'text-red-400' },
  };
  const m = map[status] ?? map.not_started;
  return <span className={clsx('rounded-full px-1.5 py-0.5 text-[8px] font-bold uppercase font-mono', m.bg, m.text)}>{status.replace(/_/g, ' ')}</span>;
}
