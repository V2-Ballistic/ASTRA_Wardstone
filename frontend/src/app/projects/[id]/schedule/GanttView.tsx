'use client';

/**
 * ASTRA — read-only visual Gantt for the project's Master Schedule.
 *
 * Mirrors the WRENCH workspace's SVG Gantt renderer but in ASTRA's
 * styling and without editing. Team-grouped rows, milestone diamonds,
 * dependency arrows (FS/SS/FF/SF), critical-path glow, baseline ghost
 * bars, today line, weekend tint, day/week/month zoom, L1–L4 view
 * filters.
 *
 * Data comes from `/api/v1/projects/{id}/schedule/gantt` which proxies
 * to the WRENCH plugin. Pure useState — no react-query dep.
 */

import { useEffect, useMemo, useState } from 'react';
import { ExternalLink, Loader2, Search } from 'lucide-react';
import clsx from 'clsx';

const ROW_H = 28;
const HEADER_H = 56;
const LABEL_W = 320;

type Scale = 'day' | 'week' | 'month';
type LevelView = 'L1' | 'L2' | 'L3' | 'L4';

interface Props {
  data: any; // the gantt payload — { program, dev_lines, tasks, dependencies }
  wrenchUrl: string;
  projectId: number;
}

export function GanttView({ data, wrenchUrl, projectId }: Props) {
  const [scale, setScale] = useState<Scale>('week');
  const [view, setView] = useState<LevelView>('L4');
  const [filterTeam, setFilterTeam] = useState<string>('');
  const [filterStatus, setFilterStatus] = useState<string>('');
  const [search, setSearch] = useState('');
  const [criticalOnly, setCriticalOnly] = useState(false);
  const [collapsedTeams, setCollapsedTeams] = useState<Set<string>>(new Set());
  const [hoverTask, setHoverTask] = useState<any | null>(null);
  const [hoverPos, setHoverPos] = useState<{ x: number; y: number } | null>(null);

  const dayPx = scale === 'day' ? 26 : scale === 'week' ? 13 : 6;

  const { groupedTasks, taskById, dayRange } = useGanttModel({
    data, view, filterTeam, filterStatus, search, criticalOnly,
  });

  const dayCount = dayRange ? daysBetween(dayRange.start, dayRange.end) + 1 : 0;

  const totalRows = useMemo(() => {
    let n = 0;
    for (const g of groupedTasks) {
      n += 1; // team header
      if (!collapsedTeams.has(g.line.code)) {
        for (const s of g.sections) { n += 1; n += s.tasks.length; }
      }
    }
    return n;
  }, [groupedTasks, collapsedTeams]);

  if (!dayRange) {
    return <div className="p-8 text-slate-500 text-sm">No schedule data.</div>;
  }

  return (
    <div className="flex flex-col h-full -mx-6 -my-6">
      <Toolbar
        scale={scale} setScale={setScale}
        view={view} setView={setView}
        filterTeam={filterTeam} setFilterTeam={setFilterTeam}
        filterStatus={filterStatus} setFilterStatus={setFilterStatus}
        search={search} setSearch={setSearch}
        criticalOnly={criticalOnly} setCriticalOnly={setCriticalOnly}
        teams={data.dev_lines ?? []}
        taskCount={taskById.size}
        wrenchUrl={wrenchUrl}
        projectId={projectId}
      />
      <div className="flex-1 overflow-auto bg-astra-bg relative">
        <div style={{
          position: 'relative',
          width: LABEL_W + dayCount * dayPx,
          minHeight: HEADER_H + totalRows * ROW_H + 24,
        }}>
          <Header dayRange={dayRange} dayPx={dayPx} scale={scale} />
          <Body
            rangeStart={dayRange.start}
            dayPx={dayPx}
            dayCount={dayCount}
            groupedTasks={groupedTasks}
            collapsedTeams={collapsedTeams}
            toggleTeam={(code: string) => setCollapsedTeams((s) => {
              const n = new Set(s);
              if (n.has(code)) n.delete(code); else n.add(code);
              return n;
            })}
            dependencies={data.dependencies ?? []}
            taskById={taskById}
            onHover={(task: any, e: any) => {
              if (task) {
                setHoverTask(task);
                setHoverPos({ x: e.clientX, y: e.clientY });
              } else {
                setHoverTask(null);
              }
            }}
          />
        </div>
        {hoverTask && hoverPos && (
          <Tooltip task={hoverTask} pos={hoverPos} teams={data.dev_lines ?? []} />
        )}
      </div>
    </div>
  );
}

