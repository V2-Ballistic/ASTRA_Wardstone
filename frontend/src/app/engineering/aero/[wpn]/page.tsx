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
 *   - Validity-envelope heatmap (Mach × α coverage from the REAL deck
 *     breakpoints) — EnvelopeHeatmap
 *   - Revision history + two-revision diff (envelope / Sref / Lref /
 *     breakpoint-count deltas, table-presence changes) + per-revision
 *     source download + add-revision upload (from-source) +
 *     active-revision switcher (role-gated)
 *   - "Use in config" → configuration builder with this deck prebound
 *     (?aero=<wpn>&rev=<rev>)
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import {
  AlertTriangle, ArrowLeftRight, Boxes, ChevronLeft, Download, Loader2,
  Wind,
} from 'lucide-react';
import clsx from 'clsx';

import { engineeringAPI } from '@/lib/engineering-api';
import {
  type AeroDeckArtifact,
  type AeroDeckDetail,
  type AeroDeckRevisionDetail,
  type AeroIngestResponse,
  fmtDateTime,
  fmtNum,
  fmtRange,
  fmtVec3,
} from '@/lib/engineering-types';
import { formatApiError } from '@/lib/errors';
import { useHasRole } from '@/lib/auth';
import CurvePlot, { type CurveSeries } from '@/components/engineering/CurvePlot';
import EnvelopeHeatmap from '@/components/engineering/EnvelopeHeatmap';
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

// ── two-revision diff rows ───────────────────────────────────

interface AeroDiffRow {
  label: string;
  a?: number | null;
  b?: number | null;
  digits?: number;
}

/** Scalar rows of the revision diff: envelope, Sref/Lref, breakpoint
 *  counts. Table-presence changes render separately. */
function buildAeroDiffRows(
  a: AeroDeckRevisionDetail,
  b: AeroDeckRevisionDetail,
): AeroDiffRow[] {
  const bpa = a.deck?.breakpoints;
  const bpb = b.deck?.breakpoints;
  return [
    { label: 'Mach min', a: a.mach_min, b: b.mach_min, digits: 2 },
    { label: 'Mach max', a: a.mach_max, b: b.mach_max, digits: 2 },
    { label: 'α min (deg)', a: a.alpha_min_deg, b: b.alpha_min_deg, digits: 1 },
    { label: 'α max (deg)', a: a.alpha_max_deg, b: b.alpha_max_deg, digits: 1 },
    { label: 'Sref (m²)', a: a.sref_m2 ?? a.deck?.Sref_m2, b: b.sref_m2 ?? b.deck?.Sref_m2, digits: 4 },
    { label: 'Lref (m)', a: a.lref_m ?? a.deck?.Lref_m, b: b.lref_m ?? b.deck?.Lref_m, digits: 4 },
    { label: 'Mach breakpoints', a: bpa?.mach?.length, b: bpb?.mach?.length, digits: 0 },
    { label: 'α breakpoints', a: bpa?.alpha_deg?.length, b: bpb?.alpha_deg?.length, digits: 0 },
    { label: 'β breakpoints', a: bpa?.beta_deg?.length, b: bpb?.beta_deg?.length, digits: 0 },
    { label: 'δ breakpoints', a: bpa?.delta_deg?.length, b: bpb?.delta_deg?.length, digits: 0 },
  ];
}

