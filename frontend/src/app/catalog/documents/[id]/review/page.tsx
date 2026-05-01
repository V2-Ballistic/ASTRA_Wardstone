// ══════════════════════════════════════════════════════════════
//  ASTRA — ICD Pending Import Review
//  Side-by-side review for an extracted supplier document.
//
//  Path:   frontend/src/app/catalog/documents/[id]/review/page.tsx
//  Phase 7 — ASTRA-TDD-INTF-002
// ══════════════════════════════════════════════════════════════

'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  AlertTriangle, Check, ChevronLeft, Download, FileText, Loader2,
  Plug, RefreshCw, ShieldCheck, X,
} from 'lucide-react';
import { catalogAPI } from '@/lib/catalog-api';
import type {
  PendingCatalogImport, SupplierDocument,
} from '@/lib/catalog-types';

// ──────────────────────────────────────────────────────────────
//  Types — narrow on top of the JSON-blob extracted_data
// ──────────────────────────────────────────────────────────────

type ExtractedSupplier = {
  name: string;
  cage_code?: string | null;
  country?: string | null;
  source_page?: number | null;
};

type ExtractedPin = {
  pin_position: string;
  mfr_pin_name: string;
  mfr_signal_function?: string | null;
  mfr_signal_type?: string | null;
  mfr_direction?: string | null;
  mfr_voltage_min_v?: number | null;
  mfr_voltage_max_v?: number | null;
  mfr_current_max_ma?: number | null;
  mfr_impedance_ohm?: number | null;
  mfr_protocol_hint?: string | null;
  is_no_connect?: boolean;
  is_reserved?: boolean;
  is_chassis_ground?: boolean;
  notes?: string | null;
  source_page?: number | null;
};

type ExtractedConnector = {
  reference: string;
  description?: string | null;
  connector_type?: string | null;
  shell_size?: string | null;
  gender?: string | null;
  pin_count?: number;
  keying?: string | null;
  mating_part_number?: string | null;
  notes?: string | null;
  pins: ExtractedPin[];
  source_page?: number | null;
};

type ExtractedData = {
  supplier: ExtractedSupplier;
  part_number: string;
  revision?: string | null;
  name: string;
  designation?: string | null;
  description?: string | null;
  part_class: string;
  lru_classification?: string;
  // Physical
  mass_kg?: number | null;
  dim_length_mm?: number | null;
  dim_width_mm?: number | null;
  dim_height_mm?: number | null;
  // Power
  power_watts_nominal?: number | null;
  power_watts_peak?: number | null;
  voltage_input_min_v?: number | null;
  voltage_input_max_v?: number | null;
  // Environmental
  temp_operating_min_c?: number | null;
  temp_operating_max_c?: number | null;
  temp_storage_min_c?: number | null;
  temp_storage_max_c?: number | null;
  vibration_random_grms?: number | null;
  shock_mechanical_g?: number | null;
  humidity_max_pct?: number | null;
  altitude_max_m?: number | null;
  emi_ce102_limit_dbua?: number | null;
  emi_rs103_limit_vm?: number | null;
  esd_hbm_v?: number | null;
  // Compliance
  mil_std_810_tested?: boolean;
  mil_std_461_tested?: boolean;
  rohs_compliant?: boolean;
  itar_controlled?: boolean;
  export_classification?: string | null;
  // Lifecycle
  lifecycle_status?: string;
  eol_date?: string | null;
  // Children
  connectors: ExtractedConnector[];
  extraction_warnings?: string[];
  extraction_confidence?: number | null;
};

const BLANK_EXTRACTED: ExtractedData = {
  supplier: { name: '' },
  part_number: '',
  name: '',
  part_class: 'other',
  connectors: [],
};

// ──────────────────────────────────────────────────────────────
//  Page component
// ──────────────────────────────────────────────────────────────

