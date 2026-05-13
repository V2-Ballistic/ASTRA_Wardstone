'use client';

/**
 * ASTRA — Catalog Landing Page (spec §16)
 * =========================================
 * File: frontend/src/app/catalog/page.tsx
 *
 * Three tabs: Suppliers | Parts | Pending Imports.
 * Each tab renders its own search + table.
 *
 * Pending Imports tab is read-only in Phase 3 (the backend list endpoint
 * exists and returns [] until Phase 7's extraction pipeline runs).
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useRouter } from 'next/navigation';
import {
  Loader2, RefreshCw, Plus, Search, ChevronRight, Building2, Cpu,
  FileSearch2, AlertTriangle, Package, Globe, Upload,
} from 'lucide-react';
import clsx from 'clsx';

import { catalogAPI } from '@/lib/catalog-api';
import { formatApiError } from '@/lib/errors';
import {
  type Supplier,
  type CatalogPart,
  type PartClass,
  type LifecycleStatus,
  type PendingCatalogImport,
  PART_CLASS_LABELS,
  LIFECYCLE_COLORS,
  PENDING_IMPORT_STATUS_LABELS,
} from '@/lib/catalog-types';

type Tab = 'suppliers' | 'parts' | 'pending';

const PART_CLASSES: PartClass[] = [
  'processor', 'sensor', 'power_supply', 'radio', 'antenna', 'actuator',
  'display', 'harness', 'connector_only', 'compute_module',
  'power_distribution', 'interface_card', 'other',
];

const LIFECYCLE_STATUSES: LifecycleStatus[] = [
  'active', 'preferred', 'obsolete', 'eol_announced', 'nrnd', 'restricted',
];

// ══════════════════════════════════════
//  Suppliers Tab
// ══════════════════════════════════════

function SuppliersTab() {
  const router = useRouter();
  const [items, setItems] = useState<Supplier[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const refresh = useCallback(() => {
    setLoading(true);
    catalogAPI.listSuppliers({ q: search || undefined, limit: 200 })
      .then((r) => setItems(r.data))
      .catch((e) => setError(formatApiError(e, 'Failed to load suppliers')))
      .finally(() => setLoading(false));
  }, [search]);

  useEffect(() => {
    const handle = setTimeout(refresh, 250);
    return () => clearTimeout(handle);
  }, [refresh]);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" aria-hidden="true" />
          <label htmlFor="sup-search" className="sr-only">Search suppliers</label>
          <input
            id="sup-search"
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search suppliers by name or CAGE…"
            className="w-full rounded-lg border border-astra-border bg-astra-bg pl-8 pr-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
          />
        </div>
        <button
          type="button"
          onClick={refresh}
          aria-label="Refresh suppliers"
          className="rounded-lg border border-astra-border p-2 text-slate-400 hover:border-blue-500/30 hover:text-slate-200"
        >
          <RefreshCw className={clsx('h-3.5 w-3.5', loading && 'animate-spin')} aria-hidden="true" />
        </button>
        <button
          type="button"
          onClick={() => router.push('/catalog/suppliers/new')}
          className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-500"
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" /> New Supplier
        </button>
      </div>

      {error && (
        <div role="alert" className="mb-3 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" /> {error}
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
        {loading && items.length === 0 ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="h-5 w-5 animate-spin text-blue-500" aria-label="Loading" />
          </div>
        ) : items.length === 0 ? (
          <div className="py-12 text-center text-sm text-slate-500">
            <Building2 className="h-8 w-8 mx-auto mb-2 text-slate-600" aria-hidden="true" />
            No suppliers yet. Click <strong className="text-slate-300">New Supplier</strong> to add one.
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead className="bg-astra-surface-alt text-slate-400">
              <tr>
                <th className="px-3 py-2 text-left font-semibold">Name</th>
                <th className="px-3 py-2 text-left font-semibold">CAGE</th>
                <th className="px-3 py-2 text-left font-semibold">Country</th>
                <th className="px-3 py-2 text-right font-semibold">Parts</th>
                <th className="px-3 py-2 text-right font-semibold">Documents</th>
                <th className="px-3 py-2 text-center font-semibold">Status</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((s) => (
                <tr
                  key={s.id}
                  className="border-t border-astra-border hover:bg-astra-surface-alt cursor-pointer"
                  onClick={() => router.push(`/catalog/suppliers/${s.id}`)}
                >
                  <td className="px-3 py-2 font-semibold text-slate-200">
                    <div className="flex items-center gap-2">
                      <Building2 className="h-3.5 w-3.5 text-blue-400" aria-hidden="true" />
                      {s.name}
                      {s.is_in_house && (
                        <span className="rounded-full bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-emerald-400">
                          In House
                        </span>
                      )}
                    </div>
                    {s.short_name && <div className="text-[10px] text-slate-500 ml-5">{s.short_name}</div>}
                  </td>
                  <td className="px-3 py-2 text-slate-400 font-mono">{s.cage_code || '—'}</td>
                  <td className="px-3 py-2 text-slate-400">{s.country || '—'}</td>
                  <td className="px-3 py-2 text-right text-slate-300">{s.catalog_part_count}</td>
                  <td className="px-3 py-2 text-right text-slate-300">{s.document_count}</td>
                  <td className="px-3 py-2 text-center">
                    {s.is_active
                      ? <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">Active</span>
                      : <span className="rounded-full bg-slate-500/15 px-2 py-0.5 text-[10px] font-semibold text-slate-400">Inactive</span>
                    }
                  </td>
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

// ══════════════════════════════════════
//  Parts Tab
// ══════════════════════════════════════

function PartsTab() {
  const router = useRouter();
  const [items, setItems] = useState<CatalogPart[]>([]);
  const [search, setSearch] = useState('');
  const [partClass, setPartClass] = useState<PartClass | ''>('');
  const [lifecycle, setLifecycle] = useState<LifecycleStatus | ''>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  // ── TDD-CAT-002: STEP upload state ──
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    catalogAPI.listParts({
      q: search || undefined,
      part_class: partClass || undefined,
      lifecycle_status: lifecycle || undefined,
      limit: 200,
    })
      .then((r) => setItems(r.data))
      .catch((e) => setError(formatApiError(e, 'Failed to load catalog parts')))
      .finally(() => setLoading(false));
  }, [search, partClass, lifecycle]);

  useEffect(() => {
    const h = setTimeout(refresh, 250);
    return () => clearTimeout(h);
  }, [refresh]);

  // TDD-CAT-002: STEP upload handler — file picker → POST /catalog/upload-step
  // → navigate to the new pending-imports review page.
  const onPickStepFile = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const onStepFileSelected = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setError('');
    setUploading(true);
    try {
      const r = await catalogAPI.uploadStep(f);
      router.push(`/catalog/pending-imports/${r.data.pending_import_id}`);
    } catch (err) {
      setError(formatApiError(err, 'Upload failed'));
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }, [router]);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" aria-hidden="true" />
          <label htmlFor="parts-search" className="sr-only">Search catalog parts</label>
          <input
            id="parts-search"
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search part number, name, designation…"
            className="w-full rounded-lg border border-astra-border bg-astra-bg pl-8 pr-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
          />
        </div>
        <div>
          <label htmlFor="parts-class" className="sr-only">Part class</label>
          <select id="parts-class" value={partClass} onChange={(e) => setPartClass(e.target.value as PartClass | '')}
            className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-xs text-slate-200 outline-none focus:border-blue-500/50">
            <option value="">All classes</option>
            {PART_CLASSES.map((c) => <option key={c} value={c}>{PART_CLASS_LABELS[c]}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="parts-lifecycle" className="sr-only">Lifecycle</label>
          <select id="parts-lifecycle" value={lifecycle} onChange={(e) => setLifecycle(e.target.value as LifecycleStatus | '')}
            className="rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-xs text-slate-200 outline-none focus:border-blue-500/50">
            <option value="">Any lifecycle</option>
            {LIFECYCLE_STATUSES.map((s) => <option key={s} value={s}>{LIFECYCLE_COLORS[s].label}</option>)}
          </select>
        </div>
        <button
          type="button"
          onClick={refresh}
          aria-label="Refresh catalog parts"
          className="rounded-lg border border-astra-border p-2 text-slate-400 hover:border-blue-500/30 hover:text-slate-200"
        >
          <RefreshCw className={clsx('h-3.5 w-3.5', loading && 'animate-spin')} aria-hidden="true" />
        </button>
        {/* TDD-CAT-002 — Upload STEP button. Distinct from "New Part"
            (manual create) by the emerald accent. Clicking triggers the
            hidden file input below. */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".step,.stp,.STEP,.STP,model/step,application/STEP"
          onChange={onStepFileSelected}
          className="hidden"
          aria-hidden="true"
        />
        <button
          type="button"
          onClick={onPickStepFile}
          disabled={uploading}
          className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
        >
          {uploading
            ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            : <Upload className="h-3.5 w-3.5" aria-hidden="true" />}
          {uploading ? 'Parsing STEP…' : 'Upload STEP'}
        </button>
        <button
          type="button"
          onClick={() => router.push('/catalog/parts/new')}
          className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-500"
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" /> New Part
        </button>
      </div>

      {error && (
        <div role="alert" className="mb-3 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" /> {error}
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
        {loading && items.length === 0 ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="h-5 w-5 animate-spin text-blue-500" aria-label="Loading" />
          </div>
        ) : items.length === 0 ? (
          <div className="py-12 text-center text-sm text-slate-500">
            <Cpu className="h-8 w-8 mx-auto mb-2 text-slate-600" aria-hidden="true" />
            No catalog parts match. Click <strong className="text-slate-300">New Part</strong> to add one.
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead className="bg-astra-surface-alt text-slate-400">
              <tr>
                <th className="px-3 py-2 text-left font-semibold">WPN / Mfr P/N</th>
                <th className="px-3 py-2 text-left font-semibold">Name</th>
                <th className="px-3 py-2 text-left font-semibold">Supplier</th>
                <th className="px-3 py-2 text-left font-semibold">Class</th>
                <th className="px-3 py-2 text-left font-semibold">Lifecycle</th>
                <th className="px-3 py-2 text-right font-semibold">Used</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => {
                const lc = LIFECYCLE_COLORS[p.lifecycle_status];
                const wpn = p.internal_part_number;
                return (
                  <tr
                    key={p.id}
                    className="border-t border-astra-border hover:bg-astra-surface-alt cursor-pointer"
                    onClick={() => router.push(`/catalog/parts/${p.id}`)}
                  >
                    <td className="px-3 py-2 text-slate-200">
                      <div className="flex items-center gap-2">
                        <Cpu className="h-3.5 w-3.5 text-blue-400 flex-shrink-0" aria-hidden="true" />
                        {wpn ? (
                          <span className="font-mono font-bold tracking-wider text-slate-100">{wpn}</span>
                        ) : (
                          <span className="font-bold text-slate-200">{p.part_number}</span>
                        )}
                        {p.wpn_pending_sync && (
                          // Amber dot — fallback WPN that hasn't reconciled with HAROLD yet.
                          <span
                            title="WPN minted by fallback allocator; awaiting HAROLD sync"
                            aria-label="Pending HAROLD sync"
                            className="inline-block h-1.5 w-1.5 flex-shrink-0 rounded-full bg-amber-400"
                          />
                        )}
                      </div>
                      <div className="ml-5 text-[10px] text-slate-500">
                        {wpn ? <span className="font-mono">{p.part_number}</span> : null}
                        {wpn && p.revision ? ' · ' : ''}
                        {p.revision ? `rev ${p.revision}` : ''}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-slate-300">{p.name}</td>
                    <td className="px-3 py-2 text-slate-400">{p.supplier_name || '—'}</td>
                    <td className="px-3 py-2 text-slate-400">{PART_CLASS_LABELS[p.part_class]}</td>
                    <td className="px-3 py-2">
                      <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold" style={{ background: lc.bg, color: lc.text }}>
                        {lc.label}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right text-slate-300">{p.used_in_project_count}</td>
                    <td className="px-3 py-2 text-right text-slate-500">
                      <ChevronRight className="inline h-3.5 w-3.5" aria-hidden="true" />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  Pending Imports Tab (read-only in Phase 3)
// ══════════════════════════════════════

function PendingImportsTab() {
  const router = useRouter();
  const [items, setItems] = useState<PendingCatalogImport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    catalogAPI.listPendingImports({ limit: 200 })
      .then((r) => setItems(r.data))
      .catch((e) => setError(formatApiError(e, 'Failed to load pending imports')))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      {/* TDD-CAT-002: STEP ingestion is live, so the prior "Phase 7 preview"
          banner has been retired. ICD-PDF AI extraction is still the
          old Phase 7 path; that's surfaced via the existing per-document
          flow (POST /catalog/documents/{id}/extract). */}

      {error && (
        <div role="alert" className="mb-3 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" /> {error}
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
        {loading ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="h-5 w-5 animate-spin text-blue-500" aria-label="Loading" />
          </div>
        ) : items.length === 0 ? (
          <div className="py-12 text-center text-sm text-slate-500">
            <FileSearch2 className="h-8 w-8 mx-auto mb-2 text-slate-600" aria-hidden="true" />
            No pending imports. Drop a STEP file via the Parts tab to queue one.
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead className="bg-astra-surface-alt text-slate-400">
              <tr>
                <th className="px-3 py-2 text-left font-semibold">ID</th>
                <th className="px-3 py-2 text-left font-semibold">Source Document</th>
                <th className="px-3 py-2 text-left font-semibold">Supplier</th>
                <th className="px-3 py-2 text-left font-semibold">Status</th>
                <th className="px-3 py-2 text-left font-semibold">Confidence</th>
                <th className="px-3 py-2 text-left font-semibold">Created</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr
                  key={row.id}
                  onClick={() => router.push(`/catalog/pending-imports/${row.id}`)}
                  className="border-t border-astra-border hover:bg-astra-surface-alt cursor-pointer"
                >
                  <td className="px-3 py-2 font-mono text-slate-300">#{row.id}</td>
                  <td className="px-3 py-2 text-slate-300">doc {row.source_document_id}</td>
                  <td className="px-3 py-2 text-slate-300">supplier {row.supplier_id}</td>
                  <td className="px-3 py-2 text-slate-300">{PENDING_IMPORT_STATUS_LABELS[row.status]}</td>
                  <td className="px-3 py-2 text-slate-400">{row.extraction_confidence ?? '—'}</td>
                  <td className="px-3 py-2 text-slate-500">{new Date(row.created_at).toLocaleString()}</td>
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

// ══════════════════════════════════════
//  Page
// ══════════════════════════════════════

export default function CatalogLandingPage() {
  const [tab, setTab] = useState<Tab>('suppliers');

  const tabs: { key: Tab; label: string; icon: typeof Building2 }[] = useMemo(() => ([
    { key: 'suppliers', label: 'Suppliers',       icon: Building2 },
    { key: 'parts',     label: 'Parts',           icon: Cpu },
    { key: 'pending',   label: 'Pending Imports', icon: FileSearch2 },
  ]), []);

  return (
    <div>
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
            <Package className="h-6 w-6 text-blue-400" aria-hidden="true" />
            Supplier Catalog
          </h1>
          <p className="mt-1 text-sm text-slate-500 flex items-center gap-1.5">
            <Globe className="h-3.5 w-3.5" aria-hidden="true" />
            Global master data — visible to every project on this ASTRA instance.
          </p>
        </div>
      </div>

      <div role="tablist" aria-label="Catalog sections" className="mb-4 flex gap-1 border-b border-astra-border">
        {tabs.map(({ key, label, icon: Icon }) => {
          const active = tab === key;
          return (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={active}
              aria-controls={`catalog-panel-${key}`}
              id={`catalog-tab-${key}`}
              onClick={() => setTab(key)}
              className={clsx(
                'flex items-center gap-1.5 rounded-t-lg border-b-2 px-4 py-2 text-xs font-semibold transition',
                active
                  ? 'border-blue-400 text-blue-300'
                  : 'border-transparent text-slate-400 hover:text-slate-200',
              )}
            >
              <Icon className="h-3.5 w-3.5" aria-hidden="true" />
              {label}
            </button>
          );
        })}
      </div>

      <div id={`catalog-panel-${tab}`} role="tabpanel" aria-labelledby={`catalog-tab-${tab}`}>
        {tab === 'suppliers' && <SuppliersTab />}
        {tab === 'parts' && <PartsTab />}
        {tab === 'pending' && <PendingImportsTab />}
      </div>
    </div>
  );
}
