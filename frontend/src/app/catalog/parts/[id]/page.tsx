'use client';

/**
 * ASTRA — Catalog Part Detail Page
 * ==================================
 * File: frontend/src/app/catalog/parts/[id]/page.tsx
 *
 * Sections:
 *   - Header (part number, name, lifecycle pill, supplier link)
 *   - Physical / Power / Environmental / Compliance specs
 *   - Connectors+Pins (drill-in via expand rows)
 *   - Where-used (project units)
 *   - Variants (children of this part) and parent link
 *
 * Phase 3 — ASTRA-TDD-INTF-002.
 */

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ChevronLeft, ChevronRight, ChevronDown, Cpu, Loader2, AlertTriangle,
  Trash2, Plug, Building2, MapPin, GitBranch, Clock, Zap, Thermometer,
  ShieldCheck, Hash, RefreshCw, CheckCircle2,
} from 'lucide-react';
import clsx from 'clsx';

import { catalogAPI } from '@/lib/catalog-api';
import { haroldAPI } from '@/lib/harold-api';
import { formatApiError, parseStructuredApiError } from '@/lib/errors';
import {
  type CatalogPartDetail,
  type CatalogPartUsage,
  type CatalogPartUsageReport,
  type CatalogPart,
  PART_CLASS_LABELS,
  LRU_CLASS_LABELS,
  LIFECYCLE_COLORS,
} from '@/lib/catalog-types';
import { useAuth } from '@/lib/auth';

// ══════════════════════════════════════
//  Helpers
// ══════════════════════════════════════

function fmtNum(v?: string | number | null): string {
  if (v === null || v === undefined || v === '') return '—';
  return String(v);
}

type IconType = React.ComponentType<React.SVGProps<SVGSVGElement> & { className?: string }>;

