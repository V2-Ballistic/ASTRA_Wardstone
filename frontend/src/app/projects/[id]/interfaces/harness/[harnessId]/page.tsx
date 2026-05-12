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

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft, Loader2, Cable, ArrowRight, RefreshCw,
  Download, Zap, CheckCircle, AlertTriangle, Sparkles,
  ChevronRight, FileText, ExternalLink,
  ChevronDown, ChevronUp, Copy, Check, RotateCw, Info,
  Edit3, Save, X, Trash2, Plus,
} from 'lucide-react';
import clsx from 'clsx';
import { interfaceAPI, downloadBlob } from '@/lib/interface-api';
import { formatApiError } from '@/lib/errors';
import type {
  WireHarnessDetail, Wire, InterfaceRequirementLink,
  AutoGrowPair,
} from '@/lib/interface-types';
import { SIGNAL_TYPE_COLORS, labelize } from '@/lib/interface-types';
import {
  AutoGrowAmbiguityModal, useAmbiguityModal,
} from '@/components/AutoGrowAmbiguityModal';

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

// F-097: a one-character glyph paired with the color so signal type
// is conveyed by both colour AND text. Maps the same prefixes
// wireColor uses; defaults to "S" for generic signal.
function signalGlyph(signalType?: string | null, wireType?: string | null): string {
  const s = (signalType || '').toLowerCase();
  if (s.startsWith('power')) return 'P';
  if (s.includes('ground')) return 'G';
  if (s.startsWith('clock')) return 'C';
  if (s.startsWith('rf_') || s === 'rf_signal') return 'R';
  if (s.startsWith('discrete')) return 'D';
  if (s.includes('analog')) return 'A';
  if (s.includes('digital')) return 'D';
  if (s.startsWith('serial') || s.startsWith('spi') || s.startsWith('i2c') || s.startsWith('can')) return 'B';
  if (s.startsWith('fiber') || s.startsWith('shield')) return 'S';
  if (s === 'spare' || s === 'no_connect') return '–';
  const t = (wireType || '').toLowerCase();
  if (t.startsWith('power')) return 'P';
  if (t.startsWith('ground')) return 'G';
  if (t.startsWith('shield')) return 'S';
  if (t.startsWith('coax') || t.startsWith('rf')) return 'R';
  if (t.startsWith('fiber')) return 'S';
  return 'S';
}

