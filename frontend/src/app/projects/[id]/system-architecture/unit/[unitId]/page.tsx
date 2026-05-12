'use client';

/**
 * ASTRA — Unit Detail Page (Full Rewrite)
 * ==========================================
 * File: frontend/src/app/projects/[id]/system-architecture/unit/[unitId]/page.tsx
 *
 * Relocated from /interfaces/unit/[unitId]/ by TDD-SYSARCH-002 Phase 6.
 * The old path 307-redirects via frontend/next.config.js so existing
 * bookmarks survive.
 *
 * Breadcrumb: System Architecture → {System Name} → {Unit Designation}
 * Tabs: Overview | Connectors | Communication | Specifications
 *
 * API calls:
 *   interfaceAPI.getUnit(unitId)              → UnitDetail
 *   interfaceAPI.getSystem(systemId)          → SystemDetail (for breadcrumb)
 *   interfaceAPI.updateUnit(unitId, data)     → UnitResponse
 *   interfaceAPI.createConnector(data)        → Connector
 *   interfaceAPI.deleteConnector(id, force)   → { status }
 *   interfaceAPI.createBus(data)              → BusDefinition
 *   interfaceAPI.deleteBus(id, confirm)       → { status }
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft, Loader2, Edit3, Save, X, Plus, Cpu, Box,
  Cable, Radio, Zap, ChevronRight, ChevronDown, Trash2,
  RefreshCw, Wifi, Thermometer, Shield, AlertTriangle,
  CheckCircle, Package, GitBranch, Link2, Unlink,
} from 'lucide-react';
import CatalogPartPicker from '@/components/catalog/CatalogPartPicker';
import type { CatalogPart, PartClass } from '@/lib/catalog-types';
import clsx from 'clsx';
import { interfaceAPI } from '@/lib/interface-api';
import { formatApiError } from '@/lib/errors';
import type {
  UnitDetail, ConnectorWithPins, Pin, BusWithMessages, MessageSummary,
  UnitEnvironmentalSpec, SystemDetail as SystemDetailType,
  ConnectorType, ConnectorGender, BusProtocol,
} from '@/lib/interface-types';
import { SIGNAL_TYPE_COLORS } from '@/lib/interface-types';

/**
 * Phase 3 — INTF-002: catalog linkage on Unit.
 *
 * The backend Unit row carries `catalog_part_id`, `location_zone`,
 * `serial_number`, `asset_tag`. The Pydantic UnitResponse hasn't been
 * extended yet (frontend-only phase), so we read the fields via this
 * augmented type and render the badge / project-instance fields only
 * when present.
 */
interface UnitWithCatalog extends UnitDetail {
  catalog_part_id?: number | null;
  catalog_part_number?: string | null;
  catalog_revision?: string | null;
  location_zone?: string | null;
  serial_number?: string | null;
  asset_tag?: string | null;
}

type Tab = 'overview' | 'connectors' | 'communication' | 'specifications';

// ══════════════════════════════════════
//  Shared UI
// ══════════════════════════════════════

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  concept:            { bg: 'rgba(100,116,139,0.15)', text: '#94A3B8' },
  preliminary_design: { bg: 'rgba(139,92,246,0.15)',  text: '#A78BFA' },
  detailed_design:    { bg: 'rgba(59,130,246,0.12)',  text: '#3B82F6' },
  prototype:          { bg: 'rgba(245,158,11,0.15)',  text: '#F59E0B' },
  engineering_model:  { bg: 'rgba(6,182,212,0.15)',   text: '#06B6D4' },
  qualification_unit: { bg: 'rgba(234,88,12,0.15)',   text: '#F97316' },
  flight_unit:        { bg: 'rgba(16,185,129,0.20)',  text: '#10B981' },
  operational:        { bg: 'rgba(16,185,129,0.25)',  text: '#34D399' },
  installed:          { bg: 'rgba(16,185,129,0.15)',  text: '#10B981' },
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

/**
 * Phase 3 — INTF-002. Renders the "Catalog: {part_number} (rev X)" badge
 * with a link to /catalog/parts/{id} when the unit was placed from a
 * catalog part. Also renders a "Variants" sibling link.
 *
 * The data is read off the augmented {@link UnitWithCatalog} shape — the
 * Pydantic UnitResponse hasn't been extended yet, so the field may simply
 * be undefined for legacy units, in which case nothing renders.
 */
function CatalogBadge({ unit, router }: {
  unit: UnitWithCatalog;
  router: ReturnType<typeof useRouter>;
}) {
  const cid = unit.catalog_part_id;
  if (!cid) return null;
  const partNumber = unit.catalog_part_number || unit.part_number;
  const revision = unit.catalog_revision || unit.revision;
  return (
    <div className="mt-1 flex items-center gap-2 text-[11px]">
      <button
        type="button"
        onClick={() => router.push(`/catalog/parts/${cid}`)}
        className="inline-flex items-center gap-1 rounded-md bg-blue-500/10 px-2 py-0.5 text-blue-300 ring-1 ring-blue-500/20 hover:bg-blue-500/20"
        aria-label={`View catalog part ${partNumber}`}
      >
        <Package className="h-3 w-3" aria-hidden="true" />
        Catalog: <span className="font-semibold">{partNumber}</span>
        {revision && <span className="text-blue-400/70">(rev {revision})</span>}
      </button>
      <button
        type="button"
        onClick={() => router.push(`/catalog/parts/${cid}`)}
        className="inline-flex items-center gap-1 text-slate-400 hover:text-blue-300"
        aria-label="View part variants"
      >
        <GitBranch className="h-3 w-3" aria-hidden="true" />
        Variants
      </button>
    </div>
  );
}

function SignalDot({ type }: { type: string }) {
  const color = SIGNAL_TYPE_COLORS[type] || '#475569';
  return <div className="h-2 w-2 rounded-full flex-shrink-0" style={{ background: color }} />;
}

function SpecRow({ label, value, unit: u }: { label: string; value: any; unit?: string }) {
  if (value === null || value === undefined) return null;
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-astra-border/50 last:border-0">
      <span className="text-[11px] text-slate-500">{label}</span>
      <span className="text-[12px] font-semibold text-slate-300">{value}{u ? ` ${u}` : ''}</span>
    </div>
  );
}


/**
 * TDD-SYSARCH-002 §6.2 — catalog linkage banner.
 *
 * Sits at the top of the Unit Detail Overview tab. Two visual states:
 *   - Green when `unit.catalog_part_summary` is populated. Shows the
 *     part number, name, mass, attached-CAD/ICD chips, supplier, and
 *     "in-house" indicator. Buttons: Edit Link / Unlink.
 *   - Amber when not linked. Single CTA: "Link to Catalog".
 */
