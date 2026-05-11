'use client';

/**
 * ASTRA — Project BOM page  (TDD-PROJPARTS-001 Path C, Phase 4)
 * =============================================================
 * The canonical Bill-of-Materials surface for a project. Renders:
 *
 *   • Stat strip (total / planned / released / installed)
 *   • Filter row: search + status select + part_class chips
 *   • Card grid of BOM lines (catalog summary, status chip, qty,
 *     unit link, position, parent designation)
 *   • Add modal — wraps CatalogPartPicker with broad allowedClasses
 *   • Edit drawer — status, quantity, unit link, parent, notes
 *
 * Distinction from the legacy /parts page: lines are catalog-anchored
 * (catalog_part_summary), duplicate catalog references are legal, and
 * fractional quantities round-trip as Decimal strings.
 *
 * File: frontend/src/app/projects/[id]/parts/page.tsx
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import clsx from 'clsx';
import {
  Boxes, Filter, Loader2, Pencil, Plus, RotateCw, Search, Trash2, X,
} from 'lucide-react';

import { projectsAPI } from '@/lib/api';
import { interfaceAPI } from '@/lib/interface-api';
import { projectPartsBomAPI } from '@/lib/projparts-api';
import type {
  BomStats, BomStatus, ProjectPartBom, ProjectPartBomCreate,
  ProjectPartBomUpdate,
} from '@/lib/projparts-types';
import {
  BOM_FILTER_CLASSES, BOM_STATUS_COLORS, BOM_STATUS_LABELS,
  BOM_STATUS_VALUES,
} from '@/lib/projparts-types';
import type { PartClass, CatalogPart } from '@/lib/catalog-types';
import { PART_CLASS_LABELS } from '@/lib/catalog-types';
import CatalogPartPicker from '@/components/catalog/CatalogPartPicker';


// ═══════════════════════════════════════════════════════════════
//  Page
// ═══════════════════════════════════════════════════════════════

export default function ProjectBomPage() {
  const params = useParams();
  const projectId = Number(params?.id);

  const [projectCode, setProjectCode] = useState('');
  const [rows, setRows] = useState<ProjectPartBom[]>([]);
  const [stats, setStats] = useState<BomStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<BomStatus | ''>('');
  const [classFilter, setClassFilter] = useState<PartClass | null>(null);

  // Modals
  const [addOpen, setAddOpen] = useState(false);
  const [editRow, setEditRow] = useState<ProjectPartBom | null>(null);

  // Debounce typed search → server-side filter.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  const reload = useCallback(() => {
    if (Number.isNaN(projectId)) return;
    setLoading(true);
    setError(null);
    Promise.all([
      projectPartsBomAPI.list(projectId, {
        status:     statusFilter || undefined,
        part_class: classFilter || undefined,
        search:     debouncedSearch.length >= 2 ? debouncedSearch : undefined,
        limit:      200,
      }),
      projectPartsBomAPI.stats(projectId),
    ])
      .then(([list, st]) => {
        setRows(list.data);
        setStats(st.data);
      })
      .catch((err) => {
        const detail = err?.response?.data?.detail;
        setError(typeof detail === 'string' ? detail : 'Failed to load BOM');
      })
      .finally(() => setLoading(false));
  }, [projectId, statusFilter, classFilter, debouncedSearch]);

  useEffect(() => { reload(); }, [reload]);

  useEffect(() => {
    if (Number.isNaN(projectId)) return;
    projectsAPI.get(projectId)
      .then((r) => setProjectCode(r.data.code))
      .catch(() => {});
  }, [projectId]);

  const onRemove = async (row: ProjectPartBom) => {
    const label = row.designation
      || row.catalog_part_summary?.part_number
      || row.library_part?.wardstone_part_number
      || `#${row.id}`;
    if (!confirm(`Remove BOM line "${label}"?`)) return;
    try {
      await projectPartsBomAPI.remove(projectId, row.id);
      reload();
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: { detail?: string } | string } } };
      const detail = ax?.response?.data?.detail;
      const msg = typeof detail === 'string'
        ? detail
        : (detail as { detail?: string })?.detail || 'Remove failed';
      alert(msg);
    }
  };

  // Stat strip values from the /stats endpoint (zero-safe).
  const total     = stats?.total ?? 0;
  const planned   = stats?.by_status.planned   ?? 0;
  const released  = stats?.by_status.released  ?? 0;
  const installed = stats?.by_status.installed ?? 0;

  return (
    <div className="mx-auto max-w-7xl">
      {/* ── Header ─────────────────────────────────────────────── */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Bill of Materials</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            {projectCode ? `${projectCode} · ` : ''}
            Catalog parts and library parts attached to this project as BOM lines.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={reload}
            className="flex items-center gap-1.5 rounded-lg border border-astra-border px-3 py-2 text-sm text-slate-300 hover:bg-astra-surface-alt"
            aria-label="Refresh"
            title="Refresh"
          >
            <RotateCw className="h-4 w-4" />
          </button>
          <button
            onClick={() => setAddOpen(true)}
            className="flex items-center gap-2 rounded-lg bg-blue-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-600"
          >
            <Plus className="h-4 w-4" />
            Add BOM Line
          </button>
        </div>
      </div>

      {/* ── Stat strip ─────────────────────────────────────────── */}
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Total Lines" value={total}     color="#3B82F6" />
        <StatCard label="Planned"     value={planned}   color="#94A3B8" />
        <StatCard label="Released"    value={released}  color="#0EA5E9" />
        <StatCard label="Installed"   value={installed} color="#10B981" />
      </div>

      {/* ── Filter row ─────────────────────────────────────────── */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[260px]">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            placeholder="Search designation, bom_position, notes…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-astra-border bg-astra-surface py-2 pl-10 pr-3 text-sm text-slate-200 placeholder:text-slate-500 outline-none focus:border-blue-500/50"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as BomStatus | '')}
          className="rounded-lg border border-astra-border bg-astra-surface px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
          aria-label="Filter by status"
        >
          <option value="">All statuses</option>
          {BOM_STATUS_VALUES.map((s) => (
            <option key={s} value={s}>{BOM_STATUS_LABELS[s]}</option>
          ))}
        </select>
      </div>

      {/* ── Part-class chip filter ─────────────────────────────── */}
      <div className="mb-5 flex flex-wrap items-center gap-1.5">
        <Filter className="mr-1 h-3.5 w-3.5 text-slate-500" />
        <Chip
          active={classFilter === null}
          onClick={() => setClassFilter(null)}
          label="All classes"
          count={total}
        />
        {BOM_FILTER_CLASSES.map((cls) => {
          const count = stats?.by_part_class[cls] ?? 0;
          if (count === 0 && classFilter !== cls) return null;
          return (
            <Chip
              key={cls}
              active={classFilter === cls}
              onClick={() => setClassFilter(classFilter === cls ? null : cls)}
              label={PART_CLASS_LABELS[cls]}
              count={count}
            />
          );
        })}
      </div>

      {/* ── Error / loading / empty / grid ─────────────────────── */}
      {error && (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {loading ? (
        <div className="py-12 text-center text-sm text-slate-500">
          <Loader2 className="mx-auto mb-2 h-6 w-6 animate-spin" />
          Loading BOM…
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-xl border border-astra-border bg-astra-surface py-12 text-center">
          <Boxes className="mx-auto mb-3 h-12 w-12 text-slate-600" />
          <h3 className="font-medium text-slate-200">
            {classFilter || statusFilter || debouncedSearch
              ? 'No BOM lines match the current filters.'
              : 'No BOM lines yet.'}
          </h3>
          <p className="mx-auto mb-4 mt-1 max-w-md text-sm text-slate-500">
            Add catalog parts as BOM lines so you can track quantities, status,
            and which unit each line installs on.
          </p>
          <button
            onClick={() => setAddOpen(true)}
            className="rounded-lg bg-blue-500 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-600"
          >
            Add the first one
          </button>
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {rows.map((row) => (
            <BomLineCard
              key={row.id}
              projectId={projectId}
              row={row}
              onEdit={() => setEditRow(row)}
              onRemove={() => onRemove(row)}
            />
          ))}
        </div>
      )}

      {/* ── Modals ─────────────────────────────────────────────── */}
      {addOpen && (
        <AddBomItemModal
          projectId={projectId}
          onClose={() => setAddOpen(false)}
          onCreated={() => { setAddOpen(false); reload(); }}
        />
      )}
      {editRow && (
        <EditBomItemDrawer
          projectId={projectId}
          row={editRow}
          onClose={() => setEditRow(null)}
          onSaved={() => { setEditRow(null); reload(); }}
        />
      )}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════
//  Stat card / chip
// ═══════════════════════════════════════════════════════════════

function StatCard({ label, value, color }: {
  label: string; value: number; color: string;
}) {
  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
      <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
        {label}
      </div>
      <div className="mt-2 text-2xl font-bold" style={{ color }}>
        {value}
      </div>
    </div>
  );
}

function Chip({ active, onClick, label, count }: {
  active: boolean; onClick: () => void; label: string; count: number;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        'rounded-full border px-3 py-1 text-xs transition',
        active
          ? 'border-blue-500/50 bg-blue-500/15 text-blue-200'
          : 'border-astra-border bg-astra-surface text-slate-300 hover:border-blue-500/30',
      )}
    >
      {label}
      <span className="ml-1.5 text-slate-500">{count}</span>
    </button>
  );
}


