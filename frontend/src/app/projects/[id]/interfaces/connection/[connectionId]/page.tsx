'use client';

/**
 * ASTRA — Connection Detail Page
 * ==================================
 * File: frontend/src/app/projects/[id]/interfaces/connection/[connectionId]/page.tsx
 *
 * A Connection is a bidirectional "these two LRUs are wired together" rollup.
 * Auto-created and auto-maintained by the wire-create/delete flow. This page
 * shows:
 *
 *   — Summary header: the two LRUs, total wire count, which harnesses carry
 *     the wires between them
 *   — One pin-map section PER connector-pair. If LRU-A has J1 and J2 that
 *     both land on LRU-B's P1, that's two separate pin maps — they're
 *     physically different connectors even though they're both between the
 *     same pair of LRUs.
 *   — A flat wire list at the bottom with filters
 *
 * We avoid arrow language ("A → B"). Connections are symmetric: "A — B".
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft, Loader2, RefreshCw, Cable, Search, ChevronRight,
  Circle, AlertTriangle,
} from 'lucide-react';
import clsx from 'clsx';
import { interfaceAPI } from '@/lib/interface-api';
import { formatApiError } from '@/lib/errors';
import type { ConnectionDetail, Wire } from '@/lib/interface-types';

// ══════════════════════════════════════════════════════════════
//  Wire-type color — shared with the harness page's conventions
// ══════════════════════════════════════════════════════════════

/** Color for a wire strand in the pin map, chosen from signal_type first,
 *  then wire_type. Matches the rest of the app so visual identity is
 *  consistent across pages. */
function wireColorForWire(w: Wire): string {
  const wt = (w.wire_type || '').toLowerCase();
  if (wt.startsWith('power_positive')) return '#EF4444';
  if (wt.startsWith('power_negative')) return '#3B82F6';
  if (wt.startsWith('power_return') || wt.startsWith('ground')) return '#6B7280';
  if (wt.startsWith('shield')) return '#9CA3AF';
  if (wt.startsWith('coax')) return '#F59E0B';
  if (wt.startsWith('fiber')) return '#EC4899';
  if (wt.startsWith('signal_twisted')) return '#10B981';
  if (wt.startsWith('signal_shielded')) return '#06B6D4';
  if (wt === 'spare') return '#64748B';
  if (wt === 'jumper') return '#A855F7';
  return '#60A5FA';
}

// ══════════════════════════════════════════════════════════════
//  Pin Map SVG — renders one connector pair
// ══════════════════════════════════════════════════════════════

/**
 * Interactive pin map for one connector pair. Renders the two connectors
 * side-by-side with their pins, draws wires between them, and supports:
 *
 *   — Hover any wire → the whole line + its endpoint pins light up
 *   — Click any wire → pop up a detail card with wire metadata
 *
 * This is the "(iii) Interactive" version Mason picked in the scope
 * discussion. It reuses the color scheme from the harness page so the
 * same wire looks the same everywhere.
 */
