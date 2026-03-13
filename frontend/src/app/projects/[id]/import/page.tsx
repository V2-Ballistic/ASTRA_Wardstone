'use client';

/**
 * ASTRA — Requirements Import Page
 * ===================================
 * File: frontend/src/app/projects/[id]/import/page.tsx
 *
 * Steps: Upload → Preview (with row accept/reject) → Confirm → Summary
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  Upload, Loader2, FileText, CheckCircle, XCircle, AlertTriangle,
  Download, ChevronRight, RefreshCw, X, Check, FileSpreadsheet,
} from 'lucide-react';
import clsx from 'clsx';
import { projectsAPI } from '@/lib/api';
import api from '@/lib/api';

// ── Types ──

interface ImportRow {
  row_number: number;
  title: string;
  statement: string;
  rationale: string;
  req_type: string;
  priority: string;
  level: string;
  parent_req_id: string;
  quality_score: number;
  quality_passed: boolean;
  warnings: string[];
  errors: string[];
  included: boolean;
}

interface PreviewData {
  filename: string;
  total_rows: number;
  valid_rows: number;
  error_rows: number;
  column_mapping: Record<string, string>;
  rows: ImportRow[];
}

interface ImportResult {
  created: number;
  skipped: number;
  errors: string[];
  requirements: { id: number; req_id: string; title: string; quality_score: number }[];
}

type Step = 'upload' | 'preview' | 'importing' | 'done';

// ── Quality badge ──

function QualityBadge({ score }: { score: number }) {
  const color = score >= 80 ? '#10B981' : score >= 60 ? '#F59E0B' : '#EF4444';
  return (
    <span className="font-mono text-[11px] font-bold" style={{ color }}>
      {score.toFixed(0)}
    </span>
  );
}

// ══════════════════════════════════════
//  Main Page
// ══════════════════════════════════════

export default function ImportPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);
  const p = `/projects/${projectId}`;
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [projectCode, setProjectCode] = useState('');
  const [step, setStep] = useState<Step>('upload');
  const [uploading, setUploading] = useState(false);
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [rows, setRows] = useState<ImportRow[]>([]);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState('');
  const [progress, setProgress] = useState(0);
  const [dragOver, setDragOver] = useState(false);

  useEffect(() => {
    projectsAPI.get(projectId)
      .then((res) => setProjectCode(res.data?.code || ''))
      .catch(() => {});
  }, [projectId]);

  // ── Upload handler ──
  const handleFile = useCallback(async (file: File) => {
    const ext = file.name.split('.').pop()?.toLowerCase();
    if (!ext || !['csv', 'xlsx', 'xls'].includes(ext)) {
      setError('Unsupported file type. Use .csv or .xlsx');
      return;
    }

    setUploading(true);
    setError('');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await api.post(`/imports/requirements?project_id=${projectId}`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setPreview(res.data);
      setRows(res.data.rows);
      setStep('preview');
    } catch (e: any) {
      const detail = e.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Failed to parse file');
    }
    setUploading(false);
  }, [projectId]);

  // ── Drag and drop ──
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setDragOver(true); };
  const handleDragLeave = () => setDragOver(false);

  // ── Row toggle ──
  const toggleRow = (rowNum: number) => {
    setRows((prev) => prev.map((r) =>
      r.row_number === rowNum ? { ...r, included: !r.included } : r
    ));
  };

  const includeAll = () => setRows((prev) => prev.map((r) => ({ ...r, included: r.errors.length === 0 })));
  const excludeAll = () => setRows((prev) => prev.map((r) => ({ ...r, included: false })));

  // ── Confirm import ──
  const handleConfirm = async () => {
    setStep('importing');
    setProgress(0);
    setError('');

    // Animate progress
    const interval = setInterval(() => {
      setProgress((p) => Math.min(p + 2, 90));
    }, 100);

    try {
      const res = await api.post('/imports/requirements/confirm', {
        project_id: projectId,
        rows: rows.filter((r) => r.included),
      });
      setResult(res.data);
      setProgress(100);
      setStep('done');
    } catch (e: any) {
      const detail = e.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Import failed');
      setStep('preview');
    }
    clearInterval(interval);
  };

  // ── Download template ──
  const downloadTemplate = async () => {
    try {
      const res = await api.get('/imports/template', { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = 'astra_import_template.csv';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      setError('Failed to download template');
    }
  };

  // ── Counts ──
  const includedCount = rows.filter((r) => r.included).length;
  const errorCount = rows.filter((r) => r.errors.length > 0).length;
  const avgQuality = includedCount > 0
    ? rows.filter((r) => r.included).reduce((s, r) => s + r.quality_score, 0) / includedCount
    : 0;

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Import Requirements</h1>
          <p className="mt-0.5 text-sm text-slate-500">{projectCode} · Import from CSV or Excel</p>
        </div>
        <button onClick={downloadTemplate}
          className="flex items-center gap-1.5 rounded-lg border border-astra-border px-3 py-2 text-xs font-semibold text-slate-400 transition hover:border-blue-500/30 hover:text-slate-200">
          <Download className="h-3.5 w-3.5" /> Download Template
        </button>
      </div>

      {error && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {error}
          <button onClick={() => setError('')} className="ml-auto"><X className="h-3.5 w-3.5" /></button>
        </div>
      )}

      {/* ═══════════════════════════════════
          Step 1: Upload
          ═══════════════════════════════════ */}
      {step === 'upload' && (
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
              <span className="text-sm text-slate-400">Parsing file…</span>
            </div>
          ) : (
            <>
              <Upload className="mx-auto h-12 w-12 text-slate-600 mb-4" />
              <h3 className="text-sm font-bold text-slate-200 mb-1">
                Drag & drop a CSV or Excel file
              </h3>
              <p className="text-xs text-slate-500 mb-4">
                Or click to browse. Expects columns: title, statement, rationale, req_type, priority, level
              </p>
              <button
                onClick={() => fileInputRef.current?.click()}
                className="rounded-lg bg-blue-500 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-600"
              >
                Choose File
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.xlsx,.xls"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleFile(f);
                  e.target.value = '';
                }}
              />
            </>
          )}
        </div>
      )}

      {/* ═══════════════════════════════════
          Step 2: Preview
          ═══════════════════════════════════ */}
      {step === 'preview' && preview && (
        <div>
          {/* Summary bar */}
          <div className="mb-4 flex items-center gap-4 rounded-xl border border-astra-border bg-astra-surface px-5 py-3">
            <FileSpreadsheet className="h-5 w-5 text-blue-400" />
            <div className="flex-1">
              <span className="text-sm font-semibold text-slate-200">{preview.filename}</span>
              <span className="ml-2 text-xs text-slate-500">{preview.total_rows} rows</span>
            </div>
            <div className="flex items-center gap-4 text-xs">
              <span className="text-emerald-400">{includedCount} included</span>
              <span className="text-slate-500">{preview.total_rows - includedCount} excluded</span>
              {errorCount > 0 && <span className="text-red-400">{errorCount} with errors</span>}
              <span className="text-slate-400">Avg quality: <QualityBadge score={avgQuality} /></span>
            </div>
          </div>

          {/* Column mapping */}
          <div className="mb-4 rounded-xl border border-astra-border bg-astra-surface p-4">
            <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Column Mapping
            </h3>
            <div className="flex flex-wrap gap-2">
              {Object.entries(preview.column_mapping).map(([csv_col, field]) => (
                <div key={csv_col} className="flex items-center gap-1.5 rounded-lg bg-astra-surface-alt px-3 py-1.5">
                  <span className="text-[11px] text-slate-400">{csv_col}</span>
                  <ChevronRight className="h-3 w-3 text-slate-600" />
                  <span className="text-[11px] font-semibold text-blue-400">{field}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Bulk actions */}
          <div className="mb-3 flex items-center gap-2">
            <button onClick={includeAll}
              className="rounded-lg border border-astra-border px-3 py-1.5 text-[11px] font-semibold text-slate-400 hover:text-slate-200">
              Include All Valid
            </button>
            <button onClick={excludeAll}
              className="rounded-lg border border-astra-border px-3 py-1.5 text-[11px] font-semibold text-slate-400 hover:text-slate-200">
              Exclude All
            </button>
          </div>

          {/* Preview table */}
          <div className="overflow-x-auto rounded-xl border border-astra-border bg-astra-surface">
            <table className="w-full">
              <thead>
                <tr className="border-b border-astra-border bg-astra-surface-alt">
                  <th className="px-3 py-2 text-left text-[10px] font-bold uppercase tracking-wider text-slate-500 w-10"></th>
                  <th className="px-3 py-2 text-left text-[10px] font-bold uppercase tracking-wider text-slate-500 w-10">#</th>
                  <th className="px-3 py-2 text-left text-[10px] font-bold uppercase tracking-wider text-slate-500">Title</th>
                  <th className="px-3 py-2 text-left text-[10px] font-bold uppercase tracking-wider text-slate-500 max-w-[300px]">Statement</th>
                  <th className="px-3 py-2 text-center text-[10px] font-bold uppercase tracking-wider text-slate-500 w-16">Type</th>
                  <th className="px-3 py-2 text-center text-[10px] font-bold uppercase tracking-wider text-slate-500 w-14">Level</th>
                  <th className="px-3 py-2 text-center text-[10px] font-bold uppercase tracking-wider text-slate-500 w-16">Quality</th>
                  <th className="px-3 py-2 text-center text-[10px] font-bold uppercase tracking-wider text-slate-500 w-16">Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const hasErrors = row.errors.length > 0;
                  const hasWarnings = row.warnings.length > 0;
                  return (
                    <tr key={row.row_number}
                      className={clsx(
                        'border-b border-astra-border/50 transition',
                        !row.included && 'opacity-40',
                        hasErrors && 'bg-red-500/[0.03]'
                      )}>
                      <td className="px-3 py-2">
                        <button onClick={() => toggleRow(row.row_number)}
                          className="flex h-5 w-5 items-center justify-center rounded border transition"
                          style={{
                            borderColor: row.included ? '#3B82F6' : '#475569',
                            background: row.included ? '#3B82F6' : 'transparent',
                          }}>
                          {row.included && <Check className="h-3 w-3 text-white" />}
                        </button>
                      </td>
                      <td className="px-3 py-2 text-[11px] text-slate-500">{row.row_number}</td>
                      <td className="px-3 py-2">
                        <span className="text-xs font-semibold text-slate-200">{row.title || '—'}</span>
                      </td>
                      <td className="px-3 py-2 max-w-[300px]">
                        <span className="text-[11px] text-slate-400 line-clamp-2">{row.statement || '—'}</span>
                      </td>
                      <td className="px-3 py-2 text-center">
                        <span className="text-[10px] text-slate-400 capitalize">{row.req_type}</span>
                      </td>
                      <td className="px-3 py-2 text-center">
                        <span className="text-[10px] font-bold text-slate-400">{row.level}</span>
                      </td>
                      <td className="px-3 py-2 text-center">
                        <QualityBadge score={row.quality_score} />
                      </td>
                      <td className="px-3 py-2 text-center">
                        {hasErrors ? (
                          <div className="group relative">
                            <XCircle className="mx-auto h-4 w-4 text-red-400" />
                            <div className="absolute right-0 top-6 z-10 hidden w-48 rounded-lg border border-red-500/20 bg-slate-900 p-2 text-left text-[10px] text-red-400 shadow-xl group-hover:block">
                              {row.errors.map((e, i) => <div key={i}>{e}</div>)}
                            </div>
                          </div>
                        ) : hasWarnings ? (
                          <div className="group relative">
                            <AlertTriangle className="mx-auto h-4 w-4 text-amber-400" />
                            <div className="absolute right-0 top-6 z-10 hidden w-48 rounded-lg border border-amber-500/20 bg-slate-900 p-2 text-left text-[10px] text-amber-400 shadow-xl group-hover:block">
                              {row.warnings.map((w, i) => <div key={i}>{w}</div>)}
                            </div>
                          </div>
                        ) : (
                          <CheckCircle className="mx-auto h-4 w-4 text-emerald-400" />
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Actions */}
          <div className="mt-4 flex items-center justify-between">
            <button onClick={() => { setStep('upload'); setPreview(null); setRows([]); }}
              className="rounded-lg border border-astra-border px-4 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200">
              Upload Different File
            </button>
            <div className="flex items-center gap-3">
              <span className="text-xs text-slate-500">
                {includedCount} requirement{includedCount !== 1 ? 's' : ''} will be imported
              </span>
              <button onClick={handleConfirm} disabled={includedCount === 0}
                className="rounded-lg bg-blue-500 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-600 disabled:opacity-50">
                Import {includedCount} Requirements
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════
          Step 3: Importing (progress)
          ═══════════════════════════════════ */}
      {step === 'importing' && (
        <div className="rounded-2xl border border-astra-border bg-astra-surface p-12 text-center">
          <Loader2 className="mx-auto h-10 w-10 animate-spin text-blue-500 mb-4" />
          <h3 className="text-sm font-bold text-slate-200 mb-2">Importing Requirements…</h3>
          <div className="mx-auto max-w-xs">
            <div className="h-2 overflow-hidden rounded-full bg-astra-surface-alt">
              <div
                className="h-full rounded-full bg-blue-500 transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
            <span className="mt-1 text-[10px] text-slate-500">{progress}%</span>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════
          Step 4: Done
          ═══════════════════════════════════ */}
      {step === 'done' && result && (
        <div className="rounded-2xl border border-astra-border bg-astra-surface p-8">
          <div className="text-center mb-6">
            <CheckCircle className="mx-auto h-12 w-12 text-emerald-400 mb-3" />
            <h3 className="text-lg font-bold text-slate-200">Import Complete</h3>
          </div>

          {/* Summary cards */}
          <div className="grid grid-cols-3 gap-4 mb-6">
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4 text-center">
              <div className="text-2xl font-bold text-emerald-400">{result.created}</div>
              <div className="text-[10px] text-slate-500">Created</div>
            </div>
            <div className="rounded-xl border border-astra-border bg-astra-surface-alt p-4 text-center">
              <div className="text-2xl font-bold text-slate-400">{result.skipped}</div>
              <div className="text-[10px] text-slate-500">Skipped</div>
            </div>
            <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4 text-center">
              <div className="text-2xl font-bold text-red-400">{result.errors.length}</div>
              <div className="text-[10px] text-slate-500">Errors</div>
            </div>
          </div>

          {/* Created requirements */}
          {result.requirements.length > 0 && (
            <div className="mb-4">
              <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Created Requirements
              </h4>
              <div className="max-h-48 overflow-y-auto rounded-xl border border-astra-border bg-astra-surface-alt">
                {result.requirements.map((r) => (
                  <div key={r.id} className="flex items-center gap-3 border-b border-astra-border/50 px-4 py-2 last:border-0">
                    <span className="font-mono text-xs font-semibold text-blue-400">{r.req_id}</span>
                    <span className="flex-1 truncate text-xs text-slate-300">{r.title}</span>
                    <QualityBadge score={r.quality_score} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Errors */}
          {result.errors.length > 0 && (
            <div className="mb-4 rounded-xl border border-red-500/20 bg-red-500/5 p-4">
              <h4 className="mb-2 text-xs font-semibold text-red-400">Errors</h4>
              {result.errors.map((e, i) => (
                <div key={i} className="text-[11px] text-red-400/80">{e}</div>
              ))}
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-center gap-3 mt-6">
            <button onClick={() => router.push(`${p}/requirements`)}
              className="rounded-lg bg-blue-500 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-600">
              View Requirements
            </button>
            <button onClick={() => { setStep('upload'); setPreview(null); setRows([]); setResult(null); }}
              className="rounded-lg border border-astra-border px-5 py-2.5 text-sm font-semibold text-slate-400 transition hover:text-slate-200">
              Import More
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
