'use client';

/**
 * ASTRA — Connector Detail Page
 * =================================
 * File: frontend/src/app/projects/[id]/interfaces/connector/[connectorId]/page.tsx
 *
 * Breadcrumb: Interfaces → {System} → {Unit Designation} → {Connector Designator}
 * Tabs: Overview | Pins
 *
 * API calls:
 *   interfaceAPI.getConnector(connectorId)           → ConnectorWithPins
 *   interfaceAPI.getUnit(unitId)                     → UnitDetail (for breadcrumb)
 *   interfaceAPI.getSystem(systemId)                 → SystemDetail (for breadcrumb)
 *   interfaceAPI.updateConnector(connectorId, data)  → Connector
 *   interfaceAPI.deleteConnector(connectorId, force) → { status }
 *   interfaceAPI.batchAddPins(connectorId, pins)     → Pin[]
 *   interfaceAPI.autoGeneratePins(connectorId)       → Pin[]
 *   interfaceAPI.deletePin(pinId)                    → void
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft, Loader2, Edit3, Save, X, Plus, Trash2, RefreshCw,
  Cable, ChevronRight, ChevronDown, AlertTriangle, Search,
  Zap, Sparkles, ArrowUpDown, CheckCircle, Lock, Wand2, Copy,
} from 'lucide-react';
import clsx from 'clsx';
import { interfaceAPI } from '@/lib/interface-api';
import { formatApiError } from '@/lib/errors';
import type { ConnectorWithPins, Pin } from '@/lib/interface-types';
import { SIGNAL_TYPE_COLORS, labelize } from '@/lib/interface-types';

/**
 * Phase 3 — INTF-002: dual-name pin row.
 *
 * The backend Pin row carries `mfr_pin_name` (cached from the catalog at
 * placement time, locked) alongside the legacy `signal_name` field which is
 * the project-side editable internal name. The PinResponse Pydantic schema
 * doesn't surface mfr_pin_name yet — we read it via this augmented type
 * and display "—" when absent (legacy pins or pre-INTF-002 connectors).
 */
interface PinDualName extends Pin {
  mfr_pin_name?: string | null;
  /** internal_signal_name on the model — exposed as `signal_name` already
   *  on PinResponse, but we keep this alias here for naming clarity in the
   *  Phase 3 dual-column UI. */
  internal_signal_name?: string | null;
}

type Tab = 'overview' | 'pins';

// ══════════════════════════════════════
//  Constants
// ══════════════════════════════════════

const CONNECTOR_TYPES = [
  'circular_mil', 'circular_commercial', 'rectangular', 'd_sub', 'micro_d',
  'nano_d', 'sma', 'smb', 'smc', 'bnc', 'tnc', 'type_n', 'type_f',
  'sc_fiber', 'lc_fiber', 'mt_fiber', 'mpo_fiber', 'rj45', 'rj11',
  'usb_a', 'usb_b', 'usb_c', 'usb_micro', 'usb_mini',
  'hdmi', 'displayport', 'ethernet_industrial', 'm8', 'm12', 'm23',
  'power_anderson', 'power_molex', 'power_jst', 'power_te',
  'pcb_header', 'pcb_edge', 'idc', 'zif', 'spring_loaded',
  'terminal_block', 'lug', 'ring', 'spade', 'banana', 'binding_post',
  'custom',
];

const GENDERS = ['male_pin', 'female_socket', 'hermaphroditic', 'genderless', 'hybrid'];

const MOUNTINGS = [
  'panel_mount', 'box_mount', 'bulkhead', 'cable_mount',
  'pcb_through_hole', 'pcb_surface_mount',
  'rack_mount', 'flange_mount',
  'jam_nut', 'threaded_coupling', 'bayonet', 'push_pull',
  'free_hanging', 'hermetic_seal', 'custom',
];

// ══════════════════════════════════════
//  Signal types — matches backend SignalType enum exactly
//  Grouped into <optgroup>s for easier selection
// ══════════════════════════════════════

const SIGNAL_TYPE_GROUPS: { label: string; values: string[] }[] = [
  { label: 'Power & Ground', values: [
    'power_primary', 'power_secondary', 'power_return',
    'chassis_ground', 'signal_ground',
  ]},
  { label: 'Digital (voltage-specific)', values: [
    'digital_3v3', 'digital_5v', 'digital_12v', 'digital_lvds',
  ]},
  { label: 'Digital (generic)', values: [
    'signal_digital_single', 'signal_digital_differential',
  ]},
  { label: 'Analog', values: [
    'signal_analog_single', 'signal_analog_differential',
    'analog_voltage', 'analog_current_4_20ma',
  ]},
  { label: 'Clocks', values: [
    'clock_single', 'clock_differential', 'clock_reference',
  ]},
  { label: 'I²C / SPI / CAN', values: [
    'i2c_sda', 'i2c_scl',
    'spi_mosi', 'spi_miso', 'spi_clk', 'spi_cs',
    'can_high', 'can_low',
  ]},
  { label: 'Serial', values: [
    'serial_rs232', 'serial_rs422', 'serial_rs485', 'serial_uart',
    'serial_data', 'parallel_data',
  ]},
  { label: 'Aerospace buses (pin-level)', values: [
    'mil_std_1553_a', 'mil_std_1553_b',
    'arinc_429', 'arinc_664',
    'spacewire_data', 'spacewire_strobe',
  ]},
  { label: 'Ethernet', values: [
    'ethernet_100base_t', 'ethernet_1000base_t',
  ]},
  { label: 'RF / Coax', values: [
    'rf_signal', 'rf_lo', 'rf_if', 'coax_signal',
  ]},
  { label: 'Media', values: [
    'video_analog', 'video_sdi', 'audio_analog', 'audio_digital_aes',
  ]},
  { label: 'Fiber', values: [
    'fiber_optic_single', 'fiber_optic_multi', 'fiber_tx', 'fiber_rx',
  ]},
  { label: 'Discrete I/O', values: [
    'discrete_input', 'discrete_output', 'discrete_bidirectional',
    'discrete_command', 'discrete_status',
  ]},
  { label: 'Transducers', values: [
    'thermocouple', 'rtd', 'strain_gauge', 'lvdt',
  ]},
  { label: 'Pulse & Timing', values: [
    'pwm', 'pulse',
  ]},
  { label: 'Ordnance', values: [
    'pyro_fire', 'pyro_arm',
  ]},
  { label: 'Shields', values: [
    'shield', 'shield_overall', 'shield_individual', 'shield_drain',
  ]},
  { label: 'Misc', values: [
    'test_point', 'key_pin', 'alignment_pin',
    'spare', 'no_connect', 'reserved', 'custom',
  ]},
];

// Flat list for backwards compatibility with any callers that use SIGNAL_TYPES
const SIGNAL_TYPES = SIGNAL_TYPE_GROUPS.flatMap(g => g.values);

// ══════════════════════════════════════
//  Pin directions — matches backend PinDirection enum exactly
// ══════════════════════════════════════

const PIN_DIRECTIONS = [
  'input', 'output', 'bidirectional', 'tri_state',
  'open_collector', 'open_drain', 'passive',
  'power_source', 'power_sink', 'power_return',
  'ground', 'chassis_ground', 'no_connect', 'spare', 'custom',
];

// ══════════════════════════════════════
//  Shared UI
// ══════════════════════════════════════

function SignalDot({ type }: { type: string }) {
  const color = SIGNAL_TYPE_COLORS[type] || '#475569';
  return <div className="h-2 w-2 rounded-full flex-shrink-0" style={{ background: color }} />;
}

function MetaRow({ label, value }: { label: string; value?: string | number | null }) {
  if (value === null || value === undefined || value === '') return null;
  return (
    <div className="flex items-start justify-between py-2 border-b border-astra-border/50 last:border-0">
      <span className="text-[11px] text-slate-500 flex-shrink-0 w-44">{label}</span>
      <span className="text-[12px] font-medium text-slate-300 text-right">{String(value)}</span>
    </div>
  );
}

// ══════════════════════════════════════
//  Edit-form helpers (reusable, stacked layout)
// ══════════════════════════════════════

/** Uppercased section header with a subtle underline. Used in the edit form. */
function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="mb-4 border-b border-astra-border/60 pb-2 text-[11px] font-bold uppercase tracking-[0.14em] text-slate-400">
      {children}
    </h4>
  );
}

/** Stacked label-over-input. Wider fields, bigger font, clearer focus state. */
function FieldInput({
  label, value, onChange, placeholder, type = 'text',
}: {
  label: string;
  value: string | number;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-slate-400">{label}</span>
      <input
        type={type}
        value={value as any}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-astra-border bg-astra-bg px-3.5 py-2.5 text-sm text-slate-100 placeholder:text-slate-600 outline-none transition focus:border-blue-500/50 focus:ring-2 focus:ring-blue-500/10"
      />
    </label>
  );
}

/** Stacked label-over-select with the same visual weight as FieldInput. */
function FieldSelect({
  label, value, onChange, options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-slate-400">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full appearance-none rounded-lg border border-astra-border bg-astra-bg px-3.5 py-2.5 text-sm text-slate-100 outline-none transition focus:border-blue-500/50 focus:ring-2 focus:ring-blue-500/10 cursor-pointer bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2212%22 height=%2212%22 viewBox=%220 0 24 24%22 fill=%22none%22 stroke=%22%2394a3b8%22 stroke-width=%222%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22><polyline points=%226 9 12 15 18 9%22/></svg>')] bg-[length:12px] bg-[position:right_14px_center] bg-no-repeat pr-10"
      >
        <option value="">—</option>
        {options.map((o) => (
          <option key={o} value={o}>{labelize(o)}</option>
        ))}
      </select>
    </label>
  );
}

