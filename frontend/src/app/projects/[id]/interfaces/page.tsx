'use client';

/**
 * ASTRA — Interface Module Main Page
 * ======================================
 * File: frontend/src/app/projects/[id]/interfaces/page.tsx
 * Path: C:\Users\Mason\Documents\ASTRA\frontend\src\app\projects\[id]\interfaces\page.tsx
 *
 * Tabs: [Units] [Systems] [Connections]
 * Units tab: search, filter by system/type, create modal, grouped view
 * Systems tab: system tree with unit counts
 * Connections tab: N² matrix + harness list
 */

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  Loader2, RefreshCw, Plus, Search, Filter, ChevronRight,
  Cpu, Cable, Network, Box, Zap, Shield, Radio,
  ChevronDown, X, Download, Upload, ArrowRight,
} from 'lucide-react';
import clsx from 'clsx';
import { projectsAPI } from '@/lib/api';
import { interfaceAPI, downloadBlob } from '@/lib/interface-api';
import type {
  System, UnitSummary, WireHarness, N2MatrixResponse, N2MatrixCell,
  InterfaceCoverageResponse,
} from '@/lib/interface-types';

// ── Unit type icon map ──
const TYPE_ICONS: Record<string, any> = {
  processor: Cpu, antenna: Radio, power_supply: Zap,
  sensor: Shield, transceiver: Cable, default: Box,
};
function UnitIcon({ type }: { type: string }) {
  const Icon = TYPE_ICONS[type] || TYPE_ICONS.default;
  return <Icon className="h-4 w-4 flex-shrink-0 text-slate-500" />;
}

// ── Status badge ──
const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  concept:           { bg: 'rgba(100,116,139,0.15)', text: '#94A3B8' },
  preliminary_design:{ bg: 'rgba(139,92,246,0.15)',  text: '#A78BFA' },
  detailed_design:   { bg: 'rgba(59,130,246,0.12)',  text: '#3B82F6' },
  flight_unit:       { bg: 'rgba(16,185,129,0.15)',  text: '#10B981' },
  operational:       { bg: 'rgba(16,185,129,0.25)',  text: '#34D399' },
};
function StatusBadge({ status }: { status: string }) {
  const c = STATUS_COLORS[status] || STATUS_COLORS.concept;
  return (
    <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize"
      style={{ background: c.bg, color: c.text }}>
      {status.replace(/_/g, ' ')}
    </span>
  );
}

