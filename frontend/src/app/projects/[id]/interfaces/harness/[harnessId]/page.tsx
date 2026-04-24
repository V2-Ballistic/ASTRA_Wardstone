'use client';

/**
 * ASTRA — Harness Detail Page (Enhanced)
 * ==========================================
 * File: frontend/src/app/projects/[id]/interfaces/harness/[harnessId]/page.tsx
 *
 * Enhancements:
 *   - Breadcrumb: Interfaces → {Harness Name}
 *   - "Generate Requirements" button (appears when wires exist)
 *   - Inline requirement generation results
 *   - Auto-req badge showing generation status
 *   - Link to Auto Requirements review page
 *   - Auto-wire result includes auto_requirements from backend
 *
 * API calls:
 *   interfaceAPI.getHarness(harnessId)           → WireHarnessDetail
 *   interfaceAPI.autoWire(harnessId)             → { matched, wires_created, auto_requirements }
 *   interfaceAPI.generateRequirements(harnessId) → { requirements_generated, requirements[] }
 *   interfaceAPI.exportHarness(harnessId)        → blob
 *   interfaceAPI.listReqLinks({ entity_type: 'wire_harness', entity_id })
 *                                                → InterfaceRequirementLink[]
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft, Loader2, Cable, ArrowRight, RefreshCw,
  Download, Zap, CheckCircle, AlertTriangle, Sparkles,
  ChevronRight, FileText, ExternalLink,
  ChevronDown, ChevronUp, Copy, Check, RotateCw, Info,
} from 'lucide-react';
import clsx from 'clsx';
import { interfaceAPI, downloadBlob } from '@/lib/interface-api';
import type { WireHarnessDetail, Wire, InterfaceRequirementLink } from '@/lib/interface-types';
import { SIGNAL_TYPE_COLORS, labelize } from '@/lib/interface-types';

// ══════════════════════════════════════
//  Shared UI
// ══════════════════════════════════════

// ── Wire color lookup: prefer the signal_type color, fall back to wire_type heuristic ──
function wireColor(signalType?: string | null, wireType?: string | null): string {
  if (signalType && SIGNAL_TYPE_COLORS[signalType]) return SIGNAL_TYPE_COLORS[signalType];
  const t = (wireType || '').toLowerCase();
  if (t.startsWith('power'))  return '#EF4444';
  if (t.startsWith('ground')) return '#6B7280';
  if (t.startsWith('shield')) return '#A78BFA';
  if (t.startsWith('coax'))   return '#F59E0B';
  if (t.startsWith('fiber'))  return '#06B6D4';
  return '#3B82F6';
}

function WireColor({ type, signalType }: { type: string; signalType?: string }) {
  const color = wireColor(signalType, type);
  return <div className="h-2 w-2 rounded-full flex-shrink-0" style={{ background: color }} />;
}

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  concept:            { bg: 'rgba(100,116,139,0.15)', text: '#94A3B8' },
  preliminary_design: { bg: 'rgba(139,92,246,0.15)',  text: '#A78BFA' },
  detailed_design:    { bg: 'rgba(59,130,246,0.12)',  text: '#3B82F6' },
  drawing_released:   { bg: 'rgba(16,185,129,0.15)',  text: '#10B981' },
  fabrication:        { bg: 'rgba(245,158,11,0.15)',  text: '#F59E0B' },
  installed:          { bg: 'rgba(16,185,129,0.25)',  text: '#34D399' },
};

function StatusBadge({ status }: { status: string }) {
  const c = STATUS_COLORS[status] || STATUS_COLORS.concept;
  return (
    <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
      style={{ background: c.bg, color: c.text }}>
      {labelize(status)}
    </span>
  );
}

// ══════════════════════════════════════════════════════════════
//  Pin Map — SVG electrical-schematic view
//
//  Each wire drawn as a colored trace between the FROM connector
//  (left) and TO connector (right). Signal-type color coding,
//  direction arrows at the midpoint, signal-name labels floating
//  above each trace. Hover highlights an individual trace.
// ══════════════════════════════════════════════════════════════

function PinMapSvg({
  harness,
  hoveredWireId,
  onHover,
}: {
  harness: WireHarnessDetail;
  hoveredWireId: number | null;
  onHover: (id: number | null) => void;
}) {
  const wires = harness.wires;

  // Layout constants
  const rowHeight = 36;
  const padY = 36;
  const padX = 24;
  const connectorWidth = 180;
  const connectorGap = 320;
  const pinBoxW = 28;
  const pinBoxH = 22;

  const width = connectorWidth * 2 + connectorGap + padX * 2;
  const height = Math.max(wires.length * rowHeight + padY * 2, 160);

  const leftBodyX = padX;
  const rightBodyX = padX + connectorWidth + connectorGap;
  const bodyTop = padY - 14;
  const bodyHeight = height - padY * 2 + 28;

  // Helper: get the Y coordinate of the i-th row's center
  const rowY = (i: number) => padY + i * rowHeight + rowHeight / 2;

  // Legend: collect unique signal types used in this harness
  const legend = useMemo(() => {
    const seen = new Map<string, string>();
    for (const w of wires) {
      const key = w.signal_name && (w as any).signal_type ? (w as any).signal_type : w.wire_type;
      if (!seen.has(key)) seen.set(key, wireColor((w as any).signal_type, w.wire_type));
    }
    return [...seen.entries()];
  }, [wires]);

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" preserveAspectRatio="xMidYMid meet">
        <defs>
          <linearGradient id="pinmap-body" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#1E293B" />
            <stop offset="1" stopColor="#0B1220" />
          </linearGradient>
          <marker id="pinmap-arrow" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
          </marker>
        </defs>

        {/* Connector body — FROM (left) */}
        <rect x={leftBodyX} y={bodyTop} width={connectorWidth} height={bodyHeight}
          rx={8} fill="url(#pinmap-body)" stroke="#334155" strokeWidth={1.5} />
        <text x={leftBodyX + connectorWidth / 2} y={bodyTop - 6}
          textAnchor="middle" fill="#10B981" fontSize="11" fontWeight="700" letterSpacing="0.12em">
          {(harness.from_unit_designation || '').toUpperCase()} ▸ {(harness.from_connector_designator || '').toUpperCase()}
        </text>

        {/* Connector body — TO (right) */}
        <rect x={rightBodyX} y={bodyTop} width={connectorWidth} height={bodyHeight}
          rx={8} fill="url(#pinmap-body)" stroke="#334155" strokeWidth={1.5} />
        <text x={rightBodyX + connectorWidth / 2} y={bodyTop - 6}
          textAnchor="middle" fill="#A78BFA" fontSize="11" fontWeight="700" letterSpacing="0.12em">
          {(harness.to_unit_designation || '').toUpperCase()} ▸ {(harness.to_connector_designator || '').toUpperCase()}
        </text>

        {/* Left-side pin rows */}
        {wires.map((w, i) => {
          const y = rowY(i);
          const isHover = hoveredWireId === w.id;
          return (
            <g key={`L-${w.id}`} onMouseEnter={() => onHover(w.id)} onMouseLeave={() => onHover(null)}
              style={{ cursor: 'pointer' }}>
              {/* Pin box */}
              <rect
                x={leftBodyX + 10} y={y - pinBoxH / 2}
                width={pinBoxW} height={pinBoxH} rx={3}
                fill={isHover ? '#0F172A' : '#0B1220'}
                stroke={isHover ? wireColor((w as any).signal_type, w.wire_type) : '#334155'}
                strokeWidth={isHover ? 1.5 : 1}
              />
              <text x={leftBodyX + 10 + pinBoxW / 2} y={y + 3} textAnchor="middle"
                fill="#CBD5E1" fontSize="10" fontFamily="monospace" fontWeight="700">
                {w.from_pin_number}
              </text>
              {/* Signal name */}
              <text x={leftBodyX + 10 + pinBoxW + 8} y={y + 3}
                fill={isHover ? '#F8FAFC' : '#94A3B8'} fontSize="10.5" fontFamily="monospace">
                {w.signal_name}
              </text>
              {/* Contact nub (where wire exits body) */}
              <circle cx={leftBodyX + connectorWidth} cy={y} r={3.5}
                fill={wireColor((w as any).signal_type, w.wire_type)} />
            </g>
          );
        })}

        {/* Right-side pin rows */}
        {wires.map((w, i) => {
          const y = rowY(i);
          const isHover = hoveredWireId === w.id;
          return (
            <g key={`R-${w.id}`} onMouseEnter={() => onHover(w.id)} onMouseLeave={() => onHover(null)}
              style={{ cursor: 'pointer' }}>
              <circle cx={rightBodyX} cy={y} r={3.5}
                fill={wireColor((w as any).signal_type, w.wire_type)} />
              <rect
                x={rightBodyX + connectorWidth - pinBoxW - 10} y={y - pinBoxH / 2}
                width={pinBoxW} height={pinBoxH} rx={3}
                fill={isHover ? '#0F172A' : '#0B1220'}
                stroke={isHover ? wireColor((w as any).signal_type, w.wire_type) : '#334155'}
                strokeWidth={isHover ? 1.5 : 1}
              />
              <text x={rightBodyX + connectorWidth - 10 - pinBoxW / 2} y={y + 3} textAnchor="middle"
                fill="#CBD5E1" fontSize="10" fontFamily="monospace" fontWeight="700">
                {w.to_pin_number}
              </text>
              <text x={rightBodyX + connectorWidth - 10 - pinBoxW - 8} y={y + 3} textAnchor="end"
                fill={isHover ? '#F8FAFC' : '#94A3B8'} fontSize="10.5" fontFamily="monospace">
                {w.signal_name}
              </text>
            </g>
          );
        })}

        {/* Wire traces — drawn last so they sit on top */}
        {wires.map((w, i) => {
          const y = rowY(i);
          const x1 = leftBodyX + connectorWidth;
          const x2 = rightBodyX;
          const midX = (x1 + x2) / 2;
          const color = wireColor((w as any).signal_type, w.wire_type);
          const isHover = hoveredWireId === w.id;
          // Slight vertical jitter to avoid overlap when many wires share a row
          const dy = 0;
          // Bezier: start horizontal, gentle S-curve through the mid
          const d = `M ${x1} ${y} C ${midX} ${y + dy}, ${midX} ${y + dy}, ${x2} ${y}`;
          return (
            <g key={`trace-${w.id}`} onMouseEnter={() => onHover(w.id)} onMouseLeave={() => onHover(null)}
              style={{ cursor: 'pointer' }}>
              {/* Glow on hover */}
              {isHover && (
                <path d={d} stroke={color} strokeWidth={8} fill="none" opacity={0.18} strokeLinecap="round" />
              )}
              <path d={d} stroke={color} strokeWidth={isHover ? 2.6 : 1.8} fill="none"
                strokeLinecap="round" markerEnd="url(#pinmap-arrow)" style={{ color }} />
              {/* Signal name floating above the trace at mid-point */}
              <text x={midX} y={y - 8} textAnchor="middle"
                fill={isHover ? color : '#64748B'}
                fontSize={isHover ? 10.5 : 9.5}
                fontFamily="monospace"
                fontWeight={isHover ? 700 : 500}>
                {w.signal_name}
              </text>
              {/* Wire gauge/type underneath, only on hover */}
              {isHover && (
                <text x={midX} y={y + 16} textAnchor="middle"
                  fill="#64748B" fontSize="8.5" fontFamily="monospace">
                  {w.wire_gauge ? `${w.wire_gauge} · ` : ''}{labelize(w.wire_type)}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      {legend.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-astra-border/60 pt-3">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Legend</span>
          {legend.map(([key, color]) => (
            <div key={key} className="flex items-center gap-1.5">
              <span className="h-2 w-6 rounded-full" style={{ background: color }} />
              <span className="text-[10px] text-slate-400 font-mono">{labelize(key)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

type ViewMode = 'wires' | 'pinmap' | 'signals';

// ══════════════════════════════════════
//  Main Page
// ══════════════════════════════════════

export default function HarnessDetailPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);
  const harnessId = Number(params.harnessId);
  const p = `/projects/${projectId}`;

  const [harness, setHarness]             = useState<WireHarnessDetail | null>(null);
  const [loading, setLoading]             = useState(true);
  const [viewMode, setViewMode]           = useState<ViewMode>('wires');
  const [msg, setMsg]                     = useState('');

  // Auto-wire
  const [autoWiring, setAutoWiring]       = useState(false);
  const [autoWireResult, setAutoWireResult] = useState<any>(null);

  // Generate requirements
  const [generatingReqs, setGeneratingReqs] = useState(false);
  const [genReqResult, setGenReqResult]     = useState<any>(null);

  // Auto-req badge (existing requirement links for this harness)
  const [reqLinks, setReqLinks]           = useState<InterfaceRequirementLink[]>([]);

  // ── Pin Map hover state ──
  const [hoveredWireId, setHoveredWireId] = useState<number | null>(null);

  // ── Error card UI state ──
  const [errorExpanded, setErrorExpanded] = useState(false);
  const [errorCopied, setErrorCopied]     = useState(false);

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(''), 4000); };

  // ── Fetch harness + req links ──
  const fetchHarness = useCallback(async () => {
    setLoading(true);
    try {
      const [harnRes, linkRes] = await Promise.all([
        interfaceAPI.getHarness(harnessId),
        interfaceAPI.listReqLinks({ entity_type: 'wire_harness', entity_id: harnessId }).catch(() => ({ data: [] })),
      ]);
      setHarness(harnRes.data);
      setReqLinks(linkRes.data || []);
    } catch { }
    setLoading(false);
  }, [harnessId]);

  useEffect(() => { fetchHarness(); }, [fetchHarness]);

  // ── Auto-Wire ──
  const handleAutoWire = async () => {
    setAutoWiring(true);
    setAutoWireResult(null);
    setGenReqResult(null);
    try {
      const res = await interfaceAPI.autoWire(harnessId);
      setAutoWireResult(res.data);
      // Auto-wire response includes auto_requirements field from backend
      if (res.data?.auto_requirements) {
        setGenReqResult(res.data.auto_requirements);
      }
      fetchHarness();
    } catch (e: any) {
      flash(e?.response?.data?.detail || 'Auto-wire failed');
    }
    setAutoWiring(false);
  };

  // ── Generate Requirements (standalone, for existing wires) ──
  const handleGenerateReqs = async () => {
    setGeneratingReqs(true);
    setGenReqResult(null);
    try {
      // Uses the new endpoint: POST /interfaces/harnesses/{id}/generate-requirements
      const res = await (interfaceAPI as any).generateRequirements
        ? (interfaceAPI as any).generateRequirements(harnessId)
        : interfaceAPI.autoWire(harnessId); // fallback if method not yet added
      setGenReqResult(res.data);
      fetchHarness(); // refresh req links
    } catch (e: any) {
      setGenReqResult({ requirements_generated: 0, error: e?.response?.data?.detail || 'Generation failed' });
    }
    setGeneratingReqs(false);
  };

  // ── Export ──
  const handleExport = async () => {
    try {
      const res = await interfaceAPI.exportHarness(harnessId);
      downloadBlob(res, `harness-${harnessId}.xlsx`);
    } catch { flash('Export failed'); }
  };

  // ── Loading / not found ──
  if (loading) return <div className="flex items-center justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-blue-500" /></div>;
  if (!harness) return (
    <div className="py-20 text-center">
      <AlertTriangle className="mx-auto h-10 w-10 text-red-400 mb-3" />
      <p className="text-sm text-slate-400">Harness not found.</p>
      <button onClick={() => router.push(`${p}/interfaces`)} className="mt-3 text-xs text-blue-400 hover:underline">Back to Interfaces</button>
    </div>
  );

  const wireCount = harness.wires?.length || 0;
  const autoReqCount = reqLinks.filter(l => l.auto_generated).length;
  const pendingReqCount = reqLinks.filter(l => l.status === 'pending_review').length;
  const approvedReqCount = reqLinks.filter(l => l.status === 'approved').length;

  return (
    <div>
      {/* ── Breadcrumb ── */}
      <div className="mb-4 flex items-center gap-1.5 text-[11px] text-slate-500">
        <button onClick={() => router.push(`${p}/interfaces`)} className="hover:text-blue-400 transition">Interfaces</button>
        <ChevronRight className="h-3 w-3" />
        <span className="text-slate-300 font-semibold">{harness.name}</span>
      </div>

      {/* ── Header ── */}
      <div className="mb-6 flex items-start justify-between">
        <div className="flex items-start gap-4">
          <button onClick={() => router.push(`${p}/interfaces`)}
            className="mt-1 rounded-lg border border-astra-border p-2 text-slate-500 hover:text-slate-300 transition">
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Cable className="h-5 w-5 text-emerald-400" />
              <h1 className="text-lg font-bold text-slate-100">{harness.name}</h1>
              {harness.harness_id && <span className="font-mono text-sm text-slate-500">({harness.harness_id})</span>}
              <StatusBadge status={harness.status || 'concept'} />
              {/* Auto-req badge */}
              {autoReqCount > 0 && (
                <span className="rounded-full bg-violet-500/15 px-2 py-0.5 text-[10px] font-bold text-violet-400 flex items-center gap-1">
                  <Sparkles className="h-3 w-3" />
                  {autoReqCount} req{autoReqCount !== 1 ? 's' : ''}
                  {pendingReqCount > 0 && <span className="text-yellow-400">({pendingReqCount} pending)</span>}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 text-[12px] text-slate-400">
              <span className="font-mono text-emerald-400">{harness.from_unit_designation}</span>
              <span className="text-slate-600">({harness.from_connector_designator})</span>
              <ArrowRight className="h-3.5 w-3.5 text-slate-600" />
              <span className="font-mono text-violet-400">{harness.to_unit_designation}</span>
              <span className="text-slate-600">({harness.to_connector_designator})</span>
            </div>
            {harness.description && <p className="mt-1 text-sm text-slate-500">{harness.description}</p>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={handleExport}
            className="flex items-center gap-1 rounded-lg border border-astra-border px-3 py-2 text-xs text-slate-400 hover:text-slate-200" title="Export wire list">
            <Download className="h-3.5 w-3.5" /> Export
          </button>
          <button onClick={fetchHarness}
            className="rounded-lg border border-astra-border p-2 text-slate-500 hover:text-slate-300" title="Refresh">
            <RefreshCw className={clsx('h-3.5 w-3.5', loading && 'animate-spin')} />
          </button>
        </div>
      </div>

      {/* ── Message ── */}
      {msg && (
        <div className={clsx('mb-4 rounded-lg border px-3 py-2 text-xs flex items-center gap-2',
          msg.includes('fail') ? 'border-red-500/20 bg-red-500/10 text-red-400' : 'border-emerald-500/20 bg-emerald-500/10 text-emerald-400')}>
          {msg.includes('fail') ? <AlertTriangle className="h-3.5 w-3.5" /> : <CheckCircle className="h-3.5 w-3.5" />} {msg}
        </div>
      )}

      {/* ── Stats row ── */}
      <div className="mb-5 grid grid-cols-5 gap-3">
        <div className="rounded-xl border border-astra-border bg-astra-surface p-3 text-center">
          <div className="text-xl font-bold text-blue-400">{wireCount}</div>
          <div className="text-[10px] text-slate-500">Wires</div>
        </div>
        <div className="rounded-xl border border-astra-border bg-astra-surface p-3 text-center">
          <div className="text-xl font-bold text-emerald-400">{harness.conductor_count || wireCount}</div>
          <div className="text-[10px] text-slate-500">Conductors</div>
        </div>
        <div className="rounded-xl border border-astra-border bg-astra-surface p-3 text-center">
          <div className="text-xl font-bold text-slate-300">{harness.overall_length_m ? `${harness.overall_length_m}m` : '—'}</div>
          <div className="text-[10px] text-slate-500">Length</div>
        </div>
        <div className="rounded-xl border border-astra-border bg-astra-surface p-3 text-center">
          <div className="text-xl font-bold text-violet-400">{autoReqCount}</div>
          <div className="text-[10px] text-slate-500">Auto Reqs</div>
        </div>
        <div className="rounded-xl border border-astra-border bg-astra-surface p-3 text-center">
          <div className="text-xl font-bold text-emerald-400">{approvedReqCount}</div>
          <div className="text-[10px] text-slate-500">Approved</div>
        </div>
      </div>

      {/* ── Action buttons ── */}
      <div className="mb-5 flex items-center gap-3">
        <button onClick={handleAutoWire} disabled={autoWiring}
          className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2.5 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-40">
          {autoWiring ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Zap className="h-3.5 w-3.5" />}
          Auto-Wire
        </button>

        {wireCount > 0 && (
          <button onClick={handleGenerateReqs} disabled={generatingReqs}
            className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-4 py-2.5 text-xs font-semibold text-white hover:bg-violet-500 disabled:opacity-40">
            {generatingReqs ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
            Generate Requirements
          </button>
        )}

        {autoReqCount > 0 && (
          <button onClick={() => router.push(`${p}/interfaces/auto-requirements`)}
            className="flex items-center gap-1.5 rounded-lg border border-violet-500/30 px-4 py-2.5 text-xs font-semibold text-violet-400 hover:bg-violet-500/10">
            <FileText className="h-3.5 w-3.5" />
            View in Auto Requirements
            <ExternalLink className="h-3 w-3" />
          </button>
        )}
      </div>

      {/* ── Auto-Wire Results ── */}
      {autoWireResult && (
        <div className="mb-4 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle className="h-4 w-4 text-emerald-400" />
            <span className="text-sm font-semibold text-emerald-400">Auto-Wire Complete</span>
          </div>
          <div className="text-[12px] text-slate-400 space-y-1">
            <p>Matched {autoWireResult.matched || 0} signal{(autoWireResult.matched || 0) !== 1 ? 's' : ''} by name.</p>
            {(autoWireResult.unmatched_from?.length > 0 || autoWireResult.unmatched_to?.length > 0) && (
              <p className="text-yellow-400">
                {autoWireResult.unmatched_from?.length || 0} unmatched from-pins,
                {' '}{autoWireResult.unmatched_to?.length || 0} unmatched to-pins
              </p>
            )}
          </div>
        </div>
      )}

      {/* ── Generate Requirements Results ── */}
      {genReqResult && (() => {
        const hasError = !!genReqResult.error;
        const rawError: string = hasError ? String(genReqResult.error) : '';

        // Parse common Postgres / SQLAlchemy error patterns into a friendly summary
        const friendlyErrorSummary = (err: string): { title: string; hint: string | null } => {
          const enumMatch = err.match(/invalid input value for enum (\w+):\s*"([^"]+)"/);
          if (enumMatch) {
            const [, enumName, value] = enumMatch;
            return {
              title: `Database enum "${enumName}" doesn't include value "${value}"`,
              hint: `The Python code is using a value that hasn't been added to the Postgres enum type. Run an ALTER TYPE ${enumName} ADD VALUE IF NOT EXISTS '${value}' in pgAdmin to fix.`,
            };
          }
          if (/duplicate key value violates unique constraint/i.test(err)) {
            return {
              title: 'A requirement with this ID already exists',
              hint: 'The auto-generator tried to create a requirement that collides with an existing req_id. Delete the existing one or rename it before retrying.',
            };
          }
          if (/foreign key/i.test(err)) {
            return {
              title: 'A referenced record was missing',
              hint: 'Something this requirement depends on (like a parent requirement or a user account) no longer exists. Check the technical details below.',
            };
          }
          if (/not-null constraint/i.test(err)) {
            return {
              title: 'A required field was empty',
              hint: 'The generator produced a requirement missing a field that the database requires. Check the technical details below.',
            };
          }
          return {
            title: 'Requirement generation failed',
            hint: 'The wires were created successfully, but the auto-requirement step hit an error. Your harness data is intact.',
          };
        };

        const summary = hasError ? friendlyErrorSummary(rawError) : null;

        const copyError = async () => {
          try {
            await navigator.clipboard.writeText(rawError);
            setErrorCopied(true);
            setTimeout(() => setErrorCopied(false), 1800);
          } catch {}
        };

        const retry = () => { setGenReqResult(null); setErrorExpanded(false); handleGenerateRequirements(); };

        return (
          <div className={clsx('mb-4 rounded-xl border p-4',
            hasError
              ? 'border-red-500/30 bg-red-500/5'
              : genReqResult.requirements_generated > 0
                ? 'border-violet-500/20 bg-violet-500/5'
                : 'border-astra-border bg-astra-surface')}>
            {/* ── Header row ── */}
            <div className="flex items-start gap-3">
              {hasError ? (
                <AlertTriangle className="h-5 w-5 shrink-0 text-red-400" />
              ) : (
                <Sparkles className="h-5 w-5 shrink-0 text-violet-400" />
              )}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={clsx('text-sm font-bold',
                    hasError ? 'text-red-400' : 'text-violet-400')}>
                    {hasError ? 'Requirement Generation Failed'
                              : genReqResult.requirements_generated > 0
                                ? `${genReqResult.requirements_generated} Requirement${genReqResult.requirements_generated !== 1 ? 's' : ''} Generated`
                                : 'No New Requirements'}
                  </span>
                  {genReqResult.verifications_generated > 0 && (
                    <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold text-emerald-400">
                      + {genReqResult.verifications_generated} verification{genReqResult.verifications_generated !== 1 ? 's' : ''}
                    </span>
                  )}
                </div>

                {/* Friendly error summary */}
                {hasError && summary && (
                  <div className="mt-1.5">
                    <p className="text-[13px] text-red-200">{summary.title}</p>
                    {summary.hint && (
                      <div className="mt-2 flex items-start gap-2 rounded-lg border border-blue-500/20 bg-blue-500/5 px-3 py-2">
                        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-blue-400" />
                        <p className="text-[11px] leading-relaxed text-slate-300">{summary.hint}</p>
                      </div>
                    )}
                  </div>
                )}

                {genReqResult.message && !hasError && (
                  <p className="mt-1 text-[12px] text-slate-400">{genReqResult.message}</p>
                )}
              </div>

              {/* Action buttons */}
              {hasError && (
                <div className="flex shrink-0 gap-1.5">
                  <button onClick={retry}
                    className="flex items-center gap-1 rounded-lg border border-red-500/30 bg-red-500/10 px-2.5 py-1.5 text-[10px] font-bold text-red-300 transition hover:bg-red-500/20"
                    title="Retry requirement generation">
                    <RotateCw className="h-3 w-3" /> Retry
                  </button>
                </div>
              )}
            </div>

            {/* ── Collapsible technical details ── */}
            {hasError && (
              <div className="mt-3 border-t border-red-500/20 pt-2">
                <button onClick={() => setErrorExpanded(v => !v)}
                  className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500 transition hover:text-slate-300">
                  {errorExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                  {errorExpanded ? 'Hide' : 'Show'} technical details
                </button>
                {errorExpanded && (
                  <div className="mt-2 relative">
                    <pre className="max-h-64 overflow-auto rounded-lg border border-astra-border bg-astra-bg p-3 font-mono text-[10px] leading-relaxed text-slate-400 whitespace-pre-wrap break-all">
                      {rawError}
                    </pre>
                    <button onClick={copyError}
                      className="absolute top-2 right-2 flex items-center gap-1 rounded border border-astra-border bg-astra-surface px-2 py-1 text-[10px] font-semibold text-slate-400 hover:text-slate-200"
                      title="Copy full error">
                      {errorCopied
                        ? <><Check className="h-3 w-3 text-emerald-400" /> Copied</>
                        : <><Copy className="h-3 w-3" /> Copy</>}
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* ── Requirement list (success case) ── */}
            {genReqResult.requirements && genReqResult.requirements.length > 0 && (
              <div className="mt-3 space-y-1.5">
                {genReqResult.requirements.slice(0, 12).map((r: any, i: number) => (
                  <div key={i} className="flex items-center gap-2 text-[11px]">
                    <span className="font-mono text-blue-400 font-bold w-24 flex-shrink-0">{r.req_id}</span>
                    <span className="rounded-full bg-violet-500/15 px-1.5 py-0.5 text-[9px] text-violet-400 w-8 text-center">{r.level}</span>
                    <span className="text-slate-300 truncate">{r.title}</span>
                    {r.quality_score && (
                      <span className={clsx('font-mono text-[10px] font-bold ml-auto flex-shrink-0',
                        r.quality_score >= 85 ? 'text-emerald-400' : r.quality_score >= 70 ? 'text-yellow-400' : 'text-red-400'
                      )}>{r.quality_score}</span>
                    )}
                  </div>
                ))}
                {genReqResult.requirements.length > 12 && (
                  <p className="text-[11px] text-slate-500 pt-1">+{genReqResult.requirements.length - 12} more requirements</p>
                )}
              </div>
            )}

            {genReqResult.requirements_generated > 0 && (
              <button onClick={() => router.push(`${p}/interfaces/auto-requirements`)}
                className="mt-3 flex items-center gap-1 text-[11px] text-violet-400 hover:text-violet-300">
                Review in Auto Requirements <ExternalLink className="h-3 w-3" />
              </button>
            )}
          </div>
        );
      })()}

      {/* ── View mode tabs ── */}
      <div className="mb-4 flex gap-1 border-b border-astra-border">
        {([
          { key: 'wires' as ViewMode, label: `Wires (${wireCount})` },
          { key: 'pinmap' as ViewMode, label: 'Pin Map' },
          { key: 'signals' as ViewMode, label: 'Signals' },
        ]).map(t => (
          <button key={t.key} onClick={() => setViewMode(t.key)}
            className={clsx('border-b-2 px-4 py-2.5 text-xs font-semibold transition',
              viewMode === t.key ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-500 hover:text-slate-300')}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ══════════════════════════════════════ */}
      {/*  WIRES VIEW                            */}
      {/* ══════════════════════════════════════ */}
      {viewMode === 'wires' && (
        wireCount === 0 ? (
          <div className="py-16 text-center rounded-xl border border-astra-border bg-astra-surface">
            <Cable className="mx-auto h-10 w-10 text-slate-600 mb-3" />
            <p className="text-sm text-slate-400 mb-1">No wires yet.</p>
            <p className="text-[11px] text-slate-500">
              Click "Auto-Wire" to create wires by matching signal names between the two connectors.
            </p>
          </div>
        ) : (
          <div className="rounded-xl border border-astra-border bg-astra-surface overflow-hidden">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="border-b border-astra-border bg-astra-surface-alt">
                  <th className="px-3 py-2.5 text-left font-semibold text-slate-400 w-16">Wire #</th>
                  <th className="px-3 py-2.5 text-left font-semibold text-slate-400">Signal Name</th>
                  <th className="px-3 py-2.5 text-left font-semibold text-slate-400 w-28">Type</th>
                  <th className="px-3 py-2.5 text-left font-semibold text-slate-400">From</th>
                  <th className="px-3 py-2.5 text-left font-semibold text-slate-400">To</th>
                  <th className="px-3 py-2.5 text-left font-semibold text-slate-400 w-16">Gauge</th>
                  <th className="px-3 py-2.5 text-left font-semibold text-slate-400 w-16">Color</th>
                </tr>
              </thead>
              <tbody>
                {harness.wires.map(w => (
                  <tr key={w.id} className="border-b border-astra-border/50 hover:bg-astra-surface-alt/50 transition">
                    <td className="px-3 py-2 font-mono font-bold text-slate-300">{w.wire_number}</td>
                    <td className="px-3 py-2 font-semibold text-slate-200">{w.signal_name}</td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1.5">
                        <WireColor type={w.wire_type} signalType={(w as any).signal_type} />
                        <span className="text-slate-400 text-[11px]">{labelize(w.wire_type)}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2 text-slate-400">
                      <span className="font-mono text-emerald-400">{w.from_unit_designation}</span>
                      <span className="text-slate-600 mx-1">{w.from_connector_designator}:{w.from_pin_number}</span>
                    </td>
                    <td className="px-3 py-2 text-slate-400">
                      <span className="font-mono text-violet-400">{w.to_unit_designation}</span>
                      <span className="text-slate-600 mx-1">{w.to_connector_designator}:{w.to_pin_number}</span>
                    </td>
                    <td className="px-3 py-2 text-slate-500 font-mono">{w.wire_gauge || '—'}</td>
                    <td className="px-3 py-2 text-slate-500">{w.wire_color_primary || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* ══════════════════════════════════════ */}
      {/*  PIN MAP VIEW                          */}
      {/* ══════════════════════════════════════ */}
      {viewMode === 'pinmap' && (
        wireCount === 0 ? (
          <div className="py-12 text-center rounded-xl border border-astra-border bg-astra-surface text-sm text-slate-500">
            No wires to map. Run Auto-Wire first.
          </div>
        ) : (
          <div className="rounded-xl border border-astra-border bg-gradient-to-b from-astra-surface to-astra-bg p-6">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Harness Pin Map — {wireCount} wire{wireCount !== 1 ? 's' : ''}
              </h3>
              <span className="text-[10px] text-slate-600">Hover a trace for details</span>
            </div>
            <PinMapSvg
              harness={harness}
              hoveredWireId={hoveredWireId}
              onHover={setHoveredWireId}
            />
          </div>
        )
      )}

      {/* ══════════════════════════════════════ */}
      {/*  SIGNALS VIEW                          */}
      {/* ══════════════════════════════════════ */}
      {viewMode === 'signals' && (
        wireCount === 0 ? (
          <div className="py-12 text-center rounded-xl border border-astra-border bg-astra-surface text-sm text-slate-500">
            No wires to group. Run Auto-Wire first.
          </div>
        ) : (
          <div className="space-y-3">
            {(() => {
              const groups = new Map<string, Wire[]>();
              for (const w of harness.wires) {
                const t = w.wire_type;
                if (!groups.has(t)) groups.set(t, []);
                groups.get(t)!.push(w);
              }
              return [...groups.entries()].map(([type, wires]) => (
                <div key={type} className="rounded-xl border border-astra-border bg-astra-surface p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <WireColor type={type} />
                    <span className="text-sm font-semibold text-slate-200">{labelize(type)}</span>
                    <span className="rounded-full bg-astra-surface-alt px-1.5 py-0.5 text-[9px] font-bold text-slate-500">{wires.length}</span>
                  </div>
                  <div className="space-y-1">
                    {wires.map(w => (
                      <div key={w.id} className="flex items-center gap-4 text-[11px] py-1 border-b border-astra-border/30 last:border-0">
                        <span className="font-mono text-slate-300 w-14">{w.wire_number}</span>
                        <span className="font-semibold text-slate-200 flex-1">{w.signal_name}</span>
                        <span className="text-emerald-400 font-mono">{w.from_unit_designation}:{w.from_pin_number}</span>
                        <ArrowRight className="h-3 w-3 text-slate-600" />
                        <span className="text-violet-400 font-mono">{w.to_unit_designation}:{w.to_pin_number}</span>
                        {w.wire_gauge && <span className="text-slate-500">{w.wire_gauge}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              ));
            })()}
          </div>
        )
      )}
    </div>
  );
}
