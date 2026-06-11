'use client';

/**
 * ASTRA — Motor Detail Page (spec §5 UX)
 * ========================================
 * File: frontend/src/app/engineering/motors/[wpn]/page.tsx
 *
 * Sections:
 *   - Header (WPN, name, class, tier, active rev, origin)
 *   - Spec sheet card (impulse, peak, Isp, burn time, prop mass)
 *   - d3 plots from the viewed revision's artifact: thrust / chamber
 *     pressure / propellant mass vs time, optional 3-temperature
 *     thrust overlay (GrainTempGrid_K)
 *   - Revision history (every revision row) + two-revision diff view
 *   - Add revision (CSV → :from-csv), new revision from design link,
 *     active-revision switcher — all role-gated
 *   - "Use in config" → /engineering?tab=configurations (placeholder)
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import {
  AlertTriangle, ArrowLeftRight, Boxes, ChevronLeft, Flame, Loader2,
  PencilRuler, Thermometer,
} from 'lucide-react';
import clsx from 'clsx';

import { engineeringAPI } from '@/lib/engineering-api';
import {
  type MotorArtifact,
  type MotorIngestResponse,
  type MotorResponse,
  type MotorRevisionDetail,
  type MotorSummarySheet,
  fmtDateTime,
  fmtImpulse,
  fmtKg,
  fmtSeconds,
  fmtThrust,
} from '@/lib/engineering-types';
import { formatApiError } from '@/lib/errors';
import { useHasRole } from '@/lib/auth';
import CurvePlot, { type CurveSeries } from '@/components/engineering/CurvePlot';
import UploadDropzone from '@/components/engineering/UploadDropzone';
import {
  MotorClassBadge, OriginBadge, QualityTierBadge,
} from '@/components/engineering/QualityTierBadge';

// ── helpers ──────────────────────────────────────────────────

function SpecItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className="font-mono text-sm font-semibold tabular-nums text-slate-200">{value}</div>
    </div>
  );
}

/** Flatten nested design inputs into dotted paths for the diff view. */
function flattenInputs(obj: unknown, prefix = ''): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  if (obj === null || typeof obj !== 'object' || Array.isArray(obj)) {
    out[prefix || '(value)'] = obj;
    return out;
  }
  for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
    const path = prefix ? `${prefix}.${k}` : k;
    if (v !== null && typeof v === 'object' && !Array.isArray(v)) {
      Object.assign(out, flattenInputs(v, path));
    } else {
      out[path] = v;
    }
  }
  return out;
}

function fmtVal(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—';
  return String(v);
}

const metricRows: {
  label: string;
  key: 'total_impulse_ns' | 'peak_thrust_n' | 'burn_time_s' | 'isp_s';
  fmt: (v?: number | null) => string;
}[] = [
  { label: 'Total impulse', key: 'total_impulse_ns', fmt: fmtImpulse },
  { label: 'Peak thrust', key: 'peak_thrust_n', fmt: fmtThrust },
  { label: 'Burn time', key: 'burn_time_s', fmt: fmtSeconds },
  { label: 'Isp', key: 'isp_s', fmt: (v) => (v == null ? '—' : `${v.toFixed(1)} s`) },
];

// ══════════════════════════════════════
//  Page
// ══════════════════════════════════════