// ── Toolbar ─────────────────────────────────────────────────────────────

function Toolbar({
  scale, setScale, view, setView, filterTeam, setFilterTeam,
  filterStatus, setFilterStatus, search, setSearch,
  criticalOnly, setCriticalOnly, teams, taskCount, wrenchUrl, projectId,
}: any) {
  return (
    <div className="px-4 py-2 border-b border-astra-border bg-astra-surface flex items-center gap-2 flex-wrap text-xs">
      <span className="text-slate-500">{taskCount} tasks</span>
      <div className="flex-1" />
      <Segment items={[
        { v: 'L1', label: 'L1' }, { v: 'L2', label: 'L2' },
        { v: 'L3', label: 'L3' }, { v: 'L4', label: 'L4' },
      ]} value={view} onChange={(v: any) => setView(v)} />
      <Segment items={[
        { v: 'day', label: 'Day' }, { v: 'week', label: 'Week' }, { v: 'month', label: 'Month' },
      ]} value={scale} onChange={(v: any) => setScale(v)} />
      <select className="bg-astra-surface-alt border border-astra-border rounded px-2 py-1 text-xs text-slate-200"
              value={filterTeam} onChange={(e) => setFilterTeam(e.target.value)}>
        <option value="">All teams</option>
        {teams.map((t: any) => (
          <option key={t.code} value={t.code}>{t.code} · {t.name}</option>
        ))}
      </select>
      <select className="bg-astra-surface-alt border border-astra-border rounded px-2 py-1 text-xs text-slate-200"
              value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
        <option value="">Any status</option>
        <option value="not_started">Not Started</option>
        <option value="in_progress">In Progress</option>
        <option value="complete">Complete</option>
        <option value="at_risk">At Risk</option>
        <option value="blocked">Blocked</option>
      </select>
      <label className={clsx(
        'inline-flex items-center gap-1 px-2 py-1 rounded border cursor-pointer',
        criticalOnly ? 'bg-red-500/10 border-red-500 text-red-400' : 'bg-astra-surface-alt border-astra-border text-slate-400'
      )}>
        <input type="checkbox" checked={criticalOnly} onChange={(e) => setCriticalOnly(e.target.checked)}
               className="accent-red-500" />
        Critical only
      </label>
      <div className="relative">
        <Search className="h-3 w-3 absolute left-2 top-1/2 -translate-y-1/2 text-slate-500" />
        <input className="bg-astra-surface-alt border border-astra-border rounded pl-7 pr-2 py-1 text-xs text-slate-200 w-44"
               placeholder="Search task or ID…" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <a href={`${wrenchUrl}/master-schedule#project/${projectId}/gantt`}
         target="_blank" rel="noopener noreferrer"
         className="inline-flex items-center gap-1 rounded border border-astra-border bg-astra-surface-alt px-2 py-1 text-xs text-slate-300 hover:text-blue-400">
        Edit in WRENCH <ExternalLink className="h-3 w-3" />
      </a>
    </div>
  );
}

function Segment({ items, value, onChange }: { items: { v: string; label: string }[]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="inline-flex bg-astra-surface-alt border border-astra-border rounded p-0.5">
      {items.map((it) => (
        <button key={it.v} onClick={() => onChange(it.v)}
                className={clsx(
                  'px-2 py-0.5 rounded text-xs font-medium',
                  value === it.v ? 'bg-blue-500 text-white' : 'text-slate-400 hover:text-slate-200',
                )}>{it.label}</button>
      ))}
    </div>
  );
}

// ── Header (month + day strips) ─────────────────────────────────────────

