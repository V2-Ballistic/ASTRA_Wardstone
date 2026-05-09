'use client';

/**
 * ASTRA — CatalogPartPicker (TDD-SYSARCH-002 Phase 3 §3 + AD-9)
 * ==============================================================
 * Reusable searchable picker for `catalog_parts` rows. Built generic
 * (`allowedClasses` prop) so the future Project Parts BOM page
 * (TDD-PROJPARTS-001) can drop it in without rebuilding.
 *
 * UX:
 *   - Combobox: input + dropdown.
 *   - Type to search; debounced 300 ms.
 *   - Each result row: WPN (mono), name, manufacturer chip,
 *     part_class chip, mass.
 *   - "None / clear" sentinel at the top of the dropdown to deselect.
 *   - Empty state: "No catalog parts match. Upload a STEP file in the
 *     Catalog or add manually."
 *   - onChange receives the full CatalogPart row, or null on clear.
 *
 * Backend filter API note (CAT-002 gotcha §9): the existing
 * /api/v1/catalog/parts endpoint accepts a single `part_class` value
 * per request. The picker fans out one request per allowed class and
 * merges the results client-side, dedup-by-id, then ranks by best
 * match against the typed query.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronsUpDown, Cpu, Loader2, Package, Search, Trash2, X } from 'lucide-react';
import clsx from 'clsx';

import { catalogAPI } from '@/lib/catalog-api';
import {
  type CatalogPart,
  type LifecycleStatus,
  type PartClass,
  PART_CLASS_LABELS,
} from '@/lib/catalog-types';


export interface CatalogPartPickerProps {
  /** Optional filter — accept only catalog parts with these classes.
   *  When omitted, all classes are accepted. */
  allowedClasses?: PartClass[];
  /** Optional lifecycle filter (defaults to no filter). */
  lifecycleStatus?: LifecycleStatus;
  /** Currently-selected catalog part. null shows the placeholder. */
  value: CatalogPart | null;
  /** Fired on selection or clear. */
  onChange: (part: CatalogPart | null) => void;
  /** Visible placeholder when nothing is selected. */
  placeholder?: string;
  /** Show a small inline label above the trigger button. */
  label?: string;
  /** Disable the picker entirely (e.g. while saving). */
  disabled?: boolean;
}


const DEBOUNCE_MS = 300;
const MAX_RESULTS = 20;


