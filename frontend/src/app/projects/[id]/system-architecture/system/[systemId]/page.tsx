'use client';

/**
 * ASTRA — System Detail Page
 * ==============================
 * File: frontend/src/app/projects/[id]/system-architecture/system/[systemId]/page.tsx
 *
 * Relocated from /interfaces/system/[systemId]/ to /system-architecture/...
 * by TDD-SYSARCH-002 Phase 6. The old path 307-redirects via
 * frontend/next.config.js so existing bookmarks survive.
 *
 * Layout per spec:
 *   1. Breadcrumb: Interfaces → {System Name}
 *   2. Header: name, abbreviation, type badge, status badge, Edit/Delete/Refresh
 *   3. System Metadata: description, WBS, responsible org, parent system
 *   4. Units Section: 2-col card grid, Add Unit, Delete Unit
 *   5. Empty state when no units
 *
 * API calls:
 *   - interfaceAPI.getSystem(systemId)         → SystemDetail (includes units[])
 *   - interfaceAPI.updateSystem(systemId, data) → SystemResponse
 *   - interfaceAPI.deleteSystem(systemId, force) → { status, units_deleted }
 *   - interfaceAPI.createUnit(projectId, data)  → UnitResponse
 *   - interfaceAPI.deleteUnit(unitId, confirm)   → { status }
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft, Loader2, Edit3, Save, X, Plus, Trash2, RefreshCw,
  Box, Cpu, Cable, Radio, Zap, Shield, Network, ChevronRight,
  AlertTriangle, Search, GitMerge, Link2,
} from 'lucide-react';
import clsx from 'clsx';
import { interfaceAPI } from '@/lib/interface-api';
import type { SystemDetail, UnitSummary, Connection, WireHarness, UnitType } from '@/lib/interface-types';

// ══════════════════════════════════════
//  Constants
// ══════════════════════════════════════

const SYSTEM_TYPES = [
  'subsystem', 'lru', 'wru', 'sru', 'sensor_suite', 'actuator_assembly',
  'processor_unit', 'power_system', 'thermal_system', 'structural',
  'ground_segment', 'vehicle', 'payload', 'antenna_system', 'propulsion',
  'guidance_nav_control', 'communication', 'data_handling', 'ordnance',
  'test_equipment', 'external_system', 'software', 'firmware', 'custom',
];

const SYSTEM_STATUSES = [
  'concept', 'preliminary_design', 'detailed_design', 'fabrication',
  'integration', 'qualification_test', 'acceptance_test', 'operational',
  'maintenance', 'retired', 'obsolete',
];

const UNIT_TYPES = [
  'lru', 'wru', 'sru', 'cca', 'pcb', 'backplane', 'chassis',
  'sensor', 'actuator', 'motor', 'processor', 'fpga', 'asic',
  'power_supply', 'power_converter', 'battery', 'solar_panel',
  'transmitter', 'receiver', 'transceiver', 'antenna', 'waveguide',
  'filter_rf', 'amplifier', 'oscillator', 'switch_rf', 'diplexer',
  'coupler', 'cable_assembly', 'connector_assembly', 'relay_box',
  'junction_box', 'terminal_block', 'fuse_box', 'transformer',
  'regulator', 'gyroscope', 'accelerometer', 'star_tracker',
  'sun_sensor', 'earth_sensor', 'gps_receiver',
  'inertial_measurement_unit', 'reaction_wheel', 'thruster', 'valve',
  'pyrotechnic', 'cots_equipment', 'gse', 'firmware_module',
  'software_module', 'custom',
];

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
  prototype:          { bg: 'rgba(245,158,11,0.15)',  text: '#F59E0B' },
  engineering_model:  { bg: 'rgba(6,182,212,0.15)',   text: '#06B6D4' },
  flight_unit:        { bg: 'rgba(16,185,129,0.20)',  text: '#10B981' },
  flight_spare:       { bg: 'rgba(16,185,129,0.10)',  text: '#34D399' },
  production:         { bg: 'rgba(59,130,246,0.15)',  text: '#60A5FA' },
  installed:          { bg: 'rgba(16,185,129,0.15)',  text: '#10B981' },
  qualified:          { bg: 'rgba(16,185,129,0.25)',  text: '#34D399' },
  accepted:           { bg: 'rgba(16,185,129,0.30)',  text: '#34D399' },
  maintenance:        { bg: 'rgba(245,158,11,0.12)',  text: '#FBBF24' },
  retired:            { bg: 'rgba(107,114,128,0.15)', text: '#6B7280' },
  obsolete:           { bg: 'rgba(107,114,128,0.10)', text: '#4B5563' },
  failed:             { bg: 'rgba(239,68,68,0.15)',   text: '#EF4444' },
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

const UNIT_ICONS: Record<string, any> = {
  processor: Cpu, antenna: Radio, power_supply: Zap,
  sensor: Shield, transceiver: Cable, transmitter: Radio,
  receiver: Radio, default: Box,
};

function UnitIcon({ type }: { type: string }) {
  const Icon = UNIT_ICONS[type] || UNIT_ICONS.default;
  return <Icon className="h-4 w-4 flex-shrink-0 text-slate-500" />;
}

// ── Metadata row ──
function MetaRow({ label, value }: { label: string; value?: string | number | null }) {
  if (value === null || value === undefined || value === '') return null;
  return (
    <div className="flex items-start justify-between py-2 border-b border-astra-border/50 last:border-0">
      <span className="text-[11px] text-slate-500 flex-shrink-0 w-40">{label}</span>
      <span className="text-[12px] font-medium text-slate-300 text-right">{String(value)}</span>
    </div>
  );
}

// ══════════════════════════════════════
//  Delete System Confirmation
// ══════════════════════════════════════

function DeleteSystemDialog({ system, onClose, onConfirm }: {
  system: SystemDetail; onClose: () => void; onConfirm: () => void;
}) {
  const [deleting, setDeleting] = useState(false);
  const handleDelete = async () => { setDeleting(true); await onConfirm(); setDeleting(false); };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl border border-red-500/20 bg-astra-surface p-6 shadow-2xl"
        onClick={e => e.stopPropagation()}>
        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-500/10">
            <AlertTriangle className="h-5 w-5 text-red-400" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-200">Delete System</h3>
            <p className="text-[11px] text-slate-500">This action cannot be undone.</p>
          </div>
        </div>
        <div className="rounded-lg bg-astra-bg border border-astra-border p-3 mb-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="font-mono text-xs font-bold text-cyan-400">{system.system_id}</span>
            <span className="text-sm text-slate-300">{system.name}</span>
          </div>
          {system.unit_count > 0 && (
            <div className="mt-1 text-[11px]">
              <p className="text-red-400 font-semibold">
                This will cascade delete {system.unit_count} unit{system.unit_count !== 1 ? 's' : ''} and all their connectors, pins, buses, and wires.
              </p>
            </div>
          )}
          {system.interface_count > 0 && (
            <p className="mt-1 text-[11px] text-yellow-400">
              {system.interface_count} interface{system.interface_count !== 1 ? 's' : ''} reference this system.
            </p>
          )}
        </div>
        <div className="flex justify-end gap-2">
          <button onClick={onClose}
            className="rounded-lg border border-astra-border px-4 py-2 text-xs text-slate-400 hover:text-slate-200">
            Cancel
          </button>
          <button onClick={handleDelete} disabled={deleting}
            className="flex items-center gap-1.5 rounded-lg bg-red-600 px-4 py-2 text-xs font-semibold text-white hover:bg-red-500 disabled:opacity-40">
            {deleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
            Delete System
          </button>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  Delete Unit Confirmation
// ══════════════════════════════════════

function DeleteUnitDialog({ unit, onClose, onConfirm }: {
  unit: UnitSummary; onClose: () => void; onConfirm: () => void;
}) {
  const [deleting, setDeleting] = useState(false);
  const handleDelete = async () => { setDeleting(true); await onConfirm(); setDeleting(false); };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl border border-red-500/20 bg-astra-surface p-6 shadow-2xl"
        onClick={e => e.stopPropagation()}>
        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-500/10">
            <AlertTriangle className="h-5 w-5 text-red-400" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-200">Delete Unit</h3>
            <p className="text-[11px] text-slate-500">This action cannot be undone.</p>
          </div>
        </div>
        <div className="rounded-lg bg-astra-bg border border-astra-border p-3 mb-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="font-mono text-xs font-bold text-blue-400">{unit.designation}</span>
            <span className="text-sm text-slate-300">{unit.name}</span>
          </div>
          <p className="text-[11px] text-slate-500">This will cascade delete:</p>
          <div className="mt-1 flex gap-4 text-[11px]">
            <span className="text-red-400 font-semibold">{unit.connector_count} connector{unit.connector_count !== 1 ? 's' : ''}</span>
            <span className="text-red-400 font-semibold">{unit.bus_count} bus{unit.bus_count !== 1 ? 'es' : ''}</span>
            <span className="text-slate-500">+ all pins, wires, harness refs</span>
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <button onClick={onClose}
            className="rounded-lg border border-astra-border px-4 py-2 text-xs text-slate-400 hover:text-slate-200">
            Cancel
          </button>
          <button onClick={handleDelete} disabled={deleting}
            className="flex items-center gap-1.5 rounded-lg bg-red-600 px-4 py-2 text-xs font-semibold text-white hover:bg-red-500 disabled:opacity-40">
            {deleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
            Delete Unit
          </button>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  Add Unit Modal
// ══════════════════════════════════════

function AddUnitModal({ projectId, systemId, onClose, onCreated }: {
  projectId: number; systemId: number; onClose: () => void; onCreated: () => void;
}) {
  const [name, setName]               = useState('');
  const [designation, setDesignation]  = useState('');
  const [partNumber, setPartNumber]    = useState('');
  const [manufacturer, setManufacturer] = useState('');
  const [unitType, setUnitType]        = useState<UnitType>('lru');
  const [desc, setDesc]                = useState('');
  const [saving, setSaving]            = useState(false);
  const [error, setError]              = useState('');

  const canSave = name.trim() && designation.trim() && partNumber.trim() && manufacturer.trim();

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true);
    setError('');
    try {
      await interfaceAPI.createUnit(projectId, {
        name,
        designation,
        part_number: partNumber,
        manufacturer,
        unit_type: unitType,
        system_id: systemId,
        description: desc || undefined,
      });
      onCreated();
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to create unit');
    }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl border border-astra-border bg-astra-surface p-6 shadow-2xl"
        onClick={e => e.stopPropagation()}>
        <h3 className="text-sm font-bold text-slate-200 mb-1">Add Unit</h3>
        <p className="text-[11px] text-slate-500 mb-4">
          Fields marked * are required. The unit will be added to this system.
        </p>

        {error && (
          <div className="mb-3 rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
            <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" /> {error}
          </div>
        )}

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">
                Name *
              </label>
              <input value={name} onChange={e => setName(e.target.value)}
                placeholder="e.g. Flight Computer"
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <div>
              <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">
                Designation *
              </label>
              <input value={designation} onChange={e => setDesignation(e.target.value)}
                placeholder="e.g. FCA-001"
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">
                Part Number *
              </label>
              <input value={partNumber} onChange={e => setPartNumber(e.target.value)}
                placeholder="e.g. PN-2024-001"
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <div>
              <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">
                Manufacturer *
              </label>
              <input value={manufacturer} onChange={e => setManufacturer(e.target.value)}
                placeholder="e.g. BAE Systems"
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
          </div>

          <div>
            <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">
              Unit Type
            </label>
            <select value={unitType} onChange={e => setUnitType(e.target.value as UnitType)}
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50">
              {UNIT_TYPES.map(t => (
                <option key={t} value={t}>{t.replace(/_/g, ' ').toUpperCase()}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">
              Description
            </label>
            <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={2}
              placeholder="Optional..."
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50 resize-none" />
          </div>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose}
            className="rounded-lg border border-astra-border px-4 py-2 text-xs text-slate-400 hover:text-slate-200">
            Cancel
          </button>
          <button onClick={handleSave} disabled={saving || !canSave}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-40">
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
            Create Unit
          </button>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  Main Page
// ══════════════════════════════════════

// ══════════════════════════════════════════════════════════════
//  Phase 3a: System-scoped Connections + Harnesses section
// ══════════════════════════════════════════════════════════════

/**
 * Two sub-panels (Connections and Harnesses) scoped to one system.
 *
 * Per Mason's spec:
 *  - Connections: show connection rows where at least one endpoint LRU is
 *    in this system. The backend's ?system_id filter already enforces
 *    that rule, so we render whatever the API returned.
 *  - Harnesses: show harnesses where at least one endpoint LRU is in
 *    this system. Backend's harness endpoint doesn't yet accept a system
 *    filter, so we filter client-side using the system's unit id set.
 *
 * Both are read-only here — click through to the connection detail /
 * harness detail page for edits. Kept as a component (not inline JSX)
 * so the section is self-contained and easy to move around later.
 */
