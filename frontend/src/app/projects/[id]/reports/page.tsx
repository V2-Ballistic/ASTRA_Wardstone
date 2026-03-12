'use client';

/**
 * ASTRA — Reports Page (Project-Scoped)
 * File: frontend/src/app/projects/[id]/reports/page.tsx
 */

import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { FileText, Network, Shield, CheckSquare, LayoutDashboard, History, Download, Loader2, FileDown, Calendar, AlertCircle } from 'lucide-react';
import api from '@/lib/api';
import { projectsAPI } from '@/lib/api';

interface ReportItem { key: string; name: string; description: string; formats: string[]; frameworks?: string[]; icon: string; }
const ICON_MAP: Record<string, any> = { Network, FileText, Shield, CheckSquare, LayoutDashboard, History };
const FORMAT_LABELS: Record<string, { label: string; color: string }> = {
  xlsx: { label: 'Excel', color: '#10B981' }, pdf: { label: 'PDF', color: '#EF4444' },
  html: { label: 'HTML', color: '#3B82F6' }, docx: { label: 'Word', color: '#8B5CF6' },
};

export default function ReportsPage() {
  const params = useParams();
  const projectId = Number(params.id);
  const [catalog, setCatalog] = useState<ReportItem[]>([]);
  const [projectCode, setProjectCode] = useState('');
  const [loading, setLoading] = useState(true);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [selectedFormat, setSelectedFormat] = useState('');
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    Promise.all([
      api.get('/reports/catalog').catch(() => ({ data: [] })),
      projectsAPI.get(projectId).catch(() => null),
    ]).then(([catRes, projRes]) => {
      setCatalog(catRes.data || []);
      setProjectCode(projRes?.data?.code || '');
      setLoading(false);
    });
  }, [projectId]);

  const activeItem = catalog.find(c => c.key === activeKey);

  const generateReport = async () => {
    if (!activeKey || !selectedFormat) return;
    setGenerating(true); setError(''); setSuccess('');
    try {
      const params: any = { project_id: projectId };
      if (selectedFormat !== 'pdf' && selectedFormat !== 'html') params.format = selectedFormat;
      const res = await api.get(`/reports/${activeKey}`, { params, responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a'); link.href = url;
      link.download = `${projectCode}-${activeKey}.${selectedFormat}`; link.click();
      window.URL.revokeObjectURL(url);
      setSuccess(`${activeItem?.name} generated successfully`);
      setTimeout(() => setSuccess(''), 3000);
    } catch (e: any) { setError('Report generation failed. Check the backend logs.'); }
    setGenerating(false);
  };

  if (loading) return <div className="flex min-h-[60vh] items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-blue-500" /></div>;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-bold tracking-tight">Reports</h1>
        <p className="mt-0.5 text-sm text-slate-500">{projectCode} · Generate SRS, RTM, quality, and compliance reports</p>
      </div>

      {error && <div className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">{error}</div>}
      {success && <div className="mb-4 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-400">{success}</div>}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {catalog.map(item => {
          const Icon = ICON_MAP[item.icon] || FileText;
          const isActive = activeKey === item.key;
          return (
            <button key={item.key} onClick={() => { setActiveKey(isActive ? null : item.key); setSelectedFormat(item.formats[0] || 'pdf'); }}
              className={`rounded-xl border p-5 text-left transition-all ${isActive ? 'border-blue-500/40 bg-blue-500/5 shadow-lg shadow-blue-500/5' : 'border-astra-border bg-astra-surface hover:border-blue-500/20'}`}>
              <div className="flex items-center gap-3 mb-2">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-500/10"><Icon className="h-4 w-4 text-blue-400" /></div>
                <h3 className="text-sm font-bold text-slate-200">{item.name}</h3>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed mb-3">{item.description}</p>
              <div className="flex gap-1.5">
                {item.formats.map(fmt => (
                  <span key={fmt} className="rounded-full px-2 py-0.5 text-[9px] font-semibold" style={{ background: `${FORMAT_LABELS[fmt]?.color || '#6B7280'}20`, color: FORMAT_LABELS[fmt]?.color || '#6B7280' }}>
                    {FORMAT_LABELS[fmt]?.label || fmt.toUpperCase()}
                  </span>
                ))}
              </div>
            </button>
          );
        })}
      </div>

      {/* Active report config */}
      {activeItem && (
        <div className="mt-6 rounded-xl border border-blue-500/20 bg-astra-surface p-5">
          <h3 className="text-sm font-bold text-slate-200 mb-3">Generate: {activeItem.name}</h3>
          <div className="flex items-center gap-3">
            <div className="flex gap-2">
              {activeItem.formats.map(fmt => (
                <button key={fmt} onClick={() => setSelectedFormat(fmt)}
                  className={`rounded-lg border px-3 py-2 text-xs font-semibold transition ${selectedFormat === fmt ? 'border-blue-500/40 bg-blue-500/10 text-blue-400' : 'border-astra-border text-slate-400 hover:text-slate-200'}`}>
                  <FileDown className="inline h-3.5 w-3.5 mr-1" />{FORMAT_LABELS[fmt]?.label || fmt}
                </button>
              ))}
            </div>
            <button onClick={generateReport} disabled={generating}
              className="flex items-center gap-2 rounded-lg bg-blue-500 px-5 py-2 text-xs font-semibold text-white hover:bg-blue-600 disabled:opacity-50">
              {generating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
              {generating ? 'Generating…' : 'Download'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
