'use client';

/**
 * ASTRA — Unit Detail Page
 * ===========================
 * File: frontend/src/app/projects/[id]/interfaces/[unitId]/page.tsx
 * Path: C:\Users\Mason\Documents\ASTRA\frontend\src\app\projects\[id]\interfaces\[unitId]\page.tsx
 *
 * Tabs: [Overview] [Connectors] [Communication] [Specifications]
 */

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft, Loader2, Edit3, Save, X, Plus, Cpu, Box,
  Cable, Radio, Zap, ChevronRight, ChevronDown, Trash2,
  RefreshCw, Copy, Download, Wifi, Thermometer, Shield,
} from 'lucide-react';
import clsx from 'clsx';
import { interfaceAPI, downloadBlob } from '@/lib/interface-api';
import type {
  UnitDetail, ConnectorWithPins, Pin, BusWithMessages, MessageSummary,
  UnitEnvironmentalSpec, PinBusAssignment,
} from '@/lib/interface-types';
import { SIGNAL_TYPE_COLORS } from '@/lib/interface-types';

type Tab = 'overview' | 'connectors' | 'communication' | 'specifications';

// ── Signal type color dot ──
function SignalDot({ type }: { type: string }) {
  const color = SIGNAL_TYPE_COLORS[type] || '#475569';
  return <div className="h-2 w-2 rounded-full flex-shrink-0" style={{ background: color }} />;
}

// ── Spec row ──
function SpecRow({ label, value, unit: u }: { label: string; value: any; unit?: string }) {
  if (value === null || value === undefined) return null;
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-astra-border/50">
      <span className="text-[11px] text-slate-500">{label}</span>
      <span className="text-[12px] font-semibold text-slate-300">{value}{u ? ` ${u}` : ''}</span>
    </div>
  );
}

// ══════════════════════════════════════
//  Main Page
// ══════════════════════════════════════