export default function ReviewPendingImportPage() {
  const params = useParams<{ id: string }>();
  const docId = Number(params.id);
  const router = useRouter();

  const [document, setDocument] = useState<SupplierDocument | null>(null);
  const [pending, setPending] = useState<PendingCatalogImport | null>(null);
  const [data, setData] = useState<ExtractedData>(BLANK_EXTRACTED);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [rejectMode, setRejectMode] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [activeTab, setActiveTab] = useState<'supplier' | 'physical' | 'env' | 'connectors'>('supplier');

  // ── Initial load ──
  useEffect(() => {
    if (!Number.isFinite(docId)) return;
    let cancelled = false;
    setLoading(true);
    setError('');

    (async () => {
      try {
        const docResp = await catalogAPI.getDocument(docId);
        if (cancelled) return;
        setDocument(docResp.data);

        // Find the matching PENDING PendingCatalogImport for this document.
        const pendings = await catalogAPI.listPendingImports({ status: 'pending' });
        if (cancelled) return;
        const match = pendings.data.find((p) => p.source_document_id === docId);
        if (!match) {
          setError(
            `No pending import found for document ${docId}. Status is "${docResp.data.extraction_status}".`,
          );
          setLoading(false);
          return;
        }
        setPending(match);
        setData({ ...BLANK_EXTRACTED, ...(match.extracted_data as unknown as ExtractedData) });
        // PDF preview
        if (docResp.data.mime_type === 'application/pdf') {
          try {
            const blobResp = await catalogAPI.downloadDocumentFile(docId);
            if (!cancelled) {
              const url = URL.createObjectURL(blobResp.data as Blob);
              setPreviewUrl(url);
            }
          } catch {
            // Preview failure is non-fatal — the form still works.
          }
        }
      } catch (e) {
        const ax = e as { response?: { data?: { detail?: string } }; message?: string };
        if (!cancelled) setError(ax?.response?.data?.detail || ax?.message || 'Failed to load review');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [docId]);

  // ── Cleanup blob URL ──
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  // ── Save edits back to the pending row ──
  const handleSave = useCallback(async () => {
    if (!pending) return;
    setSaving(true);
    setError('');
    setInfo('');
    try {
      const resp = await catalogAPI.updatePendingImport(pending.id, {
        extracted_data: data as unknown as Record<string, unknown>,
      });
      setPending(resp.data);
      setInfo('Edits saved');
      setTimeout(() => setInfo(''), 3000);
    } catch (e) {
      const ax = e as { response?: { data?: { detail?: string } } };
      setError(ax?.response?.data?.detail || 'Save failed');
    } finally {
      setSaving(false);
    }
  }, [pending, data]);

  // ── Approve ──
  const handleApprove = useCallback(async () => {
    if (!pending) return;
    setSubmitting(true);
    setError('');
    try {
      // Always save edits first so the approve uses the latest data.
      await catalogAPI.updatePendingImport(pending.id, {
        extracted_data: data as unknown as Record<string, unknown>,
      });
      const resp = await catalogAPI.approvePendingImport(pending.id);
      router.push(`/catalog/parts/${resp.data.id}`);
    } catch (e) {
      const ax = e as { response?: { data?: { detail?: string } } };
      setError(ax?.response?.data?.detail || 'Approval failed');
      setSubmitting(false);
    }
  }, [pending, data, router]);

  // ── Reject ──
  const handleReject = useCallback(async () => {
    if (!pending) return;
    setSubmitting(true);
    setError('');
    try {
      await catalogAPI.rejectPendingImport(pending.id, rejectReason || undefined);
      router.push('/catalog');
    } catch (e) {
      const ax = e as { response?: { data?: { detail?: string } } };
      setError(ax?.response?.data?.detail || 'Rejection failed');
      setSubmitting(false);
    }
  }, [pending, rejectReason, router]);

  // ── Form helpers ──
  const updateField = useCallback(<K extends keyof ExtractedData>(field: K, value: ExtractedData[K]) => {
    setData((prev) => ({ ...prev, [field]: value }));
  }, []);

  const updateSupplier = useCallback(<K extends keyof ExtractedSupplier>(field: K, value: ExtractedSupplier[K]) => {
    setData((prev) => ({ ...prev, supplier: { ...prev.supplier, [field]: value } }));
  }, []);

  const updateConnector = useCallback((idx: number, patch: Partial<ExtractedConnector>) => {
    setData((prev) => {
      const next = [...prev.connectors];
      next[idx] = { ...next[idx], ...patch };
      return { ...prev, connectors: next };
    });
  }, []);

  const updatePin = useCallback((cIdx: number, pIdx: number, patch: Partial<ExtractedPin>) => {
    setData((prev) => {
      const conns = [...prev.connectors];
      const pins = [...conns[cIdx].pins];
      pins[pIdx] = { ...pins[pIdx], ...patch };
      conns[cIdx] = { ...conns[cIdx], pins };
      return { ...prev, connectors: conns };
    });
  }, []);

  const warnings = useMemo<string[]>(() => {
    const fromPending = pending?.extraction_warnings as { warnings?: string[] } | null | undefined;
    return fromPending?.warnings || data.extraction_warnings || [];
  }, [pending, data.extraction_warnings]);

  const confidence = useMemo(() => {
    if (data.extraction_confidence != null) return data.extraction_confidence;
    if (pending?.extraction_confidence) return Number(pending.extraction_confidence);
    return null;
  }, [data, pending]);

  if (!Number.isFinite(docId)) {
    return <CenterMessage tone="error">Invalid document id</CenterMessage>;
  }
  if (loading) {
    return <CenterMessage tone="info"><Loader2 className="inline h-4 w-4 animate-spin" /> Loading review</CenterMessage>;
  }
  if (error && !pending) {
    return <CenterMessage tone="error">{error}</CenterMessage>;
  }
  if (!pending || !document) {
    return <CenterMessage tone="error">Pending import not available</CenterMessage>;
  }

  return (
    <div className="min-h-screen bg-astra-bg pb-12">
      {/* Header */}
      <header className="border-b border-astra-border bg-astra-surface px-6 py-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <Link href="/catalog" className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-blue-300">
              <ChevronLeft className="h-3 w-3" /> Back to Catalog
            </Link>
            <h1 className="mt-1 text-lg font-bold text-slate-100">Review extracted ICD</h1>
            <p className="mt-0.5 text-xs text-slate-500">
              {document.title} • SHA {document.sha256.slice(0, 12)}…
              {document.page_count ? ` • ${document.page_count} pages` : ''}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {confidence != null && (
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-bold ${
                  confidence >= 0.85
                    ? 'bg-emerald-500/15 text-emerald-300'
                    : confidence >= 0.6
                      ? 'bg-amber-500/15 text-amber-300'
                      : 'bg-rose-500/15 text-rose-300'
                }`}
                title="Self-assessed extraction confidence"
              >
                <ShieldCheck className="h-3 w-3" /> {(confidence * 100).toFixed(0)}%
              </span>
            )}
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="inline-flex items-center gap-1 rounded-lg border border-astra-border px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-astra-surface-alt disabled:opacity-50"
            >
              {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
              Save edits
            </button>
            <button
              type="button"
              onClick={() => setRejectMode((v) => !v)}
              className="inline-flex items-center gap-1 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-xs font-semibold text-rose-300 hover:bg-rose-500/20"
            >
              <X className="h-3 w-3" /> Reject
            </button>
            <button
              type="button"
              onClick={handleApprove}
              disabled={submitting}
              className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
            >
              {submitting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
              Approve & commit
            </button>
          </div>
        </div>
        {info && <div className="mt-2 inline-flex items-center gap-1 rounded bg-emerald-500/10 px-2 py-1 text-[11px] text-emerald-300"><Check className="h-3 w-3" /> {info}</div>}
        {error && <div className="mt-2 inline-flex items-center gap-1 rounded bg-rose-500/10 px-2 py-1 text-[11px] text-rose-300"><AlertTriangle className="h-3 w-3" /> {error}</div>}
        {warnings.length > 0 && (
          <details className="mt-2 group">
            <summary className="cursor-pointer text-[11px] text-amber-300/90 hover:text-amber-200">
              <AlertTriangle className="inline h-3 w-3" /> {warnings.length} extraction warning{warnings.length === 1 ? '' : 's'}
            </summary>
            <ul className="mt-1 ml-4 list-disc space-y-0.5 text-[11px] text-amber-200/80">
              {warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          </details>
        )}
      </header>

      {rejectMode && (
        <div className="bg-rose-950/30 border-b border-rose-500/30 px-6 py-3">
          <div className="flex items-center gap-3">
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Reason for rejection (optional, recorded in audit log)"
              rows={2}
              className="flex-1 rounded-lg border border-rose-500/40 bg-astra-bg px-3 py-2 text-xs text-slate-200 outline-none focus:border-rose-400"
            />
            <button
              type="button"
              onClick={handleReject}
              disabled={submitting}
              className="rounded-lg bg-rose-600 px-3 py-2 text-xs font-bold text-white hover:bg-rose-500 disabled:opacity-50"
            >
              {submitting ? <Loader2 className="inline h-3 w-3 animate-spin" /> : null} Confirm Reject
            </button>
            <button
              type="button"
              onClick={() => setRejectMode(false)}
              className="rounded-lg border border-astra-border px-3 py-2 text-xs text-slate-400 hover:text-slate-200"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Side-by-side: preview (left) | extracted form (right) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 p-4">
        {/* Document preview */}
        <section className="rounded-xl border border-astra-border bg-astra-surface overflow-hidden lg:sticky lg:top-4 lg:self-start lg:max-h-[calc(100vh-2rem)]">
          <div className="flex items-center justify-between border-b border-astra-border px-4 py-2">
            <h2 className="text-xs font-bold text-slate-200 inline-flex items-center gap-1.5">
              <FileText className="h-3.5 w-3.5" /> Original document
            </h2>
            <a
              href={`/api/v1/catalog/documents/${docId}/file`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-[11px] text-blue-300 hover:underline"
            >
              <Download className="h-3 w-3" /> Download
            </a>
          </div>
          <div className="h-[calc(100vh-9rem)] min-h-[400px] bg-black/30">
            {previewUrl ? (
              <iframe
                src={previewUrl}
                title="Document preview"
                className="w-full h-full"
              />
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-center px-6">
                <FileText className="h-8 w-8 text-slate-500" />
                <p className="text-sm text-slate-400">
                  Preview not available for {document.mime_type}
                </p>
                <p className="text-xs text-slate-500">Use the Download link above to view the original.</p>
              </div>
            )}
          </div>
        </section>

        {/* Extracted form */}
        <section className="rounded-xl border border-astra-border bg-astra-surface">
          {/* Tab nav */}
          <div role="tablist" aria-label="Extracted sections" className="flex gap-1 border-b border-astra-border px-4 pt-2">
            {(['supplier', 'physical', 'env', 'connectors'] as const).map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={activeTab === t}
                type="button"
                onClick={() => setActiveTab(t)}
                className={`rounded-t-lg border-b-2 px-3 py-1.5 text-xs font-semibold transition ${
                  activeTab === t
                    ? 'border-blue-400 text-blue-300'
                    : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                {t === 'supplier' ? 'Supplier & Part'
                  : t === 'physical' ? 'Physical & Power'
                  : t === 'env' ? 'Environmental'
                  : `Connectors (${data.connectors.length})`}
              </button>
            ))}
          </div>

          {/* Tab body */}
          <div className="p-4 space-y-3">
            {activeTab === 'supplier' && (
              <SupplierTab
                data={data}
                onUpdate={updateField}
                onUpdateSupplier={updateSupplier}
              />
            )}
            {activeTab === 'physical' && (
              <PhysicalTab data={data} onUpdate={updateField} />
            )}
            {activeTab === 'env' && (
              <EnvTab data={data} onUpdate={updateField} />
            )}
            {activeTab === 'connectors' && (
              <ConnectorsTab
                connectors={data.connectors}
                onUpdateConnector={updateConnector}
                onUpdatePin={updatePin}
              />
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
//  Tab components
// ──────────────────────────────────────────────────────────────

type FieldUpdater = <K extends keyof ExtractedData>(field: K, value: ExtractedData[K]) => void;
type SupplierUpdater = <K extends keyof ExtractedSupplier>(field: K, value: ExtractedSupplier[K]) => void;

function SupplierTab({
  data, onUpdate, onUpdateSupplier,
}: {
  data: ExtractedData;
  onUpdate: FieldUpdater;
  onUpdateSupplier: SupplierUpdater;
}) {
  return (
    <>
      <Section title="Supplier">
        <Row>
          <Field label="Name (required)">
            <input value={data.supplier.name || ''} onChange={(e) => onUpdateSupplier('name', e.target.value)} className={inputCls} />
          </Field>
          <Field label="CAGE Code">
            <input value={data.supplier.cage_code || ''} onChange={(e) => onUpdateSupplier('cage_code', e.target.value)} className={inputCls} />
          </Field>
          <Field label="Country">
            <input value={data.supplier.country || ''} onChange={(e) => onUpdateSupplier('country', e.target.value)} className={inputCls} />
          </Field>
        </Row>
      </Section>

      <Section title="Part identity">
        <Row>
          <Field label="Part Number (required)">
            <input value={data.part_number} onChange={(e) => onUpdate('part_number', e.target.value)} className={inputCls} />
          </Field>
          <Field label="Revision">
            <input value={data.revision || ''} onChange={(e) => onUpdate('revision', e.target.value)} className={inputCls} />
          </Field>
        </Row>
        <Row>
          <Field label="Name (required)" wide>
            <input value={data.name} onChange={(e) => onUpdate('name', e.target.value)} className={inputCls} />
          </Field>
          <Field label="Designation">
            <input value={data.designation || ''} onChange={(e) => onUpdate('designation', e.target.value)} className={inputCls} />
          </Field>
        </Row>
        <Row>
          <Field label="Part Class">
            <select value={data.part_class} onChange={(e) => onUpdate('part_class', e.target.value)} className={inputCls}>
              {['processor','sensor','power_supply','radio','antenna','actuator','display',
                'harness','connector_only','compute_module','power_distribution',
                'interface_card','other'].map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </Field>
          <Field label="LRU Class">
            <select value={data.lru_classification || 'lru'} onChange={(e) => onUpdate('lru_classification', e.target.value)} className={inputCls}>
              {['lru','sru','wra','subassembly','component'].map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </Field>
          <Field label="Lifecycle">
            <select value={data.lifecycle_status || 'active'} onChange={(e) => onUpdate('lifecycle_status', e.target.value)} className={inputCls}>
              {['active','preferred','obsolete','eol_announced','nrnd','restricted'].map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </Field>
        </Row>
        <Field label="Description" wide>
          <textarea value={data.description || ''} onChange={(e) => onUpdate('description', e.target.value)} rows={3} className={inputCls} />
        </Field>
      </Section>
    </>
  );
}

function PhysicalTab({ data, onUpdate }: { data: ExtractedData; onUpdate: FieldUpdater }) {
  return (
    <>
      <Section title="Physical">
        <Row>
          <NumField label="Mass (kg)" value={data.mass_kg} onChange={(v) => onUpdate('mass_kg', v)} />
          <NumField label="Length (mm)" value={data.dim_length_mm} onChange={(v) => onUpdate('dim_length_mm', v)} />
          <NumField label="Width (mm)" value={data.dim_width_mm} onChange={(v) => onUpdate('dim_width_mm', v)} />
          <NumField label="Height (mm)" value={data.dim_height_mm} onChange={(v) => onUpdate('dim_height_mm', v)} />
        </Row>
      </Section>
      <Section title="Power">
        <Row>
          <NumField label="Nominal (W)" value={data.power_watts_nominal} onChange={(v) => onUpdate('power_watts_nominal', v)} />
          <NumField label="Peak (W)" value={data.power_watts_peak} onChange={(v) => onUpdate('power_watts_peak', v)} />
          <NumField label="Vin Min (V)" value={data.voltage_input_min_v} onChange={(v) => onUpdate('voltage_input_min_v', v)} />
          <NumField label="Vin Max (V)" value={data.voltage_input_max_v} onChange={(v) => onUpdate('voltage_input_max_v', v)} />
        </Row>
      </Section>
      <Section title="Compliance">
        <Row>
          <BoolField label="MIL-STD-810" value={data.mil_std_810_tested} onChange={(v) => onUpdate('mil_std_810_tested', v)} />
          <BoolField label="MIL-STD-461" value={data.mil_std_461_tested} onChange={(v) => onUpdate('mil_std_461_tested', v)} />
          <BoolField label="RoHS" value={data.rohs_compliant} onChange={(v) => onUpdate('rohs_compliant', v)} />
          <BoolField label="ITAR" value={data.itar_controlled} onChange={(v) => onUpdate('itar_controlled', v)} />
        </Row>
        <Field label="Export Classification">
          <input value={data.export_classification || ''} onChange={(e) => onUpdate('export_classification', e.target.value)} className={inputCls} />
        </Field>
      </Section>
    </>
  );
}

function EnvTab({ data, onUpdate }: { data: ExtractedData; onUpdate: FieldUpdater }) {
  return (
    <>
      <Section title="Temperature">
        <Row>
          <NumField label="Op Min (°C)" value={data.temp_operating_min_c} onChange={(v) => onUpdate('temp_operating_min_c', v)} />
          <NumField label="Op Max (°C)" value={data.temp_operating_max_c} onChange={(v) => onUpdate('temp_operating_max_c', v)} />
          <NumField label="Storage Min (°C)" value={data.temp_storage_min_c} onChange={(v) => onUpdate('temp_storage_min_c', v)} />
          <NumField label="Storage Max (°C)" value={data.temp_storage_max_c} onChange={(v) => onUpdate('temp_storage_max_c', v)} />
        </Row>
      </Section>
      <Section title="Mechanical">
        <Row>
          <NumField label="Vibration (g rms)" value={data.vibration_random_grms} onChange={(v) => onUpdate('vibration_random_grms', v)} />
          <NumField label="Shock (g)" value={data.shock_mechanical_g} onChange={(v) => onUpdate('shock_mechanical_g', v)} />
          <NumField label="Humidity Max (%)" value={data.humidity_max_pct} onChange={(v) => onUpdate('humidity_max_pct', v)} />
          <NumField label="Altitude Max (m)" value={data.altitude_max_m} onChange={(v) => onUpdate('altitude_max_m', v)} />
        </Row>
      </Section>
      <Section title="EMI / ESD">
        <Row>
          <NumField label="CE102 (dBuA)" value={data.emi_ce102_limit_dbua} onChange={(v) => onUpdate('emi_ce102_limit_dbua', v)} />
          <NumField label="RS103 (V/m)" value={data.emi_rs103_limit_vm} onChange={(v) => onUpdate('emi_rs103_limit_vm', v)} />
          <NumField label="ESD HBM (V)" value={data.esd_hbm_v} onChange={(v) => onUpdate('esd_hbm_v', v)} />
        </Row>
      </Section>
    </>
  );
}

function ConnectorsTab({
  connectors, onUpdateConnector, onUpdatePin,
}: {
  connectors: ExtractedConnector[];
  onUpdateConnector: (idx: number, patch: Partial<ExtractedConnector>) => void;
  onUpdatePin: (cIdx: number, pIdx: number, patch: Partial<ExtractedPin>) => void;
}) {
  if (connectors.length === 0) {
    return <p className="text-xs text-slate-500">No connectors extracted.</p>;
  }
  return (
    <div className="space-y-4">
      {connectors.map((conn, cIdx) => (
        <details key={cIdx} className="rounded-lg border border-astra-border bg-astra-surface-alt" open={cIdx === 0}>
          <summary className="cursor-pointer px-3 py-2 text-xs font-semibold text-slate-200 inline-flex items-center gap-2">
            <Plug className="h-3.5 w-3.5 text-blue-300" /> {conn.reference || `Connector ${cIdx + 1}`}
            <span className="ml-2 text-[11px] text-slate-500">{conn.pins.length} pins</span>
          </summary>
          <div className="border-t border-astra-border p-3 space-y-3">
            <Row>
              <Field label="Reference">
                <input value={conn.reference} onChange={(e) => onUpdateConnector(cIdx, { reference: e.target.value })} className={inputCls} />
              </Field>
              <Field label="Type">
                <input value={conn.connector_type || ''} onChange={(e) => onUpdateConnector(cIdx, { connector_type: e.target.value })} className={inputCls} />
              </Field>
              <Field label="Shell">
                <input value={conn.shell_size || ''} onChange={(e) => onUpdateConnector(cIdx, { shell_size: e.target.value })} className={inputCls} />
              </Field>
              <Field label="Gender">
                <select value={conn.gender || ''} onChange={(e) => onUpdateConnector(cIdx, { gender: e.target.value || null })} className={inputCls}>
                  <option value="">—</option>
                  {['male', 'female', 'hermaphroditic', 'unknown'].map((g) => <option key={g}>{g}</option>)}
                </select>
              </Field>
            </Row>
            <Row>
              <Field label="Description" wide>
                <input value={conn.description || ''} onChange={(e) => onUpdateConnector(cIdx, { description: e.target.value })} className={inputCls} />
              </Field>
            </Row>
            {/* Pin table */}
            <div className="overflow-x-auto rounded-lg border border-astra-border">
              <table className="w-full text-[11px]">
                <thead className="bg-astra-bg/50 text-slate-400">
                  <tr>
                    <th className="px-2 py-1.5 text-left">Pos</th>
                    <th className="px-2 py-1.5 text-left">Mfr Name</th>
                    <th className="px-2 py-1.5 text-left">Function</th>
                    <th className="px-2 py-1.5 text-left">Type</th>
                    <th className="px-2 py-1.5 text-left">Dir</th>
                    <th className="px-2 py-1.5 text-right">Vmin</th>
                    <th className="px-2 py-1.5 text-right">Vmax</th>
                  </tr>
                </thead>
                <tbody>
                  {conn.pins.map((pin, pIdx) => (
                    <tr key={pIdx} className="border-t border-astra-border/40">
                      <td className="px-2 py-1"><input value={pin.pin_position} onChange={(e) => onUpdatePin(cIdx, pIdx, { pin_position: e.target.value })} className={inputCellCls + ' w-12'} /></td>
                      <td className="px-2 py-1"><input value={pin.mfr_pin_name} onChange={(e) => onUpdatePin(cIdx, pIdx, { mfr_pin_name: e.target.value })} className={inputCellCls + ' w-28'} /></td>
                      <td className="px-2 py-1"><input value={pin.mfr_signal_function || ''} onChange={(e) => onUpdatePin(cIdx, pIdx, { mfr_signal_function: e.target.value })} className={inputCellCls} /></td>
                      <td className="px-2 py-1">
                        <select value={pin.mfr_signal_type || ''} onChange={(e) => onUpdatePin(cIdx, pIdx, { mfr_signal_type: e.target.value || null })} className={inputCellCls}>
                          <option value="">—</option>
                          {['power','ground','digital','analog','diff_pair','rf','discrete','no_connect','reserved','unknown'].map((v) => <option key={v}>{v}</option>)}
                        </select>
                      </td>
                      <td className="px-2 py-1">
                        <select value={pin.mfr_direction || ''} onChange={(e) => onUpdatePin(cIdx, pIdx, { mfr_direction: e.target.value || null })} className={inputCellCls}>
                          <option value="">—</option>
                          {['input','output','bidirectional','power','ground','unknown'].map((v) => <option key={v}>{v}</option>)}
                        </select>
                      </td>
                      <td className="px-2 py-1"><input type="number" step="0.01" value={pin.mfr_voltage_min_v ?? ''} onChange={(e) => onUpdatePin(cIdx, pIdx, { mfr_voltage_min_v: e.target.value === '' ? null : Number(e.target.value) })} className={inputCellCls + ' w-16 text-right'} /></td>
                      <td className="px-2 py-1"><input type="number" step="0.01" value={pin.mfr_voltage_max_v ?? ''} onChange={(e) => onUpdatePin(cIdx, pIdx, { mfr_voltage_max_v: e.target.value === '' ? null : Number(e.target.value) })} className={inputCellCls + ' w-16 text-right'} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </details>
      ))}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
//  Layout primitives
// ──────────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-astra-border/60 bg-astra-bg/30 p-3">
      <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wide text-slate-400">{title}</h3>
      <div className="space-y-2">{children}</div>
    </div>
  );
}
function Row({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-wrap gap-2">{children}</div>;
}
function Field({ label, children, wide }: { label: string; children: React.ReactNode; wide?: boolean }) {
  return (
    <label className={`flex flex-col gap-1 ${wide ? 'flex-1 min-w-[200px]' : 'min-w-[120px]'}`}>
      <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</span>
      {children}
    </label>
  );
}
function NumField({ label, value, onChange }: { label: string; value: number | null | undefined; onChange: (v: number | null) => void }) {
  return (
    <Field label={label}>
      <input
        type="number"
        step="0.01"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
        className={inputCls}
      />
    </Field>
  );
}
function BoolField({ label, value, onChange }: { label: string; value: boolean | undefined; onChange: (v: boolean) => void }) {
  return (
    <label className="inline-flex items-center gap-2 text-xs text-slate-300">
      <input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} className="rounded border-astra-border bg-astra-bg" />
      {label}
    </label>
  );
}

const inputCls = 'w-full rounded-md border border-astra-border bg-astra-bg px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-blue-500/50';
const inputCellCls = 'rounded border border-transparent bg-transparent px-1 py-0.5 text-[11px] text-slate-200 outline-none focus:border-blue-500/50 focus:bg-astra-bg';

function CenterMessage({ children, tone }: { children: React.ReactNode; tone: 'info' | 'error' }) {
  return (
    <div className="flex h-screen items-center justify-center bg-astra-bg">
      <div className={`rounded-lg border px-6 py-4 text-sm ${tone === 'error' ? 'border-rose-500/30 bg-rose-500/10 text-rose-300' : 'border-astra-border bg-astra-surface text-slate-300'}`}>
        {children}
      </div>
    </div>
  );
}
