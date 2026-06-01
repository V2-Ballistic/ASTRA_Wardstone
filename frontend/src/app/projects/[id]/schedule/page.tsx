'use client';

/**
 * ASTRA — Schedule (read-only view of the WRENCH master-schedule plugin)
 * ======================================================================
 *
 * v2: ASTRA's project_id IS the key. The Master Schedule plugin scopes
 * every schedule to an ASTRA project — opening this page just asks the
 * plugin "what's the schedule for project N?" No manual linking step.
 *
 * Sub-tabs: Overview · Gantt · Critical Path · Health.
 * All editing happens in WRENCH; "Edit in WRENCH →" deep-links to the
 * workspace with this project pre-selected.
 *
 * No react-query here — ASTRA's frontend uses plain useState + useEffect.
 */

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import {
  CalendarClock, ExternalLink, Loader2, AlertTriangle,
  LayoutDashboard, GanttChart, GitBranch, ShieldCheck,
  CalendarPlus, Target,
} from 'lucide-react';
import clsx from 'clsx';
import { masterScheduleAPI } from '@/lib/api';
import { GanttView } from './GanttView';
import { MilestoneOutline } from './MilestoneOutline';

const WRENCH_BASE_URL = process.env.NEXT_PUBLIC_WRENCH_URL || 'http://192.168.1.74:3030';

type Tab = 'overview' | 'gantt' | 'milestones' | 'critical' | 'health';

interface ProgramResp {
  available: boolean;
  has_schedule: boolean;
  data?: any;
  reason?: string;
}