function WireColor({ type, signalType }: { type: string; signalType?: string }) {
  const color = wireColor(signalType, type);
  const glyph = signalGlyph(signalType, type);
  // F-097: render a glyph next to the color dot — colour-only signals
  // failed WCAG 1.4.1; the adjacent letter gives the same info to
  // users who can't distinguish the colours.
  return (
    <div className="flex items-center gap-1 flex-shrink-0">
      <div className="h-2 w-2 rounded-full" style={{ background: color }} aria-hidden="true" />
      <span className="text-[8px] font-bold text-slate-400" aria-label={`Signal class ${glyph}`}>{glyph}</span>
    </div>
  );
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

// F-129: paginate when wire count exceeds this threshold. Below it,
// the SVG renders the full set the way it always has. Above, the
// component renders a 200-wire window plus a "Showing wires X..Y of N"
// header with previous/next controls. SVG-aware viewport-based
// virtualization would be cleaner but requires the parent scroll
// container to be on the SVG itself; the harness page lets the
// page-level scroll do the work today, so paged chunks are the
// simpler bounded fix. Canvas would scale further but is a
// substantial rewrite — defer until 1000+ wires becomes common.
const PIN_MAP_PAGE_SIZE = 200;

function PinMapSvg({
  harness,
  hoveredWireId,
  onHover,
}: {
  harness: WireHarnessDetail;
  hoveredWireId: number | null;
  onHover: (id: number | null) => void;
}) {
  const allWires = harness.wires;
  const [page, setPage] = useState(0);
  const totalPages = Math.max(1, Math.ceil(allWires.length / PIN_MAP_PAGE_SIZE));
  const wires = allWires.length > PIN_MAP_PAGE_SIZE
    ? allWires.slice(page * PIN_MAP_PAGE_SIZE, (page + 1) * PIN_MAP_PAGE_SIZE)
    : allWires;

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
      const key = w.signal_name && w.signal_type ? w.signal_type : w.wire_type;
      if (!seen.has(key)) seen.set(key, wireColor(w.signal_type, w.wire_type));
    }
    return [...seen.entries()];
  }, [wires]);

  return (
    <div>
      {/* F-129: pagination strip when wire count exceeds the page size. */}
      {allWires.length > PIN_MAP_PAGE_SIZE && (
        <div className="mb-3 flex items-center justify-between rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-200">
          <span>
            Showing wires {page * PIN_MAP_PAGE_SIZE + 1}–
            {Math.min((page + 1) * PIN_MAP_PAGE_SIZE, allWires.length)} of {allWires.length}
            <span className="ml-2 text-amber-300/70">
              (paginated for performance — use the Wires table for the full list)
            </span>
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={page === 0}
              className="rounded-md border border-amber-500/30 px-2 py-1 text-[10px] font-medium text-amber-200 hover:bg-amber-500/10 disabled:opacity-40"
              aria-label="Previous page of wires"
            >
              ◀
            </button>
            <span className="px-1 text-[10px] text-amber-200/80">
              Page {page + 1} of {totalPages}
            </span>
            <button
              type="button"
              onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="rounded-md border border-amber-500/30 px-2 py-1 text-[10px] font-medium text-amber-200 hover:bg-amber-500/10 disabled:opacity-40"
              aria-label="Next page of wires"
            >
              ▶
            </button>
          </div>
        </div>
      )}
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
                stroke={isHover ? wireColor(w.signal_type, w.wire_type) : '#334155'}
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
                fill={wireColor(w.signal_type, w.wire_type)} />
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
                fill={wireColor(w.signal_type, w.wire_type)} />
              <rect
                x={rightBodyX + connectorWidth - pinBoxW - 10} y={y - pinBoxH / 2}
                width={pinBoxW} height={pinBoxH} rx={3}
                fill={isHover ? '#0F172A' : '#0B1220'}
                stroke={isHover ? wireColor(w.signal_type, w.wire_type) : '#334155'}
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
          const color = wireColor(w.signal_type, w.wire_type);
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

type ViewMode = 'overview' | 'wires' | 'pinmap' | 'endpoints' | 'signals';

// ══════════════════════════════════════
//  Main Page
// ══════════════════════════════════════

// ══════════════════════════════════════════════════════════════
//  Phase 3b — Harness Overview panel (editable form)
// ══════════════════════════════════════════════════════════════

/**
 * Dropdown values for the Overview form. Mason picked these last turn — if
 * you want to add or remove options, edit here AND keep in mind the backend
 * columns are VARCHAR so any string passes through; no enum-coupling.
 *
 * The "custom" sentinel lets users type a free-text value via
 * *_custom fields later if needed — not wired yet in 3b, deferred.
 */
const SHIELDING_CLASSES = [
  'Unshielded',
  'Braided shield',
  'Foil shield',
  'Foil + braid (composite)',
  'Twisted pair (shielded)',
  'Twisted pair (unshielded)',
  'Coaxial',
];
const JACKET_MATERIALS = [
  'PVC',
  'Teflon (PTFE)',
  'FEP',
  'Cross-linked ETFE (MIL-W-22759 style)',
  'Silicone',
  'Polyurethane',
  'Kapton (polyimide)',
  'Rubber / neoprene',
];
const SLEEVE_TYPES = [
  'None',
  'Expandable braided sleeving (PET)',
  'Heat-shrink tubing',
  'Spiral wrap',
  'Conduit (metal)',
  'Conduit (plastic)',
  'Tape only',
  'NOMEX',
];
const HARNESS_STATUSES = [
  'concept', 'preliminary_design', 'detailed_design', 'fabrication',
  'integration', 'qualification_test', 'acceptance_test',
  'drawing_released', 'installed', 'maintenance', 'retired',
];

function HarnessOverviewPanel({
  harness, editing, fields, setFields, saving, error,
  onStartEdit, onCancel, onSave,
}: {
  harness: WireHarnessDetail;
  editing: boolean;
  fields: Record<string, any>;
  setFields: (f: Record<string, any>) => void;
  saving: boolean;
  error: string;
  onStartEdit: () => void;
  onCancel: () => void;
  onSave: () => void;
}) {
  const update = (k: string, v: any) => setFields({ ...fields, [k]: v });

  if (!editing) {
    // ── Read-only display ──
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">
            Harness Overview
          </h3>
          <button onClick={onStartEdit}
            className="flex items-center gap-1.5 rounded-lg border border-astra-border px-3 py-1.5 text-xs font-semibold text-slate-300 hover:border-blue-500/30 hover:text-blue-300 transition">
            <Edit3 className="h-3 w-3" /> Edit
          </button>
        </div>

        <Section title="Identity">
          <Field label="Name" value={harness.name} />
          <Field label="Harness ID" value={harness.harness_id} mono />
          <Field label="Status" value={harness.status} badge />
          <Field label="Description" value={harness.description} fullWidth />
        </Section>

        <Section title="Physical / Cable">
          <Field label="Cable Part Number" value={harness.cable_part_number} mono />
          <Field label="Cable Manufacturer" value={harness.cable_manufacturer} />
          <Field label="Overall Length" value={harness.overall_length_m} unit="m" />
          <Field label="Weight per meter" value={harness.weight_g_per_m} unit="g/m" />
          <Field label="Outer Diameter" value={harness.outer_diameter_mm} unit="mm" />
          <Field label="Mass" value={harness.mass_kg} unit="kg" />
          <Field label="Min Bend Radius" value={harness.min_bend_radius_mm} unit="mm" />
          <Field label="Service Loop" value={harness.service_loop_m} unit="m" />
        </Section>

        <Section title="Construction">
          <Field label="Shielding Class" value={harness.shielding_class} />
          <Field label="Jacket Material" value={harness.jacket_material} />
          <Field label="Jacket Color" value={harness.jacket_color} />
          <Field label="Sleeve Type" value={harness.sleeve_type} />
          <Field label="Drain Wire" value={harness.drain_wire_spec} />
          <Field label="MIL Spec" value={harness.mil_spec} />
        </Section>

        <Section title="Ratings">
          <Field label="Operating Temp Min" value={harness.operating_temp_min_c} unit="°C" />
          <Field label="Operating Temp Max" value={harness.operating_temp_max_c} unit="°C" />
          <Field label="Voltage Rating" value={harness.voltage_rating_v} unit="V" />
        </Section>

        <Section title="Release">
          <Field label="Drawing Number" value={harness.drawing_number} mono />
          <Field label="Drawing Revision" value={harness.drawing_revision} mono />
          <Field label="Approved By" value={harness.approved_by} />
          <Field label="Approval Date" value={harness.approval_date} />
        </Section>
      </div>
    );
  }

  // ── Edit mode ──
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">
          Editing Harness Overview
        </h3>
        <div className="flex gap-2">
          <button onClick={onCancel} disabled={saving}
            className="flex items-center gap-1.5 rounded-lg border border-astra-border px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-astra-surface-alt disabled:opacity-40">
            <X className="h-3 w-3" /> Cancel
          </button>
          <button onClick={onSave} disabled={saving}
            className="flex items-center gap-1.5 rounded-lg bg-blue-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-600 disabled:opacity-40">
            {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
            Save Changes
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2 text-xs text-red-400 flex items-start gap-2">
          <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" /> {error}
        </div>
      )}

      <EditSection title="Identity">
        <EditField label="Name *" value={fields.name} onChange={v => update('name', v)} />
        <EditField label="Harness ID" value={fields.harness_id} onChange={v => update('harness_id', v)} mono />
        <EditSelect label="Status" value={fields.status} onChange={v => update('status', v)}
          options={HARNESS_STATUSES.map(s => ({ value: s, label: s.replace(/_/g, ' ') }))} />
        <EditTextarea label="Description" value={fields.description} onChange={v => update('description', v)} fullWidth />
      </EditSection>

      <EditSection title="Physical / Cable">
        <EditField label="Cable Part Number" value={fields.cable_part_number} onChange={v => update('cable_part_number', v)} mono />
        <EditField label="Cable Manufacturer" value={fields.cable_manufacturer} onChange={v => update('cable_manufacturer', v)} />
        <EditField label="Overall Length (m)" type="number" step="0.01" value={fields.overall_length_m} onChange={v => update('overall_length_m', v)} />
        <EditField label="Weight (g/m)" type="number" step="0.1" value={fields.weight_g_per_m} onChange={v => update('weight_g_per_m', v)} />
        <EditField label="Outer Diameter (mm)" type="number" step="0.1" value={fields.outer_diameter_mm} onChange={v => update('outer_diameter_mm', v)} />
        <EditField label="Mass (kg)" type="number" step="0.001" value={fields.mass_kg} onChange={v => update('mass_kg', v)} />
        <EditField label="Min Bend Radius (mm)" type="number" step="1" value={fields.min_bend_radius_mm} onChange={v => update('min_bend_radius_mm', v)} />
        <EditField label="Service Loop (m)" type="number" step="0.01" value={fields.service_loop_m} onChange={v => update('service_loop_m', v)} />
      </EditSection>

      <EditSection title="Construction">
        <EditSelect label="Shielding Class" value={fields.shielding_class} onChange={v => update('shielding_class', v)}
          options={[{ value: '', label: '— none —' }, ...SHIELDING_CLASSES.map(s => ({ value: s, label: s }))]} />
        <EditSelect label="Jacket Material" value={fields.jacket_material} onChange={v => update('jacket_material', v)}
          options={[{ value: '', label: '— none —' }, ...JACKET_MATERIALS.map(s => ({ value: s, label: s }))]} />
        <EditField label="Jacket Color" value={fields.jacket_color} onChange={v => update('jacket_color', v)} />
        <EditSelect label="Sleeve Type" value={fields.sleeve_type} onChange={v => update('sleeve_type', v)}
          options={[{ value: '', label: '— none —' }, ...SLEEVE_TYPES.map(s => ({ value: s, label: s }))]} />
        <EditField label="Drain Wire Spec" value={fields.drain_wire_spec} onChange={v => update('drain_wire_spec', v)}
          placeholder="e.g., 22 AWG tinned copper" />
        <EditField label="MIL Spec" value={fields.mil_spec} onChange={v => update('mil_spec', v)}
          placeholder="e.g., MIL-DTL-38999 Series III" />
      </EditSection>

      <EditSection title="Ratings">
        <EditField label="Operating Temp Min (°C)" type="number" step="1" value={fields.operating_temp_min_c}
          onChange={v => update('operating_temp_min_c', v)} placeholder="e.g., -55" />
        <EditField label="Operating Temp Max (°C)" type="number" step="1" value={fields.operating_temp_max_c}
          onChange={v => update('operating_temp_max_c', v)} placeholder="e.g., 125" />
        <EditField label="Voltage Rating (V)" type="number" step="1" value={fields.voltage_rating_v}
          onChange={v => update('voltage_rating_v', v)} />
      </EditSection>

      <EditSection title="Release">
        <EditField label="Drawing Number" value={fields.drawing_number} onChange={v => update('drawing_number', v)} mono />
        <EditField label="Drawing Revision" value={fields.drawing_revision} onChange={v => update('drawing_revision', v)} mono />
      </EditSection>
    </div>
  );
}

