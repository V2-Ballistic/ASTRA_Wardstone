'use client';

/**
 * ASTRA — Interface Module Import Wizard
 * ==========================================
 * File: frontend/src/app/projects/[id]/interfaces/import/page.tsx
 * Path: C:\Users\Mason\Documents\ASTRA\frontend\src\app\projects\[id]\interfaces\import\page.tsx
 *
 * Four-step wizard for bulk-importing interface data from Excel:
 *   1. Upload    — download styled .xlsx template, drag/drop or browse to upload
 *   2. Preview   — summary + per-sheet row inspection with errors/warnings
 *   3. Importing — progress during server-side entity creation
 *   4. Done      — summary of what was created with "View Interfaces" action
 *
 * Backend endpoints (already implemented in backend/app/routers/interface_import.py):
 *   POST /api/v1/interfaces/io/import/template → blob
 *   POST /api/v1/interfaces/io/import/preview  → ImportPreviewResponse
 *   POST /api/v1/interfaces/io/import/confirm  → ImportConfirmResponse
 */

import { useState, useCallback, useRef, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  Upload, Loader2, CheckCircle, XCircle, AlertTriangle,
  Download, ChevronRight, X, Check, FileSpreadsheet, ArrowLeft,
  Cable, Cpu, Radio, MessageSquare, Zap, Pin as PinIcon,
  Info,
} from 'lucide-react';
import clsx from 'clsx';
import { interfaceAPI, downloadBlob } from '@/lib/interface-api';
import type { ImportPreviewResponse, ImportConfirmResponse } from '@/lib/interface-types';
import { labelize } from '@/lib/interface-types';

type Step = 'upload' | 'preview' | 'importing' | 'done';
type SheetKey = 'units' | 'connectors' | 'pins' | 'buses' | 'messages' | 'fields';

interface RowPreview {
  row: number;
  valid: boolean;
  errors: string[];
  warnings: string[];
  data: Record<string, any>;
}

const SHEET_META: Record<SheetKey, { label: string; icon: any; color: string; description: string }> = {
  units:      { label: 'Units',      icon: Cpu,           color: '#3B82F6', description: 'Line-replaceable units, sensors, processors, actuators' },
  connectors: { label: 'Connectors', icon: Cable,         color: '#10B981', description: 'Physical connectors with shell and keying data' },
  pins:       { label: 'Pins',       icon: PinIcon,       color: '#F59E0B', description: 'Contact-level pin definitions with signals and electrical specs' },
  buses:      { label: 'Buses',      icon: Radio,         color: '#8B5CF6', description: 'Communication buses (MIL-STD-1553, Ethernet, I²C, etc.)' },
  messages:   { label: 'Messages',   icon: MessageSquare, color: '#EC4899', description: 'Bus messages with scheduling and priority' },
  fields:     { label: 'Fields',     icon: Zap,           color: '#06B6D4', description: 'Message payload fields (byte layout)' },
};

// ══════════════════════════════════════
//  Small presentational helpers
// ══════════════════════════════════════

function StatPill({ label, value, color = '#3B82F6' }: { label: string; value: number | string; color?: string }) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-astra-border bg-astra-surface px-5 py-3">
      <span className="text-[10px] uppercase tracking-wider text-slate-500">{label}</span>
      <span className="mt-0.5 text-2xl font-bold" style={{ color }}>{value}</span>
    </div>
  );
}

function StepMarker({ n, label, active, done }: { n: number; label: string; active?: boolean; done?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <div className={clsx(
        'flex h-7 w-7 items-center justify-center rounded-full border text-[11px] font-bold',
        active && 'border-blue-500 bg-blue-500/15 text-blue-400',
        done   && 'border-emerald-500/60 bg-emerald-500/15 text-emerald-400',
        !active && !done && 'border-astra-border bg-astra-surface text-slate-600'
      )}>
        {done ? <Check className="h-3.5 w-3.5" /> : n}
      </div>
      <span className={clsx(
        'text-[11px] font-semibold uppercase tracking-wider',
        active ? 'text-slate-200' : done ? 'text-emerald-400' : 'text-slate-600'
      )}>
        {label}
      </span>
    </div>
  );
}

