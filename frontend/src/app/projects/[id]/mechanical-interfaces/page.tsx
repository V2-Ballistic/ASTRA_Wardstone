'use client';

/**
 * ASTRA — Mechanical Interfaces (TDD-MECH-001, Path A rebuild)
 * =============================================================
 * Three-tab page that wraps the existing project_parts-keyed
 * mechanical_joints backend (ASTRA-SPEC-PARTS-001 / migration 0027).
 *
 * Path A per docs/MECH_INVESTIGATION.md — keep the backend, rebuild
 * the frontend. The literal MECH-001 catalog_part_a/b design needs
 * project_parts ↔ catalog_parts consolidation which is queued for
 * TDD-PROJPARTS-001.
 *
 * Tabs (?tab=overview|joints|parts-with-joints, default `overview`):
 *   - overview: stat strip + status breakdown + recent activity
 *   - joints:   card grid with filters + AddJointModal
 *   - parts-with-joints: cross-reference of project parts that
 *                        participate in at least one joint
 *
 * Hooks rule: every useState/useEffect/useMemo lives ABOVE any
 * conditional render. Optional chaining throughout.
 */

import {
  useCallback, useEffect, useMemo, useRef, useState,
} from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import {
  AlertTriangle, ArrowRight, Box, CheckCircle, ChevronRight, Clock,
  GitMerge, Layers, Link2, Loader2, Plus, RefreshCw, Search, Trash2,
  Wrench, X,
} from 'lucide-react';
import clsx from 'clsx';

import { mechanicalJointsAPI, partsLibraryAPI, projectPartsAPI } from '@/lib/parts-api';
import { formatApiError } from '@/lib/errors';
import type {
  JointStatus, JointType, LibraryPartSummary, LockingFeature,
  MechanicalJointCreate, MechanicalJointResponse, ProjectPartResponse,
} from '@/lib/parts-types';
import { JOINT_TYPE_LABELS } from '@/lib/parts-types';
import { useFormAutosave } from '@/lib/autosave';
import RestorePromptBanner from '@/components/RestorePromptBanner';
import AssembliesTab from '@/components/cadport/AssembliesTab';


// ─────────────────────────────────────────────────────────────────
//  Constants
// ─────────────────────────────────────────────────────────────────

type Tab = 'overview' | 'joints' | 'parts-with-joints' | 'assemblies';

function isTab(s: string | null | undefined): s is Tab {
  return s === 'overview' || s === 'joints' || s === 'parts-with-joints' || s === 'assemblies';
}

const JOINT_TYPES: JointType[] = [
  'bolted', 'riveted', 'press_fit', 'adhesive', 'weld',
  'seal', 'alignment_pin', 'thermal_bond', 'spring_clip',
];

const JOINT_STATUSES: JointStatus[] = ['draft', 'active', 'superseded'];

const LOCKING_FEATURES: LockingFeature[] = [
  'none', 'nylok', 'prevailing_torque', 'safety_wire',
  'loctite', 'castellated', 'lockwire_hole',
];

// Joint types whose torque / engagement / locking fields are
// meaningful — drives the conditional reveal in AddJointModal.
const TORQUE_JOINT_TYPES = new Set<JointType>(['bolted']);
const SEAL_JOINT_TYPES = new Set<JointType>(['seal']);

const STATUS_PILL: Record<JointStatus, { bg: string; text: string; label: string }> = {
  draft:      { bg: 'rgba(148,163,184,0.18)', text: '#CBD5E1', label: 'Draft' },
  active:     { bg: 'rgba(16,185,129,0.15)',  text: '#10B981', label: 'Active' },
  superseded: { bg: 'rgba(245,158,11,0.18)',  text: '#F59E0B', label: 'Superseded' },
};


// ─────────────────────────────────────────────────────────────────
//  Stat-card helper (mirrors the Projects-dashboard / SYSARCH pattern)
// ─────────────────────────────────────────────────────────────────