// ── Read-only helpers ──

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
      <h4 className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-3">{title}</h4>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2.5">{children}</dl>
    </div>
  );
}

function Field({ label, value, unit, mono, badge, fullWidth }: {
  label: string;
  value?: string | number | null;
  unit?: string;
  mono?: boolean;
  badge?: boolean;
  fullWidth?: boolean;
}) {
  const display = value === null || value === undefined || value === ''
    ? <span className="text-slate-600">—</span>
    : <>
        <span className={clsx(mono && 'font-mono', badge && 'rounded-full bg-astra-surface-alt px-2 py-0.5 text-[11px] font-semibold')}>
          {String(value).replace(/_/g, ' ')}
        </span>
        {unit && <span className="text-slate-500 ml-1 text-[10px]">{unit}</span>}
      </>;
  return (
    <div className={fullWidth ? 'col-span-2' : undefined}>
      <dt className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">{label}</dt>
      <dd className="text-[12px] text-slate-200 mt-0.5">{display}</dd>
    </div>
  );
}

// ── Edit helpers ──

function EditSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
      <h4 className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-3">{title}</h4>
      <div className="grid grid-cols-2 gap-3">{children}</div>
    </div>
  );
}

function EditField({ label, value, onChange, type = 'text', step, placeholder, mono, fullWidth }: {
  label: string;
  value: any;
  onChange: (v: string) => void;
  type?: string;
  step?: string;
  placeholder?: string;
  mono?: boolean;
  fullWidth?: boolean;
}) {
  return (
    <label className={clsx('block', fullWidth && 'col-span-2')}>
      <span className="mb-1 block text-[10px] uppercase tracking-wider text-slate-500 font-semibold">{label}</span>
      <input
        type={type}
        step={step}
        value={value ?? ''}
        placeholder={placeholder}
        onChange={e => onChange(e.target.value)}
        className={clsx(
          'w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-1.5 text-xs text-slate-100 outline-none focus:border-blue-500/50 focus:ring-2 focus:ring-blue-500/10',
          mono && 'font-mono',
          // Kill number-input spinners for a cleaner aerospace aesthetic
          type === 'number' && '[&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none',
        )}
      />
    </label>
  );
}

function EditTextarea({ label, value, onChange, fullWidth }: {
  label: string; value: any; onChange: (v: string) => void; fullWidth?: boolean;
}) {
  return (
    <label className={clsx('block', fullWidth && 'col-span-2')}>
      <span className="mb-1 block text-[10px] uppercase tracking-wider text-slate-500 font-semibold">{label}</span>
      <textarea
        value={value ?? ''}
        rows={2}
        onChange={e => onChange(e.target.value)}
        className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-1.5 text-xs text-slate-100 outline-none focus:border-blue-500/50 focus:ring-2 focus:ring-blue-500/10 resize-y"
      />
    </label>
  );
}

function EditSelect({ label, value, onChange, options, fullWidth }: {
  label: string;
  value: any;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  fullWidth?: boolean;
}) {
  return (
    <label className={clsx('block', fullWidth && 'col-span-2')}>
      <span className="mb-1 block text-[10px] uppercase tracking-wider text-slate-500 font-semibold">{label}</span>
      <select
        value={value ?? ''}
        onChange={e => onChange(e.target.value)}
        className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-1.5 text-xs text-slate-100 outline-none focus:border-blue-500/50 focus:ring-2 focus:ring-blue-500/10">
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );
}

// ══════════════════════════════════════════════════════════════
//  Phase 3b — Harness Endpoints panel
// ══════════════════════════════════════════════════════════════

/**
 * Lists all endpoints on this harness. Each row shows the LRU-side
 * connector it plugs into, the mating connector ASTRA auto-created,
 * wire count touching this endpoint, and an optional tail length /
 * label / notes.
 *
 * Delete is gated by a confirmation modal (owned by the parent page).
 * Add Endpoint is deferred to a later phase — for now, endpoints are
 * created implicitly by auto-grow when a wire extends the harness.
 */
