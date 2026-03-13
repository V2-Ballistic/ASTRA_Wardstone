'use client';

/**
 * ASTRA — Harness Detail Page
 * ===============================
 * File: frontend/src/app/projects/[id]/interfaces/harness/[harnessId]/page.tsx
 * Path: C:\Users\Mason\Documents\ASTRA\frontend\src\app\projects\[id]\interfaces\harness\[harnessId]\page.tsx
 *
 * Shows harness metadata, wire table, auto-wire results, pin mapping,
 * and export controls.
 */

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft, Loader2, Plus, Cable, ArrowRight, RefreshCw,
  Download, Zap, CheckCircle, AlertTriangle, Sparkles,
  ChevronRight, Radio, Shield, Power,
} from 'lucide-react';
import clsx from 'clsx';
import { interfaceAPI, downloadBlob } from '@/lib/interface-api';
import type { WireHarnessDetail, Wire } from '@/lib/interface-types';
import { SIGNAL_TYPE_COLORS } from '@/lib/interface-types';

// ── Wire type color ──
function WireColor({ type }: { type: string }) {
  const color = type.startsWith('power') ? '#EF4444' :
                type.startsWith('ground') ? '#6B7280' :
                type.startsWith('shield') ? '#A78BFA' :
                type.startsWith('coax') ? '#F59E0B' :
                type.startsWith('fiber') ? '#06B6D4' : '#3B82F6';
  return <div className="h-2 w-2 rounded-full flex-shrink-0" style={{ background: color }} />;
}

type ViewMode = 'wires' | 'pinmap' | 'signals';

