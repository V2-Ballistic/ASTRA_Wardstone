'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  FileText, Network, Shield, CheckSquare, LayoutDashboard,
  History, Download, Loader2, ChevronDown, ChevronRight,
  Calendar, Clock, FileSpreadsheet, FileDown, AlertCircle,
  Filter,
} from 'lucide-react';
import api from '@/lib/api';

/* ══════════════════════════════════════
   Types
   ══════════════════════════════════════ */

interface ReportCatalogItem {
  key: string;
  name: string;
  description: string;
  formats: string[];
  frameworks?: string[];
  icon: string;
}

interface HistoryEntry {
  report_type: string;
  project_id: number;
  format: string;
  user_full_name: string;
  generated_at: string;
}

const ICON_MAP: Record<string, any> = {
  Network, FileText, Shield, CheckSquare, LayoutDashboard, History,
};

const FORMAT_LABELS: Record<string, { label: string; color: string }> = {
  xlsx: { label: 'Excel', color: '#10B981' },
  pdf:  { label: 'PDF',   color: '#EF4444' },
  html: { label: 'HTML',  color: '#3B82F6' },
  docx: { label: 'Word',  color: '#8B5CF6' },
};

const FRAMEWORK_LABELS: Record<string, string> = {
  'nist-800-53': 'NIST SP 800-53',
  'mil-std-882e': 'MIL-STD-882E',
  'do-178c': 'DO-178C',
  'iso-29148': 'ISO 29148',
};

/* ══════════════════════════════════════
   Component
   ══════════════════════════════════════ */

