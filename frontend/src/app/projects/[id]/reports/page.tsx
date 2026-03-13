'use client';

/**
 * ASTRA — Reports Page (Project-Scoped)
 * ========================================
 * File: frontend/src/app/projects/[id]/reports/page.tsx
 *
 * 6 report types with format selection, generation, and download.
 * Compliance matrix has framework picker, Change History has date range.
 */

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import {
  Loader2, FileBarChart, Network, FileText, Shield, CheckSquare,
  LayoutDashboard, Clock, Download, RefreshCw, ChevronDown,
  AlertTriangle, CheckCircle,
} from 'lucide-react';
import clsx from 'clsx';
import { projectsAPI } from '@/lib/api';
import api from '@/lib/api';

// ── Report catalog ──

interface ReportType {
  key: string;
  name: string;
  description: string;
  formats: string[];
  icon: any;
  iconColor: string;
  frameworks?: string[];
  hasDateRange?: boolean;
}

const REPORTS: ReportType[] = [
  {
    key: 'traceability-matrix',
    name: 'Traceability Matrix (RTM)',
    description: 'Full requirements-to-artifacts-to-verification traceability matrix with color-coded coverage status.',
    formats: ['xlsx', 'pdf', 'html'],
    icon: Network,
    iconColor: '#3B82F6',
  },
  {
    key: 'requirements-spec',
    name: 'Requirements Specification (SRS)',
    description: 'Formal IEEE 830 / ISO 29148 specification document with cover page, revision history, and grouped requirements.',
    formats: ['docx', 'pdf'],
    icon: FileText,
    iconColor: '#8B5CF6',
  },
  {
    key: 'quality',
    name: 'Quality Assessment',
    description: 'Quality score distribution, common issues, prohibited terms tracking, TBD/TBR counts, and improvement recommendations.',
    formats: ['xlsx', 'pdf'],
    icon: Shield,
    iconColor: '#F59E0B',
  },
  {
    key: 'compliance',
    name: 'Compliance Matrix',
    description: 'Map requirements to compliance frameworks with gap analysis.',
    formats: ['xlsx', 'pdf'],
    icon: CheckSquare,
    iconColor: '#10B981',
    frameworks: ['nist-800-53', 'mil-std-882e', 'do-178c', 'iso-29148'],
  },
  {
    key: 'status-dashboard',
    name: 'Status Dashboard',
    description: 'Project snapshot: requirement counts, verification progress, traceability coverage, baselines, and recent activity.',
    formats: ['pdf'],
    icon: LayoutDashboard,
    iconColor: '#06B6D4',
  },
  {
    key: 'change-history',
    name: 'Change History (CCB)',
    description: 'Detailed change log grouped by requirement, showing field diffs within a date range. For Configuration Control Board meetings.',
    formats: ['xlsx', 'pdf'],
    icon: Clock,
    iconColor: '#EF4444',
    hasDateRange: true,
  },
];

const FORMAT_LABELS: Record<string, { label: string; color: string }> = {
  xlsx: { label: 'XLSX', color: '#10B981' },
  pdf: { label: 'PDF', color: '#EF4444' },
  docx: { label: 'DOCX', color: '#3B82F6' },
  html: { label: 'HTML', color: '#F59E0B' },
};

const FRAMEWORK_LABELS: Record<string, string> = {
  'nist-800-53': 'NIST 800-53',
  'mil-std-882e': 'MIL-STD-882E',
  'do-178c': 'DO-178C',
  'iso-29148': 'ISO 29148',
};

// ── Format button ──

function FormatButton({ format, generating, onClick }: {
  format: string; generating: boolean; onClick: () => void;
}) {
  const cfg = FORMAT_LABELS[format] || { label: format.toUpperCase(), color: '#6B7280' };
  return (
    <button
      onClick={onClick}
      disabled={generating}
      className={clsx(
        'flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[11px] font-bold transition',
        generating
          ? 'border-slate-700 text-slate-600 cursor-wait'
          : 'border-astra-border hover:border-blue-500/30 hover:bg-astra-surface-hover'
      )}
      style={!generating ? { color: cfg.color } : undefined}
    >
      {generating ? (
        <Loader2 className="h-3 w-3 animate-spin" />
      ) : (
        <Download className="h-3 w-3" />
      )}
      {cfg.label}
    </button>
  );
}

// ── Report Card ──