export default function MotorDetailPage() {
  const params = useParams();
  const wpn = decodeURIComponent(String(params?.wpn ?? ''));
  const canWrite = useHasRole('admin', 'project_manager', 'requirements_engineer');

  const [motor, setMotor] = useState<MotorResponse | null>(null);
  const [summary, setSummary] = useState<MotorSummarySheet | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // ── plotted revision + artifact ──
  const [viewRev, setViewRev] = useState<string | null>(null);
  const [artifact, setArtifact] = useState<MotorArtifact | null>(null);
  const [artifactLoading, setArtifactLoading] = useState(false);
  const [artifactError, setArtifactError] = useState('');
  const [showTempGrid, setShowTempGrid] = useState(false);

  // ── revision diff ──
  const [diffA, setDiffA] = useState('');
  const [diffB, setDiffB] = useState('');
  const [diff, setDiff] = useState<{ a: MotorRevisionDetail; b: MotorRevisionDetail } | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffError, setDiffError] = useState('');

  // ── mutations ──
  const [settingActive, setSettingActive] = useState<string | null>(null);
  const [actionError, setActionError] = useState('');
  const [uploading, setUploading] = useState(false);
  const [ingested, setIngested] = useState<MotorIngestResponse | null>(null);

  const activeRevLetter = useMemo(() => {
    if (!motor) return null;
    if (motor.active_revision_id != null) {
      const r = motor.revisions.find((x) => x.id === motor.active_revision_id);
      if (r) return r.rev_letter;
    }
    return motor.revisions.length
      ? motor.revisions[motor.revisions.length - 1].rev_letter
      : null;
  }, [motor]);

  const refresh = useCallback(() => {
    if (!wpn) return;
    setLoading(true);
    Promise.all([
      engineeringAPI.getMotor(wpn),
      engineeringAPI.getMotorSummary(wpn),
    ])
      .then(([mRes, sRes]) => {
        setMotor(mRes.data);
        setSummary(sRes.data);
        setError('');
      })
      .catch((e) => setError(formatApiError(e, 'Failed to load motor')))
      .finally(() => setLoading(false));
  }, [wpn]);

  useEffect(() => { refresh(); }, [refresh]);

  // Default the plotted revision to the active one.
  useEffect(() => {
    if (viewRev === null && activeRevLetter) setViewRev(activeRevLetter);
  }, [activeRevLetter, viewRev]);

  // Fetch the artifact for the viewed revision.
  useEffect(() => {
    if (!wpn || !viewRev) return;
    let cancelled = false;
    setArtifactLoading(true);
    setArtifactError('');
    engineeringAPI.getMotorArtifact(wpn, viewRev)
      .then((r) => { if (!cancelled) setArtifact(r.data); })
      .catch((e) => {
        if (!cancelled) setArtifactError(formatApiError(e, 'Failed to load revision artifact'));
      })
      .finally(() => { if (!cancelled) setArtifactLoading(false); });
    return () => { cancelled = true; };
  }, [wpn, viewRev]);

  // Default the diff selectors to the two most recent revisions.
  useEffect(() => {
    if (!motor || motor.revisions.length < 2 || diffA || diffB) return;
    const revs = motor.revisions;
    setDiffA(revs[revs.length - 2].rev_letter);
    setDiffB(revs[revs.length - 1].rev_letter);
  }, [diffA, diffB, motor]);

  // Fetch diff details when both selectors are set.
  useEffect(() => {
    if (!wpn || !diffA || !diffB || diffA === diffB) {
      setDiff(null);
      return;
    }
    let cancelled = false;
    setDiffLoading(true);
    setDiffError('');
    Promise.all([
      engineeringAPI.getMotorRevision(wpn, diffA),
      engineeringAPI.getMotorRevision(wpn, diffB),
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

  // ── plot series ──
  const thrustSeries = useMemo<CurveSeries[]>(() => {
    if (!artifact) return [];
    const base: CurveSeries[] = [
      { label: 'Thrust', x: artifact.MotorTime_s, y: artifact.Thrust_N, color: '#3B82F6' },
    ];
    if (showTempGrid && artifact.Thrust_N_byTgrain?.length === 3) {
      const tempLabels = ['cold', 'nominal', 'hot'];
      const tempColors = ['#06B6D4', '#8B5CF6', '#F59E0B'];
      artifact.Thrust_N_byTgrain.forEach((row, i) => {
        base.push({
          label: `${tempLabels[i]} (${artifact.GrainTempGrid_K[i]?.toFixed(0) ?? '?'} K)`,
          x: artifact.MotorTime_s,
          y: row,
          color: tempColors[i],
          dashed: true,
        });
      });
    }
    return base;
  }, [artifact, showTempGrid]);

  const pressureSeries = useMemo(() => {
    if (!artifact) return [];
    return [{
      label: 'Pc',
      x: artifact.MotorTime_s,
      y: artifact.Pchamber_Pa.map((p) => p / 1e6),
      color: '#10B981',
    }];
  }, [artifact]);

  const massSeries = useMemo(() => {
    if (!artifact) return [];
    return [{
      label: 'Propellant mass',
      x: artifact.MotorTime_s,
      y: artifact.PropMassRem_kg,
      color: '#F59E0B',
    }];
  }, [artifact]);

  // ── mutations ──
  const handleSetActive = useCallback(async (rev: string) => {
    setActionError('');
    setSettingActive(rev);
    try {
      const r = await engineeringAPI.setMotorActiveRevision(wpn, rev);
      setMotor(r.data);
      engineeringAPI.getMotorSummary(wpn).then((s) => setSummary(s.data)).catch(() => {});
    } catch (e) {
      setActionError(formatApiError(e, 'Failed to set active revision'));
    } finally {
      setSettingActive(null);
    }
  }, [wpn]);

  const handleRevisionCsv = useCallback(async (files: File[]) => {
    const file = files[0];
    if (!file) return;
    setActionError('');
    setIngested(null);
    setUploading(true);
    try {
      const r = await engineeringAPI.addMotorRevisionFromCsv(wpn, file);
      setIngested(r.data);
      setViewRev(r.data.rev_letter);
      refresh();
    } catch (e) {
      setActionError(formatApiError(e, 'Revision CSV ingest failed'));
    } finally {
      setUploading(false);
    }
  }, [refresh, wpn]);

  // ── render ──
  if (loading && !motor) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-6 w-6 animate-spin text-blue-500" aria-label="Loading motor" />
      </div>
    );
  }

  if (error && !motor) {
    return (
      <div>
        <Link href="/engineering" className="mb-4 inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200">
          <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" /> Engineering
        </Link>
        <div role="alert" className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
          <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {error}
        </div>
      </div>
    );
  }

  if (!motor) return null;

  const bothDesign = diff
    && diff.a.origin === 'design' && diff.b.origin === 'design'
    && diff.a.design_inputs && diff.b.design_inputs;
  const inputDiffs = bothDesign
    ? (() => {
        const fa = flattenInputs(diff!.a.design_inputs);
        const fb = flattenInputs(diff!.b.design_inputs);
        const keys = Array.from(new Set([...Object.keys(fa), ...Object.keys(fb)])).sort();
        return keys
          .filter((k) => JSON.stringify(fa[k]) !== JSON.stringify(fb[k]))
          .map((k) => ({ key: k, a: fa[k], b: fb[k] }));
      })()
    : [];

  return (
    <div>
      {/* ── Breadcrumb ── */}
      <Link href="/engineering" className="mb-4 inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200">
        <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" /> Engineering / Motors
      </Link>

      {/* ── Header ── */}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex flex-wrap items-center gap-2.5 text-2xl font-bold tracking-tight text-slate-100">
            <Flame className="h-6 w-6 text-orange-400" aria-hidden="true" />
            <span className="font-mono tracking-wider">{motor.wpn}</span>
            <MotorClassBadge letter={motor.motor_class} />
            <QualityTierBadge tier={summary?.quality_tier} />
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            {motor.name}
            <span className="ml-2 text-xs text-slate-500">
              active rev <span className="font-mono text-slate-300">{activeRevLetter || '—'}</span>
              {summary?.origin && <> · origin <span className="text-slate-300">{summary.origin}</span></>}
              {' '}· {motor.revisions.length} revision{motor.revisions.length === 1 ? '' : 's'}
            </span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canWrite && (
            <Link
              href={`/engineering/motors/design?wpn=${encodeURIComponent(motor.wpn)}`}
              className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-500"
            >
              <PencilRuler className="h-3.5 w-3.5" aria-hidden="true" /> New revision from design
            </Link>
          )}
          <Link
            href="/engineering?tab=configurations"
            className="flex items-center gap-1.5 rounded-lg border border-astra-border px-3 py-2 text-xs font-semibold text-slate-300 hover:border-blue-500/30 hover:text-slate-100"
          >
            <Boxes className="h-3.5 w-3.5" aria-hidden="true" /> Use in config
          </Link>
        </div>
      </div>

      {(error || actionError) && (
        <div role="alert" className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
          <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {error || actionError}
        </div>
      )}

      {ingested && (
        <div role="status" className="mb-4 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-400">
          New revision <span className="font-mono font-bold text-emerald-300">{ingested.wpn}</span>{' '}
          issued by HAROLD — qualityTier <QualityTierBadge tier={ingested.quality_tier} />
          {ingested.warnings.length > 0 && (
            <ul className="mt-1.5 list-inside list-disc space-y-0.5 text-amber-400">
              {ingested.warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          )}
        </div>
      )}

      {/* ── Spec sheet ── */}
      {summary && (
        <div className="mb-6 grid grid-cols-2 gap-4 rounded-xl border border-astra-border bg-astra-surface p-4 sm:grid-cols-3 lg:grid-cols-6">
          <SpecItem label="Total impulse" value={fmtImpulse(summary.total_impulse_ns)} />
          <SpecItem label="Peak thrust" value={fmtThrust(summary.peak_thrust_n)} />
          <SpecItem label="Isp" value={summary.isp_s == null ? '—' : `${summary.isp_s.toFixed(1)} s`} />
          <SpecItem label="Burn time" value={fmtSeconds(summary.burn_time_s)} />
          <SpecItem label="Propellant mass" value={fmtKg(summary.prop_mass_init_kg)} />
          <SpecItem label="Class" value={summary.motor_class || '—'} />
        </div>
      )}

      {/* ── Plots ── */}
      <div className="mb-6">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-200">
            Revision <span className="font-mono text-blue-300">{viewRev || '—'}</span> curves
            {viewRev && viewRev !== activeRevLetter && (
              <span className="ml-2 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold text-amber-400">
                not the active revision
              </span>
            )}
          </h2>
          <button
            type="button"
            onClick={() => setShowTempGrid((v) => !v)}
            aria-pressed={showTempGrid}
            className={clsx(
              'flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-semibold transition',
              showTempGrid
                ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
                : 'border-astra-border text-slate-400 hover:text-slate-200',
            )}
          >
            <Thermometer className="h-3.5 w-3.5" aria-hidden="true" />
            Temperature-grid overlay
          </button>
        </div>

        {artifactError && (
          <div role="alert" className="mb-3 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
            <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {artifactError}
          </div>
        )}

        {artifactLoading && !artifact ? (
          <div className="flex items-center justify-center rounded-xl border border-astra-border bg-astra-surface py-16">
            <Loader2 className="h-5 w-5 animate-spin text-blue-500" aria-label="Loading artifact" />
          </div>
        ) : artifact ? (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <CurvePlot
              title="Thrust vs time"
              series={thrustSeries}
              xLabel="t (s)"
              yLabel="Thrust (N)"
              className="xl:col-span-2"
              height={260}
            />
            <CurvePlot
              title="Chamber pressure vs time"
              series={pressureSeries}
              xLabel="t (s)"
              yLabel="Pc (MPa)"
            />
            <CurvePlot
              title="Propellant mass vs time"
              series={massSeries}
              xLabel="t (s)"
              yLabel="mass (kg)"
            />
          </div>
        ) : !artifactError ? (
          <div className="rounded-xl border border-astra-border bg-astra-surface py-12 text-center text-sm text-slate-500">
            No revision artifact to plot.
          </div>
        ) : null}
      </div>

      {/* ── Revision history ── */}
      <div className="mb-6">
        <h2 className="mb-2 text-sm font-semibold text-slate-200">Revision history</h2>
        <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
          {motor.revisions.length === 0 ? (
            <div className="py-10 text-center text-sm text-slate-500">No revisions.</div>
          ) : (
            <table className="w-full text-xs" aria-label="Motor revisions">
              <thead className="bg-astra-surface-alt text-slate-400">
                <tr>
                  <th scope="col" className="px-3 py-2 text-left font-semibold">Rev</th>
                  <th scope="col" className="px-3 py-2 text-left font-semibold">Origin</th>
                  <th scope="col" className="px-3 py-2 text-center font-semibold">Quality</th>
                  <th scope="col" className="px-3 py-2 text-right font-semibold">Total Impulse</th>
                  <th scope="col" className="px-3 py-2 text-right font-semibold">Peak</th>
                  <th scope="col" className="px-3 py-2 text-left font-semibold">Created</th>
                  <th scope="col" className="px-3 py-2 text-right font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody>
                {motor.revisions.map((r) => {
                  const isActive = r.rev_letter === activeRevLetter;
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
                      <td className="px-3 py-2"><OriginBadge origin={r.origin} /></td>
                      <td className="px-3 py-2 text-center"><QualityTierBadge tier={r.quality_tier} /></td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums text-slate-300">
                        {fmtImpulse(r.total_impulse_ns)}
                      </td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums text-slate-300">
                        {fmtThrust(r.peak_thrust_n)}
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
                            {isViewed ? 'Plotted' : 'Plot'}
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

        {/* ── Add revision (CSV) ── */}
        {canWrite && (
          <div className="mt-3">
            <UploadDropzone
              compact
              label="Add a revision from CSV"
              sublabel="HAROLD issues the next -REV of this motor"
              accept=".csv,text/csv"
              uploading={uploading}
              uploadingLabel="Ingesting revision CSV…"
              onFiles={handleRevisionCsv}
            />
          </div>
        )}
      </div>

      {/* ── Revision diff ── */}
      {motor.revisions.length >= 2 && (
        <div className="mb-6">
          <h2 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-slate-200">
            <ArrowLeftRight className="h-4 w-4 text-slate-400" aria-hidden="true" />
            Compare revisions
          </h2>
          <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
            <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <label htmlFor="diff-a" className="font-semibold">A:</label>
              <select
                id="diff-a" value={diffA} onChange={(e) => setDiffA(e.target.value)}
                className="rounded-lg border border-astra-border bg-astra-bg px-2.5 py-1.5 font-mono text-xs text-slate-200 outline-none focus:border-blue-500/50"
              >
                {motor.revisions.map((r) => (
                  <option key={r.id} value={r.rev_letter}>{r.rev_letter} ({r.origin})</option>
                ))}
              </select>
              <label htmlFor="diff-b" className="font-semibold">B:</label>
              <select
                id="diff-b" value={diffB} onChange={(e) => setDiffB(e.target.value)}
                className="rounded-lg border border-astra-border bg-astra-bg px-2.5 py-1.5 font-mono text-xs text-slate-200 outline-none focus:border-blue-500/50"
              >
                {motor.revisions.map((r) => (
                  <option key={r.id} value={r.rev_letter}>{r.rev_letter} ({r.origin})</option>
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
                      <th scope="col" className="px-2 py-1.5 text-left font-semibold">Metric</th>
                      <th scope="col" className="px-2 py-1.5 text-right font-semibold font-mono">{diffA}</th>
                      <th scope="col" className="px-2 py-1.5 text-right font-semibold font-mono">{diffB}</th>
                      <th scope="col" className="px-2 py-1.5 text-right font-semibold">Δ (B − A)</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-b border-astra-border/50">
                      <td className="px-2 py-1.5 text-slate-400">Origin</td>
                      <td className="px-2 py-1.5 text-right"><OriginBadge origin={diff.a.origin} /></td>
                      <td className="px-2 py-1.5 text-right"><OriginBadge origin={diff.b.origin} /></td>
                      <td className="px-2 py-1.5 text-right text-slate-500">
                        {diff.a.origin === diff.b.origin ? '—' : 'changed'}
                      </td>
                    </tr>
                    <tr className="border-b border-astra-border/50">
                      <td className="px-2 py-1.5 text-slate-400">Quality tier</td>
                      <td className="px-2 py-1.5 text-right"><QualityTierBadge tier={diff.a.quality_tier} /></td>
                      <td className="px-2 py-1.5 text-right"><QualityTierBadge tier={diff.b.quality_tier} /></td>
                      <td className="px-2 py-1.5 text-right text-slate-500">
                        {diff.a.quality_tier === diff.b.quality_tier ? '—' : 'changed'}
                      </td>
                    </tr>
                    {metricRows.map(({ label, key, fmt }) => {
                      const va = diff.a[key];
                      const vb = diff.b[key];
                      const delta = va != null && vb != null ? vb - va : null;
                      return (
                        <tr key={key} className="border-b border-astra-border/50">
                          <td className="px-2 py-1.5 text-slate-400">{label}</td>
                          <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-300">{fmt(va)}</td>
                          <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-300">{fmt(vb)}</td>
                          <td className={clsx(
                            'px-2 py-1.5 text-right font-mono tabular-nums',
                            delta == null ? 'text-slate-500'
                              : delta > 0 ? 'text-emerald-400'
                              : delta < 0 ? 'text-red-400' : 'text-slate-500',
                          )}>
                            {delta == null ? '—' : `${delta > 0 ? '+' : ''}${fmt(delta)}`}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>

                {bothDesign && (
                  <div className="mt-4">
                    <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                      Design input changes
                    </h3>
                    {inputDiffs.length === 0 ? (
                      <div className="text-xs text-slate-500">Design inputs are identical.</div>
                    ) : (
                      <table className="w-full text-xs" aria-label="Design input diffs">
                        <thead className="text-slate-400">
                          <tr className="border-b border-astra-border">
                            <th scope="col" className="px-2 py-1.5 text-left font-semibold">Input</th>
                            <th scope="col" className="px-2 py-1.5 text-right font-semibold font-mono">{diffA}</th>
                            <th scope="col" className="px-2 py-1.5 text-right font-semibold font-mono">{diffB}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {inputDiffs.map(({ key, a, b }) => (
                            <tr key={key} className="border-b border-astra-border/50">
                              <td className="px-2 py-1.5 font-mono text-slate-400">{key}</td>
                              <td className="px-2 py-1.5 text-right font-mono tabular-nums text-red-300/80">{fmtVal(a)}</td>
                              <td className="px-2 py-1.5 text-right font-mono tabular-nums text-emerald-300/90">{fmtVal(b)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                )}
                {!bothDesign && (
                  <p className="mt-3 text-[11px] text-slate-500">
                    Input-level diff is only available when both revisions originate from the design solver.
                  </p>
                )}
              </>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