export default function ReportsPage() {
  const [catalog, setCatalog] = useState<ReportCatalogItem[]>([]);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);

  // Active report config
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [selectedFormat, setSelectedFormat] = useState('');
  const [selectedFramework, setSelectedFramework] = useState('nist-800-53');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');

  // Project
  const [projectId, setProjectId] = useState<number | null>(null);

  useEffect(() => {
    api.get('/projects/').then(r => {
      if (r.data?.length) setProjectId(r.data[0].id);
    }).catch(() => {});
  }, []);

  const loadCatalog = useCallback(async () => {
    try {
      const r = await api.get('/reports/catalog');
      setCatalog(r.data || []);
    } catch { /* ignore */ }
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const r = await api.get('/reports/history', {
        params: projectId ? { project_id: projectId, limit: 20 } : { limit: 20 },
      });
      setHistory(r.data?.items || []);
    } catch { /* ignore */ }
  }, [projectId]);

  useEffect(() => {
    Promise.all([loadCatalog(), loadHistory()]).finally(() => setLoading(false));
  }, [loadCatalog, loadHistory]);

  const selectReport = (key: string) => {
    const item = catalog.find(c => c.key === key);
    if (!item) return;
    setActiveKey(key);
    setSelectedFormat(item.formats[0]);
    setError('');
  };

  const generateReport = async () => {
    if (!activeKey || !projectId) return;
    setGenerating(true);
    setError('');

    try {
      // Build endpoint and params
      const params: Record<string, string> = {
        project_id: String(projectId),
      };

      let endpoint = `/reports/${activeKey}`;

      // Format (status-dashboard is always pdf)
      if (activeKey !== 'status-dashboard') {
        params.format = selectedFormat;
      }

      // Compliance-specific
      if (activeKey === 'compliance') {
        params.framework = selectedFramework;
      }

      // Change history date range
      if (activeKey === 'change-history') {
        if (dateFrom) params.date_from = dateFrom;
        if (dateTo) params.date_to = dateTo;
      }

      const response = await api.get(endpoint, {
        params,
        responseType: 'blob',
      });

      // Extract filename from Content-Disposition header
      const disposition = response.headers['content-disposition'] || '';
      const filenameMatch = disposition.match(/filename="?([^"]+)"?/);
      const filename = filenameMatch
        ? filenameMatch[1]
        : `report_${activeKey}.${selectedFormat}`;

      // Trigger download
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);

      // Refresh history
      loadHistory();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Report generation failed');
    }
    setGenerating(false);
  };

  const activeItem = catalog.find(c => c.key === activeKey);

  const inputClass =
    'rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-1.5 text-xs text-slate-200 outline-none focus:border-blue-500/50';

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-xl font-bold tracking-tight">Reports</h1>
        <p className="mt-0.5 text-sm text-slate-500">
          Generate compliance reports, traceability matrices, and project documentation
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_380px]">
        {/* ── Left: Report Catalog ── */}
        <div className="space-y-3">
          {catalog.map((item) => {
            const IconComponent = ICON_MAP[item.icon] || FileText;
            const isActive = activeKey === item.key;

            return (
              <button
                key={item.key}
                onClick={() => selectReport(item.key)}
                className={`w-full rounded-xl border p-5 text-left transition ${
                  isActive
                    ? 'border-blue-500/40 bg-blue-500/8'
                    : 'border-astra-border bg-astra-surface hover:border-blue-500/20'
                }`}
              >
                <div className="flex items-start gap-4">
                  <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
                    isActive ? 'bg-blue-500/15' : 'bg-astra-surface-alt'
                  }`}>
                    <IconComponent className={`h-5 w-5 ${
                      isActive ? 'text-blue-400' : 'text-slate-400'
                    }`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1">
                      <h3 className="text-sm font-bold text-slate-200">{item.name}</h3>
                      <ChevronRight className={`h-4 w-4 transition ${
                        isActive ? 'text-blue-400 rotate-90' : 'text-slate-600'
                      }`} />
                    </div>
                    <p className="text-xs text-slate-500 leading-relaxed">{item.description}</p>
                    <div className="mt-2 flex gap-1.5">
                      {item.formats.map(fmt => (
                        <span key={fmt} className="rounded-full px-2 py-0.5 text-[9px] font-bold"
                          style={{
                            background: (FORMAT_LABELS[fmt]?.color || '#666') + '15',
                            color: FORMAT_LABELS[fmt]?.color || '#666',
                          }}>
                          {FORMAT_LABELS[fmt]?.label || fmt.toUpperCase()}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {/* ── Right: Config Panel + History ── */}
        <div className="space-y-4">
          {/* Config panel */}
          {activeItem ? (
            <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
              <h3 className="mb-4 text-sm font-bold text-slate-200">
                Generate: {activeItem.name}
              </h3>

              <div className="space-y-3">
                {/* Format selector */}
                {activeItem.formats.length > 1 && (
                  <div>
                    <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                      Output Format
                    </label>
                    <div className="flex gap-2">
                      {activeItem.formats.map(fmt => (
                        <button
                          key={fmt}
                          onClick={() => setSelectedFormat(fmt)}
                          className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-semibold transition ${
                            selectedFormat === fmt
                              ? 'border-blue-500/40 bg-blue-500/10 text-blue-400'
                              : 'border-astra-border text-slate-400 hover:text-slate-200'
                          }`}
                        >
                          <FileDown className="h-3.5 w-3.5" />
                          {FORMAT_LABELS[fmt]?.label || fmt.toUpperCase()}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Framework selector (compliance only) */}
                {activeItem.frameworks && (
                  <div>
                    <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                      Compliance Framework
                    </label>
                    <select
                      value={selectedFramework}
                      onChange={e => setSelectedFramework(e.target.value)}
                      className={inputClass + ' w-full'}
                    >
                      {activeItem.frameworks.map(fw => (
                        <option key={fw} value={fw}>
                          {FRAMEWORK_LABELS[fw] || fw}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {/* Date range (change history) */}
                {activeKey === 'change-history' && (
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                        From Date
                      </label>
                      <input
                        type="date"
                        value={dateFrom}
                        onChange={e => setDateFrom(e.target.value)}
                        className={inputClass + ' w-full'}
                      />
                    </div>
                    <div>
                      <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                        To Date
                      </label>
                      <input
                        type="date"
                        value={dateTo}
                        onChange={e => setDateTo(e.target.value)}
                        className={inputClass + ' w-full'}
                      />
                    </div>
                  </div>
                )}

                {/* Error */}
                {error && (
                  <div className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
                    <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                    {error}
                  </div>
                )}

                {/* Generate button */}
                <button
                  onClick={generateReport}
                  disabled={generating || !projectId}
                  className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-500 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-600 disabled:opacity-50"
                >
                  {generating ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Download className="h-4 w-4" />
                  )}
                  {generating ? 'Generating…' : 'Generate & Download'}
                </button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center rounded-xl border border-astra-border bg-astra-surface py-12">
              <div className="text-center">
                <FileSpreadsheet className="mx-auto mb-2 h-8 w-8 text-slate-600" />
                <p className="text-xs text-slate-500">Select a report to configure</p>
              </div>
            </div>
          )}

          {/* Report History */}
          <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-bold text-slate-200">
              <Clock className="h-4 w-4 text-slate-400" />
              Recent Reports
            </h3>
            {history.length === 0 ? (
              <p className="text-xs text-slate-500 italic">No reports generated yet</p>
            ) : (
              <div className="space-y-2">
                {history.map((h, i) => {
                  const fmtStyle = FORMAT_LABELS[h.format] || { label: h.format, color: '#666' };
                  return (
                    <div key={i} className="flex items-center gap-2.5 rounded-lg bg-astra-surface-alt p-2.5">
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-semibold text-slate-300 truncate">
                          {h.report_type.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                        </div>
                        <div className="text-[10px] text-slate-500">
                          {h.user_full_name} · {new Date(h.generated_at).toLocaleString()}
                        </div>
                      </div>
                      <span
                        className="rounded-full px-2 py-0.5 text-[9px] font-bold"
                        style={{
                          background: fmtStyle.color + '15',
                          color: fmtStyle.color,
                        }}
                      >
                        {fmtStyle.label}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