function ReportCard({ report, projectId, projectCode }: {
  report: ReportType; projectId: number; projectCode: string;
}) {
  const [generating, setGenerating] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Compliance framework
  const [framework, setFramework] = useState(report.frameworks?.[0] || '');

  // Date range
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const handleGenerate = async (format: string) => {
    setGenerating(format);
    setError('');
    setSuccess('');

    try {
      const params: Record<string, string> = {
        project_id: String(projectId),
      };

      // Format (status-dashboard is always pdf)
      if (report.key !== 'status-dashboard') {
        params.format = format;
      }

      // Compliance framework
      if (report.key === 'compliance' && framework) {
        params.framework = framework;
      }

      // Date range
      if (report.key === 'change-history') {
        if (dateFrom) params.date_from = dateFrom;
        if (dateTo) params.date_to = dateTo;
      }

      const response = await api.get(`/reports/${report.key}`, {
        params,
        responseType: 'blob',
      });

      // Extract filename from Content-Disposition header
      const disposition = response.headers['content-disposition'] || '';
      const filenameMatch = disposition.match(/filename="?([^"]+)"?/);
      const filename = filenameMatch
        ? filenameMatch[1]
        : `${projectCode}_${report.key.replace(/-/g, '_')}.${format}`;

      // Download
      const blob = new Blob([response.data]);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      setSuccess(`${FORMAT_LABELS[format]?.label || format} downloaded`);
      setTimeout(() => setSuccess(''), 3000);
    } catch (e: any) {
      if (e.response?.data instanceof Blob) {
        const text = await e.response.data.text();
        try {
          const json = JSON.parse(text);
          setError(json.detail || 'Generation failed');
        } catch {
          setError('Report generation failed');
        }
      } else {
        setError(e.response?.data?.detail || 'Report generation failed');
      }
    }
    setGenerating(null);
  };

  const Icon = report.icon;

  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface p-5 transition hover:border-astra-border-light">
      {/* Header */}
      <div className="flex items-start gap-3 mb-3">
        <div
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
          style={{ background: `${report.iconColor}15` }}
        >
          <Icon className="h-5 w-5" style={{ color: report.iconColor }} />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-bold text-slate-200">{report.name}</h3>
          <p className="mt-0.5 text-[11px] text-slate-500 leading-relaxed">{report.description}</p>
        </div>
      </div>

      {/* Compliance framework selector */}
      {report.frameworks && (
        <div className="mb-3">
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Framework
          </label>
          <div className="relative">
            <select
              value={framework}
              onChange={(e) => setFramework(e.target.value)}
              className="w-full appearance-none rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 pr-8 text-xs text-slate-200 outline-none focus:border-blue-500/50"
            >
              {report.frameworks.map((fw) => (
                <option key={fw} value={fw}>{FRAMEWORK_LABELS[fw] || fw}</option>
              ))}
            </select>
            <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-slate-500" />
          </div>
        </div>
      )}

      {/* Date range for change history */}
      {report.hasDateRange && (
        <div className="mb-3 grid grid-cols-2 gap-2">
          <div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">From</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-xs text-slate-200 outline-none focus:border-blue-500/50"
            />
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">To</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-xs text-slate-200 outline-none focus:border-blue-500/50"
            />
          </div>
        </div>
      )}

      {/* Format buttons */}
      <div className="flex items-center gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-600 mr-1">
          Download
        </span>
        {report.formats.map((fmt) => (
          <FormatButton
            key={fmt}
            format={fmt}
            generating={generating === fmt}
            onClick={() => handleGenerate(fmt)}
          />
        ))}
      </div>

      {/* Status messages */}
      {error && (
        <div className="mt-3 flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2">
          <AlertTriangle className="h-3.5 w-3.5 text-red-400 shrink-0" />
          <span className="text-[11px] text-red-400">{error}</span>
        </div>
      )}
      {success && (
        <div className="mt-3 flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-3 py-2">
          <CheckCircle className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
          <span className="text-[11px] text-emerald-400">{success}</span>
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════
//  Main Page
// ══════════════════════════════════════

export default function ReportsPage() {
  const params = useParams();
  const projectId = Number(params.id);

  const [projectCode, setProjectCode] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    projectsAPI.get(projectId)
      .then((res) => setProjectCode(res.data?.code || ''))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectId]);

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-xl font-bold tracking-tight">Reports</h1>
        <p className="mt-0.5 text-sm text-slate-500">
          {projectCode} · Generate and download project reports
        </p>
      </div>

      {/* Report cards grid */}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {REPORTS.map((report) => (
          <ReportCard
            key={report.key}
            report={report}
            projectId={projectId}
            projectCode={projectCode}
          />
        ))}
      </div>
    </div>
  );
}