function Header({ dayRange, dayPx, scale }: { dayRange: { start: Date; end: Date }; dayPx: number; scale: Scale }) {
  const dayCount = daysBetween(dayRange.start, dayRange.end) + 1;
  const days = Array.from({ length: dayCount }, (_, i) => addDays(dayRange.start, i));
  const months = useMemo(() => {
    const out: { count: number; label: string }[] = [];
    for (const d of days) {
      const label = `${d.toLocaleDateString(undefined, { month: 'short' })} ${d.getFullYear()}`;
      if (out.length === 0 || out[out.length - 1].label !== label) out.push({ count: 1, label });
      else out[out.length - 1].count += 1;
    }
    return out;
  }, [days]);

  return (
    <div className="sticky top-0 z-10 bg-astra-surface border-b border-astra-border">
      <div className="flex h-6" style={{ marginLeft: LABEL_W }}>
        {months.map((m, i) => (
          <div key={i} style={{ width: m.count * dayPx }}
               className="border-r border-astra-border px-2 flex items-center text-[10px] font-semibold text-slate-400 bg-astra-surface-alt">
            {m.label}
          </div>
        ))}
      </div>
      <div className="flex h-7" style={{ marginLeft: LABEL_W }}>
        {days.map((d, i) => {
          const we = d.getDay() === 0 || d.getDay() === 6;
          const isStartOfWeek = d.getDay() === 1;
          const showLabel = scale === 'day' || (scale === 'week' && isStartOfWeek) || (scale === 'month' && d.getDate() === 1);
          return (
            <div key={i} style={{ width: dayPx }}
                 className={clsx(
                   'flex items-center justify-center text-[9px] overflow-hidden',
                   isStartOfWeek && 'border-r border-astra-border',
                   we ? 'bg-astra-surface-alt text-slate-600' : 'text-slate-500',
                 )}>
              {showLabel ? d.getDate() : ''}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Body ────────────────────────────────────────────────────────────────

function Body({
  rangeStart, dayPx, dayCount, groupedTasks, collapsedTeams, toggleTeam,
  dependencies, taskById, onHover,
}: any) {
  const rowsRender: React.ReactNode[] = [];
  const taskY = new Map<string, number>();
  let row = 0;
  for (const g of groupedTasks) {
    rowsRender.push(<TeamHeader key={`th-${g.line.code}`} line={g.line} y={row * ROW_H}
                                 collapsed={collapsedTeams.has(g.line.code)} onToggle={() => toggleTeam(g.line.code)} />);
    row += 1;
    if (!collapsedTeams.has(g.line.code)) {
      for (const s of g.sections) {
        rowsRender.push(<SectionHeader key={`sh-${g.line.code}-${s.section}`} title={sectionLabel(s.section)} y={row * ROW_H} />);
        row += 1;
        for (const t of s.tasks) {
          taskY.set(t.task_id, row);
          rowsRender.push(
            <TaskBar key={`tr-${t.task_id}`} task={t} y={row * ROW_H}
                     rangeStart={rangeStart} dayPx={dayPx} color={g.line.color}
                     onHover={onHover} />
          );
          row += 1;
        }
      }
    }
  }

  const today = new Date(); today.setHours(0,0,0,0);
  const todayX = LABEL_W + daysBetween(rangeStart, today) * dayPx;

  const arrows = useMemo(() => {
    const out: React.ReactNode[] = [];
    for (const d of dependencies) {
      const py = taskY.get(d.predecessor_task_id);
      const sy = taskY.get(d.successor_task_id);
      if (py === undefined || sy === undefined) continue;
      const pTask = taskById.get(d.predecessor_task_id);
      const sTask = taskById.get(d.successor_task_id);
      if (!pTask?.start_date || !pTask?.finish_date || !sTask?.start_date) continue;
      const pEnd = parseDate(pTask.finish_date);
      const sStart = parseDate(sTask.start_date);
      if (!pEnd || !sStart) continue;
      const x1 = LABEL_W + (daysBetween(rangeStart, pEnd) + 1) * dayPx;
      const x2 = LABEL_W + daysBetween(rangeStart, sStart) * dayPx;
      const y1 = HEADER_H + py * ROW_H + ROW_H / 2;
      const y2 = HEADER_H + sy * ROW_H + ROW_H / 2;
      const isCritical = pTask.is_critical && sTask.is_critical;
      const path = `M ${x1} ${y1} L ${x1 + 6} ${y1} L ${x1 + 6} ${y2} L ${x2} ${y2}`;
      out.push(
        <path key={d.id} d={path} fill="none"
              stroke={isCritical ? '#ef4444' : 'rgba(96,165,250,0.35)'}
              strokeWidth={isCritical ? 1.4 : 1}
              markerEnd={isCritical ? 'url(#astra-dep-arrow-crit)' : 'url(#astra-dep-arrow)'} />
      );
    }
    return out;
  }, [dependencies, taskById, taskY, rangeStart, dayPx]);

  return (
    <div className="relative">
      <WeekendTint rangeStart={rangeStart} dayPx={dayPx} dayCount={dayCount} totalRows={row} />
      <div className="absolute top-[56px] w-px bg-red-500 z-[3]"
           style={{ left: todayX, height: row * ROW_H, boxShadow: '0 0 6px rgba(239,68,68,0.4)' }}
           title="Today" />
      <div className="relative">{rowsRender}</div>
      <svg
        className="absolute left-0 top-0 pointer-events-none z-[2]"
        style={{ width: LABEL_W + dayCount * dayPx, height: HEADER_H + row * ROW_H }}
      >
        <defs>
          <marker id="astra-dep-arrow" viewBox="0 0 8 8" refX="6" refY="4" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" fill="rgba(96,165,250,0.5)" />
          </marker>
          <marker id="astra-dep-arrow-crit" viewBox="0 0 8 8" refX="6" refY="4" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" fill="#ef4444" />
          </marker>
        </defs>
        {arrows}
      </svg>
    </div>
  );
}

function WeekendTint({ rangeStart, dayPx, dayCount, totalRows }: any) {
  const tints: React.ReactNode[] = [];
  for (let i = 0; i < dayCount; i++) {
    const d = addDays(rangeStart, i);
    if (d.getDay() === 0 || d.getDay() === 6) {
      tints.push(
        <div key={i} className="absolute pointer-events-none"
             style={{
               left: LABEL_W + i * dayPx,
               top: HEADER_H,
               width: dayPx, height: totalRows * ROW_H,
               background: 'rgba(15, 23, 42, 0.6)',
             }} />
      );
    }
  }
  return <>{tints}</>;
}

function TeamHeader({ line, y, collapsed, onToggle }: any) {
  return (
    <div onClick={onToggle}
         className="absolute left-0 w-full flex items-center gap-2 px-3 bg-astra-surface-alt border-b border-astra-border cursor-pointer text-xs font-semibold text-slate-200"
         style={{ top: HEADER_H + y, height: ROW_H }}>
      <span style={{ width: 4, height: 16, background: line.color, borderRadius: 2 }} />
      <span className="text-[10px] text-slate-500">{collapsed ? '▶' : '▼'}</span>
      <span className="font-mono text-[10px] text-slate-500">{line.code}</span>
      <span>{line.name}</span>
      <span className="flex-1" />
      <span className="text-[11px] text-slate-500">
        {line.owner_name || line.lead_name || ''}
      </span>
    </div>
  );
}

function SectionHeader({ title, y }: { title: string; y: number }) {
  return (
    <div className="absolute left-0 w-full flex items-center px-8 bg-astra-surface border-b border-astra-border/40 text-[10px] font-semibold text-slate-500 uppercase tracking-wider"
         style={{ top: HEADER_H + y, height: ROW_H }}>
      {title}
    </div>
  );
}

function TaskBar({ task, y, rangeStart, dayPx, color, onHover }: any) {
  const start = parseDate(task.start_date);
  const finish = parseDate(task.finish_date);
  const baseStart = parseDate(task.baseline_start);
  const baseFin = parseDate(task.baseline_finish);
  const x = start ? daysBetween(rangeStart, start) * dayPx : 0;
  const width = start && finish ? Math.max(2, (daysBetween(start, finish) + 1) * dayPx) : 0;
  const baseX = baseStart ? daysBetween(rangeStart, baseStart) * dayPx : null;
  const baseW = baseStart && baseFin ? Math.max(2, (daysBetween(baseStart, baseFin) + 1) * dayPx) : null;

  return (
    <div className="absolute left-0 w-full flex border-b border-astra-border/30"
         style={{ top: HEADER_H + y, height: ROW_H }}
         onMouseEnter={(e) => onHover(task, e)}
         onMouseLeave={() => onHover(null, null)}
         onMouseMove={(e) => onHover(task, e)}
    >
      <div className="px-3 pl-12 flex items-center gap-2 bg-astra-surface border-r border-astra-border/40"
           style={{ width: LABEL_W }}>
        {task.is_critical && <span className="inline-block w-1.5 h-1.5 rounded-full bg-red-500" style={{ boxShadow: '0 0 6px rgba(239,68,68,0.4)' }} />}
        <span className="font-mono text-[10px] text-slate-500 flex-shrink-0">{task.task_id}</span>
        <span className={clsx(
          'text-xs overflow-hidden text-ellipsis whitespace-nowrap',
          task.is_critical ? 'text-slate-200' : 'text-slate-400'
        )}>
          {task.name}
        </span>
        {task.is_milestone && <span className="rounded-full bg-blue-500/15 text-blue-400 px-1 text-[9px]">◆</span>}
      </div>
      {start && finish && (
        <div className="relative flex-1">
          {baseX !== null && baseW !== null && (
            <div className="absolute rounded"
                 style={{
                   left: baseX, top: 14, height: 6, width: baseW,
                   background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.08)',
                 }} />
          )}
          {task.is_milestone ? (
            <div className="absolute"
                 style={{
                   left: x - 6, top: ROW_H / 2 - 7,
                   width: 14, height: 14,
                   background: task.is_critical ? '#ef4444' : color,
                   transform: 'rotate(45deg)', borderRadius: 2,
                   boxShadow: task.is_critical ? '0 0 6px rgba(239,68,68,0.4)' : 'none',
                 }} />
          ) : (
            <div className="absolute rounded overflow-hidden"
                 style={{
                   left: x, top: 6, width, height: ROW_H - 12,
                   background: task.is_critical ? 'rgba(239,68,68,0.18)' : `${color}28`,
                   border: `1.5px solid ${task.is_critical ? '#ef4444' : color}`,
                   boxShadow: task.is_critical ? '0 0 4px rgba(239,68,68,0.4)' : 'none',
                 }}>
              <div style={{
                width: `${Math.max(0, Math.min(100, task.percent_complete))}%`,
                height: '100%',
                background: task.is_critical ? '#ef4444' : color,
                opacity: 0.5,
              }} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Tooltip ─────────────────────────────────────────────────────────────

function Tooltip({ task, pos, teams }: { task: any; pos: { x: number; y: number }; teams: any[] }) {
  const line = teams.find((l: any) => l.id === task.dev_line_id);
  return (
    <div className="fixed pointer-events-none z-50 bg-astra-surface border border-astra-border-strong rounded-lg shadow-xl p-3 text-xs"
         style={{ left: pos.x + 12, top: pos.y + 12, maxWidth: 320 }}>
      <div className="flex items-center gap-2 mb-1">
        <span style={{ background: (line?.color ?? '#666') + '24', color: line?.color ?? '#9ca3af', border: `1px solid ${line?.color}40` }}
              className="px-1.5 py-0.5 rounded text-[10px] font-mono">
          {line?.code ?? '??'}
        </span>
        <span className="font-mono text-[10px] text-slate-500">{task.task_id}</span>
      </div>
      <div className="font-semibold text-slate-200 mb-2">{task.name}</div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
        <Row label="Start" value={task.start_date ?? '—'} />
        <Row label="Finish" value={task.finish_date ?? '—'} />
        <Row label="Duration" value={`${task.duration_days}d`} />
        <Row label="Float" value={task.total_float_days !== null ? `${task.total_float_days}d` : '—'}
             color={task.total_float_days != null && task.total_float_days < 0 ? '#f87171' : task.is_critical ? '#ef4444' : undefined} />
        <Row label="% complete" value={`${task.percent_complete}%`} />
        <Row label="Status" value={task.status.replace(/_/g, ' ')} />
        <Row label="Owner" value={task.owner || '—'} />
        {task.gate_alignment && <Row label="Gate" value={task.gate_alignment} />}
      </div>
    </div>
  );
}

function Row({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <>
      <span className="text-slate-500 uppercase text-[9px]">{label}</span>
      <span className="tabular-nums" style={{ color: color ?? '#e2e8f0' }}>{value}</span>
    </>
  );
}

// ── Model ───────────────────────────────────────────────────────────────

function useGanttModel({ data, view, filterTeam, filterStatus, search, criticalOnly }: any) {
  const taskById = useMemo(() => {
    const m = new Map<string, any>();
    for (const t of data?.tasks ?? []) m.set(t.task_id, t);
    return m;
  }, [data]);

  const tasks = useMemo(() => {
    if (!data) return [];
    let xs = data.tasks ?? [];
    if (view === 'L1') xs = xs.filter((t: any) => t.is_milestone && t.task_id.startsWith('WS-'));
    else if (view === 'L2') xs = xs.filter((t: any) => t.is_milestone);
    if (filterTeam) xs = xs.filter((t: any) => t.task_id.startsWith(`${filterTeam}-`) || (filterTeam === 'PRG' && t.task_id.startsWith('WS-')));
    if (filterStatus) xs = xs.filter((t: any) => t.status === filterStatus);
    if (criticalOnly) xs = xs.filter((t: any) => t.is_critical);
    if (search) {
      const s = search.toLowerCase();
      xs = xs.filter((t: any) => t.name.toLowerCase().includes(s) || t.task_id.toLowerCase().includes(s));
    }
    return xs;
  }, [data, view, filterTeam, filterStatus, search, criticalOnly]);

  const dayRange = useMemo(() => {
    if (!data) return null;
    let min: Date | null = null;
    let max: Date | null = null;
    for (const t of tasks) {
      const s = parseDate(t.start_date);
      const f = parseDate(t.finish_date);
      if (s && (!min || s < min)) min = s;
      if (f && (!max || f > max)) max = f;
    }
    if (!min) min = parseDate(data.program.start_date);
    if (!max) max = parseDate(data.program.target_finish_date);
    if (!min || !max) return null;
    min = startOfWeekMon(addDays(min, -3));
    max = addDays(max, 7);
    return { start: min, end: max };
  }, [tasks, data]);

  const groupedTasks = useMemo(() => {
    if (!data) return [];
    const byLineId = new Map<number, { line: any; sections: { section: string; tasks: any[] }[] }>();
    const sectionOrder = ['supply_chain', 'development', 'testing_integration'];
    for (const l of data.dev_lines ?? []) {
      byLineId.set(l.id, {
        line: l,
        sections: sectionOrder.map((s) => ({ section: s, tasks: [] as any[] })),
      });
    }
    for (const t of tasks) {
      const g = byLineId.get(t.dev_line_id);
      if (!g) continue;
      const sect = g.sections.find((s: any) => s.section === t.section);
      if (sect) sect.tasks.push(t);
    }
    return Array.from(byLineId.values())
      .map((g) => ({ ...g, sections: g.sections.filter((s: any) => s.tasks.length) }))
      .filter((g) => g.sections.length);
  }, [data, tasks]);

  return { groupedTasks, taskById, dayRange };
}

// ── Date helpers ────────────────────────────────────────────────────────

function parseDate(s: string | null | undefined): Date | null {
  if (!s) return null;
  const [y, m, d] = s.split('-').map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
}

function addDays(d: Date, n: number): Date {
  const r = new Date(d); r.setDate(r.getDate() + n); return r;
}

function daysBetween(a: Date, b: Date): number {
  return Math.round((b.getTime() - a.getTime()) / 86_400_000);
}

function startOfWeekMon(d: Date): Date {
  const r = new Date(d);
  const day = r.getDay();
  const diff = (day === 0 ? -6 : 1) - day;
  r.setDate(r.getDate() + diff);
  return r;
}

function sectionLabel(s: string): string {
  if (s === 'supply_chain') return 'Supply Chain';
  if (s === 'development') return 'Development';
  if (s === 'testing_integration') return 'Testing & Integration';
  return s;
}