function StatCard({
  icon: Icon, label, value, color, subText,
}: {
  icon: typeof Wrench;
  label: string;
  value: string | number;
  color: string;
  subText?: string;
}) {
  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{label}</p>
          <p className="mt-1.5 text-2xl font-bold tabular-nums text-slate-100">{value}</p>
          {subText && <p className="text-[10px] text-slate-500">{subText}</p>}
        </div>
        <div className="rounded-lg p-2" style={{ background: `${color}20` }}>
          <Icon className="h-4 w-4" style={{ color }} aria-hidden="true" />
        </div>
      </div>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────
//  Project-Part picker
//
//  Search-as-you-type dropdown over project_parts. Filters out the
//  excluded id (used to keep Part A and Part B distinct). Mechanical-
//  only filtering is done client-side via the linked library_part's
//  part_type — the backend list endpoint doesn't filter by part_type
//  yet.
// ─────────────────────────────────────────────────────────────────

interface ProjectPartPickerProps {
  parts: ProjectPartResponse[];
  value: number | null;
  onChange: (id: number | null) => void;
  excludeIds?: number[];
  label: string;
  placeholder?: string;
  disabled?: boolean;
}

function ProjectPartPicker({
  parts, value, onChange, excludeIds = [], label, placeholder, disabled,
}: ProjectPartPickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return parts
      .filter((p) => !excludeIds.includes(p.id))
      .filter((p) => {
        if (!q) return true;
        const blob = [
          p.designation || '',
          p.library_part.name,
          p.library_part.wardstone_part_number,
          p.library_part.manufacturer_part_number || '',
        ].join(' ').toLowerCase();
        return blob.includes(q);
      })
      .slice(0, 30);
  }, [parts, query, excludeIds]);

  const selected = useMemo(
    () => (value == null ? null : parts.find((p) => p.id === value) || null),
    [parts, value],
  );

  const display = selected
    ? `${selected.designation || selected.library_part.wardstone_part_number} — ${selected.library_part.name}`
    : (placeholder || 'Pick a project part…');

  return (
    <div ref={containerRef} className="relative">
      <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        {label}
      </label>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={disabled}
        className={clsx(
          'flex w-full items-center justify-between rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm outline-none transition focus:border-blue-500/50',
          selected ? 'text-slate-200' : 'text-slate-500',
          disabled && 'cursor-not-allowed opacity-50',
        )}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="truncate">{display}</span>
        <div className="flex flex-shrink-0 items-center gap-1">
          {selected && (
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => { e.stopPropagation(); onChange(null); }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.stopPropagation();
                  onChange(null);
                }
              }}
              aria-label="Clear selection"
              className="rounded p-0.5 text-slate-500 hover:bg-astra-surface-alt hover:text-slate-300"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </span>
          )}
        </div>
      </button>
      {open && (
        <div
          role="listbox"
          className="absolute left-0 right-0 z-30 mt-1 max-h-72 overflow-hidden rounded-xl border border-astra-border bg-astra-surface shadow-xl"
        >
          <div className="border-b border-astra-border bg-astra-surface-alt p-2">
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500"
                aria-hidden="true"
              />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search WPN, name, designation…"
                className="w-full rounded border border-astra-border bg-astra-bg pl-8 pr-2 py-1.5 text-xs text-slate-200 outline-none focus:border-blue-500/50"
              />
            </div>
          </div>
          <div className="max-h-56 overflow-y-auto">
            {filtered.length === 0 ? (
              <div className="px-3 py-6 text-center text-xs text-slate-500">
                No project parts match.
              </div>
            ) : filtered.map((p) => (
              <button
                key={p.id}
                type="button"
                role="option"
                aria-selected={value === p.id}
                onClick={() => { onChange(p.id); setOpen(false); setQuery(''); }}
                className={clsx(
                  'flex w-full flex-col gap-0.5 border-b border-astra-border px-3 py-2 text-left transition hover:bg-astra-surface-alt',
                  value === p.id && 'bg-blue-500/5',
                )}
              >
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-mono text-slate-200">
                    {p.designation || p.library_part.wardstone_part_number}
                  </span>
                  <span className="rounded-full bg-blue-500/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase text-blue-300">
                    {p.library_part.part_type}
                  </span>
                </div>
                <div className="truncate text-[11px] text-slate-300">{p.library_part.name}</div>
                {p.library_part.manufacturer_part_number && (
                  <div className="text-[10px] text-slate-500">
                    {p.library_part.manufacturer_name || ''}{' '}
                    {p.library_part.manufacturer_part_number}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────
//  Fastener picker (library_parts of part_type='fastener')
// ─────────────────────────────────────────────────────────────────

interface FastenerPickerProps {
  value: number | null;
  onChange: (lp: LibraryPartSummary | null) => void;
  disabled?: boolean;
}

function FastenerPicker({ value, onChange, disabled }: FastenerPickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [results, setResults] = useState<LibraryPartSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<LibraryPartSummary | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Debounce typing
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query), 300);
    return () => clearTimeout(t);
  }, [query]);

  // Outside-click closes
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  // Search runner
  useEffect(() => {
    if (!open) return;
    setLoading(true);
    partsLibraryAPI.list({
      part_type: 'fastener',
      search: debouncedQuery || undefined,
      limit: 20,
    })
      .then((r) => setResults(r.data))
      .catch(() => setResults([]))
      .finally(() => setLoading(false));
  }, [open, debouncedQuery]);

  // If the parent supplied a `value` (e.g. when editing), fetch the
  // summary so we can display it.
  useEffect(() => {
    if (value == null) {
      setSelected(null);
      return;
    }
    if (selected?.id === value) return;
    partsLibraryAPI.get(value)
      .then((r) => {
        const d = r.data;
        setSelected({
          id: d.id,
          wardstone_part_number: d.wardstone_part_number,
          revision: d.revision,
          part_type: d.part_type,
          name: d.name,
          status: d.status,
          manufacturer_name: d.manufacturer_name,
          manufacturer_part_number: d.manufacturer_part_number,
          material_name: d.material_name,
          material_class: d.material_class,
          mass_nominal_g: d.mass_nominal_g,
          approved_at: null,
        });
      })
      .catch(() => setSelected(null));
  }, [value, selected?.id]);

  const display = selected
    ? `${selected.wardstone_part_number} — ${selected.name}`
    : 'Pick a fastener (optional)';

  return (
    <div ref={containerRef} className="relative">
      <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        Fastener
      </label>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={disabled}
        className={clsx(
          'flex w-full items-center justify-between rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm outline-none transition focus:border-blue-500/50',
          selected ? 'text-slate-200' : 'text-slate-500',
          disabled && 'cursor-not-allowed opacity-50',
        )}
      >
        <span className="truncate">{display}</span>
        {selected && (
          <span
            role="button"
            tabIndex={0}
            onClick={(e) => { e.stopPropagation(); onChange(null); setSelected(null); }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.stopPropagation();
                onChange(null);
                setSelected(null);
              }
            }}
            aria-label="Clear fastener"
            className="rounded p-0.5 text-slate-500 hover:bg-astra-surface-alt hover:text-slate-300"
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
          </span>
        )}
      </button>
      {open && (
        <div className="absolute left-0 right-0 z-30 mt-1 max-h-72 overflow-hidden rounded-xl border border-astra-border bg-astra-surface shadow-xl">
          <div className="border-b border-astra-border bg-astra-surface-alt p-2">
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500"
                aria-hidden="true"
              />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search fasteners…"
                className="w-full rounded border border-astra-border bg-astra-bg pl-8 pr-2 py-1.5 text-xs text-slate-200 outline-none focus:border-blue-500/50"
              />
            </div>
          </div>
          <div className="max-h-56 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-4 w-4 animate-spin text-blue-500" aria-hidden="true" />
              </div>
            ) : results.length === 0 ? (
              <div className="px-3 py-6 text-center text-xs text-slate-500">
                No fasteners found.
              </div>
            ) : results.map((row) => (
              <button
                key={row.id}
                type="button"
                onClick={() => {
                  setSelected(row);
                  onChange(row);
                  setOpen(false);
                }}
                className={clsx(
                  'flex w-full flex-col gap-0.5 border-b border-astra-border px-3 py-2 text-left transition hover:bg-astra-surface-alt',
                  value === row.id && 'bg-blue-500/5',
                )}
              >
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-mono text-slate-200">{row.wardstone_part_number}</span>
                  {row.manufacturer_part_number && (
                    <span className="rounded-full bg-blue-500/10 px-1.5 py-0.5 text-[9px] font-semibold text-blue-300">
                      {row.manufacturer_part_number}
                    </span>
                  )}
                </div>
                <div className="truncate text-[11px] text-slate-300">{row.name}</div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────
//  AddJointModal
// ─────────────────────────────────────────────────────────────────

interface JointDraft {
  joint_type: JointType;
  part_a_id: number | null;
  part_b_id: number | null;
  fastener_part_id: number | null;
  fastener_count: string;        // string in the form, parsed on submit
  torque_nominal_nm: string;
  torque_min_nm: string;
  torque_max_nm: string;
  engagement_length_mm: string;
  locking_feature: LockingFeature | '';
  hole_pattern_description: string;
  mating_surface_flatness_mm: string;
  mating_surface_finish_ra: string;
  leak_rate_max_scc_s: string;
  test_pressure_bar: string;
  interface_drawing: string;
  notes: string;
}

const EMPTY_DRAFT: JointDraft = {
  joint_type: 'bolted',
  part_a_id: null,
  part_b_id: null,
  fastener_part_id: null,
  fastener_count: '',
  torque_nominal_nm: '',
  torque_min_nm: '',
  torque_max_nm: '',
  engagement_length_mm: '',
  locking_feature: '',
  hole_pattern_description: '',
  mating_surface_flatness_mm: '',
  mating_surface_finish_ra: '',
  leak_rate_max_scc_s: '',
  test_pressure_bar: '',
  interface_drawing: '',
  notes: '',
};


interface AddJointModalProps {
  open: boolean;
  projectId: number;
  projectParts: ProjectPartResponse[];
  onClose: () => void;
  onCreated: () => void;
}

function AddJointModal({
  open, projectId, projectParts, onClose, onCreated,
}: AddJointModalProps) {
  const [draft, setDraft] = useState<JointDraft>(EMPTY_DRAFT);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const storageKey = `astra:autosave:mech-joint-new:project-${projectId}`;
  const memoDraft = useMemo(() => draft, [draft]);
  const {
    hasDraft, draftAge, restoreDraft, clearDraft,
  } = useFormAutosave<JointDraft>(storageKey, memoDraft);

  useEffect(() => {
    if (!open) {
      setError(null);
      setSubmitting(false);
    }
  }, [open]);

  const showTorqueFields = TORQUE_JOINT_TYPES.has(draft.joint_type);
  const showSealFields = SEAL_JOINT_TYPES.has(draft.joint_type);

  // Inline same-part validation per the prompt's gotcha §1.
  const samePartError =
    draft.part_a_id != null
    && draft.part_b_id != null
    && draft.part_a_id === draft.part_b_id
      ? 'Part A and Part B must be different project parts.'
      : null;

  const canSubmit =
    draft.part_a_id != null
    && draft.part_b_id != null
    && samePartError == null
    && !submitting;

  const onRestore = () => {
    const v = restoreDraft();
    if (v) setDraft(v);
  };

  const submit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    // Build payload — coerce numeric strings, drop empties.
    const payload: MechanicalJointCreate = {
      joint_type: draft.joint_type,
      part_a_id: draft.part_a_id!,
      part_b_id: draft.part_b_id!,
    };
    if (draft.fastener_part_id != null) payload.fastener_part_id = draft.fastener_part_id;
    if (draft.fastener_count.trim()) {
      const n = Number(draft.fastener_count);
      if (Number.isFinite(n) && n > 0) payload.fastener_count = n;
    }
    if (draft.torque_nominal_nm.trim()) payload.torque_nominal_nm = draft.torque_nominal_nm.trim();
    if (draft.torque_min_nm.trim()) payload.torque_min_nm = draft.torque_min_nm.trim();
    if (draft.torque_max_nm.trim()) payload.torque_max_nm = draft.torque_max_nm.trim();
    if (draft.engagement_length_mm.trim()) payload.engagement_length_mm = draft.engagement_length_mm.trim();
    if (draft.locking_feature) payload.locking_feature = draft.locking_feature;
    if (draft.hole_pattern_description.trim()) payload.hole_pattern_description = draft.hole_pattern_description.trim();
    if (draft.mating_surface_flatness_mm.trim()) payload.mating_surface_flatness_mm = draft.mating_surface_flatness_mm.trim();
    if (draft.mating_surface_finish_ra.trim()) payload.mating_surface_finish_ra = draft.mating_surface_finish_ra.trim();
    if (draft.leak_rate_max_scc_s.trim()) payload.leak_rate_max_scc_s = draft.leak_rate_max_scc_s.trim();
    if (draft.test_pressure_bar.trim()) payload.test_pressure_bar = draft.test_pressure_bar.trim();
    if (draft.interface_drawing.trim()) payload.interface_drawing = draft.interface_drawing.trim();
    if (draft.notes.trim()) payload.notes = draft.notes.trim();

    try {
      await mechanicalJointsAPI.create(projectId, payload);
      clearDraft();
      setDraft(EMPTY_DRAFT);
      onCreated();
      onClose();
    } catch (e: unknown) {
      setError(formatApiError(e, 'Create failed'));
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-joint-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-2xl rounded-xl border border-astra-border bg-astra-surface p-5 shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="mb-4 flex items-center justify-between">
          <h2 id="add-joint-title" className="text-base font-bold text-slate-100">
            Add Joint
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            aria-label="Close"
            className="rounded p-1 text-slate-400 hover:bg-astra-surface-alt hover:text-slate-200"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {hasDraft && draftAge !== null && (
          <RestorePromptBanner
            ageMs={draftAge}
            onRestore={onRestore}
            onDiscard={clearDraft}
          />
        )}

        {error && (
          <div role="alert" className="mb-3 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
            {error}
          </div>
        )}

        {samePartError && (
          <div role="alert" className="mb-3 rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
            {samePartError}
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <ProjectPartPicker
            label="Part A *"
            parts={projectParts}
            value={draft.part_a_id}
            onChange={(id) => setDraft({ ...draft, part_a_id: id })}
            excludeIds={draft.part_b_id != null ? [draft.part_b_id] : []}
            disabled={submitting}
          />
          <ProjectPartPicker
            label="Part B *"
            parts={projectParts}
            value={draft.part_b_id}
            onChange={(id) => setDraft({ ...draft, part_b_id: id })}
            excludeIds={draft.part_a_id != null ? [draft.part_a_id] : []}
            disabled={submitting}
          />
        </div>

        <div className="mt-3 grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="mj-type" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Joint type *
            </label>
            <select
              id="mj-type"
              value={draft.joint_type}
              onChange={(e) => setDraft({ ...draft, joint_type: e.target.value as JointType })}
              className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
            >
              {JOINT_TYPES.map((t) => (
                <option key={t} value={t}>{JOINT_TYPE_LABELS[t]}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Joint ID
            </label>
            <div className="rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-xs text-slate-500">
              Auto-assigned on save (MJ-NNN)
            </div>
          </div>
        </div>

        <div className="mt-3">
          <FastenerPicker
            value={draft.fastener_part_id}
            onChange={(lp) => setDraft({
              ...draft,
              fastener_part_id: lp?.id ?? null,
            })}
            disabled={submitting}
          />
        </div>

        {draft.fastener_part_id != null && (
          <div className="mt-3 grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="mj-fcount" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Fastener count
              </label>
              <input
                id="mj-fcount"
                type="number"
                min={1}
                value={draft.fastener_count}
                onChange={(e) => setDraft({ ...draft, fastener_count: e.target.value })}
                className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
              />
            </div>
          </div>
        )}

        {showTorqueFields && (
          <fieldset className="mt-3 rounded border border-astra-border bg-astra-bg p-3">
            <legend className="px-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Torque (bolted)
            </legend>
            <div className="grid grid-cols-3 gap-2">
              {([
                ['torque_nominal_nm', 'Nominal (N·m)'],
                ['torque_min_nm', 'Min (N·m)'],
                ['torque_max_nm', 'Max (N·m)'],
              ] as const).map(([key, label]) => (
                <div key={key}>
                  <label htmlFor={`mj-${key}`} className="mb-0.5 block text-[10px] text-slate-500">
                    {label}
                  </label>
                  <input
                    id={`mj-${key}`}
                    type="text"
                    inputMode="decimal"
                    value={draft[key]}
                    onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
                    className="w-full rounded border border-astra-border bg-astra-surface px-2 py-1 text-xs text-slate-200 outline-none focus:border-blue-500/50"
                  />
                </div>
              ))}
            </div>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <div>
                <label htmlFor="mj-engagement" className="mb-0.5 block text-[10px] text-slate-500">
                  Engagement length (mm)
                </label>
                <input
                  id="mj-engagement"
                  type="text"
                  inputMode="decimal"
                  value={draft.engagement_length_mm}
                  onChange={(e) => setDraft({ ...draft, engagement_length_mm: e.target.value })}
                  className="w-full rounded border border-astra-border bg-astra-surface px-2 py-1 text-xs text-slate-200 outline-none focus:border-blue-500/50"
                />
              </div>
              <div>
                <label htmlFor="mj-locking" className="mb-0.5 block text-[10px] text-slate-500">
                  Locking feature
                </label>
                <select
                  id="mj-locking"
                  value={draft.locking_feature}
                  onChange={(e) => setDraft({ ...draft, locking_feature: e.target.value as LockingFeature | '' })}
                  className="w-full rounded border border-astra-border bg-astra-surface px-2 py-1 text-xs text-slate-200 outline-none focus:border-blue-500/50"
                >
                  <option value="">— none —</option>
                  {LOCKING_FEATURES.map((f) => <option key={f} value={f}>{f.replace(/_/g, ' ')}</option>)}
                </select>
              </div>
            </div>
          </fieldset>
        )}

        {showSealFields && (
          <fieldset className="mt-3 rounded border border-astra-border bg-astra-bg p-3">
            <legend className="px-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Seal
            </legend>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label htmlFor="mj-leak" className="mb-0.5 block text-[10px] text-slate-500">
                  Max leak rate (scc/s)
                </label>
                <input
                  id="mj-leak"
                  type="text"
                  inputMode="decimal"
                  value={draft.leak_rate_max_scc_s}
                  onChange={(e) => setDraft({ ...draft, leak_rate_max_scc_s: e.target.value })}
                  className="w-full rounded border border-astra-border bg-astra-surface px-2 py-1 text-xs text-slate-200 outline-none focus:border-blue-500/50"
                />
              </div>
              <div>
                <label htmlFor="mj-pressure" className="mb-0.5 block text-[10px] text-slate-500">
                  Test pressure (bar)
                </label>
                <input
                  id="mj-pressure"
                  type="text"
                  inputMode="decimal"
                  value={draft.test_pressure_bar}
                  onChange={(e) => setDraft({ ...draft, test_pressure_bar: e.target.value })}
                  className="w-full rounded border border-astra-border bg-astra-surface px-2 py-1 text-xs text-slate-200 outline-none focus:border-blue-500/50"
                />
              </div>
            </div>
          </fieldset>
        )}

        <div className="mt-3 grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="mj-flatness" className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Mating flatness (mm)
            </label>
            <input
              id="mj-flatness"
              type="text"
              inputMode="decimal"
              value={draft.mating_surface_flatness_mm}
              onChange={(e) => setDraft({ ...draft, mating_surface_flatness_mm: e.target.value })}
              className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
            />
          </div>
          <div>
            <label htmlFor="mj-finish" className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Mating finish Ra
            </label>
            <input
              id="mj-finish"
              type="text"
              inputMode="decimal"
              value={draft.mating_surface_finish_ra}
              onChange={(e) => setDraft({ ...draft, mating_surface_finish_ra: e.target.value })}
              className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
            />
          </div>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <label htmlFor="mj-hole" className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Hole pattern description
            </label>
            <input
              id="mj-hole"
              type="text"
              value={draft.hole_pattern_description}
              onChange={(e) => setDraft({ ...draft, hole_pattern_description: e.target.value })}
              placeholder="4× 6mm on 50mm PCD"
              className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
            />
          </div>
          <div className="col-span-2">
            <label htmlFor="mj-drawing" className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Interface drawing
            </label>
            <input
              id="mj-drawing"
              type="text"
              value={draft.interface_drawing}
              onChange={(e) => setDraft({ ...draft, interface_drawing: e.target.value })}
              placeholder="ICD-MECH-001 Rev B"
              className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
            />
          </div>
        </div>

        <div className="mt-3">
          <label htmlFor="mj-notes" className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Notes
          </label>
          <textarea
            id="mj-notes"
            rows={3}
            value={draft.notes}
            onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
            className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
          />
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded border border-astra-border px-3 py-1.5 text-xs text-slate-300 hover:bg-astra-surface-alt"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!canSubmit}
            className="flex items-center gap-1.5 rounded bg-gradient-to-br from-blue-500 to-violet-500 px-3 py-1.5 text-xs font-semibold text-white hover:shadow-lg disabled:opacity-50"
          >
            {submitting && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
            Add Joint
          </button>
        </div>
      </div>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────
//  Page
// ─────────────────────────────────────────────────────────────────

export default function MechanicalInterfacesPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const projectId = Number(params?.id);

  const rawTab = searchParams?.get('tab');
  const initialTab: Tab = isTab(rawTab) ? rawTab : 'overview';

  // ── Data ──
  const [joints, setJoints] = useState<MechanicalJointResponse[]>([]);
  const [projectParts, setProjectParts] = useState<ProjectPartResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ── Tab state (URL-driven) ──
  const [tab, setTab] = useState<Tab>(initialTab);
  const setTabPersist = useCallback((next: Tab) => {
    setTab(next);
    const sp = new URLSearchParams(searchParams?.toString() || '');
    sp.set('tab', next);
    router.replace(`/projects/${projectId}/mechanical-interfaces?${sp.toString()}`);
  }, [projectId, router, searchParams]);

  // ── Filters (Joints tab) ──
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<JointType | ''>('');
  const [statusFilter, setStatusFilter] = useState<JointStatus | ''>('');
  const [partFilter, setPartFilter] = useState<number | null>(null);

  // ── Add modal ──
  const [addOpen, setAddOpen] = useState(false);

  const reload = useCallback(() => {
    if (!Number.isFinite(projectId)) return;
    setLoading(true);
    setError(null);
    Promise.all([
      mechanicalJointsAPI.list(projectId, { limit: 200 }),
      projectPartsAPI.list(projectId, { limit: 200 }),
    ])
      .then(([j, p]) => {
        setJoints(j.data);
        setProjectParts(p.data);
      })
      .catch((e: unknown) => {
        setError(formatApiError(e, 'Failed to load mechanical joints'));
      })
      .finally(() => setLoading(false));
  }, [projectId]);

  useEffect(() => { reload(); }, [reload]);

  // ── Derived state — keep all hooks before any early return ──
  const partsById = useMemo(() => {
    const m = new Map<number, ProjectPartResponse>();
    for (const p of projectParts) m.set(p.id, p);
    return m;
  }, [projectParts]);

  const filteredJoints = useMemo(() => {
    const q = search.trim().toLowerCase();
    return joints.filter((j) => {
      if (typeFilter && j.joint_type !== typeFilter) return false;
      if (statusFilter && j.status !== statusFilter) return false;
      if (partFilter && j.part_a_id !== partFilter && j.part_b_id !== partFilter) return false;
      if (q) {
        const a = partsById.get(j.part_a_id);
        const b = partsById.get(j.part_b_id);
        const blob = [
          j.joint_id,
          j.joint_type,
          j.interface_drawing || '',
          a?.designation || '',
          a?.library_part.name || '',
          a?.library_part.wardstone_part_number || '',
          b?.designation || '',
          b?.library_part.name || '',
          b?.library_part.wardstone_part_number || '',
        ].join(' ').toLowerCase();
        if (!blob.includes(q)) return false;
      }
      return true;
    });
  }, [joints, search, typeFilter, statusFilter, partFilter, partsById]);

  const statusBreakdown = useMemo(() => {
    const out: Record<JointStatus, number> = {
      draft: 0, active: 0, superseded: 0,
    };
    for (const j of joints) out[j.status] += 1;
    return out;
  }, [joints]);

  // Parts-with-joints cross-reference: project_part → joint count.
  const partsWithJoints = useMemo(() => {
    const counts = new Map<number, number>();
    for (const j of joints) {
      counts.set(j.part_a_id, (counts.get(j.part_a_id) ?? 0) + 1);
      counts.set(j.part_b_id, (counts.get(j.part_b_id) ?? 0) + 1);
    }
    return Array.from(counts.entries())
      .map(([ppId, count]) => ({ part: partsById.get(ppId), count, id: ppId }))
      .filter((r) => r.part != null)
      .sort((a, b) => b.count - a.count);
  }, [joints, partsById]);

  const recentJoints = useMemo(
    () => joints.slice().sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 5),
    [joints],
  );

  const onApprove = async (joint: MechanicalJointResponse) => {
    if (!window.confirm(`Approve joint ${joint.joint_id}? This generates auto-requirements.`)) {
      return;
    }
    try {
      await mechanicalJointsAPI.approve(projectId, joint.joint_id);
      reload();
    } catch (e: unknown) {
      window.alert(formatApiError(e, 'Approve failed'));
    }
  };

  const onDelete = async (joint: MechanicalJointResponse) => {
    const isActive = joint.status === 'active';
    if (isActive && !window.confirm(
      `Joint ${joint.joint_id} is ACTIVE. Force-deleting it will mark linked auto-requirements for review. Continue?`,
    )) return;
    if (!isActive && !window.confirm(`Delete draft joint ${joint.joint_id}?`)) return;
    try {
      await mechanicalJointsAPI.delete(projectId, joint.joint_id, isActive);
      reload();
    } catch (e: unknown) {
      window.alert(formatApiError(e, 'Delete failed'));
    }
  };

  // ── Render ──
  return (
    <div>
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-slate-100">
            <Wrench className="h-6 w-6 text-blue-400" aria-hidden="true" />
            Mechanical Interfaces
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Joints between project parts — bolted, sealed, press-fit, and more.
          </p>
        </div>
      </div>

      {error && (
        <div role="alert" className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
          {error}
        </div>
      )}

      {/* Stat strip */}
      <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={Wrench}
          label="Joints"
          value={loading ? '—' : joints.length}
          color="#3B82F6"
        />
        <StatCard
          icon={CheckCircle}
          label="Active"
          value={loading ? '—' : statusBreakdown.active}
          color="#10B981"
          subText={joints.length > 0 ? `${statusBreakdown.active} of ${joints.length}` : undefined}
        />
        <StatCard
          icon={Clock}
          label="Drafts"
          value={loading ? '—' : statusBreakdown.draft}
          color="#F59E0B"
        />
        <StatCard
          icon={Layers}
          label="Parts in joints"
          value={loading ? '—' : partsWithJoints.length}
          color="#A78BFA"
        />
      </div>

      {/* Tabs */}
      <div role="tablist" aria-label="Mechanical Interfaces sections" className="mb-4 flex gap-1 border-b border-astra-border">
        {(['overview', 'joints', 'parts-with-joints', 'assemblies'] as Tab[]).map((t) => {
          const active = tab === t;
          const labels: Record<Tab, string> = {
            overview: 'Overview',
            joints: 'Joints',
            'parts-with-joints': 'Parts with Joints',
            assemblies: 'Assemblies',
          };
          return (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={active}
              aria-controls={`mech-panel-${t}`}
              id={`mech-tab-${t}`}
              onClick={() => setTabPersist(t)}
              className={clsx(
                'flex items-center gap-1.5 rounded-t-lg border-b-2 px-4 py-2 text-xs font-semibold transition',
                active
                  ? 'border-blue-400 text-blue-300'
                  : 'border-transparent text-slate-400 hover:text-slate-200',
              )}
            >
              {labels[t]}
            </button>
          );
        })}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-5 w-5 animate-spin text-blue-500" aria-label="Loading" />
        </div>
      ) : (
        <div id={`mech-panel-${tab}`} role="tabpanel" aria-labelledby={`mech-tab-${tab}`}>
          {tab === 'overview' && (
            <OverviewTab
              joints={joints}
              partsById={partsById}
              statusBreakdown={statusBreakdown}
              recentJoints={recentJoints}
              onOpenJoints={() => setTabPersist('joints')}
              onAddJoint={() => setAddOpen(true)}
              hasProjectParts={projectParts.length >= 2}
            />
          )}
          {tab === 'joints' && (
            <JointsTab
              joints={joints}
              filtered={filteredJoints}
              partsById={partsById}
              partOptions={projectParts}
              search={search}
              setSearch={setSearch}
              typeFilter={typeFilter}
              setTypeFilter={setTypeFilter}
              statusFilter={statusFilter}
              setStatusFilter={setStatusFilter}
              partFilter={partFilter}
              setPartFilter={setPartFilter}
              onAddJoint={() => setAddOpen(true)}
              onApprove={onApprove}
              onDelete={onDelete}
              onRefresh={reload}
              hasProjectParts={projectParts.length >= 2}
            />
          )}
          {tab === 'parts-with-joints' && (
            <PartsWithJointsTab
              partsWithJoints={partsWithJoints}
              onPick={(ppId) => { setPartFilter(ppId); setTabPersist('joints'); }}
            />
          )}
          {tab === 'assemblies' && (
            <AssembliesTab projectId={projectId} />
          )}
        </div>
      )}

      <AddJointModal
        open={addOpen}
        projectId={projectId}
        projectParts={projectParts}
        onClose={() => setAddOpen(false)}
        onCreated={reload}
      />
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────
//  Overview tab
// ─────────────────────────────────────────────────────────────────

function OverviewTab({
  joints, partsById, statusBreakdown, recentJoints, onOpenJoints, onAddJoint,
  hasProjectParts,
}: {
  joints: MechanicalJointResponse[];
  partsById: Map<number, ProjectPartResponse>;
  statusBreakdown: Record<JointStatus, number>;
  recentJoints: MechanicalJointResponse[];
  onOpenJoints: () => void;
  onAddJoint: () => void;
  hasProjectParts: boolean;
}) {
  if (joints.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-astra-border bg-astra-surface px-6 py-16 text-center">
        <Wrench className="mx-auto mb-3 h-10 w-10 text-slate-600" aria-hidden="true" />
        <p className="mb-2 text-sm text-slate-300">No mechanical joints defined yet.</p>
        <p className="mb-5 text-xs text-slate-500">
          Add your first joint to start tracking mechanical interfaces between project parts.
        </p>
        <button
          type="button"
          onClick={onAddJoint}
          disabled={!hasProjectParts}
          title={hasProjectParts ? '' : 'Need at least 2 project parts to create a joint'}
          className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-br from-blue-500 to-violet-500 px-3 py-1.5 text-xs font-semibold text-white hover:shadow-lg disabled:opacity-50"
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add Joint
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
        <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-400">Status breakdown</h3>
        <div className="flex flex-wrap gap-2">
          {(Object.entries(statusBreakdown) as [JointStatus, number][]).map(([status, count]) => {
            const pill = STATUS_PILL[status];
            return (
              <span
                key={status}
                className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold"
                style={{ background: pill.bg, color: pill.text }}
              >
                {pill.label}
                <span className="rounded-full bg-black/20 px-1.5 py-0.5 text-[10px]">{count}</span>
              </span>
            );
          })}
        </div>
      </div>

      <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">Recent activity</h3>
          <button
            type="button"
            onClick={onOpenJoints}
            className="flex items-center gap-1 text-[11px] font-semibold text-blue-400 hover:text-blue-300"
          >
            View all <ArrowRight className="h-3 w-3" aria-hidden="true" />
          </button>
        </div>
        <ul className="space-y-2">
          {recentJoints.map((j) => {
            const a = partsById.get(j.part_a_id);
            const b = partsById.get(j.part_b_id);
            const pill = STATUS_PILL[j.status];
            return (
              <li key={j.id} className="flex items-center gap-3 rounded-lg bg-astra-bg px-3 py-2">
                <span className="font-mono text-xs text-blue-400">{j.joint_id}</span>
                <span className="text-[11px] text-slate-300">
                  {JOINT_TYPE_LABELS[j.joint_type]} ·{' '}
                  <span className="font-mono">{a?.designation || a?.library_part.wardstone_part_number || `#${j.part_a_id}`}</span>
                  {' ↔ '}
                  <span className="font-mono">{b?.designation || b?.library_part.wardstone_part_number || `#${j.part_b_id}`}</span>
                </span>
                <span
                  className="ml-auto rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
                  style={{ background: pill.bg, color: pill.text }}
                >
                  {pill.label}
                </span>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────
//  Joints tab
// ─────────────────────────────────────────────────────────────────

function JointsTab({
  joints, filtered, partsById, partOptions,
  search, setSearch, typeFilter, setTypeFilter, statusFilter, setStatusFilter,
  partFilter, setPartFilter, onAddJoint, onApprove, onDelete, onRefresh,
  hasProjectParts,
}: {
  joints: MechanicalJointResponse[];
  filtered: MechanicalJointResponse[];
  partsById: Map<number, ProjectPartResponse>;
  partOptions: ProjectPartResponse[];
  search: string; setSearch: (v: string) => void;
  typeFilter: JointType | ''; setTypeFilter: (v: JointType | '') => void;
  statusFilter: JointStatus | ''; setStatusFilter: (v: JointStatus | '') => void;
  partFilter: number | null; setPartFilter: (v: number | null) => void;
  onAddJoint: () => void;
  onApprove: (j: MechanicalJointResponse) => void;
  onDelete: (j: MechanicalJointResponse) => void;
  onRefresh: () => void;
  hasProjectParts: boolean;
}) {
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" aria-hidden="true" />
          <label htmlFor="mj-search" className="sr-only">Search joints</label>
          <input
            id="mj-search"
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search joint ID, parts, drawing…"
            className="w-full rounded-lg border border-astra-border bg-astra-bg pl-8 pr-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
          />
        </div>
        <select
          aria-label="Filter by joint type"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value as JointType | '')}
          className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-xs text-slate-200 outline-none focus:border-blue-500/50"
        >
          <option value="">All types</option>
          {JOINT_TYPES.map((t) => <option key={t} value={t}>{JOINT_TYPE_LABELS[t]}</option>)}
        </select>
        <select
          aria-label="Filter by status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as JointStatus | '')}
          className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-xs text-slate-200 outline-none focus:border-blue-500/50"
        >
          <option value="">Any status</option>
          {JOINT_STATUSES.map((s) => <option key={s} value={s}>{STATUS_PILL[s].label}</option>)}
        </select>
        <select
          aria-label="Filter by part"
          value={partFilter == null ? '' : String(partFilter)}
          onChange={(e) => setPartFilter(e.target.value === '' ? null : Number(e.target.value))}
          className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-xs text-slate-200 outline-none focus:border-blue-500/50"
        >
          <option value="">Any part</option>
          {partOptions.map((p) => (
            <option key={p.id} value={p.id}>
              {p.designation || p.library_part.wardstone_part_number} — {p.library_part.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={onRefresh}
          aria-label="Refresh joints"
          className="rounded-lg border border-astra-border p-2 text-slate-400 hover:border-blue-500/30 hover:text-slate-200"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
        <button
          type="button"
          onClick={onAddJoint}
          disabled={!hasProjectParts}
          title={hasProjectParts ? '' : 'Need at least 2 project parts to create a joint'}
          className="flex items-center gap-1.5 rounded-lg bg-gradient-to-br from-blue-500 to-violet-500 px-3 py-2 text-xs font-semibold text-white hover:shadow-lg disabled:opacity-50"
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add Joint
        </button>
      </div>

      {filtered.length === 0 ? (
        <div className="rounded-xl border border-dashed border-astra-border bg-astra-surface px-6 py-12 text-center">
          <Wrench className="mx-auto mb-3 h-8 w-8 text-slate-600" aria-hidden="true" />
          <p className="mb-2 text-sm text-slate-300">
            {joints.length === 0
              ? 'No joints defined yet. Add your first joint to begin.'
              : 'No joints match the current filters.'}
          </p>
          {joints.length === 0 && (
            <button
              type="button"
              onClick={onAddJoint}
              disabled={!hasProjectParts}
              title={hasProjectParts ? '' : 'Need at least 2 project parts to create a joint'}
              className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-br from-blue-500 to-violet-500 px-3 py-1.5 text-xs font-semibold text-white hover:shadow-lg disabled:opacity-50"
            >
              <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add Joint
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-3">
          {filtered.map((j) => (
            <JointCard
              key={j.id}
              joint={j}
              partsById={partsById}
              onApprove={() => onApprove(j)}
              onDelete={() => onDelete(j)}
            />
          ))}
        </div>
      )}
    </div>
  );
}


function JointCard({
  joint, partsById, onApprove, onDelete,
}: {
  joint: MechanicalJointResponse;
  partsById: Map<number, ProjectPartResponse>;
  onApprove: () => void;
  onDelete: () => void;
}) {
  const a = partsById.get(joint.part_a_id);
  const b = partsById.get(joint.part_b_id);
  const pill = STATUS_PILL[joint.status];

  const torque = joint.torque_nominal_nm
    ? `${joint.torque_nominal_nm} N·m`
    : (joint.torque_min_nm && joint.torque_max_nm)
      ? `${joint.torque_min_nm}–${joint.torque_max_nm} N·m`
      : null;

  return (
    <div className="group rounded-xl border border-astra-border bg-astra-surface p-4 transition hover:border-blue-500/30">
      <div className="mb-2 flex items-start justify-between">
        <div className="flex items-center gap-2">
          <GitMerge className="h-3.5 w-3.5 text-blue-400" aria-hidden="true" />
          <span className="font-mono text-xs font-semibold text-slate-200">{joint.joint_id}</span>
          <span className="rounded-full bg-astra-surface-alt px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-slate-400">
            {JOINT_TYPE_LABELS[joint.joint_type]}
          </span>
        </div>
        <span
          className="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
          style={{ background: pill.bg, color: pill.text }}
        >
          {pill.label}
        </span>
      </div>

      <div className="mt-2 flex items-center gap-2 text-[11px] text-slate-300">
        <span className="rounded bg-astra-bg px-2 py-1 font-mono">
          {a?.designation || a?.library_part.wardstone_part_number || `#${joint.part_a_id}`}
        </span>
        <Link2 className="h-3 w-3 text-slate-500" aria-hidden="true" />
        <span className="rounded bg-astra-bg px-2 py-1 font-mono">
          {b?.designation || b?.library_part.wardstone_part_number || `#${joint.part_b_id}`}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px] text-slate-500">
        {joint.fastener_part && (
          <span className="rounded-full bg-blue-500/10 px-1.5 py-0.5 text-blue-300">
            {joint.fastener_part.wardstone_part_number}
            {joint.fastener_count ? ` ×${joint.fastener_count}` : ''}
          </span>
        )}
        {torque && <span>{torque}</span>}
        {joint.interface_drawing && <span>📑 {joint.interface_drawing}</span>}
      </div>

      <div className="mt-3 flex justify-end gap-2 opacity-0 transition-opacity group-hover:opacity-100">
        {joint.status === 'draft' && (
          <button
            type="button"
            onClick={onApprove}
            className="flex items-center gap-1 rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-[11px] font-semibold text-emerald-300 hover:bg-emerald-500/20"
          >
            <CheckCircle className="h-3 w-3" aria-hidden="true" /> Approve
          </button>
        )}
        <button
          type="button"
          onClick={onDelete}
          className="flex items-center gap-1 rounded border border-red-500/30 bg-red-500/10 px-2 py-1 text-[11px] font-semibold text-red-300 hover:bg-red-500/20"
        >
          <Trash2 className="h-3 w-3" aria-hidden="true" />
          {joint.status === 'active' ? 'Force delete' : 'Delete'}
        </button>
      </div>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────
//  Parts-with-joints tab
// ─────────────────────────────────────────────────────────────────

function PartsWithJointsTab({
  partsWithJoints, onPick,
}: {
  partsWithJoints: Array<{ part: ProjectPartResponse | undefined; count: number; id: number }>;
  onPick: (ppId: number) => void;
}) {
  if (partsWithJoints.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-astra-border bg-astra-surface px-6 py-12 text-center">
        <Box className="mx-auto mb-3 h-8 w-8 text-slate-600" aria-hidden="true" />
        <p className="text-sm text-slate-300">No project parts participate in any joint yet.</p>
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-3">
      {partsWithJoints.map(({ part, count, id }) => {
        if (!part) return null;
        return (
          <button
            key={id}
            type="button"
            onClick={() => onPick(id)}
            className="flex items-center gap-3 rounded-xl border border-astra-border bg-astra-surface p-3 text-left transition hover:border-blue-500/30"
          >
            <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-violet-500 text-[10px] font-bold text-white">
              {(part.library_part.part_type || 'X').slice(0, 3).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 text-xs">
                <span className="font-mono text-slate-200">
                  {part.designation || part.library_part.wardstone_part_number}
                </span>
                <span className="rounded-full bg-blue-500/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase text-blue-300">
                  {part.library_part.part_type}
                </span>
              </div>
              <div className="truncate text-[11px] text-slate-300">{part.library_part.name}</div>
              <div className="mt-0.5 text-[10px] text-emerald-300">
                Used in {count} joint{count === 1 ? '' : 's'}
              </div>
            </div>
            <ChevronRight className="h-4 w-4 flex-shrink-0 text-slate-500" aria-hidden="true" />
          </button>
        );
      })}
    </div>
  );
}