function HarnessEndpointsPanel({
  harness, projectPath, onDeleteEndpoint, router,
}: {
  harness: WireHarnessDetail;
  projectPath: string;
  onDeleteEndpoint: (id: number) => void;
  router: any;
}) {
  const endpoints = harness.endpoints || [];

  if (endpoints.length === 0) {
    return (
      <div className="rounded-xl border border-astra-border bg-astra-surface py-10 text-center">
        <Cable className="h-8 w-8 text-slate-600 mx-auto mb-2" />
        <p className="text-sm text-slate-400">
          No endpoints recorded. This shouldn&apos;t happen for a migrated harness —
          check that the Phase 1 migration ran successfully.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">
          Endpoints ({endpoints.length})
        </h3>
        <span className="text-[10px] text-slate-500">
          New endpoints are added automatically when Auto-Wire extends this harness.
        </span>
      </div>

      <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="border-b border-astra-border bg-astra-surface-alt">
              <th className="px-3 py-2 text-left font-semibold text-slate-400 w-16">Label</th>
              <th className="px-3 py-2 text-left font-semibold text-slate-400">LRU</th>
              <th className="px-3 py-2 text-left font-semibold text-slate-400">Connector</th>
              <th className="px-3 py-2 text-left font-semibold text-slate-400">Mating</th>
              <th className="px-3 py-2 text-left font-semibold text-slate-400 w-20">Wires</th>
              <th className="px-3 py-2 text-left font-semibold text-slate-400 w-24">Tail</th>
              <th className="px-3 py-2 w-10" />
            </tr>
          </thead>
          <tbody>
            {endpoints.map(ep => (
              <tr key={ep.id} className="border-b border-astra-border/50 hover:bg-astra-surface-alt/50 transition">
                <td className="px-3 py-2 font-mono text-slate-300">
                  {ep.label || `#${ep.id}`}
                </td>
                <td className="px-3 py-2">
                  {ep.lru_unit_id ? (
                    <button
                      onClick={() => router.push(`${projectPath}/interfaces/unit/${ep.lru_unit_id}`)}
                      className="font-mono text-cyan-400 hover:text-cyan-300">
                      {ep.lru_unit_designation}
                    </button>
                  ) : (
                    <span className="text-slate-600">—</span>
                  )}
                  {ep.lru_unit_name && (
                    <div className="text-[10px] text-slate-500">{ep.lru_unit_name}</div>
                  )}
                </td>
                <td className="px-3 py-2">
                  {ep.lru_connector_id ? (
                    <button
                      onClick={() => router.push(`${projectPath}/interfaces/connector/${ep.lru_connector_id}`)}
                      className="font-mono text-slate-300 hover:text-blue-300">
                      {ep.lru_connector_designator}
                    </button>
                  ) : (
                    <span className="text-slate-600">—</span>
                  )}
                </td>
                <td className="px-3 py-2 text-[11px]">
                  <span className="font-mono text-violet-300">
                    {ep.mating_connector_designator || '?'}
                  </span>
                  {ep.mating_connector_type && (
                    <span className="text-slate-600 ml-1.5">
                      ({ep.mating_connector_type.replace(/_/g, ' ')})
                    </span>
                  )}
                </td>
                <td className="px-3 py-2">
                  <span className="rounded-full bg-astra-surface-alt px-2 py-0.5 text-[11px] font-bold text-slate-300">
                    {ep.wire_count || 0}
                  </span>
                </td>
                <td className="px-3 py-2 text-[11px] text-slate-400 font-mono">
                  {ep.tail_length_m != null ? `${ep.tail_length_m}m` : '—'}
                </td>
                <td className="px-3 py-2">
                  <button
                    onClick={() => onDeleteEndpoint(ep.id)}
                    className="rounded p-1 text-slate-600 hover:text-red-400 transition"
                    title="Delete endpoint (cascades wires + mating connector)">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
//  Phase 3b — Multi-endpoint pin map (radial layout)
// ══════════════════════════════════════════════════════════════

/**
 * Interactive pin map for 3+ endpoint harnesses. Unlike the classic
 * 2-endpoint PinMapSvg which uses a left/right layout, this one puts
 * endpoints around the outside of a central hub and draws curves for
 * each wire from one endpoint's mating connector to another's.
 *
 * Features matching Phase 3a's interactive spec:
 *   - Hover a wire → it brightens, others dim
 *   - Hover the row on the side panel → same highlight in the map
 *   - Click a wire → wire detail card shows up in the bottom right
 *
 * Layout choice: endpoints equally-spaced on a circle, centered on a
 * hub showing the harness name. Wire curves go through a mid-point
 * near the hub so bundling is visually apparent at a glance.
 */
function MultiEndpointPinMap({
  harness, hoveredWireId, onHover,
}: {
  harness: WireHarnessDetail;
  hoveredWireId: number | null;
  onHover: (id: number | null) => void;
}) {
  const endpoints = harness.endpoints || [];
  const wires = harness.wires || [];
  const [clickedWire, setClickedWire] = useState<Wire | null>(null);

  // SVG geometry
  const W = 720;
  const H = 560;
  const cx = W / 2;
  const cy = H / 2;
  const ringR = 210;     // radius at which endpoint boxes are placed
  const boxW = 150;
  const boxH = 64;

  // Place each endpoint at an equal angle around the hub
  const positions = useMemo(() => {
    const arr: Array<{
      id: number;
      unit: string;
      connector: string;
      label: string;
      x: number; y: number;
      angleDeg: number;
      wireCount: number;
    }> = [];
    const n = endpoints.length;
    for (let i = 0; i < n; i++) {
      // Start at top (angle -90°) and go clockwise
      const angle = -Math.PI / 2 + (2 * Math.PI * i) / n;
      arr.push({
        id: endpoints[i].id,
        unit: endpoints[i].lru_unit_designation || '?',
        connector: endpoints[i].lru_connector_designator || '?',
        label: endpoints[i].label || `P${i + 1}`,
        x: cx + ringR * Math.cos(angle) - boxW / 2,
        y: cy + ringR * Math.sin(angle) - boxH / 2,
        angleDeg: (angle * 180) / Math.PI,
        wireCount: endpoints[i].wire_count || 0,
      });
    }
    return arr;
  }, [endpoints]);

  // Map endpoint id → its box center (for drawing wires)
  const endpointCenter = useMemo(() => {
    const m = new Map<number, { x: number; y: number }>();
    positions.forEach(p => m.set(p.id, { x: p.x + boxW / 2, y: p.y + boxH / 2 }));
    return m;
  }, [positions]);

  // Resolve which endpoint a given wire's side belongs to. Wire has
  // from_mating_pin_id + to_mating_pin_id pointing at pins on the harness's
  // mating connectors; we match each mating pin's connector_id back to
  // an endpoint via mating_connector_id.
  //
  // But wires also store from_connector_designator + to_connector_designator
  // (LRU-side), so we can take a shortcut by matching designator to an
  // endpoint's lru_connector_designator — simpler than joining through
  // mating_pin_id and avoids a second API call.
  const findEndpointForSide = useCallback((unitDesig?: string, connDesig?: string): number | null => {
    if (!unitDesig || !connDesig) return null;
    const ep = endpoints.find(e =>
      e.lru_unit_designation === unitDesig &&
      e.lru_connector_designator === connDesig
    );
    return ep ? ep.id : null;
  }, [endpoints]);

  // Pre-compute wire endpoints for rendering
  const wireLines = useMemo(() => {
    return wires.map(w => {
      const fromEpId = findEndpointForSide(w.from_unit_designation, w.from_connector_designator);
      const toEpId = findEndpointForSide(w.to_unit_designation, w.to_connector_designator);
      if (!fromEpId || !toEpId) return null;
      const a = endpointCenter.get(fromEpId);
      const b = endpointCenter.get(toEpId);
      if (!a || !b) return null;
      return {
        wire: w,
        fromEpId,
        toEpId,
        ax: a.x, ay: a.y,
        bx: b.x, by: b.y,
      };
    }).filter((w): w is NonNullable<typeof w> => w !== null);
  }, [wires, findEndpointForSide, endpointCenter]);

  return (
    <div>
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full font-mono" preserveAspectRatio="xMidYMid meet">
          <defs>
            <linearGradient id="meshbg" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#1E293B" />
              <stop offset="1" stopColor="#0B1220" />
            </linearGradient>
          </defs>

          {/* Center hub */}
          <circle cx={cx} cy={cy} r={42} fill="url(#meshbg)" stroke="#475569" strokeWidth={1.5} />
          <text x={cx} y={cy - 2} textAnchor="middle"
            fill="#94A3B8" fontSize="10" fontWeight="700" letterSpacing="0.08em">
            HARNESS
          </text>
          <text x={cx} y={cy + 12} textAnchor="middle"
            fill="#60A5FA" fontSize="10" fontFamily="ui-sans-serif">
            {wires.length} wires
          </text>

          {/* Wires — drawn as quadratic Bezier curves through the hub so
              bundling is visually apparent. Each wire's midpoint is
              offset slightly along the perpendicular to avoid coincident
              curves when many wires share the same endpoint pair. */}
          {wireLines.map((wl, i) => {
            const { wire, ax, ay, bx, by } = wl;
            const isHovered = hoveredWireId === wire.id;
            // Curve midpoint: center of the line, pulled toward the hub
            // by a small bias. Index-based offset keeps parallel wires
            // visually distinct.
            const mx = (ax + bx) / 2;
            const my = (ay + by) / 2;
            const toHubX = cx - mx;
            const toHubY = cy - my;
            const len = Math.sqrt(toHubX * toHubX + toHubY * toHubY) || 1;
            const pull = 0.35 + ((i % 5) * 0.06);
            const px = mx + (toHubX / len) * (len * pull);
            const py = my + (toHubY / len) * (len * pull);

            return (
              <path
                key={wire.id}
                d={`M ${ax} ${ay} Q ${px} ${py} ${bx} ${by}`}
                fill="none"
                stroke={wireColor((wire as any).signal_type, wire.wire_type)}
                strokeWidth={isHovered ? 3 : 1.5}
                opacity={hoveredWireId !== null && !isHovered ? 0.18 : 0.85}
                style={{ cursor: 'pointer', transition: 'stroke-width 140ms, opacity 140ms' }}
                onMouseEnter={() => onHover(wire.id)}
                onMouseLeave={() => onHover(null)}
                onClick={() => setClickedWire(wire)}
              />
            );
          })}

          {/* Endpoint boxes — drawn on top of wires */}
          {positions.map(pos => (
            <g key={pos.id}>
              <rect
                x={pos.x} y={pos.y}
                width={boxW} height={boxH}
                rx={8}
                fill="url(#meshbg)"
                stroke="#334155" strokeWidth={1.5}
              />
              <text x={pos.x + boxW / 2} y={pos.y + 18}
                textAnchor="middle" fill="#60A5FA"
                fontSize="10" fontWeight="700" letterSpacing="0.08em">
                {pos.label}
              </text>
              <text x={pos.x + boxW / 2} y={pos.y + 36}
                textAnchor="middle" fill="#E2E8F0" fontSize="12" fontWeight="600">
                {pos.unit}
              </text>
              <text x={pos.x + boxW / 2} y={pos.y + 52}
                textAnchor="middle" fill="#94A3B8" fontSize="10">
                {pos.connector} · {pos.wireCount} wire{pos.wireCount === 1 ? '' : 's'}
              </text>
            </g>
          ))}
        </svg>
      </div>

      {/* Wire detail popup on click */}
      {clickedWire && (
        <div className="fixed bottom-4 right-4 z-40 w-80 rounded-xl border border-blue-500/30 bg-astra-surface p-4 shadow-2xl">
          <div className="flex items-start justify-between mb-3">
            <div>
              <p className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">Wire</p>
              <p className="text-sm font-bold text-slate-100 font-mono">{clickedWire.wire_number}</p>
            </div>
            <button onClick={() => setClickedWire(null)}
              className="rounded p-1 text-slate-500 hover:text-slate-200">✕</button>
          </div>
          <dl className="space-y-1.5 text-[11px]">
            {clickedWire.signal_name && (
              <div className="flex justify-between gap-3">
                <dt className="text-slate-500">Signal</dt>
                <dd className="text-slate-200 text-right">{clickedWire.signal_name}</dd>
              </div>
            )}
            {clickedWire.wire_type && (
              <div className="flex justify-between gap-3">
                <dt className="text-slate-500">Type</dt>
                <dd className="text-slate-200 text-right">{clickedWire.wire_type.replace(/_/g, ' ')}</dd>
              </div>
            )}
            {clickedWire.wire_gauge && (
              <div className="flex justify-between gap-3">
                <dt className="text-slate-500">Gauge</dt>
                <dd className="text-slate-200 text-right">{clickedWire.wire_gauge.replace(/_/g, ' ')}</dd>
              </div>
            )}
            <div className="pt-2 mt-2 border-t border-astra-border">
              <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 font-semibold">From</p>
              <p className="text-slate-200">
                <span className="font-mono text-cyan-400">{clickedWire.from_unit_designation}</span>
                <span className="text-slate-600"> · </span>
                <span className="text-slate-400">{clickedWire.from_connector_designator}</span>
                <span className="text-slate-600"> · pin </span>
                <span className="font-mono text-slate-300">{clickedWire.from_pin_number}</span>
              </p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 font-semibold">To</p>
              <p className="text-slate-200">
                <span className="font-mono text-violet-400">{clickedWire.to_unit_designation}</span>
                <span className="text-slate-600"> · </span>
                <span className="text-slate-400">{clickedWire.to_connector_designator}</span>
                <span className="text-slate-600"> · pin </span>
                <span className="font-mono text-slate-300">{clickedWire.to_pin_number}</span>
              </p>
            </div>
          </dl>
        </div>
      )}
    </div>
  );
}

export default function HarnessDetailPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);
  const harnessId = Number(params.harnessId);
  const p = `/projects/${projectId}`;

  const [harness, setHarness]             = useState<WireHarnessDetail | null>(null);
  const [loading, setLoading]             = useState(true);
  const [viewMode, setViewMode]           = useState<ViewMode>('overview');
  const [msg, setMsg]                     = useState('');

  // Phase 3b: Overview edit state (inline form, not modal)
  const [editingOverview, setEditingOverview] = useState(false);
  const [overviewFields, setOverviewFields]   = useState<Record<string, any>>({});
  const [savingOverview, setSavingOverview]   = useState(false);
  const [overviewError, setOverviewError]     = useState('');

  // Phase 3b: Wires tab filters
  const [wireSearchFilter, setWireSearchFilter] = useState('');
  const [wireConnectorFilter, setWireConnectorFilter] = useState<number | ''>('');
  const [wireTypeFilter, setWireTypeFilter]    = useState('');

  // Phase 3b: Endpoints tab state
  const [deleteEndpointId, setDeleteEndpointId] = useState<number | null>(null);
  const [deletingEndpoint, setDeletingEndpoint] = useState(false);

  // Auto-wire
  const [autoWiring, setAutoWiring]       = useState(false);
  const [autoWireResult, setAutoWireResult] = useState<any>(null);
  // Wiring strategy picker — defaults to 'auto' which picks straight-through
  // for RJ-45 pairs and falls back to signal-name matching for everything else.
  const [wiringStrategy, setWiringStrategy] = useState<'auto' | 'by_signal' | 'straight_through' | 'crossover'>('auto');

  // Phase 3a: Ambiguity modal state. The auto-wire endpoint (routed through
  // the engine since Phase 2b) can surface ambiguities when a wire would
  // span two existing harnesses. We resolve them here via a sequential
  // modal, then the engine commits the whole batch once all decisions
  // are in.
  const ambiguityModal = useAmbiguityModal();

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
  // abortRef: a ref to the AbortController for the currently in-flight fetch.
  // On re-fetch or unmount, we abort the prior request. This prevents the
  // "Unhandled Runtime Error: AxiosError: Network Error" that fires when a
  // user navigates away mid-request — the canceled request's rejection was
  // surfacing on window.onunhandledrejection before our local .catch() ran.
  const abortRef = useRef<AbortController | null>(null);

  const fetchHarness = useCallback(async () => {
    // Cancel any previous in-flight fetch for this component
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    try {
      const [harnRes, linkRes] = await Promise.all([
        interfaceAPI.getHarness(harnessId, { signal: controller.signal } as any),
        interfaceAPI.listReqLinks(
          { entity_type: 'wire_harness', entity_id: harnessId },
          { signal: controller.signal } as any,
        ).catch(() => ({ data: [] })),
      ]);
      // If aborted between await and setState, bail
      if (controller.signal.aborted) return;
      setHarness(harnRes.data);
      setReqLinks(linkRes.data || []);
    } catch (e: any) {
      // Swallow aborts silently — they're expected on navigation/re-fetch.
      // Also tolerate Network Error without dropping it on the floor: leave
      // the existing harness visible (stale-while-error) and let the retry
      // button drive a re-fetch.
      const isAbort = e?.name === 'CanceledError' || e?.code === 'ERR_CANCELED' || e?.message === 'canceled';
      if (!isAbort) {
        // eslint-disable-next-line no-console
        console.warn('[harness] fetch failed:', e?.message || e);
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [harnessId]);

  useEffect(() => {
    fetchHarness();
    // Cleanup on unmount: cancel any in-flight request so its rejection
    // doesn't bubble up as an unhandled runtime error.
    return () => { abortRef.current?.abort(); };
  }, [fetchHarness]);

  // ══════════════════════════════════════
  //  T568B Wire Coloring (RJ-45 harnesses)
  // ══════════════════════════════════════
  //
  // Colors live on the `wires` table (wire_color_primary, wire_color_secondary,
  // wire_color_tertiary), NOT on pins. So T568B colors are applied here — once
  // wires exist, we look at the pin-to-pin mapping and color any 8-wire
  // straight-through RJ-45 harness per the T568B standard.
  //
  // Detection heuristic (no backend schema lookup needed):
  //   - Harness has exactly 8 wires
  //   - Each wire connects pin N to pin N where N ∈ {1..8}
  //
  // If the heuristic matches, apply the standard T568B color map. If not, we
  // leave wires uncolored. This is safe for any harness — non-RJ-45 harnesses
  // won't match the heuristic and nothing happens.
  const T568B_WIRE_COLORS: Record<string, { primary: string; secondary?: string }> = {
    '1': { primary: 'white',  secondary: 'orange' },
    '2': { primary: 'orange' },
    '3': { primary: 'white',  secondary: 'green'  },
    '4': { primary: 'blue'  },
    '5': { primary: 'white',  secondary: 'blue'   },
    '6': { primary: 'green' },
    '7': { primary: 'white',  secondary: 'brown'  },
    '8': { primary: 'brown' },
  };

  const applyT568BWireColors = async () => {
    try {
      const fresh = await interfaceAPI.getHarness(harnessId);
      const wires = (fresh.data as any)?.wires || [];

      // Heuristic check: 8 wires, straight-through pin mapping 1-8
      if (wires.length !== 8) return;
      const pinPairs = wires.map((w: any) => ({
        from: String(w.from_pin_number || ''),
        to: String(w.to_pin_number || ''),
      }));
      const isStraightThrough = pinPairs.every((p: any) =>
        p.from === p.to && ['1', '2', '3', '4', '5', '6', '7', '8'].includes(p.from)
      );
      if (!isStraightThrough) return;

      const anyApi = interfaceAPI as any;
      if (typeof anyApi.updateWire !== 'function') {
        // eslint-disable-next-line no-console
        console.info('[T568B] interfaceAPI.updateWire not available — wire colors not applied.');
        return;
      }

      // Apply colors per pin number
      for (const w of wires) {
        const pinNum = String(w.from_pin_number || '');
        const color = T568B_WIRE_COLORS[pinNum];
        if (!color) continue;
        try {
          await anyApi.updateWire(w.id, {
            wire_color_primary: color.primary,
            wire_color_secondary: color.secondary || null,
          });
        } catch (err) {
          // eslint-disable-next-line no-console
          console.warn(`[T568B] wire ${pinNum} color update failed`, err);
        }
      }
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('[T568B] wire color pass failed', err);
    }
  };

  // ── Auto-Wire ──
  const handleAutoWire = async () => {
    setAutoWiring(true);
    setAutoWireResult(null);
    setGenReqResult(null);
    try {
      const res = await interfaceAPI.autoWire(harnessId, wiringStrategy);

      // Phase 3a: the auto-wire endpoint (routed through the auto-grow
      // engine since Phase 2b) may return an `ambiguities` list instead
      // of creating wires when a pair would span two harnesses. Surface
      // the modal and let the user resolve them sequentially.
      const data: any = res.data;
      if (data?.ambiguities && Array.isArray(data.ambiguities) && data.ambiguities.length > 0) {
        // Build the original pair list from the server's ambiguity entries.
        // The engine remembers each pair by its submitted pin ids, so we
        // pass those through unchanged when re-submitting decisions via
        // /interfaces/auto-grow.
        const pairs: AutoGrowPair[] = data.ambiguities.map((a: any) => ({
          from_lru_pin_id: a.from_lru_pin_id,
          to_lru_pin_id: a.to_lru_pin_id,
        }));
        setAutoWiring(false);
        ambiguityModal.start({
          projectId,
          pairs,
          ambiguities: data.ambiguities,
          onDone: (result) => {
            // After all ambiguities resolved, refresh harness to pick up
            // whatever got created on THIS harness (the resolution might
            // have merged or spun off a different harness — the user may
            // need to navigate there separately).
            setAutoWireResult({
              matched: result.wires_created,
              wires_created: [],
              strategy: wiringStrategy,
              strategy_requested: wiringStrategy,
              resolved_via_modal: true,
            });
            fetchHarness();
            if (result.new_harness_ids.length > 0) {
              flash(
                `${result.wires_created} wires created. ` +
                `New harness(es) created: ${result.new_harness_ids.join(', ')}.`
              );
            }
          },
          onCancelled: () => {
            flash('Auto-wire cancelled — no wires created.');
          },
        });
        return;
      }

      setAutoWireResult(data);
      // Auto-wire response includes auto_requirements field from backend
      if (data?.auto_requirements) {
        setGenReqResult(data.auto_requirements);
      }
      // If this looks like an 8P8C RJ-45 harness (8 straight-through wires),
      // apply T568B colors. Safe no-op on non-RJ-45 harnesses.
      await applyT568BWireColors();
      fetchHarness();
    } catch (e: any) {
      flash(formatApiError(e, 'Auto-wire failed'));
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
      const fallback = e?.message === 'Network Error'
        ? 'Network error — the request never reached the backend. Check that astra-backend-1 is running (docker compose ps), and check DevTools → Network for the status code.'
        : 'Generation failed';
      setGenReqResult({ requirements_generated: 0, error: formatApiError(e, fallback) });
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

  // ══════════════════════════════════════════════════════════════
  //  Phase 3b memos — MUST live above the early returns below.
  //  React's rules of hooks: hooks must be called in the same order
  //  on every render. If we put these after `if (loading) return`, the
  //  first render (with loading=true) skips them, then the second
  //  render (with loading=false) calls them, and React panics with
  //  "Rendered more hooks than during the previous render."
  //
  //  Each memo handles harness being null/undefined gracefully so the
  //  loading-render is happy. The early-returns below still bail out
  //  before the memo values get read.
  // ══════════════════════════════════════════════════════════════

  /** LRU-side connectors plugged into this harness (one per endpoint). */
  const wireConnectorOptions = useMemo(() => {
    if (!harness?.endpoints || harness.endpoints.length === 0) return [];
    return harness.endpoints
      .filter(e => e.lru_connector_id && e.lru_connector_designator)
      .map(e => ({
        id: e.lru_connector_id!,
        // "FCC.J1" — friendlier than a bare designator when multiple LRUs
        // have a "J1" connector
        label: `${e.lru_unit_designation || '?'}.${e.lru_connector_designator}`,
      }));
  }, [harness?.endpoints]);

  const wireTypeOptions = useMemo(() => {
    const s = new Set<string>();
    for (const w of (harness?.wires || [])) if (w.wire_type) s.add(w.wire_type);
    return [...s].sort();
  }, [harness?.wires]);

  const filteredWires = useMemo(() => {
    return (harness?.wires || []).filter(w => {
      if (wireSearchFilter) {
        const q = wireSearchFilter.toLowerCase();
        const hit =
          (w.wire_number || '').toLowerCase().includes(q) ||
          (w.signal_name || '').toLowerCase().includes(q) ||
          (w.from_pin_number || '').toLowerCase().includes(q) ||
          (w.to_pin_number || '').toLowerCase().includes(q) ||
          (w.from_connector_designator || '').toLowerCase().includes(q) ||
          (w.to_connector_designator || '').toLowerCase().includes(q) ||
          (w.from_unit_designation || '').toLowerCase().includes(q) ||
          (w.to_unit_designation || '').toLowerCase().includes(q);
        if (!hit) return false;
      }
      if (wireConnectorFilter !== '') {
        // Match by designator since Wire doesn't carry a connector_id —
        // the responses populate from/to_connector_designator instead.
        const sel = wireConnectorOptions.find(c => c.id === wireConnectorFilter);
        if (sel) {
          const [selUnit, selDesig] = sel.label.split('.');
          const fromMatch = (w.from_unit_designation === selUnit) && (w.from_connector_designator === selDesig);
          const toMatch = (w.to_unit_designation === selUnit) && (w.to_connector_designator === selDesig);
          if (!fromMatch && !toMatch) return false;
        }
      }
      if (wireTypeFilter && w.wire_type !== wireTypeFilter) return false;
      return true;
    });
  }, [harness?.wires, wireSearchFilter, wireConnectorFilter, wireTypeFilter, wireConnectorOptions]);

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

  // Phase 3b: Endpoint delete flow. Delete confirms first (backend
  // requires confirm=true when wires will be cascaded), then removes
  // the endpoint + its mating connector + any wires touching it.
  const handleConfirmDeleteEndpoint = async () => {
    if (deleteEndpointId === null) return;
    setDeletingEndpoint(true);
    try {
      await interfaceAPI.deleteHarnessEndpoint(deleteEndpointId, true);
      setDeleteEndpointId(null);
      flash('Endpoint deleted.');
      await fetchHarness();
    } catch (e: any) {
      flash(formatApiError(e, 'Delete failed'));
    }
    setDeletingEndpoint(false);
  };

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
      <div className="mb-5 flex flex-wrap items-center gap-3">
        {/* Auto-Wire group: strategy picker + trigger button share a visual unit */}
        <div className="flex items-stretch overflow-hidden rounded-lg border border-emerald-500/30">
          <select
            value={wiringStrategy}
            onChange={(e) => setWiringStrategy(e.target.value as any)}
            disabled={autoWiring}
            title="Wiring strategy"
            className="border-r border-emerald-500/30 bg-astra-surface px-3 py-2.5 text-xs font-semibold text-emerald-300 outline-none transition hover:bg-astra-surface-alt focus:bg-astra-surface-alt disabled:opacity-40 cursor-pointer"
          >
            <option value="auto">Auto (smart default)</option>
            <option value="by_signal">Match by signal name</option>
            <option value="straight_through">Straight-through (1→1, 2→2…)</option>
            <option value="crossover">T568B crossover (RJ-45 only)</option>
          </select>
          <button
            onClick={handleAutoWire}
            disabled={autoWiring}
            className="flex items-center gap-1.5 bg-emerald-600 px-4 py-2.5 text-xs font-semibold text-white transition hover:bg-emerald-500 disabled:opacity-40"
          >
            {autoWiring ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Zap className="h-3.5 w-3.5" />}
            Auto-Wire
          </button>
        </div>

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
          <div className="mb-2 flex items-center gap-2">
            <CheckCircle className="h-4 w-4 text-emerald-400" />
            <span className="text-sm font-semibold text-emerald-400">Auto-Wire Complete</span>
            {autoWireResult.strategy && (
              <span className="ml-auto rounded-full bg-emerald-500/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-emerald-300">
                {String(autoWireResult.strategy).replace(/_/g, ' ')}
              </span>
            )}
          </div>
          <div className="space-y-1 text-[12px] text-slate-400">
            {(() => {
              // Explain what the strategy did, in one sentence
              const strat = autoWireResult.strategy;
              const matched = autoWireResult.matched || 0;
              const noun = matched === 1 ? 'wire' : 'wires';
              if (strat === 'straight_through') {
                return <p>Created {matched} {noun} pin-to-pin (1→1, 2→2, …) — ignoring signal names.</p>;
              }
              if (strat === 'crossover') {
                return <p>Created {matched} {noun} with T568B crossover (TX/RX pairs swapped).</p>;
              }
              return <p>Matched {matched} signal{matched === 1 ? '' : 's'} by name.</p>;
            })()}
            {autoWireResult.strategy_requested === 'auto' && autoWireResult.strategy !== 'by_signal' && (
              <p className="text-[11px] text-slate-500">
                (Auto-detected from connector types — pick a different strategy above to override.)
              </p>
            )}
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

        const retry = () => { setGenReqResult(null); setErrorExpanded(false); handleGenerateReqs(); };

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
      <div className="mb-4 flex gap-1 border-b border-astra-border overflow-x-auto">
        {([
          { key: 'overview' as ViewMode, label: 'Overview' },
          { key: 'wires' as ViewMode, label: `Wires (${wireCount})` },
          { key: 'pinmap' as ViewMode, label: 'Pin Map' },
          { key: 'endpoints' as ViewMode, label: `Endpoints (${harness.endpoints?.length || 0})` },
          { key: 'signals' as ViewMode, label: 'Signals' },
        ]).map(t => (
          <button key={t.key} onClick={() => setViewMode(t.key)}
            className={clsx('border-b-2 px-4 py-2.5 text-xs font-semibold transition whitespace-nowrap',
              viewMode === t.key ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-500 hover:text-slate-300')}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ══════════════════════════════════════ */}
      {/*  OVERVIEW VIEW (Phase 3b)              */}
      {/* ══════════════════════════════════════ */}
      {viewMode === 'overview' && (
        <HarnessOverviewPanel
          harness={harness}
          editing={editingOverview}
          fields={overviewFields}
          setFields={setOverviewFields}
          saving={savingOverview}
          error={overviewError}
          onStartEdit={() => {
            setOverviewFields({
              name:                harness.name || '',
              harness_id:          harness.harness_id || '',
              description:         harness.description || '',
              cable_part_number:   harness.cable_part_number || '',
              cable_manufacturer:  harness.cable_manufacturer || '',
              overall_length_m:    harness.overall_length_m ?? '',
              mass_kg:             harness.mass_kg ?? '',
              outer_diameter_mm:   harness.outer_diameter_mm ?? '',
              status:              harness.status || 'concept',
              drawing_number:      harness.drawing_number || '',
              drawing_revision:    harness.drawing_revision || '',
              // Phase 1+3b additions
              shielding_class:     harness.shielding_class || '',
              jacket_material:     harness.jacket_material || '',
              sleeve_type:         harness.sleeve_type || '',
              operating_temp_min_c: harness.operating_temp_min_c ?? '',
              operating_temp_max_c: harness.operating_temp_max_c ?? '',
              min_bend_radius_mm:  harness.min_bend_radius_mm ?? '',
              weight_g_per_m:      harness.weight_g_per_m ?? '',
              drain_wire_spec:     harness.drain_wire_spec || '',
              service_loop_m:      harness.service_loop_m ?? '',
              mil_spec:            harness.mil_spec || '',
              jacket_color:        harness.jacket_color || '',
              voltage_rating_v:    harness.voltage_rating_v ?? '',
            });
            setOverviewError('');
            setEditingOverview(true);
          }}
          onCancel={() => {
            setEditingOverview(false);
            setOverviewError('');
          }}
          onSave={async () => {
            setSavingOverview(true);
            setOverviewError('');
            try {
              // Build payload: '' → null for nullable fields so users can
              // clear a value, numeric strings → numbers, everything else
              // passes through. Required field 'name' is protected from
              // being cleared to null.
              const payload: Record<string, any> = {};
              const REQUIRED = new Set(['name']);
              const NUMERIC = new Set([
                'overall_length_m', 'mass_kg', 'outer_diameter_mm',
                'operating_temp_min_c', 'operating_temp_max_c',
                'min_bend_radius_mm', 'weight_g_per_m', 'service_loop_m',
                'voltage_rating_v',
              ]);
              for (const [k, v] of Object.entries(overviewFields)) {
                if (v === '' || v === null || v === undefined) {
                  if (REQUIRED.has(k)) continue;
                  payload[k] = null;
                } else if (NUMERIC.has(k)) {
                  const n = Number(v);
                  payload[k] = Number.isFinite(n) ? n : null;
                } else {
                  payload[k] = v;
                }
              }
              await interfaceAPI.updateHarness(harnessId, payload);
              await fetchHarness();
              setEditingOverview(false);
              flash('Harness updated.');
            } catch (e: any) {
              setOverviewError(formatApiError(e, 'Update failed'));
            }
            setSavingOverview(false);
          }}
        />
      )}

      {/* ══════════════════════════════════════ */}
      {/*  WIRES VIEW                            */}
      {/* ══════════════════════════════════════ */}
      {viewMode === 'wires' && (
        wireCount === 0 ? (
          <div className="py-16 text-center rounded-xl border border-astra-border bg-astra-surface">
            <Cable className="mx-auto h-10 w-10 text-slate-600 mb-3" />
            <p className="text-sm text-slate-400 mb-1">No wires yet.</p>
            <p className="text-[11px] text-slate-500">
              Click &quot;Auto-Wire&quot; to create wires by matching signal names between the two connectors.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {/* Phase 3b: filter toolbar. Lets users narrow the wire list
                by connector (useful on big multi-endpoint harnesses),
                wire type, or free-text search across signal/wire number. */}
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative flex-1 min-w-[200px] max-w-md">
                <input
                  value={wireSearchFilter}
                  onChange={e => setWireSearchFilter(e.target.value)}
                  placeholder="Search wires (number, signal, pin)…"
                  className="w-full rounded-lg border border-astra-border bg-astra-surface px-3 py-1.5 text-xs text-slate-200 outline-none focus:border-blue-500/50"
                />
              </div>
              {wireConnectorOptions.length > 0 && (
                <select
                  value={wireConnectorFilter}
                  onChange={e => setWireConnectorFilter(e.target.value ? Number(e.target.value) : '')}
                  className="rounded-lg border border-astra-border bg-astra-surface px-2.5 py-1.5 text-xs text-slate-300 outline-none focus:border-blue-500/50">
                  <option value="">All connectors</option>
                  {wireConnectorOptions.map(c => (
                    <option key={c.id} value={c.id}>{c.label}</option>
                  ))}
                </select>
              )}
              {wireTypeOptions.length > 1 && (
                <select
                  value={wireTypeFilter}
                  onChange={e => setWireTypeFilter(e.target.value)}
                  className="rounded-lg border border-astra-border bg-astra-surface px-2.5 py-1.5 text-xs text-slate-300 outline-none focus:border-blue-500/50">
                  <option value="">All types</option>
                  {wireTypeOptions.map(t => (
                    <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
                  ))}
                </select>
              )}
              <div className="flex-1" />
              <span className="text-[10px] text-slate-500">
                {filteredWires.length} of {wireCount}
              </span>
            </div>

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
                {filteredWires.map(w => {
                  // Phase 3 — INTF-002: dual-name secondary line.
                  // Backend may surface the wire's catalog mfr names via these
                  // fields (not yet in WireResponse schema; safe fallback to
                  // undefined when absent — pre-INTF-002 wires render only the
                  // existing internal signal_name without the secondary line).
                  const augmented = w as typeof w & {
                    from_mfr_pin_name?: string | null;
                    to_mfr_pin_name?: string | null;
                  };
                  const mfrSubtitle = augmented.from_mfr_pin_name || augmented.to_mfr_pin_name;
                  return (
                  <tr key={w.id} className="border-b border-astra-border/50 hover:bg-astra-surface-alt/50 transition">
                    <td className="px-3 py-2 font-mono font-bold text-slate-300">{w.wire_number}</td>
                    <td className="px-3 py-2">
                      <div className="font-semibold text-slate-200">{w.signal_name}</div>
                      {mfrSubtitle && (
                        <div className="text-[10px] font-mono text-slate-500" title="Manufacturer pin name from catalog">
                          mfr: {mfrSubtitle}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1.5">
                        <WireColor type={w.wire_type} signalType={w.signal_type} />
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
                  );
                })}
              </tbody>
            </table>
          </div>
          </div>
        )
      )}
      {/* ══════════════════════════════════════ */}
      {/*  PIN MAP VIEW (Phase 3b: multi-endpoint aware)  */}
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
                {harness.endpoints && harness.endpoints.length > 2 && (
                  <span className="ml-2 text-amber-400">
                    · {harness.endpoints.length} endpoints
                  </span>
                )}
              </h3>
              <span className="text-[10px] text-slate-600">
                Hover a trace for details · click for wire card
              </span>
            </div>
            {/* Route to the right layout based on endpoint count. The
                classic 2-endpoint PinMapSvg draws a clean left/right layout.
                For 3+ endpoints, MultiEndpointPinMap radiates endpoints
                around a central hub. */}
            {harness.endpoints && harness.endpoints.length > 2 ? (
              <MultiEndpointPinMap
                harness={harness}
                hoveredWireId={hoveredWireId}
                onHover={setHoveredWireId}
              />
            ) : (
              <PinMapSvg
                harness={harness}
                hoveredWireId={hoveredWireId}
                onHover={setHoveredWireId}
              />
            )}
          </div>
        )
      )}

      {/* ══════════════════════════════════════ */}
      {/*  ENDPOINTS VIEW (Phase 3b)             */}
      {/* ══════════════════════════════════════ */}
      {viewMode === 'endpoints' && (
        <HarnessEndpointsPanel
          harness={harness}
          projectPath={p}
          onDeleteEndpoint={(id) => setDeleteEndpointId(id)}
          router={router}
        />
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

      {/* Phase 3a: Ambiguity modal — rendered at root so it overlays
          everything. Shown only when state.open is true (auto-wire
          triggered ambiguity resolution). */}
      <AutoGrowAmbiguityModal
        state={ambiguityModal.state}
        onResolve={ambiguityModal.resolveCurrent}
        onCancel={ambiguityModal.cancel}
      />

      {/* Phase 3b: Endpoint delete confirmation. Separate modal because
          the consequence (cascading wires + mating connector) is big
          enough to warrant an explicit yes. */}
      {deleteEndpointId !== null && (() => {
        const ep = harness.endpoints?.find(e => e.id === deleteEndpointId);
        if (!ep) return null;
        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
            <div className="w-full max-w-md rounded-xl border border-red-500/30 bg-astra-surface p-5">
              <div className="flex items-start gap-3 mb-3">
                <AlertTriangle className="h-5 w-5 text-red-400 flex-shrink-0 mt-0.5" />
                <div>
                  <h3 className="text-sm font-bold text-slate-100">Delete Endpoint?</h3>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    Endpoint <span className="font-mono text-slate-300">{ep.label || `P${ep.id}`}</span>
                    {' '}— {ep.lru_unit_designation}.{ep.lru_connector_designator}
                  </p>
                </div>
              </div>
              <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2 mb-4">
                <p className="text-[11px] text-red-300">
                  This removes the mating connector, all its cloned pins, and
                  {' '}<span className="font-bold">{ep.wire_count || 0} wire{ep.wire_count === 1 ? '' : 's'}</span>
                  {' '}touching this endpoint. This cannot be undone.
                </p>
              </div>
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setDeleteEndpointId(null)}
                  disabled={deletingEndpoint}
                  className="rounded-lg border border-astra-border px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-astra-surface-alt disabled:opacity-40">
                  Cancel
                </button>
                <button
                  onClick={handleConfirmDeleteEndpoint}
                  disabled={deletingEndpoint}
                  className="flex items-center gap-1.5 rounded-lg bg-red-500 px-4 py-1.5 text-xs font-semibold text-white hover:bg-red-600 disabled:opacity-40">
                  {deletingEndpoint ? (
                    <><Loader2 className="h-3 w-3 animate-spin" /> Deleting…</>
                  ) : (
                    <><Trash2 className="h-3 w-3" /> Delete Endpoint</>
                  )}
                </button>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}
