'use client';

/**
 * ASTRA — Engineering » Aero tab (spec §6 UX)
 * =============================================
 * File: frontend/src/components/engineering/AeroTab.tsx
 *
 * Aero-deck list + multi-file drag-drop ingest. The uploader does NOT
 * name the deck — HAROLD's filename precheck decides; the optional
 * fields (name hint, oml_wpn, Sref, Lref) ride along as form fields.
 */

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  AlertTriangle, ChevronRight, Loader2, RefreshCw, Search,
  SlidersHorizontal, Wind,
} from 'lucide-react';
import clsx from 'clsx';

import { engineeringAPI, type AeroIngestOptions } from '@/lib/engineering-api';
import {
  type AeroDeckSummary,
  type AeroIngestResponse,
  fmtDateTime,
  fmtRange,
} from '@/lib/engineering-types';
import { formatApiError } from '@/lib/errors';
import { useHasRole } from '@/lib/auth';
import UploadDropzone from './UploadDropzone';

export default function AeroTab() {
  const router = useRouter();
  const canWrite = useHasRole('admin', 'project_manager', 'requirements_engineer');

  const [items, setItems] = useState<AeroDeckSummary[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // ── ingest state ──
  const [uploading, setUploading] = useState(false);
  const [ingested, setIngested] = useState<AeroIngestResponse | null>(null);
  const [showOptions, setShowOptions] = useState(false);
  const [optName, setOptName] = useState('');
  const [optOml, setOptOml] = useState('');
  const [optSref, setOptSref] = useState('');
  const [optLref, setOptLref] = useState('');

  const refresh = useCallback(() => {
    setLoading(true);
    engineeringAPI.listAeroDecks({ q: search || undefined, limit: 200 })
      .then((r) => { setItems(r.data); setError(''); })
      .catch((e) => setError(formatApiError(e, 'Failed to load aero decks')))
      .finally(() => setLoading(false));
  }, [search]);

  useEffect(() => {
    const handle = setTimeout(refresh, 250);
    return () => clearTimeout(handle);
  }, [refresh]);

  const onSourceFiles = useCallback(async (files: File[]) => {
    if (files.length === 0) return;
    setError('');
    setIngested(null);
    setUploading(true);
    try {
      const opts: AeroIngestOptions = {};
      if (optName.trim()) opts.name = optName.trim();
      if (optOml.trim()) opts.oml_wpn = optOml.trim();
      const sref = parseFloat(optSref);
      const lref = parseFloat(optLref);
      if (Number.isFinite(sref)) opts.sref_m2 = sref;
      if (Number.isFinite(lref)) opts.lref_m = lref;
      const r = await engineeringAPI.ingestAeroSource(files, opts);
      setIngested(r.data);
      refresh();
    } catch (e) {
      setError(formatApiError(e, 'Aero source ingest failed'));
    } finally {
      setUploading(false);
    }
  }, [optLref, optName, optOml, optSref, refresh]);

  return (
    <div>
      {/* ── Drag-drop ingest (write roles only) ── */}
      {canWrite && (
        <div className="mb-4">
          <UploadDropzone
            label="Drop aero coefficient CSVs here"
            sublabel="1..N source files merge into one deck — HAROLD names it automatically"
            accept=".csv,text/csv"
            multiple
            uploading={uploading}
            uploadingLabel="Merging sources — HAROLD is naming the deck…"
            onFiles={onSourceFiles}
          />
          <button
            type="button"
            onClick={() => setShowOptions((v) => !v)}
            aria-expanded={showOptions}
            aria-controls="aero-ingest-options"
            className="mt-2 flex items-center gap-1.5 text-[11px] font-semibold text-slate-400 hover:text-slate-200"
          >
            <SlidersHorizontal className="h-3 w-3" aria-hidden="true" />
            Optional ingest fields {showOptions ? '▴' : '▾'}
          </button>
          {showOptions && (
            <div
              id="aero-ingest-options"
              className="mt-2 grid grid-cols-2 gap-2 rounded-lg border border-astra-border bg-astra-surface p-3 md:grid-cols-4"
            >
              <div>
                <label htmlFor="aero-opt-name" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  Name hint
                </label>
                <input
                  id="aero-opt-name" type="text" value={optName}
                  onChange={(e) => setOptName(e.target.value)}
                  placeholder="(HAROLD decides)"
                  className="w-full rounded-lg border border-astra-border bg-astra-bg px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-blue-500/50"
                />
              </div>
              <div>
                <label htmlFor="aero-opt-oml" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  OML WPN
                </label>
                <input
                  id="aero-opt-oml" type="text" value={optOml}
                  onChange={(e) => setOptOml(e.target.value)}
                  placeholder="WS-OML-…"
                  className="w-full rounded-lg border border-astra-border bg-astra-bg px-2.5 py-1.5 font-mono text-xs text-slate-200 outline-none focus:border-blue-500/50"
                />
              </div>
              <div>
                <label htmlFor="aero-opt-sref" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  Sref (m²)
                </label>
                <input
                  id="aero-opt-sref" type="number" step="any" value={optSref}
                  onChange={(e) => setOptSref(e.target.value)}
                  placeholder="from file"
                  className="w-full rounded-lg border border-astra-border bg-astra-bg px-2.5 py-1.5 font-mono text-xs text-slate-200 outline-none focus:border-blue-500/50"
                />
              </div>
              <div>
                <label htmlFor="aero-opt-lref" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  Lref (m)
                </label>
                <input
                  id="aero-opt-lref" type="number" step="any" value={optLref}
                  onChange={(e) => setOptLref(e.target.value)}
                  placeholder="from file"
                  className="w-full rounded-lg border border-astra-border bg-astra-bg px-2.5 py-1.5 font-mono text-xs text-slate-200 outline-none focus:border-blue-500/50"
                />
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Ingest success status ── */}
      {ingested && (
        <div
          role="status"
          className="mb-3 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-400"
        >
          <div className="flex flex-wrap items-center gap-1.5">
            Named
            <span className="font-mono font-bold tracking-wider text-emerald-300">{ingested.wpn}</span>
            by HAROLD —
            {ingested.is_new_deck ? 'new deck' : `revision ${ingested.rev_letter} of an existing deck`}
            · Mach {fmtRange(ingested.envelope.mach_min, ingested.envelope.mach_max)}
            · α {fmtRange(ingested.envelope.alpha_min_deg, ingested.envelope.alpha_max_deg, 0, '°')}
            <Link
              href={`/engineering/aero/${encodeURIComponent(ingested.deck_wpn)}`}
              className="ml-auto font-semibold text-emerald-300 underline-offset-2 hover:underline"
            >
              View deck →
            </Link>
          </div>
          {ingested.warnings.length > 0 && (
            <ul className="mt-1.5 list-inside list-disc space-y-0.5 text-amber-400">
              {ingested.warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          )}
        </div>
      )}

      {/* ── Toolbar ── */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" aria-hidden="true" />
          <label htmlFor="aero-search" className="sr-only">Search aero decks</label>
          <input
            id="aero-search"
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search decks by WPN, name, or OML WPN…"
            className="w-full rounded-lg border border-astra-border bg-astra-bg pl-8 pr-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
          />
        </div>
        <button
          type="button"
          onClick={refresh}
          aria-label="Refresh aero decks"
          className="rounded-lg border border-astra-border p-2 text-slate-400 hover:border-blue-500/30 hover:text-slate-200"
        >
          <RefreshCw className={clsx('h-3.5 w-3.5', loading && 'animate-spin')} aria-hidden="true" />
        </button>
      </div>

      {error && (
        <div role="alert" className="mb-3 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
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
            <Wind className="h-8 w-8 mx-auto mb-2 text-slate-600" aria-hidden="true" />
            No aero decks yet. Drop coefficient CSVs above to ingest one.
          </div>
        ) : (
          <table className="w-full text-xs" aria-label="Aero decks">
            <thead className="bg-astra-surface-alt text-slate-400">
              <tr>
                <th scope="col" className="px-3 py-2 text-left font-semibold">WPN</th>
                <th scope="col" className="px-3 py-2 text-left font-semibold">Name</th>
                <th scope="col" className="px-3 py-2 text-left font-semibold">OML WPN</th>
                <th scope="col" className="px-3 py-2 text-center font-semibold">Mach</th>
                <th scope="col" className="px-3 py-2 text-center font-semibold">α (deg)</th>
                <th scope="col" className="px-3 py-2 text-center font-semibold">Rev</th>
                <th scope="col" className="px-3 py-2 text-left font-semibold">Updated</th>
                <th scope="col" className="px-3 py-2"><span className="sr-only">Open</span></th>
              </tr>
            </thead>
            <tbody>
              {items.map((d) => (
                <tr
                  key={d.id}
                  className="border-t border-astra-border hover:bg-astra-surface-alt cursor-pointer"
                  onClick={() => router.push(`/engineering/aero/${encodeURIComponent(d.wpn)}`)}
                >
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <Wind className="h-3.5 w-3.5 flex-shrink-0 text-cyan-400" aria-hidden="true" />
                      <span className="font-mono font-bold tracking-wider text-slate-100">{d.wpn}</span>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-slate-300">{d.name}</td>
                  <td className="px-3 py-2 font-mono text-slate-400">{d.oml_wpn || '—'}</td>
                  <td className="px-3 py-2 text-center font-mono tabular-nums text-slate-300">
                    {fmtRange(d.mach_min, d.mach_max)}
                  </td>
                  <td className="px-3 py-2 text-center font-mono tabular-nums text-slate-300">
                    {fmtRange(d.alpha_min_deg, d.alpha_max_deg, 0)}
                  </td>
                  <td className="px-3 py-2 text-center font-mono text-slate-300">
                    {d.current_rev || '—'}
                    {d.revision_count > 1 && (
                      <span className="ml-1 text-[10px] text-slate-500">({d.revision_count})</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-slate-500">{fmtDateTime(d.updated_at)}</td>
                  <td className="px-3 py-2 text-right text-slate-500">
                    <ChevronRight className="inline h-3.5 w-3.5" aria-hidden="true" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