export default function HarnessDetailPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);
  const harnessId = Number(params.harnessId);
  const p = `/projects/${projectId}`;

  const [harness, setHarness] = useState<WireHarnessDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<ViewMode>('wires');
  const [autoWiring, setAutoWiring] = useState(false);
  const [autoWireResult, setAutoWireResult] = useState<any>(null);

  const fetchHarness = useCallback(async () => {
    setLoading(true);
    try {
      const res = await interfaceAPI.getHarness(harnessId);
      setHarness(res.data);
    } catch { }
    setLoading(false);
  }, [harnessId]);

  useEffect(() => { fetchHarness(); }, [fetchHarness]);

  const handleAutoWire = async () => {
    setAutoWiring(true);
    setAutoWireResult(null);
    try {
      const res = await interfaceAPI.autoWire(harnessId);
      setAutoWireResult(res.data);
      fetchHarness();
    } catch { }
    setAutoWiring(false);
  };

  const handleExport = async () => {
    try {
      const res = await interfaceAPI.exportHarness(harnessId);
      downloadBlob(res, `harness_${harnessId}.xlsx`);
    } catch { }
  };

  if (loading) return <div className="flex items-center justify-center py-24"><Loader2 className="h-6 w-6 animate-spin text-blue-500" /></div>;
  if (!harness) return <div className="py-24 text-center text-slate-500">Harness not found</div>;

  // Group wires by type for signal view
  const wiresByType = new Map<string, Wire[]>();
  for (const w of harness.wires) {
    const t = w.wire_type;
    if (!wiresByType.has(t)) wiresByType.set(t, []);
    wiresByType.get(t)!.push(w);
  }

  return (
    <div>
      {/* Back */}
      <button onClick={() => router.push(`${p}/interfaces`)}
        className="mb-4 flex items-center gap-1.5 text-[11px] text-slate-500 hover:text-blue-400 transition">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to Interface Management
      </button>

      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <Cable className="h-5 w-5 text-emerald-400" />
            <span className="text-lg font-bold text-slate-200">{harness.name}</span>
            {harness.harness_id && <span className="font-mono text-sm text-slate-500">({harness.harness_id})</span>}
          </div>
          <div className="flex items-center gap-2 text-[11px] text-slate-500 mt-1">
            <span className="font-semibold text-slate-300">{harness.from_unit_designation}</span>
            <span>({harness.from_connector_designator})</span>
            <ArrowRight className="h-3 w-3 text-blue-400" />
            <span className="font-semibold text-slate-300">{harness.to_unit_designation}</span>
            <span>({harness.to_connector_designator})</span>
            {harness.cable_type && <><span>·</span><span>{harness.cable_type}</span></>}
            {harness.overall_length_m && <><span>·</span><span>{harness.overall_length_m}m</span></>}
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={handleAutoWire} disabled={autoWiring}
            className="flex items-center gap-1.5 rounded-lg border border-violet-500/30 bg-violet-500/10 px-4 py-2 text-xs font-semibold text-violet-400 hover:bg-violet-500/20 disabled:opacity-50">
            {autoWiring ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />} Auto-Wire
          </button>
          <button onClick={handleExport}
            className="flex items-center gap-1.5 rounded-lg border border-astra-border px-3 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200">
            <Download className="h-3.5 w-3.5" /> Export
          </button>
          <button onClick={fetchHarness} className="rounded-lg border border-astra-border p-2 text-slate-500 hover:text-slate-300">
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="mb-5 grid grid-cols-4 gap-3">
        {[
          { label: 'Total Wires', value: harness.wire_count, color: '#3B82F6' },
          { label: 'Power', value: harness.wires.filter(w => w.wire_type.startsWith('power')).length, color: '#EF4444' },
          { label: 'Signal', value: harness.wires.filter(w => w.wire_type.startsWith('signal')).length, color: '#10B981' },
          { label: 'Shield/Ground', value: harness.wires.filter(w => w.wire_type.startsWith('shield') || w.wire_type.startsWith('ground')).length, color: '#8B5CF6' },
        ].map(s => (
          <div key={s.label} className="rounded-xl border border-astra-border bg-astra-surface p-3 text-center">
            <div className="text-xl font-bold" style={{ color: s.color }}>{s.value}</div>
            <div className="text-[10px] text-slate-500">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Auto-wire result banner */}
      {autoWireResult && (
        <div className="mb-4 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle className="h-4 w-4 text-emerald-400" />
            <span className="text-sm font-semibold text-emerald-400">Auto-Wire Complete</span>
          </div>
          <div className="flex gap-6 text-[11px]">
            <span className="text-emerald-400 font-bold">{autoWireResult.matched} matched</span>
            {autoWireResult.unmatched_from?.length > 0 && (
              <span className="text-yellow-400">{autoWireResult.unmatched_from.length} unmatched (from)</span>
            )}
            {autoWireResult.unmatched_to?.length > 0 && (
              <span className="text-yellow-400">{autoWireResult.unmatched_to.length} unmatched (to)</span>
            )}
          </div>
          {autoWireResult.unmatched_from?.length > 0 && (
            <div className="mt-2 text-[10px] text-slate-500">
              Unmatched from pins: {autoWireResult.unmatched_from.map((p: any) => p.signal_name).join(', ')}
            </div>
          )}
        </div>
      )}

      {/* View mode tabs */}
      <div className="mb-4 flex gap-1 border-b border-astra-border">
        {([
          { key: 'wires' as ViewMode, label: 'Wire List' },
          { key: 'pinmap' as ViewMode, label: 'Pin-to-Pin' },
          { key: 'signals' as ViewMode, label: 'By Signal Type' },
        ]).map(t => (
          <button key={t.key} onClick={() => setViewMode(t.key)}
            className={clsx('border-b-2 px-4 py-2.5 text-xs font-semibold transition',
              viewMode === t.key ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-500 hover:text-slate-300')}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ════════════ WIRE LIST VIEW ════════════ */}
      {viewMode === 'wires' && (
        harness.wires.length === 0 ? (
          <div className="py-12 text-center">
            <Cable className="mx-auto h-10 w-10 text-slate-600 mb-3" />
            <p className="text-sm text-slate-400">No wires yet. Use Auto-Wire to match pins by signal name.</p>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-astra-border">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="bg-astra-surface-alt text-left text-slate-500">
                  {['Wire #', 'Signal Name', 'Type', 'Gauge', 'Color', 'From Pin', 'From Signal', 'To Pin', 'To Signal', 'Length'].map(h => (
                    <th key={h} className="px-3 py-2.5 font-semibold">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {harness.wires.map(w => (
                  <tr key={w.id} className="border-t border-astra-border/50 hover:bg-astra-surface-hover transition">
                    <td className="px-3 py-2 font-mono font-bold text-slate-300">{w.wire_number}</td>
                    <td className="px-3 py-2 font-semibold text-slate-200">{w.signal_name}</td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1.5">
                        <WireColor type={w.wire_type} />
                        <span className="capitalize text-slate-400">{w.wire_type.replace(/_/g, ' ')}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2 text-slate-400">{w.wire_gauge?.replace('awg_', 'AWG ') || '—'}</td>
                    <td className="px-3 py-2 text-slate-400">{w.wire_color_primary || '—'}</td>
                    <td className="px-3 py-2 font-mono text-slate-300">{w.from_pin_number || '—'}</td>
                    <td className="px-3 py-2 text-slate-400">{w.from_signal_name || '—'}</td>
                    <td className="px-3 py-2 font-mono text-slate-300">{w.to_pin_number || '—'}</td>
                    <td className="px-3 py-2 text-slate-400">{w.to_signal_name || '—'}</td>
                    <td className="px-3 py-2 text-slate-400">{w.length_m ? `${w.length_m}m` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* ════════════ PIN-TO-PIN VIEW ════════════ */}
      {viewMode === 'pinmap' && (
        <div className="overflow-x-auto rounded-xl border border-astra-border">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="bg-astra-surface-alt text-left text-slate-500">
                <th className="px-3 py-2.5 font-semibold" colSpan={3}>
                  FROM: {harness.from_unit_designation} / {harness.from_connector_designator}
                </th>
                <th className="px-3 py-2.5 font-semibold text-center border-l border-r border-astra-border">Wire</th>
                <th className="px-3 py-2.5 font-semibold" colSpan={3}>
                  TO: {harness.to_unit_designation} / {harness.to_connector_designator}
                </th>
              </tr>
              <tr className="bg-astra-surface text-left text-slate-600">
                <th className="px-3 py-1.5">Pin</th>
                <th className="px-3 py-1.5">Signal</th>
                <th className="px-3 py-1.5">Type</th>
                <th className="px-3 py-1.5 text-center border-l border-r border-astra-border">#</th>
                <th className="px-3 py-1.5">Pin</th>
                <th className="px-3 py-1.5">Signal</th>
                <th className="px-3 py-1.5">Type</th>
              </tr>
            </thead>
            <tbody>
              {harness.wires.map(w => (
                <tr key={w.id} className="border-t border-astra-border/50 hover:bg-astra-surface-hover">
                  <td className="px-3 py-1.5 font-mono font-bold text-slate-300">{w.from_pin_number}</td>
                  <td className="px-3 py-1.5 text-slate-200">{w.from_signal_name}</td>
                  <td className="px-3 py-1.5"><WireColor type={w.wire_type} /></td>
                  <td className="px-3 py-1.5 text-center font-mono text-blue-400 border-l border-r border-astra-border bg-blue-500/5">
                    {w.wire_number}
                  </td>
                  <td className="px-3 py-1.5 font-mono font-bold text-slate-300">{w.to_pin_number}</td>
                  <td className="px-3 py-1.5 text-slate-200">{w.to_signal_name}</td>
                  <td className="px-3 py-1.5"><WireColor type={w.wire_type} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ════════════ BY SIGNAL TYPE VIEW ════════════ */}
      {viewMode === 'signals' && (
        <div className="space-y-3">
          {[...wiresByType.entries()].map(([type, wires]) => (
            <div key={type} className="rounded-xl border border-astra-border bg-astra-surface p-4">
              <div className="flex items-center gap-2 mb-2">
                <WireColor type={type} />
                <span className="text-xs font-bold text-slate-300 capitalize">{type.replace(/_/g, ' ')}</span>
                <span className="rounded-full bg-astra-surface-alt px-1.5 py-0.5 text-[9px] font-bold text-slate-500">{wires.length}</span>
              </div>
              <div className="space-y-1">
                {wires.map(w => (
                  <div key={w.id} className="flex items-center gap-3 text-[11px] text-slate-400">
                    <span className="font-mono font-bold text-slate-300 w-12">{w.wire_number}</span>
                    <span className="flex-1 font-semibold text-slate-200">{w.signal_name}</span>
                    <span>{w.from_pin_number} → {w.to_pin_number}</span>
                    {w.wire_gauge && <span className="text-slate-500">{w.wire_gauge.replace('awg_', 'AWG ')}</span>}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Harness metadata */}
      <div className="mt-6 rounded-xl border border-astra-border bg-astra-surface p-4">
        <h3 className="text-xs font-bold text-slate-400 mb-3">HARNESS DETAILS</h3>
        <div className="grid grid-cols-3 gap-x-6 gap-y-1 text-[11px]">
          {[
            ['Status', harness.status?.replace(/_/g, ' ')],
            ['Cable Type', harness.cable_type],
            ['Cable Spec', harness.cable_spec],
            ['Cable P/N', harness.cable_part_number],
            ['Manufacturer', harness.cable_manufacturer],
            ['Length', harness.overall_length_m ? `${harness.overall_length_m}m` : null],
            ['Max Length', harness.overall_length_max_m ? `${harness.overall_length_max_m}m` : null],
            ['Shield Type', harness.shield_type?.replace(/_/g, ' ')],
            ['Shield Coverage', harness.shield_coverage_pct ? `${harness.shield_coverage_pct}%` : null],
            ['Drawing', harness.drawing_number],
            ['Revision', harness.drawing_revision],
            ['Approved By', harness.approved_by],
          ].filter(([, v]) => v).map(([label, value]) => (
            <div key={label as string} className="flex justify-between py-1 border-b border-astra-border/30">
              <span className="text-slate-500">{label}</span>
              <span className="font-semibold text-slate-300 capitalize">{value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