function ConnectorPairPinMap({
  leftLabel, rightLabel,
  leftPins, rightPins,
  wires,
  onWireClick,
  hoveredWireId, onHoverWire,
}: {
  leftLabel: string;
  rightLabel: string;
  /** Distinct pin numbers (as strings) on the left-side connector, ordered
   *  as they should appear top-to-bottom. */
  leftPins: string[];
  rightPins: string[];
  /** Wires touching this connector pair. Each wire contributes one line. */
  wires: Wire[];
  onWireClick: (wire: Wire) => void;
  hoveredWireId: number | null;
  onHoverWire: (id: number | null) => void;
}) {
  const ROW_H = 28;
  const HEADER_H = 32;
  const padTop = 18;
  const padSide = 24;
  const boxW = 150;
  const gap = 180;
  const rows = Math.max(leftPins.length, rightPins.length);
  const height = padTop + HEADER_H + rows * ROW_H + 16;
  const width = padSide * 2 + boxW * 2 + gap;

  const leftBoxX = padSide;
  const rightBoxX = padSide + boxW + gap;

  // Map pin_number → row index (y coordinate) for fast lookup when drawing lines
  const leftRow: Record<string, number> = {};
  leftPins.forEach((pn, i) => { leftRow[pn] = i; });
  const rightRow: Record<string, number> = {};
  rightPins.forEach((pn, i) => { rightRow[pn] = i; });

  const pinY = (row: number) => padTop + HEADER_H + row * ROW_H + ROW_H / 2;

  return (
    <div className="overflow-x-auto rounded-xl border border-astra-border bg-astra-surface p-4">
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="font-mono"
        style={{ maxWidth: '100%' }}>
        {/* Connector frames */}
        <g>
          {/* Left */}
          <rect
            x={leftBoxX}
            y={padTop}
            width={boxW}
            height={HEADER_H + rows * ROW_H}
            rx={8}
            className="fill-astra-bg stroke-astra-border" strokeWidth={1}
          />
          <text
            x={leftBoxX + boxW / 2}
            y={padTop + 20}
            textAnchor="middle"
            className="fill-slate-300 text-[11px] font-bold">
            {leftLabel}
          </text>
          <line
            x1={leftBoxX + 8}
            x2={leftBoxX + boxW - 8}
            y1={padTop + HEADER_H - 4}
            y2={padTop + HEADER_H - 4}
            className="stroke-astra-border" strokeWidth={1}
          />

          {/* Right */}
          <rect
            x={rightBoxX}
            y={padTop}
            width={boxW}
            height={HEADER_H + rows * ROW_H}
            rx={8}
            className="fill-astra-bg stroke-astra-border" strokeWidth={1}
          />
          <text
            x={rightBoxX + boxW / 2}
            y={padTop + 20}
            textAnchor="middle"
            className="fill-slate-300 text-[11px] font-bold">
            {rightLabel}
          </text>
          <line
            x1={rightBoxX + 8}
            x2={rightBoxX + boxW - 8}
            y1={padTop + HEADER_H - 4}
            y2={padTop + HEADER_H - 4}
            className="stroke-astra-border" strokeWidth={1}
          />
        </g>

        {/* Left pins */}
        {leftPins.map((pn, i) => {
          const y = pinY(i);
          // Find the wire for this pin on the left side. Null if spare.
          const wire = wires.find(
            w => w.from_connector_designator === leftLabel
              ? w.from_pin_number === pn
              : w.to_pin_number === pn
          );
          const isHovered = wire && hoveredWireId === wire.id;
          return (
            <g key={`L-${pn}`}>
              <text
                x={leftBoxX + 10}
                y={y + 4}
                className={clsx(
                  'text-[11px]',
                  isHovered ? 'fill-amber-300 font-bold' : 'fill-slate-500',
                )}>
                {pn}
              </text>
              <text
                x={leftBoxX + 34}
                y={y + 4}
                className={clsx(
                  'text-[10px]',
                  isHovered ? 'fill-slate-100' : 'fill-slate-400',
                )}>
                {wire
                  ? (wire.from_connector_designator === leftLabel
                      ? wire.from_signal_name || ''
                      : wire.to_signal_name || '')
                  : ''}
              </text>
              {/* Pin dot at the connector's right edge */}
              <circle
                cx={leftBoxX + boxW - 6}
                cy={y}
                r={3}
                fill={wire ? wireColorForWire(wire) : '#334155'}
              />
            </g>
          );
        })}

        {/* Right pins */}
        {rightPins.map((pn, i) => {
          const y = pinY(i);
          const wire = wires.find(
            w => w.to_connector_designator === rightLabel
              ? w.to_pin_number === pn
              : w.from_pin_number === pn
          );
          const isHovered = wire && hoveredWireId === wire.id;
          return (
            <g key={`R-${pn}`}>
              <circle
                cx={rightBoxX + 6}
                cy={y}
                r={3}
                fill={wire ? wireColorForWire(wire) : '#334155'}
              />
              <text
                x={rightBoxX + 14}
                y={y + 4}
                className={clsx(
                  'text-[10px]',
                  isHovered ? 'fill-slate-100' : 'fill-slate-400',
                )}>
                {wire
                  ? (wire.to_connector_designator === rightLabel
                      ? wire.to_signal_name || ''
                      : wire.from_signal_name || '')
                  : ''}
              </text>
              <text
                x={rightBoxX + boxW - 10}
                y={y + 4}
                textAnchor="end"
                className={clsx(
                  'text-[11px]',
                  isHovered ? 'fill-amber-300 font-bold' : 'fill-slate-500',
                )}>
                {pn}
              </text>
            </g>
          );
        })}

        {/* Wire lines between pins */}
        {wires.map(w => {
          // The caller passed wires that touch this pair. But a wire's
          // from-side might be the RIGHT connector in this rendering, so
          // we look up by designator to figure out which pin number on
          // each side we're drawing between.
          const fromIsLeft = w.from_connector_designator === leftLabel;
          const leftPinNum = fromIsLeft ? w.from_pin_number : w.to_pin_number;
          const rightPinNum = fromIsLeft ? w.to_pin_number : w.from_pin_number;
          if (!leftPinNum || !rightPinNum) return null;
          const ly = leftRow[leftPinNum] !== undefined ? pinY(leftRow[leftPinNum]) : null;
          const ry = rightRow[rightPinNum] !== undefined ? pinY(rightRow[rightPinNum]) : null;
          if (ly === null || ry === null) return null;
          const isHovered = hoveredWireId === w.id;
          return (
            <line
              key={w.id}
              x1={leftBoxX + boxW - 6}
              y1={ly}
              x2={rightBoxX + 6}
              y2={ry}
              stroke={wireColorForWire(w)}
              strokeWidth={isHovered ? 3 : 1.5}
              opacity={hoveredWireId !== null && !isHovered ? 0.25 : 0.9}
              style={{ cursor: 'pointer', transition: 'stroke-width 120ms, opacity 120ms' }}
              onMouseEnter={() => onHoverWire(w.id)}
              onMouseLeave={() => onHoverWire(null)}
              onClick={() => onWireClick(w)}
            />
          );
        })}
      </svg>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
//  Wire detail popup — shown on click
// ══════════════════════════════════════════════════════════════

function WireDetailPopup({ wire, onClose }: { wire: Wire; onClose: () => void }) {
  return (
    <div className="fixed bottom-4 right-4 z-40 w-80 rounded-xl border border-blue-500/30 bg-astra-surface p-4 shadow-2xl">
      <div className="flex items-start justify-between mb-3">
        <div>
          <p className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">Wire</p>
          <p className="text-sm font-bold text-slate-100 font-mono">{wire.wire_number}</p>
        </div>
        <button onClick={onClose}
          className="rounded p-1 text-slate-500 hover:text-slate-200">✕</button>
      </div>

      <dl className="space-y-1.5 text-[11px]">
        <Row label="Signal"      value={wire.signal_name} />
        <Row label="Type"        value={wire.wire_type?.replace(/_/g, ' ')} />
        <Row label="Gauge"       value={wire.wire_gauge?.replace(/_/g, ' ')} />
        <Row label="Length"      value={wire.length_m != null ? `${wire.length_m} m` : undefined} />
        <div className="pt-2 mt-2 border-t border-astra-border">
          <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 font-semibold">From</p>
          <p className="text-slate-200">
            <span className="font-mono text-cyan-400">{wire.from_unit_designation}</span>
            {' · '}
            <span className="text-slate-400">{wire.from_connector_designator}</span>
            {' · pin '}
            <span className="font-mono text-slate-300">{wire.from_pin_number}</span>
          </p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 font-semibold">To</p>
          <p className="text-slate-200">
            <span className="font-mono text-violet-400">{wire.to_unit_designation}</span>
            {' · '}
            <span className="text-slate-400">{wire.to_connector_designator}</span>
            {' · pin '}
            <span className="font-mono text-slate-300">{wire.to_pin_number}</span>
          </p>
        </div>
        {wire.notes && (
          <div className="pt-2 mt-2 border-t border-astra-border">
            <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 font-semibold">Notes</p>
            <p className="text-slate-300">{wire.notes}</p>
          </div>
        )}
      </dl>
    </div>
  );
}

function Row({ label, value }: { label: string; value?: string | null }) {
  if (value === undefined || value === null || value === '') return null;
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-slate-200 text-right">{value}</dd>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
//  Main page
// ══════════════════════════════════════════════════════════════

export default function ConnectionDetailPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);
  const connectionId = Number(params.connectionId);
  const p = `/projects/${projectId}`;

  const [conn, setConn] = useState<ConnectionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters on the flat wire list
  const [wireSearch, setWireSearch] = useState('');
  const [harnessFilter, setHarnessFilter] = useState<number | ''>('');
  const [typeFilter, setTypeFilter] = useState('');

  // Pin-map interaction state
  const [hoveredWireId, setHoveredWireId] = useState<number | null>(null);
  const [clickedWire, setClickedWire] = useState<Wire | null>(null);

  const fetchConnection = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await interfaceAPI.getConnection(connectionId);
      setConn(res.data);
    } catch (e: any) {
      setError(formatApiError(e, 'Failed to load connection'));
    }
    setLoading(false);
  }, [connectionId]);

  useEffect(() => { fetchConnection(); }, [fetchConnection]);

  // Group wires by connector pair. Two wires belong in the same group if
  // they share {from_connector_designator, to_connector_designator} (as an
  // unordered pair — a wire going LRU-A.J1 → LRU-B.P1 and another going
  // LRU-B.P1 → LRU-A.J1 should end up in the same group).
  const connectorPairGroups = useMemo(() => {
    if (!conn?.wires) return [];
    const groups = new Map<string, {
      key: string;
      leftLabel: string;
      rightLabel: string;
      leftUnit: string;
      rightUnit: string;
      leftPinSet: Set<string>;
      rightPinSet: Set<string>;
      wires: Wire[];
    }>();

    for (const w of conn.wires) {
      const fromDesig = w.from_connector_designator || '?';
      const toDesig = w.to_connector_designator || '?';
      // Canonical key: alphabetical order of designators so A-B and B-A
      // collapse to one group. We also remember which side was which unit
      // so the rendering can assign LRU-a to the left consistently.
      const leftDesig = fromDesig < toDesig ? fromDesig : toDesig;
      const rightDesig = fromDesig < toDesig ? toDesig : fromDesig;
      const key = `${leftDesig}||${rightDesig}`;

      let group = groups.get(key);
      if (!group) {
        const leftUnit = fromDesig < toDesig
          ? w.from_unit_designation || ''
          : w.to_unit_designation || '';
        const rightUnit = fromDesig < toDesig
          ? w.to_unit_designation || ''
          : w.from_unit_designation || '';
        group = {
          key,
          leftLabel: leftDesig,
          rightLabel: rightDesig,
          leftUnit,
          rightUnit,
          leftPinSet: new Set<string>(),
          rightPinSet: new Set<string>(),
          wires: [],
        };
        groups.set(key, group);
      }
      group.wires.push(w);

      // Collect pin numbers for each side. We need both so the pin map
      // can render spare pins (pins on the connector not involved in
      // any wire) alongside the connected ones.
      const fromIsLeft = fromDesig === leftDesig;
      if (fromIsLeft) {
        if (w.from_pin_number) group.leftPinSet.add(w.from_pin_number);
        if (w.to_pin_number) group.rightPinSet.add(w.to_pin_number);
      } else {
        if (w.from_pin_number) group.rightPinSet.add(w.from_pin_number);
        if (w.to_pin_number) group.leftPinSet.add(w.to_pin_number);
      }
    }

    // Sort pins numerically where possible, alphabetically otherwise
    const sortPins = (set: Set<string>): string[] => {
      return [...set].sort((a, b) => {
        const na = parseInt(a, 10);
        const nb = parseInt(b, 10);
        if (!isNaN(na) && !isNaN(nb)) return na - nb;
        return a.localeCompare(b);
      });
    };

    return [...groups.values()].map(g => ({
      key: g.key,
      leftLabel: g.leftLabel,
      rightLabel: g.rightLabel,
      leftUnit: g.leftUnit,
      rightUnit: g.rightUnit,
      leftPins: sortPins(g.leftPinSet),
      rightPins: sortPins(g.rightPinSet),
      wires: g.wires,
    }));
  }, [conn]);

  // Filtered flat wire list
  const filteredWires = useMemo(() => {
    const source = conn?.wires || [];
    return source.filter(w => {
      if (wireSearch) {
        const q = wireSearch.toLowerCase();
        const hit =
          (w.wire_number || '').toLowerCase().includes(q) ||
          (w.signal_name || '').toLowerCase().includes(q) ||
          (w.from_connector_designator || '').toLowerCase().includes(q) ||
          (w.to_connector_designator || '').toLowerCase().includes(q);
        if (!hit) return false;
      }
      if (harnessFilter !== '' && w.harness_id !== harnessFilter) return false;
      if (typeFilter && w.wire_type !== typeFilter) return false;
      return true;
    });
  }, [conn, wireSearch, harnessFilter, typeFilter]);

  // Wire types present in this connection (for filter dropdown)
  const wireTypes = useMemo(() => {
    const t = new Set((conn?.wires || []).map(w => w.wire_type).filter(Boolean));
    return [...t].sort();
  }, [conn]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <Loader2 className="h-6 w-6 animate-spin text-slate-500" />
      </div>
    );
  }

  if (error || !conn) {
    return (
      <div className="p-6">
        <button onClick={() => router.back()}
          className="flex items-center gap-1 text-sm text-slate-400 hover:text-slate-200 mb-4">
          <ArrowLeft className="h-3.5 w-3.5" /> Back
        </button>
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-6 text-center">
          <AlertTriangle className="h-8 w-8 text-red-400 mx-auto mb-2" />
          <p className="text-sm text-red-300">{error || 'Connection not found'}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Back + header */}
      <div>
        <button onClick={() => router.back()}
          className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 mb-3">
          <ArrowLeft className="h-3.5 w-3.5" /> Back
        </button>

        <div className="rounded-2xl border border-astra-border bg-astra-surface px-6 py-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Cable className="h-6 w-6 text-emerald-400" />
              <div>
                <h1 className="text-xl font-bold text-slate-100 font-mono">
                  <span className="text-cyan-300">{conn.lru_a_designation}</span>
                  <span className="mx-3 text-slate-500">—</span>
                  <span className="text-violet-300">{conn.lru_b_designation}</span>
                </h1>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  {conn.lru_a_name} and {conn.lru_b_name}
                </p>
              </div>
            </div>
            <button onClick={fetchConnection}
              className="rounded-lg border border-astra-border p-2 text-slate-400 hover:text-slate-200">
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Stats row */}
          <div className="mt-5 flex items-center gap-6 border-t border-astra-border pt-4">
            <Stat label="Wires" value={conn.wire_count} />
            <Stat label="Harnesses" value={conn.harness_ids?.length || 0} />
            <Stat label="Connector pairs" value={connectorPairGroups.length} />
            {conn.harness_names && conn.harness_names.length > 0 && (
              <div className="flex items-center gap-2 ml-auto">
                <span className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
                  Via
                </span>
                <div className="flex flex-wrap gap-1">
                  {conn.harness_ids.map((hid, i) => (
                    <Link
                      key={hid}
                      href={`${p}/interfaces/harness/${hid}`}
                      className="rounded-full bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-0.5 text-[11px] text-emerald-300 hover:bg-emerald-500/20 transition">
                      {conn.harness_names[i] || `Harness ${hid}`}
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Pin maps */}
      <div>
        <h2 className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold mb-3">
          Pin Maps ({connectorPairGroups.length})
        </h2>
        {connectorPairGroups.length === 0 ? (
          <div className="rounded-xl border border-astra-border bg-astra-surface py-10 text-center">
            <Cable className="h-8 w-8 text-slate-600 mx-auto mb-2" />
            <p className="text-sm text-slate-400">No wires in this connection.</p>
          </div>
        ) : (
          <div className="space-y-4">
            {connectorPairGroups.map(group => (
              <div key={group.key}>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[12px] font-mono text-cyan-300">
                    {group.leftUnit}
                    <span className="text-slate-600 mx-1">.</span>
                    <span className="text-slate-300">{group.leftLabel}</span>
                  </span>
                  <span className="text-slate-700">—</span>
                  <span className="text-[12px] font-mono text-violet-300">
                    {group.rightUnit}
                    <span className="text-slate-600 mx-1">.</span>
                    <span className="text-slate-300">{group.rightLabel}</span>
                  </span>
                  <span className="ml-auto text-[10px] text-slate-500">
                    {group.wires.length} wire{group.wires.length === 1 ? '' : 's'}
                  </span>
                </div>
                <ConnectorPairPinMap
                  leftLabel={group.leftLabel}
                  rightLabel={group.rightLabel}
                  leftPins={group.leftPins}
                  rightPins={group.rightPins}
                  wires={group.wires}
                  onWireClick={setClickedWire}
                  hoveredWireId={hoveredWireId}
                  onHoverWire={setHoveredWireId}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Flat wire list with filters */}
      <div>
        <div className="flex items-center gap-3 mb-3">
          <h2 className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">
            All Wires ({filteredWires.length} of {conn.wire_count})
          </h2>
          <div className="flex-1" />
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-600" />
            <input
              value={wireSearch}
              onChange={e => setWireSearch(e.target.value)}
              placeholder="Search wires…"
              className="rounded-lg border border-astra-border bg-astra-surface pl-7 pr-3 py-1.5 text-xs text-slate-200 outline-none focus:border-blue-500/50 w-48"
            />
          </div>
          {conn.harness_ids && conn.harness_ids.length > 1 && (
            <select
              value={harnessFilter}
              onChange={e => setHarnessFilter(e.target.value ? Number(e.target.value) : '')}
              className="rounded-lg border border-astra-border bg-astra-surface px-2.5 py-1.5 text-xs text-slate-300 outline-none focus:border-blue-500/50">
              <option value="">All harnesses</option>
              {conn.harness_ids.map((hid, i) => (
                <option key={hid} value={hid}>{conn.harness_names?.[i] || `Harness ${hid}`}</option>
              ))}
            </select>
          )}
          {wireTypes.length > 1 && (
            <select
              value={typeFilter}
              onChange={e => setTypeFilter(e.target.value)}
              className="rounded-lg border border-astra-border bg-astra-surface px-2.5 py-1.5 text-xs text-slate-300 outline-none focus:border-blue-500/50">
              <option value="">All types</option>
              {wireTypes.map(t => (
                <option key={t} value={t as string}>
                  {(t as string).replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          )}
        </div>

        {filteredWires.length === 0 ? (
          <div className="rounded-xl border border-astra-border bg-astra-surface py-8 text-center">
            <p className="text-sm text-slate-500">No wires match your filters.</p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="border-b border-astra-border bg-astra-surface-alt">
                  <th className="px-3 py-2 text-left font-semibold text-slate-400 w-20">Wire #</th>
                  <th className="px-3 py-2 text-left font-semibold text-slate-400">Signal</th>
                  <th className="px-3 py-2 text-left font-semibold text-slate-400 w-28">Type</th>
                  <th className="px-3 py-2 text-left font-semibold text-slate-400">From</th>
                  <th className="px-3 py-2 text-left font-semibold text-slate-400">To</th>
                  <th className="px-3 py-2 text-left font-semibold text-slate-400 w-24">Harness</th>
                </tr>
              </thead>
              <tbody>
                {filteredWires.map(w => (
                  <tr
                    key={w.id}
                    onMouseEnter={() => setHoveredWireId(w.id)}
                    onMouseLeave={() => setHoveredWireId(null)}
                    onClick={() => setClickedWire(w)}
                    className={clsx(
                      'border-b border-astra-border cursor-pointer transition',
                      hoveredWireId === w.id ? 'bg-amber-500/5' : 'hover:bg-astra-surface-alt/50',
                    )}>
                    <td className="px-3 py-2 font-mono text-slate-200">{w.wire_number}</td>
                    <td className="px-3 py-2 text-slate-300 flex items-center gap-1.5">
                      <Circle className="h-2 w-2" fill={wireColorForWire(w)} stroke="none" />
                      {w.signal_name}
                    </td>
                    <td className="px-3 py-2 text-slate-500 text-[11px]">
                      {w.wire_type?.replace(/_/g, ' ')}
                    </td>
                    <td className="px-3 py-2 text-[11px]">
                      <span className="font-mono text-cyan-400">{w.from_unit_designation}</span>
                      <span className="text-slate-600">.{w.from_connector_designator}</span>
                      <span className="text-slate-500"> pin {w.from_pin_number}</span>
                    </td>
                    <td className="px-3 py-2 text-[11px]">
                      <span className="font-mono text-violet-400">{w.to_unit_designation}</span>
                      <span className="text-slate-600">.{w.to_connector_designator}</span>
                      <span className="text-slate-500"> pin {w.to_pin_number}</span>
                    </td>
                    <td className="px-3 py-2">
                      <Link
                        href={`${p}/interfaces/harness/${w.harness_id}`}
                        onClick={e => e.stopPropagation()}
                        className="text-[11px] text-emerald-400 hover:text-emerald-300">
                        #{w.harness_id}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {clickedWire && (
        <WireDetailPopup wire={clickedWire} onClose={() => setClickedWire(null)} />
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div>
      <p className="text-2xl font-bold text-slate-100">{value}</p>
      <p className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
        {label}
      </p>
    </div>
  );
}