function SystemConnectionsSection({
  projectId, systemId, systemUnitIds,
  connections, harnesses,
}: {
  projectId: number;
  systemId: number;
  systemUnitIds: Set<number>;
  connections: Connection[];
  harnesses: WireHarness[];
}) {
  const router = useRouter();
  const p = `/projects/${projectId}`;

  // Filter harnesses: include one if at least one of its (from, to) units
  // is in this system. Defensive against null unit_ids (shouldn't happen
  // but we handle it rather than crash).
  const systemHarnesses = useMemo(() => {
    return harnesses.filter(h => {
      const f = h.from_unit_id;
      const t = h.to_unit_id;
      return (f != null && systemUnitIds.has(f)) ||
             (t != null && systemUnitIds.has(t));
    });
  }, [harnesses, systemUnitIds]);

  if (connections.length === 0 && systemHarnesses.length === 0) {
    // No wiring at all in this system — skip the section entirely rather
    // than showing two empty-state blocks.
    return null;
  }

  return (
    <div className="space-y-6 mt-8">
      {/* ── Connections ── */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <GitMerge className="h-4 w-4 text-cyan-400" />
          <h2 className="text-sm font-bold text-slate-200">Connections</h2>
          <span className="rounded-full bg-astra-surface-alt px-2 py-0.5 text-[10px] font-bold text-slate-500">
            {connections.length}
          </span>
        </div>

        {connections.length === 0 ? (
          <div className="rounded-xl border border-astra-border bg-astra-surface py-6 text-center">
            <p className="text-sm text-slate-500">
              No connections in this system yet.
            </p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="border-b border-astra-border bg-astra-surface-alt">
                  <th className="px-3 py-2 text-left font-semibold text-slate-400">LRU Pair</th>
                  <th className="px-3 py-2 text-left font-semibold text-slate-400 w-20">Wires</th>
                  <th className="px-3 py-2 text-left font-semibold text-slate-400">Harnesses</th>
                  <th className="px-3 py-2 w-10" />
                </tr>
              </thead>
              <tbody>
                {connections.map(c => (
                  <tr
                    key={c.id}
                    onClick={() => router.push(`${p}/interfaces/connection/${c.id}`)}
                    className="border-b border-astra-border hover:bg-astra-surface-alt/50 cursor-pointer transition">
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2 font-mono">
                        <span className="text-cyan-300">{c.lru_a_designation}</span>
                        <span className="text-slate-500">—</span>
                        <span className="text-violet-300">{c.lru_b_designation}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <span className="rounded-full bg-astra-surface-alt px-2 py-0.5 text-[11px] font-bold text-slate-300">
                        {c.wire_count}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {(c.harness_names || []).slice(0, 3).map((name, i) => (
                          <span
                            key={c.harness_ids?.[i] || i}
                            className="rounded-full bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 text-[10px] text-emerald-300">
                            {name}
                          </span>
                        ))}
                        {(c.harness_names || []).length > 3 && (
                          <span className="text-[10px] text-slate-500 self-center">
                            +{c.harness_names.length - 3}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <ChevronRight className="h-4 w-4 text-slate-600" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Harnesses ── */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Cable className="h-4 w-4 text-emerald-400" />
          <h2 className="text-sm font-bold text-slate-200">Harnesses</h2>
          <span className="rounded-full bg-astra-surface-alt px-2 py-0.5 text-[10px] font-bold text-slate-500">
            {systemHarnesses.length}
          </span>
        </div>

        {systemHarnesses.length === 0 ? (
          <div className="rounded-xl border border-astra-border bg-astra-surface py-6 text-center">
            <p className="text-sm text-slate-500">
              No harnesses in this system yet.
            </p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="border-b border-astra-border bg-astra-surface-alt">
                  <th className="px-3 py-2 text-left font-semibold text-slate-400">Harness</th>
                  <th className="px-3 py-2 text-left font-semibold text-slate-400">Endpoints</th>
                  <th className="px-3 py-2 text-left font-semibold text-slate-400 w-20">Wires</th>
                  <th className="px-3 py-2 w-10" />
                </tr>
              </thead>
              <tbody>
                {systemHarnesses.map(h => (
                  <tr
                    key={h.id}
                    onClick={() => router.push(`${p}/interfaces/harness/${h.id}`)}
                    className="border-b border-astra-border hover:bg-astra-surface-alt/50 cursor-pointer transition">
                    <td className="px-3 py-2">
                      <div className="font-semibold text-slate-200">{h.name}</div>
                      {h.harness_id && (
                        <div className="text-[10px] font-mono text-slate-500">{h.harness_id}</div>
                      )}
                    </td>
                    <td className="px-3 py-2 text-[11px] text-slate-400">
                      <span className="font-mono text-emerald-400">
                        {h.from_unit_designation}
                      </span>
                      <span className="text-slate-600 mx-1">—</span>
                      <span className="font-mono text-violet-400">
                        {h.to_unit_designation}
                      </span>
                      {h.endpoints && h.endpoints.length > 2 && (
                        <span className="ml-2 text-[10px] text-amber-400">
                          +{h.endpoints.length - 2} more
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <span className="rounded-full bg-astra-surface-alt px-2 py-0.5 text-[11px] font-bold text-slate-300">
                        {h.wire_count}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <ChevronRight className="h-4 w-4 text-slate-600" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
//  Main page
// ══════════════════════════════════════════════════════════════

export default function SystemDetailPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);
  const systemId  = Number(params.systemId);
  const p = `/projects/${projectId}`;

  // ── State ──
  const [system, setSystem]               = useState<SystemDetail | null>(null);
  const [loading, setLoading]             = useState(true);
  const [editing, setEditing]             = useState(false);
  const [editFields, setEditFields]       = useState<Record<string, any>>({});
  const [savingEdit, setSavingEdit]       = useState(false);
  const [showAddUnit, setShowAddUnit]     = useState(false);
  const [deleteUnitTarget, setDeleteUnitTarget] = useState<UnitSummary | null>(null);
  const [showDeleteSystem, setShowDeleteSystem] = useState(false);
  const [unitSearch, setUnitSearch]       = useState('');
  const [msg, setMsg]                     = useState('');

  // Phase 3a: System-scoped Connections + Harnesses.
  // Per spec, a Connection is shown in this system if AT LEAST ONE of its
  // two LRUs belongs to this system. The backend's ?system_id filter
  // applies that rule server-side. Harnesses are filtered client-side
  // against the system's unit list.
  const [connections, setConnections] = useState<Connection[]>([]);
  const [harnesses, setHarnesses]     = useState<WireHarness[]>([]);

  // ── Fetch ──
  const fetchSystem = useCallback(async () => {
    setLoading(true);
    try {
      // Parallel fetch: system detail + system-scoped connections + all
      // harnesses for this project. We filter harnesses to this system
      // below (one-side-in-system rule) since the harness list endpoint
      // doesn't yet have a system_id filter server-side.
      const [sysRes, connRes, harnRes] = await Promise.all([
        interfaceAPI.getSystem(systemId),
        interfaceAPI.listConnections(projectId, systemId).catch(() => ({ data: [] })),
        interfaceAPI.listHarnesses(projectId).catch(() => ({ data: [] })),
      ]);
      setSystem(sysRes.data);
      setConnections(connRes.data || []);
      setHarnesses(harnRes.data || []);
    } catch { }
    setLoading(false);
  }, [systemId, projectId]);

  useEffect(() => { fetchSystem(); }, [fetchSystem]);

  // ── Start inline edit ──
  const startEdit = () => {
    if (!system) return;
    setEditFields({
      name: system.name,
      abbreviation: system.abbreviation || '',
      system_type: system.system_type,
      status: system.status,
      description: system.description || '',
      wbs_number: system.wbs_number || '',
      responsible_org: system.responsible_org || '',
    });
    setEditing(true);
  };

  // ── Save inline edit ──
  const saveEdit = async () => {
    setSavingEdit(true);
    try {
      const data: Record<string, any> = {};
      for (const [k, v] of Object.entries(editFields)) {
        data[k] = v === '' ? null : v;
      }
      await interfaceAPI.updateSystem(systemId, data);
      setEditing(false);
      setEditFields({});
      setMsg('System updated');
      fetchSystem();
    } catch (e: any) {
      setMsg(e?.response?.data?.detail || 'Save failed');
    }
    setSavingEdit(false);
    setTimeout(() => setMsg(''), 3000);
  };

  // ── Delete system ──
  const handleDeleteSystem = async () => {
    try {
      await interfaceAPI.deleteSystem(systemId, true);
      router.push(`${p}/system-architecture?tab=systems`);
    } catch (e: any) {
      setMsg(e?.response?.data?.detail || 'Delete failed');
      setShowDeleteSystem(false);
      setTimeout(() => setMsg(''), 4000);
    }
  };

  // ── Delete unit ──
  const handleDeleteUnit = async () => {
    if (!deleteUnitTarget) return;
    try {
      await interfaceAPI.deleteUnit(deleteUnitTarget.id, true);
      setDeleteUnitTarget(null);
      fetchSystem();
    } catch (e: any) {
      setMsg(e?.response?.data?.detail || 'Delete failed');
      setDeleteUnitTarget(null);
      setTimeout(() => setMsg(''), 4000);
    }
  };

  // ── Filtered units ──
  const filteredUnits = useMemo(() => {
    if (!system) return [];
    if (!unitSearch) return system.units;
    const q = unitSearch.toLowerCase();
    return system.units.filter(u =>
      u.name.toLowerCase().includes(q) ||
      u.designation.toLowerCase().includes(q) ||
      u.part_number.toLowerCase().includes(q) ||
      u.manufacturer.toLowerCase().includes(q)
    );
  }, [system, unitSearch]);

  // ── Loading / not found ──
  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
      </div>
    );
  }
  if (!system) {
    return (
      <div className="py-20 text-center">
        <AlertTriangle className="mx-auto h-10 w-10 text-red-400 mb-3" />
        <p className="text-sm text-slate-400">System not found.</p>
        <button onClick={() => router.push(`${p}/system-architecture?tab=systems`)}
          className="mt-3 text-xs text-blue-400 hover:underline">
          Back to System Architecture
        </button>
      </div>
    );
  }

  // ══════════════════════════════════════
  //  Render
  // ══════════════════════════════════════

  return (
    <div>
      {/* ─── 1. Breadcrumb ─── */}
      <div className="mb-4 flex items-center gap-1.5 text-[11px] text-slate-500">
        <button onClick={() => router.push(`${p}/system-architecture?tab=systems`)}
          className="hover:text-blue-400 transition">
          System Architecture
        </button>
        <ChevronRight className="h-3 w-3" />
        <span className="text-slate-300 font-semibold">{system.name}</span>
      </div>

      {/* ─── 2. Header ─── */}
      <div className="mb-6 flex items-start justify-between">
        <div className="flex items-start gap-4">
          <button onClick={() => router.push(`${p}/system-architecture?tab=systems`)}
            className="mt-1 rounded-lg border border-astra-border p-2 text-slate-500 hover:text-slate-300 hover:border-blue-500/30 transition">
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div>
            <h1 className="text-xl font-bold text-slate-100 tracking-tight flex items-center gap-2">
              {system.name}
              {system.abbreviation && (
                <span className="rounded-full bg-blue-500/15 px-2.5 py-0.5 text-xs font-semibold text-blue-400">
                  {system.abbreviation}
                </span>
              )}
            </h1>
            <div className="mt-1.5 flex items-center gap-2">
              <span className="font-mono text-[11px] text-cyan-400">{system.system_id}</span>
              <span className="inline-flex items-center gap-1 rounded-full bg-astra-surface-alt px-2 py-0.5 text-[10px] font-semibold text-slate-400 capitalize">
                {system.system_type.replace(/_/g, ' ')}
              </span>
              <StatusBadge status={system.status} />
            </div>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          <button onClick={fetchSystem}
            className="rounded-lg border border-astra-border p-2 text-slate-500 hover:text-slate-300"
            title="Refresh">
            <RefreshCw className={clsx('h-3.5 w-3.5', loading && 'animate-spin')} />
          </button>
          {!editing && (
            <button onClick={startEdit}
              className="flex items-center gap-1.5 rounded-lg border border-astra-border px-3 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200 hover:border-blue-500/30">
              <Edit3 className="h-3.5 w-3.5" /> Edit System
            </button>
          )}
          <button onClick={() => setShowDeleteSystem(true)}
            className="flex items-center gap-1.5 rounded-lg border border-red-500/20 px-3 py-2 text-xs font-semibold text-red-400 hover:bg-red-500/10">
            <Trash2 className="h-3.5 w-3.5" /> Delete
          </button>
        </div>
      </div>

      {/* ─── Message ─── */}
      {msg && (
        <div className={clsx(
          'mb-4 rounded-lg border px-3 py-2 text-xs flex items-center gap-2',
          msg.includes('fail') || msg.includes('error')
            ? 'border-red-500/20 bg-red-500/10 text-red-400'
            : 'border-emerald-500/20 bg-emerald-500/10 text-emerald-400'
        )}>
          {msg.includes('fail') || msg.includes('error')
            ? <AlertTriangle className="h-3.5 w-3.5" />
            : <Network className="h-3.5 w-3.5" />}
          {msg}
        </div>
      )}

      {/* ─── 3. System Metadata ─── */}
      {editing ? (
        <div className="mb-6 rounded-xl border border-blue-500/20 bg-astra-surface p-5 space-y-4">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Edit System</h3>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-[10px] font-semibold text-slate-500 mb-1 block">Name *</label>
              <input value={editFields.name || ''}
                onChange={e => setEditFields({ ...editFields, name: e.target.value })}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <div>
              <label className="text-[10px] font-semibold text-slate-500 mb-1 block">Abbreviation</label>
              <input value={editFields.abbreviation || ''}
                onChange={e => setEditFields({ ...editFields, abbreviation: e.target.value })}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="text-[10px] font-semibold text-slate-500 mb-1 block">Type</label>
              <select value={editFields.system_type || 'subsystem'}
                onChange={e => setEditFields({ ...editFields, system_type: e.target.value })}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50">
                {SYSTEM_TYPES.map(t => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
              </select>
            </div>
            <div>
              <label className="text-[10px] font-semibold text-slate-500 mb-1 block">Status</label>
              <select value={editFields.status || 'concept'}
                onChange={e => setEditFields({ ...editFields, status: e.target.value })}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50">
                {SYSTEM_STATUSES.map(s => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
              </select>
            </div>
            <div>
              <label className="text-[10px] font-semibold text-slate-500 mb-1 block">WBS Number</label>
              <input value={editFields.wbs_number || ''}
                onChange={e => setEditFields({ ...editFields, wbs_number: e.target.value })}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
          </div>

          <div>
            <label className="text-[10px] font-semibold text-slate-500 mb-1 block">Responsible Org</label>
            <input value={editFields.responsible_org || ''}
              onChange={e => setEditFields({ ...editFields, responsible_org: e.target.value })}
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
          </div>

          <div>
            <label className="text-[10px] font-semibold text-slate-500 mb-1 block">Description</label>
            <textarea value={editFields.description || ''} rows={3}
              onChange={e => setEditFields({ ...editFields, description: e.target.value })}
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50 resize-none" />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button onClick={() => { setEditing(false); setEditFields({}); }}
              className="rounded-lg border border-astra-border px-4 py-2 text-xs text-slate-400 hover:text-slate-200">
              <X className="inline h-3 w-3 mr-1" />Cancel
            </button>
            <button onClick={saveEdit} disabled={savingEdit || !(editFields.name || '').trim()}
              className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-40">
              {savingEdit
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <Save className="h-3.5 w-3.5" />}
              Save Changes
            </button>
          </div>
        </div>
      ) : (
        <div className="mb-6 rounded-xl border border-astra-border bg-astra-surface p-5">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
            System Details
          </h3>
          <div className="grid grid-cols-2 gap-x-8">
            <div>
              <MetaRow label="Description" value={system.description} />
              <MetaRow label="WBS Number" value={system.wbs_number} />
              <MetaRow label="Responsible Org" value={system.responsible_org} />
              <MetaRow label="Parent System" value={system.parent_system_id ? `ID: ${system.parent_system_id}` : null} />
            </div>
            <div>
              <MetaRow label="System ID" value={system.system_id} />
              <MetaRow label="Type" value={system.system_type.replace(/_/g, ' ')} />
              <MetaRow label="Status" value={system.status.replace(/_/g, ' ')} />
              <MetaRow label="Units" value={system.unit_count} />
              <MetaRow label="Interfaces" value={system.interface_count} />
            </div>
          </div>
        </div>
      )}

      {/* ─── 4. Units Section ─── */}
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-bold text-slate-300 flex items-center gap-2">
          <Box className="h-4 w-4 text-blue-400" />
          Units ({system.units.length})
        </h2>
        <button onClick={() => setShowAddUnit(true)}
          className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-500">
          <Plus className="h-3.5 w-3.5" /> Add Unit
        </button>
      </div>

      {/* Search (only if units exist) */}
      {system.units.length > 0 && (
        <div className="mb-4">
          <div className="relative max-w-md">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
            <input value={unitSearch} onChange={e => setUnitSearch(e.target.value)}
              placeholder="Search units by name, designation, part number, manufacturer..."
              className="w-full rounded-lg border border-astra-border bg-astra-surface pl-9 pr-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
          </div>
        </div>
      )}

      {/* ─── 5. Unit Cards / Empty State ─── */}
      {system.units.length === 0 ? (
        <div className="py-16 text-center rounded-xl border border-astra-border bg-astra-surface">
          <Box className="mx-auto h-10 w-10 text-slate-600 mb-3" />
          <p className="text-sm text-slate-400 mb-1">No units in this system yet.</p>
          <p className="text-[11px] text-slate-500">
            Add a unit to get started.
          </p>
        </div>
      ) : filteredUnits.length === 0 ? (
        <div className="py-12 text-center rounded-xl border border-astra-border bg-astra-surface">
          <Search className="mx-auto h-8 w-8 text-slate-600 mb-2" />
          <p className="text-sm text-slate-400">No units match your search.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {filteredUnits.map(u => (
            <div key={u.id}
              className="group relative rounded-xl border border-astra-border bg-astra-surface p-4 hover:border-blue-500/30 transition cursor-pointer"
              onClick={() => router.push(`${p}/system-architecture/unit/${u.id}`)}>

              {/* Delete button — top right, hover-visible */}
              <button
                onClick={e => { e.stopPropagation(); setDeleteUnitTarget(u); }}
                className="absolute top-3 right-3 rounded-lg p-1.5 text-slate-600 opacity-0 group-hover:opacity-100 hover:text-red-400 hover:bg-red-500/10 transition"
                title="Delete unit">
                <Trash2 className="h-3.5 w-3.5" />
              </button>

              {/* Designation + Status */}
              <div className="flex items-center gap-2 mb-2">
                <UnitIcon type={u.unit_type} />
                <span className="font-mono text-xs font-bold text-blue-400">{u.designation}</span>
                <StatusBadge status={u.status} />
              </div>

              {/* Name */}
              <h3 className="text-[13px] font-semibold text-slate-200 mb-0.5 pr-8 truncate group-hover:text-blue-300 transition">
                {u.name}
              </h3>

              {/* Manufacturer + Part Number */}
              <p className="text-[11px] text-slate-500 mb-2 truncate">
                {u.manufacturer} · {u.part_number}
              </p>

              {/* TDD-SYSARCH-002 §6.1: catalog linkage chip when this
                  unit is linked to a CatalogPart. Backend Phase 2
                  populates u.catalog_part_summary on UnitSummary. */}
              {u.catalog_part_summary && (
                <div className="mb-3 inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
                  <Link2 className="h-3 w-3" aria-hidden="true" />
                  <span className="font-mono">{u.catalog_part_summary.part_number}</span>
                </div>
              )}

              {/* Stats row */}
              <div className="flex gap-5 pt-2.5 border-t border-astra-border">
                <div className="text-center">
                  <div className="text-base font-bold text-slate-300">{u.connector_count}</div>
                  <div className="text-[9px] text-slate-500">Connectors</div>
                </div>
                <div className="text-center">
                  <div className="text-base font-bold text-slate-300">{u.bus_count}</div>
                  <div className="text-[9px] text-slate-500">Buses</div>
                </div>
                <div className="flex-1 flex items-center justify-end">
                  <ChevronRight className="h-4 w-4 text-slate-600 group-hover:text-blue-400 transition" />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ════════════════════════════════════════════════════════════ */}
      {/*  Phase 3a: System-scoped Connections + Harnesses             */}
      {/* ════════════════════════════════════════════════════════════ */}
      <SystemConnectionsSection
        projectId={projectId}
        systemId={systemId}
        systemUnitIds={new Set((system?.units || []).map(u => u.id))}
        connections={connections}
        harnesses={harnesses}
      />

      {/* ─── Modals ─── */}
      {showAddUnit && (
        <AddUnitModal
          projectId={projectId} systemId={systemId}
          onClose={() => setShowAddUnit(false)}
          onCreated={fetchSystem}
        />
      )}
      {deleteUnitTarget && (
        <DeleteUnitDialog
          unit={deleteUnitTarget}
          onClose={() => setDeleteUnitTarget(null)}
          onConfirm={handleDeleteUnit}
        />
      )}
      {showDeleteSystem && (
        <DeleteSystemDialog
          system={system}
          onClose={() => setShowDeleteSystem(false)}
          onConfirm={handleDeleteSystem}
        />
      )}
    </div>
  );
}
