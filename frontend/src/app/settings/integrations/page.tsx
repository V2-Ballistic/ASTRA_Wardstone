'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Plus, Loader2, CheckCircle, XCircle, AlertTriangle,
  RefreshCw, Settings2, Trash2, TestTube, ArrowDownToLine,
  ArrowUpFromLine, Clock, ChevronRight, Link2, Unplug, Power,
} from 'lucide-react';
import api from '@/lib/api';

/* ══════════════════════════════════════
   Types
   ══════════════════════════════════════ */

interface CatalogItem {
  type: string;
  name: string;
  description: string;
  config_fields: { key: string; label: string; type: string; placeholder: string }[];
  supports_webhook: boolean;
  webhook_url?: string;
}

interface IntegrationConfig {
  id: number;
  project_id: number;
  integration_type: string;
  display_name: string;
  external_project: string;
  field_mapping: Record<string, string>;
  sync_direction: string;
  sync_schedule: string;
  last_sync_at: string | null;
  is_active: boolean;
  config_keys: string[];
  created_at: string;
}

interface SyncLogEntry {
  id: number;
  direction: string;
  status: string;
  created_count: number;
  updated_count: number;
  skipped_count: number;
  error_count: number;
  triggered_by: string;
  started_at: string;
  completed_at: string | null;
}

const STATUS_COLORS: Record<string, string> = {
  success: '#10B981', partial: '#F59E0B', failed: '#EF4444', running: '#3B82F6',
};

const TOOL_ICONS: Record<string, string> = {
  jira: '🔷', azure_devops: '🔶', doors: '🏛️',
};

const ASTRA_FIELDS = [
  'title', 'statement', 'rationale', 'req_type', 'priority', 'status', 'level',
];

/* ══════════════════════════════════════
   Component
   ══════════════════════════════════════ */