export default function UnitDetailPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);
  const unitId = Number(params.unitId);
  const p = `/projects/${projectId}`;

  const [unit, setUnit] = useState<UnitDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>('overview');
  const [expandedConn, setExpandedConn] = useState<Set<number>>(new Set());

  const fetchUnit = useCallback(async () => {
    setLoading(true);
    try {
      const res = await interfaceAPI.getUnit(unitId);
      setUnit(res.data);
    } catch { }
    setLoading(false);
  }, [unitId]);

  useEffect(() => { fetchUnit(); }, [fetchUnit]);

  if (loading) return <div className="flex items-center justify-center py-24"><Loader2 className="h-6 w-6 animate-spin text-blue-500" /></div>;
  if (!unit) return <div className="py-24 text-center text-slate-500">Unit not found</div>;

  const toggleConn = (id: number) => {
    setExpandedConn(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const totalPins = unit.connectors.reduce((s, c) => s + c.pins.length, 0);
  const totalMsgs = unit.bus_definitions.reduce((s, b) => s + b.messages.length, 0);

  return (
    <div>
      {/* Back + header */}
      <button onClick={() => router.push(`${p}/interfaces`)}
        className="mb-4 flex items-center gap-1.5 text-[11px] text-slate-500 hover:text-blue-400 transition">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to Interface Management
      </button>

      <div className="mb-6 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <span className="font-mono text-lg font-bold text-blue-400">{unit.designation}</span>
            <span className="text-lg font-semibold text-slate-200">{unit.name}</span>
          </div>
          <div className="flex items-center gap-3 text-[11px] text-slate-500">
            <span>{unit.manufacturer}</span>
            <span>·</span>
            <span>{unit.part_number}</span>
            <span>·</span>
            <span className="capitalize">{unit.unit_type.replace(/_/g, ' ')}</span>
            <span>·</span>
            <span className="capitalize rounded-full bg-astra-surface-alt px-2 py-0.5 text-[10px]">{unit.status.replace(/_/g, ' ')}</span>
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={fetchUnit} className="rounded-lg border border-astra-border p-2 text-slate-500 hover:text-slate-300">
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Quick stats */}
      <div className="mb-5 grid grid-cols-5 gap-3">
        {[
          { label: 'Connectors', value: unit.connector_count, color: '#3B82F6' },
          { label: 'Pins', value: totalPins, color: '#06B6D4' },
          { label: 'Buses', value: unit.bus_count, color: '#8B5CF6' },
          { label: 'Messages', value: totalMsgs, color: '#10B981' },
          { label: 'Env Specs', value: unit.environmental_specs.length, color: '#F59E0B' },
        ].map(s => (
          <div key={s.label} className="rounded-xl border border-astra-border bg-astra-surface p-3 text-center">
            <div className="text-xl font-bold" style={{ color: s.color }}>{s.value}</div>
            <div className="text-[10px] text-slate-500">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
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

      {/* ════════════ OVERVIEW TAB ════════════ */}
      {tab === 'overview' && (
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
          </div>
          <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
            <h3 className="text-xs font-bold text-slate-400 mb-3">PHYSICAL</h3>
            <SpecRow label="Mass" value={unit.mass_kg} unit="kg" />
            <SpecRow label="Max Mass" value={unit.mass_max_kg} unit="kg" />
            <SpecRow label="Dimensions (L×W×H)" value={unit.dimensions_l_mm && `${unit.dimensions_l_mm} × ${unit.dimensions_w_mm} × ${unit.dimensions_h_mm}`} unit="mm" />
            <h3 className="text-xs font-bold text-slate-400 mt-4 mb-3">ELECTRICAL</h3>
            <SpecRow label="Power (nominal)" value={unit.power_watts_nominal} unit="W" />
            <SpecRow label="Power (peak)" value={unit.power_watts_peak} unit="W" />
            <SpecRow label="Voltage Input" value={unit.voltage_input_nominal} />
            <SpecRow label="Voltage Range" value={unit.voltage_input_min !== undefined && unit.voltage_input_max !== undefined ? `${unit.voltage_input_min} – ${unit.voltage_input_max}` : null} unit="V" />
            <SpecRow label="Inrush Current" value={unit.current_inrush_amps} unit="A" />
            <h3 className="text-xs font-bold text-slate-400 mt-4 mb-3">RELIABILITY</h3>
            <SpecRow label="MTBF" value={unit.mtbf_hours} unit="hrs" />
            <SpecRow label="Design Life" value={unit.design_life_years} unit="yrs" />
            <SpecRow label="Duty Cycle" value={unit.duty_cycle_pct} unit="%" />
          </div>
        </div>
      )}

      {/* ════════════ CONNECTORS TAB ════════════ */}
      {tab === 'connectors' && (
        <div className="space-y-3">
          {unit.connectors.length === 0 ? (
            <div className="py-12 text-center text-sm text-slate-500">No connectors defined yet</div>
          ) : unit.connectors.map(c => (
            <div key={c.id} className="rounded-xl border border-astra-border bg-astra-surface overflow-hidden">
              {/* Connector header */}
              <button onClick={() => toggleConn(c.id)}
                className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-astra-surface-hover transition">
                <Cable className="h-4 w-4 text-blue-400 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-blue-400">{c.designator}</span>
                    {c.name && <span className="text-[13px] text-slate-300">{c.name}</span>}
                  </div>
                  <div className="text-[10px] text-slate-500">
                    {c.connector_type.replace(/_/g, ' ')} · {c.gender.replace(/_/g, ' ')} · {c.total_contacts} contacts
                    {c.shell_size && ` · Shell ${c.shell_size}`}
                    {c.mil_spec && ` · ${c.mil_spec}`}
                  </div>
                </div>
                <span className="rounded-full bg-astra-surface-alt px-2 py-0.5 text-[10px] font-bold text-slate-400">
                  {c.pin_count} pins
                </span>
                {expandedConn.has(c.id) ? <ChevronDown className="h-4 w-4 text-slate-500" /> : <ChevronRight className="h-4 w-4 text-slate-500" />}
              </button>

              {/* Pin table */}
              {expandedConn.has(c.id) && (
                <div className="border-t border-astra-border">
                  <table className="w-full text-[11px]">
                    <thead>
                      <tr className="bg-astra-surface-alt">
                        {['Pin', 'Label', 'Signal Name', 'Type', 'Direction', 'Voltage', 'Current', 'Impedance', 'Bus'].map(h => (
                          <th key={h} className="px-3 py-2 text-left font-semibold text-slate-500">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {c.pins.map(pin => (
                        <tr key={pin.id} className="border-t border-astra-border/50 hover:bg-astra-surface-hover transition">
                          <td className="px-3 py-1.5 font-mono font-bold text-slate-300">{pin.pin_number}</td>
                          <td className="px-3 py-1.5 text-slate-400">{pin.pin_label || '—'}</td>
                          <td className="px-3 py-1.5">
                            <div className="flex items-center gap-1.5">
                              <SignalDot type={pin.signal_type} />
                              <span className="font-semibold text-slate-200">{pin.signal_name}</span>
                            </div>
                          </td>
                          <td className="px-3 py-1.5 text-slate-400 capitalize">{pin.signal_type.replace(/_/g, ' ')}</td>
                          <td className="px-3 py-1.5 text-slate-400 capitalize">{pin.direction.replace(/_/g, ' ')}</td>
                          <td className="px-3 py-1.5 text-slate-400">{pin.voltage_nominal || '—'}</td>
                          <td className="px-3 py-1.5 text-slate-400">{pin.current_max_amps ? `${pin.current_max_amps}A` : '—'}</td>
                          <td className="px-3 py-1.5 text-slate-400">{pin.impedance_ohms ? `${pin.impedance_ohms}Ω` : '—'}</td>
                          <td className="px-3 py-1.5">
                            {pin.bus_assignment ? (
                              <span className="rounded-full bg-violet-500/15 px-2 py-0.5 text-[9px] font-bold text-violet-400">
                                {pin.bus_assignment.pin_role.replace(/_/g, ' ')}
                              </span>
                            ) : <span className="text-slate-600">—</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ════════════ COMMUNICATION TAB ════════════ */}
      {tab === 'communication' && (
        <div className="space-y-4">
          {unit.bus_definitions.length === 0 ? (
            <div className="py-12 text-center text-sm text-slate-500">No bus definitions yet</div>
          ) : unit.bus_definitions.map(bus => (
            <div key={bus.id} className="rounded-xl border border-astra-border bg-astra-surface p-4">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <div className="flex items-center gap-2">
                    <Wifi className="h-4 w-4 text-violet-400" />
                    <span className="text-sm font-bold text-slate-200">{bus.name}</span>
                    <span className="rounded-full bg-violet-500/15 px-2 py-0.5 text-[10px] font-bold text-violet-400">
                      {bus.protocol.replace(/_/g, '-').toUpperCase()}
                    </span>
                  </div>
                  <div className="mt-1 text-[10px] text-slate-500">
                    Role: {bus.bus_role.replace(/_/g, ' ')}
                    {bus.bus_address && ` · Addr: ${bus.bus_address}`}
                    {bus.data_rate && ` · ${bus.data_rate}`}
                    {bus.bus_name_network && ` · Network: ${bus.bus_name_network}`}
                  </div>
                </div>
                <span className="rounded-full bg-astra-surface-alt px-2 py-0.5 text-[10px] font-bold text-slate-400">
                  {bus.message_count} msgs
                </span>
              </div>

              {/* Pin assignments */}
              {bus.pin_assignments.length > 0 && (
                <div className="mb-3">
                  <div className="text-[10px] font-semibold text-slate-500 mb-1">PIN ASSIGNMENTS</div>
                  <div className="flex flex-wrap gap-1.5">
                    {bus.pin_assignments.map(pa => (
                      <span key={pa.id} className="rounded border border-astra-border bg-astra-bg px-2 py-0.5 text-[10px] text-slate-400">
                        {pa.connector_designator}:{pa.pin_number} ({pa.pin_role.replace(/_/g, ' ')})
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Messages */}
              {bus.messages.length > 0 && (
                <div className="border-t border-astra-border pt-3">
                  <div className="text-[10px] font-semibold text-slate-500 mb-2">MESSAGES</div>
                  <table className="w-full text-[11px]">
                    <thead>
                      <tr className="text-left text-slate-500">
                        <th className="pb-1 pr-3">Label</th>
                        <th className="pb-1 pr-3">Mnemonic</th>
                        <th className="pb-1 pr-3">Direction</th>
                        <th className="pb-1 pr-3">Rate</th>
                        <th className="pb-1 pr-3">Words</th>
                        <th className="pb-1">Fields</th>
                      </tr>
                    </thead>
                    <tbody>
                      {bus.messages.map(msg => (
                        <tr key={msg.id} className="border-t border-astra-border/30 hover:bg-astra-surface-hover cursor-pointer">
                          <td className="py-1.5 pr-3 font-semibold text-slate-200">{msg.label}</td>
                          <td className="py-1.5 pr-3 font-mono text-slate-400">{msg.mnemonic || '—'}</td>
                          <td className="py-1.5 pr-3 capitalize text-slate-400">{msg.direction}</td>
                          <td className="py-1.5 pr-3 text-slate-400">{msg.rate_hz ? `${msg.rate_hz} Hz` : '—'}</td>
                          <td className="py-1.5 pr-3 text-slate-400">{msg.word_count || '—'}</td>
                          <td className="py-1.5 text-slate-400">{msg.field_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ════════════ SPECIFICATIONS TAB ════════════ */}
      {tab === 'specifications' && (
        <div className="grid grid-cols-2 gap-4">
          {/* Thermal */}
          <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
            <h3 className="text-xs font-bold text-orange-400 mb-3 flex items-center gap-1.5">
              <Thermometer className="h-3.5 w-3.5" /> THERMAL
            </h3>
            <SpecRow label="Operating Temp" value={unit.temp_operating_min_c !== undefined && unit.temp_operating_max_c !== undefined ? `${unit.temp_operating_min_c} to ${unit.temp_operating_max_c}` : null} unit="°C" />
            <SpecRow label="Storage Temp" value={unit.temp_storage_min_c !== undefined && unit.temp_storage_max_c !== undefined ? `${unit.temp_storage_min_c} to ${unit.temp_storage_max_c}` : null} unit="°C" />
            <SpecRow label="Survival Temp" value={unit.temp_survival_min_c !== undefined && unit.temp_survival_max_c !== undefined ? `${unit.temp_survival_min_c} to ${unit.temp_survival_max_c}` : null} unit="°C" />
          </div>
          {/* Mechanical */}
          <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
            <h3 className="text-xs font-bold text-blue-400 mb-3 flex items-center gap-1.5">
              <Zap className="h-3.5 w-3.5" /> MECHANICAL
            </h3>
            <SpecRow label="Random Vibration" value={unit.vibration_random_grms} unit="Grms" />
            <SpecRow label="Sine Vibration" value={unit.vibration_sine_g_peak} unit="g peak" />
            <SpecRow label="Mechanical Shock" value={unit.shock_mechanical_g} unit="g" />
            <SpecRow label="Pyroshock" value={unit.shock_pyrotechnic_g} unit="g" />
            <SpecRow label="Acceleration" value={unit.acceleration_max_g} unit="g" />
            <SpecRow label="Acoustic" value={unit.acoustic_spl_db} unit="dB SPL" />
          </div>
          {/* EMI Emissions */}
          <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
            <h3 className="text-xs font-bold text-red-400 mb-3 flex items-center gap-1.5">
              <Radio className="h-3.5 w-3.5" /> EMI EMISSIONS
            </h3>
            <SpecRow label="CE102" value={unit.emi_ce102_limit_dbua} unit="dBμA" />
            <SpecRow label="RE102" value={unit.emi_re102_limit_dbm} unit="dBμV/m" />
          </div>
          {/* EMI Susceptibility */}
          <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
            <h3 className="text-xs font-bold text-yellow-400 mb-3 flex items-center gap-1.5">
              <Shield className="h-3.5 w-3.5" /> EMI SUSCEPTIBILITY
            </h3>
            <SpecRow label="CS114" value={unit.emi_cs114_limit_dba} unit="dBA" />
            <SpecRow label="RS103" value={unit.emi_rs103_limit_vm} unit="V/m" />
            <SpecRow label="ESD HBM" value={unit.esd_hbm_v} unit="V" />
            <SpecRow label="ESD CDM" value={unit.esd_cdm_v} unit="V" />
          </div>
          {/* Radiation */}
          {(unit.radiation_tid_krad || unit.radiation_see_let_threshold) && (
            <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
              <h3 className="text-xs font-bold text-purple-400 mb-3">RADIATION</h3>
              <SpecRow label="TID" value={unit.radiation_tid_krad} unit="krad(Si)" />
              <SpecRow label="SEE LET" value={unit.radiation_see_let_threshold} unit="MeV·cm²/mg" />
              <SpecRow label="Displacement Damage" value={unit.radiation_dd_mev_cm2_g} />
            </div>
          )}
          {/* Environmental Spec Records */}
          {unit.environmental_specs.length > 0 && (
            <div className="col-span-2 rounded-xl border border-astra-border bg-astra-surface p-4">
              <h3 className="text-xs font-bold text-emerald-400 mb-3">ENVIRONMENTAL TEST SPECS ({unit.environmental_specs.length})</h3>
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-left text-slate-500">
                    <th className="pb-2 pr-3">Category</th>
                    <th className="pb-2 pr-3">Standard</th>
                    <th className="pb-2 pr-3">Method</th>
                    <th className="pb-2 pr-3">Value</th>
                    <th className="pb-2 pr-3">Range</th>
                    <th className="pb-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {unit.environmental_specs.map(es => (
                    <tr key={es.id} className="border-t border-astra-border/30">
                      <td className="py-1.5 pr-3 capitalize text-slate-300">{es.category.replace(/_/g, ' ')}</td>
                      <td className="py-1.5 pr-3 text-slate-400">{es.standard || '—'}</td>
                      <td className="py-1.5 pr-3 text-slate-400">{es.test_method || '—'}</td>
                      <td className="py-1.5 pr-3 font-mono text-slate-300">{es.limit_value ?? '—'} {es.limit_unit || ''}</td>
                      <td className="py-1.5 pr-3 text-slate-400">
                        {es.limit_min !== null && es.limit_max !== null ? `${es.limit_min} – ${es.limit_max}` : '—'}
                      </td>
                      <td className="py-1.5">
                        <span className={clsx('rounded-full px-2 py-0.5 text-[9px] font-bold capitalize',
                          es.compliance_status === 'pass' ? 'bg-emerald-500/15 text-emerald-400' :
                          es.compliance_status === 'fail' ? 'bg-red-500/15 text-red-400' :
                          'bg-astra-surface-alt text-slate-500')}>
                          {es.compliance_status || 'untested'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