// ══════════════════════════════════════
//  Main Page
// ══════════════════════════════════════

export default function InterfaceImportPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);
  const p = `/projects/${projectId}`;
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [step, setStep] = useState<Step>('upload');
  const [uploading, setUploading] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [result, setResult] = useState<ImportConfirmResponse | null>(null);
  const [error, setError] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [activeSheet, setActiveSheet] = useState<SheetKey>('units');
  // F-099: progress state removed — was driven by a fake setInterval
  // tick. Spinner now carries the "work in progress" affordance.

  // ── Upload handler ──
  const handleFile = useCallback(async (file: File) => {
    const ext = file.name.split('.').pop()?.toLowerCase();
    if (!ext || !['xlsx', 'xls'].includes(ext)) {
      setError('Unsupported file type. Use the ASTRA template (.xlsx)');
      return;
    }

    setUploading(true);
    setError('');
    setUploadedFile(file);

    try {
      const res = await interfaceAPI.importPreview(file);
      setPreview(res.data);
      // Default to the first non-empty sheet
      const first = (Object.keys(SHEET_META) as SheetKey[]).find(k => (res.data as any)[k]?.length);
      if (first) setActiveSheet(first);
      setStep('preview');
    } catch (e: any) {
      const detail = e.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Failed to parse file. Check the template format.');
      setUploadedFile(null);
    }
    setUploading(false);
  }, []);

  // ── Drag & drop ──
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setDragOver(true); };
  const handleDragLeave = () => setDragOver(false);

  // ── Download template ──
  const handleDownloadTemplate = async () => {
    try {
      const res = await interfaceAPI.downloadTemplate();
      downloadBlob(res, 'astra_interface_template.xlsx');
    } catch {
      setError('Failed to download template');
    }
  };

  // ── Confirm import ──
  const handleConfirm = async () => {
    if (!uploadedFile) return;
    setStep('importing');
    setError('');
    // F-099: pre-fix this set up a setInterval that crept the
    // progress bar by 3% every 120ms toward 90% — fake progress, no
    // signal from the server. Two issues: (a) the bar lied (it
    // implied ETA the import flow doesn't expose), and (b) on a
    // throw the interval was cleared AFTER the catch updated state,
    // so the bar could continue ticking briefly during error handling
    // depending on event loop order. Replaced with a plain spinner
    // + indeterminate-feeling wide bar; no setInterval to leak.
    try {
      const res = await interfaceAPI.importConfirm(projectId, uploadedFile);
      setResult(res.data);
      setStep('done');
    } catch (e: any) {
      const detail = e.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Import failed');
      setStep('preview');
    }
  };

  const handleReset = () => {
    setStep('upload');
    setPreview(null);
    setResult(null);
    setUploadedFile(null);
    setError('');
  };

  // ── Counts ──
  const counts = useMemo(() => {
    if (!preview) return null;
    const c: Record<SheetKey, { total: number; valid: number; errors: number }> = {
      units: { total: 0, valid: 0, errors: 0 },
      connectors: { total: 0, valid: 0, errors: 0 },
      pins: { total: 0, valid: 0, errors: 0 },
      buses: { total: 0, valid: 0, errors: 0 },
      messages: { total: 0, valid: 0, errors: 0 },
      fields: { total: 0, valid: 0, errors: 0 },
    };
    (Object.keys(SHEET_META) as SheetKey[]).forEach(k => {
      const rows = (preview as any)[k] as RowPreview[] | undefined;
      if (!rows) return;
      c[k].total = rows.length;
      c[k].valid = rows.filter(r => r.valid).length;
      c[k].errors = rows.filter(r => !r.valid).length;
    });
    return c;
  }, [preview]);

  const hasBlockingErrors = useMemo(() => {
    if (!counts) return false;
    // Block if any of the core sheets (units, connectors, pins) have errors
    return counts.units.errors > 0 || counts.connectors.errors > 0 || counts.pins.errors > 0;
  }, [counts]);

  const activeRows = useMemo<RowPreview[]>(() => {
    if (!preview) return [];
    return ((preview as any)[activeSheet] as RowPreview[]) || [];
  }, [preview, activeSheet]);

  // ══════════════════════════════════════
  //  Render
  // ══════════════════════════════════════

  return (
    <div className="mx-auto max-w-6xl">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <button onClick={() => router.push(`${p}/interfaces`)}
            className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold text-slate-500 transition hover:text-slate-300">
            <ArrowLeft className="h-3 w-3" /> Back to Interfaces
          </button>
          <h1 className="text-xl font-bold tracking-tight text-slate-100">Import from Excel</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            Bulk-import units, connectors, pins, buses, and messages from a styled template
          </p>
        </div>
        {step !== 'upload' && (
          <button onClick={handleReset}
            className="flex items-center gap-1.5 rounded-lg border border-astra-border bg-astra-surface px-3 py-2 text-xs font-semibold text-slate-400 transition hover:border-red-500/30 hover:text-red-400">
            <X className="h-3.5 w-3.5" /> Start Over
          </button>
        )}
      </div>

      {/* Stepper */}
      <div className="mb-6 flex items-center gap-4 rounded-xl border border-astra-border bg-astra-surface px-5 py-3">
        <StepMarker n={1} label="Upload"    active={step === 'upload'}    done={step !== 'upload'} />
        <ChevronRight className="h-3.5 w-3.5 text-slate-700" />
        <StepMarker n={2} label="Preview"   active={step === 'preview'}   done={step === 'importing' || step === 'done'} />
        <ChevronRight className="h-3.5 w-3.5 text-slate-700" />
        <StepMarker n={3} label="Importing" active={step === 'importing'} done={step === 'done'} />
        <ChevronRight className="h-3.5 w-3.5 text-slate-700" />
        <StepMarker n={4} label="Done"      active={step === 'done'} />
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-4 flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
          <button onClick={() => setError('')} className="ml-auto text-red-400/70 hover:text-red-400">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* ═══════════════════════════════════
          STEP 1 — UPLOAD
          ═══════════════════════════════════ */}
      {step === 'upload' && (
        <div className="space-y-6">
          {/* Instructions */}
          <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 p-5">
            <div className="flex items-start gap-3">
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-blue-400" />
              <div>
                <h3 className="mb-1 text-sm font-bold text-slate-200">How this works</h3>
                <ol className="space-y-1 text-[13px] text-slate-400">
                  <li>
                    <span className="font-semibold text-slate-300">1.</span> Download the ASTRA template
                    (4 styled sheets: <span className="text-slate-300">Units · Connectors · Buses · Messages</span>)
                  </li>
                  <li><span className="font-semibold text-slate-300">2.</span> Fill it out — each row is one entity, paste in bulk, use the dropdowns for enums</li>
                  <li><span className="font-semibold text-slate-300">3.</span> Drop the file below — you&apos;ll get a preview with errors/warnings before anything is created</li>
                  <li><span className="font-semibold text-slate-300">4.</span> Confirm the import to apply everything in one atomic transaction</li>
                </ol>
              </div>
            </div>
          </div>

          {/* Download template */}
          <div className="flex items-center justify-between rounded-xl border border-astra-border bg-astra-surface p-5">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-400">
                <FileSpreadsheet className="h-5 w-5" />
              </div>
              <div>
                <div className="text-sm font-bold text-slate-200">Step 1 — Get the template</div>
                <div className="text-[11px] text-slate-500">
                  Pre-styled .xlsx with example rows, required-column highlighting, and dropdown validation
                </div>
              </div>
            </div>
            <button onClick={handleDownloadTemplate}
              className="flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-xs font-bold text-emerald-400 transition hover:bg-emerald-500/20">
              <Download className="h-3.5 w-3.5" />
              Download Template
            </button>
          </div>

          {/* Drop zone */}
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Step 2 — Upload completed template
          </div>
          <div
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            className={clsx(
              'rounded-2xl border-2 border-dashed p-16 text-center transition-all',
              dragOver
                ? 'border-blue-500 bg-blue-500/5'
                : 'border-astra-border bg-astra-surface hover:border-blue-500/30'
            )}
          >
            {uploading ? (
              <div className="flex flex-col items-center gap-3">
                <Loader2 className="h-10 w-10 animate-spin text-blue-500" />
                <span className="text-sm font-semibold text-slate-300">Parsing file&hellip;</span>
                <span className="text-[11px] text-slate-500">Validating rows against enum values and constraints</span>
              </div>
            ) : (
              <>
                <Upload className="mx-auto mb-4 h-12 w-12 text-slate-600" />
                <h3 className="mb-1 text-sm font-bold text-slate-200">Drag &amp; drop your .xlsx here</h3>
                <p className="mb-4 text-xs text-slate-500">Or click to browse</p>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="rounded-lg bg-blue-500 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-600"
                >
                  Choose File
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".xlsx,.xls"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) handleFile(f);
                  }}
                />
              </>
            )}
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════
          STEP 2 — PREVIEW
          ═══════════════════════════════════ */}
      {step === 'preview' && preview && counts && (
        <div className="space-y-4">
          {/* File banner */}
          <div className="flex items-center gap-3 rounded-xl border border-astra-border bg-astra-surface px-4 py-3">
            <FileSpreadsheet className="h-4 w-4 text-emerald-400" />
            <span className="flex-1 truncate text-sm font-semibold text-slate-300">{preview.file_name}</span>
            <span className="text-[10px] uppercase tracking-wider text-slate-500">
              {preview.sheets_found.length} sheets found
            </span>
          </div>

          {/* Summary pills */}
          <div className="grid grid-cols-3 gap-3 md:grid-cols-6">
            {(Object.keys(SHEET_META) as SheetKey[]).map(k => (
              <StatPill key={k} label={SHEET_META[k].label} value={counts[k].total} color={SHEET_META[k].color} />
            ))}
          </div>

          {/* Blocking errors warning */}
          {hasBlockingErrors && (
            <div className="flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
              <div className="text-[12px] text-amber-300">
                <strong>Some rows have errors.</strong> You can still import — invalid rows will be skipped
                and reported in the final summary. Fix the errors in your Excel and re-upload if you want a cleaner run.
              </div>
            </div>
          )}

          {/* Sheet tabs */}
          <div className="flex flex-wrap items-center gap-1 border-b border-astra-border">
            {(Object.keys(SHEET_META) as SheetKey[]).map(k => {
              const meta = SHEET_META[k];
              const Icon = meta.icon;
              const isActive = activeSheet === k;
              const cnt = counts[k];
              return (
                <button key={k}
                  onClick={() => setActiveSheet(k)}
                  className={clsx(
                    'flex items-center gap-1.5 border-b-2 px-3 py-2 text-[11px] font-semibold transition',
                    isActive
                      ? 'border-blue-500 text-blue-400'
                      : 'border-transparent text-slate-500 hover:text-slate-300'
                  )}>
                  <Icon className="h-3.5 w-3.5" style={{ color: isActive ? meta.color : undefined }} />
                  {meta.label}
                  <span className={clsx(
                    'ml-1 rounded-full px-1.5 py-0.5 text-[10px] font-bold',
                    isActive ? 'bg-blue-500/20 text-blue-400' : 'bg-astra-surface-alt text-slate-600'
                  )}>
                    {cnt.total}
                  </span>
                  {cnt.errors > 0 && (
                    <span className="ml-1 rounded-full bg-red-500/20 px-1.5 py-0.5 text-[10px] font-bold text-red-400">
                      {cnt.errors}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Sheet description */}
          <div className="text-[11px] text-slate-500">{SHEET_META[activeSheet].description}</div>

          {/* Rows table */}
          {activeRows.length === 0 ? (
            <div className="rounded-xl border border-astra-border bg-astra-surface py-12 text-center">
              <Info className="mx-auto mb-2 h-6 w-6 text-slate-600" />
              <p className="text-sm text-slate-400">No {SHEET_META[activeSheet].label.toLowerCase()} in the uploaded file</p>
              <p className="mt-1 text-[11px] text-slate-600">
                Fill out the &quot;{SHEET_META[activeSheet].label}&quot; sheet in the template if you want to import these
              </p>
            </div>
          ) : (
            <div className="overflow-hidden rounded-xl border border-astra-border bg-astra-surface">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="border-b border-astra-border bg-astra-surface-alt">
                    <th className="px-3 py-2 text-left font-semibold uppercase tracking-wider text-slate-500">Row</th>
                    <th className="px-3 py-2 text-left font-semibold uppercase tracking-wider text-slate-500">Status</th>
                    <th className="px-3 py-2 text-left font-semibold uppercase tracking-wider text-slate-500">Key Fields</th>
                    <th className="px-3 py-2 text-left font-semibold uppercase tracking-wider text-slate-500">Errors / Warnings</th>
                  </tr>
                </thead>
                <tbody>
                  {activeRows.slice(0, 200).map((r, idx) => (
                    <tr key={`${r.row}-${idx}`} className="border-b border-astra-border/30 hover:bg-astra-surface-alt/40">
                      <td className="px-3 py-2 font-mono text-slate-400">{r.row}</td>
                      <td className="px-3 py-2">
                        {r.valid ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold text-emerald-400">
                            <CheckCircle className="h-2.5 w-2.5" /> Valid
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 rounded-full bg-red-500/15 px-2 py-0.5 text-[10px] font-bold text-red-400">
                            <XCircle className="h-2.5 w-2.5" /> Invalid
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-slate-300">
                        <RowDataSummary sheet={activeSheet} data={r.data} />
                      </td>
                      <td className="px-3 py-2">
                        {r.errors.length === 0 && r.warnings.length === 0 && (
                          <span className="text-slate-600">—</span>
                        )}
                        {r.errors.length > 0 && (
                          <div className="space-y-0.5">
                            {r.errors.map((e, i) => (
                              <div key={i} className="text-[10px] text-red-400">• {e}</div>
                            ))}
                          </div>
                        )}
                        {r.warnings.length > 0 && (
                          <div className="mt-0.5 space-y-0.5">
                            {r.warnings.map((w, i) => (
                              <div key={i} className="text-[10px] text-amber-400">! {w}</div>
                            ))}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {activeRows.length > 200 && (
                <div className="border-t border-astra-border bg-astra-surface-alt px-3 py-2 text-center text-[10px] text-slate-500">
                  Showing first 200 of {activeRows.length} rows. All will be imported on confirm.
                </div>
              )}
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-between gap-3 pt-4">
            <button onClick={handleReset}
              className="flex items-center gap-1.5 rounded-lg border border-astra-border px-4 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200">
              <ArrowLeft className="h-3.5 w-3.5" /> Upload Different File
            </button>
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-slate-500">
                Ready to create&nbsp;
                <span className="font-bold text-slate-300">{counts.units.valid}</span> units,&nbsp;
                <span className="font-bold text-slate-300">{counts.connectors.valid}</span> connectors,&nbsp;
                <span className="font-bold text-slate-300">{counts.pins.valid}</span> pins
              </span>
              <button onClick={handleConfirm}
                className="flex items-center gap-1.5 rounded-lg bg-blue-500 px-4 py-2 text-xs font-semibold text-white transition hover:bg-blue-600">
                Confirm Import <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════
          STEP 3 — IMPORTING
          ═══════════════════════════════════ */}
      {step === 'importing' && (
        <div
          className="rounded-2xl border border-astra-border bg-astra-surface py-16"
          role="status"
          aria-live="polite"
        >
          <div className="flex flex-col items-center gap-4">
            <Loader2 className="h-10 w-10 animate-spin text-blue-500" aria-hidden="true" />
            <h3 className="text-sm font-bold text-slate-200">Importing interfaces&hellip;</h3>
            <p className="text-[11px] text-slate-500">
              Creating units, connectors, pins, buses, messages, and fields&hellip;
            </p>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════
          STEP 4 — DONE
          ═══════════════════════════════════ */}
      {step === 'done' && result && (
        <div className="space-y-5">
          {/* Success banner */}
          <div className="rounded-2xl border border-emerald-500/30 bg-gradient-to-br from-emerald-500/10 to-blue-500/10 p-8 text-center">
            <CheckCircle className="mx-auto mb-3 h-12 w-12 text-emerald-400" />
            <h3 className="text-lg font-bold text-slate-100">Import Complete</h3>
            <p className="mt-1 text-sm text-slate-400">
              Your Excel file has been processed and all valid entities have been created.
            </p>
          </div>

          {/* Results grid */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatPill label="Systems"         value={result.systems_created}         color="#06B6D4" />
            <StatPill label="Units"           value={result.units_created}           color="#3B82F6" />
            <StatPill label="Connectors"      value={result.connectors_created}      color="#10B981" />
            <StatPill label="Pins"            value={result.pins_created}            color="#F59E0B" />
            <StatPill label="Buses"           value={result.buses_created}           color="#8B5CF6" />
            <StatPill label="Pin Assignments" value={result.pin_assignments_created} color="#EC4899" />
            <StatPill label="Messages"        value={result.messages_created}        color="#F43F5E" />
            <StatPill label="Fields"          value={result.fields_created}          color="#06B6D4" />
          </div>

          {/* Errors (if any) */}
          {result.errors && result.errors.length > 0 && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
              <div className="mb-2 flex items-center gap-2 text-sm font-bold text-amber-300">
                <AlertTriangle className="h-4 w-4" />
                {result.errors.length} row{result.errors.length === 1 ? '' : 's'} skipped
              </div>
              <ul className="max-h-48 space-y-0.5 overflow-y-auto font-mono text-[10px] text-amber-300/80">
                {result.errors.map((e, i) => (
                  <li key={i}>• {e}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-between pt-4">
            <button onClick={handleReset}
              className="flex items-center gap-1.5 rounded-lg border border-astra-border bg-astra-surface px-4 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200">
              Import Another File
            </button>
            <button onClick={() => router.push(`${p}/interfaces`)}
              className="flex items-center gap-1.5 rounded-lg bg-blue-500 px-4 py-2 text-xs font-semibold text-white transition hover:bg-blue-600">
              View Interfaces <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
//  Row data summary — shows the most identifying fields per sheet
// ══════════════════════════════════════════════════════════════

function RowDataSummary({ sheet, data }: { sheet: SheetKey; data: Record<string, any> }) {
  if (!data) return <span className="text-slate-600">—</span>;

  const keyFields: Record<SheetKey, string[]> = {
    units:      ['designation', 'name', 'unit_type', 'system'],
    connectors: ['unit_designation', 'connector_designator', 'connector_type', 'gender'],
    pins:       ['pin_number', 'signal_name', 'signal_type', 'direction'],
    buses:      ['unit_designation', 'bus_name', 'protocol', 'bus_role'],
    messages:   ['bus_name', 'msg_label', 'direction'],
    fields:     ['msg_label', 'field_name', 'data_type', 'bit_length'],
  };

  const fields = keyFields[sheet] || [];
  const values = fields.map(f => data[f]).filter(v => v !== null && v !== undefined && v !== '');
  if (values.length === 0) return <span className="text-slate-600">—</span>;

  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
      {fields.map((f, i) => {
        const v = data[f];
        if (v === null || v === undefined || v === '') return null;
        // Labelize known enum fields
        const enumFields = new Set(['signal_type', 'direction', 'connector_type', 'gender', 'unit_type', 'protocol', 'bus_role']);
        const display = enumFields.has(f) ? labelize(String(v)) : String(v);
        return (
          <span key={i} className={clsx(
            'whitespace-nowrap',
            i === 0 ? 'font-mono font-bold text-slate-200' : 'text-slate-400'
          )}>
            {display}
            {i < fields.length - 1 && values.length > i + 1 && <span className="ml-2 text-slate-700">·</span>}
          </span>
        );
      })}
    </div>
  );
}
