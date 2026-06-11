'use client';

/**
 * ASTRA — Engineering » Motors tab (spec §5 UX)
 * ===============================================
 * File: frontend/src/components/engineering/MotorsTab.tsx
 *
 * List of HAROLD-named motors + the two prominent entry points:
 *   1. drag-drop CSV upload zone (the headline UX) → :ingestCsv —
 *      "Named <WPN> by HAROLD" success status, list refresh, link to
 *      the new motor's detail page
 *   2. "New design" → /engineering/motors/design (parametric solver)
 */

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  AlertTriangle, ChevronRight, Flame, Loader2, PencilRuler, RefreshCw,
  Search,
} from 'lucide-react';
import clsx from 'clsx';

import { engineeringAPI } from '@/lib/engineering-api';
import {
  type MotorIngestResponse,
  type MotorListItem,
  fmtDateTime,
  fmtImpulse,
} from '@/lib/engineering-types';
import { formatApiError } from '@/lib/errors';
import { useHasRole } from '@/lib/auth';
import UploadDropzone from './UploadDropzone';
import { MotorClassBadge, QualityTierBadge } from './QualityTierBadge';

export default function MotorsTab() {
  const router = useRouter();
  const canWrite = useHasRole('admin', 'project_manager', 'requirements_engineer');

  const [items, setItems] = useState<MotorListItem[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // ── CSV ingest state ──
  const [uploading, setUploading] = useState(false);
  const [ingested, setIngested] = useState<MotorIngestResponse | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    engineeringAPI.listMotors({ q: search || undefined, limit: 200 })
      .then((r) => { setItems(r.data); setError(''); })
      .catch((e) => setError(formatApiError(e, 'Failed to load motors')))
      .finally(() => setLoading(false));
  }, [search]);

  useEffect(() => {
    const handle = setTimeout(refresh, 250);
    return () => clearTimeout(handle);
  }, [refresh]);

  const onCsvFiles = useCallback(async (files: File[]) => {
    const file = files[0];
    if (!file) return;
    setError('');
    setIngested(null);
    setUploading(true);
    try {
      const r = await engineeringAPI.ingestMotorCsv(file);
      setIngested(r.data);
      refresh();
    } catch (e) {
      // HAROLD outages arrive as 503 with a string detail — surface it.
      setError(formatApiError(e, 'Motor CSV ingest failed'));
    } finally {
      setUploading(false);
    }
  }, [refresh]);

  return (
    <div>
      {/* ── Headline UX: drag-drop CSV ingest (write roles only) ── */}
      {canWrite && (
        <div className="mb-4">
          <UploadDropzone
            label="Drop a motor CSV here"
            sublabel="HAROLD names it automatically — thrust curve in, WPN out"
            accept=".csv,text/csv"
            uploading={uploading}
            uploadingLabel="Ingesting CSV — HAROLD is naming it…"
            onFiles={onCsvFiles}
          />
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
            <span className="font-mono font-bold tracking-wider text-emerald-300">
              {ingested.wpn}
            </span>
            by HAROLD — qualityTier
            <QualityTierBadge tier={ingested.quality_tier} />
            <Link
              href={`/engineering/motors/${encodeURIComponent(ingested.motor.wpn)}`}
              className="ml-auto font-semibold text-emerald-300 underline-offset-2 hover:underline"
            >
              View motor →
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
          <label htmlFor="motors-search" className="sr-only">Search motors</label>
          <input
            id="motors-search"
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search motors by WPN or name…"
            className="w-full rounded-lg border border-astra-border bg-astra-bg pl-8 pr-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
          />
        </div>
        <button
          type="button"
          onClick={refresh}
          aria-label="Refresh motors"
          className="rounded-lg border border-astra-border p-2 text-slate-400 hover:border-blue-500/30 hover:text-slate-200"
        >
          <RefreshCw className={clsx('h-3.5 w-3.5', loading && 'animate-spin')} aria-hidden="true" />
        </button>
        {canWrite && (
          <button
            type="button"
            onClick={() => router.push('/engineering/motors/design')}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-500"
          >
            <PencilRuler className="h-3.5 w-3.5" aria-hidden="true" /> New design
          </button>
        )}
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
            <Flame className="h-8 w-8 mx-auto mb-2 text-slate-600" aria-hidden="true" />
            No motors yet. Drop a thrust-curve CSV above, or start a{' '}
            <strong className="text-slate-300">New design</strong>.
          </div>
        ) : (
          <table className="w-full text-xs" aria-label="Motors">
            <thead className="bg-astra-surface-alt text-slate-400">
              <tr>
                <th scope="col" className="px-3 py-2 text-left font-semibold">WPN</th>
                <th scope="col" className="px-3 py-2 text-left font-semibold">Name</th>
                <th scope="col" className="px-3 py-2 text-center font-semibold">Class</th>
                <th scope="col" className="px-3 py-2 text-right font-semibold">Total Impulse</th>
                <th scope="col" className="px-3 py-2 text-center font-semibold">Quality</th>
                <th scope="col" className="px-3 py-2 text-center font-semibold">Rev</th>
                <th scope="col" className="px-3 py-2 text-left font-semibold">Updated</th>
                <th scope="col" className="px-3 py-2"><span className="sr-only">Open</span></th>
              </tr>
            </thead>
            <tbody>
              {items.map((m) => (
                <tr
                  key={m.id}
                  className="border-t border-astra-border hover:bg-astra-surface-alt cursor-pointer"
                  onClick={() => router.push(`/engineering/motors/${encodeURIComponent(m.wpn)}`)}
                >
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <Flame className="h-3.5 w-3.5 flex-shrink-0 text-orange-400" aria-hidden="true" />
                      <span className="font-mono font-bold tracking-wider text-slate-100">{m.wpn}</span>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-slate-300">{m.name}</td>
                  <td className="px-3 py-2 text-center"><MotorClassBadge letter={m.motor_class} /></td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums text-slate-300">
                    {fmtImpulse(m.total_impulse_ns)}
                  </td>
                  <td className="px-3 py-2 text-center"><QualityTierBadge tier={m.quality_tier} /></td>
                  <td className="px-3 py-2 text-center font-mono text-slate-300">
                    {m.current_rev_letter || '—'}
                  </td>
                  <td className="px-3 py-2 text-slate-500">{fmtDateTime(m.updated_at)}</td>
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