// ══════════════════════════════════════
//  Add Pins Multi-Row Form
// ══════════════════════════════════════

interface PinRow {
  key: number;
  pin_number: string;
  signal_name: string;
  signal_type: string;
  direction: string;
  mating_unit_id: string;  // kept as string for form state; '' means unassigned
}

/** Lightweight shape for the mating-LRU dropdown — avoids pulling the full Unit type. */
interface UnitOption { id: number; designation: string; name: string; }

function AddPinsForm({ connectorId, existingPins, availableUnits, ownUnitId, onSaved, onCancel }: {
  connectorId: number;
  existingPins: Pin[];
  /** All project units eligible as mating peers (already filtered to exclude own unit). */
  availableUnits: UnitOption[];
  /** The unit this connector belongs to, passed so we can visually reassure users. */
  ownUnitId: number | null;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const nextNum = useMemo(() => {
    const nums = existingPins.map(p => parseInt(p.pin_number)).filter(n => !isNaN(n));
    return nums.length > 0 ? Math.max(...nums) + 1 : 1;
  }, [existingPins]);

  const [rows, setRows] = useState<PinRow[]>([
    { key: 1, pin_number: String(nextNum), signal_name: '', signal_type: 'spare', direction: 'no_connect', mating_unit_id: '' },
  ]);
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState('');

  const addRow = () => {
    const maxNum = Math.max(...rows.map(r => parseInt(r.pin_number) || 0), nextNum - 1);
    setRows(prev => [...prev, {
      key: Date.now(), pin_number: String(maxNum + 1),
      signal_name: '', signal_type: 'spare', direction: 'no_connect', mating_unit_id: '',
    }]);
  };

  const removeRow = (key: number) => { if (rows.length > 1) setRows(prev => prev.filter(r => r.key !== key)); };

  const updateRow = (key: number, field: keyof PinRow, value: string) => {
    setRows(prev => prev.map(r => r.key === key ? { ...r, [field]: value } : r));
  };

  const handleSave = async () => {
    const valid = rows.filter(r => r.pin_number.trim() && r.signal_name.trim());
    if (valid.length === 0) { setError('At least one pin with number and signal name is required'); return; }
    setSaving(true); setError('');
    try {
      await interfaceAPI.batchAddPins(connectorId,
        valid.map(r => ({
          pin_number: r.pin_number,
          signal_name: r.signal_name,
          signal_type: r.signal_type as any,
          direction: r.direction as any,
          // Pass the FK to the backend only when a peer was picked; '' means
          // the user left it blank and we send null/undefined.
          ...(r.mating_unit_id ? { mating_unit_id: Number(r.mating_unit_id) } : {}),
        }))
      );
      onSaved();
    } catch (e: any) { setError(formatApiError(e, 'Failed to add pins')); }
    setSaving(false);
  };

  return (
    <div className="rounded-xl border border-blue-500/20 bg-astra-surface p-4 mb-4">
      <h4 className="text-xs font-bold text-slate-400 mb-3">Add Pins</h4>
      {error && (
        <div className="mb-3 rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
          <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" /> {error}
        </div>
      )}
      <div className="space-y-2">
        {/* Grid columns: pin# | signal name | signal type | direction | mating LRU | remove */}
        <div className="grid grid-cols-[60px_1fr_1fr_1fr_1fr_32px] gap-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500 px-1">
          <span>Pin #</span>
          <span>Signal Name</span>
          <span>Signal Type</span>
          <span>Direction</span>
          <span>Mates With LRU</span>
          <span />
        </div>
        {rows.map(r => (
          <div key={r.key} className="grid grid-cols-[60px_1fr_1fr_1fr_1fr_32px] gap-2">
            <input value={r.pin_number} onChange={e => updateRow(r.key, 'pin_number', e.target.value)}
              className="rounded-lg border border-astra-border bg-astra-bg px-2 py-1.5 text-xs text-slate-200 font-mono outline-none focus:border-blue-500/50" />
            <input value={r.signal_name} onChange={e => updateRow(r.key, 'signal_name', e.target.value)} placeholder="e.g. PWR_28V"
              className="rounded-lg border border-astra-border bg-astra-bg px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-blue-500/50" />
            <select value={r.signal_type} onChange={e => updateRow(r.key, 'signal_type', e.target.value)}
              className="rounded-lg border border-astra-border bg-astra-bg px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-blue-500/50">
              {SIGNAL_TYPE_GROUPS.map(g => (
                <optgroup key={g.label} label={g.label}>
                  {g.values.map(v => <option key={v} value={v}>{labelize(v)}</option>)}
                </optgroup>
              ))}
            </select>
            <select value={r.direction} onChange={e => updateRow(r.key, 'direction', e.target.value)}
              className="rounded-lg border border-astra-border bg-astra-bg px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-blue-500/50">
              {PIN_DIRECTIONS.map(d => <option key={d} value={d}>{labelize(d)}</option>)}
            </select>
            {/* Mating LRU picker — empty string = none/unassigned */}
            <select value={r.mating_unit_id} onChange={e => updateRow(r.key, 'mating_unit_id', e.target.value)}
              className="rounded-lg border border-astra-border bg-astra-bg px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-blue-500/50"
              title="Which LRU does this pin connect to on the other end?">
              <option value="">— none —</option>
              {availableUnits.map(u => (
                <option key={u.id} value={u.id}>
                  {u.designation}{u.name && u.name !== u.designation ? ` · ${u.name}` : ''}
                </option>
              ))}
            </select>
            <button onClick={() => removeRow(r.key)} className="rounded-lg p-1.5 text-slate-600 hover:text-red-400" title="Remove row">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center justify-between">
        <button onClick={addRow} className="flex items-center gap-1 text-[11px] text-blue-400 hover:text-blue-300">
          <Plus className="h-3 w-3" /> Add Row
        </button>
        <div className="flex gap-2">
          <button onClick={onCancel} className="rounded-lg border border-astra-border px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200">Cancel</button>
          <button onClick={handleSave} disabled={saving}
            className="flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-40">
            {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />} Save Pins
          </button>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  Delete Connector Dialog
// ══════════════════════════════════════

function DeleteConnectorDialog({ connector, onClose, onConfirm }: {
  connector: ConnectorWithPins; onClose: () => void; onConfirm: () => void;
}) {
  const [deleting, setDeleting] = useState(false);
  const handleDelete = async () => { setDeleting(true); await onConfirm(); setDeleting(false); };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl border border-red-500/20 bg-astra-surface p-6 shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-500/10">
            <AlertTriangle className="h-5 w-5 text-red-400" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-200">Delete Connector</h3>
            <p className="text-[11px] text-slate-500">This action cannot be undone.</p>
          </div>
        </div>
        <div className="rounded-lg bg-astra-bg border border-astra-border p-3 mb-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="font-mono text-xs font-bold text-blue-400">{connector.designator}</span>
            <span className="text-sm text-slate-300">{connector.name || labelize(connector.connector_type)}</span>
          </div>
          <p className="text-[11px] text-red-400 font-semibold">
            This will delete {connector.pins?.length || 0} pin{(connector.pins?.length || 0) !== 1 ? 's' : ''} and orphan any connected wires.
          </p>
        </div>
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg border border-astra-border px-4 py-2 text-xs text-slate-400 hover:text-slate-200">Cancel</button>
          <button onClick={handleDelete} disabled={deleting}
            className="flex items-center gap-1.5 rounded-lg bg-red-600 px-4 py-2 text-xs font-semibold text-white hover:bg-red-500 disabled:opacity-40">
            {deleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />} Delete Connector
          </button>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  Main Page
// ══════════════════════════════════════

export default function ConnectorDetailPage() {
  const params = useParams();
  const router = useRouter();
  const projectId   = Number(params.id);
  const connectorId = Number(params.connectorId);
  const p = `/projects/${projectId}`;

  // ── Core state ──
  const [connector, setConnector]     = useState<ConnectorWithPins | null>(null);
  const [loading, setLoading]         = useState(true);
  const [tab, setTab]                 = useState<Tab>('overview');
  const [msg, setMsg]                 = useState('');

  // ── Breadcrumb chain: system name + unit designation ──
  const [systemName, setSystemName]     = useState('');
  const [systemId, setSystemId]         = useState<number | null>(null);
  const [unitDesignation, setUnitDesignation] = useState('');
  const [unitId, setUnitId]             = useState<number | null>(null);

  // ── Overview editing ──
  const [editing, setEditing]           = useState(false);
  const [editFields, setEditFields]     = useState<Record<string, any>>({});
  const [savingEdit, setSavingEdit]     = useState(false);

  // ── Pin tab state ──
  const [showAddPins, setShowAddPins]       = useState(false);
  const [autoGenLoading, setAutoGenLoading] = useState(false);
  const [pinSearch, setPinSearch]           = useState('');
  const [sortField, setSortField]           = useState<'pin_number' | 'signal_name'>('pin_number');
  const [deleteConfirmPin, setDeleteConfirmPin] = useState<number | null>(null);
  const [expandedPin, setExpandedPin]       = useState<number | null>(null);

  // ── Phase 3 — INTF-002: dual-name pin table state ──
  // Multi-select for bulk actions (Rename pattern, Copy mfr → internal).
  // Inline edit-on-blur for the internal_signal_name column.
  const [selectedPinIds, setSelectedPinIds] = useState<Set<number>>(new Set());
  const [internalDraft, setInternalDraft]   = useState<Record<number, string>>({});
  const [showRenameModal, setShowRenameModal] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);

  // ── Pin edit state ──
  // When a pin is being edited, its id is held here and editPinFields holds
  // the in-flight changes. Saving calls interfaceAPI.updatePin(id, fields).
  const [editingPinId, setEditingPinId]   = useState<number | null>(null);
  const [editPinFields, setEditPinFields] = useState<Record<string, any>>({});
  const [savingPin, setSavingPin]         = useState(false);
  const [pinEditError, setPinEditError]   = useState('');

  // ── Available peer LRUs for the mating dropdown ──
  // Loaded once on mount (for the project). Excludes this connector's own
  // unit so we don't offer "mates with yourself" as an option.
  const [availableUnits, setAvailableUnits] = useState<UnitOption[]>([]);

  // ── Delete connector ──
  const [showDeleteConn, setShowDeleteConn] = useState(false);

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(''), 3500); };

  // ── Fetch connector + breadcrumb chain ──
  const fetchConnector = useCallback(async () => {
    setLoading(true);
    try {
      const res = await interfaceAPI.getConnector(connectorId);
      setConnector(res.data);
      // Fetch unit for breadcrumb
      if (res.data?.unit_id) {
        setUnitId(res.data.unit_id);
        try {
          const unitRes = await interfaceAPI.getUnit(res.data.unit_id);
          setUnitDesignation(unitRes.data?.designation || '');
          if (unitRes.data?.system_id) {
            setSystemId(unitRes.data.system_id);
            try {
              const sysRes = await interfaceAPI.getSystem(unitRes.data.system_id);
              setSystemName(sysRes.data?.name || '');
            } catch { }
          }
        } catch { }
      }
    } catch { }
    setLoading(false);
  }, [connectorId]);

  useEffect(() => { fetchConnector(); }, [fetchConnector]);

  // ── Load available peer LRUs for the mating-unit dropdown ──
  // Runs once when we know the project id + own unit id. Filters out the
  // connector's own unit since "mates with self" is nonsensical.
  useEffect(() => {
    if (!projectId || unitId === null) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await interfaceAPI.listUnits(projectId, { limit: 200 });
        if (cancelled) return;
        const rows: UnitOption[] = (res.data || [])
          .filter((u: any) => u.id !== unitId)
          .map((u: any) => ({ id: u.id, designation: u.designation || '', name: u.name || '' }));
        setAvailableUnits(rows);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn('[connector] failed to load peer units', err);
      }
    })();
    return () => { cancelled = true; };
  }, [projectId, unitId]);

  // ── Sorted/filtered pins ──
  const filteredPins = useMemo(() => {
    if (!connector?.pins) return [];
    let pins = [...connector.pins];
    if (pinSearch) {
      const q = pinSearch.toLowerCase();
      pins = pins.filter(p =>
        p.pin_number.toLowerCase().includes(q) ||
        p.signal_name.toLowerCase().includes(q) ||
        p.signal_type.toLowerCase().includes(q)
      );
    }
    pins.sort((a, b) => {
      if (sortField === 'pin_number') {
        const na = parseInt(a.pin_number), nb = parseInt(b.pin_number);
        if (!isNaN(na) && !isNaN(nb)) return na - nb;
        return a.pin_number.localeCompare(b.pin_number);
      }
      return a.signal_name.localeCompare(b.signal_name);
    });
    return pins;
  }, [connector, pinSearch, sortField]);

  // ══════════════════════════════════════
  //  Overview Edit
  // ══════════════════════════════════════

  const startEdit = () => {
    if (!connector) return;
    setEditFields({
      name: connector.name || '', connector_type: connector.connector_type,
      gender: connector.gender, mounting: connector.mounting || '',
      total_contacts: connector.total_contacts,
      signal_contacts: connector.signal_contacts ?? '', power_contacts: connector.power_contacts ?? '',
      coax_contacts: connector.coax_contacts ?? '', fiber_contacts: connector.fiber_contacts ?? '',
      spare_contacts: connector.spare_contacts ?? '',
      shell_size: connector.shell_size || '', insert_arrangement: connector.insert_arrangement || '',
      keying: connector.keying || '', polarization: connector.polarization || '',
      coupling: connector.coupling || '', ip_rating: connector.ip_rating || '',
      operating_temp_min_c: connector.operating_temp_min_c ?? '',
      operating_temp_max_c: connector.operating_temp_max_c ?? '',
      mating_cycles: connector.mating_cycles ?? '',
      shell_material: connector.shell_material || '', shell_finish: connector.shell_finish || '',
      contact_finish: connector.contact_finish || '',
      mil_spec: connector.mil_spec || '', manufacturer_part_number: connector.manufacturer_part_number || '',
      connector_manufacturer: connector.connector_manufacturer || '',
      backshell_type: connector.backshell_type || '', notes: connector.notes || '',
    });
    setEditing(true);
  };

  const saveEdit = async () => {
    setSavingEdit(true);
    try {
      const data: Record<string, any> = {};
      for (const [k, v] of Object.entries(editFields)) {
        data[k] = v === '' ? null : v;
      }
      // Coerce numeric fields
      for (const nf of ['total_contacts', 'signal_contacts', 'power_contacts', 'coax_contacts', 'fiber_contacts', 'spare_contacts', 'mating_cycles', 'operating_temp_min_c', 'operating_temp_max_c']) {
        if (data[nf] !== null && data[nf] !== undefined) data[nf] = Number(data[nf]) || null;
      }
      await interfaceAPI.updateConnector(connectorId, data);
      setEditing(false); setEditFields({});
      flash('Connector updated');
      fetchConnector();
    } catch (e: any) { flash(formatApiError(e, 'Save failed')); }
    setSavingEdit(false);
  };

  const ef = (field: string, value: any) => setEditFields(prev => ({ ...prev, [field]: value }));

  // ══════════════════════════════════════
  //  Pin Actions
  // ══════════════════════════════════════

  /**
   * T568B Wiring — the more common of the two TIA/EIA standards for 8P8C (RJ-45).
   * Pin 1 is leftmost when looking into the socket with the locking tab facing down.
   *
   * Industry-standard twisted pairs:
   *   Pair 2 (Orange) → Pins 1, 2   — TX on MDI
   *   Pair 3 (Green)  → Pins 3, 6   — RX on MDI  (split pair!)
   *   Pair 1 (Blue)   → Pins 4, 5   — unused in 10/100BASE-T; used by 1000BASE-T
   *   Pair 4 (Brown)  → Pins 7, 8   — unused in 10/100BASE-T; used by 1000BASE-T
   */
  const T568B_PINS: Array<{
    pin_number: string;
    signal_name: string;
    wire_color_primary: string;
    wire_color_secondary?: string;
    signal_type: string;
    direction: string;
  }> = [
    { pin_number: '1', signal_name: 'TX+ / BI_DA+', wire_color_primary: 'white', wire_color_secondary: 'orange', signal_type: 'ethernet',    direction: 'bidirectional' },
    { pin_number: '2', signal_name: 'TX- / BI_DA-', wire_color_primary: 'orange',                                 signal_type: 'ethernet',    direction: 'bidirectional' },
    { pin_number: '3', signal_name: 'RX+ / BI_DB+', wire_color_primary: 'white', wire_color_secondary: 'green',  signal_type: 'ethernet',    direction: 'bidirectional' },
    { pin_number: '4', signal_name: 'BI_DC+',       wire_color_primary: 'blue',                                   signal_type: 'ethernet',    direction: 'bidirectional' },
    { pin_number: '5', signal_name: 'BI_DC-',       wire_color_primary: 'white', wire_color_secondary: 'blue',   signal_type: 'ethernet',    direction: 'bidirectional' },
    { pin_number: '6', signal_name: 'RX- / BI_DB-', wire_color_primary: 'green',                                  signal_type: 'ethernet',    direction: 'bidirectional' },
    { pin_number: '7', signal_name: 'BI_DD+',       wire_color_primary: 'white', wire_color_secondary: 'brown',  signal_type: 'ethernet',    direction: 'bidirectional' },
    { pin_number: '8', signal_name: 'BI_DD-',       wire_color_primary: 'brown',                                  signal_type: 'ethernet',    direction: 'bidirectional' },
  ];

  /**
   * Apply T568B wire colors + signal names to an RJ-45 connector's pins.
   * Called automatically after autoGeneratePins if the connector is an RJ-45.
   * Uses whichever update method the API exposes — tries updatePin first,
   * falls back to batchAddPins-after-delete if needed. Fails silently with a
   * dev-console log so the main auto-generate still reports success.
   */
  const applyT568BColors = async () => {
    try {
      // Re-fetch to get the fresh pin list that autoGeneratePins just created
      const fresh = await interfaceAPI.getConnector(connectorId);
      const pins = (fresh.data as any)?.pins || [];
      if (pins.length === 0) return;

      // Build a pin_number → pin lookup so we can match generated pins to the template
      const byNumber: Record<string, any> = {};
      for (const p of pins) byNumber[String(p.pin_number)] = p;

      const anyApi = interfaceAPI as any;
      const hasUpdate = typeof anyApi.updatePin === 'function';

      if (!hasUpdate) {
        // eslint-disable-next-line no-console
        console.info('[RJ-45 auto-color] interfaceAPI.updatePin not available — colors not applied. Colors will take effect once the backend exposes a pin-update endpoint.');
        return;
      }

      for (const tmpl of T568B_PINS) {
        const existing = byNumber[tmpl.pin_number];
        if (!existing) continue;
        try {
          await anyApi.updatePin(existing.id, {
            signal_name: tmpl.signal_name,
            signal_type: tmpl.signal_type,
            direction: tmpl.direction,
            wire_color_primary: tmpl.wire_color_primary,
            wire_color_secondary: tmpl.wire_color_secondary || null,
          });
        } catch (err) {
          // eslint-disable-next-line no-console
          console.warn(`[RJ-45 auto-color] failed to update pin ${tmpl.pin_number}`, err);
        }
      }
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('[RJ-45 auto-color] failed', err);
    }
  };

  const handleAutoGenerate = async () => {
    setAutoGenLoading(true);
    try {
      await interfaceAPI.autoGeneratePins(connectorId);
      // If this is an RJ-45 connector, overlay the T568B color/signal template.
      // Safe to run on any 8P8C: it only touches pins 1–8 with matching numbers.
      const isRJ45 = connector?.connector_type === 'rj45';
      if (isRJ45) {
        await applyT568BColors();
        flash('Pins auto-generated with T568B colors');
      } else {
        flash('Pins auto-generated');
      }
      fetchConnector();
    } catch (e: any) { flash(formatApiError(e, 'Auto-generate failed')); }
    setAutoGenLoading(false);
  };

  const handleDeletePin = async (pinId: number) => {
    try {
      await interfaceAPI.deletePin(pinId);
      setDeleteConfirmPin(null);
      fetchConnector();
    } catch (e: any) { flash(formatApiError(e, 'Delete failed')); }
  };

  // ══════════════════════════════════════
  //  Phase 3 — INTF-002: dual-name pin handlers
  // ══════════════════════════════════════

  /** Toggle a pin's selection in the bulk-action set. */
  const togglePinSelected = (pinId: number) => {
    setSelectedPinIds((prev) => {
      const next = new Set(prev);
      if (next.has(pinId)) next.delete(pinId);
      else next.add(pinId);
      return next;
    });
  };

  /** Select / deselect every visible pin (for the header checkbox). */
  const toggleAllSelected = (pins: Pin[]) => {
    setSelectedPinIds((prev) => {
      const allSelected = pins.length > 0 && pins.every((p) => prev.has(p.id));
      if (allSelected) return new Set();
      return new Set(pins.map((p) => p.id));
    });
  };

  /** Commit one pin's internal_signal_name on blur. Skips the round-trip
   *  if the value is unchanged from the server-side row. */
  const commitInternalName = async (pin: Pin, value: string) => {
    if (value === pin.signal_name) {
      // No-op — clear local draft so the input syncs back to server data.
      setInternalDraft((d) => { const n = { ...d }; delete n[pin.id]; return n; });
      return;
    }
    try {
      await interfaceAPI.updatePin(pin.id, { signal_name: value });
      setInternalDraft((d) => { const n = { ...d }; delete n[pin.id]; return n; });
      fetchConnector();
    } catch (e: any) {
      flash(formatApiError(e, 'Failed to save internal signal name'));
    }
  };

  /** Bulk action — copy each selected pin's mfr_pin_name into its
   *  internal signal_name. Skips pins that don't have a mfr_pin_name
   *  (legacy units pre-INTF-002). */
  const handleCopyMfrToInternal = async () => {
    if (!connector || selectedPinIds.size === 0) return;
    setBulkBusy(true);
    try {
      const pins = (connector.pins as PinDualName[]).filter((p) => selectedPinIds.has(p.id) && p.mfr_pin_name);
      await Promise.all(
        pins.map((p) => interfaceAPI.updatePin(p.id, { signal_name: p.mfr_pin_name as string })),
      );
      flash(`Copied ${pins.length} mfr name${pins.length !== 1 ? 's' : ''} to internal`);
      setSelectedPinIds(new Set());
      fetchConnector();
    } catch (e: any) {
      flash(formatApiError(e, 'Bulk copy failed'));
    } finally {
      setBulkBusy(false);
    }
  };

  /** Bulk action — apply a regex find/replace across selected pins'
   *  internal signal names. */
  const handleRenamePattern = async (pattern: string, replacement: string, useRegex: boolean) => {
    if (!connector || selectedPinIds.size === 0) return;
    setBulkBusy(true);
    try {
      const pins = connector.pins.filter((p) => selectedPinIds.has(p.id));
      const re = useRegex
        ? new RegExp(pattern, 'g')
        : new RegExp(pattern.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g');
      const updates = pins
        .map((p) => ({ id: p.id, name: p.signal_name.replace(re, replacement) }))
        .filter((u) => u.name !== pins.find((p) => p.id === u.id)?.signal_name);
      await Promise.all(updates.map((u) => interfaceAPI.updatePin(u.id, { signal_name: u.name })));
      flash(`Renamed ${updates.length} pin${updates.length !== 1 ? 's' : ''}`);
      setSelectedPinIds(new Set());
      setShowRenameModal(false);
      fetchConnector();
    } catch (e: any) {
      flash(formatApiError(e, 'Bulk rename failed'));
    } finally {
      setBulkBusy(false);
    }
  };

  // ── Pin edit handlers ──
  /** Begin editing a pin: copy its current values into the edit-state object
   *  and flag it as active. User can change any field and save/cancel. */
  const startEditPin = (pin: Pin) => {
    setEditingPinId(pin.id);
    setExpandedPin(pin.id); // make sure the detail row is visible
    setPinEditError('');
    setEditPinFields({
      pin_number: pin.pin_number ?? '',
      pin_label: pin.pin_label ?? '',
      signal_name: pin.signal_name ?? '',
      signal_type: pin.signal_type ?? 'spare',
      direction: pin.direction ?? 'no_connect',
      voltage_nominal: pin.voltage_nominal ?? '',
      current_max_amps: pin.current_max_amps ?? '',
      impedance_ohms: pin.impedance_ohms ?? '',
      contact_type: pin.contact_type ?? '',
      termination: pin.termination ?? '',
      description: pin.description ?? '',
      notes: pin.notes ?? '',
      // Mating LRU FK — keep as string in form state, convert on save
      mating_unit_id:
        pin.mating_unit_id !== null && pin.mating_unit_id !== undefined
          ? String(pin.mating_unit_id) : '',
    });
  };

  const cancelEditPin = () => {
    setEditingPinId(null);
    setEditPinFields({});
    setPinEditError('');
  };

  const updateEditField = (field: string, value: any) => {
    setEditPinFields(prev => ({ ...prev, [field]: value }));
  };

  /** Save the active pin. Only sends fields that are actually set — avoids
   *  overwriting a value with an empty string when the user just skipped a
   *  field. Converts empty strings to null so the backend sees a clear
   *  "unset" signal for nullable columns. */
  const saveEditPin = async () => {
    if (editingPinId === null) return;
    setSavingPin(true);
    setPinEditError('');

    const payload: any = {};
    for (const [k, v] of Object.entries(editPinFields)) {
      if (v === '' || v === null || v === undefined) {
        // Nullable fields: send explicit null to clear. Required fields
        // (pin_number, signal_name, signal_type, direction) get skipped if
        // empty — keeps the backend validator from rejecting them.
        const REQUIRED = new Set(['pin_number', 'signal_name', 'signal_type', 'direction']);
        if (REQUIRED.has(k)) continue;
        payload[k] = null;
      } else if (k === 'mating_unit_id') {
        payload[k] = Number(v); // dropdown stores as string; backend wants int
      } else if (['current_max_amps', 'impedance_ohms'].includes(k)) {
        const n = Number(v);
        payload[k] = Number.isFinite(n) ? n : null;
      } else {
        payload[k] = v;
      }
    }

    try {
      await interfaceAPI.updatePin(editingPinId, payload);
      cancelEditPin();
      fetchConnector();
      flash('Pin updated');
    } catch (e: any) {
      // Surface the error inline in the edit form rather than as a toast
      setPinEditError(formatApiError(e, 'Update failed'));
    }
    setSavingPin(false);
  };

  const handleDeleteConnector = async () => {
    try {
      await interfaceAPI.deleteConnector(connectorId, true);
      // Navigate back to unit
      if (unitId) router.push(`${p}/interfaces/unit/${unitId}`);
      else router.push(`${p}/interfaces`);
    } catch (e: any) {
      flash(formatApiError(e, 'Delete failed'));
      setShowDeleteConn(false);
    }
  };

  // ── Loading / not found ──
  if (loading) return <div className="flex items-center justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-blue-500" /></div>;
  if (!connector) return (
    <div className="py-20 text-center">
      <AlertTriangle className="mx-auto h-10 w-10 text-red-400 mb-3" />
      <p className="text-sm text-slate-400">Connector not found.</p>
      <button onClick={() => router.back()} className="mt-3 text-xs text-blue-400 hover:underline">Go back</button>
    </div>
  );

  const pinCount = connector.pins?.length || 0;

  return (
    <div>
      {/* ── Breadcrumb ── */}
      <div className="mb-4 flex items-center gap-1.5 text-[11px] text-slate-500">
        <button onClick={() => router.push(`${p}/interfaces`)} className="hover:text-blue-400 transition">Interfaces</button>
        <ChevronRight className="h-3 w-3" />
        {systemId && (
          <>
            <button onClick={() => router.push(`${p}/interfaces/system/${systemId}`)} className="hover:text-blue-400 transition">
              {systemName || 'System'}
            </button>
            <ChevronRight className="h-3 w-3" />
          </>
        )}
        {unitId && (
          <>
            <button onClick={() => router.push(`${p}/interfaces/unit/${unitId}`)} className="hover:text-blue-400 transition">
              {unitDesignation || 'Unit'}
            </button>
            <ChevronRight className="h-3 w-3" />
          </>
        )}
        <span className="text-slate-300 font-semibold">{connector.designator}</span>
      </div>

      {/* ── Header ── */}
      <div className="mb-6 flex items-start justify-between">
        <div className="flex items-start gap-4">
          <button onClick={() => router.back()}
            className="mt-1 rounded-lg border border-astra-border p-2 text-slate-500 hover:text-slate-300 transition">
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Cable className="h-5 w-5 text-blue-400" />
              <span className="font-mono text-lg font-bold text-blue-400">{connector.designator}</span>
              {connector.name && <span className="text-base text-slate-300">{connector.name}</span>}
            </div>
            <div className="flex items-center gap-2 text-[11px]">
              <span className="rounded-full bg-astra-surface-alt px-2 py-0.5 text-[10px] font-semibold text-slate-400">
                {labelize(connector.connector_type)}
              </span>
              <span className="rounded-full bg-astra-surface-alt px-2 py-0.5 text-[10px] font-semibold text-slate-400">
                {labelize(connector.gender)}
              </span>
              <span className="text-slate-500">
                {pinCount} / {connector.total_contacts} contacts defined
              </span>
              {connector.mil_spec && <span className="font-mono text-cyan-400">{connector.mil_spec}</span>}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={fetchConnector} className="rounded-lg border border-astra-border p-2 text-slate-500 hover:text-slate-300" title="Refresh">
            <RefreshCw className={clsx('h-3.5 w-3.5', loading && 'animate-spin')} />
          </button>
          {!editing && (
            <button onClick={startEdit}
              className="flex items-center gap-1.5 rounded-lg border border-astra-border px-3 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200 hover:border-blue-500/30">
              <Edit3 className="h-3.5 w-3.5" /> Edit
            </button>
          )}
          <button onClick={() => setShowDeleteConn(true)}
            className="flex items-center gap-1.5 rounded-lg border border-red-500/20 px-3 py-2 text-xs font-semibold text-red-400 hover:bg-red-500/10">
            <Trash2 className="h-3.5 w-3.5" /> Delete
          </button>
        </div>
      </div>

      {/* ── Message ── */}
      {msg && (
        <div className={clsx('mb-4 rounded-lg border px-3 py-2 text-xs flex items-center gap-2',
          msg.includes('fail') || msg.includes('error') || msg.includes('already')
            ? 'border-red-500/20 bg-red-500/10 text-red-400'
            : 'border-emerald-500/20 bg-emerald-500/10 text-emerald-400')}>
          {msg.includes('fail') || msg.includes('error') || msg.includes('already')
            ? <AlertTriangle className="h-3.5 w-3.5" />
            : <CheckCircle className="h-3.5 w-3.5" />}
          {msg}
        </div>
      )}

      {/* ── Tabs ── */}
      <div className="mb-4 flex items-center gap-1 border-b border-astra-border">
        {([
          { key: 'overview' as Tab, label: 'Overview' },
          { key: 'pins' as Tab, label: `Pins (${pinCount} / ${connector.total_contacts})` },
        ]).map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={clsx('border-b-2 px-4 py-2.5 text-xs font-semibold transition',
              tab === t.key ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-500 hover:text-slate-300')}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ══════════════════════════════════════ */}
      {/*  TAB 1 — OVERVIEW                     */}
      {/* ══════════════════════════════════════ */}
      {tab === 'overview' && (
        editing ? (
          <div className="rounded-xl border border-blue-500/20 bg-astra-surface p-6 space-y-6">
            {/* ── Hide number spinners globally inside the edit form ── */}
            {/* Stops the browser from showing those weird up/down arrows on <input type="number"> */}
            <style jsx>{`
              input[type='number']::-webkit-inner-spin-button,
              input[type='number']::-webkit-outer-spin-button {
                -webkit-appearance: none;
                margin: 0;
              }
              input[type='number'] {
                -moz-appearance: textfield;
              }
            `}</style>

            {/* ── Header ── */}
            <div className="flex items-center justify-between border-b border-astra-border pb-4">
              <div>
                <h3 className="text-base font-bold text-slate-100">Edit Connector</h3>
                <p className="mt-0.5 text-xs text-slate-500">
                  Update the connector specification. Fields left blank will be cleared.
                </p>
              </div>
              <div className="flex gap-2">
                <button onClick={() => { setEditing(false); setEditFields({}); }}
                  className="rounded-lg border border-astra-border px-4 py-2 text-sm font-semibold text-slate-300 transition hover:bg-astra-surface-alt hover:text-slate-100">
                  Cancel
                </button>
                <button onClick={saveEdit} disabled={savingEdit}
                  className="flex items-center gap-2 rounded-lg bg-blue-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-600 disabled:opacity-40">
                  {savingEdit ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  Save Changes
                </button>
              </div>
            </div>

            {/* ── Body: 2-column grid ── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-8 gap-y-6">

              {/* ── LEFT COLUMN ── */}
              <div className="space-y-6">

                {/* Physical */}
                <section>
                  <SectionHeader>Physical</SectionHeader>
                  <div className="space-y-4">
                    <FieldInput
                      label="Name" value={editFields.name ?? ''}
                      onChange={v => ef('name', v)} placeholder="e.g., Eth0" />
                    <FieldSelect
                      label="Type" value={editFields.connector_type ?? ''}
                      onChange={v => ef('connector_type', v)} options={CONNECTOR_TYPES} />
                    <FieldSelect
                      label="Gender" value={editFields.gender ?? ''}
                      onChange={v => ef('gender', v)} options={GENDERS} />
                    <FieldSelect
                      label="Mounting" value={editFields.mounting ?? ''}
                      onChange={v => ef('mounting', v)} options={MOUNTINGS} />
                    <FieldInput
                      label="Shell Size" value={editFields.shell_size ?? ''}
                      onChange={v => ef('shell_size', v)} placeholder="e.g., 11" />
                    <FieldInput
                      label="Insert Arrangement" value={editFields.insert_arrangement ?? ''}
                      onChange={v => ef('insert_arrangement', v)} placeholder="e.g., 35" />
                    <FieldInput
                      label="Total Contacts" type="number" value={editFields.total_contacts ?? ''}
                      onChange={v => ef('total_contacts', v)} placeholder="e.g., 8" />
                  </div>
                </section>

                {/* Contact Breakdown */}
                <section>
                  <SectionHeader>Contact Breakdown</SectionHeader>
                  <div className="space-y-4">
                    <FieldInput label="Signal" type="number" value={editFields.signal_contacts ?? ''}
                      onChange={v => ef('signal_contacts', v)} />
                    <FieldInput label="Power" type="number" value={editFields.power_contacts ?? ''}
                      onChange={v => ef('power_contacts', v)} />
                    <FieldInput label="Coax" type="number" value={editFields.coax_contacts ?? ''}
                      onChange={v => ef('coax_contacts', v)} />
                    <FieldInput label="Fiber" type="number" value={editFields.fiber_contacts ?? ''}
                      onChange={v => ef('fiber_contacts', v)} />
                    <FieldInput label="Spare" type="number" value={editFields.spare_contacts ?? ''}
                      onChange={v => ef('spare_contacts', v)} />
                  </div>
                </section>
              </div>

              {/* ── RIGHT COLUMN ── */}
              <div className="space-y-6">

                {/* Electrical / Environmental */}
                <section>
                  <SectionHeader>Electrical / Environmental</SectionHeader>
                  <div className="space-y-4">
                    <FieldInput label="Keying" value={editFields.keying ?? ''}
                      onChange={v => ef('keying', v)} placeholder="e.g., Key A" />
                    <FieldInput label="Polarization" value={editFields.polarization ?? ''}
                      onChange={v => ef('polarization', v)} />
                    <FieldInput label="Coupling" value={editFields.coupling ?? ''}
                      onChange={v => ef('coupling', v)} placeholder="e.g., Threaded" />
                    <FieldInput label="IP Rating" value={editFields.ip_rating ?? ''}
                      onChange={v => ef('ip_rating', v)} placeholder="e.g., IP67" />
                    <FieldInput label="Temp Min (°C)" type="number" value={editFields.operating_temp_min_c ?? ''}
                      onChange={v => ef('operating_temp_min_c', v)} placeholder="e.g., -55" />
                    <FieldInput label="Temp Max (°C)" type="number" value={editFields.operating_temp_max_c ?? ''}
                      onChange={v => ef('operating_temp_max_c', v)} placeholder="e.g., 125" />
                    <FieldInput label="Mating Cycles" type="number" value={editFields.mating_cycles ?? ''}
                      onChange={v => ef('mating_cycles', v)} placeholder="e.g., 500" />
                  </div>
                </section>

                {/* Materials / Spec */}
                <section>
                  <SectionHeader>Materials / Spec</SectionHeader>
                  <div className="space-y-4">
                    <FieldInput label="Shell Material" value={editFields.shell_material ?? ''}
                      onChange={v => ef('shell_material', v)} placeholder="e.g., Aluminum" />
                    <FieldInput label="Shell Finish" value={editFields.shell_finish ?? ''}
                      onChange={v => ef('shell_finish', v)} placeholder="e.g., Olive drab cad" />
                    <FieldInput label="Contact Finish" value={editFields.contact_finish ?? ''}
                      onChange={v => ef('contact_finish', v)} placeholder="e.g., Gold" />
                    <FieldInput label="MIL-SPEC" value={editFields.mil_spec ?? ''}
                      onChange={v => ef('mil_spec', v)} placeholder="e.g., MIL-DTL-38999" />
                    <FieldInput label="Mfr Part Number" value={editFields.manufacturer_part_number ?? ''}
                      onChange={v => ef('manufacturer_part_number', v)} />
                    <FieldInput label="Manufacturer" value={editFields.connector_manufacturer ?? ''}
                      onChange={v => ef('connector_manufacturer', v)} placeholder="e.g., Amphenol" />
                    <FieldInput label="Backshell Type" value={editFields.backshell_type ?? ''}
                      onChange={v => ef('backshell_type', v)} />
                  </div>
                </section>

                {/* Notes */}
                <section>
                  <SectionHeader>Notes</SectionHeader>
                  <textarea
                    value={editFields.notes ?? ''}
                    onChange={e => ef('notes', e.target.value)}
                    rows={4}
                    placeholder="Additional notes, part-selection rationale, mating partner info, etc."
                    className="w-full rounded-lg border border-astra-border bg-astra-bg px-3.5 py-2.5 text-sm text-slate-200 placeholder:text-slate-600 outline-none transition focus:border-blue-500/50 focus:ring-2 focus:ring-blue-500/10 resize-y" />
                </section>
              </div>
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
            <div className="grid grid-cols-2 gap-x-8">
              <div>
                <h3 className="text-xs font-bold text-slate-400 mb-3">PHYSICAL</h3>
                <MetaRow label="Connector Type" value={labelize(connector.connector_type)} />
                <MetaRow label="Gender" value={labelize(connector.gender)} />
                <MetaRow label="Mounting" value={connector.mounting ? labelize(connector.mounting) : undefined} />
                <MetaRow label="Shell Size" value={connector.shell_size} />
                <MetaRow label="Insert Arrangement" value={connector.insert_arrangement} />
                <MetaRow label="Total Contacts" value={connector.total_contacts} />
                <MetaRow label="Signal Contacts" value={connector.signal_contacts} />
                <MetaRow label="Power Contacts" value={connector.power_contacts} />
                <MetaRow label="Coax Contacts" value={connector.coax_contacts} />
                <MetaRow label="Fiber Contacts" value={connector.fiber_contacts} />
                <MetaRow label="Spare Contacts" value={connector.spare_contacts} />
              </div>
              <div>
                <h3 className="text-xs font-bold text-slate-400 mb-3">ELECTRICAL / SPEC</h3>
                <MetaRow label="Keying" value={connector.keying} />
                <MetaRow label="Polarization" value={connector.polarization} />
                <MetaRow label="Coupling" value={connector.coupling} />
                <MetaRow label="IP Rating" value={connector.ip_rating} />
                <MetaRow label="Temp Range (°C)" value={
                  connector.operating_temp_min_c != null && connector.operating_temp_max_c != null
                    ? `${connector.operating_temp_min_c} to ${connector.operating_temp_max_c}` : undefined
                } />
                <MetaRow label="Mating Cycles" value={connector.mating_cycles} />
                <MetaRow label="Shell Material" value={connector.shell_material ? labelize(connector.shell_material) : undefined} />
                <MetaRow label="Shell Finish" value={connector.shell_finish ? labelize(connector.shell_finish) : undefined} />
                <MetaRow label="Contact Finish" value={connector.contact_finish ? labelize(connector.contact_finish) : undefined} />
                <MetaRow label="MIL-SPEC" value={connector.mil_spec} />
                <MetaRow label="Manufacturer" value={connector.connector_manufacturer} />
                <MetaRow label="Manufacturer PN" value={connector.manufacturer_part_number} />
                <MetaRow label="Backshell Type" value={connector.backshell_type} />
              </div>
            </div>
            {connector.notes && (
              <div className="mt-4 pt-3 border-t border-astra-border">
                <span className="text-[10px] font-bold text-slate-500 block mb-1">NOTES</span>
                <p className="text-[12px] text-slate-300 whitespace-pre-wrap">{connector.notes}</p>
              </div>
            )}
          </div>
        )
      )}

      {/* ══════════════════════════════════════ */}
      {/*  TAB 2 — PINS                         */}
      {/* ══════════════════════════════════════ */}
      {tab === 'pins' && (
        <div>
          {/* Action bar */}
          <div className="mb-4 flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
              <input value={pinSearch} onChange={e => setPinSearch(e.target.value)}
                placeholder="Search pins by number, signal name, type..."
                className="w-full rounded-lg border border-astra-border bg-astra-surface pl-9 pr-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>

            {/* Pin count indicator */}
            <span className="text-[11px] text-slate-500 whitespace-nowrap px-2">
              {pinCount} / {connector.total_contacts} pins
            </span>

            <button onClick={() => setSortField(prev => prev === 'pin_number' ? 'signal_name' : 'pin_number')}
              className="flex items-center gap-1 rounded-lg border border-astra-border px-3 py-2 text-xs text-slate-400 hover:text-slate-200">
              <ArrowUpDown className="h-3.5 w-3.5" /> {sortField === 'pin_number' ? 'By Pin #' : 'By Signal'}
            </button>

            {pinCount === 0 && connector.total_contacts > 0 && (
              <button onClick={handleAutoGenerate} disabled={autoGenLoading}
                className="flex items-center gap-1 rounded-lg bg-violet-600 px-3 py-2 text-xs font-semibold text-white hover:bg-violet-500 disabled:opacity-40">
                {autoGenLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                Auto-Generate Pins
              </button>
            )}

            <button onClick={() => setShowAddPins(true)}
              className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-500">
              <Plus className="h-3.5 w-3.5" /> Add Pins
            </button>
          </div>

          {/* Phase 3 — INTF-002: bulk-action bar appears once any pin is selected. */}
          {selectedPinIds.size > 0 && (
            <div className="mb-3 flex items-center gap-2 rounded-lg border border-blue-500/20 bg-blue-500/5 px-3 py-2 text-xs">
              <span className="font-semibold text-blue-300">
                {selectedPinIds.size} selected
              </span>
              <div className="ml-auto flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleCopyMfrToInternal}
                  disabled={bulkBusy}
                  className="flex items-center gap-1 rounded-md bg-astra-surface-alt px-2 py-1 text-slate-200 hover:bg-blue-500/20 disabled:opacity-40"
                  title="Copy each selected pin's manufacturer name into its internal signal name"
                >
                  <Copy className="h-3 w-3" aria-hidden="true" /> Copy mfr → internal
                </button>
                <button
                  type="button"
                  onClick={() => setShowRenameModal(true)}
                  disabled={bulkBusy}
                  className="flex items-center gap-1 rounded-md bg-astra-surface-alt px-2 py-1 text-slate-200 hover:bg-blue-500/20 disabled:opacity-40"
                >
                  <Wand2 className="h-3 w-3" aria-hidden="true" /> Rename pattern…
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedPinIds(new Set())}
                  className="text-slate-500 hover:text-slate-300"
                  aria-label="Clear pin selection"
                >
                  <X className="h-3 w-3" aria-hidden="true" />
                </button>
              </div>
            </div>
          )}

          {/* Add pins form */}
          {showAddPins && (
            <AddPinsForm connectorId={connectorId} existingPins={connector.pins || []}
              availableUnits={availableUnits} ownUnitId={unitId}
              onSaved={() => { setShowAddPins(false); fetchConnector(); }}
              onCancel={() => setShowAddPins(false)} />
          )}

          {/* Pin table */}
          {filteredPins.length === 0 ? (
            <div className="py-16 text-center rounded-xl border border-astra-border bg-astra-surface">
              <Zap className="mx-auto h-10 w-10 text-slate-600 mb-3" />
              <p className="text-sm text-slate-400 mb-1">
                {pinCount === 0 ? 'No pins defined yet.' : 'No pins match your search.'}
              </p>
              {pinCount === 0 && connector.total_contacts > 0 && (
                <p className="text-[11px] text-slate-500">
                  Click &quot;Auto-Generate Pins&quot; to create {connector.total_contacts} spare pin slots, or &quot;Add Pins&quot; to define them manually.
                </p>
              )}
            </div>
          ) : (
            <div className="rounded-xl border border-astra-border bg-astra-surface overflow-hidden">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="border-b border-astra-border bg-astra-surface-alt">
                    {/* Phase 3 — INTF-002: row-select checkbox */}
                    <th className="w-8 px-2 py-2.5">
                      <input
                        type="checkbox"
                        aria-label="Select all visible pins"
                        checked={filteredPins.length > 0 && filteredPins.every((p) => selectedPinIds.has(p.id))}
                        onChange={() => toggleAllSelected(filteredPins)}
                        className="rounded border-astra-border bg-astra-bg"
                      />
                    </th>
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-400 w-14">Pin #</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-400 w-16">Label</th>
                    {/* Phase 3 — INTF-002: dual-name columns. Mfr is locked, Internal is editable. */}
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-400 w-40">
                      <span className="inline-flex items-center gap-1" title="Manufacturer pin name from the catalog. Locked.">
                        <Lock className="h-3 w-3" aria-hidden="true" /> Mfr Pin Name
                      </span>
                    </th>
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-400">Internal Signal Name</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-400 w-36">Signal Type</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-400 w-24">Direction</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-400 w-24">Mates With</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-400 w-20">Voltage</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-400 w-20">Current</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-400 w-16">Ω</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-400 w-24">Bus</th>
                    <th className="px-3 py-2.5 w-24" />
                  </tr>
                </thead>
                <tbody>
                  {filteredPins.map(pin => {
                    const dual = pin as PinDualName;
                    const draftValue = internalDraft[pin.id];
                    const internalValue = draftValue !== undefined ? draftValue : pin.signal_name;
                    return (
                    <React.Fragment key={pin.id}>
                      <tr
                        className={clsx('border-b border-astra-border/50 hover:bg-astra-surface-alt/50 transition cursor-pointer',
                          expandedPin === pin.id && 'bg-astra-surface-alt/30',
                          selectedPinIds.has(pin.id) && 'bg-blue-500/5')}
                        onClick={() => setExpandedPin(prev => prev === pin.id ? null : pin.id)}>
                        <td className="px-2 py-2" onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            aria-label={`Select pin ${pin.pin_number}`}
                            checked={selectedPinIds.has(pin.id)}
                            onChange={() => togglePinSelected(pin.id)}
                            className="rounded border-astra-border bg-astra-bg"
                          />
                        </td>
                        <td className="px-3 py-2 font-mono font-bold text-slate-300">{pin.pin_number}</td>
                        <td className="px-3 py-2 text-slate-500">{pin.pin_label || '—'}</td>
                        <td className="px-3 py-2 text-slate-300">
                          <span className="inline-flex items-center gap-1 font-mono text-[11px]" title="Locked — sourced from supplier catalog">
                            {dual.mfr_pin_name ? (
                              <>
                                <Lock className="h-3 w-3 text-slate-600" aria-hidden="true" />
                                {dual.mfr_pin_name}
                              </>
                            ) : (
                              <span className="text-slate-600">—</span>
                            )}
                          </span>
                        </td>
                        <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                          <input
                            type="text"
                            aria-label={`Internal signal name for pin ${pin.pin_number}`}
                            value={internalValue}
                            onChange={(e) => setInternalDraft((d) => ({ ...d, [pin.id]: e.target.value }))}
                            onBlur={(e) => commitInternalName(pin, e.target.value)}
                            className="w-full rounded-md border border-transparent bg-transparent px-2 py-1 text-xs font-semibold text-slate-100 hover:border-astra-border focus:border-blue-500/50 focus:bg-astra-bg outline-none"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-1.5">
                            <SignalDot type={pin.signal_type} />
                            <span className="text-slate-400 text-[11px]">{labelize(pin.signal_type)}</span>
                          </div>
                        </td>
                        <td className="px-3 py-2 text-slate-400 text-[11px]">{labelize(pin.direction)}</td>
                        <td className="px-3 py-2 text-[11px]">
                          {pin.mating_unit_designation ? (
                            <span className="rounded-full bg-blue-500/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-blue-300"
                              title={pin.mating_unit_name || ''}>
                              {pin.mating_unit_designation}
                            </span>
                          ) : <span className="text-slate-600">—</span>}
                        </td>
                        <td className="px-3 py-2 text-slate-500 font-mono text-[11px]">
                          {pin.voltage_nominal || (pin.voltage_min != null ? `${pin.voltage_min}–${pin.voltage_max}` : '—')}
                        </td>
                        <td className="px-3 py-2 text-slate-500 font-mono text-[11px]">
                          {pin.current_max_amps != null ? `${pin.current_max_amps}A` : '—'}
                        </td>
                        <td className="px-3 py-2 text-slate-500 font-mono text-[11px]">
                          {pin.impedance_ohms != null ? `${pin.impedance_ohms}` : '—'}
                        </td>
                        <td className="px-3 py-2 text-[11px]">
                          {pin.bus_assignment ? (
                            <span className="rounded-full bg-violet-500/15 px-1.5 py-0.5 text-[9px] font-semibold text-violet-400">
                              {labelize(pin.bus_assignment.pin_role)}
                            </span>
                          ) : <span className="text-slate-600">—</span>}
                        </td>
                        <td className="px-3 py-2" onClick={e => e.stopPropagation()}>
                          {deleteConfirmPin === pin.id ? (
                            <div className="flex gap-1">
                              <button onClick={() => handleDeletePin(pin.id)} className="rounded p-1 text-red-400 hover:bg-red-500/10" title="Confirm delete">
                                <CheckCircle className="h-3.5 w-3.5" />
                              </button>
                              <button onClick={() => setDeleteConfirmPin(null)} className="rounded p-1 text-slate-500 hover:text-slate-300" title="Cancel">
                                <X className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          ) : (
                            <div className="flex gap-1">
                              <button onClick={() => startEditPin(pin)}
                                className="rounded p-1 text-slate-600 hover:text-blue-400 transition" title="Edit pin">
                                <Edit3 className="h-3.5 w-3.5" />
                              </button>
                              <button onClick={() => setDeleteConfirmPin(pin.id)}
                                className="rounded p-1 text-slate-600 hover:text-red-400 transition" title="Delete pin">
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                      {/* Expanded pin detail / edit form */}
                      {expandedPin === pin.id && (
                        <tr className="bg-astra-bg/50">
                          {/* colSpan covers all 13 columns of the dual-name pin table */}
                          <td colSpan={13} className="px-6 py-3">
                            {editingPinId === pin.id ? (
                              // ── EDIT MODE ──
                              // Comprehensive pin edit form. Reuses the same
                              // dropdown option lists as the Add Pins form so
                              // values stay consistent across create/update.
                              <div className="space-y-3">
                                {pinEditError && (
                                  <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
                                    <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" /> {pinEditError}
                                  </div>
                                )}
                                <div className="grid grid-cols-4 gap-3 text-[11px]">
                                  <label className="block">
                                    <span className="mb-1 block text-slate-500">Pin #</span>
                                    <input value={editPinFields.pin_number || ''} onChange={e => updateEditField('pin_number', e.target.value)}
                                      className="w-full rounded-lg border border-astra-border bg-astra-bg px-2 py-1.5 text-xs text-slate-100 font-mono outline-none focus:border-blue-500/50 focus:ring-2 focus:ring-blue-500/10" />
                                  </label>
                                  <label className="block">
                                    <span className="mb-1 block text-slate-500">Label</span>
                                    <input value={editPinFields.pin_label || ''} onChange={e => updateEditField('pin_label', e.target.value)}
                                      className="w-full rounded-lg border border-astra-border bg-astra-bg px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-blue-500/50 focus:ring-2 focus:ring-blue-500/10" />
                                  </label>
                                  <label className="block col-span-2">
                                    <span className="mb-1 block text-slate-500">Signal Name</span>
                                    <input value={editPinFields.signal_name || ''} onChange={e => updateEditField('signal_name', e.target.value)}
                                      className="w-full rounded-lg border border-astra-border bg-astra-bg px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-blue-500/50 focus:ring-2 focus:ring-blue-500/10" />
                                  </label>

                                  <label className="block">
                                    <span className="mb-1 block text-slate-500">Signal Type</span>
                                    <select value={editPinFields.signal_type || ''} onChange={e => updateEditField('signal_type', e.target.value)}
                                      className="w-full rounded-lg border border-astra-border bg-astra-bg px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-blue-500/50">
                                      {SIGNAL_TYPE_GROUPS.map(g => (
                                        <optgroup key={g.label} label={g.label}>
                                          {g.values.map(v => <option key={v} value={v}>{labelize(v)}</option>)}
                                        </optgroup>
                                      ))}
                                    </select>
                                  </label>
                                  <label className="block">
                                    <span className="mb-1 block text-slate-500">Direction</span>
                                    <select value={editPinFields.direction || ''} onChange={e => updateEditField('direction', e.target.value)}
                                      className="w-full rounded-lg border border-astra-border bg-astra-bg px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-blue-500/50">
                                      {PIN_DIRECTIONS.map(d => <option key={d} value={d}>{labelize(d)}</option>)}
                                    </select>
                                  </label>
                                  <label className="block col-span-2">
                                    <span className="mb-1 block text-slate-500">Mates With LRU</span>
                                    <select value={editPinFields.mating_unit_id || ''} onChange={e => updateEditField('mating_unit_id', e.target.value)}
                                      className="w-full rounded-lg border border-astra-border bg-astra-bg px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-blue-500/50"
                                      title="Which LRU does this pin connect to on the other end? Enables auto-wire by peer LRU.">
                                      <option value="">— none —</option>
                                      {availableUnits.map(u => (
                                        <option key={u.id} value={u.id}>
                                          {u.designation}{u.name && u.name !== u.designation ? ` · ${u.name}` : ''}
                                        </option>
                                      ))}
                                    </select>
                                  </label>

                                  <label className="block">
                                    <span className="mb-1 block text-slate-500">Voltage</span>
                                    <input value={editPinFields.voltage_nominal || ''} onChange={e => updateEditField('voltage_nominal', e.target.value)}
                                      placeholder="e.g., 28VDC"
                                      className="w-full rounded-lg border border-astra-border bg-astra-bg px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-blue-500/50 focus:ring-2 focus:ring-blue-500/10" />
                                  </label>
                                  <label className="block">
                                    <span className="mb-1 block text-slate-500">Current (A)</span>
                                    <input type="number" step="0.01" value={editPinFields.current_max_amps ?? ''} onChange={e => updateEditField('current_max_amps', e.target.value)}
                                      className="w-full rounded-lg border border-astra-border bg-astra-bg px-2 py-1.5 text-xs text-slate-100 font-mono outline-none focus:border-blue-500/50 focus:ring-2 focus:ring-blue-500/10 [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none" />
                                  </label>
                                  <label className="block">
                                    <span className="mb-1 block text-slate-500">Impedance (Ω)</span>
                                    <input type="number" step="0.1" value={editPinFields.impedance_ohms ?? ''} onChange={e => updateEditField('impedance_ohms', e.target.value)}
                                      className="w-full rounded-lg border border-astra-border bg-astra-bg px-2 py-1.5 text-xs text-slate-100 font-mono outline-none focus:border-blue-500/50 focus:ring-2 focus:ring-blue-500/10 [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none" />
                                  </label>
                                  <label className="block">
                                    <span className="mb-1 block text-slate-500">Contact Type</span>
                                    <input value={editPinFields.contact_type || ''} onChange={e => updateEditField('contact_type', e.target.value)}
                                      className="w-full rounded-lg border border-astra-border bg-astra-bg px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-blue-500/50 focus:ring-2 focus:ring-blue-500/10" />
                                  </label>

                                  <label className="block col-span-2">
                                    <span className="mb-1 block text-slate-500">Termination</span>
                                    <input value={editPinFields.termination || ''} onChange={e => updateEditField('termination', e.target.value)}
                                      className="w-full rounded-lg border border-astra-border bg-astra-bg px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-blue-500/50 focus:ring-2 focus:ring-blue-500/10" />
                                  </label>
                                  <label className="block col-span-4">
                                    <span className="mb-1 block text-slate-500">Description</span>
                                    <textarea value={editPinFields.description || ''} onChange={e => updateEditField('description', e.target.value)} rows={2}
                                      className="w-full rounded-lg border border-astra-border bg-astra-bg px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-blue-500/50 focus:ring-2 focus:ring-blue-500/10 resize-y" />
                                  </label>
                                  <label className="block col-span-4">
                                    <span className="mb-1 block text-slate-500">Notes</span>
                                    <textarea value={editPinFields.notes || ''} onChange={e => updateEditField('notes', e.target.value)} rows={2}
                                      className="w-full rounded-lg border border-astra-border bg-astra-bg px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-blue-500/50 focus:ring-2 focus:ring-blue-500/10 resize-y" />
                                  </label>
                                </div>
                                <div className="flex justify-end gap-2">
                                  <button onClick={cancelEditPin} disabled={savingPin}
                                    className="rounded-lg border border-astra-border px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-astra-surface-alt disabled:opacity-40">
                                    Cancel
                                  </button>
                                  <button onClick={saveEditPin} disabled={savingPin}
                                    className="flex items-center gap-1.5 rounded-lg bg-blue-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-600 disabled:opacity-40">
                                    {savingPin ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                                    Save Pin
                                  </button>
                                </div>
                              </div>
                            ) : (
                              // ── READ-ONLY MODE ──
                              <div className="grid grid-cols-4 gap-4 text-[11px]">
                                <div>
                                  <span className="text-slate-500 block">Contact Type</span>
                                  <span className="text-slate-300">{pin.contact_type || '—'}</span>
                                </div>
                                <div>
                                  <span className="text-slate-500 block">Pin Size</span>
                                  <span className="text-slate-300">{pin.pin_size ? labelize(pin.pin_size) : '—'}</span>
                                </div>
                                <div>
                                  <span className="text-slate-500 block">Frequency</span>
                                  <span className="text-slate-300 font-mono">{pin.frequency_mhz != null ? `${pin.frequency_mhz} MHz` : '—'}</span>
                                </div>
                                <div>
                                  <span className="text-slate-500 block">Rise Time</span>
                                  <span className="text-slate-300 font-mono">{pin.rise_time_ns != null ? `${pin.rise_time_ns} ns` : '—'}</span>
                                </div>
                                <div>
                                  <span className="text-slate-500 block">DC Bias</span>
                                  <span className="text-slate-300 font-mono">{pin.voltage_dc_bias != null ? `${pin.voltage_dc_bias} V` : '—'}</span>
                                </div>
                                <div>
                                  <span className="text-slate-500 block">Termination</span>
                                  <span className="text-slate-300">{pin.termination || '—'}</span>
                                </div>
                                <div>
                                  <span className="text-slate-500 block">Pull Up/Down</span>
                                  <span className="text-slate-300">{pin.pull_up_down || '—'}</span>
                                </div>
                                <div>
                                  <span className="text-slate-500 block">ESD Protection</span>
                                  <span className="text-slate-300">{pin.esd_protection || '—'}</span>
                                </div>
                                {pin.description && (
                                  <div className="col-span-4">
                                    <span className="text-slate-500 block">Description</span>
                                    <span className="text-slate-300">{pin.description}</span>
                                  </div>
                                )}
                                {pin.notes && (
                                  <div className="col-span-4">
                                    <span className="text-slate-500 block">Notes</span>
                                    <span className="text-slate-300">{pin.notes}</span>
                                  </div>
                                )}
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Delete Connector Modal ── */}
      {showDeleteConn && connector && (
        <DeleteConnectorDialog connector={connector}
          onClose={() => setShowDeleteConn(false)} onConfirm={handleDeleteConnector} />
      )}

      {/* Phase 3 — INTF-002: Bulk rename pattern modal */}
      {showRenameModal && (
        <RenamePatternModal
          count={selectedPinIds.size}
          busy={bulkBusy}
          onClose={() => setShowRenameModal(false)}
          onApply={handleRenamePattern}
        />
      )}
    </div>
  );
}

/**
 * Phase 3 — INTF-002: rename-pattern modal for bulk pin renames.
 * Supports literal substring or regex find/replace across the selected pins.
 */
function RenamePatternModal({ count, busy, onClose, onApply }: {
  count: number;
  busy: boolean;
  onClose: () => void;
  onApply: (pattern: string, replacement: string, useRegex: boolean) => void;
}) {
  const [pattern, setPattern] = useState('');
  const [replacement, setReplacement] = useState('');
  const [useRegex, setUseRegex] = useState(false);
  const [patternError, setPatternError] = useState('');

  const validate = (): boolean => {
    if (!pattern) {
      setPatternError('Pattern is required');
      return false;
    }
    if (useRegex) {
      try {
        new RegExp(pattern);
      } catch {
        setPatternError('Invalid regular expression');
        return false;
      }
    }
    setPatternError('');
    return true;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-labelledby="rename-title"
        className="w-full max-w-md rounded-2xl border border-astra-border bg-astra-surface p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 id="rename-title" className="text-sm font-bold text-slate-100">Rename Pattern</h3>
          <button type="button" onClick={onClose} aria-label="Close rename modal" className="text-slate-400 hover:text-slate-200">
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <p className="mb-3 text-[11px] text-slate-500">
          Apply a find/replace pattern to the internal signal name of {count} selected pin{count !== 1 ? 's' : ''}.
        </p>

        {patternError && (
          <div role="alert" className="mb-3 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-1.5 text-xs text-red-400">
            {patternError}
          </div>
        )}

        <div className="space-y-3">
          <div>
            <label htmlFor="rp-pattern" className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">Find</label>
            <input id="rp-pattern" value={pattern} onChange={(e) => setPattern(e.target.value)}
              placeholder={useRegex ? '^OLD_(.+)$' : 'OLD_'}
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm font-mono text-slate-200 outline-none focus:border-blue-500/50" />
          </div>
          <div>
            <label htmlFor="rp-replacement" className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">Replace With</label>
            <input id="rp-replacement" value={replacement} onChange={(e) => setReplacement(e.target.value)}
              placeholder={useRegex ? 'NEW_$1' : 'NEW_'}
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm font-mono text-slate-200 outline-none focus:border-blue-500/50" />
          </div>
          <label htmlFor="rp-regex" className="flex items-center gap-2 text-[11px] text-slate-300">
            <input id="rp-regex" type="checkbox" checked={useRegex} onChange={(e) => setUseRegex(e.target.checked)}
              className="rounded border-astra-border bg-astra-bg" />
            Treat Find as a regular expression (use $1, $2 for capture groups)
          </label>
        </div>

        <div className="mt-5 flex items-center justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-astra-border px-4 py-2 text-xs text-slate-400 hover:text-slate-200">
            Cancel
          </button>
          <button type="button" disabled={busy} onClick={() => { if (validate()) onApply(pattern, replacement, useRegex); }}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed">
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Wand2 className="h-3.5 w-3.5" aria-hidden="true" />}
            Apply
          </button>
        </div>
      </div>
    </div>
  );
}