// ── Coverage stat mini bar ──
function CovStat({ label, value, total, color }: { label: string; value: number; total: number; color: string }) {
  const pct = total > 0 ? Math.round(value / total * 100) : 0;
  return (
    <div className="flex-1 min-w-[120px]">
      <div className="mb-1 flex justify-between text-[10px]">
        <span className="text-slate-500">{label}</span>
        <span className="font-bold" style={{ color }}>{pct}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-astra-surface-alt overflow-hidden">
        <div className="h-full rounded-full transition-all duration-700" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

// ── Tab type ──
type Tab = 'units' | 'systems' | 'connections';

// ══════════════════════════════════════
//  Create System Modal
// ══════════════════════════════════════

function CreateSystemModal({ projectId, onClose, onCreated }: {
  projectId: number; onClose: () => void; onCreated: () => void;
}) {
  const [name, setName] = useState('');
  const [sysType, setSysType] = useState('subsystem');
  const [abbr, setAbbr] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      await interfaceAPI.createSystem(projectId, { name, system_type: sysType, abbreviation: abbr || undefined });
      onCreated();
      onClose();
    } catch { }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl border border-astra-border bg-astra-surface p-6 shadow-2xl" onClick={e => e.stopPropagation()}>
        <h3 className="text-sm font-bold text-slate-200 mb-4">New System</h3>
        <div className="space-y-3">
          <input value={name} onChange={e => setName(e.target.value)} placeholder="System name *"
            className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
          <input value={abbr} onChange={e => setAbbr(e.target.value)} placeholder="Abbreviation"
            className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
          <select value={sysType} onChange={e => setSysType(e.target.value)}
            className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50">
            {['subsystem','payload','communication','data_handling','power_system','guidance_nav_control','propulsion','thermal_system','structural','ground_segment','custom'].map(t =>
              <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
            )}
          </select>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg border border-astra-border px-4 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200">Cancel</button>
          <button onClick={handleSave} disabled={!name.trim() || saving}
            className="rounded-lg bg-blue-500 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-600 disabled:opacity-50">
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Create System'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  Create Unit Modal
// ══════════════════════════════════════

function CreateUnitModal({ projectId, systems, onClose, onCreated }: {
  projectId: number; systems: System[]; onClose: () => void; onCreated: () => void;
}) {
  const [name, setName] = useState('');
  const [designation, setDesignation] = useState('');
  const [partNumber, setPartNumber] = useState('');
  const [manufacturer, setManufacturer] = useState('');
  const [unitType, setUnitType] = useState('processor');
  const [systemId, setSystemId] = useState<number | ''>(systems[0]?.id || '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSave = async () => {
    if (!name || !designation || !partNumber || !manufacturer || !systemId) return;
    setSaving(true);
    setError('');
    try {
      await interfaceAPI.createUnit(projectId, {
        name, designation, part_number: partNumber, manufacturer,
        unit_type: unitType, system_id: systemId as number,
      });
      onCreated();
      onClose();
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Failed to create unit');
    }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl border border-astra-border bg-astra-surface p-6 shadow-2xl" onClick={e => e.stopPropagation()}>
        <h3 className="text-sm font-bold text-slate-200 mb-4">New Unit</h3>
        {error && <div className="mb-3 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</div>}
        <div className="grid grid-cols-2 gap-3">
          <input value={designation} onChange={e => setDesignation(e.target.value)} placeholder="Designation * (e.g. RSP-100)"
            className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
          <input value={name} onChange={e => setName(e.target.value)} placeholder="Name *"
            className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
          <input value={partNumber} onChange={e => setPartNumber(e.target.value)} placeholder="Part Number *"
            className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
          <input value={manufacturer} onChange={e => setManufacturer(e.target.value)} placeholder="Manufacturer *"
            className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
          <select value={unitType} onChange={e => setUnitType(e.target.value)}
            className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50">
            {['processor','antenna','sensor','transceiver','power_supply','battery','actuator','fpga','lru','wru','sru','custom'].map(t =>
              <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
            )}
          </select>
          <select value={systemId} onChange={e => setSystemId(Number(e.target.value))}
            className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50">
            <option value="">Select System *</option>
            {systems.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg border border-astra-border px-4 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200">Cancel</button>
          <button onClick={handleSave} disabled={saving || !name || !designation || !partNumber || !manufacturer || !systemId}
            className="rounded-lg bg-blue-500 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-600 disabled:opacity-50">
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Create Unit'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  N² Matrix Mini View
// ══════════════════════════════════════

function N2Matrix({ data }: { data: N2MatrixResponse | null }) {
  if (!data || data.systems.length === 0) {
    return <div className="py-12 text-center text-sm text-slate-500">No systems defined yet. Create systems and interfaces to see the N² matrix.</div>;
  }
  const { systems, matrix } = data;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px]">
        <thead>
          <tr>
            <th className="border border-astra-border bg-astra-surface-alt p-2 text-left font-semibold text-slate-400">From / To</th>
            {systems.map(s => (
              <th key={s.id} className="border border-astra-border bg-astra-surface-alt p-2 text-center font-semibold text-slate-400 max-w-[100px] truncate">
                {s.abbreviation || s.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {systems.map((src, ri) => (
            <tr key={src.id}>
              <td className="border border-astra-border bg-astra-surface-alt p-2 font-semibold text-slate-300 whitespace-nowrap">
                {src.abbreviation || src.name}
              </td>
              {systems.map((tgt, ci) => {
                const cell: N2MatrixCell | null = matrix[ri]?.[ci] ?? null;
                const isDiag = ri === ci;
                return (
                  <td key={tgt.id} className={clsx('border border-astra-border p-2 text-center',
                    isDiag ? 'bg-astra-surface-alt' : cell ? 'bg-blue-500/5 hover:bg-blue-500/10 cursor-pointer' : '')}>
                    {isDiag ? <span className="text-slate-600">—</span> :
                      cell ? (
                        <div>
                          <span className="font-bold text-blue-400">{cell.interface_count}</span>
                          {cell.harness_count > 0 && <span className="ml-1 text-slate-500">({cell.harness_count}h)</span>}
                        </div>
                      ) : <span className="text-slate-700">·</span>
                    }
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ══════════════════════════════════════
//  Main Page
// ══════════════════════════════════════

export default function InterfacesPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);
  const p = `/projects/${projectId}`;

  const [projectCode, setProjectCode] = useState('');
  const [tab, setTab] = useState<Tab>('units');
  const [loading, setLoading] = useState(true);

  // Data
  const [systems, setSystems] = useState<System[]>([]);
  const [units, setUnits] = useState<UnitSummary[]>([]);
  const [harnesses, setHarnesses] = useState<WireHarness[]>([]);
  const [n2Data, setN2Data] = useState<N2MatrixResponse | null>(null);
  const [coverage, setCoverage] = useState<InterfaceCoverageResponse | null>(null);

  // Filters
  const [search, setSearch] = useState('');
  const [filterSystem, setFilterSystem] = useState<number | ''>('');
  const [filterType, setFilterType] = useState('');

  // Modals
  const [showCreateUnit, setShowCreateUnit] = useState(false);
  const [showCreateSystem, setShowCreateSystem] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [projRes, sysRes, unitRes] = await Promise.all([
        projectsAPI.get(projectId),
        interfaceAPI.listSystems(projectId),
        interfaceAPI.listUnits(projectId, { limit: 200 }),
      ]);
      setProjectCode(projRes.data?.code || '');
      setSystems(sysRes.data || []);
      setUnits(unitRes.data || []);

      // Background fetches
      interfaceAPI.listHarnesses(projectId).then(r => setHarnesses(r.data || [])).catch(() => {});
      interfaceAPI.getN2Matrix(projectId).then(r => setN2Data(r.data)).catch(() => {});
      interfaceAPI.getCoverage(projectId).then(r => setCoverage(r.data)).catch(() => {});
    } catch { }
    setLoading(false);
  }, [projectId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Filtered units
  const filtered = units.filter(u => {
    if (search) {
      const s = search.toLowerCase();
      if (!u.name.toLowerCase().includes(s) && !u.designation.toLowerCase().includes(s) && !u.part_number.toLowerCase().includes(s)) return false;
    }
    if (filterSystem && u.system_id !== filterSystem) return false;
    if (filterType && u.unit_type !== filterType) return false;
    return true;
  });

  // Group units by system for display
  const systemMap = new Map(systems.map(s => [s.id, s]));
  const grouped = new Map<number, UnitSummary[]>();
  for (const u of filtered) {
    const sid = u.system_id ?? 0;
    if (!grouped.has(sid)) grouped.set(sid, []);
    grouped.get(sid)!.push(u);
  }

  const unitTypes = [...new Set(units.map(u => u.unit_type))].sort();

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Interface Management</h1>
          <p className="mt-0.5 text-sm text-slate-500">{projectCode} · Systems, Units, Wiring, Buses</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => downloadBlob(interfaceAPI.exportUnits(projectId), `${projectCode}_units.xlsx`).catch(() => {})}
            className="flex items-center gap-1.5 rounded-lg border border-astra-border px-3 py-2 text-xs font-semibold text-slate-400 hover:border-blue-500/30 hover:text-slate-200">
            <Download className="h-3.5 w-3.5" /> Export
          </button>
          <button onClick={() => setShowCreateUnit(true)}
            className="flex items-center gap-1.5 rounded-lg bg-blue-500 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-600">
            <Plus className="h-3.5 w-3.5" /> New Unit
          </button>
        </div>
      </div>

      {/* Coverage stats bar */}
      {coverage && (
        <div className="mb-5 flex gap-6 rounded-xl border border-astra-border bg-astra-surface p-4">
          <CovStat label="Interfaces Traced" value={coverage.with_requirements} total={coverage.total_interfaces} color="#3B82F6" />
          <CovStat label="Units with Specs" value={coverage.units_with_specs} total={coverage.units_with_specs + coverage.units_without_specs} color="#10B981" />
          <CovStat label="Auto-Reqs Approved" value={coverage.approved_count} total={coverage.auto_generated_count || 1} color="#8B5CF6" />
          <div className="flex items-center gap-2 border-l border-astra-border pl-6">
            <span className="text-2xl font-bold text-blue-400">{units.length}</span>
            <span className="text-[11px] text-slate-500">Units</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-2xl font-bold text-emerald-400">{systems.length}</span>
            <span className="text-[11px] text-slate-500">Systems</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-2xl font-bold text-violet-400">{harnesses.length}</span>
            <span className="text-[11px] text-slate-500">Harnesses</span>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="mb-4 flex items-center gap-1 border-b border-astra-border">
        {([
          { key: 'units' as Tab, label: 'Units', icon: Box, count: units.length },
          { key: 'systems' as Tab, label: 'Systems', icon: Network, count: systems.length },
          { key: 'connections' as Tab, label: 'Connections', icon: Cable, count: harnesses.length },
        ]).map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={clsx('flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-xs font-semibold transition',
              tab === t.key ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-500 hover:text-slate-300')}>
            <t.icon className="h-3.5 w-3.5" /> {t.label}
            <span className={clsx('ml-1 rounded-full px-1.5 py-0.5 text-[10px] font-bold',
              tab === t.key ? 'bg-blue-500/20 text-blue-400' : 'bg-astra-surface-alt text-slate-600')}>
              {t.count}
            </span>
          </button>
        ))}
        <div className="flex-1" />
        <button onClick={fetchData} className="rounded-lg p-2 text-slate-500 hover:text-slate-300">
          <RefreshCw className={clsx('h-3.5 w-3.5', loading && 'animate-spin')} />
        </button>
      </div>

      {/* ════════════ UNITS TAB ════════════ */}
      {tab === 'units' && (
        <>
          {/* Filters */}
          <div className="mb-4 flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search units by name, designation, part number..."
                className="w-full rounded-lg border border-astra-border bg-astra-surface pl-9 pr-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <select value={filterSystem} onChange={e => setFilterSystem(e.target.value ? Number(e.target.value) : '')}
              className="rounded-lg border border-astra-border bg-astra-surface px-3 py-2 text-sm text-slate-300 outline-none">
              <option value="">All Systems</option>
              {systems.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <select value={filterType} onChange={e => setFilterType(e.target.value)}
              className="rounded-lg border border-astra-border bg-astra-surface px-3 py-2 text-sm text-slate-300 outline-none">
              <option value="">All Types</option>
              {unitTypes.map(t => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
            </select>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-blue-500" /></div>
          ) : filtered.length === 0 ? (
            <div className="py-16 text-center">
              <Box className="mx-auto h-10 w-10 text-slate-600 mb-3" />
              <p className="text-sm text-slate-400">{search || filterSystem || filterType ? 'No units match your filters' : 'No units yet'}</p>
              <button onClick={() => setShowCreateUnit(true)} className="mt-3 rounded-lg bg-blue-500 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-600">
                <Plus className="mr-1 inline h-3.5 w-3.5" /> Create First Unit
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {[...grouped.entries()].map(([sysId, sysUnits]) => {
                const sys = systemMap.get(sysId);
                return (
                  <div key={sysId}>
                    <div className="mb-2 flex items-center gap-2">
                      <Network className="h-3.5 w-3.5 text-slate-500" />
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                        {sys?.name || 'Unassigned'} ({sysUnits.length})
                      </span>
                    </div>
                    <div className="space-y-1">
                      {sysUnits.map(u => (
                        <div key={u.id} onClick={() => router.push(`${p}/interfaces/${u.id}`)}
                          className="group flex items-center gap-3 rounded-xl border border-astra-border bg-astra-surface px-4 py-3 cursor-pointer transition hover:border-blue-500/20 hover:bg-blue-500/5">
                          <UnitIcon type={u.unit_type} />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-xs font-bold text-blue-400">{u.designation}</span>
                              <span className="text-[13px] font-medium text-slate-200 truncate">{u.name}</span>
                            </div>
                            <div className="mt-0.5 flex items-center gap-3 text-[11px] text-slate-500">
                              <span>{u.manufacturer}</span>
                              <span>·</span>
                              <span>{u.part_number}</span>
                              <span>·</span>
                              <span className="capitalize">{u.unit_type.replace(/_/g, ' ')}</span>
                            </div>
                          </div>
                          <div className="flex items-center gap-3">
                            <div className="text-center">
                              <div className="text-xs font-bold text-slate-300">{u.connector_count}</div>
                              <div className="text-[9px] text-slate-600">Conn</div>
                            </div>
                            <div className="text-center">
                              <div className="text-xs font-bold text-slate-300">{u.bus_count}</div>
                              <div className="text-[9px] text-slate-600">Buses</div>
                            </div>
                            <StatusBadge status={u.status} />
                            <ChevronRight className="h-4 w-4 text-slate-600 group-hover:text-blue-400 transition" />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* ════════════ SYSTEMS TAB ════════════ */}
      {tab === 'systems' && (
        <div>
          <div className="mb-4 flex justify-end">
            <button onClick={() => setShowCreateSystem(true)}
              className="flex items-center gap-1.5 rounded-lg bg-blue-500 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-600">
              <Plus className="h-3.5 w-3.5" /> New System
            </button>
          </div>
          {systems.length === 0 ? (
            <div className="py-16 text-center">
              <Network className="mx-auto h-10 w-10 text-slate-600 mb-3" />
              <p className="text-sm text-slate-400">No systems defined yet</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
              {systems.map(s => (
                <div key={s.id} className="rounded-xl border border-astra-border bg-astra-surface p-4 hover:border-blue-500/20 transition cursor-pointer"
                  onClick={() => { setTab('units'); setFilterSystem(s.id); }}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-mono text-xs font-bold text-cyan-400">{s.system_id}</span>
                    <StatusBadge status={s.status} />
                  </div>
                  <h3 className="text-sm font-semibold text-slate-200 mb-1">{s.name}</h3>
                  {s.abbreviation && <p className="text-[11px] text-slate-500 mb-2">({s.abbreviation})</p>}
                  <div className="flex gap-4 mt-3 pt-3 border-t border-astra-border">
                    <div className="text-center">
                      <div className="text-lg font-bold text-slate-300">{s.unit_count}</div>
                      <div className="text-[9px] text-slate-500">Units</div>
                    </div>
                    <div className="text-center">
                      <div className="text-lg font-bold text-slate-300">{s.interface_count}</div>
                      <div className="text-[9px] text-slate-500">Interfaces</div>
                    </div>
                    <div className="flex-1 text-right">
                      <span className="capitalize text-[11px] text-slate-500">{s.system_type.replace(/_/g, ' ')}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ════════════ CONNECTIONS TAB ════════════ */}
      {tab === 'connections' && (
        <div className="space-y-6">
          <div>
            <h3 className="text-sm font-bold text-slate-300 mb-3">N² Interface Matrix</h3>
            <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
              <N2Matrix data={n2Data} />
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-slate-300">Wire Harnesses ({harnesses.length})</h3>
            </div>
            {harnesses.length === 0 ? (
              <div className="rounded-xl border border-astra-border bg-astra-surface p-8 text-center text-sm text-slate-500">
                No harnesses created yet
              </div>
            ) : (
              <div className="space-y-2">
                {harnesses.map(h => (
                  <div key={h.id} className="flex items-center gap-3 rounded-xl border border-astra-border bg-astra-surface px-4 py-3 hover:border-blue-500/20 cursor-pointer"
                    onClick={() => router.push(`${p}/interfaces/harness/${h.id}`)}>
                    <Cable className="h-4 w-4 text-emerald-500 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <span className="text-[13px] font-medium text-slate-200">{h.name}</span>
                      <div className="text-[11px] text-slate-500">
                        {h.from_unit_designation} ({h.from_connector_designator}) <ArrowRight className="inline h-3 w-3 mx-1" /> {h.to_unit_designation} ({h.to_connector_designator})
                      </div>
                    </div>
                    <span className="rounded-full bg-astra-surface-alt px-2 py-0.5 text-[10px] font-bold text-slate-400">{h.wire_count} wires</span>
                    <ChevronRight className="h-4 w-4 text-slate-600" />
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Modals */}
      {showCreateUnit && <CreateUnitModal projectId={projectId} systems={systems} onClose={() => setShowCreateUnit(false)} onCreated={fetchData} />}
      {showCreateSystem && <CreateSystemModal projectId={projectId} onClose={() => setShowCreateSystem(false)} onCreated={fetchData} />}
    </div>
  );
}
