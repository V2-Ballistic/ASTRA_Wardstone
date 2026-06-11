'use client';

/**
 * ASTRA — Configuration Detail Page (spec §8/§9 UX)
 * ===================================================
 * File: frontend/src/app/engineering/configurations/[wpn]/page.tsx
 *
 * Sections:
 *   - Header (CFG WPN, name, active-revision selector — role-gated)
 *   - The flight card: resolved mass-properties roll-up (total mass,
 *     CG vector, 3×3 inertia matrix, method, frame ICD stamp) +
 *     component BOM table + aero binding card + stage map table +
 *     validation warnings panel
 *   - Revision history + two-revision structured diff (added /
 *     removed / changed components, aero / stage / roll-up deltas)
 *   - §9 CITADEL bundle export (role-gated) + export history with
 *     manifest viewer and zip download
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  AlertTriangle, ArrowLeftRight, Boxes, ChevronDown, ChevronLeft,
  ChevronRight, Download, FileJson, Flame, Loader2, Package2, Plus,
  Wind,
} from 'lucide-react';
import clsx from 'clsx';

import { engineeringAPI } from '@/lib/engineering-api';
import { catalogAPI } from '@/lib/catalog-api';
import {
  type BundleExportResponse,
  type BundleExportSummary,
  type ConfigDetail,
  type ConfigDiff,
  type ConfigRevisionDetail,
  type ConfigStageIn,
  fmtDateTime,
  fmtKg,
  fmtNum,
  fmtVec3,
} from '@/lib/engineering-types';
import { formatApiError } from '@/lib/errors';
import { useHasRole } from '@/lib/auth';
import { ConfigRoleBadge } from '@/components/engineering/QualityTierBadge';

// ══════════════════════════════════════
//  Small presentational helpers
// ══════════════════════════════════════

function RollupItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className="font-mono text-sm font-semibold tabular-nums text-slate-200">{value}</div>
    </div>
  );
}

/** 3×3 inertia tensor as a small mono table. */
function InertiaMatrix({ m }: { m?: number[][] | null }) {
  if (!m || m.length !== 3) return <span className="text-slate-600">—</span>;
  return (
    <table className="font-mono text-[11px] tabular-nums text-slate-300" aria-label="Inertia tensor (kg·m², body frame)">
      <tbody>
        {m.map((row, i) => (
          <tr key={i}>
            {row.slice(0, 3).map((v, j) => (
              <td key={j} className="px-1.5 py-0.5 text-right">{fmtNum(v)}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function StageAxis({ stage }: { stage: ConfigStageIn }) {
  return <>{fmtVec3(stage.thrustAxis_B, 2)}</>;
}

const hash8 = (h: string) => h.slice(0, 8);

// ══════════════════════════════════════
//  Page
// ══════════════════════════════════════

export default function ConfigurationDetailPage() {
  const params = useParams();
  const router = useRouter();
  const wpn = decodeURIComponent(String(params?.wpn ?? ''));
  const canWrite = useHasRole('admin', 'project_manager', 'requirements_engineer');

  const [config, setConfig] = useState<ConfigDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // ── viewed revision (the flight card) ──
  const [viewRev, setViewRev] = useState<string | null>(null);
  const [revision, setRevision] = useState<ConfigRevisionDetail | null>(null);
  const [revLoading, setRevLoading] = useState(false);
  const [revError, setRevError] = useState('');

  // ── component WPN → catalog part id (best-effort, for links).
  //    null = lookup attempted, no catalog match (render plain mono). ──
  const [partIds, setPartIds] = useState<Record<string, number | null>>({});

  // ── mutations ──
  const [settingActive, setSettingActive] = useState(false);
  const [actionError, setActionError] = useState('');

  // ── diff ──
  const [diffA, setDiffA] = useState('');
  const [diffB, setDiffB] = useState('');
  const [diff, setDiff] = useState<ConfigDiff | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffError, setDiffError] = useState('');

  // ── §9 bundles ──
  const [bundles, setBundles] = useState<BundleExportSummary[]>([]);
  const [bundlesLoading, setBundlesLoading] = useState(false);
  const [bundlesError, setBundlesError] = useState('');
  const [exporting, setExporting] = useState(false);
  const [exported, setExported] = useState<BundleExportResponse | null>(null);
  const [exportError, setExportError] = useState('');
  const [openManifest, setOpenManifest] = useState<string | null>(null);
  const [manifests, setManifests] = useState<Record<string, unknown>>({});
  const [manifestLoading, setManifestLoading] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);

  const refresh = useCallback(() => {
    if (!wpn) return;
    setLoading(true);
    engineeringAPI.getConfig(wpn)
      .then((r) => { setConfig(r.data); setError(''); })
      .catch((e) => setError(formatApiError(e, 'Failed to load configuration')))
      .finally(() => setLoading(false));
  }, [wpn]);

  useEffect(() => { refresh(); }, [refresh]);

  // Default the viewed revision to the current/active one.
  useEffect(() => {
    if (viewRev === null && config?.current_rev) setViewRev(config.current_rev);
  }, [config, viewRev]);

  // Fetch the full flight card for the viewed revision.
  useEffect(() => {
    if (!wpn || !viewRev) return;
    let cancelled = false;
    setRevLoading(true);
    setRevError('');
    setExported(null);
    setExportError('');
    engineeringAPI.getConfigRevision(wpn, viewRev)
      .then((r) => { if (!cancelled) setRevision(r.data); })
      .catch((e) => {
        if (!cancelled) setRevError(formatApiError(e, 'Failed to load revision'));
      })
      .finally(() => { if (!cancelled) setRevLoading(false); });
    return () => { cancelled = true; };
  }, [wpn, viewRev]);

  // Best-effort: resolve component WPNs to catalog part ids so the
  // BOM table can deep-link into /catalog/parts/[id].
  useEffect(() => {
    if (!revision) return;
    const unresolved = Array.from(
      new Set(revision.components.map((c) => c.wpn)),
    ).filter((w) => w && partIds[w] === undefined);
    if (unresolved.length === 0) return;
    let cancelled = false;
    Promise.all(
      unresolved.map((w) =>
        catalogAPI.listParts({ q: w, limit: 5 })
          .then((r) => {
            const hit = r.data.find((p) => p.internal_part_number === w);
            return [w, hit?.id ?? null] as const;
          })
          .catch(() => [w, null] as const)),
    ).then((pairs) => {
      if (cancelled) return;
      setPartIds((prev) => {
        const next = { ...prev };
        for (const [w, id] of pairs) next[w] = id;
        return next;
      });
    });
    return () => { cancelled = true; };
  }, [partIds, revision]);

  // Default diff selectors to the two most recent revisions.
  useEffect(() => {
    if (!config || config.revisions.length < 2 || diffA || diffB) return;
    const revs = config.revisions;
    setDiffA(revs[revs.length - 2].rev_letter);
    setDiffB(revs[revs.length - 1].rev_letter);
  }, [config, diffA, diffB]);

  // Fetch the structured diff.
  useEffect(() => {
    if (!wpn || !diffA || !diffB || diffA === diffB) {
      setDiff(null);
      return;
    }
    let cancelled = false;
    setDiffLoading(true);
    setDiffError('');
    engineeringAPI.diffConfigRevisions(wpn, diffA, diffB)
      .then((r) => { if (!cancelled) setDiff(r.data); })
      .catch((e) => {
        if (!cancelled) setDiffError(formatApiError(e, 'Failed to load revision diff'));
      })
      .finally(() => { if (!cancelled) setDiffLoading(false); });
    return () => { cancelled = true; };
  }, [wpn, diffA, diffB]);

  // Bundle export history for the viewed revision.
  const refreshBundles = useCallback(() => {
    if (!wpn || !viewRev) return;
    setBundlesLoading(true);
    setBundlesError('');
    engineeringAPI.listConfigBundles(wpn, viewRev)
      .then((r) => setBundles(r.data))
      .catch((e) => setBundlesError(formatApiError(e, 'Failed to load bundle exports')))
      .finally(() => setBundlesLoading(false));
  }, [viewRev, wpn]);

  useEffect(() => {
    setBundles([]);
    setOpenManifest(null);
    refreshBundles();
  }, [refreshBundles]);

  // ── mutations ──
  const handleSetActive = useCallback(async (rev: string) => {
    setActionError('');
    setSettingActive(true);
    try {
      const r = await engineeringAPI.setConfigActiveRevision(wpn, rev);
      setConfig(r.data);
      setViewRev(rev);
    } catch (e) {
      setActionError(formatApiError(e, 'Failed to set active revision'));
    } finally {
      setSettingActive(false);
    }
  }, [wpn]);

  const handleExport = useCallback(async () => {
    if (!viewRev) return;
    setExportError('');
    setExported(null);
    setExporting(true);
    try {
      const r = await engineeringAPI.exportConfigBundle(wpn, viewRev);
      setExported(r.data);
      refreshBundles();
    } catch (e) {
      setExportError(formatApiError(e, 'Bundle export failed'));
    } finally {
      setExporting(false);
    }
  }, [refreshBundles, viewRev, wpn]);

  const handleManifest = useCallback(async (b: BundleExportSummary) => {
    if (openManifest === b.bundle_hash) {
      setOpenManifest(null);
      return;
    }
    setOpenManifest(b.bundle_hash);
    if (manifests[b.bundle_hash] !== undefined) return;
    setManifestLoading(b.bundle_hash);
    try {
      const r = await engineeringAPI.getConfigBundleManifest(wpn, b.rev_letter, b.bundle_hash);
      setManifests((prev) => ({ ...prev, [b.bundle_hash]: r.data }));
    } catch (e) {
      setBundlesError(formatApiError(e, 'Failed to load bundle manifest'));
    } finally {
      setManifestLoading(null);
    }
  }, [manifests, openManifest, wpn]);

  const handleDownload = useCallback(async (b: BundleExportSummary) => {
    setDownloading(b.bundle_hash);
    setBundlesError('');
    try {
      await engineeringAPI.downloadConfigBundle(
        wpn, b.rev_letter, b.bundle_hash, b.bundle_dirname,
      );
    } catch (e) {
      setBundlesError(formatApiError(e, 'Bundle download failed'));
    } finally {
      setDownloading(null);
    }
  }, [wpn]);

  const showMassColumn = useMemo(
    () => (revision?.components ?? []).some((c) => c.mass_kg != null),
    [revision],
  );

  // ── render ──
  if (loading && !config) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-6 w-6 animate-spin text-blue-500" aria-label="Loading configuration" />
      </div>
    );
  }

  if (error && !config) {
    return (
      <div>
        <Link href="/engineering?tab=configurations" className="mb-4 inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200">
          <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" /> Engineering / Configurations
        </Link>
        <div role="alert" className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
          <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {error}
        </div>
      </div>
    );
  }

  if (!config) return null;

  const warnings = revision?.validation?.warnings ?? [];

  return (
    <div>
      {/* ── Breadcrumb ── */}
      <Link href="/engineering?tab=configurations" className="mb-4 inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200">
        <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" /> Engineering / Configurations
      </Link>

      {/* ── Header ── */}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex flex-wrap items-center gap-2.5 text-2xl font-bold tracking-tight text-slate-100">
            <Boxes className="h-6 w-6 text-blue-400" aria-hidden="true" />
            <span className="font-mono tracking-wider">{config.wpn}</span>
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            {config.name}
            <span className="ml-2 text-xs text-slate-500">
              current rev <span className="font-mono text-slate-300">{config.current_rev || '—'}</span>
              {' '}· {config.revision_count} revision{config.revision_count === 1 ? '' : 's'}
              {config.astra_baseline_id != null && (
                <> · baseline <span className="font-mono text-slate-300">#{config.astra_baseline_id}</span></>
              )}
            </span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canWrite && config.revisions.length > 0 && (
            <div className="flex items-center gap-1.5 text-xs text-slate-400">
              <label htmlFor="active-rev" className="font-semibold">Active rev:</label>
              <select
                id="active-rev"
                value={config.current_rev ?? ''}
                disabled={settingActive}
                onChange={(e) => handleSetActive(e.target.value)}
                className="rounded-lg border border-astra-border bg-astra-bg px-2.5 py-1.5 font-mono text-xs text-slate-200 outline-none focus:border-blue-500/50 disabled:opacity-50"
              >
                {config.revisions.map((r) => (
                  <option key={r.id} value={r.rev_letter}>{r.rev_letter}</option>
                ))}
              </select>
              {settingActive && <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" aria-label="Setting active revision" />}
            </div>
          )}
          {canWrite && viewRev && (
            <Link
              href={`/engineering/configurations/new?from=${encodeURIComponent(config.wpn)}&rev=${encodeURIComponent(viewRev)}`}
              className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-500"
            >
              <Plus className="h-3.5 w-3.5" aria-hidden="true" /> New revision
            </Link>
          )}
        </div>
      </div>

      {(error || actionError) && (
        <div role="alert" className="mb-4 flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
          <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {error || actionError}
        </div>
      )}

      {/* ══ The flight card — viewed revision ══ */}
      <div className="mb-6">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-200">
            Flight card — revision{' '}
            <span className="font-mono text-blue-300">{viewRev || '—'}</span>
            {viewRev && viewRev !== config.current_rev && (
              <span className="ml-2 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold text-amber-400">
                not the active revision
              </span>
            )}
          </h2>
          {revision && (
            <span className="font-mono text-[11px] text-slate-500">{revision.wpn}</span>
          )}
        </div>

        {revError && (
          <div role="alert" className="mb-3 flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
            <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {revError}
          </div>
        )}

        {revLoading && !revision ? (
          <div className="flex items-center justify-center rounded-xl border border-astra-border bg-astra-surface py-16">
            <Loader2 className="h-5 w-5 animate-spin text-blue-500" aria-label="Loading flight card" />
          </div>
        ) : revision ? (
          <>
            {/* ── Validation warnings (amber) ── */}
            {warnings.length > 0 && (
              <div role="status" className="mb-3 rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-400">
                <div className="mb-1 flex items-center gap-1.5 font-semibold">
                  <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
                  {warnings.length} validation warning{warnings.length === 1 ? '' : 's'}
                </div>
                <ul className="list-inside list-disc space-y-0.5">
                  {warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              </div>
            )}

            {/* ── Roll-up card ── */}
            <div className="mb-4 rounded-xl border border-astra-border bg-astra-surface p-4">
              <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Mass-properties roll-up
              </h3>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
                <RollupItem label="Total mass" value={fmtKg(revision.rollup.totalMass_kg)} />
                <RollupItem label="CG (m, body)" value={fmtVec3(revision.rollup.cg_m_B)} />
                <div className="col-span-2">
                  <div className="text-[10px] uppercase tracking-wider text-slate-500">Inertia (kg·m², body)</div>
                  <InertiaMatrix m={revision.rollup.inertia_kgm2_B} />
                </div>
                <RollupItem label="Reference point" value={fmtVec3(revision.rollup.referencePoint_m_B, 1)} />
                <div>
                  <RollupItem label="Method" value={revision.rollup.method || '—'} />
                  <div className="mt-2 text-[10px] uppercase tracking-wider text-slate-500">Frame ICD</div>
                  <div className="font-mono text-sm font-semibold tabular-nums text-slate-200">
                    #{revision.frame_icd_id} rev {revision.frame_icd_rev}
                  </div>
                </div>
              </div>
              {(revision.description || revision.top_assembly_wpn) && (
                <p className="mt-3 border-t border-astra-border pt-2 text-xs text-slate-500">
                  {revision.description}
                  {revision.top_assembly_wpn && (
                    <span className="ml-2">
                      top assembly{' '}
                      <span className="font-mono text-slate-300">{revision.top_assembly_wpn}</span>
                    </span>
                  )}
                </p>
              )}
            </div>

            {/* ── Components (BOM) ── */}
            <div className="mb-4 overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
              <div className="border-b border-astra-border bg-astra-surface-alt px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Components ({revision.components.length})
              </div>
              {revision.components.length === 0 ? (
                <div className="py-8 text-center text-sm text-slate-500">No components.</div>
              ) : (
                <table className="w-full text-xs" aria-label="Configuration components">
                  <thead className="bg-astra-surface-alt text-slate-400">
                    <tr>
                      <th scope="col" className="px-3 py-2 text-left font-semibold">Role</th>
                      <th scope="col" className="px-3 py-2 text-left font-semibold">WPN</th>
                      <th scope="col" className="px-3 py-2 text-center font-semibold">Rev</th>
                      <th scope="col" className="px-3 py-2 text-left font-semibold">Name</th>
                      {showMassColumn && (
                        <th scope="col" className="px-3 py-2 text-right font-semibold">Mass</th>
                      )}
                      <th scope="col" className="px-3 py-2 text-left font-semibold">Placement</th>
                      <th scope="col" className="px-3 py-2 text-left font-semibold">Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {revision.components.map((c, i) => {
                      const partId = partIds[c.wpn];
                      return (
                        <tr key={`${c.wpn}-${i}`} className="border-t border-astra-border">
                          <td className="px-3 py-2"><ConfigRoleBadge role={c.role} /></td>
                          <td className="px-3 py-2">
                            {partId != null ? (
                              <Link
                                href={`/catalog/parts/${partId}`}
                                className="font-mono font-bold tracking-wider text-blue-300 underline-offset-2 hover:underline"
                              >
                                {c.wpn}
                              </Link>
                            ) : (
                              <span className="font-mono font-bold tracking-wider text-slate-100">{c.wpn}</span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-center font-mono text-slate-300">{c.rev || '—'}</td>
                          <td className="px-3 py-2 text-slate-300">{c.name || '—'}</td>
                          {showMassColumn && (
                            <td className="px-3 py-2 text-right font-mono tabular-nums text-slate-300">
                              {fmtKg(c.mass_kg)}
                            </td>
                          )}
                          <td className="px-3 py-2 text-slate-500">
                            {c.placement ? (
                              <span className="rounded-full bg-violet-500/15 px-2 py-0.5 text-[10px] font-semibold text-violet-300" title={JSON.stringify(c.placement)}>
                                4×4 placed
                              </span>
                            ) : 'identity'}
                          </td>
                          <td className="px-3 py-2 text-slate-500">{c.notes || '—'}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>

            {/* ── Aero binding + stage map ── */}
            <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
              <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
                <h3 className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                  <Wind className="h-3.5 w-3.5 text-cyan-400" aria-hidden="true" /> Aero binding
                </h3>
                {revision.aero_binding ? (
                  <div className="text-sm">
                    <Link
                      href={`/engineering/aero/${encodeURIComponent(revision.aero_binding.wpn)}`}
                      className="font-mono font-bold tracking-wider text-cyan-300 underline-offset-2 hover:underline"
                    >
                      {revision.aero_binding.wpn}
                    </Link>
                    <span className="ml-2 text-xs text-slate-400">
                      rev <span className="font-mono text-slate-200">{revision.aero_binding.rev_letter}</span>
                    </span>
                  </div>
                ) : (
                  <div className="text-xs text-slate-500">No aero deck bound.</div>
                )}
              </div>

              <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface lg:col-span-2">
                <div className="flex items-center gap-1.5 border-b border-astra-border bg-astra-surface-alt px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                  <Flame className="h-3.5 w-3.5 text-orange-400" aria-hidden="true" /> Stage map
                </div>
                {revision.stage_map.length === 0 ? (
                  <div className="py-6 text-center text-xs text-slate-500">No stages.</div>
                ) : (
                  <table className="w-full text-xs" aria-label="Stage map">
                    <thead className="bg-astra-surface-alt text-slate-400">
                      <tr>
                        <th scope="col" className="px-3 py-2 text-left font-semibold">Stage</th>
                        <th scope="col" className="px-3 py-2 text-left font-semibold">Motor</th>
                        <th scope="col" className="px-3 py-2 text-center font-semibold">Rev</th>
                        <th scope="col" className="px-3 py-2 text-right font-semibold">Ignition (s)</th>
                        <th scope="col" className="px-3 py-2 text-left font-semibold">Thrust axis (B)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {revision.stage_map.map((s) => (
                        <tr key={s.stageNum} className="border-t border-astra-border">
                          <td className="px-3 py-2 font-mono font-bold text-slate-100">{s.stageNum}</td>
                          <td className="px-3 py-2">
                            <Link
                              href={`/engineering/motors/${encodeURIComponent(s.motorWpn)}`}
                              className="font-mono font-bold tracking-wider text-orange-300 underline-offset-2 hover:underline"
                            >
                              {s.motorWpn}
                            </Link>
                          </td>
                          <td className="px-3 py-2 text-center font-mono text-slate-300">{s.motorRevLetter}</td>
                          <td className="px-3 py-2 text-right font-mono tabular-nums text-slate-300">
                            {s.ignitionTime_s.toFixed(2)}
                          </td>
                          <td className="px-3 py-2 font-mono tabular-nums text-slate-300">
                            <StageAxis stage={s} />
                            {s.mcTrialId && (
                              <span className="ml-2 text-[10px] text-slate-500">MC {s.mcTrialId}</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </>
        ) : !revError ? (
          <div className="rounded-xl border border-astra-border bg-astra-surface py-12 text-center text-sm text-slate-500">
            No revision to display.
          </div>
        ) : null}
      </div>

      {/* ══ Revision history ══ */}
      <div className="mb-6">
        <h2 className="mb-2 text-sm font-semibold text-slate-200">Revision history</h2>
        <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
          {config.revisions.length === 0 ? (
            <div className="py-10 text-center text-sm text-slate-500">No revisions.</div>
          ) : (
            <table className="w-full text-xs" aria-label="Configuration revisions">
              <thead className="bg-astra-surface-alt text-slate-400">
                <tr>
                  <th scope="col" className="px-3 py-2 text-left font-semibold">Rev</th>
                  <th scope="col" className="px-3 py-2 text-left font-semibold">Description</th>
                  <th scope="col" className="px-3 py-2 text-right font-semibold">Total Mass</th>
                  <th scope="col" className="px-3 py-2 text-right font-semibold">Components</th>
                  <th scope="col" className="px-3 py-2 text-center font-semibold">Baseline</th>
                  <th scope="col" className="px-3 py-2 text-left font-semibold">Created</th>
                  <th scope="col" className="px-3 py-2 text-right font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody>
                {config.revisions.map((r) => {
                  const isActive = r.rev_letter === config.current_rev;
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
                      <td className="px-3 py-2 text-slate-400">{r.description || '—'}</td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums text-slate-300">
                        {fmtKg(r.total_mass_kg)}
                      </td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums text-slate-300">
                        {r.component_count}
                      </td>
                      <td className="px-3 py-2 text-center font-mono tabular-nums text-slate-400">
                        {r.astra_baseline_id != null ? `#${r.astra_baseline_id}` : '—'}
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
                            {isViewed ? 'Viewed' : 'View'}
                          </button>
                          {canWrite && !isActive && (
                            <button
                              type="button"
                              disabled={settingActive}
                              onClick={() => handleSetActive(r.rev_letter)}
                              className="rounded-lg border border-astra-border px-2 py-1 text-[10px] font-semibold text-slate-400 hover:border-emerald-500/40 hover:text-emerald-300 disabled:opacity-50"
                            >
                              Set active
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
      </div>

      {/* ══ Revision diff ══ */}
      {config.revisions.length >= 2 && (
        <div className="mb-6">
          <h2 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-slate-200">
            <ArrowLeftRight className="h-4 w-4 text-slate-400" aria-hidden="true" />
            Compare revisions
          </h2>
          <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
            <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <label htmlFor="cfg-diff-a" className="font-semibold">From:</label>
              <select
                id="cfg-diff-a" value={diffA} onChange={(e) => setDiffA(e.target.value)}
                className="rounded-lg border border-astra-border bg-astra-bg px-2.5 py-1.5 font-mono text-xs text-slate-200 outline-none focus:border-blue-500/50"
              >
                {config.revisions.map((r) => (
                  <option key={r.id} value={r.rev_letter}>{r.rev_letter}</option>
                ))}
              </select>
              <label htmlFor="cfg-diff-b" className="font-semibold">To:</label>
              <select
                id="cfg-diff-b" value={diffB} onChange={(e) => setDiffB(e.target.value)}
                className="rounded-lg border border-astra-border bg-astra-bg px-2.5 py-1.5 font-mono text-xs text-slate-200 outline-none focus:border-blue-500/50"
              >
                {config.revisions.map((r) => (
                  <option key={r.id} value={r.rev_letter}>{r.rev_letter}</option>
                ))}
              </select>
              {diffLoading && <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" aria-label="Loading diff" />}
            </div>

            {diffError && (
              <div role="alert" className="mb-3 flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
                <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {diffError}
              </div>
            )}

            {diffA === diffB ? (
              <div className="text-xs text-slate-500">Pick two different revisions to compare.</div>
            ) : diff ? (
              <DiffView diff={diff} />
            ) : null}
          </div>
        </div>
      )}

      {/* ══ §9 Bundle export ══ */}
      <div className="mb-6">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="flex items-center gap-1.5 text-sm font-semibold text-slate-200">
            <Package2 className="h-4 w-4 text-slate-400" aria-hidden="true" />
            CITADEL bundles — revision{' '}
            <span className="font-mono text-blue-300">{viewRev || '—'}</span>
          </h2>
          {canWrite && viewRev && (
            <button
              type="button"
              onClick={handleExport}
              disabled={exporting}
              className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
            >
              {exporting
                ? <><Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> Exporting bundle…</>
                : <><Package2 className="h-3.5 w-3.5" aria-hidden="true" /> Export bundle</>}
            </button>
          )}
        </div>

        {exportError && (
          <div role="alert" className="mb-3 flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
            <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {exportError}
          </div>
        )}

        {exported && (
          <div role="status" className="mb-3 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-400">
            <div className="flex flex-wrap items-center gap-1.5">
              {exported.reused ? 'Deterministic re-export — reused bundle' : 'Bundle exported'}
              <span className="font-mono font-bold tracking-wider text-emerald-300">{exported.bundle_hash}</span>
              · {exported.artifact_count} artifact{exported.artifact_count === 1 ? '' : 's'}
              <button
                type="button"
                onClick={() => handleDownload(exported)}
                disabled={downloading === exported.bundle_hash}
                className="ml-auto flex items-center gap-1 font-semibold text-emerald-300 underline-offset-2 hover:underline disabled:opacity-50"
              >
                <Download className="h-3 w-3" aria-hidden="true" />
                {downloading === exported.bundle_hash ? 'Downloading…' : 'Download zip'}
              </button>
            </div>
            {exported.warnings.length > 0 && (
              <ul className="mt-1.5 list-inside list-disc space-y-0.5 text-amber-400">
                {exported.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            )}
          </div>
        )}

        {bundlesError && (
          <div role="alert" className="mb-3 flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
            <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" /> {bundlesError}
          </div>
        )}

        <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
          {bundlesLoading && bundles.length === 0 ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-blue-500" aria-label="Loading bundle history" />
            </div>
          ) : bundles.length === 0 ? (
            <div className="py-8 text-center text-sm text-slate-500">
              No bundle exports for this revision yet.
            </div>
          ) : (
            <ul aria-label="Bundle export history">
              {bundles.map((b) => {
                const isOpen = openManifest === b.bundle_hash;
                return (
                  <li key={b.id} className="border-t border-astra-border first:border-t-0">
                    <div className="flex flex-wrap items-center gap-2 px-3 py-2 text-xs">
                      <span className="font-mono font-bold tracking-wider text-slate-100" title={b.bundle_hash}>
                        {hash8(b.bundle_hash)}
                      </span>
                      <span className="font-mono text-slate-500">{b.bundle_dirname}</span>
                      <span className="text-slate-500">{fmtDateTime(b.created_utc)}</span>
                      <span className="text-slate-400">
                        {b.artifact_count} artifact{b.artifact_count === 1 ? '' : 's'}
                      </span>
                      <div className="ml-auto flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => handleManifest(b)}
                          aria-expanded={isOpen}
                          className={clsx(
                            'flex items-center gap-1 rounded-lg border px-2 py-1 text-[10px] font-semibold',
                            isOpen
                              ? 'border-blue-500/40 bg-blue-500/10 text-blue-300'
                              : 'border-astra-border text-slate-400 hover:text-slate-200',
                          )}
                        >
                          <FileJson className="h-3 w-3" aria-hidden="true" /> Manifest
                          {isOpen
                            ? <ChevronDown className="h-3 w-3" aria-hidden="true" />
                            : <ChevronRight className="h-3 w-3" aria-hidden="true" />}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDownload(b)}
                          disabled={downloading === b.bundle_hash}
                          className="flex items-center gap-1 rounded-lg border border-astra-border px-2 py-1 text-[10px] font-semibold text-slate-400 hover:border-blue-500/40 hover:text-blue-300 disabled:opacity-50"
                        >
                          {downloading === b.bundle_hash
                            ? <Loader2 className="h-3 w-3 animate-spin" aria-label="Downloading" />
                            : <Download className="h-3 w-3" aria-hidden="true" />}
                          Download zip
                        </button>
                      </div>
                    </div>
                    {isOpen && (
                      <div className="border-t border-astra-border bg-astra-bg px-3 py-2">
                        {manifestLoading === b.bundle_hash ? (
                          <div className="flex items-center justify-center py-4">
                            <Loader2 className="h-4 w-4 animate-spin text-blue-500" aria-label="Loading manifest" />
                          </div>
                        ) : (
                          <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all font-mono text-[10px] leading-relaxed text-slate-400">
                            {JSON.stringify(manifests[b.bundle_hash] ?? {}, null, 2)}
                          </pre>
                        )}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  Structured diff renderer
// ══════════════════════════════════════

function DiffView({ diff }: { diff: ConfigDiff }) {
  const comp = diff.components;
  const stage = diff.stage_map;
  const empty =
    comp.added.length === 0 && comp.removed.length === 0
    && comp.changed.length === 0 && !diff.aero_binding
    && stage.added.length === 0 && stage.removed.length === 0
    && stage.changed.length === 0
    && Object.keys(diff.rollup_delta || {}).length === 0;

  if (empty) {
    return (
      <div className="text-xs text-slate-500">
        Revisions <span className="font-mono text-slate-300">{diff.from_rev}</span> and{' '}
        <span className="font-mono text-slate-300">{diff.to_rev}</span> are identical.
      </div>
    );
  }

  const massDelta = diff.rollup_delta?.totalMass_kg;

  return (
    <div className="space-y-4">
      {/* Components */}
      {(comp.added.length > 0 || comp.removed.length > 0 || comp.changed.length > 0) && (
        <div>
          <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Component changes
          </h3>
          <table className="w-full text-xs" aria-label={`Component diff ${diff.from_rev} to ${diff.to_rev}`}>
            <thead className="text-slate-400">
              <tr className="border-b border-astra-border">
                <th scope="col" className="px-2 py-1.5 text-left font-semibold">Change</th>
                <th scope="col" className="px-2 py-1.5 text-left font-semibold">WPN</th>
                <th scope="col" className="px-2 py-1.5 text-left font-semibold">Detail</th>
              </tr>
            </thead>
            <tbody>
              {comp.added.map((c, i) => (
                <tr key={`a-${c.wpn}-${i}`} className="border-b border-astra-border/50 bg-emerald-500/5">
                  <td className="px-2 py-1.5 font-semibold text-emerald-400">+ added</td>
                  <td className="px-2 py-1.5 font-mono text-emerald-300">{c.wpn}</td>
                  <td className="px-2 py-1.5 text-slate-400">
                    <ConfigRoleBadge role={c.role} />
                    <span className="ml-2">{c.name || ''}</span>
                  </td>
                </tr>
              ))}
              {comp.removed.map((c, i) => (
                <tr key={`r-${c.wpn}-${i}`} className="border-b border-astra-border/50 bg-red-500/5">
                  <td className="px-2 py-1.5 font-semibold text-red-400">− removed</td>
                  <td className="px-2 py-1.5 font-mono text-red-300">{c.wpn}</td>
                  <td className="px-2 py-1.5 text-slate-400">
                    <ConfigRoleBadge role={c.role} />
                    <span className="ml-2">{c.name || ''}</span>
                  </td>
                </tr>
              ))}
              {comp.changed.map((c, i) => (
                <tr key={`c-${c.wpn}-${i}`} className="border-b border-astra-border/50 bg-amber-500/5">
                  <td className="px-2 py-1.5 font-semibold text-amber-400">~ changed</td>
                  <td className="px-2 py-1.5 font-mono text-amber-300">{c.wpn}</td>
                  <td className="px-2 py-1.5 text-slate-400">
                    {c.fields.map((f) => (
                      <span key={f} className="mr-3">
                        {f}:{' '}
                        <span className="font-mono text-red-300/80">
                          {f === 'placement'
                            ? (c.from?.placement ? '4×4' : 'identity')
                            : String((c.from as Record<string, unknown>)?.[f] ?? '—')}
                        </span>
                        {' → '}
                        <span className="font-mono text-emerald-300/90">
                          {f === 'placement'
                            ? (c.to?.placement ? '4×4' : 'identity')
                            : String((c.to as Record<string, unknown>)?.[f] ?? '—')}
                        </span>
                      </span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Aero binding */}
      {diff.aero_binding && (
        <div>
          <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Aero binding change
          </h3>
          <div className="text-xs text-slate-400">
            <span className="font-mono text-red-300/80">
              {diff.aero_binding.from
                ? `${diff.aero_binding.from.wpn} rev ${diff.aero_binding.from.rev_letter}`
                : 'none'}
            </span>
            {' → '}
            <span className="font-mono text-emerald-300/90">
              {diff.aero_binding.to
                ? `${diff.aero_binding.to.wpn} rev ${diff.aero_binding.to.rev_letter}`
                : 'none'}
            </span>
          </div>
        </div>
      )}

      {/* Stage map */}
      {(stage.added.length > 0 || stage.removed.length > 0 || stage.changed.length > 0) && (
        <div>
          <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Stage map changes
          </h3>
          <ul className="space-y-1 text-xs">
            {stage.added.map((s) => (
              <li key={`sa-${s.stageNum}`} className="text-emerald-400">
                + stage {s.stageNum}:{' '}
                <span className="font-mono text-emerald-300">
                  {s.motorWpn} rev {s.motorRevLetter}
                </span>{' '}
                @ {s.ignitionTime_s.toFixed(2)} s
              </li>
            ))}
            {stage.removed.map((s) => (
              <li key={`sr-${s.stageNum}`} className="text-red-400">
                − stage {s.stageNum}:{' '}
                <span className="font-mono text-red-300">
                  {s.motorWpn} rev {s.motorRevLetter}
                </span>{' '}
                @ {s.ignitionTime_s.toFixed(2)} s
              </li>
            ))}
            {stage.changed.map((s) => (
              <li key={`sc-${s.stageNum}`} className="text-amber-400">
                ~ stage {s.stageNum}:{' '}
                <span className="font-mono text-red-300/80">
                  {s.from.motorWpn} rev {s.from.motorRevLetter} @ {s.from.ignitionTime_s.toFixed(2)} s · axis {fmtVec3(s.from.thrustAxis_B, 2)}
                </span>
                {' → '}
                <span className="font-mono text-emerald-300/90">
                  {s.to.motorWpn} rev {s.to.motorRevLetter} @ {s.to.ignitionTime_s.toFixed(2)} s · axis {fmtVec3(s.to.thrustAxis_B, 2)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Roll-up delta */}
      {Object.keys(diff.rollup_delta || {}).length > 0 && (
        <div>
          <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Roll-up delta ({diff.to_rev} − {diff.from_rev})
          </h3>
          <div className="flex flex-wrap gap-6 text-xs">
            {massDelta !== undefined && (
              <div>
                <span className="text-slate-500">Total mass: </span>
                <span className={clsx(
                  'font-mono tabular-nums',
                  massDelta > 0 ? 'text-emerald-400' : massDelta < 0 ? 'text-red-400' : 'text-slate-400',
                )}>
                  {massDelta > 0 ? '+' : ''}{fmtNum(massDelta)} kg
                </span>
              </div>
            )}
            {diff.rollup_delta?.cg_m_B && (
              <div>
                <span className="text-slate-500">ΔCG (m, body): </span>
                <span className="font-mono tabular-nums text-slate-300">
                  {fmtVec3(diff.rollup_delta.cg_m_B)}
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