// ═══════════════════════════════════════════════════════════════
//  BOM line card
// ═══════════════════════════════════════════════════════════════

function BomLineCard({ projectId, row, onEdit, onRemove }: {
  projectId: number;
  row: ProjectPartBom;
  onEdit: () => void;
  onRemove: () => void;
}) {
  const cp = row.catalog_part_summary;
  const lp = row.library_part;
  const partNumber = cp?.part_number || lp?.wardstone_part_number || '—';
  const name       = cp?.name        || lp?.name                  || 'Unnamed BOM line';
  const className  = cp ? PART_CLASS_LABELS[cp.part_class] : null;
  const massKg     = cp?.mass_kg ? Number(cp.mass_kg) : null;
  const qty        = Number(row.quantity);

  return (
    <div className="group relative rounded-xl border border-astra-border bg-astra-surface p-4 transition hover:border-blue-500/40 hover:bg-astra-surface-alt">
      {/* Hover actions */}
      <div className="absolute right-2 top-2 flex gap-1 opacity-0 transition group-hover:opacity-100">
        <button
          onClick={onEdit}
          className="rounded-md p-1.5 text-slate-400 hover:bg-blue-500/15 hover:text-blue-300"
          aria-label="Edit BOM line"
          title="Edit"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={onRemove}
          className="rounded-md p-1.5 text-slate-400 hover:bg-red-500/15 hover:text-red-300"
          aria-label="Remove BOM line"
          title="Remove"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="mb-1 flex items-center gap-2 pr-16">
        {row.bom_position && (
          <span className="rounded bg-slate-700/40 px-1.5 py-0.5 font-mono text-[10px] text-slate-300">
            {row.bom_position}
          </span>
        )}
        <span
          className={clsx(
            'rounded-full border px-2 py-0.5 text-[10px] font-medium',
            BOM_STATUS_COLORS[row.status],
          )}
        >
          {BOM_STATUS_LABELS[row.status]}
        </span>
        {className && (
          <span className="rounded-full bg-slate-700/30 px-2 py-0.5 text-[10px] text-slate-300">
            {className}
          </span>
        )}
      </div>

      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          {cp ? (
            <Link
              href={`/catalog/parts/${cp.id}`}
              className="font-mono text-[11px] text-blue-300 hover:underline"
            >
              {partNumber}
            </Link>
          ) : lp ? (
            <Link
              href={`/parts-library/${row.library_part_id}`}
              className="font-mono text-[11px] text-blue-300 hover:underline"
            >
              {partNumber}
            </Link>
          ) : (
            <span className="font-mono text-[11px] text-slate-500">{partNumber}</span>
          )}
          <h3 className="mt-0.5 truncate text-sm font-medium text-slate-200">
            {row.designation || name}
          </h3>
          {row.designation && row.designation !== name && (
            <div className="truncate text-[11px] text-slate-500">{name}</div>
          )}
        </div>
        <div className="flex-shrink-0 text-right">
          <div className="text-lg font-bold text-slate-100">
            {Number.isFinite(qty) ? qty : row.quantity}
            <span className="ml-1 text-xs font-normal text-slate-500">
              {row.quantity_unit}
            </span>
          </div>
          {massKg != null && (
            <div className="text-[10px] text-slate-500">
              {(massKg * qty).toFixed(3)} kg total
            </div>
          )}
        </div>
      </div>

      {/* Footer row */}
      {(row.linked_unit || row.parent_designation || row.location_zone || cp?.supplier_name) && (
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500">
          {row.linked_unit && (
            <Link
              href={`/projects/${projectId}/system-architecture/unit/${row.linked_unit.id}`}
              className="text-blue-300 hover:underline"
            >
              ↳ {row.linked_unit.designation}
            </Link>
          )}
          {row.parent_designation && (
            <span>parent: <span className="text-slate-300">{row.parent_designation}</span></span>
          )}
          {row.location_zone && <span>📍 {row.location_zone}</span>}
          {cp?.supplier_name && <span className="ml-auto">{cp.supplier_name}</span>}
        </div>
      )}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════
//  Add modal
// ═══════════════════════════════════════════════════════════════

function AddBomItemModal({ projectId, onClose, onCreated }: {
  projectId: number;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [catalog, setCatalog] = useState<CatalogPart | null>(null);
  const [quantity, setQuantity] = useState('1');
  const [unit, setUnit] = useState('each');
  const [designation, setDesignation] = useState('');
  const [bomPosition, setBomPosition] = useState('');
  const [status, setStatus] = useState<BomStatus>('planned');
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const qtyValid = useMemo(() => {
    const n = Number(quantity);
    return Number.isFinite(n) && n > 0;
  }, [quantity]);

  const onSubmit = async () => {
    if (!catalog) {
      setErr('Pick a catalog part first.');
      return;
    }
    if (!qtyValid) {
      setErr('Quantity must be a positive number.');
      return;
    }
    setSubmitting(true);
    setErr(null);
    try {
      const payload: ProjectPartBomCreate = {
        catalog_part_id: catalog.id,
        quantity:        quantity,
        quantity_unit:   unit.trim() || 'each',
        status,
      };
      if (designation.trim()) payload.designation = designation.trim();
      if (bomPosition.trim()) payload.bom_position = bomPosition.trim();
      await projectPartsBomAPI.create(projectId, payload);
      onCreated();
    } catch (e: unknown) {
      const ax = e as { response?: { data?: { detail?: { detail?: string } | string } } };
      const detail = ax?.response?.data?.detail;
      setErr(typeof detail === 'string'
        ? detail
        : (detail as { detail?: string })?.detail || 'Add failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl rounded-xl border border-astra-border bg-astra-bg p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-100">Add BOM Line</h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-slate-400 hover:bg-astra-surface-alt"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mb-3">
          <CatalogPartPicker
            label="Catalog part"
            value={catalog}
            onChange={setCatalog}
            placeholder="Search by part number, name, supplier…"
          />
        </div>

        <div className="grid grid-cols-3 gap-3">
          <Field label="Quantity">
            <input
              type="text"
              inputMode="decimal"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              className={clsx(
                'w-full rounded-lg border bg-astra-bg px-3 py-2 text-sm outline-none',
                qtyValid ? 'border-astra-border focus:border-blue-500/50' : 'border-red-500/50',
              )}
            />
          </Field>
          <Field label="Unit">
            <input
              type="text"
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
              placeholder="each, m, L…"
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm outline-none focus:border-blue-500/50"
            />
          </Field>
          <Field label="Status">
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as BomStatus)}
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm outline-none focus:border-blue-500/50"
            >
              {BOM_STATUS_VALUES.map((s) => (
                <option key={s} value={s}>{BOM_STATUS_LABELS[s]}</option>
              ))}
            </select>
          </Field>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-3">
          <Field label="Designation (optional)">
            <input
              type="text"
              value={designation}
              onChange={(e) => setDesignation(e.target.value)}
              placeholder="e.g. Primary CPU, Bay-1 mount…"
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm outline-none focus:border-blue-500/50"
            />
          </Field>
          <Field label="BOM position (optional)">
            <input
              type="text"
              value={bomPosition}
              onChange={(e) => setBomPosition(e.target.value)}
              placeholder="e.g. 1.A.3"
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm outline-none focus:border-blue-500/50"
            />
          </Field>
        </div>

        {err && (
          <div className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 p-2 text-sm text-red-300">
            {err}
          </div>
        )}

        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg border border-astra-border px-3 py-2 text-sm text-slate-300 hover:bg-astra-surface-alt"
          >
            Cancel
          </button>
          <button
            onClick={onSubmit}
            disabled={!catalog || !qtyValid || submitting}
            className="rounded-lg bg-blue-500 px-3 py-2 text-sm font-semibold text-white transition hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? 'Adding…' : 'Add to BOM'}
          </button>
        </div>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════
//  Edit drawer
// ═══════════════════════════════════════════════════════════════

function EditBomItemDrawer({ projectId, row, onClose, onSaved }: {
  projectId: number;
  row: ProjectPartBom;
  onClose: () => void;
  onSaved: () => void;
}) {
  // ── Local edit state ──
  const [status, setStatus]         = useState<BomStatus>(row.status);
  const [quantity, setQuantity]     = useState(row.quantity);
  const [quantityUnit, setQtyUnit]  = useState(row.quantity_unit);
  const [designation, setDesignation] = useState(row.designation ?? '');
  const [bomPosition, setBomPosition] = useState(row.bom_position ?? '');
  const [locationZone, setLocationZone] = useState(row.location_zone ?? '');
  const [installationNotes, setInstallNotes] = useState(row.installation_notes ?? '');
  const [procurementNotes, setProcNotes]    = useState(row.procurement_notes ?? '');
  const [notes, setNotes]           = useState(row.notes ?? '');
  const [unitId, setUnitId]         = useState<number | null>(row.unit_id);
  const [parentBomId, setParentBomId] = useState<number | null>(row.parent_bom_id);

  // ── Dropdown data sources ──
  const [units, setUnits] = useState<Array<{ id: number; designation: string; name: string }>>([]);
  const [bomLines, setBomLines] = useState<Array<{ id: number; designation: string | null; bom_position: string | null }>>([]);

  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    interfaceAPI.listUnits(projectId, { limit: 500 })
      .then((r) => setUnits(r.data.map((u) => ({
        id: u.id, designation: u.designation, name: u.name,
      }))))
      .catch(() => setUnits([]));
    projectPartsBomAPI.list(projectId, { limit: 500 })
      .then((r) => setBomLines(
        r.data
          .filter((x) => x.id !== row.id)
          .map((x) => ({
            id: x.id,
            designation: x.designation,
            bom_position: x.bom_position,
          })),
      ))
      .catch(() => setBomLines([]));
  }, [projectId, row.id]);

  const onSave = async () => {
    setSubmitting(true);
    setErr(null);
    try {
      const payload: ProjectPartBomUpdate = {
        status,
        quantity,
        quantity_unit: quantityUnit,
        designation:   designation.trim() || null,
        bom_position:  bomPosition.trim() || null,
        location_zone: locationZone.trim() || null,
        installation_notes: installationNotes.trim() || null,
        procurement_notes:  procurementNotes.trim()  || null,
        notes:              notes.trim() || null,
        unit_id:       unitId,
        parent_bom_id: parentBomId,
      };
      await projectPartsBomAPI.update(projectId, row.id, payload);
      onSaved();
    } catch (e: unknown) {
      const ax = e as { response?: { data?: { detail?: { detail?: string } | string } } };
      const detail = ax?.response?.data?.detail;
      setErr(typeof detail === 'string'
        ? detail
        : (detail as { detail?: string })?.detail || 'Save failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/50"
      onClick={onClose}
    >
      <div
        className="h-full w-full max-w-md overflow-y-auto border-l border-astra-border bg-astra-bg p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <div>
            <div className="font-mono text-[11px] text-slate-500">
              {row.catalog_part_summary?.part_number
                || row.library_part?.wardstone_part_number
                || `#${row.id}`}
            </div>
            <h2 className="text-base font-semibold text-slate-100">
              Edit BOM Line
            </h2>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-slate-400 hover:bg-astra-surface-alt"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Status">
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value as BomStatus)}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm outline-none focus:border-blue-500/50"
              >
                {BOM_STATUS_VALUES.map((s) => (
                  <option key={s} value={s}>{BOM_STATUS_LABELS[s]}</option>
                ))}
              </select>
            </Field>
            <Field label="Quantity">
              <input
                type="text"
                inputMode="decimal"
                value={String(quantity)}
                onChange={(e) => setQuantity(e.target.value)}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm outline-none focus:border-blue-500/50"
              />
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Unit">
              <input
                type="text"
                value={quantityUnit}
                onChange={(e) => setQtyUnit(e.target.value)}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm outline-none focus:border-blue-500/50"
              />
            </Field>
            <Field label="BOM position">
              <input
                type="text"
                value={bomPosition}
                onChange={(e) => setBomPosition(e.target.value)}
                className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm outline-none focus:border-blue-500/50"
              />
            </Field>
          </div>

          <Field label="Designation">
            <input
              type="text"
              value={designation}
              onChange={(e) => setDesignation(e.target.value)}
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm outline-none focus:border-blue-500/50"
            />
          </Field>

          <Field label="Linked unit">
            <select
              value={unitId ?? ''}
              onChange={(e) => setUnitId(e.target.value ? Number(e.target.value) : null)}
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm outline-none focus:border-blue-500/50"
            >
              <option value="">— None —</option>
              {units.map((u) => (
                <option key={u.id} value={u.id}>{u.designation} — {u.name}</option>
              ))}
            </select>
          </Field>

          <Field label="Parent BOM line">
            <select
              value={parentBomId ?? ''}
              onChange={(e) => setParentBomId(e.target.value ? Number(e.target.value) : null)}
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm outline-none focus:border-blue-500/50"
            >
              <option value="">— None —</option>
              {bomLines.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.bom_position ? `[${b.bom_position}] ` : ''}{b.designation || `#${b.id}`}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Location zone">
            <input
              type="text"
              value={locationZone}
              onChange={(e) => setLocationZone(e.target.value)}
              placeholder="e.g. Chassis bay 2"
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm outline-none focus:border-blue-500/50"
            />
          </Field>

          <Field label="Installation notes">
            <textarea
              value={installationNotes}
              onChange={(e) => setInstallNotes(e.target.value)}
              rows={2}
              className="w-full resize-y rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm outline-none focus:border-blue-500/50"
            />
          </Field>

          <Field label="Procurement notes">
            <textarea
              value={procurementNotes}
              onChange={(e) => setProcNotes(e.target.value)}
              rows={2}
              className="w-full resize-y rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm outline-none focus:border-blue-500/50"
            />
          </Field>

          <Field label="Notes">
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="w-full resize-y rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm outline-none focus:border-blue-500/50"
            />
          </Field>
        </div>

        {err && (
          <div className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 p-2 text-sm text-red-300">
            {err}
          </div>
        )}

        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg border border-astra-border px-3 py-2 text-sm text-slate-300 hover:bg-astra-surface-alt"
          >
            Cancel
          </button>
          <button
            onClick={onSave}
            disabled={submitting}
            className="rounded-lg bg-blue-500 px-3 py-2 text-sm font-semibold text-white transition hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════
//  Misc
// ═══════════════════════════════════════════════════════════════

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        {label}
      </div>
      {children}
    </label>
  );
}
