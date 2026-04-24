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

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft, Loader2, Edit3, Save, X, Plus, Trash2, RefreshCw,
  Cable, ChevronRight, ChevronDown, AlertTriangle, Search,
  Zap, Sparkles, ArrowUpDown, CheckCircle,
} from 'lucide-react';
import clsx from 'clsx';
import { interfaceAPI } from '@/lib/interface-api';
import type { ConnectorWithPins, Pin } from '@/lib/interface-types';
import { SIGNAL_TYPE_COLORS, labelize } from '@/lib/interface-types';

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
//  Add Pins Multi-Row Form
// ══════════════════════════════════════

interface PinRow { key: number; pin_number: string; signal_name: string; signal_type: string; direction: string; }

function AddPinsForm({ connectorId, existingPins, onSaved, onCancel }: {
  connectorId: number; existingPins: Pin[]; onSaved: () => void; onCancel: () => void;
}) {
  const nextNum = useMemo(() => {
    const nums = existingPins.map(p => parseInt(p.pin_number)).filter(n => !isNaN(n));
    return nums.length > 0 ? Math.max(...nums) + 1 : 1;
  }, [existingPins]);

  const [rows, setRows] = useState<PinRow[]>([
    { key: 1, pin_number: String(nextNum), signal_name: '', signal_type: 'spare', direction: 'no_connect' },
  ]);
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState('');

  const addRow = () => {
    const maxNum = Math.max(...rows.map(r => parseInt(r.pin_number) || 0), nextNum - 1);
    setRows(prev => [...prev, {
      key: Date.now(), pin_number: String(maxNum + 1),
      signal_name: '', signal_type: 'spare', direction: 'no_connect',
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
        valid.map(r => ({ pin_number: r.pin_number, signal_name: r.signal_name, signal_type: r.signal_type, direction: r.direction }))
      );
      onSaved();
    } catch (e: any) { setError(e?.response?.data?.detail || 'Failed to add pins'); }
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
        <div className="grid grid-cols-[60px_1fr_1fr_1fr_32px] gap-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500 px-1">
          <span>Pin #</span><span>Signal Name</span><span>Signal Type</span><span>Direction</span><span />
        </div>
        {rows.map(r => (
          <div key={r.key} className="grid grid-cols-[60px_1fr_1fr_1fr_32px] gap-2">
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
    } catch (e: any) { flash(e?.response?.data?.detail || 'Save failed'); }
    setSavingEdit(false);
  };

  const ef = (field: string, value: any) => setEditFields(prev => ({ ...prev, [field]: value }));

  // ══════════════════════════════════════
  //  Pin Actions
  // ══════════════════════════════════════

  const handleAutoGenerate = async () => {
    setAutoGenLoading(true);
    try {
      await interfaceAPI.autoGeneratePins(connectorId);
      flash('Pins auto-generated');
      fetchConnector();
    } catch (e: any) { flash(e?.response?.data?.detail || 'Auto-generate failed'); }
    setAutoGenLoading(false);
  };

  const handleDeletePin = async (pinId: number) => {
    try {
      await interfaceAPI.deletePin(pinId);
      setDeleteConfirmPin(null);
      fetchConnector();
    } catch (e: any) { flash(e?.response?.data?.detail || 'Delete failed'); }
  };

  const handleDeleteConnector = async () => {
    try {
      await interfaceAPI.deleteConnector(connectorId, true);
      // Navigate back to unit
      if (unitId) router.push(`${p}/interfaces/unit/${unitId}`);
      else router.push(`${p}/interfaces`);
    } catch (e: any) {
      flash(e?.response?.data?.detail || 'Delete failed');
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
          <div className="rounded-xl border border-blue-500/20 bg-astra-surface p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Edit Connector</h3>
              <div className="flex gap-2">
                <button onClick={() => { setEditing(false); setEditFields({}); }}
                  className="rounded-lg border border-astra-border px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200">Cancel</button>
                <button onClick={saveEdit} disabled={savingEdit}
                  className="flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-40">
                  {savingEdit ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />} Save
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-6">
              <div className="space-y-2">
                <h4 className="text-[10px] font-bold text-slate-500">PHYSICAL</h4>
                {[
                  { f: 'name', l: 'Name', el: 'input' },
                  { f: 'connector_type', l: 'Type', el: 'select', opts: CONNECTOR_TYPES },
                  { f: 'gender', l: 'Gender', el: 'select', opts: GENDERS },
                  { f: 'mounting', l: 'Mounting', el: 'select', opts: MOUNTINGS },
                  { f: 'shell_size', l: 'Shell Size', el: 'input' },
                  { f: 'insert_arrangement', l: 'Insert Arrangement', el: 'input' },
                  { f: 'total_contacts', l: 'Total Contacts', el: 'input', type: 'number' },
                ].map(r => (
                  <div key={r.f} className="flex items-center justify-between py-1 border-b border-astra-border/50">
                    <span className="text-[11px] text-slate-500 w-40">{r.l}</span>
                    {r.el === 'select' ? (
                      <select value={editFields[r.f] || ''} onChange={e => ef(r.f, e.target.value)}
                        className="w-40 rounded border border-astra-border bg-astra-bg px-2 py-1 text-[12px] text-slate-200 outline-none focus:border-blue-500/50">
                        <option value="">—</option>
                        {r.opts!.map(o => <option key={o} value={o}>{labelize(o)}</option>)}
                      </select>
                    ) : (
                      <input type={r.type || 'text'} value={editFields[r.f] ?? ''} onChange={e => ef(r.f, e.target.value)}
                        className="w-40 rounded border border-astra-border bg-astra-bg px-2 py-1 text-[12px] text-slate-200 outline-none focus:border-blue-500/50 text-right" />
                    )}
                  </div>
                ))}

                <h4 className="text-[10px] font-bold text-slate-500 pt-2">CONTACT BREAKDOWN</h4>
                {[
                  { f: 'signal_contacts', l: 'Signal' }, { f: 'power_contacts', l: 'Power' },
                  { f: 'coax_contacts', l: 'Coax' }, { f: 'fiber_contacts', l: 'Fiber' },
                  { f: 'spare_contacts', l: 'Spare' },
                ].map(r => (
                  <div key={r.f} className="flex items-center justify-between py-1 border-b border-astra-border/50">
                    <span className="text-[11px] text-slate-500 w-40">{r.l}</span>
                    <input type="number" value={editFields[r.f] ?? ''} onChange={e => ef(r.f, e.target.value)}
                      className="w-40 rounded border border-astra-border bg-astra-bg px-2 py-1 text-[12px] text-slate-200 outline-none focus:border-blue-500/50 text-right" />
                  </div>
                ))}
              </div>

              <div className="space-y-2">
                <h4 className="text-[10px] font-bold text-slate-500">ELECTRICAL / ENVIRONMENTAL</h4>
                {[
                  { f: 'keying', l: 'Keying' }, { f: 'polarization', l: 'Polarization' },
                  { f: 'coupling', l: 'Coupling' }, { f: 'ip_rating', l: 'IP Rating' },
                  { f: 'operating_temp_min_c', l: 'Temp Min (°C)', type: 'number' },
                  { f: 'operating_temp_max_c', l: 'Temp Max (°C)', type: 'number' },
                  { f: 'mating_cycles', l: 'Mating Cycles', type: 'number' },
                ].map(r => (
                  <div key={r.f} className="flex items-center justify-between py-1 border-b border-astra-border/50">
                    <span className="text-[11px] text-slate-500 w-40">{r.l}</span>
                    <input type={r.type || 'text'} value={editFields[r.f] ?? ''} onChange={e => ef(r.f, e.target.value)}
                      className="w-40 rounded border border-astra-border bg-astra-bg px-2 py-1 text-[12px] text-slate-200 outline-none focus:border-blue-500/50 text-right" />
                  </div>
                ))}

                <h4 className="text-[10px] font-bold text-slate-500 pt-2">MATERIALS / SPEC</h4>
                {[
                  { f: 'shell_material', l: 'Shell Material' }, { f: 'shell_finish', l: 'Shell Finish' },
                  { f: 'contact_finish', l: 'Contact Finish' }, { f: 'mil_spec', l: 'MIL-SPEC' },
                  { f: 'manufacturer_part_number', l: 'Mfr Part Number' },
                  { f: 'connector_manufacturer', l: 'Manufacturer' },
                  { f: 'backshell_type', l: 'Backshell Type' },
                ].map(r => (
                  <div key={r.f} className="flex items-center justify-between py-1 border-b border-astra-border/50">
                    <span className="text-[11px] text-slate-500 w-40">{r.l}</span>
                    <input value={editFields[r.f] ?? ''} onChange={e => ef(r.f, e.target.value)}
                      className="w-40 rounded border border-astra-border bg-astra-bg px-2 py-1 text-[12px] text-slate-200 outline-none focus:border-blue-500/50 text-right" />
                  </div>
                ))}

                <h4 className="text-[10px] font-bold text-slate-500 pt-2">NOTES</h4>
                <textarea value={editFields.notes || ''} onChange={e => ef('notes', e.target.value)} rows={3}
                  className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-[12px] text-slate-200 outline-none focus:border-blue-500/50 resize-none" />
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

          {/* Add pins form */}
          {showAddPins && (
            <AddPinsForm connectorId={connectorId} existingPins={connector.pins || []}
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
                  Click "Auto-Generate Pins" to create {connector.total_contacts} spare pin slots, or "Add Pins" to define them manually.
                </p>
              )}
            </div>
          ) : (
            <div className="rounded-xl border border-astra-border bg-astra-surface overflow-hidden">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="border-b border-astra-border bg-astra-surface-alt">
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-400 w-14">Pin #</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-400 w-16">Label</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-400">Signal Name</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-400 w-36">Signal Type</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-400 w-28">Direction</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-400 w-20">Voltage</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-400 w-20">Current</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-400 w-16">Ω</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-400 w-24">Bus</th>
                    <th className="px-3 py-2.5 w-16" />
                  </tr>
                </thead>
                <tbody>
                  {filteredPins.map(pin => (
                    <>
                      <tr key={pin.id}
                        className={clsx('border-b border-astra-border/50 hover:bg-astra-surface-alt/50 transition cursor-pointer',
                          expandedPin === pin.id && 'bg-astra-surface-alt/30')}
                        onClick={() => setExpandedPin(prev => prev === pin.id ? null : pin.id)}>
                        <td className="px-3 py-2 font-mono font-bold text-slate-300">{pin.pin_number}</td>
                        <td className="px-3 py-2 text-slate-500">{pin.pin_label || '—'}</td>
                        <td className="px-3 py-2 font-semibold text-slate-200">{pin.signal_name}</td>
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-1.5">
                            <SignalDot type={pin.signal_type} />
                            <span className="text-slate-400 text-[11px]">{labelize(pin.signal_type)}</span>
                          </div>
                        </td>
                        <td className="px-3 py-2 text-slate-400 text-[11px]">{labelize(pin.direction)}</td>
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
                            <button onClick={() => setDeleteConfirmPin(pin.id)}
                              className="rounded p-1 text-slate-600 hover:text-red-400 transition" title="Delete pin">
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          )}
                        </td>
                      </tr>
                      {/* Expanded pin detail */}
                      {expandedPin === pin.id && (
                        <tr key={`${pin.id}-detail`} className="bg-astra-bg/50">
                          <td colSpan={10} className="px-6 py-3">
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
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
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
    </div>
  );
}
