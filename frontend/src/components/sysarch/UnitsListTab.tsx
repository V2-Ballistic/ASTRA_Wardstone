'use client';

/**
 * ASTRA — UnitsListTab (TDD-SYSARCH-002 §4 Phase 4)
 * ===================================================
 * Project-wide flat unit list. Filters: search, system, type, status,
 * and a catalog-linkage segmented control (All / Linked / Not linked).
 * Click a unit → /system-architecture/unit/[id].
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ChevronRight, Cpu, Link2, Loader2, Plus, RefreshCw, Search,
} from 'lucide-react';
import clsx from 'clsx';

import { interfaceAPI } from '@/lib/interface-api';
import type {
  System, UnitStatus, UnitSummary, UnitType,
} from '@/lib/interface-types';
import AddUnitModal from './AddUnitModal';


type LinkFilter = 'all' | 'linked' | 'not_linked';


interface Props {
  projectId: number;
}


function initialsOfUnitType(t: UnitType): string {
  return (t || 'unit').split('_').map((s) => s[0] || '').join('').toUpperCase().slice(0, 3);
}


export default function UnitsListTab({ projectId }: Props) {
  const router = useRouter();
  const [systems, setSystems] = useState<System[]>([]);
  const [units, setUnits] = useState<UnitSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [systemFilter, setSystemFilter] = useState<number | ''>('');
  const [typeFilter, setTypeFilter] = useState<UnitType | ''>('');
  const [statusFilter, setStatusFilter] = useState<UnitStatus | ''>('');
  const [linkFilter, setLinkFilter] = useState<LinkFilter>('all');
  const [addOpen, setAddOpen] = useState(false);

  // Load systems once for the dropdown + the parent-system chip on each card.
  useEffect(() => {
    interfaceAPI.listSystems(projectId, 'flat')
      .then((r) => setSystems(r.data))
      .catch(() => { /* non-fatal — units still render */ });
  }, [projectId]);

  const refresh = useCallback(() => {
    setLoading(true);
    setError(null);
    const params: {
      system_id?: number; unit_type?: string; search?: string;
      linked_to_catalog?: boolean; limit?: number;
    } = { limit: 200 };
    if (systemFilter !== '') params.system_id = systemFilter;
    if (typeFilter !== '') params.unit_type = typeFilter;
    if (search.trim()) params.search = search.trim();
    if (linkFilter === 'linked') params.linked_to_catalog = true;
    if (linkFilter === 'not_linked') params.linked_to_catalog = false;

    interfaceAPI.listUnits(projectId, params)
      .then((r) => setUnits(r.data))
      .catch((e) => {
        const detail = e?.response?.data?.detail || e?.message || 'Failed to load units';
        setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
      })
      .finally(() => setLoading(false));
  }, [projectId, search, systemFilter, typeFilter, linkFilter]);

  useEffect(() => { refresh(); }, [refresh]);

  // Status filter is client-side because the backend list doesn't expose
  // it (consistent with the existing /interfaces tab behavior).
  const filtered = useMemo(() => {
    if (!statusFilter) return units;
    return units.filter((u) => u.status === statusFilter);
  }, [units, statusFilter]);

  const systemNameById = useMemo(() => {
    const out: Record<number, string> = {};
    for (const s of systems) {
      out[s.id] = s.abbreviation || s.name;
    }
    return out;
  }, [systems]);

  return (
    <div>
      {/* Filter row 1: search + system / type / status */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" aria-hidden="true" />
          <label htmlFor="unit-list-search" className="sr-only">Search units</label>
          <input
            id="unit-list-search"
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search designation, name, manufacturer, MPN…"
            className="w-full rounded-lg border border-astra-border bg-astra-bg pl-8 pr-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
          />
        </div>
        <select
          aria-label="Filter by system"
          value={systemFilter === '' ? '' : String(systemFilter)}
          onChange={(e) => setSystemFilter(e.target.value === '' ? '' : Number(e.target.value))}
          className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-xs text-slate-200 outline-none focus:border-blue-500/50"
        >
          <option value="">All systems</option>
          {systems.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
        <select
          aria-label="Filter by unit type"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value as UnitType | '')}
          className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-xs text-slate-200 outline-none focus:border-blue-500/50"
        >
          <option value="">All types</option>
          {([
            'lru', 'wru', 'sru', 'cca', 'pcb', 'sensor', 'actuator', 'motor',
            'processor', 'fpga', 'asic', 'power_supply', 'transmitter',
            'receiver', 'transceiver', 'antenna', 'cable_assembly',
            'connector_assembly', 'custom',
          ] as UnitType[]).map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select
          aria-label="Filter by status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as UnitStatus | '')}
          className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-xs text-slate-200 outline-none focus:border-blue-500/50"
        >
          <option value="">Any status</option>
          {([
            'concept', 'preliminary_design', 'detailed_design', 'prototype',
            'engineering_model', 'qualification_unit', 'flight_unit',
            'production', 'installed', 'qualified', 'accepted', 'operational',
            'failed', 'obsolete',
          ] as UnitStatus[]).map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {/* Filter row 2: linkage segmented control + actions */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div role="radiogroup" aria-label="Catalog linkage" className="inline-flex overflow-hidden rounded-lg border border-astra-border">
          {([
            { value: 'all', label: 'All' },
            { value: 'linked', label: 'Linked' },
            { value: 'not_linked', label: 'Not linked' },
          ] as { value: LinkFilter; label: string }[]).map((opt) => (
            <button
              key={opt.value}
              type="button"
              role="radio"
              aria-checked={linkFilter === opt.value}
              onClick={() => setLinkFilter(opt.value)}
              className={clsx(
                'px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider transition',
                linkFilter === opt.value
                  ? 'bg-blue-500/20 text-blue-300'
                  : 'text-slate-400 hover:bg-astra-surface-alt hover:text-slate-200',
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={refresh}
            aria-label="Refresh units"
            className="rounded-lg border border-astra-border p-2 text-slate-400 hover:border-blue-500/30 hover:text-slate-200"
          >
            <RefreshCw className={clsx('h-3.5 w-3.5', loading && 'animate-spin')} aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => setAddOpen(true)}
            className="flex items-center gap-1.5 rounded-lg bg-gradient-to-br from-blue-500 to-violet-500 px-3 py-2 text-xs font-semibold text-white hover:shadow-lg"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add Unit
          </button>
        </div>
      </div>

      {error && (
        <div role="alert" className="mb-3 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
          {error}
        </div>
      )}

      {loading && units.length === 0 ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-5 w-5 animate-spin text-blue-500" aria-label="Loading" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-dashed border-astra-border bg-astra-surface px-6 py-12 text-center">
          <Cpu className="mx-auto mb-3 h-8 w-8 text-slate-600" aria-hidden="true" />
          <p className="mb-2 text-sm text-slate-300">
            {units.length === 0
              ? 'No units defined. Add a unit to start populating systems.'
              : 'No units match the current filters.'}
          </p>
          {units.length === 0 && (
            <button
              type="button"
              onClick={() => setAddOpen(true)}
              className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-br from-blue-500 to-violet-500 px-3 py-1.5 text-xs font-semibold text-white hover:shadow-lg"
            >
              <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add Unit
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-3">
          {filtered.map((u) => {
            const linked = u.catalog_part_summary != null;
            const sysName = systemNameById[u.system_id] || `system #${u.system_id}`;
            return (
              <button
                key={u.id}
                type="button"
                onClick={() => router.push(`/projects/${projectId}/system-architecture/unit/${u.id}`)}
                className="flex flex-col rounded-xl border border-astra-border bg-astra-surface p-4 text-left transition hover:border-blue-500/30 hover:shadow-lg"
              >
                <div className="flex items-start gap-3">
                  <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-violet-500 text-[10px] font-bold text-white">
                    {initialsOfUnitType(u.unit_type)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-mono text-xs font-semibold text-slate-200">{u.designation}</span>
                      <span className="rounded-full bg-astra-surface-alt px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-slate-400">
                        {u.unit_type}
                      </span>
                    </div>
                    <div className="mt-0.5 truncate text-sm text-slate-100">{u.name}</div>
                  </div>
                  <span className="rounded-full bg-slate-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-300">
                    {u.status}
                  </span>
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px] text-slate-500">
                  <span className="rounded-full bg-blue-500/10 px-1.5 py-0.5 font-semibold text-blue-300">
                    {sysName}
                  </span>
                </div>

                <div className="mt-2 flex items-center justify-between">
                  {linked ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
                      <Link2 className="h-3 w-3" aria-hidden="true" />
                      <span className="font-mono">{u.catalog_part_summary?.part_number}</span>
                    </span>
                  ) : (
                    <span className="text-[10px] italic text-slate-500">Not linked to catalog</span>
                  )}
                  <ChevronRight className="h-4 w-4 text-slate-500" aria-hidden="true" />
                </div>

                <div className="mt-2 flex items-center gap-2 text-[10px] text-slate-500">
                  <span>{u.manufacturer}</span>
                  <span>·</span>
                  <span className="font-mono">{u.part_number}</span>
                </div>
              </button>
            );
          })}
        </div>
      )}

      <AddUnitModal
        open={addOpen}
        projectId={projectId}
        systems={systems}
        defaultSystemId={systemFilter === '' ? null : systemFilter}
        onClose={() => setAddOpen(false)}
        onCreated={(unit) => {
          refresh();
          router.push(`/projects/${projectId}/system-architecture/unit/${unit.id}`);
        }}
      />
    </div>
  );
}
