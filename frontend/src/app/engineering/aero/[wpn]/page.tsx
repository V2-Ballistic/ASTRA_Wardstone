'use client';

/**
 * ASTRA — Aero Deck Detail Page (spec §6 UX)
 * ============================================
 * File: frontend/src/app/engineering/aero/[wpn]/page.tsx
 *
 * Sections:
 *   - Header (WPN, name, OML WPN, current rev)
 *   - Envelope cards (Sref, Lref, Mach / α / β ranges)
 *   - Coefficient previews via CurvePlot: CN vs α and Cm vs α at a
 *     selectable Mach breakpoint, CA vs Mach at α≈0 — sliced from the
 *     deck artifact on the β≈0 / δ≈0 plane
 *   - Revision history + add-revision upload (from-source) +
 *     active-revision switcher (role-gated)
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import {
  AlertTriangle, ChevronLeft, Loader2, Wind,
} from 'lucide-react';
import clsx from 'clsx';

import { engineeringAPI } from '@/lib/engineering-api';
import {
  type AeroDeckArtifact,
  type AeroDeckDetail,
  type AeroIngestResponse,
  fmtDateTime,
  fmtRange,
} from '@/lib/engineering-types';
import { formatApiError } from '@/lib/errors';
import { useHasRole } from '@/lib/auth';
import CurvePlot, { type CurveSeries } from '@/components/engineering/CurvePlot';
import UploadDropzone from '@/components/engineering/UploadDropzone';

function EnvelopeCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface px-4 py-3">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className="font-mono text-sm font-semibold tabular-nums text-slate-200">{value}</div>
    </div>
  );
}

function closestIndex(values: number[], target: number): number {
  let best = 0;
  for (let i = 1; i < values.length; i++) {
    if (Math.abs(values[i] - target) < Math.abs(values[best] - target)) best = i;
  }
  return best;
}

export default function AeroDeckDetailPage() {
  const params = useParams();
  const wpn = decodeURIComponent(String(params?.wpn ?? ''));
  const canWrite = useHasRole('admin', 'project_manager', 'requirements_engineer');

  const [deck, setDeck] = useState<AeroDeckDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [viewRev, setViewRev] = useState<string | null>(null);
  const [artifact, setArtifact] = useState<AeroDeckArtifact | null>(null);
  const [artifactLoading, setArtifactLoading] = useState(false);
  const [artifactError, setArtifactError] = useState('');
  const [machIdx, setMachIdx] = useState(0);

  const [settingActive, setSettingActive] = useState<string | null>(null);
  const [actionError, setActionError] = useState('');
  const [uploading, setUploading] = useState(false);
  const [ingested, setIngested] = useState<AeroIngestResponse | null>(null);

  const refresh = useCallback(() => {
    if (!wpn) return;
    setLoading(true);
    engineeringAPI.getAeroDeck(wpn)
      .then((r) => { setDeck(r.data); setError(''); })
      .catch((e) => setError(formatApiError(e, 'Failed to load aero deck')))
      .finally(() => setLoading(false));
  }, [wpn]);

  useEffect(() => { refresh(); }, [refresh]);

  // Default the viewed revision to the current one.
  useEffect(() => {
    if (viewRev === null && deck?.current_rev) setViewRev(deck.current_rev);
  }, [deck, viewRev]);

  // Fetch the deck artifact for the viewed revision.
  useEffect(() => {
    if (!wpn || !viewRev) return;
    let cancelled = false;
    setArtifactLoading(true);
    setArtifactError('');
    engineeringAPI.getAeroDeckArtifact(wpn, viewRev)
      .then((r) => {
        if (cancelled) return;
        setArtifact(r.data);
        setMachIdx(0);
      })
      .catch((e) => {
        if (!cancelled) setArtifactError(formatApiError(e, 'Failed to load deck artifact'));
      })
      .finally(() => { if (!cancelled) setArtifactLoading(false); });
    return () => { cancelled = true; };
  }, [wpn, viewRev]);

  // ── coefficient slices (β≈0, δ≈0 plane) ──
  const slices = useMemo(() => {
    if (!artifact) return null;
    const bp = artifact.breakpoints;
    if (!bp?.mach?.length || !bp?.alpha_deg?.length) return null;
    const ib = closestIndex(bp.beta_deg ?? [0], 0);
    const idl = closestIndex(bp.delta_deg ?? [0], 0);
    const mi = Math.min(machIdx, bp.mach.length - 1);
    const ia0 = closestIndex(bp.alpha_deg, 0);

    const vsAlpha = (coeff: string): CurveSeries | null => {
      const table = artifact.tables?.[coeff];
      if (!table) return null;
      const y = bp.alpha_deg.map((_, ai) => table[mi]?.[ai]?.[ib]?.[idl]);
      if (y.some((v) => typeof v !== 'number')) return null;
      return { label: coeff, x: bp.alpha_deg, y: y as number[] };
    };
    const vsMach = (coeff: string): CurveSeries | null => {
      const table = artifact.tables?.[coeff];
      if (!table) return null;
      const y = bp.mach.map((_, mj) => table[mj]?.[ia0]?.[ib]?.[idl]);
      if (y.some((v) => typeof v !== 'number')) return null;
      return { label: coeff, x: bp.mach, y: y as number[] };
    };

    return {
      mach: bp.mach,
      mi,
      alpha0: bp.alpha_deg[ia0],
      beta: (bp.beta_deg ?? [0])[ib],
      delta: (bp.delta_deg ?? [0])[idl],
      cnVsAlpha: vsAlpha('CN'),
      cmVsAlpha: vsAlpha('Cm'),
      caVsMach: vsMach('CA'),
    };
  }, [artifact, machIdx]);

  const handleSetActive = useCallback(async (rev: string) => {
    setActionError('');
    setSettingActive(rev);
    try {
      const r = await engineeringAPI.setAeroActiveRevision(wpn, rev);
      setDeck(r.data);
    } catch (e) {
      setActionError(formatApiError(e, 'Failed to set active revision'));
    } finally {
      setSettingActive(null);
    }
  }, [wpn]);

  const handleRevisionFiles = useCallback(async (files: File[]) => {
    if (files.length === 0) return;
    setActionError('');
    setIngested(null);
    setUploading(true);
    try {
      const r = await engineeringAPI.addAeroRevisionFromSource(wpn, files);
      setIngested(r.data);
      setViewRev(r.data.rev_letter);
      refresh();
    } catch (e) {
      setActionError(formatApiError(e, 'Revision source ingest failed'));
    } finally {
      setUploading(false);
    }
  }, [refresh, wpn]);

  // ── render ──
  if (loading && !deck) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-6 w-6 animate-spin text-blue-500" aria-label="Loading aero deck" />
      </div>
    );
  }

  if (error && !deck) {
    return (
      <div>
        <Link href="/engineering?tab=aero" className="mb-4 inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200">
          <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" /> Engineering / Aero
        </Link>
        <div role="alert" className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
          <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {error}
        </div>
      </div>
    );
  }

  if (!deck) return null;

  const env = artifact?.validityEnvelope;

  return (
    <div>
      <Link href="/engineering?tab=aero" className="mb-4 inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200">
        <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" /> Engineering / Aero
      </Link>

      {/* ── Header ── */}
      <div className="mb-6">
        <h1 className="flex flex-wrap items-center gap-2.5 text-2xl font-bold tracking-tight text-slate-100">
          <Wind className="h-6 w-6 text-cyan-400" aria-hidden="true" />
          <span className="font-mono tracking-wider">{deck.wpn}</span>
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          {deck.name}
          <span className="ml-2 text-xs text-slate-500">
            current rev <span className="font-mono text-slate-300">{deck.current_rev || '—'}</span>
            {deck.oml_wpn && <> · OML <span className="font-mono text-slate-300">{deck.oml_wpn}</span></>}
            {' '}· {deck.revision_count} revision{deck.revision_count === 1 ? '' : 's'}
          </span>
        </p>
      </div>

      {(error || actionError) && (
        <div role="alert" className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
          <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {error || actionError}
        </div>
      )}

      {ingested && (
        <div role="status" className="mb-4 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-400">
          New revision <span className="font-mono font-bold text-emerald-300">{ingested.wpn}</span>{' '}
          issued by HAROLD.
          {ingested.warnings.length > 0 && (
            <ul className="mt-1.5 list-inside list-disc space-y-0.5 text-amber-400">
              {ingested.warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          )}
        </div>
      )}

      {/* ── Envelope cards ── */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <EnvelopeCard label="Sref" value={artifact ? `${artifact.Sref_m2} m²` : '—'} />
        <EnvelopeCard label="Lref" value={artifact ? `${artifact.Lref_m} m` : '—'} />
        <EnvelopeCard
          label="Mach range"
          value={env ? fmtRange(env.machRange[0], env.machRange[1]) : fmtRange(deck.mach_min, deck.mach_max)}
        />
        <EnvelopeCard
          label="α range"
          value={env
            ? fmtRange(env.alphaRange_deg[0], env.alphaRange_deg[1], 0, '°')
            : fmtRange(deck.alpha_min_deg, deck.alpha_max_deg, 0, '°')}
        />
        <EnvelopeCard
          label="β range"
          value={env ? fmtRange(env.betaRange_deg[0], env.betaRange_deg[1], 0, '°') : '—'}
        />
      </div>

      {/* ── Coefficient previews ── */}
      <div className="mb-6">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-200">
            Coefficient previews — revision{' '}
            <span className="font-mono text-blue-300">{viewRev || '—'}</span>
            {slices && (
              <span className="ml-2 text-[11px] font-normal text-slate-500">
                β = {slices.beta}°, δ = {slices.delta}° slice
              </span>
            )}
          </h2>
          {slices && (
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <label htmlFor="aero-mach" className="font-semibold">Mach breakpoint:</label>
              <select
                id="aero-mach"
                value={slices.mi}
                onChange={(e) => setMachIdx(Number(e.target.value))}
                className="rounded-lg border border-astra-border bg-astra-bg px-2.5 py-1.5 font-mono text-xs text-slate-200 outline-none focus:border-blue-500/50"
              >
                {slices.mach.map((m, i) => (
                  <option key={i} value={i}>{m}</option>
                ))}
              </select>
            </div>
          )}
        </div>

        {artifactError && (
          <div role="alert" className="mb-3 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
            <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {artifactError}
          </div>
        )}

        {artifactLoading && !artifact ? (
          <div className="flex items-center justify-center rounded-xl border border-astra-border bg-astra-surface py-16">
            <Loader2 className="h-5 w-5 animate-spin text-blue-500" aria-label="Loading deck artifact" />
          </div>
        ) : slices ? (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            {slices.cnVsAlpha ? (
              <CurvePlot
                title={`CN vs α — Mach ${slices.mach[slices.mi]}`}
                series={[{ ...slices.cnVsAlpha, color: '#3B82F6' }]}
                xLabel="α (deg)" yLabel="CN"
              />
            ) : (
              <div className="flex items-center justify-center rounded-xl border border-astra-border bg-astra-surface text-xs text-slate-500">
                No CN table in this deck
              </div>
            )}
            {slices.cmVsAlpha ? (
              <CurvePlot
                title={`Cm vs α — Mach ${slices.mach[slices.mi]}`}
                series={[{ ...slices.cmVsAlpha, color: '#8B5CF6' }]}
                xLabel="α (deg)" yLabel="Cm"
              />
            ) : (
              <div className="flex items-center justify-center rounded-xl border border-astra-border bg-astra-surface text-xs text-slate-500">
                No Cm table in this deck
              </div>
            )}
            {slices.caVsMach ? (
              <CurvePlot
                title={`CA vs Mach — α = ${slices.alpha0}°`}
                series={[{ ...slices.caVsMach, color: '#10B981' }]}
                xLabel="Mach" yLabel="CA"
              />
            ) : (
              <div className="flex items-center justify-center rounded-xl border border-astra-border bg-astra-surface text-xs text-slate-500">
                No CA table in this deck
              </div>
            )}
          </div>
        ) : !artifactError ? (
          <div className="rounded-xl border border-astra-border bg-astra-surface py-12 text-center text-sm text-slate-500">
            No deck artifact to preview.
          </div>
        ) : null}
      </div>

      {/* ── Revision history ── */}
      <div className="mb-6">
        <h2 className="mb-2 text-sm font-semibold text-slate-200">Revision history</h2>
        <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
          {deck.revisions.length === 0 ? (
            <div className="py-10 text-center text-sm text-slate-500">No revisions.</div>
          ) : (
            <table className="w-full text-xs" aria-label="Aero deck revisions">
              <thead className="bg-astra-surface-alt text-slate-400">
                <tr>
                  <th scope="col" className="px-3 py-2 text-left font-semibold">Rev</th>
                  <th scope="col" className="px-3 py-2 text-left font-semibold">Sources</th>
                  <th scope="col" className="px-3 py-2 text-center font-semibold">Mach</th>
                  <th scope="col" className="px-3 py-2 text-center font-semibold">α (deg)</th>
                  <th scope="col" className="px-3 py-2 text-left font-semibold">Created</th>
                  <th scope="col" className="px-3 py-2 text-right font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody>
                {deck.revisions.map((r) => {
                  const isActive = r.rev_letter === deck.current_rev;
                  const isViewed = r.rev_letter === viewRev;
                  return (
                    <tr key={r.id} className="border-t border-astra-border">
                      <td className="px-3 py-2">
                        <span className="font-mono font-bold text-slate-100">{r.rev_letter}</span>
                        {isActive && (
                          <span className="ml-2 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
                            Active
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-slate-400">
                        {r.source_filenames.length
                          ? r.source_filenames.join(', ')
                          : '—'}
                        {r.warnings.length > 0 && (
                          <span
                            className="ml-1.5 rounded-full bg-amber-500/15 px-1.5 py-0.5 text-[9px] font-semibold text-amber-400"
                            title={r.warnings.join('\n')}
                          >
                            {r.warnings.length} warning{r.warnings.length === 1 ? '' : 's'}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-center font-mono tabular-nums text-slate-300">
                        {fmtRange(r.mach_min, r.mach_max)}
                      </td>
                      <td className="px-3 py-2 text-center font-mono tabular-nums text-slate-300">
                        {fmtRange(r.alpha_min_deg, r.alpha_max_deg, 0)}
                      </td>
                      <td className="px-3 py-2 text-slate-500">{fmtDateTime(r.created_utc)}</td>
                      <td className="px-3 py-2 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            type="button"
                            disabled={isViewed}
                            onClick={() => setViewRev(r.rev_letter)}
                            className={clsx(
                              'rounded-lg border px-2 py-1 text-[10px] font-semibold',
                              isViewed
                                ? 'border-blue-500/40 bg-blue-500/10 text-blue-300'
                                : 'border-astra-border text-slate-400 hover:text-slate-200',
                            )}
                          >
                            {isViewed ? 'Previewed' : 'Preview'}
                          </button>
                          {canWrite && !isActive && (
                            <button
                              type="button"
                              disabled={settingActive !== null}
                              onClick={() => handleSetActive(r.rev_letter)}
                              className="rounded-lg border border-astra-border px-2 py-1 text-[10px] font-semibold text-slate-400 hover:border-emerald-500/40 hover:text-emerald-300 disabled:opacity-50"
                            >
                              {settingActive === r.rev_letter
                                ? <Loader2 className="h-3 w-3 animate-spin" aria-label="Setting active" />
                                : 'Set active'}
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {canWrite && (
          <div className="mt-3">
            <UploadDropzone
              compact
              multiple
              label="Add a revision from new source files"
              sublabel="HAROLD issues the next -REV of this deck"
              accept=".csv,text/csv"
              uploading={uploading}
              uploadingLabel="Merging sources…"
              onFiles={handleRevisionFiles}
            />
          </div>
        )}
      </div>
    </div>
  );
}
