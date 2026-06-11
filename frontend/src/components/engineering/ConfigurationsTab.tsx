'use client';

/**
 * ASTRA — Engineering » Configurations tab (spec §8 UX)
 * =======================================================
 * File: frontend/src/components/engineering/ConfigurationsTab.tsx
 *
 * HAROLD-named (CFG) vehicle configurations:
 *   - searchable list (WPN, name, current rev, total mass, component
 *     count, baseline, updated)
 *   - "New configuration" → /engineering/configurations/new (builder)
 *   - row → /engineering/configurations/[wpn] (flight card)
 *   - per-row Clone → new CFG identity from the latest revision
 */

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  AlertTriangle, Boxes, ChevronRight, Copy, Loader2, Plus, RefreshCw,
  Search, X,
} from 'lucide-react';
import clsx from 'clsx';

import { engineeringAPI } from '@/lib/engineering-api';
import {
  type ConfigCreateResponse,
  type ConfigSummary,
  fmtDateTime,
  fmtKg,
} from '@/lib/engineering-types';
import { formatApiError } from '@/lib/errors';
import { useHasRole } from '@/lib/auth';

// ══════════════════════════════════════
//  Clone modal
// ══════════════════════════════════════

function CloneModal({
  source,
  onClose,
  onCloned,
}: {
  source: ConfigSummary;
  onClose: () => void;
  onCloned: (r: ConfigCreateResponse) => void;
}) {
  const [name, setName] = useState(`${source.name} (clone)`);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const submit = useCallback(async () => {
    if (!name.trim()) {
      setError('A name for the new configuration is required.');
      return;
    }
    setError('');
    setSaving(true);
    try {
      const r = await engineeringAPI.cloneConfig(source.wpn, name.trim());
      onCloned(r.data);
    } catch (e) {
      // HAROLD outages arrive as 503 with a string detail — surface it.
      setError(formatApiError(e, 'Clone failed'));
      setSaving(false);
    }
  }, [name, onCloned, source.wpn]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="clone-config-title"
      onClick={(e) => { if (e.target === e.currentTarget && !saving) onClose(); }}
    >
      <div className="w-full max-w-md rounded-xl border border-astra-border bg-astra-surface p-5 shadow-2xl">
        <div className="mb-3 flex items-start justify-between gap-3">
          <h2 id="clone-config-title" className="flex items-center gap-2 text-sm font-semibold text-slate-200">
            <Copy className="h-4 w-4 text-blue-400" aria-hidden="true" />
            Clone configuration
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            aria-label="Close clone dialog"
            className="rounded p-1 text-slate-500 hover:bg-astra-surface-alt hover:text-slate-300"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        <p className="mb-3 text-xs leading-relaxed text-slate-400">
          Copies the latest revision of{' '}
          <span className="font-mono font-bold text-slate-200">{source.wpn}</span>{' '}
          into a <strong className="text-slate-300">new</strong> configuration —
          HAROLD allocates a fresh CFG WPN.
        </p>

        <label htmlFor="clone-config-name" className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          New configuration name
        </label>
        <input
          id="clone-config-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') submit(); }}
          disabled={saving}
          autoFocus
          className="mb-3 w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
        />

        {error && (
          <div role="alert" className="mb-3 flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
            <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {error}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="rounded-lg border border-astra-border px-3 py-2 text-xs font-semibold text-slate-300 hover:text-slate-100 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={saving || !name.trim()}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {saving
              ? <><Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> Cloning — HAROLD is naming it…</>
              : <><Copy className="h-3.5 w-3.5" aria-hidden="true" /> Clone</>}
          </button>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  Tab
// ══════════════════════════════════════

export default function ConfigurationsTab() {
  const router = useRouter();
  const canWrite = useHasRole('admin', 'project_manager', 'requirements_engineer');

  const [items, setItems] = useState<ConfigSummary[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [cloneSource, setCloneSource] = useState<ConfigSummary | null>(null);
  const [cloned, setCloned] = useState<ConfigCreateResponse | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    engineeringAPI.listConfigs({ q: search || undefined, limit: 200 })
      .then((r) => { setItems(r.data); setError(''); })
      .catch((e) => setError(formatApiError(e, 'Failed to load configurations')))
      .finally(() => setLoading(false));
  }, [search]);

  useEffect(() => {
    const handle = setTimeout(refresh, 250);
    return () => clearTimeout(handle);
  }, [refresh]);

  const onCloned = useCallback((r: ConfigCreateResponse) => {
    setCloneSource(null);
    setCloned(r);
    refresh();
  }, [refresh]);

  return (
    <div>
      {/* ── Clone success status ── */}
      {cloned && (
        <div
          role="status"
          className="mb-3 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-400"
        >
          <div className="flex flex-wrap items-center gap-1.5">
            Cloned as
            <span className="font-mono font-bold tracking-wider text-emerald-300">{cloned.wpn}</span>
            — named by HAROLD
            <button
              type="button"
              onClick={() => router.push(`/engineering/configurations/${encodeURIComponent(cloned.config_wpn)}`)}
              className="ml-auto font-semibold text-emerald-300 underline-offset-2 hover:underline"
            >
              View configuration →
            </button>
          </div>
        </div>
      )}

      {/* ── Toolbar ── */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" aria-hidden="true" />
          <label htmlFor="configs-search" className="sr-only">Search configurations</label>
          <input
            id="configs-search"
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search configurations by WPN or name…"
            className="w-full rounded-lg border border-astra-border bg-astra-bg pl-8 pr-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
          />
        </div>
        <button
          type="button"
          onClick={refresh}
          aria-label="Refresh configurations"
          className="rounded-lg border border-astra-border p-2 text-slate-400 hover:border-blue-500/30 hover:text-slate-200"
        >
          <RefreshCw className={clsx('h-3.5 w-3.5', loading && 'animate-spin')} aria-hidden="true" />
        </button>
        {canWrite && (
          <button
            type="button"
            onClick={() => router.push('/engineering/configurations/new')}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-500"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden="true" /> New configuration
          </button>
        )}
      </div>

      {error && (
        <div role="alert" className="mb-3 flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
          <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {error}
        </div>
      )}

      {/* ── Table ── */}
      <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
        {loading && items.length === 0 ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="h-5 w-5 animate-spin text-blue-500" aria-label="Loading" />
          </div>
        ) : items.length === 0 ? (
          <div className="py-12 text-center text-sm text-slate-500">
            <Boxes className="mx-auto mb-2 h-8 w-8 text-slate-600" aria-hidden="true" />
            No configurations yet.
            {canWrite
              ? <> Assemble one with <strong className="text-slate-300">New configuration</strong>.</>
              : ' Configurations are assembled by engineering write roles.'}
          </div>
        ) : (
          <table className="w-full text-xs" aria-label="Vehicle configurations">
            <thead className="bg-astra-surface-alt text-slate-400">
              <tr>
                <th scope="col" className="px-3 py-2 text-left font-semibold">CFG WPN</th>
                <th scope="col" className="px-3 py-2 text-left font-semibold">Name</th>
                <th scope="col" className="px-3 py-2 text-center font-semibold">Rev</th>
                <th scope="col" className="px-3 py-2 text-right font-semibold">Total Mass</th>
                <th scope="col" className="px-3 py-2 text-right font-semibold">Components</th>
                <th scope="col" className="px-3 py-2 text-center font-semibold">Baseline</th>
                <th scope="col" className="px-3 py-2 text-left font-semibold">Updated</th>
                <th scope="col" className="px-3 py-2 text-right font-semibold">
                  {canWrite ? 'Actions' : <span className="sr-only">Open</span>}
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr
                  key={c.id}
                  className="border-t border-astra-border hover:bg-astra-surface-alt cursor-pointer"
                  onClick={() => router.push(`/engineering/configurations/${encodeURIComponent(c.wpn)}`)}
                >
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <Boxes className="h-3.5 w-3.5 flex-shrink-0 text-blue-400" aria-hidden="true" />
                      <span className="font-mono font-bold tracking-wider text-slate-100">{c.wpn}</span>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-slate-300">{c.name}</td>
                  <td className="px-3 py-2 text-center font-mono text-slate-300">
                    {c.current_rev || '—'}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums text-slate-300">
                    {fmtKg(c.total_mass_kg)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums text-slate-300">
                    {c.component_count}
                  </td>
                  <td className="px-3 py-2 text-center font-mono tabular-nums text-slate-400">
                    {c.astra_baseline_id != null ? `#${c.astra_baseline_id}` : '—'}
                  </td>
                  <td className="px-3 py-2 text-slate-500">{fmtDateTime(c.updated_at)}</td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex items-center justify-end gap-1.5">
                      {canWrite && (
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); setCloned(null); setCloneSource(c); }}
                          className="flex items-center gap-1 rounded-lg border border-astra-border px-2 py-1 text-[10px] font-semibold text-slate-400 hover:border-blue-500/40 hover:text-blue-300"
                          aria-label={`Clone configuration ${c.wpn}`}
                        >
                          <Copy className="h-3 w-3" aria-hidden="true" /> Clone
                        </button>
                      )}
                      <ChevronRight className="inline h-3.5 w-3.5 text-slate-500" aria-hidden="true" />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {cloneSource && (
        <CloneModal
          source={cloneSource}
          onClose={() => setCloneSource(null)}
          onCloned={onCloned}
        />
      )}
    </div>
  );
}