function Spec({ icon: Icon, label, value, unit }: {
  icon: IconType;
  label: string; value?: string | number | null; unit?: string;
}) {
  return (
    <div className="flex items-start gap-2 text-xs">
      <Icon className="h-3.5 w-3.5 mt-0.5 text-slate-500 flex-shrink-0" aria-hidden="true" />
      <div className="flex-1">
        <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
        <div className="text-slate-200">{fmtNum(value)}{value !== null && value !== undefined && value !== '' && unit ? ` ${unit}` : ''}</div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  Page
// ══════════════════════════════════════

export default function CatalogPartDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { user } = useAuth();
  const partId = Number(params?.id);

  const [part, setPart] = useState<CatalogPartDetail | null>(null);
  const [usage, setUsage] = useState<CatalogPartUsage[]>([]);
  const [usageReport, setUsageReport] = useState<CatalogPartUsageReport | null>(null);
  const [variants, setVariants] = useState<CatalogPart[]>([]);
  const [parent, setParent] = useState<CatalogPart | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expandedConn, setExpandedConn] = useState<Set<number>>(new Set());
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  // ── Phase 4: manual HAROLD reconcile state ──
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  const canDelete = user?.role === 'admin';

  const refresh = useCallback(() => {
    if (!Number.isFinite(partId)) return;
    setLoading(true);
    setError('');
    Promise.all([
      catalogAPI.getPart(partId),
      catalogAPI.getPartUsage(partId),
      catalogAPI.getPartUsageReport(partId),
    ])
      .then(async ([pRes, uRes, rRes]) => {
        setPart(pRes.data);
        setUsage(uRes.data);
        setUsageReport(rRes.data);

        // Variants: list parts whose parent_part_id == this part
        // The list endpoint doesn't filter by parent_part_id, so we
        // fetch the full list and filter client-side. Cheap for catalog
        // sizes the UI is designed for.
        try {
          const listAll = await catalogAPI.listParts({ limit: 200 });
          setVariants(listAll.data.filter((p) => {
            const v = p as CatalogPart & { parent_part_id?: number | null };
            return v.parent_part_id === partId;
          }));
        } catch {
          setVariants([]);
        }

        // Parent
        if (pRes.data.parent_part_id) {
          try {
            const par = await catalogAPI.getPart(pRes.data.parent_part_id);
            setParent(par.data);
          } catch {
            setParent(null);
          }
        } else {
          setParent(null);
        }
      })
      .catch((e) => setError(formatApiError(e, 'Failed to load catalog part')))
      .finally(() => setLoading(false));
  }, [partId]);

  useEffect(() => { refresh(); }, [refresh]);

  const toggleConn = (cid: number) => {
    setExpandedConn((prev) => {
      const next = new Set(prev);
      if (next.has(cid)) next.delete(cid);
      else next.add(cid);
      return next;
    });
  };

  const handleDelete = async () => {
    setDeleting(true);
    setError('');
    try {
      await catalogAPI.deletePart(partId);
      router.push('/catalog');
    } catch (e: unknown) {
      // CLEANUP-002 Phase 4 (AD-7): a 409 carries a structured
      // usage report. Refresh the local usageReport so the modal
      // surfaces the live project list rather than the stale
      // "looked deletable a moment ago" view.
      const structured = parseStructuredApiError(e);
      if (
        structured?.code === 'part_in_use'
        && typeof structured.usage === 'object'
        && structured.usage !== null
      ) {
        setUsageReport(structured.usage as CatalogPartUsageReport);
        setError(
          typeof structured.message === 'string'
            ? structured.message
            : 'Cannot delete — part is in use.',
        );
      } else {
        setError(formatApiError(e, 'Failed to delete catalog part'));
        setConfirmDelete(false);
      }
    } finally {
      setDeleting(false);
    }
  };

  // Manual "Sync with HAROLD" — visible only when wpn_pending_sync is true.
  // Calls POST /harold/parts/{id}/reconcile and refetches the part on
  // success so the freshly cleared flag (and any reissued WPN) lands.
  const handleReconcile = async () => {
    setSyncing(true);
    setSyncMessage(null);
    setSyncError(null);
    try {
      const r = await haroldAPI.reconcile(partId);
      if (r.data.harold_available) {
        const result = r.data.data;
        if (result.reconciled) {
          const reissued = result.prior_wpn && result.prior_wpn !== result.wpn;
          setSyncMessage(
            reissued
              ? `Reissued: ${result.prior_wpn} → ${result.wpn}`
              : `Synced with HAROLD as ${result.wpn}`,
          );
        } else {
          setSyncMessage(result.message || 'Nothing to reconcile');
        }
        refresh();
      } else {
        setSyncError(r.data.reason || 'HAROLD unavailable');
      }
    } catch (e) {
      setSyncError(formatApiError(e, 'Sync failed'));
    } finally {
      setSyncing(false);
    }
  };

  if (loading && !part) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-blue-500" aria-label="Loading catalog part" />
      </div>
    );
  }

  if (!part) {
    return (
      <div>
        <button type="button" onClick={() => router.push('/catalog')} className="mb-3 flex items-center gap-1 text-xs text-slate-400 hover:text-blue-300">
          <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" /> Back to Catalog
        </button>
        <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {error || 'Catalog part not found'}
        </div>
      </div>
    );
  }

  const lc = LIFECYCLE_COLORS[part.lifecycle_status];

  return (
    <div>
      <button type="button" onClick={() => router.push('/catalog')} className="mb-4 flex items-center gap-1 text-xs text-slate-400 hover:text-blue-300">
        <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" /> Back to Catalog
      </button>

      {/* Header */}
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Cpu className="h-4 w-4 text-blue-400" aria-hidden="true" />
            <button type="button" onClick={() => router.push(`/catalog/suppliers/${part.supplier_id}`)}
              className="hover:text-blue-300 flex items-center gap-1">
              <Building2 className="h-3 w-3" aria-hidden="true" />
              {part.supplier_name || `supplier ${part.supplier_id}`}
            </button>
          </div>
          <h1 className="mt-1 flex flex-wrap items-baseline gap-2 text-2xl font-bold tracking-tight text-slate-100">
            {part.internal_part_number ? (
              <>
                <span className="font-mono tracking-wider">{part.internal_part_number}</span>
                {part.wpn_pending_sync && (
                  <span
                    title="Fallback WPN — pending HAROLD reconciliation"
                    className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-300"
                  >
                    <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-400" aria-hidden="true" />
                    Pending Sync
                  </span>
                )}
              </>
            ) : (
              <span>{part.part_number}</span>
            )}
            {part.revision && <span className="text-sm font-normal text-slate-500">rev {part.revision}</span>}
          </h1>
          {part.internal_part_number && (
            <p className="mt-0.5 text-[11px] text-slate-500">
              Mfr P/N <span className="font-mono text-slate-300">{part.part_number}</span>
            </p>
          )}
          <p className="text-sm text-slate-300">{part.name}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
            <span className="rounded-full px-2 py-0.5 font-semibold" style={{ background: lc.bg, color: lc.text }}>{lc.label}</span>
            <span>{PART_CLASS_LABELS[part.part_class]}</span>
            <span>·</span>
            <span>{LRU_CLASS_LABELS[part.lru_classification]}</span>
            {part.designation && <><span>·</span><span>{part.designation}</span></>}
            {part.variant_label && <><span>·</span><span>variant: <strong className="text-slate-300">{part.variant_label}</strong></span></>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {part.wpn_pending_sync && (
            <button
              type="button"
              onClick={handleReconcile}
              disabled={syncing}
              title="Re-register this fallback-issued WPN with HAROLD"
              className="flex items-center gap-1.5 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-xs font-semibold text-amber-300 hover:bg-amber-500/20 disabled:opacity-50"
            >
              {syncing
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                : <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />}
              {syncing ? 'Syncing…' : 'Sync with HAROLD'}
            </button>
          )}
          {/* CLEANUP-002 Phase 4 (AD-8): proactive usage badge so the
              operator sees deletability before clicking. The same
              report drives the disabled/enabled state of the Delete
              button below. */}
          {usageReport && (
            usageReport.deletable ? (
              <span
                className="rounded-full bg-emerald-500/15 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-emerald-400"
                title="No downstream references — safe to delete"
              >
                Unused
              </span>
            ) : (
              <span
                className="rounded-full bg-amber-500/15 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-amber-300"
                title={`${usageReport.total_references} reference(s) across ${usageReport.projects.length} project(s)`}
              >
                Used in {usageReport.projects.length} project{usageReport.projects.length === 1 ? '' : 's'}
              </span>
            )
          )}
          {canDelete && (
            <button type="button" onClick={() => setConfirmDelete(true)}
              className="flex items-center gap-1 rounded-lg border border-red-500/30 px-3 py-1.5 text-xs text-red-400 hover:bg-red-500/10">
              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" /> Delete
            </button>
          )}
        </div>
      </div>

      {syncMessage && (
        <div role="status" className="mb-3 flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
          <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" /> {syncMessage}
        </div>
      )}
      {syncError && (
        <div role="alert" className="mb-3 flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" /> Sync skipped: {syncError}
        </div>
      )}

      {error && (
        <div role="alert" className="mb-3 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" /> {error}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Physical specs */}
        <section className="rounded-xl border border-astra-border bg-astra-surface p-4">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">Physical</h2>
          <div className="grid grid-cols-2 gap-3">
            <Spec icon={Hash}    label="Mass" value={part.mass_kg} unit="kg" />
            <Spec icon={Hash}    label="L × W × H" value={[part.dim_length_mm, part.dim_width_mm, part.dim_height_mm].some((v) => v) ? `${fmtNum(part.dim_length_mm)} × ${fmtNum(part.dim_width_mm)} × ${fmtNum(part.dim_height_mm)}` : null} unit="mm" />
          </div>
        </section>

        {/* Power */}
        <section className="rounded-xl border border-astra-border bg-astra-surface p-4">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">Power &amp; Voltage</h2>
          <div className="grid grid-cols-2 gap-3">
            <Spec icon={Zap} label="Nominal" value={part.power_watts_nominal} unit="W" />
            <Spec icon={Zap} label="Peak"    value={part.power_watts_peak} unit="W" />
            <Spec icon={Zap} label="V In Min" value={part.voltage_input_min_v} unit="V" />
            <Spec icon={Zap} label="V In Max" value={part.voltage_input_max_v} unit="V" />
          </div>
        </section>

        {/* Environmental */}
        <section className="rounded-xl border border-astra-border bg-astra-surface p-4 lg:col-span-2">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">Environmental Envelope</h2>
          <div className="grid grid-cols-4 gap-3">
            <Spec icon={Thermometer} label="Op Temp Min"    value={part.temp_operating_min_c} unit="°C" />
            <Spec icon={Thermometer} label="Op Temp Max"    value={part.temp_operating_max_c} unit="°C" />
            <Spec icon={Thermometer} label="Storage Min"    value={part.temp_storage_min_c}   unit="°C" />
            <Spec icon={Thermometer} label="Storage Max"    value={part.temp_storage_max_c}   unit="°C" />
            <Spec icon={Hash}        label="Vibration"      value={part.vibration_random_grms} unit="Grms" />
            <Spec icon={Hash}        label="Shock"          value={part.shock_mechanical_g}    unit="g" />
            <Spec icon={Hash}        label="Humidity Max"   value={part.humidity_max_pct}      unit="%" />
            <Spec icon={Hash}        label="Altitude Max"   value={part.altitude_max_m}        unit="m" />
            <Spec icon={Hash}        label="EMI CE102"      value={part.emi_ce102_limit_dbua}  unit="dBµA" />
            <Spec icon={Hash}        label="EMI RS103"      value={part.emi_rs103_limit_vm}    unit="V/m" />
            <Spec icon={Hash}        label="ESD HBM"        value={part.esd_hbm_v}             unit="V" />
          </div>
        </section>

        {/* Compliance & Lifecycle */}
        <section className="rounded-xl border border-astra-border bg-astra-surface p-4">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">Compliance</h2>
          <ul className="space-y-1 text-xs text-slate-300">
            <li><ShieldCheck className="inline h-3 w-3 mr-1" aria-hidden="true" /> MIL-STD-810: <strong>{part.mil_std_810_tested ? 'Yes' : 'No'}</strong></li>
            <li><ShieldCheck className="inline h-3 w-3 mr-1" aria-hidden="true" /> MIL-STD-461: <strong>{part.mil_std_461_tested ? 'Yes' : 'No'}</strong></li>
            <li><ShieldCheck className="inline h-3 w-3 mr-1" aria-hidden="true" /> RoHS: <strong>{part.rohs_compliant ? 'Yes' : 'No'}</strong></li>
            <li><ShieldCheck className="inline h-3 w-3 mr-1" aria-hidden="true" /> ITAR: <strong>{part.itar_controlled ? 'Yes' : 'No'}</strong></li>
            {part.export_classification && <li>Export Class: <strong className="text-slate-200">{part.export_classification}</strong></li>}
          </ul>
        </section>

        <section className="rounded-xl border border-astra-border bg-astra-surface p-4">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">Lifecycle</h2>
          <div className="space-y-2 text-xs text-slate-300">
            <div className="flex items-center gap-2">
              <Clock className="h-3 w-3" aria-hidden="true" />
              <span>Status:</span>
              <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold" style={{ background: lc.bg, color: lc.text }}>{lc.label}</span>
            </div>
            {part.eol_date && (
              <div className="flex items-center gap-2">
                <Clock className="h-3 w-3" aria-hidden="true" /> EOL Date: <strong>{part.eol_date}</strong>
              </div>
            )}
            {parent && (
              <div className="mt-2 flex items-center gap-2">
                <GitBranch className="h-3 w-3" aria-hidden="true" />
                Parent:
                <button type="button" onClick={() => router.push(`/catalog/parts/${parent.id}`)}
                  className="text-blue-400 hover:text-blue-300">{parent.part_number}</button>
              </div>
            )}
          </div>
        </section>

        {/* Connectors + Pins */}
        <section className="rounded-xl border border-astra-border bg-astra-surface p-4 lg:col-span-2">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-2">
            <Plug className="h-3.5 w-3.5" aria-hidden="true" />
            Connectors &amp; Pins ({part.connectors.length})
          </h2>
          {part.connectors.length === 0 ? (
            <div className="py-4 text-center text-xs text-slate-500">No connectors defined for this part.</div>
          ) : (
            <ul className="divide-y divide-astra-border">
              {part.connectors.map((c) => {
                const open = expandedConn.has(c.id);
                return (
                  <li key={c.id} className="py-2">
                    <button type="button"
                      onClick={() => toggleConn(c.id)}
                      aria-expanded={open}
                      className="flex w-full items-center justify-between gap-2 text-left hover:text-blue-300"
                    >
                      <div className="flex items-center gap-2">
                        {open ? <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" /> : <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />}
                        <Plug className="h-3.5 w-3.5 text-blue-400" aria-hidden="true" />
                        <span className="text-xs font-bold text-slate-200">{c.reference}</span>
                        {c.connector_type && <span className="text-[10px] text-slate-500">{c.connector_type}</span>}
                        {c.gender && <span className="text-[10px] text-slate-500">({c.gender})</span>}
                      </div>
                      <span className="text-[10px] text-slate-500">{c.pin_count} pins</span>
                    </button>
                    {open && (
                      <div className="mt-2 overflow-x-auto rounded-lg border border-astra-border bg-astra-bg">
                        <table className="w-full text-[11px]">
                          <thead className="bg-astra-surface-alt text-slate-500">
                            <tr>
                              <th className="px-2 py-1 text-left font-semibold">Pos</th>
                              <th className="px-2 py-1 text-left font-semibold">Mfr Pin Name</th>
                              <th className="px-2 py-1 text-left font-semibold">Function</th>
                              <th className="px-2 py-1 text-left font-semibold">Type</th>
                              <th className="px-2 py-1 text-left font-semibold">Direction</th>
                              <th className="px-2 py-1 text-left font-semibold">Notes</th>
                            </tr>
                          </thead>
                          <tbody>
                            {c.pins.map((p) => (
                              <tr key={p.id} className="border-t border-astra-border/40">
                                <td className="px-2 py-1 font-mono text-slate-300">{p.pin_position}</td>
                                <td className="px-2 py-1 font-semibold text-slate-200">{p.mfr_pin_name}</td>
                                <td className="px-2 py-1 text-slate-400">{p.mfr_signal_function || '—'}</td>
                                <td className="px-2 py-1 text-slate-400">{p.mfr_signal_type || '—'}</td>
                                <td className="px-2 py-1 text-slate-400">{p.mfr_direction || '—'}</td>
                                <td className="px-2 py-1 text-slate-500">{p.notes || ''}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {/* Where used */}
        <section className="rounded-xl border border-astra-border bg-astra-surface p-4 lg:col-span-2">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-2">
            <MapPin className="h-3.5 w-3.5" aria-hidden="true" />
            Where Used ({usage.length})
          </h2>
          {usage.length === 0 ? (
            <div className="py-4 text-center text-xs text-slate-500">Not yet placed in any project.</div>
          ) : (
            <table className="w-full text-xs">
              <thead className="text-slate-500">
                <tr className="border-b border-astra-border">
                  <th className="px-2 py-2 text-left font-semibold">Project</th>
                  <th className="px-2 py-2 text-left font-semibold">Designation</th>
                  <th className="px-2 py-2 text-left font-semibold">Location</th>
                  <th className="px-2 py-2 text-left font-semibold">Serial</th>
                </tr>
              </thead>
              <tbody>
                {usage.map((u) => (
                  <tr key={u.unit_id}
                    className="border-b border-astra-border/40 hover:bg-astra-surface-alt cursor-pointer"
                    onClick={() => router.push(`/projects/${u.project_id}/interfaces/unit/${u.unit_id}`)}
                  >
                    <td className="px-2 py-2 text-slate-300">{u.project_code || `project ${u.project_id}`}</td>
                    <td className="px-2 py-2 font-bold text-slate-200">{u.designation}</td>
                    <td className="px-2 py-2 text-slate-400">{u.location_zone || '—'}</td>
                    <td className="px-2 py-2 text-slate-400 font-mono">{u.serial_number || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {/* Variants */}
        <section className="rounded-xl border border-astra-border bg-astra-surface p-4 lg:col-span-2">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-2">
            <GitBranch className="h-3.5 w-3.5" aria-hidden="true" />
            Variants ({variants.length})
          </h2>
          {variants.length === 0 ? (
            <div className="py-4 text-center text-xs text-slate-500">No variants of this part exist yet.</div>
          ) : (
            <ul className="divide-y divide-astra-border">
              {variants.map((v) => (
                <li key={v.id}>
                  <button type="button" onClick={() => router.push(`/catalog/parts/${v.id}`)}
                    className={clsx(
                      'flex w-full items-center justify-between py-2 px-1 text-left text-xs',
                      'hover:bg-astra-surface-alt'
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <Cpu className="h-3.5 w-3.5 text-blue-400" aria-hidden="true" />
                      <span className="font-bold text-slate-200">{v.part_number}</span>
                      {v.revision && <span className="text-[10px] text-slate-500">rev {v.revision}</span>}
                      <span className="text-slate-400">— {v.name}</span>
                    </div>
                    <ChevronRight className="h-3.5 w-3.5 text-slate-500" aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {/* CLEANUP-002 Phase 4 (AD-7 + AD-8): structured delete modal
          driven by the usage report. When `deletable` is false the
          confirm button is hard-disabled and the modal renders the
          full project list so the operator can go remove references
          themselves. The 409 path overwrites usageReport with the
          server's snapshot if state drifted between mount + click. */}
      {confirmDelete && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="catalog-delete-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={() => !deleting && setConfirmDelete(false)}
        >
          <div
            className="w-full max-w-lg rounded-2xl border border-astra-border bg-astra-surface p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 id="catalog-delete-title" className="text-sm font-bold text-slate-100">
              Delete catalog part &ldquo;{part.internal_part_number || part.part_number}&rdquo;?
            </h3>

            {!usageReport || usageReport.deletable ? (
              <p className="mt-2 text-xs text-slate-400">
                This part has no downstream references. It will be soft-deleted
                (the row stays for audit, but it disappears from the catalog).
              </p>
            ) : (
              <>
                <p className="mt-2 text-xs text-amber-300">
                  Cannot delete — this part is referenced by{' '}
                  <strong>{usageReport.total_references}</strong>{' '}
                  {usageReport.total_references === 1 ? 'entity' : 'entities'}
                  {usageReport.projects.length > 0
                    ? ` across ${usageReport.projects.length} project${usageReport.projects.length === 1 ? '' : 's'}`
                    : ''}
                  . Remove the references first, then retry.
                </p>

                {usageReport.projects.length > 0 && (
                  <div className="mt-3 max-h-64 overflow-auto rounded-lg border border-astra-border">
                    <table className="w-full text-[11px]">
                      <thead className="bg-astra-surface-alt text-slate-500">
                        <tr>
                          <th className="px-2 py-1 text-left font-semibold">Project</th>
                          <th className="px-2 py-1 text-right font-semibold">BOM lines</th>
                          <th className="px-2 py-1 text-right font-semibold">Joints</th>
                          <th className="px-2 py-1 text-right font-semibold">Units</th>
                        </tr>
                      </thead>
                      <tbody>
                        {usageReport.projects.map((p) => (
                          <tr key={p.project_id} className="border-t border-astra-border/40">
                            <td className="px-2 py-1 text-slate-300">
                              {p.project_code ? <span className="font-mono mr-1">{p.project_code}</span> : null}
                              {p.project_name || `project ${p.project_id}`}
                            </td>
                            <td className="px-2 py-1 text-right text-slate-300">{p.project_part_count}</td>
                            <td className="px-2 py-1 text-right text-slate-300">{p.mechanical_joint_count}</td>
                            <td className="px-2 py-1 text-right text-slate-300">{p.unit_count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

              </>
            )}

            <div className="mt-5 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirmDelete(false)}
                disabled={deleting}
                className="rounded-lg border border-astra-border px-4 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200 disabled:opacity-40"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={deleting || (usageReport ? !usageReport.deletable : false)}
                className="flex items-center gap-1.5 rounded-lg bg-red-500 px-4 py-2 text-xs font-semibold text-white outline-none focus:ring-2 focus:ring-red-500/40 hover:bg-red-600 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {deleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : null}
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