export default function CatalogPartPicker({
  allowedClasses,
  lifecycleStatus,
  value,
  onChange,
  placeholder = 'Pick a catalog part…',
  label,
  disabled = false,
}: CatalogPartPickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [results, setResults] = useState<CatalogPart[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // ── Debounce typing → search ──
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [query]);

  // ── Outside-click → close ──
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

  // ── Focus input on open ──
  useEffect(() => {
    if (open) {
      // Defer to after the popover renders.
      const t = setTimeout(() => inputRef.current?.focus(), 0);
      return () => clearTimeout(t);
    }
  }, [open]);

  // ── Search runner. Fan out one request per allowed class
  //    (single-class endpoint), merge + dedup by id, slice to MAX. ──
  const runSearch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const classes = (allowedClasses && allowedClasses.length > 0)
        ? allowedClasses
        : ([undefined] as Array<PartClass | undefined>);
      const responses = await Promise.all(
        classes.map((cls) => catalogAPI.listParts({
          q: debouncedQuery || undefined,
          part_class: cls,
          lifecycle_status: lifecycleStatus,
          limit: MAX_RESULTS,
        }).then((r) => r.data).catch(() => [] as CatalogPart[])),
      );
      const merged: Record<number, CatalogPart> = {};
      for (const list of responses) {
        for (const row of list) {
          merged[row.id] = row;
        }
      }
      const ranked = Object.values(merged).sort((a, b) => {
        // Crude rank: exact part_number match wins, then prefix, then lex.
        const q = (debouncedQuery || '').toLowerCase();
        if (!q) return a.part_number.localeCompare(b.part_number);
        const aExact = a.part_number.toLowerCase() === q ? 0 : 1;
        const bExact = b.part_number.toLowerCase() === q ? 0 : 1;
        if (aExact !== bExact) return aExact - bExact;
        const aPrefix = a.part_number.toLowerCase().startsWith(q) ? 0 : 1;
        const bPrefix = b.part_number.toLowerCase().startsWith(q) ? 0 : 1;
        if (aPrefix !== bPrefix) return aPrefix - bPrefix;
        return a.part_number.localeCompare(b.part_number);
      });
      setResults(ranked.slice(0, MAX_RESULTS));
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || (e instanceof Error ? e.message : 'Search failed');
      setError(detail);
    } finally {
      setLoading(false);
    }
  }, [allowedClasses, lifecycleStatus, debouncedQuery]);

  // ── Run search on open OR when debounced query changes while open ──
  useEffect(() => {
    if (!open) return;
    runSearch();
  }, [open, runSearch]);

  // ── Handlers ──
  const onPick = (part: CatalogPart) => {
    onChange(part);
    setOpen(false);
    setQuery('');
  };

  const onClear = () => {
    onChange(null);
    setOpen(false);
  };

  // ── Display helpers ──
  const displayLabel = useMemo(() => {
    if (!value) return placeholder;
    return `${value.part_number} — ${value.name}`;
  }, [value, placeholder]);

  return (
    <div ref={containerRef} className="relative">
      {label && (
        <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          {label}
        </label>
      )}

      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={disabled}
        className={clsx(
          'w-full flex items-center justify-between rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm outline-none transition focus:border-blue-500/50',
          value ? 'text-slate-200' : 'text-slate-500',
          disabled && 'opacity-50 cursor-not-allowed',
        )}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <div className="flex min-w-0 items-center gap-2">
          <Package className="h-3.5 w-3.5 flex-shrink-0 text-slate-500" aria-hidden="true" />
          <span className="truncate">{displayLabel}</span>
        </div>
        <div className="flex flex-shrink-0 items-center gap-1">
          {value && (
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => { e.stopPropagation(); onClear(); }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.stopPropagation();
                  onClear();
                }
              }}
              className="rounded p-0.5 text-slate-500 hover:bg-astra-surface-alt hover:text-slate-300"
              aria-label="Clear catalog part selection"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </span>
          )}
          <ChevronsUpDown className="h-3.5 w-3.5 text-slate-500" aria-hidden="true" />
        </div>
      </button>

      {open && (
        <div
          role="listbox"
          className="absolute left-0 right-0 z-30 mt-1 max-h-80 overflow-hidden rounded-xl border border-astra-border bg-astra-surface shadow-xl"
        >
          {/* Search input */}
          <div className="border-b border-astra-border bg-astra-surface-alt p-2">
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500"
                aria-hidden="true"
              />
              <input
                ref={inputRef}
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search WPN, name, manufacturer…"
                className="w-full rounded border border-astra-border bg-astra-bg pl-8 pr-2 py-1.5 text-xs text-slate-200 outline-none focus:border-blue-500/50"
              />
            </div>
          </div>

          <div className="max-h-64 overflow-y-auto">
            {/* None / clear sentinel */}
            <button
              type="button"
              onClick={onClear}
              className="flex w-full items-center gap-2 border-b border-astra-border px-3 py-2 text-left text-xs text-slate-400 hover:bg-astra-surface-alt"
            >
              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
              <span>None / clear selection</span>
            </button>

            {loading && (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-4 w-4 animate-spin text-blue-500" aria-label="Searching" />
              </div>
            )}

            {!loading && error && (
              <div role="alert" className="px-3 py-3 text-xs text-red-400">
                {error}
              </div>
            )}

            {!loading && !error && results.length === 0 && (
              <div className="px-3 py-6 text-center text-xs text-slate-500">
                <Package className="mx-auto mb-1.5 h-6 w-6 text-slate-600" aria-hidden="true" />
                No catalog parts match. Upload a STEP file in the Catalog
                or add a part manually.
              </div>
            )}

            {!loading && !error && results.map((row) => (
              <button
                key={row.id}
                type="button"
                role="option"
                aria-selected={value?.id === row.id}
                onClick={() => onPick(row)}
                className={clsx(
                  'flex w-full flex-col gap-1 border-b border-astra-border px-3 py-2 text-left transition hover:bg-astra-surface-alt',
                  value?.id === row.id && 'bg-blue-500/5',
                )}
              >
                <div className="flex items-center gap-2">
                  <Cpu className="h-3.5 w-3.5 text-blue-400" aria-hidden="true" />
                  <span className="font-mono text-xs text-slate-200">{row.part_number}</span>
                  <span
                    className="rounded-full bg-blue-500/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase text-blue-300"
                  >
                    {PART_CLASS_LABELS[row.part_class] || row.part_class}
                  </span>
                  {row.mass_kg != null && (
                    <span className="ml-auto text-[10px] text-slate-500">
                      {row.mass_kg} kg
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-slate-300 truncate">{row.name}</div>
                {row.supplier_name && (
                  <div className="text-[10px] text-slate-500">{row.supplier_name}</div>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