export default function IntegrationsPage() {
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [configs, setConfigs] = useState<IntegrationConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [projectId, setProjectId] = useState<number | null>(null);

  // Setup wizard
  const [wizardOpen, setWizardOpen] = useState(false);
  const [wizardStep, setWizardStep] = useState(0);
  const [wizardType, setWizardType] = useState<CatalogItem | null>(null);
  const [wizardConfig, setWizardConfig] = useState<Record<string, string>>({});
  const [wizardExtProject, setWizardExtProject] = useState('');
  const [wizardDirection, setWizardDirection] = useState('import');
  const [wizardMapping, setWizardMapping] = useState<Record<string, string>>({
    title: 'title', description: 'statement', priority: 'priority', status: 'status', type: 'req_type',
  });
  const [wizardTesting, setWizardTesting] = useState(false);
  const [wizardTestResult, setWizardTestResult] = useState<boolean | null>(null);
  const [wizardSaving, setWizardSaving] = useState(false);

  // Detail view
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [syncLogs, setSyncLogs] = useState<SyncLogEntry[]>([]);
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    api.get('/projects/').then(r => {
      if (r.data?.length) setProjectId(r.data[0].id);
    }).catch(() => {});
  }, []);

  const loadData = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [catRes, cfgRes] = await Promise.all([
        api.get('/integrations/catalog'),
        api.get('/integrations/', { params: { project_id: projectId } }),
      ]);
      setCatalog(catRes.data || []);
      setConfigs(cfgRes.data || []);
    } catch { /* ignore */ }
    setLoading(false);
  }, [projectId]);

  useEffect(() => { loadData(); }, [loadData]);

  const loadLogs = useCallback(async (configId: number) => {
    try {
      const r = await api.get(`/integrations/${configId}/logs`, { params: { limit: 15 } });
      setSyncLogs(r.data?.items || []);
    } catch { setSyncLogs([]); }
  }, []);

  useEffect(() => { if (selectedId) loadLogs(selectedId); }, [selectedId, loadLogs]);

  // ── Wizard ──

  const startWizard = (item: CatalogItem) => {
    setWizardType(item);
    setWizardConfig({});
    setWizardExtProject('');
    setWizardDirection('import');
    setWizardTestResult(null);
    setWizardStep(0);
    setWizardOpen(true);
  };

  const testConnection = async () => {
    if (!projectId || !wizardType) return;
    setWizardTesting(true);
    setWizardTestResult(null);
    try {
      // Create temporary config to test
      const createRes = await api.post('/integrations/', {
        project_id: projectId,
        integration_type: wizardType.type,
        config: wizardConfig,
        external_project: wizardExtProject,
        sync_direction: wizardDirection,
        field_mapping: wizardMapping,
      });
      const testRes = await api.post(`/integrations/${createRes.data.id}/test`);
      setWizardTestResult(testRes.data.success);
      // If test passed, keep the config; otherwise delete it
      if (!testRes.data.success) {
        await api.delete(`/integrations/${createRes.data.id}`);
      } else {
        // Update configs list
        loadData();
        setSelectedId(createRes.data.id);
        setWizardOpen(false);
      }
    } catch {
      setWizardTestResult(false);
    }
    setWizardTesting(false);
  };

  const triggerSync = async (direction: string) => {
    if (!selectedId) return;
    setSyncing(true);
    try {
      await api.post(`/integrations/${selectedId}/sync`, null, {
        params: { direction },
      });
      loadLogs(selectedId);
      loadData();
    } catch { /* ignore */ }
    setSyncing(false);
  };

  const deleteIntegration = async (id: number) => {
    try {
      await api.delete(`/integrations/${id}`);
      setConfigs(c => c.filter(x => x.id !== id));
      if (selectedId === id) setSelectedId(null);
    } catch { /* ignore */ }
  };

  const selected = configs.find(c => c.id === selectedId);

  const inputClass = 'w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50';
  const selectClass = inputClass + ' appearance-none';

  if (loading && !configs.length) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Integrations</h1>
          <p className="mt-0.5 text-sm text-slate-500">Connect ASTRA to external ALM tools</p>
        </div>
      </div>

      {/* ── Integration Catalog (when no configs exist yet, or always at top) ── */}
      {configs.length === 0 && (
        <div className="mb-6 rounded-xl border border-astra-border bg-astra-surface p-6">
          <h2 className="mb-4 text-sm font-bold text-slate-200">Available Connectors</h2>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            {catalog.map(item => (
              <button key={item.type} onClick={() => startWizard(item)}
                className="rounded-xl border border-astra-border bg-astra-surface-alt p-5 text-left transition hover:border-blue-500/30">
                <div className="mb-2 text-2xl">{TOOL_ICONS[item.type] || '🔗'}</div>
                <h3 className="text-sm font-bold text-slate-200">{item.name}</h3>
                <p className="mt-1 text-xs text-slate-500 leading-relaxed">{item.description}</p>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[300px_1fr]">
        {/* ── Sidebar: configured integrations ── */}
        <div className="space-y-2">
          {configs.map(c => (
            <button key={c.id} onClick={() => setSelectedId(c.id)}
              className={`w-full rounded-xl border p-4 text-left transition ${
                selectedId === c.id
                  ? 'border-blue-500/40 bg-blue-500/10'
                  : 'border-astra-border bg-astra-surface hover:border-blue-500/20'
              }`}>
              <div className="flex items-center gap-2.5 mb-1">
                <span className="text-lg">{TOOL_ICONS[c.integration_type] || '🔗'}</span>
                <span className="text-sm font-bold text-slate-200 flex-1 truncate">{c.display_name}</span>
                <span className={`h-2 w-2 rounded-full ${c.is_active ? 'bg-emerald-400' : 'bg-slate-500'}`} />
              </div>
              <div className="text-[10px] text-slate-500">
                {c.external_project || 'No project mapped'} · {c.sync_direction}
                {c.last_sync_at && ` · Last: ${new Date(c.last_sync_at).toLocaleDateString()}`}
              </div>
            </button>
          ))}

          {configs.length > 0 && (
            <button onClick={() => {
              const item = catalog[0];
              if (item) startWizard(item);
            }}
              className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-dashed border-astra-border-light py-3 text-xs font-semibold text-slate-500 transition hover:border-blue-500/40 hover:text-blue-400">
              <Plus className="h-3.5 w-3.5" /> Add Integration
            </button>
          )}
        </div>

        {/* ── Main: detail panel ── */}
        {selected ? (
          <div className="space-y-4">
            {/* Header */}
            <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">{TOOL_ICONS[selected.integration_type] || '🔗'}</span>
                  <div>
                    <h2 className="text-base font-bold text-slate-100">{selected.display_name}</h2>
                    <p className="text-xs text-slate-500">
                      {selected.integration_type} · {selected.external_project} · {selected.sync_direction}
                    </p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => deleteIntegration(selected.id)}
                    className="rounded-lg border border-red-500/20 px-3 py-1.5 text-xs font-semibold text-red-400 transition hover:bg-red-500/10">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>

              {/* Sync buttons */}
              <div className="flex gap-2">
                <button onClick={() => triggerSync('import')} disabled={syncing}
                  className="flex items-center gap-1.5 rounded-lg bg-blue-500 px-4 py-2 text-xs font-semibold text-white transition hover:bg-blue-600 disabled:opacity-50">
                  {syncing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ArrowDownToLine className="h-3.5 w-3.5" />}
                  Import from {selected.integration_type}
                </button>
                {(selected.sync_direction === 'export' || selected.sync_direction === 'bidirectional') && (
                  <button onClick={() => triggerSync('export')} disabled={syncing}
                    className="flex items-center gap-1.5 rounded-lg border border-astra-border px-4 py-2 text-xs font-semibold text-slate-300 transition hover:bg-astra-surface-hover disabled:opacity-50">
                    <ArrowUpFromLine className="h-3.5 w-3.5" /> Export to {selected.integration_type}
                  </button>
                )}
              </div>
            </div>

            {/* Field Mapping */}
            <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
              <h3 className="mb-3 text-sm font-bold text-slate-200">Field Mapping</h3>
              <div className="space-y-2">
                {Object.entries(selected.field_mapping || {}).map(([ext, astra]) => (
                  <div key={ext} className="flex items-center gap-2 rounded-lg bg-astra-surface-alt p-2.5">
                    <span className="flex-1 text-xs font-semibold text-slate-300">{ext}</span>
                    <ChevronRight className="h-3 w-3 text-slate-600" />
                    <span className="flex-1 text-xs font-semibold text-blue-400">{astra}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Sync History */}
            <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
              <h3 className="mb-3 flex items-center gap-2 text-sm font-bold text-slate-200">
                <Clock className="h-4 w-4 text-slate-400" /> Sync History
              </h3>
              {syncLogs.length === 0 ? (
                <p className="text-xs text-slate-500 italic">No sync history</p>
              ) : (
                <div className="space-y-2">
                  {syncLogs.map(log => (
                    <div key={log.id} className="flex items-center gap-2.5 rounded-lg bg-astra-surface-alt p-3">
                      <div className="h-2 w-2 rounded-full" style={{ background: STATUS_COLORS[log.status] || '#666' }} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-semibold text-slate-300 capitalize">{log.direction}</span>
                          <span className="rounded-full px-2 py-0.5 text-[9px] font-bold"
                            style={{ background: (STATUS_COLORS[log.status] || '#666') + '20', color: STATUS_COLORS[log.status] || '#666' }}>
                            {log.status}
                          </span>
                        </div>
                        <div className="mt-0.5 text-[10px] text-slate-500">
                          +{log.created_count} created · {log.updated_count} updated · {log.skipped_count} skipped
                          {log.error_count > 0 && <span className="text-red-400"> · {log.error_count} errors</span>}
                          {' · '}{log.triggered_by} · {log.started_at ? new Date(log.started_at).toLocaleString() : ''}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center rounded-xl border border-astra-border bg-astra-surface py-20">
            <div className="text-center">
              <Link2 className="mx-auto mb-3 h-10 w-10 text-slate-600" />
              <p className="text-sm text-slate-400">Select an integration to manage</p>
            </div>
          </div>
        )}
      </div>

      {/* ── Setup Wizard Modal ── */}
      {wizardOpen && wizardType && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-2xl border border-astra-border bg-astra-surface p-6 shadow-2xl">
            <div className="mb-5 flex items-center gap-3">
              <span className="text-2xl">{TOOL_ICONS[wizardType.type] || '🔗'}</span>
              <div>
                <h3 className="text-sm font-bold text-slate-100">Connect {wizardType.name}</h3>
                <p className="text-xs text-slate-500">Step {wizardStep + 1} of 2</p>
              </div>
            </div>

            {wizardStep === 0 && (
              <div className="space-y-3">
                {wizardType.config_fields.map(f => (
                  <div key={f.key}>
                    <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">{f.label}</label>
                    <input
                      type={f.type === 'password' ? 'password' : 'text'}
                      value={wizardConfig[f.key] || ''}
                      onChange={e => setWizardConfig({ ...wizardConfig, [f.key]: e.target.value })}
                      className={inputClass}
                      placeholder={f.placeholder}
                    />
                  </div>
                ))}
                <div>
                  <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">External Project</label>
                  <input value={wizardExtProject} onChange={e => setWizardExtProject(e.target.value)}
                    className={inputClass} placeholder="Project key or name" />
                </div>
                <div>
                  <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">Sync Direction</label>
                  <select value={wizardDirection} onChange={e => setWizardDirection(e.target.value)} className={selectClass}>
                    <option value="import">Import (External → ASTRA)</option>
                    <option value="export">Export (ASTRA → External)</option>
                    <option value="bidirectional">Bidirectional</option>
                  </select>
                </div>
              </div>
            )}

            {wizardStep === 1 && (
              <div className="space-y-3">
                <p className="text-xs text-slate-400 mb-3">Map external fields to ASTRA requirement fields:</p>
                {Object.entries(wizardMapping).map(([ext, astra]) => (
                  <div key={ext} className="flex items-center gap-2">
                    <input value={ext} onChange={e => {
                      const updated = { ...wizardMapping };
                      const val = updated[ext];
                      delete updated[ext];
                      updated[e.target.value] = val;
                      setWizardMapping(updated);
                    }} className={inputClass + ' flex-1'} placeholder="External field" />
                    <ChevronRight className="h-3.5 w-3.5 text-slate-600 shrink-0" />
                    <select value={astra} onChange={e => setWizardMapping({ ...wizardMapping, [ext]: e.target.value })}
                      className={selectClass + ' flex-1'}>
                      {ASTRA_FIELDS.map(f => <option key={f} value={f}>{f}</option>)}
                    </select>
                  </div>
                ))}
              </div>
            )}

            {wizardTestResult !== null && (
              <div className={`mt-3 flex items-center gap-2 rounded-lg border px-3 py-2 text-xs ${
                wizardTestResult
                  ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-400'
                  : 'border-red-500/20 bg-red-500/10 text-red-400'
              }`}>
                {wizardTestResult ? <CheckCircle className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
                {wizardTestResult ? 'Connection successful! Integration saved.' : 'Connection failed. Check credentials.'}
              </div>
            )}

            <div className="mt-5 flex gap-2">
              <button onClick={() => setWizardOpen(false)}
                className="flex-1 rounded-lg border border-astra-border py-2.5 text-sm font-semibold text-slate-400 transition hover:text-slate-200">
                Cancel
              </button>
              {wizardStep === 0 ? (
                <button onClick={() => setWizardStep(1)}
                  className="flex-1 rounded-lg bg-blue-500 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-600">
                  Next: Field Mapping
                </button>
              ) : (
                <>
                  <button onClick={() => setWizardStep(0)}
                    className="rounded-lg border border-astra-border px-4 py-2.5 text-sm font-semibold text-slate-400 transition hover:text-slate-200">
                    Back
                  </button>
                  <button onClick={testConnection} disabled={wizardTesting}
                    className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-emerald-500 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-600 disabled:opacity-50">
                    {wizardTesting ? <Loader2 className="h-4 w-4 animate-spin" /> : <TestTube className="h-4 w-4" />}
                    Test &amp; Save
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
