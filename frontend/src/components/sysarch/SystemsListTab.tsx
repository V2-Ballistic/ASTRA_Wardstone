'use client';

/**
 * ASTRA — SystemsListTab (TDD-SYSARCH-002 §4 Phase 4)
 * =====================================================
 * Project-wide systems list under the new System Architecture page.
 * Card grid with search + system_type / status filters. Click → detail
 * page at /system-architecture/system/[id].
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Boxes, ChevronRight, Loader2, Plus, RefreshCw, Search,
} from 'lucide-react';
import clsx from 'clsx';

import { interfaceAPI } from '@/lib/interface-api';
import type {
  System, SystemStatus, SystemType,
} from '@/lib/interface-types';
import AddSystemModal from './AddSystemModal';


interface Props {
  projectId: number;
}


function initialsOfType(t: SystemType): string {
  return (t || 'sys').split('_').map((s) => s[0] || '').join('').toUpperCase().slice(0, 3);
}


export default function SystemsListTab({ projectId }: Props) {
  const router = useRouter();
  const [systems, setSystems] = useState<System[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<SystemType | ''>('');
  const [statusFilter, setStatusFilter] = useState<SystemStatus | ''>('');
  const [addOpen, setAddOpen] = useState(false);

  const refresh = useCallback(() => {
    setLoading(true);
    setError(null);
    interfaceAPI.listSystems(projectId, 'flat')
      .then((r) => setSystems(r.data))
      .catch((e) => {
        const detail = e?.response?.data?.detail || e?.message || 'Failed to load systems';
        setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
      })
      .finally(() => setLoading(false));
  }, [projectId]);

  useEffect(() => { refresh(); }, [refresh]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return systems.filter((s) => {
      if (typeFilter && s.system_type !== typeFilter) return false;
      if (statusFilter && s.status !== statusFilter) return false;
      if (q) {
        const blob = `${s.name} ${s.abbreviation || ''} ${s.system_id || ''}`.toLowerCase();
        if (!blob.includes(q)) return false;
      }
      return true;
    });
  }, [systems, search, typeFilter, statusFilter]);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" aria-hidden="true" />
          <label htmlFor="sys-list-search" className="sr-only">Search systems</label>
          <input
            id="sys-list-search"
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, abbreviation, system_id…"
            className="w-full rounded-lg border border-astra-border bg-astra-bg pl-8 pr-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
          />
        </div>
        <select
          aria-label="Filter by system type"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value as SystemType | '')}
          className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-xs text-slate-200 outline-none focus:border-blue-500/50"
        >
          <option value="">All types</option>
          {([
            'subsystem', 'lru', 'wru', 'sru', 'sensor_suite', 'actuator_assembly',
            'processor_unit', 'power_system', 'thermal_system', 'structural',
            'ground_segment', 'vehicle', 'payload', 'antenna_system', 'propulsion',
            'guidance_nav_control', 'communication', 'data_handling', 'ordnance',
            'test_equipment', 'external_system', 'software', 'firmware', 'custom',
          ] as SystemType[]).map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select
          aria-label="Filter by status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as SystemStatus | '')}
          className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-xs text-slate-200 outline-none focus:border-blue-500/50"
        >
          <option value="">Any status</option>
          {([
            'concept', 'preliminary_design', 'detailed_design', 'fabrication',
            'integration', 'qualification_test', 'acceptance_test', 'operational',
            'maintenance', 'retired', 'obsolete',
          ] as SystemStatus[]).map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <button
          type="button"
          onClick={refresh}
          aria-label="Refresh systems"
          className="rounded-lg border border-astra-border p-2 text-slate-400 hover:border-blue-500/30 hover:text-slate-200"
        >
          <RefreshCw className={clsx('h-3.5 w-3.5', loading && 'animate-spin')} aria-hidden="true" />
        </button>
        <button
          type="button"
          onClick={() => setAddOpen(true)}
          className="flex items-center gap-1.5 rounded-lg bg-gradient-to-br from-blue-500 to-violet-500 px-3 py-2 text-xs font-semibold text-white hover:shadow-lg"
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add System
        </button>
      </div>

      {error && (
        <div role="alert" className="mb-3 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
          {error}
        </div>
      )}

      {loading && systems.length === 0 ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-5 w-5 animate-spin text-blue-500" aria-label="Loading" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-dashed border-astra-border bg-astra-surface px-6 py-12 text-center">
          <Boxes className="mx-auto mb-3 h-8 w-8 text-slate-600" aria-hidden="true" />
          <p className="mb-2 text-sm text-slate-300">
            {systems.length === 0
              ? 'No systems defined yet. Add your first system to begin decomposing the architecture.'
              : 'No systems match the current filters.'}
          </p>
          {systems.length === 0 && (
            <button
              type="button"
              onClick={() => setAddOpen(true)}
              className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-br from-blue-500 to-violet-500 px-3 py-1.5 text-xs font-semibold text-white hover:shadow-lg"
            >
              <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add System
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {filtered.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => router.push(`/projects/${projectId}/system-architecture/system/${s.id}`)}
              className="flex flex-col rounded-xl border border-astra-border bg-astra-surface p-4 text-left transition hover:border-blue-500/30 hover:shadow-lg"
            >
              <div className="flex items-start gap-3">
                <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-violet-500 text-[11px] font-bold text-white">
                  {initialsOfType(s.system_type)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-semibold text-slate-100">{s.name}</span>
                    {s.abbreviation && (
                      <span className="rounded-full bg-blue-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-blue-300">
                        {s.abbreviation}
                      </span>
                    )}
                  </div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[10px] text-slate-500">
                    <span className="font-mono">{s.system_id}</span>
                    <span className="rounded-full bg-astra-surface-alt px-1.5 py-0.5 uppercase tracking-wider">{s.system_type}</span>
                    {s.wbs_number && <span>WBS {s.wbs_number}</span>}
                    {s.responsible_org && <span>· {s.responsible_org}</span>}
                  </div>
                </div>
                <span className="rounded-full bg-slate-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-300">
                  {s.status}
                </span>
                <ChevronRight className="h-4 w-4 flex-shrink-0 text-slate-500" aria-hidden="true" />
              </div>
            </button>
          ))}
        </div>
      )}

      <AddSystemModal
        open={addOpen}
        projectId={projectId}
        systems={systems}
        onClose={() => setAddOpen(false)}
        onCreated={(s) => {
          setSystems((prev) => [...prev, s]);
          // Navigate to the new system's detail page so the user can keep editing.
          router.push(`/projects/${projectId}/system-architecture/system/${s.id}`);
        }}
      />
    </div>
  );
}
