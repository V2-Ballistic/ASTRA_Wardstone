'use client';

/**
 * ASTRA — Interface Module Landing Page
 * =========================================
 * File: frontend/src/app/projects/[id]/interfaces/page.tsx
 *
 * Three horizontal tabs:
 *   [Systems]  (default) — card grid, click → System Detail
 *   [Connections]        — harnesses grouped by system, filterable
 *   [N² Matrix]          — hidden by default, expand to view
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  Loader2, RefreshCw, Plus, Search, ChevronRight, ChevronDown,
  Cable, Network, Box, Zap, Shield, Radio, Layers, Cpu,
  X, ArrowRight, Grid3X3, AlertTriangle, FileSpreadsheet,
} from 'lucide-react';
import clsx from 'clsx';
import { projectsAPI } from '@/lib/api';
import { interfaceAPI } from '@/lib/interface-api';
import type {
  System, SystemDetail, UnitSummary, Connector, WireHarness,
  N2MatrixResponse, N2MatrixCell, InterfaceCoverageResponse,
} from '@/lib/interface-types';

// ══════════════════════════════════════
//  Shared UI
// ══════════════════════════════════════

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  concept:            { bg: 'rgba(100,116,139,0.15)', text: '#94A3B8' },
  preliminary_design: { bg: 'rgba(139,92,246,0.15)',  text: '#A78BFA' },
  detailed_design:    { bg: 'rgba(59,130,246,0.12)',  text: '#3B82F6' },
  fabrication:        { bg: 'rgba(245,158,11,0.15)',  text: '#F59E0B' },
  integration:        { bg: 'rgba(6,182,212,0.15)',   text: '#06B6D4' },
  qualification_test: { bg: 'rgba(234,88,12,0.15)',   text: '#F97316' },
  acceptance_test:    { bg: 'rgba(16,185,129,0.15)',  text: '#10B981' },
  operational:        { bg: 'rgba(16,185,129,0.25)',  text: '#34D399' },
  drawing_released:   { bg: 'rgba(16,185,129,0.15)',  text: '#10B981' },
  maintenance:        { bg: 'rgba(245,158,11,0.12)',  text: '#FBBF24' },
  retired:            { bg: 'rgba(107,114,128,0.15)', text: '#6B7280' },
  obsolete:           { bg: 'rgba(107,114,128,0.10)', text: '#4B5563' },
  installed:          { bg: 'rgba(16,185,129,0.25)',  text: '#34D399' },
  proposed:           { bg: 'rgba(139,92,246,0.12)',  text: '#A78BFA' },
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

const SYSTEM_TYPE_ICONS: Record<string, any> = {
  processor_unit: Cpu, power_system: Zap, communication: Radio,
  antenna_system: Radio, sensor_suite: Shield, data_handling: Layers,
  guidance_nav_control: Network, default: Box,
};

function SystemTypeIcon({ type }: { type: string }) {
  const Icon = SYSTEM_TYPE_ICONS[type] || SYSTEM_TYPE_ICONS.default;
  return <Icon className="h-3.5 w-3.5 flex-shrink-0" />;
}

const CRITICALITY_COLORS: Record<string, string> = {
  catastrophic: '#EF4444', hazardous: '#F97316', major: '#F59E0B',
  minor: '#3B82F6', no_effect: '#6B7280', mission_critical: '#F59E0B',
  non_critical: '#6B7280',
};

function CovStat({ label, value, total, color }: {
  label: string; value: number; total: number; color: string;
}) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div className="flex-1 min-w-[120px]">
      <div className="mb-1 flex justify-between text-[10px]">
        <span className="text-slate-500">{label}</span>
        <span className="font-bold" style={{ color }}>{pct}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-astra-surface-alt overflow-hidden">
        <div className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  Create System Modal
// ══════════════════════════════════════

const SYSTEM_TYPES = [
  'subsystem', 'lru', 'wru', 'sru', 'sensor_suite', 'actuator_assembly',
  'processor_unit', 'power_system', 'thermal_system', 'structural',
  'ground_segment', 'vehicle', 'payload', 'antenna_system', 'propulsion',
  'guidance_nav_control', 'communication', 'data_handling', 'ordnance',
  'test_equipment', 'external_system', 'software', 'firmware', 'custom',
];

function CreateSystemModal({ projectId, onClose, onCreated }: {
  projectId: number; onClose: () => void; onCreated: () => void;
}) {
  const [name, setName] = useState('');
  const [sysType, setSysType] = useState('subsystem');
  const [abbr, setAbbr] = useState('');
  const [desc, setDesc] = useState('');
  const [wbs, setWbs] = useState('');
  const [org, setOrg] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSave = async () => {
    if (!name.trim()) { setError('System name is required'); return; }
    setSaving(true);
    setError('');
    try {
      await interfaceAPI.createSystem(projectId, {
        name, system_type: sysType,
        abbreviation: abbr || undefined,
        description: desc || undefined,
        wbs_number: wbs || undefined,
        responsible_org: org || undefined,
      });
      onCreated();
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to create system');
    }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl border border-astra-border bg-astra-surface p-6 shadow-2xl"
        onClick={e => e.stopPropagation()}>
        <h3 className="text-sm font-bold text-slate-200 mb-4">New System</h3>

        {error && (
          <div className="mb-3 rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
            <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" /> {error}
          </div>
        )}

        <div className="space-y-3">
          <div>
            <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">Name *</label>
            <input value={name} onChange={e => setName(e.target.value)}
              placeholder="e.g. Flight Computer Assembly"
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">Type</label>
              <select value={sysType} onChange={e => setSysType(e.target.value)}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50">
                {SYSTEM_TYPES.map(t => (
                  <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">Abbreviation</label>
              <input value={abbr} onChange={e => setAbbr(e.target.value)}
                placeholder="e.g. FCA"
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">WBS Number</label>
              <input value={wbs} onChange={e => setWbs(e.target.value)}
                placeholder="e.g. 1.2.3"
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <div>
              <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">Responsible Org</label>
              <input value={org} onChange={e => setOrg(e.target.value)}
                placeholder="e.g. Avionics Team"
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
          </div>
          <div>
            <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">Description</label>
            <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={2}
              placeholder="Optional description..."
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50 resize-none" />
          </div>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose}
            className="rounded-lg border border-astra-border px-4 py-2 text-xs text-slate-400 hover:text-slate-200">
            Cancel
          </button>
          <button onClick={handleSave} disabled={saving || !name.trim()}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-40">
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
            Create System
          </button>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  Add Connection Modal
// ══════════════════════════════════════

function AddConnectionModal({ projectId, units, onClose, onCreated }: {
  projectId: number; units: UnitSummary[]; onClose: () => void; onCreated: () => void;
}) {
  const [fromUnitId, setFromUnitId]           = useState<number | ''>('');
  const [fromConnectorId, setFromConnectorId] = useState<number | ''>('');
  const [toUnitId, setToUnitId]               = useState<number | ''>('');
  const [toConnectorId, setToConnectorId]     = useState<number | ''>('');
  const [name, setName]                       = useState('');
  const [description, setDescription]         = useState('');
  const [fromConnectors, setFromConnectors]   = useState<Connector[]>([]);
  const [toConnectors, setToConnectors]       = useState<Connector[]>([]);
  const [loadingFrom, setLoadingFrom]         = useState(false);
  const [loadingTo, setLoadingTo]             = useState(false);
  const [saving, setSaving]                   = useState(false);
  const [error, setError]                     = useState('');

  // Fetch connectors when unit changes
  const loadConnectors = useCallback(async (unitId: number, side: 'from' | 'to') => {
    const setLoading = side === 'from' ? setLoadingFrom : setLoadingTo;
    const setConns   = side === 'from' ? setFromConnectors : setToConnectors;
    setLoading(true);
    try {
      const res = await interfaceAPI.listConnectors(unitId);
      setConns(res.data || []);
    } catch { setConns([]); }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (fromUnitId) { loadConnectors(Number(fromUnitId), 'from'); setFromConnectorId(''); }
    else { setFromConnectors([]); setFromConnectorId(''); }
  }, [fromUnitId, loadConnectors]);

  useEffect(() => {
    if (toUnitId) { loadConnectors(Number(toUnitId), 'to'); setToConnectorId(''); }
    else { setToConnectors([]); setToConnectorId(''); }
  }, [toUnitId, loadConnectors]);

  // Auto-generate name
  useEffect(() => {
    if (fromUnitId && toUnitId) {
      const fu = units.find(u => u.id === Number(fromUnitId));
      const tu = units.find(u => u.id === Number(toUnitId));
      const fc = fromConnectors.find(c => c.id === Number(fromConnectorId));
      const tc = toConnectors.find(c => c.id === Number(toConnectorId));
      if (fu && tu) {
        setName(`W${fu.designation}${fc ? '-' + fc.designator : ''}_${tu.designation}${tc ? '-' + tc.designator : ''}`);
      }
    }
  }, [fromUnitId, toUnitId, fromConnectorId, toConnectorId, units, fromConnectors, toConnectors]);

  const canSave = fromUnitId && fromConnectorId && toUnitId && toConnectorId && name.trim();

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true); setError('');
    try {
      await interfaceAPI.createHarness({
        name,
        description: description || undefined,
        from_unit_id: Number(fromUnitId),
        from_connector_id: Number(fromConnectorId),
        to_unit_id: Number(toUnitId),
        to_connector_id: Number(toConnectorId),
        project_id: projectId,
      });
      onCreated();
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to create connection');
    }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={onClose}>
      <div className="w-full max-w-xl rounded-2xl border border-astra-border bg-astra-surface p-6 shadow-2xl"
        onClick={e => e.stopPropagation()}>
        <h3 className="text-sm font-bold text-slate-200 mb-1">New Connection</h3>
        <p className="text-[11px] text-slate-500 mb-4">
          Select source and destination unit + connector to create a wire harness.
        </p>

        {error && (
          <div className="mb-3 rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
            <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" /> {error}
          </div>
        )}

        <div className="space-y-4">
          {/* From */}
          <div className="rounded-xl border border-astra-border bg-astra-bg p-4">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-emerald-400 mb-3">
              Source (From)
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] text-slate-500 mb-1 block">Unit</label>
                <select value={fromUnitId}
                  onChange={e => setFromUnitId(e.target.value ? Number(e.target.value) : '')}
                  className="w-full rounded-lg border border-astra-border bg-astra-surface px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50">
                  <option value="">Select unit...</option>
                  {units.map(u => (
                    <option key={u.id} value={u.id}>{u.designation} — {u.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-[10px] text-slate-500 mb-1 block">Connector</label>
                <select value={fromConnectorId}
                  onChange={e => setFromConnectorId(e.target.value ? Number(e.target.value) : '')}
                  disabled={!fromUnitId || loadingFrom}
                  className="w-full rounded-lg border border-astra-border bg-astra-surface px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50 disabled:opacity-40">
                  <option value="">{loadingFrom ? 'Loading...' : 'Select connector...'}</option>
                  {fromConnectors.map(c => (
                    <option key={c.id} value={c.id}>
                      {c.designator}{c.name ? ` — ${c.name}` : ''}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Arrow */}
          <div className="flex justify-center">
            <div className="flex h-8 w-8 items-center justify-center rounded-full border border-astra-border bg-astra-surface">
              <ArrowRight className="h-4 w-4 text-blue-400" />
            </div>
          </div>

          {/* To */}
          <div className="rounded-xl border border-astra-border bg-astra-bg p-4">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-violet-400 mb-3">
              Destination (To)
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] text-slate-500 mb-1 block">Unit</label>
                <select value={toUnitId}
                  onChange={e => setToUnitId(e.target.value ? Number(e.target.value) : '')}
                  className="w-full rounded-lg border border-astra-border bg-astra-surface px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50">
                  <option value="">Select unit...</option>
                  {units.map(u => (
                    <option key={u.id} value={u.id}>{u.designation} — {u.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-[10px] text-slate-500 mb-1 block">Connector</label>
                <select value={toConnectorId}
                  onChange={e => setToConnectorId(e.target.value ? Number(e.target.value) : '')}
                  disabled={!toUnitId || loadingTo}
                  className="w-full rounded-lg border border-astra-border bg-astra-surface px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50 disabled:opacity-40">
                  <option value="">{loadingTo ? 'Loading...' : 'Select connector...'}</option>
                  {toConnectors.map(c => (
                    <option key={c.id} value={c.id}>
                      {c.designator}{c.name ? ` — ${c.name}` : ''}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Name + Description */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">
                Harness Name
              </label>
              <input value={name} onChange={e => setName(e.target.value)}
                placeholder="Auto-generated or custom..."
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <div>
              <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">
                Description
              </label>
              <input value={description} onChange={e => setDescription(e.target.value)}
                placeholder="Optional..."
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
          </div>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose}
            className="rounded-lg border border-astra-border px-4 py-2 text-xs text-slate-400 hover:text-slate-200">
            Cancel
          </button>
          <button onClick={handleSave} disabled={saving || !canSave}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-40">
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Cable className="h-3.5 w-3.5" />}
            Create Connection
          </button>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  N² Matrix Component
// ══════════════════════════════════════

function N2Matrix({ data }: { data: N2MatrixResponse | null }) {
  if (!data || data.systems.length === 0) {
    return (
      <div className="py-12 text-center text-sm text-slate-500">
        No systems defined yet. Create systems and interfaces to populate the N² matrix.
      </div>
    );
  }
  const { systems, matrix } = data;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px]">
        <thead>
          <tr>
            <th className="border border-astra-border bg-astra-surface-alt p-2 text-left font-semibold text-slate-400">
              From ↓ / To →
            </th>
            {systems.map(s => (
              <th key={s.id}
                className="border border-astra-border bg-astra-surface-alt p-2 text-center font-semibold text-slate-400 max-w-[100px]">
                <div className="truncate">{s.abbreviation || s.name}</div>
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
                const critColor = cell?.criticality_max
                  ? CRITICALITY_COLORS[cell.criticality_max] || '#3B82F6'
                  : '#3B82F6';
                return (
                  <td key={tgt.id}
                    className={clsx(
                      'border border-astra-border p-2 text-center transition',
                      isDiag ? 'bg-astra-surface-alt' :
                      cell ? 'bg-blue-500/5 hover:bg-blue-500/10 cursor-pointer' : ''
                    )}>
                    {isDiag ? (
                      <span className="text-slate-600">—</span>
                    ) : cell ? (
                      <div>
                        <span className="font-bold" style={{ color: critColor }}>
                          {cell.interface_count}
                        </span>
                        {cell.harness_count > 0 && (
                          <span className="ml-1 text-slate-500">
                            ({cell.harness_count}h)
                          </span>
                        )}
                      </div>
                    ) : (
                      <span className="text-slate-700">·</span>
                    )}
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
//  Tab type
// ══════════════════════════════════════

type Tab = 'systems' | 'connections' | 'n2matrix';

// ══════════════════════════════════════
//  Main Page
// ══════════════════════════════════════

export default function InterfacesPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);
  const p = `/projects/${projectId}`;

  const [projectCode, setProjectCode] = useState('');
  const [tab, setTab]                 = useState<Tab>('systems');
  const [loading, setLoading]         = useState(true);

  // ── Core data ──
  const [systems, setSystems]     = useState<System[]>([]);
  const [units, setUnits]         = useState<UnitSummary[]>([]);
  const [harnesses, setHarnesses] = useState<WireHarness[]>([]);
  const [n2Data, setN2Data]       = useState<N2MatrixResponse | null>(null);
  const [coverage, setCoverage]   = useState<InterfaceCoverageResponse | null>(null);

  // ── unit_id → system mapping (built from SystemDetail calls) ──
  const [unitSystemMap, setUnitSystemMap] = useState<Record<number, number>>({});

  // ── UI state ──
  const [showCreateSystem, setShowCreateSystem]     = useState(false);
  const [showAddConnection, setShowAddConnection]   = useState(false);
  const [n2Visible, setN2Visible]                   = useState(false);
  const [systemSearch, setSystemSearch]              = useState('');
  const [systemTypeFilter, setSystemTypeFilter]      = useState('');
  const [connSystemFilter, setConnSystemFilter]      = useState<number | ''>('');
  const [connStatusFilter, setConnStatusFilter]      = useState('');
  const [connExpandedSys, setConnExpandedSys]        = useState<Set<number | 0>>(new Set());

  // ── Fetch everything ──
  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [projRes, sysRes, unitRes, harnRes, n2Res, covRes] = await Promise.all([
        projectsAPI.get(projectId),
        interfaceAPI.listSystems(projectId),
        interfaceAPI.listUnits(projectId),
        interfaceAPI.listHarnesses(projectId),
        interfaceAPI.getN2Matrix(projectId).catch(() => ({ data: null })),
        interfaceAPI.getCoverage(projectId).catch(() => ({ data: null })),
      ]);

      setProjectCode(projRes.data?.code || '');
      const sysList: System[] = sysRes.data || [];
      setSystems(sysList);
      setUnits(unitRes.data || []);
      setHarnesses(harnRes.data || []);
      setN2Data(n2Res.data || null);
      setCoverage(covRes.data || null);

      // Build unit → system map by fetching SystemDetail for each system
      const map: Record<number, number> = {};
      const detailPromises = sysList.map(s =>
        interfaceAPI.getSystem(s.id).catch(() => ({ data: null }))
      );
      const details = await Promise.all(detailPromises);
      for (const d of details) {
        const sd = d.data as SystemDetail | null;
        if (sd?.units) {
          for (const u of sd.units) {
            map[u.id] = sd.id;
          }
        }
      }
      setUnitSystemMap(map);

      // Auto-expand all system groups
      const expandSet = new Set<number | 0>([0, ...sysList.map(s => s.id)]);
      setConnExpandedSys(expandSet);
    } catch { }
    setLoading(false);
  }, [projectId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // ══════════════════════════════════════
  //  Derived data
  // ══════════════════════════════════════

  // ── Filtered systems ──
  const filteredSystems = useMemo(() => {
    return systems.filter(s => {
      if (systemSearch) {
        const q = systemSearch.toLowerCase();
        if (!s.name.toLowerCase().includes(q) &&
            !s.system_id.toLowerCase().includes(q) &&
            !(s.abbreviation || '').toLowerCase().includes(q)) return false;
      }
      if (systemTypeFilter && s.system_type !== systemTypeFilter) return false;
      return true;
    });
  }, [systems, systemSearch, systemTypeFilter]);

  // ── System types for filter dropdown ──
  const systemTypes = useMemo(() => {
    const t = new Set(systems.map(s => s.system_type));
    return [...t].sort();
  }, [systems]);

  // ── Harnesses grouped by system ──
  const harnessGroups = useMemo(() => {
    const groups = new Map<number, { system: System | null; harnesses: WireHarness[] }>();

    // Initialize groups for every system + an "ungrouped" bucket (key 0)
    groups.set(0, { system: null, harnesses: [] });
    for (const s of systems) {
      groups.set(s.id, { system: s, harnesses: [] });
    }

    for (const h of harnesses) {
      // Apply filters
      if (connStatusFilter && h.status !== connStatusFilter) continue;

      const sysId = unitSystemMap[h.from_unit_id] || 0;
      if (connSystemFilter && sysId !== Number(connSystemFilter)) continue;

      const group = groups.get(sysId) || groups.get(0)!;
      group.harnesses.push(h);
    }

    // Return only groups that have harnesses, unless a system filter is active
    const result: { sysId: number; sysName: string; harnesses: WireHarness[] }[] = [];
    for (const [sysId, { system, harnesses: hList }] of groups) {
      if (hList.length === 0 && !connSystemFilter) continue;
      if (connSystemFilter && sysId !== Number(connSystemFilter) && sysId !== 0) continue;
      result.push({
        sysId,
        sysName: system ? (system.abbreviation || system.name) : 'Ungrouped',
        harnesses: hList,
      });
    }

    // Sort: named systems first, ungrouped last
    return result.sort((a, b) => {
      if (a.sysId === 0) return 1;
      if (b.sysId === 0) return -1;
      return a.sysName.localeCompare(b.sysName);
    });
  }, [harnesses, systems, unitSystemMap, connSystemFilter, connStatusFilter]);

  const filteredHarnessCount = useMemo(() =>
    harnessGroups.reduce((s, g) => s + g.harnesses.length, 0),
  [harnessGroups]);

  // ── Toggle connection group ──
  const toggleConnGroup = (sysId: number) => {
    setConnExpandedSys(prev => {
      const next = new Set(prev);
      next.has(sysId) ? next.delete(sysId) : next.add(sysId);
      return next;
    });
  };

  // ── Unique harness statuses ──
  const harnessStatuses = useMemo(() => {
    const s = new Set(harnesses.map(h => h.status).filter(Boolean) as string[]);
    return [...s].sort();
  }, [harnesses]);

  // ── Summary counts ──
  const totalUnits      = units.length;
  const totalHarnesses  = harnesses.length;
  const totalInterfaces = coverage?.total_interfaces || 0;

  // ══════════════════════════════════════
  //  Render
  // ══════════════════════════════════════

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
            <Cable className="h-5 w-5 text-blue-400" /> Interface Management
          </h1>
          <p className="mt-0.5 text-sm text-slate-500">
            {projectCode} · Systems, connections, and interface control
          </p>
        </div>
      </div>

      {/* Summary stats */}
      {!loading && (
        <div className="mb-5 flex items-center gap-6 rounded-xl border border-astra-border bg-astra-surface px-5 py-3">
          <div className="flex items-center gap-2">
            <span className="text-2xl font-bold text-cyan-400">{systems.length}</span>
            <span className="text-[11px] text-slate-500">Systems</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-2xl font-bold text-blue-400">{totalUnits}</span>
            <span className="text-[11px] text-slate-500">Units</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-2xl font-bold text-emerald-400">{totalHarnesses}</span>
            <span className="text-[11px] text-slate-500">Harnesses</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-2xl font-bold text-violet-400">{totalInterfaces}</span>
            <span className="text-[11px] text-slate-500">Interfaces</span>
          </div>
          {coverage && (
            <>
              <div className="h-8 w-px bg-astra-border" />
              <CovStat label="Req Coverage"
                value={coverage.with_requirements} total={coverage.total_interfaces || 1}
                color="#3B82F6" />
              <CovStat label="Approved"
                value={coverage.approved_count} total={coverage.auto_generated_count || 1}
                color="#10B981" />
            </>
          )}
        </div>
      )}

      {/* ── Tabs ── */}
      <div className="mb-4 flex items-center gap-1 border-b border-astra-border">
        {([
          { key: 'systems' as Tab,     label: 'Systems',     icon: Network,   count: systems.length },
          { key: 'connections' as Tab,  label: 'Connections', icon: Cable,     count: harnesses.length },
          { key: 'n2matrix' as Tab,     label: 'N² Matrix',  icon: Grid3X3,   count: null },
        ]).map(t => (
          <button key={t.key}
            onClick={() => setTab(t.key)}
            className={clsx(
              'flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-xs font-semibold transition',
              tab === t.key
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-slate-500 hover:text-slate-300'
            )}>
            <t.icon className="h-3.5 w-3.5" />
            {t.label}
            {t.count !== null && (
              <span className={clsx(
                'ml-1 rounded-full px-1.5 py-0.5 text-[10px] font-bold',
                tab === t.key
                  ? 'bg-blue-500/20 text-blue-400'
                  : 'bg-astra-surface-alt text-slate-600'
              )}>
                {t.count}
              </span>
            )}
          </button>
        ))}
        <div className="flex-1" />
        <button onClick={() => router.push(`/projects/${projectId}/interfaces/import`)}
          className="flex items-center gap-1.5 rounded-lg border border-astra-border bg-astra-surface px-3 py-1.5 text-[11px] font-semibold text-slate-300 transition hover:border-emerald-500/40 hover:text-emerald-400"
          title="Import units, connectors, and pins from an Excel template">
          <FileSpreadsheet className="h-3.5 w-3.5" />
          Import from Excel
        </button>
        <button onClick={fetchData}
          className="rounded-lg p-2 text-slate-500 hover:text-slate-300" title="Refresh">
          <RefreshCw className={clsx('h-3.5 w-3.5', loading && 'animate-spin')} />
        </button>
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
        </div>
      )}

      {/* ══════════════════════════════════════ */}
      {/*  SYSTEMS TAB                          */}
      {/* ══════════════════════════════════════ */}
      {tab === 'systems' && !loading && (
        <div>
          {/* Toolbar */}
          <div className="mb-4 flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
              <input value={systemSearch} onChange={e => setSystemSearch(e.target.value)}
                placeholder="Search systems by name, ID, or abbreviation..."
                className="w-full rounded-lg border border-astra-border bg-astra-surface pl-9 pr-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            {systemTypes.length > 1 && (
              <select value={systemTypeFilter}
                onChange={e => setSystemTypeFilter(e.target.value)}
                className="rounded-lg border border-astra-border bg-astra-surface px-3 py-2 text-sm text-slate-300 outline-none focus:border-blue-500/50">
                <option value="">All Types</option>
                {systemTypes.map(t => (
                  <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
                ))}
              </select>
            )}
            <button onClick={() => setShowCreateSystem(true)}
              className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-500">
              <Plus className="h-3.5 w-3.5" /> Add System
            </button>
          </div>

          {/* Card grid */}
          {filteredSystems.length === 0 ? (
            <div className="py-16 text-center">
              <Network className="mx-auto h-10 w-10 text-slate-600 mb-3" />
              <p className="text-sm text-slate-400">
                {systems.length === 0
                  ? 'No systems defined yet. Click "Add System" to get started.'
                  : 'No systems match your search.'}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
              {filteredSystems.map(s => (
                <div key={s.id}
                  className="group rounded-xl border border-astra-border bg-astra-surface p-4 hover:border-blue-500/30 transition cursor-pointer"
                  onClick={() => router.push(`${p}/interfaces/system/${s.id}`)}>
                  {/* System ID + Status */}
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-mono text-xs font-bold text-cyan-400">
                      {s.system_id}
                    </span>
                    <StatusBadge status={s.status} />
                  </div>
                  {/* Name */}
                  <h3 className="text-[14px] font-semibold text-slate-200 mb-0.5 group-hover:text-blue-300 transition">
                    {s.name}
                  </h3>
                  {s.abbreviation && (
                    <p className="text-[11px] text-slate-500 mb-2">({s.abbreviation})</p>
                  )}
                  {/* Type badge */}
                  <span className="inline-flex items-center gap-1 rounded-full bg-astra-surface-alt px-2 py-0.5 text-[10px] font-semibold text-slate-400 capitalize mb-3">
                    <SystemTypeIcon type={s.system_type} />
                    {s.system_type.replace(/_/g, ' ')}
                  </span>
                  {/* Stats */}
                  <div className="flex gap-4 pt-3 border-t border-astra-border">
                    <div className="text-center">
                      <div className="text-lg font-bold text-slate-300">{s.unit_count}</div>
                      <div className="text-[9px] text-slate-500">Units</div>
                    </div>
                    <div className="text-center">
                      <div className="text-lg font-bold text-slate-300">{s.interface_count}</div>
                      <div className="text-[9px] text-slate-500">Interfaces</div>
                    </div>
                    <div className="flex-1 flex items-center justify-end">
                      <ChevronRight className="h-4 w-4 text-slate-600 group-hover:text-blue-400 transition" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ══════════════════════════════════════ */}
      {/*  CONNECTIONS TAB                      */}
      {/* ══════════════════════════════════════ */}
      {tab === 'connections' && !loading && (
        <div>
          {/* Toolbar */}
          <div className="mb-4 flex gap-2">
            {systems.length > 0 && (
              <select value={connSystemFilter}
                onChange={e => setConnSystemFilter(e.target.value ? Number(e.target.value) : '')}
                className="rounded-lg border border-astra-border bg-astra-surface px-3 py-2 text-sm text-slate-300 outline-none focus:border-blue-500/50">
                <option value="">All Systems</option>
                {systems.map(s => (
                  <option key={s.id} value={s.id}>{s.abbreviation || s.name}</option>
                ))}
              </select>
            )}
            {harnessStatuses.length > 1 && (
              <select value={connStatusFilter}
                onChange={e => setConnStatusFilter(e.target.value)}
                className="rounded-lg border border-astra-border bg-astra-surface px-3 py-2 text-sm text-slate-300 outline-none focus:border-blue-500/50">
                <option value="">All Statuses</option>
                {harnessStatuses.map(s => (
                  <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
                ))}
              </select>
            )}
            <div className="flex-1" />
            <button onClick={() => setShowAddConnection(true)}
              className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-500">
              <Plus className="h-3.5 w-3.5" /> Add Connection
            </button>
          </div>

          {/* Empty state */}
          {harnesses.length === 0 ? (
            <div className="py-16 text-center">
              <Cable className="mx-auto h-10 w-10 text-slate-600 mb-3" />
              <p className="text-sm text-slate-400">
                No connections defined yet. Click "Add Connection" to create a wire harness.
              </p>
            </div>
          ) : filteredHarnessCount === 0 ? (
            <div className="py-12 text-center">
              <Search className="mx-auto h-8 w-8 text-slate-600 mb-2" />
              <p className="text-sm text-slate-400">No connections match your filters.</p>
            </div>
          ) : (
            /* Grouped harness list */
            <div className="space-y-4">
              {harnessGroups.map(group => {
                if (group.harnesses.length === 0) return null;
                const isOpen = connExpandedSys.has(group.sysId);
                return (
                  <div key={group.sysId}>
                    {/* Group header */}
                    <button onClick={() => toggleConnGroup(group.sysId)}
                      className="mb-2 flex w-full items-center gap-2 text-left">
                      {isOpen
                        ? <ChevronDown className="h-3.5 w-3.5 text-slate-500" />
                        : <ChevronRight className="h-3.5 w-3.5 text-slate-500" />}
                      <Network className="h-3.5 w-3.5 text-cyan-400" />
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                        {group.sysName}
                      </span>
                      <span className="rounded-full bg-astra-surface-alt px-1.5 py-0.5 text-[9px] font-bold text-slate-500">
                        {group.harnesses.length}
                      </span>
                    </button>

                    {isOpen && (
                      <div className="space-y-1.5 ml-6 mb-2">
                        {group.harnesses.map(h => (
                          <div key={h.id}
                            className="flex items-center gap-3 rounded-xl border border-astra-border bg-astra-surface px-4 py-3 hover:border-blue-500/20 cursor-pointer transition"
                            onClick={() => router.push(`${p}/interfaces/harness/${h.id}`)}>
                            <Cable className="h-4 w-4 text-emerald-500 flex-shrink-0" />
                            <div className="w-36 flex-shrink-0">
                              <span className="text-[13px] font-medium text-slate-200 truncate block">
                                {h.name}
                              </span>
                              {h.harness_id && (
                                <span className="text-[10px] font-mono text-slate-500">
                                  {h.harness_id}
                                </span>
                              )}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-1.5 text-[12px] text-slate-400">
                                <span className="font-mono text-emerald-400">
                                  {h.from_unit_designation}
                                </span>
                                <span className="text-slate-600">
                                  ({h.from_connector_designator})
                                </span>
                                <ArrowRight className="h-3 w-3 text-slate-600" />
                                <span className="font-mono text-violet-400">
                                  {h.to_unit_designation}
                                </span>
                                <span className="text-slate-600">
                                  ({h.to_connector_designator})
                                </span>
                              </div>
                            </div>
                            <span className="rounded-full bg-astra-surface-alt px-2 py-0.5 text-[10px] font-bold text-slate-400">
                              {h.wire_count} wires
                            </span>
                            <StatusBadge status={h.status || 'concept'} />
                            <ChevronRight className="h-4 w-4 text-slate-600 flex-shrink-0" />
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
      )}

      {/* ══════════════════════════════════════ */}
      {/*  N² MATRIX TAB                        */}
      {/* ══════════════════════════════════════ */}
      {tab === 'n2matrix' && !loading && (
        <div>
          {!n2Visible ? (
            /* Hidden by default — show expand button */
            <div className="py-16 text-center">
              <Grid3X3 className="mx-auto h-10 w-10 text-slate-600 mb-3" />
              <p className="text-sm text-slate-400 mb-4">
                The N² Interface Matrix shows all system-to-system interface relationships.
              </p>
              <button onClick={() => setN2Visible(true)}
                className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-5 py-2.5 text-xs font-semibold text-white hover:bg-violet-500">
                <Grid3X3 className="h-4 w-4" /> Expand N² Matrix
              </button>
            </div>
          ) : (
            /* Matrix visible */
            <div className="rounded-xl border border-violet-500/20 bg-astra-surface p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-bold text-slate-300 flex items-center gap-2">
                  <Grid3X3 className="h-4 w-4 text-violet-400" /> N² Interface Matrix
                </h3>
                <button onClick={() => setN2Visible(false)}
                  className="flex items-center gap-1 rounded-lg border border-astra-border px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200">
                  <X className="h-3.5 w-3.5" /> Collapse
                </button>
              </div>
              <N2Matrix data={n2Data} />
            </div>
          )}
        </div>
      )}

      {/* ══════════════════════════════════════ */}
      {/*  MODALS                                */}
      {/* ══════════════════════════════════════ */}
      {showCreateSystem && (
        <CreateSystemModal projectId={projectId}
          onClose={() => setShowCreateSystem(false)} onCreated={fetchData} />
      )}
      {showAddConnection && (
        <AddConnectionModal projectId={projectId} units={units}
          onClose={() => setShowAddConnection(false)} onCreated={fetchData} />
      )}
    </div>
  );
}