/** Coefficient tables present in only one of the two revisions. */
function diffTablePresence(
  a: AeroDeckRevisionDetail,
  b: AeroDeckRevisionDetail,
): { added: string[]; removed: string[]; kept: string[] } {
  const ka = new Set(Object.keys(a.deck?.tables ?? {}));
  const kb = new Set(Object.keys(b.deck?.tables ?? {}));
  return {
    added: [...kb].filter((k) => !ka.has(k)).sort(),
    removed: [...ka].filter((k) => !kb.has(k)).sort(),
    kept: [...ka].filter((k) => kb.has(k)).sort(),
  };
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
  const [downloadingSource, setDownloadingSource] = useState<string | null>(null);

  // ── revision diff ──
  const [diffA, setDiffA] = useState('');
  const [diffB, setDiffB] = useState('');
  const [diff, setDiff] = useState<{ a: AeroDeckRevisionDetail; b: AeroDeckRevisionDetail } | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffError, setDiffError] = useState('');

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

  // Default the diff selectors to the two most recent revisions.
  useEffect(() => {
    if (!deck || deck.revisions.length < 2 || diffA || diffB) return;
    const revs = deck.revisions;
    setDiffA(revs[revs.length - 2].rev_letter);
    setDiffB(revs[revs.length - 1].rev_letter);
  }, [deck, diffA, diffB]);

  // Fetch both revision details (incl. deck artifacts) for the diff.
  useEffect(() => {
    if (!wpn || !diffA || !diffB || diffA === diffB) {
      setDiff(null);
      return;
    }
    let cancelled = false;
    setDiffLoading(true);
    setDiffError('');
    Promise.all([
      engineeringAPI.getAeroDeckRevision(wpn, diffA),
      engineeringAPI.getAeroDeckRevision(wpn, diffB),
    ])
      .then(([aRes, bRes]) => {
        if (!cancelled) setDiff({ a: aRes.data, b: bRes.data });
      })
      .catch((e) => {
        if (!cancelled) setDiffError(formatApiError(e, 'Failed to load revisions for diff'));
      })
      .finally(() => { if (!cancelled) setDiffLoading(false); });
    return () => { cancelled = true; };
  }, [wpn, diffA, diffB]);

  // ── stored source download (CSV or zip) ──
  const handleDownloadSource = useCallback(async (rev: string) => {
    setActionError('');
    setDownloadingSource(rev);
    try {
      await engineeringAPI.downloadAeroRevisionSource(wpn, rev);
    } catch (e) {
      setActionError(formatApiError(e, `Failed to download the source files of revision ${rev}`));
    } finally {
      setDownloadingSource(null);
    }
  }, [wpn]);

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
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
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
        <Link
          href={`/engineering/configurations/new?aero=${encodeURIComponent(deck.wpn)}${
            (viewRev || deck.current_rev)
              ? `&rev=${encodeURIComponent(viewRev || deck.current_rev || '')}`
              : ''
          }`}
          className="flex items-center gap-1.5 rounded-lg border border-astra-border px-3 py-2 text-xs font-semibold text-slate-300 hover:border-blue-500/30 hover:text-slate-100"
        >
          <Boxes className="h-3.5 w-3.5" aria-hidden="true" /> Use in config
        </Link>
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
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <EnvelopeCard label="Sref" value={artifact ? `${artifact.Sref_m2} m²` : '—'} />
        <EnvelopeCard label="Lref" value={artifact ? `${artifact.Lref_m} m` : '—'} />
        <EnvelopeCard
          label="Ref point (m, B)"
          value={artifact ? fmtVec3(artifact.refPoint_m_B, 3) : '—'}
        />
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

      {/* ── Validity-envelope heatmap ── */}
      {artifact && (
        <div className="mb-6">
          <EnvelopeHeatmap artifact={artifact} />
        </div>
      )}

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
                          <button
                            type="button"
                            disabled={downloadingSource !== null}
                            onClick={() => handleDownloadSource(r.rev_letter)}
                            title="Download the stored source files of this revision (CSV or zip)"
                            className="flex items-center gap-1 rounded-lg border border-astra-border px-2 py-1 text-[10px] font-semibold text-slate-400 hover:border-blue-500/40 hover:text-blue-300 disabled:opacity-50"
                          >
                            {downloadingSource === r.rev_letter
                              ? <Loader2 className="h-3 w-3 animate-spin" aria-label="Downloading source" />
                              : <><Download className="h-3 w-3" aria-hidden="true" /> Source</>}
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

      {/* ── Revision diff ── */}
      {deck.revisions.length >= 2 && (
        <div className="mb-6">
          <h2 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-slate-200">
            <ArrowLeftRight className="h-4 w-4 text-slate-400" aria-hidden="true" />
            Compare revisions
          </h2>
          <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
            <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <label htmlFor="aero-diff-a" className="font-semibold">A:</label>
              <select
                id="aero-diff-a" value={diffA} onChange={(e) => setDiffA(e.target.value)}
                className="rounded-lg border border-astra-border bg-astra-bg px-2.5 py-1.5 font-mono text-xs text-slate-200 outline-none focus:border-blue-500/50"
              >
                {deck.revisions.map((r) => (
                  <option key={r.id} value={r.rev_letter}>{r.rev_letter}</option>
                ))}
              </select>
              <label htmlFor="aero-diff-b" className="font-semibold">B:</label>
              <select
                id="aero-diff-b" value={diffB} onChange={(e) => setDiffB(e.target.value)}
                className="rounded-lg border border-astra-border bg-astra-bg px-2.5 py-1.5 font-mono text-xs text-slate-200 outline-none focus:border-blue-500/50"
              >
                {deck.revisions.map((r) => (
                  <option key={r.id} value={r.rev_letter}>{r.rev_letter}</option>
                ))}
              </select>
              {diffLoading && <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" aria-label="Loading diff" />}
            </div>

            {diffError && (
              <div role="alert" className="mb-3 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
                <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {diffError}
              </div>
            )}

            {diffA === diffB ? (
              <div className="text-xs text-slate-500">Pick two different revisions to compare.</div>
            ) : diff ? (
              <>
                <table className="w-full text-xs" aria-label={`Diff of revisions ${diffA} and ${diffB}`}>
                  <thead className="text-slate-400">
                    <tr className="border-b border-astra-border">
                      <th scope="col" className="px-2 py-1.5 text-left font-semibold">Property</th>
                      <th scope="col" className="px-2 py-1.5 text-right font-semibold font-mono">{diffA}</th>
                      <th scope="col" className="px-2 py-1.5 text-right font-semibold font-mono">{diffB}</th>
                      <th scope="col" className="px-2 py-1.5 text-right font-semibold">Δ (B − A)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {buildAeroDiffRows(diff.a, diff.b).map(({ label, a, b, digits = 2 }) => {
                      const delta = a != null && b != null ? b - a : null;
                      const show = (v?: number | null) =>
                        (v == null ? '—' : digits === 0 ? String(v) : fmtNum(v, digits));
                      return (
                        <tr key={label} className="border-b border-astra-border/50">
                          <td className="px-2 py-1.5 text-slate-400">{label}</td>
                          <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-300">{show(a)}</td>
                          <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-300">{show(b)}</td>
                          <td className={clsx(
                            'px-2 py-1.5 text-right font-mono tabular-nums',
                            delta == null || delta === 0 ? 'text-slate-500'
                              : delta > 0 ? 'text-emerald-400' : 'text-red-400',
                          )}>
                            {delta == null ? '—'
                              : delta === 0 ? '—'
                              : `${delta > 0 ? '+' : ''}${digits === 0 ? delta : fmtNum(delta, digits)}`}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>

                {(() => {
                  const presence = diffTablePresence(diff.a, diff.b);
                  return (
                    <div className="mt-4">
                      <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                        Coefficient table presence
                      </h3>
                      {presence.added.length === 0 && presence.removed.length === 0 ? (
                        <div className="text-xs text-slate-500">
                          Same table set in both revisions
                          {presence.kept.length > 0 && (
                            <span className="ml-1 font-mono text-slate-400">
                              ({presence.kept.join(', ')})
                            </span>
                          )}.
                        </div>
                      ) : (
                        <div className="flex flex-wrap items-center gap-1.5 text-xs">
                          {presence.added.map((t) => (
                            <span key={`add-${t}`} className="rounded-full bg-emerald-500/15 px-2 py-0.5 font-mono text-[10px] font-semibold text-emerald-400">
                              + {t}
                            </span>
                          ))}
                          {presence.removed.map((t) => (
                            <span key={`rm-${t}`} className="rounded-full bg-red-500/15 px-2 py-0.5 font-mono text-[10px] font-semibold text-red-400">
                              − {t}
                            </span>
                          ))}
                          {presence.kept.length > 0 && (
                            <span className="text-[10px] text-slate-500">
                              unchanged: <span className="font-mono">{presence.kept.join(', ')}</span>
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })()}
              </>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