function CatalogLinkageBanner({
  unit,
  onUnlinkRequested,
  onLinkRequested,
}: {
  unit: UnitDetail;
  onUnlinkRequested: () => void;
  onLinkRequested: () => void;
}) {
  const cp = unit.catalog_part_summary;
  if (!cp) {
    return (
      <div className="mb-4 flex items-center gap-3 rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3">
        <Unlink className="h-4 w-4 flex-shrink-0 text-amber-400" aria-hidden="true" />
        <div className="flex-1">
          <p className="text-[12px] font-semibold text-amber-200">Not linked to catalog</p>
          <p className="text-[10px] text-amber-300/70">
            Link to a CatalogPart to source manufacturer / part number / mass automatically.
          </p>
        </div>
        <button
          type="button"
          onClick={onLinkRequested}
          className="rounded-lg bg-gradient-to-br from-blue-500 to-violet-500 px-3 py-1.5 text-[11px] font-semibold text-white hover:shadow-lg"
        >
          Link to Catalog
        </button>
      </div>
    );
  }
  return (
    <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-emerald-500/30 bg-emerald-500/5 px-4 py-3">
      <Link2 className="h-4 w-4 flex-shrink-0 text-emerald-400" aria-hidden="true" />
      <div className="flex flex-1 flex-wrap items-center gap-2">
        <span className="text-[12px] text-emerald-200">
          Linked to <strong className="font-mono">{cp.part_number}</strong> · {cp.name}
        </span>
        {cp.mass_kg != null && (
          <span className="rounded-full bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-300">
            {cp.mass_kg} kg
          </span>
        )}
        {cp.cad_step_path && (
          <span className="rounded-full bg-blue-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-blue-300">
            CAD attached
          </span>
        )}
        {cp.supplier_name && (
          <span className="rounded-full bg-slate-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-slate-200">
            {cp.supplier_name}
            {cp.supplier_is_in_house && (
              <span className="ml-1 text-emerald-300">· in-house</span>
            )}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onLinkRequested}
          className="rounded border border-astra-border px-2.5 py-1 text-[11px] text-slate-300 hover:border-blue-500/30 hover:text-blue-300"
        >
          Edit link
        </button>
        <button
          type="button"
          onClick={onUnlinkRequested}
          className="rounded border border-red-500/30 bg-red-500/10 px-2.5 py-1 text-[11px] text-red-300 hover:bg-red-500/20"
        >
          Unlink
        </button>
      </div>
    </div>
  );
}

// ── Editable spec row ──
function EditRow({ label, field, value, onChange, type = 'text', unit: u }: {
  label: string; field: string; value: any; onChange: (f: string, v: any) => void;
  type?: string; unit?: string;
}) {
  return (
    <div className="flex items-center justify-between py-1 border-b border-astra-border/50 last:border-0">
      <span className="text-[11px] text-slate-500 w-40 flex-shrink-0">{label}</span>
      <div className="flex items-center gap-1">
        <input type={type} value={value ?? ''} onChange={e => onChange(field, type === 'number' ? e.target.value : e.target.value)}
          className="w-32 rounded border border-astra-border bg-astra-bg px-2 py-1 text-[12px] text-slate-200 outline-none focus:border-blue-500/50 text-right" />
        {u && <span className="text-[10px] text-slate-500 w-8">{u}</span>}
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  Connector type / gender / bus type lists (subset for forms)
// ══════════════════════════════════════

const CONNECTOR_TYPES = [
  'd_sub_25', 'd_sub_15', 'd_sub_9', 'circular_mil', 'circular_commercial',
  'micro_d', 'nano_d', 'rectangular', 'rj45', 'usb_c', 'sma', 'bnc',
  'tnc', 'type_n', 'sc_fiber', 'lc_fiber', 'm8', 'm12', 'pcb_header',
  'terminal_block', 'custom',
];

const GENDERS = ['male_pin', 'female_socket', 'hermaphroditic', 'genderless', 'hybrid'];

const BUS_TYPES = [
  'mil_std_1553b', 'mil_std_1553a', 'can_2_0b', 'can_fd', 'spi', 'i2c',
  'rs422', 'rs485', 'rs232', 'spacewire', 'arinc_429', 'arinc_664',
  'ethernet_100base_t', 'ethernet_1000base_t', 'uart', 'jtag',
  'custom',
];

// ══════════════════════════════════════
//  Main Page
// ══════════════════════════════════════

export default function UnitDetailPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);
  const unitId    = Number(params.unitId);
  const p = `/projects/${projectId}`;

  // ── Core state ──
  const [unit, setUnit]               = useState<UnitDetail | null>(null);
  const [systemName, setSystemName]   = useState('');
  const [loading, setLoading]         = useState(true);
  const [tab, setTab]                 = useState<Tab>('overview');
  const [msg, setMsg]                 = useState('');

  // ── Overview editing ──
  const [editingOverview, setEditingOverview]   = useState(false);
  const [editFields, setEditFields]             = useState<Record<string, any>>({});
  const [savingOverview, setSavingOverview]      = useState(false);

  // ── TDD-SYSARCH-002 §6.2: catalog link / unlink modals ──
  const [showLinkPicker, setShowLinkPicker]     = useState(false);
  const [showUnlinkConfirm, setShowUnlinkConfirm] = useState(false);
  const [linkSaving, setLinkSaving]              = useState(false);
  const [linkError, setLinkError]                = useState<string | null>(null);

  // ── Specs editing ──
  const [editingSpecs, setEditingSpecs]   = useState(false);
  const [specFields, setSpecFields]       = useState<Record<string, any>>({});
  const [savingSpecs, setSavingSpecs]     = useState(false);

  // ── Connector CRUD ──
  const [showAddConn, setShowAddConn]     = useState(false);
  const [connForm, setConnForm]           = useState<{
    designator: string; name: string; connector_type: ConnectorType; gender: ConnectorGender; total_contacts: number;
  }>({ designator: '', name: '', connector_type: 'mil_dtl_38999_series_iii', gender: 'female_socket', total_contacts: 37 });
  const [savingConn, setSavingConn]       = useState(false);
  const [expandedConns, setExpandedConns] = useState<Set<number>>(new Set());
  const [deleteConnId, setDeleteConnId]   = useState<number | null>(null);

  // ── Bus CRUD ──
  const [showAddBus, setShowAddBus]       = useState(false);
  const [busForm, setBusForm]             = useState<{ name: string; bus_type: BusProtocol; protocol_version: string }>({ name: '', bus_type: 'mil_std_1553b', protocol_version: '' });
  const [savingBus, setSavingBus]         = useState(false);

  // ── Fetch ──
  const fetchUnit = useCallback(async () => {
    setLoading(true);
    try {
      const res = await interfaceAPI.getUnit(unitId);
      setUnit(res.data);
      // Fetch system name for breadcrumb
      if (res.data?.system_id) {
        try {
          const sysRes = await interfaceAPI.getSystem(res.data.system_id);
          setSystemName(sysRes.data?.name || '');
        } catch { setSystemName(''); }
      }
    } catch { }
    setLoading(false);
  }, [unitId]);

  useEffect(() => { fetchUnit(); }, [fetchUnit]);

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(''), 3500); };

  // ══════════════════════════════════════
  //  Overview edit handlers
  // ══════════════════════════════════════

  const startEditOverview = () => {
    if (!unit) return;
    setEditFields({
      name: unit.name, designation: unit.designation, part_number: unit.part_number,
      manufacturer: unit.manufacturer, status: unit.status, heritage: unit.heritage || '',
      description: unit.description || '', cage_code: unit.cage_code || '',
      nsn: unit.nsn || '', drawing_number: unit.drawing_number || '', revision: unit.revision || '',
      mass_kg: unit.mass_kg ?? '', mass_max_kg: unit.mass_max_kg ?? '',
      power_watts_nominal: unit.power_watts_nominal ?? '', power_watts_peak: unit.power_watts_peak ?? '',
      power_watts_standby: unit.power_watts_standby ?? '',
      voltage_input_nominal: unit.voltage_input_nominal || '',
      voltage_input_min: unit.voltage_input_min ?? '', voltage_input_max: unit.voltage_input_max ?? '',
      current_inrush_amps: unit.current_inrush_amps ?? '',
      current_steady_state_amps: unit.current_steady_state_amps ?? '',
      mtbf_hours: unit.mtbf_hours ?? '', design_life_years: unit.design_life_years ?? '',
      duty_cycle_pct: unit.duty_cycle_pct ?? '',
    });
    setEditingOverview(true);
  };

  const saveOverview = async () => {
    setSavingOverview(true);
    try {
      const data: Record<string, any> = {};
      for (const [k, v] of Object.entries(editFields)) {
        data[k] = v === '' ? null : v;
      }
      await interfaceAPI.updateUnit(unitId, data);
      setEditingOverview(false);
      flash('Unit updated');
      fetchUnit();
    } catch (e: any) { flash(formatApiError(e, 'Save failed')); }
    setSavingOverview(false);
  };

  // ── TDD-SYSARCH-002 §6.2: catalog link / unlink handlers ──
  const handleLinkCatalog = async (cp: CatalogPart | null) => {
    if (cp == null) {
      setShowLinkPicker(false);
      return;
    }
    setLinkSaving(true);
    setLinkError(null);
    try {
      // PATCH catalog_part_id; backend Phase 2 fires the right audit
      // event (linked_to_catalog vs catalog_link_changed) and returns
      // the eager-loaded catalog_part_summary on the response.
      await interfaceAPI.updateUnit(unitId, { catalog_part_id: cp.id } as Record<string, unknown>);
      setShowLinkPicker(false);
      flash(`Linked to catalog part ${cp.part_number}`);
      fetchUnit();
    } catch (e: any) {
      setLinkError(formatApiError(e, 'Link failed'));
    } finally {
      setLinkSaving(false);
    }
  };

  const handleUnlinkCatalog = async () => {
    setLinkSaving(true);
    setLinkError(null);
    try {
      await interfaceAPI.updateUnit(unitId, { catalog_part_id: null } as Record<string, unknown>);
      setShowUnlinkConfirm(false);
      flash('Unlinked from catalog');
      fetchUnit();
    } catch (e: any) {
      setLinkError(formatApiError(e, 'Unlink failed'));
    } finally {
      setLinkSaving(false);
    }
  };

  const onEditField = (field: string, value: any) => {
    setEditFields(prev => ({ ...prev, [field]: value }));
  };

  // ══════════════════════════════════════
  //  Specs edit handlers
  // ══════════════════════════════════════

  const startEditSpecs = () => {
    if (!unit) return;
    setSpecFields({
      temp_operating_min_c: unit.temp_operating_min_c ?? '', temp_operating_max_c: unit.temp_operating_max_c ?? '',
      temp_storage_min_c: unit.temp_storage_min_c ?? '', temp_storage_max_c: unit.temp_storage_max_c ?? '',
      temp_survival_min_c: unit.temp_survival_min_c ?? '', temp_survival_max_c: unit.temp_survival_max_c ?? '',
      vibration_random_grms: unit.vibration_random_grms ?? '', vibration_sine_g_peak: unit.vibration_sine_g_peak ?? '',
      shock_mechanical_g: unit.shock_mechanical_g ?? '', shock_pyrotechnic_g: unit.shock_pyrotechnic_g ?? '',
      acceleration_max_g: unit.acceleration_max_g ?? '', acoustic_spl_db: unit.acoustic_spl_db ?? '',
      emi_ce101_limit_dba: unit.emi_ce101_limit_dba ?? '', emi_ce102_limit_dbua: unit.emi_ce102_limit_dbua ?? '',
      emi_cs101_limit_db: unit.emi_cs101_limit_db ?? '', emi_re102_limit_dbm: unit.emi_re102_limit_dbm ?? '',
      emi_rs103_limit_vm: unit.emi_rs103_limit_vm ?? '', esd_hbm_v: unit.esd_hbm_v ?? '',
      radiation_tid_krad: unit.radiation_tid_krad ?? '', radiation_see_let_threshold: unit.radiation_see_let_threshold ?? '',
    });
    setEditingSpecs(true);
  };

  const saveSpecs = async () => {
    setSavingSpecs(true);
    try {
      const data: Record<string, any> = {};
      for (const [k, v] of Object.entries(specFields)) { data[k] = v === '' ? null : Number(v); }
      await interfaceAPI.updateUnit(unitId, data);
      setEditingSpecs(false);
      flash('Specifications updated');
      fetchUnit();
    } catch { flash('Save failed'); }
    setSavingSpecs(false);
  };

  const onSpecField = (field: string, value: any) => {
    setSpecFields(prev => ({ ...prev, [field]: value }));
  };

  // ══════════════════════════════════════
  //  Connector handlers
  // ══════════════════════════════════════

  const handleAddConnector = async () => {
    setSavingConn(true);
    try {
      await interfaceAPI.createConnector({ unit_id: unitId, ...connForm });
      setShowAddConn(false);
      setConnForm({ designator: '', name: '', connector_type: 'mil_dtl_38999_series_iii' as ConnectorType, gender: 'female_socket' as ConnectorGender, total_contacts: 37 });
      flash('Connector created');
      fetchUnit();
    } catch (e: any) { flash(formatApiError(e, 'Failed')); }
    setSavingConn(false);
  };

  const handleDeleteConnector = async (connId: number) => {
    try {
      await interfaceAPI.deleteConnector(connId, true);
      setDeleteConnId(null);
      flash('Connector deleted');
      fetchUnit();
    } catch (e: any) { flash(formatApiError(e, 'Delete failed')); }
  };

  const toggleConnExpand = (id: number) => {
    setExpandedConns(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  };

  // ══════════════════════════════════════
  //  Bus handlers
  // ══════════════════════════════════════

  const handleAddBus = async () => {
    setSavingBus(true);
    try {
      await interfaceAPI.createBus({ unit_id: unitId, project_id: projectId, name: busForm.name, protocol: busForm.bus_type, protocol_version: busForm.protocol_version || undefined });
      setShowAddBus(false);
      setBusForm({ name: '', bus_type: 'mil_std_1553b', protocol_version: '' });
      flash('Bus created');
      fetchUnit();
    } catch (e: any) { flash(formatApiError(e, 'Failed')); }
    setSavingBus(false);
  };

  // ══════════════════════════════════════
  //  Computed
  // ══════════════════════════════════════

  const totalPins = useMemo(() => unit?.connectors.reduce((s, c) => s + (c.pins?.length || 0), 0) || 0, [unit]);
  const totalMsgs = useMemo(() => unit?.bus_definitions.reduce((s, b) => s + (b.messages?.length || 0), 0) || 0, [unit]);

  // ── Loading / not found ──
  if (loading) return <div className="flex items-center justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-blue-500" /></div>;
  if (!unit) return (
    <div className="py-20 text-center">
      <AlertTriangle className="mx-auto h-10 w-10 text-red-400 mb-3" />
      <p className="text-sm text-slate-400">Unit not found.</p>
      <button onClick={() => router.push(`${p}/system-architecture?tab=units`)} className="mt-3 text-xs text-blue-400 hover:underline">Back to System Architecture</button>
    </div>
  );

  return (
    <div>
      {/* ── Breadcrumb ── */}
      <div className="mb-4 flex items-center gap-1.5 text-[11px] text-slate-500">
        <button onClick={() => router.push(`${p}/system-architecture?tab=units`)} className="hover:text-blue-400 transition">System Architecture</button>
        <ChevronRight className="h-3 w-3" />
        {unit.system_id && (
          <>
            <button onClick={() => router.push(`${p}/system-architecture/system/${unit.system_id}`)} className="hover:text-blue-400 transition">
              {systemName || 'System'}
            </button>
            <ChevronRight className="h-3 w-3" />
          </>
        )}
        <span className="text-slate-300 font-semibold">{unit.designation}</span>
      </div>

      {/* ── Header ── */}
      <div className="mb-4 flex items-start justify-between">
        <div className="flex items-start gap-4">
          <button onClick={() => router.back()} className="mt-1 rounded-lg border border-astra-border p-2 text-slate-500 hover:text-slate-300 transition">
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="font-mono text-base font-bold text-blue-400">{unit.designation}</span>
              <span className="capitalize text-[11px] text-slate-500 rounded-full bg-astra-surface-alt px-2 py-0.5">{unit.unit_type.replace(/_/g, ' ')}</span>
              <StatusBadge status={unit.status} />
            </div>
            <h1 className="text-lg font-bold text-slate-100">{unit.name}</h1>
            <p className="text-[12px] text-slate-500">{unit.manufacturer} · {unit.part_number}</p>
            {/*
             * Phase 3 — INTF-002: catalog badge + variants link.
             * Renders only when the unit was placed from a catalog part.
             */}
            <CatalogBadge unit={unit as UnitWithCatalog} router={router} />
            {/*
             * Phase 5: <SyncProposalIndicator unitId={unit.id} />
             * The req-sync data structure ships in Phase 5; until then this
             * stays as a placeholder so the layout slot is reserved.
             */}
          </div>
        </div>
        <button onClick={fetchUnit} className="rounded-lg border border-astra-border p-2 text-slate-500 hover:text-slate-300" title="Refresh">
          <RefreshCw className={clsx('h-3.5 w-3.5', loading && 'animate-spin')} />
        </button>
      </div>

      {/* ── Message ── */}
      {msg && (
        <div className={clsx('mb-4 rounded-lg border px-3 py-2 text-xs flex items-center gap-2',
          msg.includes('fail') || msg.includes('error') ? 'border-red-500/20 bg-red-500/10 text-red-400' : 'border-emerald-500/20 bg-emerald-500/10 text-emerald-400')}>
          {msg.includes('fail') || msg.includes('error') ? <AlertTriangle className="h-3.5 w-3.5" /> : <CheckCircle className="h-3.5 w-3.5" />} {msg}
        </div>
      )}

      {/* ── Quick stats ── */}
      <div className="mb-4 grid grid-cols-5 gap-3">
        {[
          { label: 'Connectors', value: unit.connectors.length, color: '#3B82F6' },
          { label: 'Pins',       value: totalPins,               color: '#06B6D4' },
          { label: 'Buses',      value: unit.bus_definitions.length, color: '#8B5CF6' },
          { label: 'Messages',   value: totalMsgs,               color: '#10B981' },
          { label: 'Env Specs',  value: unit.environmental_specs.length, color: '#F59E0B' },
        ].map(s => (
          <div key={s.label} className="rounded-xl border border-astra-border bg-astra-surface p-3 text-center">
            <div className="text-xl font-bold" style={{ color: s.color }}>{s.value}</div>
            <div className="text-[10px] text-slate-500">{s.label}</div>
          </div>
        ))}
      </div>

      {/* ── Tabs ── */}
      <div className="mb-4 flex gap-1 border-b border-astra-border">
        {([
          { key: 'overview' as Tab, label: 'Overview', icon: Box },
          { key: 'connectors' as Tab, label: 'Connectors', icon: Cable },
          { key: 'communication' as Tab, label: 'Communication', icon: Wifi },
          { key: 'specifications' as Tab, label: 'Specifications', icon: Thermometer },
        ]).map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={clsx('flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-xs font-semibold transition',
              tab === t.key ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-500 hover:text-slate-300')}>
            <t.icon className="h-3.5 w-3.5" /> {t.label}
          </button>
        ))}
      </div>

      {/* ══════════════════════════════════════════════════════ */}
      {/*  TAB 1 — OVERVIEW                                    */}
      {/* ══════════════════════════════════════════════════════ */}
      {tab === 'overview' && (
        editingOverview ? (
          <div className="rounded-xl border border-blue-500/20 bg-astra-surface p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Edit Unit</h3>
              <div className="flex gap-2">
                <button onClick={() => setEditingOverview(false)} className="rounded-lg border border-astra-border px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200">Cancel</button>
                <button onClick={saveOverview} disabled={savingOverview}
                  className="flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-40">
                  {savingOverview ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />} Save
                </button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-6">
              <div>
                <h4 className="text-[10px] font-bold text-slate-500 mb-2">IDENTIFICATION</h4>
                {[
                  { f: 'name', l: 'Name' }, { f: 'designation', l: 'Designation' },
                  { f: 'part_number', l: 'Part Number' }, { f: 'manufacturer', l: 'Manufacturer' },
                  { f: 'cage_code', l: 'CAGE Code' }, { f: 'nsn', l: 'NSN' },
                  { f: 'drawing_number', l: 'Drawing' }, { f: 'revision', l: 'Revision' },
                  { f: 'heritage', l: 'Heritage' },
                ].map(r => <EditRow key={r.f} label={r.l} field={r.f} value={editFields[r.f]} onChange={onEditField} />)}
              </div>
              <div>
                <h4 className="text-[10px] font-bold text-slate-500 mb-2">PHYSICAL / ELECTRICAL / RELIABILITY</h4>
                {[
                  { f: 'mass_kg', l: 'Mass', u: 'kg', t: 'number' },
                  { f: 'mass_max_kg', l: 'Max Mass', u: 'kg', t: 'number' },
                  { f: 'power_watts_nominal', l: 'Power Nom', u: 'W', t: 'number' },
                  { f: 'power_watts_peak', l: 'Power Peak', u: 'W', t: 'number' },
                  { f: 'power_watts_standby', l: 'Power Standby', u: 'W', t: 'number' },
                  { f: 'voltage_input_nominal', l: 'Voltage Input' },
                  { f: 'voltage_input_min', l: 'Voltage Min', u: 'V', t: 'number' },
                  { f: 'voltage_input_max', l: 'Voltage Max', u: 'V', t: 'number' },
                  { f: 'current_inrush_amps', l: 'Inrush Current', u: 'A', t: 'number' },
                  { f: 'mtbf_hours', l: 'MTBF', u: 'hrs', t: 'number' },
                  { f: 'design_life_years', l: 'Design Life', u: 'yrs', t: 'number' },
                  { f: 'duty_cycle_pct', l: 'Duty Cycle', u: '%', t: 'number' },
                ].map(r => <EditRow key={r.f} label={r.l} field={r.f} value={editFields[r.f]} onChange={onEditField} type={r.t} unit={r.u} />)}
              </div>
            </div>
          </div>
        ) : (
          <div className="relative">
            <button onClick={startEditOverview}
              className="absolute top-4 right-4 flex items-center gap-1 rounded-lg border border-astra-border px-3 py-1.5 text-xs text-slate-400 hover:text-blue-400 hover:border-blue-500/30 z-10">
              <Edit3 className="h-3 w-3" /> Edit
            </button>

            {/* TDD-SYSARCH-002 §6.2: catalog linkage banner */}
            <CatalogLinkageBanner
              unit={unit}
              onUnlinkRequested={() => setShowUnlinkConfirm(true)}
              onLinkRequested={() => setShowLinkPicker(true)}
            />

            <div className="grid grid-cols-2 gap-6">
              <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
                <h3 className="text-xs font-bold text-slate-400 mb-3">IDENTIFICATION</h3>
                <SpecRow label="Unit ID" value={unit.unit_id} />
                <SpecRow label="Designation" value={unit.designation} />
                <SpecRow label="Part Number" value={unit.part_number} />
                <SpecRow label="Manufacturer" value={unit.manufacturer} />
                <SpecRow label="CAGE Code" value={unit.cage_code} />
                <SpecRow label="NSN" value={unit.nsn} />
                <SpecRow label="Drawing" value={unit.drawing_number} />
                <SpecRow label="Revision" value={unit.revision} />
                <SpecRow label="Heritage" value={unit.heritage} />
                {unit.description && (
                  <div className="mt-3 pt-2 border-t border-astra-border">
                    <span className="text-[10px] text-slate-500 block mb-1">Description</span>
                    <p className="text-[12px] text-slate-300">{unit.description}</p>
                  </div>
                )}
              </div>
              <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
                <h3 className="text-xs font-bold text-slate-400 mb-3">PHYSICAL</h3>
                <SpecRow label="Mass" value={unit.mass_kg} unit="kg" />
                <SpecRow label="Max Mass" value={unit.mass_max_kg} unit="kg" />
                <SpecRow label="Dimensions" value={unit.dimensions_l_mm && unit.dimensions_w_mm && unit.dimensions_h_mm ? `${unit.dimensions_l_mm} × ${unit.dimensions_w_mm} × ${unit.dimensions_h_mm}` : null} unit="mm" />
                <h3 className="text-xs font-bold text-slate-400 mt-4 mb-3">ELECTRICAL</h3>
                <SpecRow label="Power (nominal)" value={unit.power_watts_nominal} unit="W" />
                <SpecRow label="Power (peak)" value={unit.power_watts_peak} unit="W" />
                <SpecRow label="Power (standby)" value={unit.power_watts_standby} unit="W" />
                <SpecRow label="Voltage Input" value={unit.voltage_input_nominal} />
                <SpecRow label="Voltage Range" value={unit.voltage_input_min != null && unit.voltage_input_max != null ? `${unit.voltage_input_min} – ${unit.voltage_input_max}` : null} unit="V" />
                <SpecRow label="Inrush Current" value={unit.current_inrush_amps} unit="A" />
                <SpecRow label="Steady State Current" value={unit.current_steady_state_amps} unit="A" />
                <h3 className="text-xs font-bold text-slate-400 mt-4 mb-3">RELIABILITY</h3>
                <SpecRow label="MTBF" value={unit.mtbf_hours} unit="hrs" />
                <SpecRow label="Design Life" value={unit.design_life_years} unit="yrs" />
                <SpecRow label="Duty Cycle" value={unit.duty_cycle_pct} unit="%" />
                <SpecRow label="Derating Std" value={unit.derating_standard} />
              </div>
            </div>
          </div>
        )
      )}

      {/* ══════════════════════════════════════════════════════ */}
      {/*  TAB 2 — CONNECTORS                                  */}
      {/* ══════════════════════════════════════════════════════ */}
      {tab === 'connectors' && (
        <div className="space-y-3">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-semibold text-slate-400">{unit.connectors.length} connector{unit.connectors.length !== 1 ? 's' : ''}</h3>
            <button onClick={() => setShowAddConn(true)}
              className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500">
              <Plus className="h-3.5 w-3.5" /> Add Connector
            </button>
          </div>

          {/* Add connector form */}
          {showAddConn && (
            <div className="rounded-xl border border-blue-500/20 bg-astra-surface p-4 mb-3 space-y-3">
              <h4 className="text-xs font-bold text-slate-400">New Connector</h4>
              <div className="grid grid-cols-5 gap-3">
                <input value={connForm.designator} onChange={e => setConnForm({ ...connForm, designator: e.target.value })} placeholder="Designator (J1) *"
                  className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
                <input value={connForm.name} onChange={e => setConnForm({ ...connForm, name: e.target.value })} placeholder="Name"
                  className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
                <select value={connForm.connector_type} onChange={e => setConnForm({ ...connForm, connector_type: e.target.value as ConnectorType })}
                  className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50">
                  {CONNECTOR_TYPES.map(t => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
                </select>
                <select value={connForm.gender} onChange={e => setConnForm({ ...connForm, gender: e.target.value as ConnectorGender })}
                  className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50">
                  {GENDERS.map(g => <option key={g} value={g}>{g.replace(/_/g, ' ')}</option>)}
                </select>
                <input type="number" value={connForm.total_contacts} onChange={e => setConnForm({ ...connForm, total_contacts: parseInt(e.target.value) || 0 })} placeholder="# contacts *"
                  className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
              </div>
              <div className="flex gap-2 justify-end">
                <button onClick={() => setShowAddConn(false)} className="rounded-lg border border-astra-border px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200">Cancel</button>
                <button onClick={handleAddConnector} disabled={savingConn || !connForm.designator.trim()}
                  className="flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-40">
                  {savingConn ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />} Create
                </button>
              </div>
            </div>
          )}

          {/* Connector list */}
          {unit.connectors.length === 0 ? (
            <div className="py-12 text-center text-sm text-slate-500">No connectors defined yet.</div>
          ) : unit.connectors.map(c => {
            const isExpanded = expandedConns.has(c.id);
            return (
              <div key={c.id} className="rounded-xl border border-astra-border bg-astra-surface overflow-hidden">
                {/* Header — click navigates to Connector Detail */}
                <div className="flex items-center gap-3 px-4 py-3 hover:bg-astra-surface-alt/50 transition">
                  {/* Expand chevron */}
                  <button onClick={e => { e.stopPropagation(); toggleConnExpand(c.id); }}
                    className="p-0.5 text-slate-500 hover:text-slate-300">
                    {isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                  </button>

                  {/* Info — click navigates */}
                  <div className="flex-1 min-w-0 cursor-pointer" onClick={() => router.push(`${p}/interfaces/connector/${c.id}`)}>
                    <div className="flex items-center gap-2">
                      <Cable className="h-4 w-4 text-blue-400 flex-shrink-0" />
                      <span className="font-mono text-xs font-bold text-blue-400">{c.designator}</span>
                      {c.name && <span className="text-[13px] text-slate-300">{c.name}</span>}
                      <span className="rounded-full bg-astra-surface-alt px-2 py-0.5 text-[9px] font-semibold text-slate-400 capitalize">{c.connector_type.replace(/_/g, ' ')}</span>
                      <span className="rounded-full bg-astra-surface-alt px-2 py-0.5 text-[9px] font-semibold text-slate-400 capitalize">{c.gender.replace(/_/g, ' ')}</span>
                    </div>
                    <div className="text-[10px] text-slate-500 mt-0.5">
                      {c.total_contacts} contacts{c.shell_size ? ` · Shell ${c.shell_size}` : ''}{c.mil_spec ? ` · ${c.mil_spec}` : ''}
                    </div>
                  </div>

                  <span className="rounded-full bg-astra-surface-alt px-2 py-0.5 text-[10px] font-bold text-slate-400">{c.pins?.length || 0} pins</span>

                  {/* Navigate arrow */}
                  <button onClick={() => router.push(`${p}/interfaces/connector/${c.id}`)}
                    className="p-1 text-slate-600 hover:text-blue-400 transition" title="Open connector">
                    <ChevronRight className="h-4 w-4" />
                  </button>

                  {/* Delete */}
                  {deleteConnId === c.id ? (
                    <div className="flex gap-1" onClick={e => e.stopPropagation()}>
                      <button onClick={() => handleDeleteConnector(c.id)} className="rounded p-1 text-red-400 hover:bg-red-500/10"><CheckCircle className="h-3.5 w-3.5" /></button>
                      <button onClick={() => setDeleteConnId(null)} className="rounded p-1 text-slate-500 hover:text-slate-300"><X className="h-3.5 w-3.5" /></button>
                    </div>
                  ) : (
                    <button onClick={e => { e.stopPropagation(); setDeleteConnId(c.id); }}
                      className="rounded p-1 text-slate-600 hover:text-red-400 transition" title="Delete connector">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>

                {/* Expanded: quick pin preview */}
                {isExpanded && c.pins && c.pins.length > 0 && (
                  <div className="border-t border-astra-border bg-astra-bg px-4 py-2">
                    <table className="w-full text-[11px]">
                      <thead>
                        <tr className="text-slate-500">
                          <th className="text-left py-1 w-12">Pin</th>
                          <th className="text-left py-1">Signal</th>
                          <th className="text-left py-1 w-28">Type</th>
                          <th className="text-left py-1 w-24">Direction</th>
                        </tr>
                      </thead>
                      <tbody>
                        {c.pins.slice(0, 10).map(pin => (
                          <tr key={pin.id} className="border-t border-astra-border/30">
                            <td className="py-1 font-mono font-bold text-slate-300">{pin.pin_number}</td>
                            <td className="py-1 text-slate-200">{pin.signal_name}</td>
                            <td className="py-1"><div className="flex items-center gap-1"><SignalDot type={pin.signal_type} /><span className="text-slate-400 capitalize">{pin.signal_type.replace(/_/g, ' ')}</span></div></td>
                            <td className="py-1 text-slate-400 capitalize">{pin.direction.replace(/_/g, ' ')}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {c.pins.length > 10 && <p className="text-[10px] text-slate-500 mt-1">+{c.pins.length - 10} more pins — click connector to view all</p>}
                  </div>
                )}
                {isExpanded && (!c.pins || c.pins.length === 0) && (
                  <div className="border-t border-astra-border bg-astra-bg px-4 py-3 text-[11px] text-slate-500">No pins defined. Open connector to add pins.</div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ══════════════════════════════════════════════════════ */}
      {/*  TAB 3 — COMMUNICATION                               */}
      {/* ══════════════════════════════════════════════════════ */}
      {tab === 'communication' && (
        <div className="space-y-3">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-semibold text-slate-400">{unit.bus_definitions.length} bus{unit.bus_definitions.length !== 1 ? 'es' : ''}</h3>
            <button onClick={() => setShowAddBus(true)}
              className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500">
              <Plus className="h-3.5 w-3.5" /> Add Bus
            </button>
          </div>

          {showAddBus && (
            <div className="rounded-xl border border-blue-500/20 bg-astra-surface p-4 mb-3 space-y-3">
              <h4 className="text-xs font-bold text-slate-400">New Bus Definition</h4>
              <div className="grid grid-cols-3 gap-3">
                <input value={busForm.name} onChange={e => setBusForm({ ...busForm, name: e.target.value })} placeholder="Bus name *"
                  className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
                <select value={busForm.bus_type} onChange={e => setBusForm({ ...busForm, bus_type: e.target.value as BusProtocol })}
                  className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50">
                  {BUS_TYPES.map(t => <option key={t} value={t}>{t.replace(/_/g, ' ').toUpperCase()}</option>)}
                </select>
                <input value={busForm.protocol_version} onChange={e => setBusForm({ ...busForm, protocol_version: e.target.value })} placeholder="Protocol version"
                  className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
              </div>
              <div className="flex gap-2 justify-end">
                <button onClick={() => setShowAddBus(false)} className="rounded-lg border border-astra-border px-3 py-1.5 text-xs text-slate-400">Cancel</button>
                <button onClick={handleAddBus} disabled={savingBus || !busForm.name.trim()}
                  className="flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-40">
                  {savingBus ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />} Create
                </button>
              </div>
            </div>
          )}

          {unit.bus_definitions.length === 0 ? (
            <div className="py-12 text-center text-sm text-slate-500">No buses defined yet.</div>
          ) : unit.bus_definitions.map(b => (
            <div key={b.id} className="rounded-xl border border-astra-border bg-astra-surface p-4">
              <div className="flex items-center gap-2 mb-2">
                <Radio className="h-4 w-4 text-violet-400" />
                <span className="font-semibold text-sm text-slate-200">{b.name}</span>
                <span className="rounded-full bg-violet-500/15 px-2 py-0.5 text-[10px] font-bold text-violet-400 uppercase">{b.protocol}</span>
                {b.bus_role && <span className="rounded-full bg-astra-surface-alt px-2 py-0.5 text-[9px] font-semibold text-slate-400 capitalize">{b.bus_role.replace(/_/g, ' ')}</span>}
                {b.bus_address && <span className="text-[10px] font-mono text-slate-500">Addr: {b.bus_address}</span>}
                {b.data_rate && <span className="text-[10px] text-slate-500">{b.data_rate}</span>}
              </div>

              {/* Pin assignments */}
              {b.pin_assignments && b.pin_assignments.length > 0 && (
                <div className="mb-2">
                  <span className="text-[10px] font-semibold text-slate-500">Pin Assignments: </span>
                  {b.pin_assignments.map(pa => (
                    <span key={pa.id} className="inline-flex items-center gap-1 mr-2 text-[10px]">
                      <span className="font-mono text-blue-400">{pa.connector_designator}:{pa.pin_number}</span>
                      <span className="text-slate-500 capitalize">({pa.pin_role.replace(/_/g, ' ')})</span>
                    </span>
                  ))}
                </div>
              )}

              {/* Messages */}
              {b.messages && b.messages.length > 0 && (
                <div className="mt-3 rounded-lg border border-astra-border/50 overflow-hidden">
                  <table className="w-full text-[11px]">
                    <thead>
                      <tr className="bg-astra-surface-alt">
                        <th className="text-left px-3 py-1.5 font-semibold text-slate-500">Label</th>
                        <th className="text-left px-3 py-1.5 font-semibold text-slate-500">Mnemonic</th>
                        <th className="text-left px-3 py-1.5 font-semibold text-slate-500">Direction</th>
                        <th className="text-left px-3 py-1.5 font-semibold text-slate-500">Rate</th>
                        <th className="text-left px-3 py-1.5 font-semibold text-slate-500">Words</th>
                        <th className="text-left px-3 py-1.5 font-semibold text-slate-500">Fields</th>
                      </tr>
                    </thead>
                    <tbody>
                      {b.messages.map(m => (
                        <tr key={m.id} className="border-t border-astra-border/30">
                          <td className="px-3 py-1.5 font-semibold text-slate-200">{m.label}</td>
                          <td className="px-3 py-1.5 font-mono text-slate-400">{m.mnemonic || '—'}</td>
                          <td className="px-3 py-1.5 text-slate-400 capitalize">{m.direction.replace(/_/g, ' ')}</td>
                          <td className="px-3 py-1.5 text-slate-400">{m.rate_hz ? `${m.rate_hz} Hz` : '—'}</td>
                          <td className="px-3 py-1.5 text-slate-400">{m.word_count ?? '—'}</td>
                          <td className="px-3 py-1.5 text-slate-400">{m.field_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {(!b.messages || b.messages.length === 0) && (
                <p className="text-[10px] text-slate-500 mt-1">No messages defined on this bus.</p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ══════════════════════════════════════════════════════ */}
      {/*  TAB 4 — SPECIFICATIONS                              */}
      {/* ══════════════════════════════════════════════════════ */}
      {tab === 'specifications' && (
        <div>
          {editingSpecs ? (
            <div className="rounded-xl border border-blue-500/20 bg-astra-surface p-5 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Edit Specifications</h3>
                <div className="flex gap-2">
                  <button onClick={() => setEditingSpecs(false)} className="rounded-lg border border-astra-border px-3 py-1.5 text-xs text-slate-400">Cancel</button>
                  <button onClick={saveSpecs} disabled={savingSpecs}
                    className="flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-40">
                    {savingSpecs ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />} Save
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-6">
                <div>
                  <h4 className="text-[10px] font-bold text-slate-500 mb-2">THERMAL</h4>
                  {[
                    { f: 'temp_operating_min_c', l: 'Operating Min', u: '°C' }, { f: 'temp_operating_max_c', l: 'Operating Max', u: '°C' },
                    { f: 'temp_storage_min_c', l: 'Storage Min', u: '°C' }, { f: 'temp_storage_max_c', l: 'Storage Max', u: '°C' },
                    { f: 'temp_survival_min_c', l: 'Survival Min', u: '°C' }, { f: 'temp_survival_max_c', l: 'Survival Max', u: '°C' },
                  ].map(r => <EditRow key={r.f} label={r.l} field={r.f} value={specFields[r.f]} onChange={onSpecField} type="number" unit={r.u} />)}
                  <h4 className="text-[10px] font-bold text-slate-500 mt-3 mb-2">MECHANICAL</h4>
                  {[
                    { f: 'vibration_random_grms', l: 'Vibration Random', u: 'Grms' }, { f: 'vibration_sine_g_peak', l: 'Vibration Sine', u: 'G' },
                    { f: 'shock_mechanical_g', l: 'Shock Mech', u: 'G' }, { f: 'shock_pyrotechnic_g', l: 'Shock Pyro', u: 'G' },
                    { f: 'acceleration_max_g', l: 'Acceleration', u: 'G' }, { f: 'acoustic_spl_db', l: 'Acoustic SPL', u: 'dB' },
                  ].map(r => <EditRow key={r.f} label={r.l} field={r.f} value={specFields[r.f]} onChange={onSpecField} type="number" unit={r.u} />)}
                </div>
                <div>
                  <h4 className="text-[10px] font-bold text-slate-500 mb-2">EMI EMISSIONS</h4>
                  {[
                    { f: 'emi_ce101_limit_dba', l: 'CE101', u: 'dBa' }, { f: 'emi_ce102_limit_dbua', l: 'CE102', u: 'dBμA' },
                    { f: 'emi_re102_limit_dbm', l: 'RE102', u: 'dBm' },
                  ].map(r => <EditRow key={r.f} label={r.l} field={r.f} value={specFields[r.f]} onChange={onSpecField} type="number" unit={r.u} />)}
                  <h4 className="text-[10px] font-bold text-slate-500 mt-3 mb-2">EMI SUSCEPTIBILITY</h4>
                  {[
                    { f: 'emi_cs101_limit_db', l: 'CS101', u: 'dB' }, { f: 'emi_rs103_limit_vm', l: 'RS103', u: 'V/m' },
                    { f: 'esd_hbm_v', l: 'ESD HBM', u: 'V' },
                  ].map(r => <EditRow key={r.f} label={r.l} field={r.f} value={specFields[r.f]} onChange={onSpecField} type="number" unit={r.u} />)}
                  <h4 className="text-[10px] font-bold text-slate-500 mt-3 mb-2">RADIATION</h4>
                  {[
                    { f: 'radiation_tid_krad', l: 'TID', u: 'krad' }, { f: 'radiation_see_let_threshold', l: 'SEE LET', u: 'MeV·cm²/mg' },
                  ].map(r => <EditRow key={r.f} label={r.l} field={r.f} value={specFields[r.f]} onChange={onSpecField} type="number" unit={r.u} />)}
                </div>
              </div>
            </div>
          ) : (
            <div className="relative">
              <button onClick={startEditSpecs}
                className="absolute top-4 right-4 flex items-center gap-1 rounded-lg border border-astra-border px-3 py-1.5 text-xs text-slate-400 hover:text-blue-400 hover:border-blue-500/30 z-10">
                <Edit3 className="h-3 w-3" /> Edit Specifications
              </button>
              <div className="grid grid-cols-2 gap-6">
                <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
                  <h3 className="text-xs font-bold text-slate-400 mb-3">THERMAL</h3>
                  <SpecRow label="Operating Temp Min" value={unit.temp_operating_min_c} unit="°C" />
                  <SpecRow label="Operating Temp Max" value={unit.temp_operating_max_c} unit="°C" />
                  <SpecRow label="Storage Temp Min" value={unit.temp_storage_min_c} unit="°C" />
                  <SpecRow label="Storage Temp Max" value={unit.temp_storage_max_c} unit="°C" />
                  <SpecRow label="Survival Temp Min" value={unit.temp_survival_min_c} unit="°C" />
                  <SpecRow label="Survival Temp Max" value={unit.temp_survival_max_c} unit="°C" />
                  <h3 className="text-xs font-bold text-slate-400 mt-4 mb-3">MECHANICAL</h3>
                  <SpecRow label="Vibration Random" value={unit.vibration_random_grms} unit="Grms" />
                  <SpecRow label="Vibration Sine" value={unit.vibration_sine_g_peak} unit="G pk" />
                  <SpecRow label="Shock Mechanical" value={unit.shock_mechanical_g} unit="G" />
                  <SpecRow label="Shock Pyro" value={unit.shock_pyrotechnic_g} unit="G" />
                  <SpecRow label="Acceleration" value={unit.acceleration_max_g} unit="G" />
                  <SpecRow label="Acoustic SPL" value={unit.acoustic_spl_db} unit="dB" />
                </div>
                <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
                  <h3 className="text-xs font-bold text-slate-400 mb-3">EMI EMISSIONS</h3>
                  <SpecRow label="CE101" value={unit.emi_ce101_limit_dba} unit="dBa" />
                  <SpecRow label="CE102" value={unit.emi_ce102_limit_dbua} unit="dBμA" />
                  <SpecRow label="RE101" value={unit.emi_re101_limit_dba} unit="dBa" />
                  <SpecRow label="RE102" value={unit.emi_re102_limit_dbm} unit="dBm" />
                  <h3 className="text-xs font-bold text-slate-400 mt-4 mb-3">EMI SUSCEPTIBILITY</h3>
                  <SpecRow label="CS101" value={unit.emi_cs101_limit_db} unit="dB" />
                  <SpecRow label="CS114" value={unit.emi_cs114_limit_dba} unit="dBa" />
                  <SpecRow label="CS116" value={unit.emi_cs116_limit_db} unit="dB" />
                  <SpecRow label="RS101" value={unit.emi_rs101_limit_db} unit="dB" />
                  <SpecRow label="RS103" value={unit.emi_rs103_limit_vm} unit="V/m" />
                  <SpecRow label="ESD HBM" value={unit.esd_hbm_v} unit="V" />
                  <SpecRow label="ESD CDM" value={unit.esd_cdm_v} unit="V" />
                  <h3 className="text-xs font-bold text-slate-400 mt-4 mb-3">RADIATION</h3>
                  <SpecRow label="TID" value={unit.radiation_tid_krad} unit="krad" />
                  <SpecRow label="SEE LET Threshold" value={unit.radiation_see_let_threshold} unit="MeV·cm²/mg" />
                  <SpecRow label="Displacement Damage" value={unit.radiation_dd_mev_cm2_g} unit="MeV·cm²/g" />
                </div>
              </div>

              {/* Environmental Test Specs table */}
              {unit.environmental_specs.length > 0 && (
                <div className="mt-5 rounded-xl border border-astra-border bg-astra-surface p-4">
                  <h3 className="text-xs font-bold text-slate-400 mb-3">ENVIRONMENTAL TEST SPECS ({unit.environmental_specs.length})</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-[11px]">
                      <thead>
                        <tr className="border-b border-astra-border">
                          <th className="text-left py-2 px-2 text-slate-500 font-semibold">Category</th>
                          <th className="text-left py-2 px-2 text-slate-500 font-semibold">Standard</th>
                          <th className="text-left py-2 px-2 text-slate-500 font-semibold">Test Method</th>
                          <th className="text-left py-2 px-2 text-slate-500 font-semibold">Test Level</th>
                          <th className="text-left py-2 px-2 text-slate-500 font-semibold">Limit</th>
                          <th className="text-left py-2 px-2 text-slate-500 font-semibold">Range</th>
                          <th className="text-left py-2 px-2 text-slate-500 font-semibold">Status</th>
                          <th className="text-left py-2 px-2 text-slate-500 font-semibold">Report</th>
                        </tr>
                      </thead>
                      <tbody>
                        {unit.environmental_specs.map(s => (
                          <tr key={s.id} className="border-b border-astra-border/50 hover:bg-astra-surface-alt/30">
                            <td className="py-1.5 px-2 text-slate-300 capitalize">{s.category.replace(/_/g, ' ')}</td>
                            <td className="py-1.5 px-2 text-slate-400">{s.standard?.replace(/_/g, ' ') || '—'}</td>
                            <td className="py-1.5 px-2 text-slate-400">{s.test_method || '—'}</td>
                            <td className="py-1.5 px-2 text-slate-400">{s.test_level || '—'}</td>
                            <td className="py-1.5 px-2 text-slate-400 font-mono">{s.limit_value != null ? `${s.limit_value} ${s.limit_unit || ''}` : '—'}</td>
                            <td className="py-1.5 px-2 text-slate-400 font-mono">
                              {s.limit_min != null || s.limit_max != null ? `${s.limit_min ?? '—'} to ${s.limit_max ?? '—'}` : '—'}
                            </td>
                            <td className="py-1.5 px-2">
                              <span className={clsx('capitalize text-[10px] font-semibold',
                                s.compliance_status === 'pass' ? 'text-emerald-400' :
                                s.compliance_status === 'fail' ? 'text-red-400' :
                                s.compliance_status === 'waived' ? 'text-yellow-400' : 'text-slate-500'
                              )}>{s.compliance_status || 'untested'}</span>
                            </td>
                            <td className="py-1.5 px-2 text-slate-500 truncate max-w-[100px]">{s.test_report_ref || '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* TDD-SYSARCH-002 §6.2 — link picker modal */}
      {showLinkPicker && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Link unit to a catalog part"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
          onClick={(e) => { if (e.target === e.currentTarget) setShowLinkPicker(false); }}
        >
          <div className="w-full max-w-lg rounded-xl border border-astra-border bg-astra-surface p-5 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-base font-bold text-slate-100">Link to catalog part</h2>
              <button
                type="button"
                onClick={() => setShowLinkPicker(false)}
                disabled={linkSaving}
                aria-label="Close"
                className="rounded p-1 text-slate-400 hover:bg-astra-surface-alt hover:text-slate-200"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            {linkError && (
              <div role="alert" className="mb-3 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
                {linkError}
              </div>
            )}
            <CatalogPartPicker
              label="Catalog part"
              value={null}
              onChange={handleLinkCatalog}
              allowedClasses={[
                'processor', 'sensor', 'power_supply', 'radio', 'antenna', 'actuator',
                'display', 'harness', 'connector_only', 'compute_module',
                'power_distribution', 'interface_card', 'other',
              ] as PartClass[]}
              placeholder="Search and pick a catalog part…"
              disabled={linkSaving}
            />
            <p className="mt-2 text-[10px] text-slate-500">
              Picking a part links this unit; the change is recorded in the audit log.
            </p>
          </div>
        </div>
      )}

      {/* TDD-SYSARCH-002 §6.2 — unlink confirmation */}
      {showUnlinkConfirm && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Unlink unit from catalog"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
          onClick={(e) => { if (e.target === e.currentTarget) setShowUnlinkConfirm(false); }}
        >
          <div className="w-full max-w-md rounded-xl border border-astra-border bg-astra-surface p-5 shadow-2xl">
            <h2 className="text-base font-bold text-slate-100">Unlink from catalog?</h2>
            <p className="mt-2 text-[12px] text-slate-300">
              The unit will keep its current field values, but they&apos;ll no longer
              be sourced from a CatalogPart. The change is recorded in the audit log.
            </p>
            {linkError && (
              <div role="alert" className="mt-3 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
                {linkError}
              </div>
            )}
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowUnlinkConfirm(false)}
                disabled={linkSaving}
                className="rounded border border-astra-border px-3 py-1.5 text-xs text-slate-300 hover:bg-astra-surface-alt"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleUnlinkCatalog}
                disabled={linkSaving}
                className="flex items-center gap-1.5 rounded bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-500 disabled:opacity-50"
              >
                {linkSaving && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
                Unlink
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