function useFetch<T>(fn: () => Promise<{ data: T }>, deps: any[] = []) {
  const [state, setState] = useState<{ loading: boolean; data: T | null; error: any }>({
    loading: true, data: null, error: null,
  });
  useEffect(() => {
    let cancelled = false;
    setState({ loading: true, data: null, error: null });
    fn().then((r) => {
      if (!cancelled) setState({ loading: false, data: r.data, error: null });
    }).catch((e) => {
      if (!cancelled) setState({ loading: false, data: null, error: e });
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

export default function SchedulePage() {
  const params = useParams<{ id: string }>();
  const projectId = Number(params.id);
  const [tab, setTab] = useState<Tab>('overview');

  const prog = useFetch<ProgramResp>(() => masterScheduleAPI.program(projectId), [projectId]);

  if (prog.loading) {
    return <div className="p-8"><Loader2 className="h-5 w-5 animate-spin text-slate-500" /></div>;
  }

  if (prog.data && !prog.data.available) {
    return (
      <div className="p-6 max-w-3xl">
        <Header />
        <Unavailable reason="unreachable" />
      </div>
    );
  }

  const hasSchedule = prog.data?.has_schedule;
  if (!hasSchedule) {
    return (
      <div className="p-6 max-w-3xl">
        <Header />
        <div className="mt-6 rounded-xl border border-astra-border bg-astra-surface p-8 text-center">
          <CalendarPlus className="mx-auto mb-3 h-10 w-10 text-blue-400" />
          <div className="text-base font-semibold text-slate-200 mb-2">No schedule yet</div>
          <div className="text-xs text-slate-400 mb-4 max-w-md mx-auto">
            This project has no master schedule yet. Set one up in WRENCH — pick the program dates,
            choose your team structure, and the schedule will appear here automatically.
          </div>
          <a
            href={`${WRENCH_BASE_URL}/master-schedule#project/${projectId}/setup`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500"
          >
            Set up in WRENCH <ExternalLink className="h-3.5 w-3.5" />
          </a>
        </div>
      </div>
    );
  }

  const programInfo = prog.data?.data?.program;

  return (
    <div className="flex flex-col h-full">
      <Header program={programInfo} projectId={projectId} />
      <div className="border-b border-astra-border bg-astra-surface px-4">
        <div className="flex gap-1">
          {([
            { k: 'overview', label: 'Overview', icon: LayoutDashboard },
            { k: 'gantt', label: 'Gantt', icon: GanttChart },
            { k: 'milestones', label: 'Milestones', icon: Target },
            { k: 'critical', label: 'Critical Path', icon: GitBranch },
            { k: 'health', label: 'Health', icon: ShieldCheck },
          ] as { k: Tab; label: string; icon: any }[]).map((t) => {
            const Icon = t.icon;
            const active = tab === t.k;
            return (
              <button key={t.k}
                onClick={() => setTab(t.k)}
                className={clsx(
                  'flex items-center gap-2 px-4 py-2 text-xs font-medium border-b-2',
                  active
                    ? 'border-blue-400 text-blue-400'
                    : 'border-transparent text-slate-400 hover:text-slate-200',
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {t.label}
              </button>
            );
          })}
        </div>
      </div>
      <div className={clsx(
        'flex-1 overflow-auto',
        // Gantt manages its own scroll; other tabs use page padding.
        tab === 'gantt' ? '' : 'p-6',
      )}>
        {tab === 'overview' && <Overview projectId={projectId} />}
        {tab === 'gantt' && <Gantt projectId={projectId} />}
        {tab === 'milestones' && <MilestoneOutline projectId={projectId} />}
        {tab === 'critical' && <CriticalPath projectId={projectId} />}
        {tab === 'health' && <Health projectId={projectId} />}
      </div>
    </div>
  );
}

function Header({ program, projectId }: { program?: any; projectId?: number }) {
  return (
    <div className="px-6 py-4 border-b border-astra-border bg-astra-surface flex items-center">
      <div>
        <div className="flex items-center gap-2">
          <CalendarClock className="h-5 w-5 text-blue-400" />
          <h1 className="text-lg font-bold text-slate-200">Schedule</h1>
          {program?.code && (
            <span className="ml-2 rounded-full bg-blue-500/15 px-2 py-0.5 text-[10px] font-bold text-blue-400 font-mono">
              {program.code}
            </span>
          )}
        </div>
        <div className="text-[11px] text-slate-500 mt-0.5">
          Live mirror of the WRENCH IMS for this project. Editing happens in WRENCH.
        </div>
      </div>
      <div className="flex-1" />
      {projectId !== undefined && (
        <a
          href={`${WRENCH_BASE_URL}/master-schedule#project/${projectId}`}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-1.5 text-xs text-slate-300 hover:text-blue-400 hover:border-blue-400/40"
        >
          Edit in WRENCH <ExternalLink className="h-3 w-3" />
        </a>
      )}
    </div>
  );
}

// ── Overview ────────────────────────────────────────────────────────────

function Overview({ projectId }: { projectId: number }) {
  const q = useFetch<any>(() => masterScheduleAPI.overview(projectId), [projectId]);
  if (q.loading) return <Loader2 className="h-5 w-5 animate-spin text-slate-500" />;
  if (!q.data?.available) return <Unavailable reason={q.data?.reason} />;
  if (!q.data?.has_schedule) return <NoSchedule projectId={projectId} />;
  const d = q.data.data;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        <Gauge title="CPLI" value={d.dcma.cpli} threshold={0.95} subtitle="Critical Path Length Index" />
        <Gauge title="BEI" value={d.dcma.bei} threshold={0.95} subtitle="Baseline Execution Index" />
        <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
          <div className="text-[10px] uppercase tracking-wider text-slate-500">14-point</div>
          <div className="text-2xl font-bold text-slate-200 mt-2 tabular-nums">
            {d.dcma.summary_passed}<span className="text-slate-500 text-sm">/{d.dcma.summary_total}</span>
          </div>
          <div className="text-[10px] text-slate-500 mt-1">metrics passing</div>
        </div>
      </div>
      <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
        <div className="text-xs font-semibold text-slate-300 mb-3 uppercase tracking-wide">Program Milestones</div>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-[10px] text-slate-500 uppercase tracking-wide border-b border-astra-border">
              <th className="text-left py-2">Milestone</th>
              <th className="text-left py-2">Forecast</th>
              <th className="text-left py-2">Baseline</th>
              <th className="text-left py-2">Status</th>
              <th className="text-right py-2">% complete</th>
            </tr>
          </thead>
          <tbody>
            {(d.milestones ?? []).map((m: any) => (
              <tr key={m.task_id} className="border-b border-astra-border/40">
                <td className="py-2">
                  {m.is_critical && <span className="inline-block w-1.5 h-1.5 rounded-full bg-red-500 mr-2 align-middle"></span>}
                  <span className="font-mono text-[10px] text-slate-500 mr-2">{m.task_id}</span>
                  <span className="text-slate-200">{m.name}</span>
                </td>
                <td className="py-2 tabular-nums text-slate-300">{m.forecast_finish ?? '—'}</td>
                <td className="py-2 tabular-nums text-slate-500">{m.baseline_finish ?? '—'}</td>
                <td className="py-2"><StatusPill status={m.status} /></td>
                <td className="py-2 text-right tabular-nums">{m.percent_complete}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Gantt (read-only, real visual) ──────────────────────────────────────

function Gantt({ projectId }: { projectId: number }) {
  const q = useFetch<any>(() => masterScheduleAPI.gantt(projectId), [projectId]);
  if (q.loading) return <div className="p-6"><Loader2 className="h-5 w-5 animate-spin text-slate-500" /></div>;
  if (!q.data?.available) return <div className="p-6"><Unavailable reason={q.data?.reason} /></div>;
  if (!q.data?.has_schedule) return <div className="p-6"><NoSchedule projectId={projectId} /></div>;
  return <GanttView data={q.data.data} projectId={projectId} wrenchUrl={WRENCH_BASE_URL} />;
}

// ── Critical Path ───────────────────────────────────────────────────────

function CriticalPath({ projectId }: { projectId: number }) {
  const q = useFetch<any>(() => masterScheduleAPI.criticalPath(projectId), [projectId]);
  if (q.loading) return <Loader2 className="h-5 w-5 animate-spin text-slate-500" />;
  if (!q.data?.available) return <Unavailable reason={q.data?.reason} />;
  if (!q.data?.has_schedule) return <NoSchedule projectId={projectId} />;
  const tasks = (q.data.data.tasks ?? []) as any[];
  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface overflow-hidden">
      <div className="px-4 py-3 border-b border-astra-border text-xs font-semibold uppercase tracking-wider text-slate-400">
        Critical Path · {tasks.length} tasks
      </div>
      <div>
        {tasks.map((t: any, i: number) => (
          <div key={t.task_id} className="grid grid-cols-12 gap-2 px-4 py-2 text-xs border-b border-astra-border/30">
            <div className="col-span-1 tabular-nums text-slate-500">{i + 1}</div>
            <div className="col-span-2 font-mono text-[10px] text-slate-400 flex items-center gap-1.5">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-red-500"></span>
              {t.task_id}
            </div>
            <div className="col-span-4 text-slate-200">{t.name}</div>
            <div className="col-span-2 text-slate-400">{t.owner || '—'}</div>
            <div className="col-span-2 tabular-nums text-slate-400">{t.start_date ?? '—'} → {t.finish_date ?? '—'}</div>
            <div className="col-span-1 text-right"><StatusPill status={t.status} /></div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Health ──────────────────────────────────────────────────────────────

function Health({ projectId }: { projectId: number }) {
  const q = useFetch<any>(() => masterScheduleAPI.dcma(projectId), [projectId]);
  if (q.loading) return <Loader2 className="h-5 w-5 animate-spin text-slate-500" />;
  if (!q.data?.available) return <Unavailable reason={q.data?.reason} />;
  if (!q.data?.has_schedule) return <NoSchedule projectId={projectId} />;
  const d = q.data.data;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3 text-sm">
        <div className="rounded-xl border border-astra-border bg-astra-surface p-3">
          <div className="text-[10px] uppercase text-slate-500">CPLI</div>
          <div className="text-xl font-bold tabular-nums">{d.cpli.toFixed(2)}</div>
        </div>
        <div className="rounded-xl border border-astra-border bg-astra-surface p-3">
          <div className="text-[10px] uppercase text-slate-500">BEI</div>
          <div className="text-xl font-bold tabular-nums">{d.bei.toFixed(2)}</div>
        </div>
        <div className="rounded-xl border border-astra-border bg-astra-surface p-3">
          <div className="text-[10px] uppercase text-slate-500">Passing</div>
          <div className="text-xl font-bold tabular-nums">
            {d.summary_passed}<span className="text-slate-500">/{d.summary_total}</span>
          </div>
        </div>
      </div>
      <div className="rounded-xl border border-astra-border bg-astra-surface overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-[10px] uppercase text-slate-500 bg-astra-surface-alt border-b border-astra-border">
              <th className="text-left p-2 w-8">#</th>
              <th className="text-left p-2">Metric</th>
              <th className="text-left p-2 w-24">Value</th>
              <th className="text-left p-2 w-24">Threshold</th>
              <th className="text-left p-2 w-16">Status</th>
            </tr>
          </thead>
          <tbody>
            {d.metrics.map((m: any) => (
              <tr key={m.number} className={clsx('border-b border-astra-border/30', !m.passed && 'bg-red-500/5')}>
                <td className="p-2 tabular-nums text-slate-500">{m.number}</td>
                <td className="p-2">
                  <div className="font-semibold text-slate-200">{m.name}</div>
                  <div className="text-[10px] text-slate-500">{m.description}</div>
                </td>
                <td className="p-2 tabular-nums font-semibold">{m.value_label}</td>
                <td className="p-2 tabular-nums text-slate-500">{m.threshold}</td>
                <td className="p-2">
                  <span className={clsx(
                    'rounded-full px-2 py-0.5 text-[9px] font-bold uppercase font-mono',
                    m.passed ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400',
                  )}>{m.passed ? 'pass' : 'fail'}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Bits ────────────────────────────────────────────────────────────────

function Gauge({ title, value, threshold, subtitle }: { title: string; value: number; threshold: number; subtitle: string }) {
  const ok = value >= threshold;
  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{subtitle}</div>
      <div className="flex items-baseline gap-2 mt-2">
        <span className={clsx('text-3xl font-bold tabular-nums', ok ? 'text-emerald-400' : 'text-red-400')}>
          {value.toFixed(2)}
        </span>
        <span className="text-[10px] text-slate-500">≥ {threshold.toFixed(2)} target</span>
      </div>
      <div className="text-xs font-semibold text-slate-300 mt-1">{title}</div>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const map: Record<string, { bg: string; text: string; label: string }> = {
    not_started: { bg: 'bg-slate-700/40', text: 'text-slate-400', label: 'Not Started' },
    in_progress: { bg: 'bg-blue-500/15',  text: 'text-blue-400',  label: 'In Progress' },
    complete:    { bg: 'bg-emerald-500/15', text: 'text-emerald-400', label: 'Complete' },
    at_risk:     { bg: 'bg-amber-500/15', text: 'text-amber-400', label: 'At Risk' },
    blocked:     { bg: 'bg-red-500/15',   text: 'text-red-400',   label: 'Blocked' },
  };
  const m = map[status] ?? map.not_started;
  return <span className={clsx('rounded-full px-2 py-0.5 text-[9px] font-bold uppercase font-mono', m.bg, m.text)}>{m.label}</span>;
}

function Unavailable({ reason }: { reason?: string }) {
  return (
    <div className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-6 text-center">
      <AlertTriangle className="mx-auto h-8 w-8 text-amber-400 mb-2" />
      <div className="text-sm font-semibold text-slate-200 mb-1">Master Schedule unavailable</div>
      <div className="text-xs text-slate-400">
        {reason === 'unreachable'
          ? 'Could not reach the WRENCH master-schedule plugin. Is the WRENCH stack running?'
          : 'The plugin is not reachable right now.'}
      </div>
    </div>
  );
}

function NoSchedule({ projectId }: { projectId: number }) {
  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface p-6 text-center">
      <CalendarPlus className="mx-auto h-8 w-8 text-blue-400 mb-2" />
      <div className="text-sm font-semibold text-slate-200 mb-1">No schedule configured for this project</div>
      <div className="text-xs text-slate-400 mb-3">Set one up in WRENCH.</div>
      <a
        href={`${WRENCH_BASE_URL}/master-schedule#project/${projectId}/setup`}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500"
      >
        Set up in WRENCH <ExternalLink className="h-3 w-3" />
      </a>
    </div>
  );
}
