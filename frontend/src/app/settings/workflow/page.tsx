'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Plus, Trash2, GripVertical, Save, Loader2, Shield,
  ChevronRight, Clock, Users, CheckCircle, AlertTriangle,
  Pencil, Power, PowerOff, ArrowUp, ArrowDown,
} from 'lucide-react';
import api from '@/lib/api';

interface Stage {
  id?: number;
  stage_number: number;
  name: string;
  description: string;
  required_role: string;
  required_count: number;
  timeout_hours: number;
  auto_escalate_to_role: string;
  can_parallel: boolean;
  require_signature: boolean;
}

interface Workflow {
  id: number;
  name: string;
  description: string;
  project_id: number;
  entity_type: string;
  status: string;
  stage_count: number;
  stages?: Stage[];
  created_at: string;
}

const ROLES = [
  { value: '', label: 'Any Role' },
  { value: 'admin', label: 'Admin' },
  { value: 'project_manager', label: 'Project Manager' },
  { value: 'requirements_engineer', label: 'Requirements Engineer' },
  { value: 'reviewer', label: 'Reviewer' },
  { value: 'stakeholder', label: 'Stakeholder' },
  { value: 'developer', label: 'Developer' },
];

const STAGE_COLORS = ['#3B82F6', '#8B5CF6', '#10B981', '#F59E0B', '#EF4444', '#06B6D4'];

function emptyStage(num: number): Stage {
  return {
    stage_number: num, name: '', description: '', required_role: '',
    required_count: 1, timeout_hours: 0, auto_escalate_to_role: '',
    can_parallel: false, require_signature: true,
  };
}

export default function WorkflowSettingsPage() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [selected, setSelected] = useState<Workflow | null>(null);
  const [stages, setStages] = useState<Stage[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');

  // Use first project for now (could add project selector)
  const [projectId, setProjectId] = useState<number | null>(null);

  useEffect(() => {
    api.get('/projects/').then(r => {
      if (r.data?.length) setProjectId(r.data[0].id);
    }).catch(() => {});
  }, []);

  const loadWorkflows = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const r = await api.get('/workflows/', { params: { project_id: projectId } });
      setWorkflows(r.data || []);
    } catch { /* ignore */ }
    setLoading(false);
  }, [projectId]);

  useEffect(() => { loadWorkflows(); }, [loadWorkflows]);

  const selectWorkflow = async (wf: Workflow) => {
    try {
      const r = await api.get(`/workflows/${wf.id}`);
      setSelected(r.data);
      setStages(r.data.stages || []);
    } catch { /* ignore */ }
  };

  const createWorkflow = async () => {
    if (!projectId) return;
    try {
      const r = await api.post('/workflows/', {
        name: 'New Approval Workflow',
        description: '',
        project_id: projectId,
        entity_type: 'requirement',
      });
      await loadWorkflows();
      selectWorkflow(r.data);
    } catch { /* ignore */ }
  };

  const seedDefault = async () => {
    if (!projectId) return;
    try {
      const r = await api.post(`/workflows/seed-default/${projectId}`);
      await loadWorkflows();
      setSelected(r.data);
      setStages(r.data.stages || []);
      setMsg('Default 4-stage workflow created');
    } catch (e: any) { setMsg(e.response?.data?.detail || 'Error'); }
  };

  const saveStages = async () => {
    if (!selected) return;
    setSaving(true);
    setMsg('');
    try {
      // Delete old stages and re-create (simplest approach)
      for (const existing of (selected.stages || [])) {
        if (existing.id) {
          await api.delete(`/workflows/stages/${existing.id}`).catch(() => {});
        }
      }
      for (const s of stages) {
        await api.post(`/workflows/${selected.id}/stages`, s);
      }
      setMsg('Stages saved');
      selectWorkflow(selected);
    } catch { setMsg('Error saving stages'); }
    setSaving(false);
  };

  const addStage = () => {
    const next = stages.length + 1;
    setStages([...stages, emptyStage(next)]);
  };

  const removeStage = (idx: number) => {
    const updated = stages.filter((_, i) => i !== idx).map((s, i) => ({
      ...s, stage_number: i + 1,
    }));
    setStages(updated);
  };

  const moveStage = (idx: number, dir: -1 | 1) => {
    const target = idx + dir;
    if (target < 0 || target >= stages.length) return;
    const copy = [...stages];
    [copy[idx], copy[target]] = [copy[target], copy[idx]];
    setStages(copy.map((s, i) => ({ ...s, stage_number: i + 1 })));
  };

  const updateStage = (idx: number, field: string, value: any) => {
    const copy = [...stages];
    (copy[idx] as any)[field] = value;
    setStages(copy);
  };

  const toggleStatus = async () => {
    if (!selected) return;
    const newStatus = selected.status === 'active' ? 'inactive' : 'active';
    try {
      await api.patch(`/workflows/${selected.id}`, { status: newStatus });
      setSelected({ ...selected, status: newStatus });
      loadWorkflows();
    } catch { /* ignore */ }
  };

  const inputClass = 'w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-1.5 text-xs text-slate-200 outline-none focus:border-blue-500/50';
  const selectClass = inputClass + ' appearance-none';
  const btnPrimary = 'flex items-center gap-1.5 rounded-lg bg-blue-500 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-blue-600 disabled:opacity-50';

  if (loading && !workflows.length) {
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
          <h1 className="text-xl font-bold tracking-tight">Approval Workflows</h1>
          <p className="mt-0.5 text-sm text-slate-500">Configure multi-stage approval pipelines per project</p>
        </div>
        <div className="flex gap-2">
          <button onClick={seedDefault} className="flex items-center gap-1.5 rounded-lg border border-astra-border px-3 py-1.5 text-xs font-semibold text-slate-300 transition hover:bg-astra-surface-hover">
            <Shield className="h-3.5 w-3.5 text-emerald-400" /> Seed Default 4-Stage
          </button>
          <button onClick={createWorkflow} className={btnPrimary}>
            <Plus className="h-3.5 w-3.5" /> New Workflow
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[280px_1fr]">
        {/* Sidebar — workflow list */}
        <div className="space-y-2">
          {workflows.map(wf => (
            <button key={wf.id} onClick={() => selectWorkflow(wf)}
              className={`w-full rounded-xl border p-4 text-left transition ${
                selected?.id === wf.id
                  ? 'border-blue-500/40 bg-blue-500/10'
                  : 'border-astra-border bg-astra-surface hover:border-blue-500/20'
              }`}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-bold text-slate-200 truncate">{wf.name}</span>
                <span className={`rounded-full px-2 py-0.5 text-[9px] font-bold ${
                  wf.status === 'active' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-slate-500/15 text-slate-400'
                }`}>{wf.status}</span>
              </div>
              <div className="text-[10px] text-slate-500">{wf.stage_count} stage{wf.stage_count !== 1 ? 's' : ''} · {wf.entity_type}</div>
            </button>
          ))}
          {workflows.length === 0 && (
            <div className="rounded-xl border border-astra-border bg-astra-surface p-6 text-center text-xs text-slate-500">
              No workflows yet
            </div>
          )}
        </div>

        {/* Main — stage editor */}
        {selected ? (
          <div className="rounded-xl border border-astra-border bg-astra-surface p-6">
            <div className="mb-5 flex items-center justify-between">
              <div>
                <h2 className="text-base font-bold text-slate-100">{selected.name}</h2>
                <p className="text-xs text-slate-500">{selected.description || 'No description'}</p>
              </div>
              <div className="flex gap-2">
                <button onClick={toggleStatus} className="flex items-center gap-1 rounded-lg border border-astra-border px-2.5 py-1 text-[11px] font-semibold text-slate-400 hover:text-slate-200">
                  {selected.status === 'active'
                    ? <><PowerOff className="h-3 w-3 text-red-400" /> Deactivate</>
                    : <><Power className="h-3 w-3 text-emerald-400" /> Activate</>}
                </button>
                <button onClick={saveStages} disabled={saving} className={btnPrimary}>
                  {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                  Save Stages
                </button>
              </div>
            </div>

            {msg && <div className="mb-4 rounded-lg border border-blue-500/20 bg-blue-500/10 px-3 py-2 text-xs text-blue-300">{msg}</div>}

            {/* Stage pipeline visualization */}
            <div className="mb-6 flex items-center gap-1 overflow-x-auto pb-2">
              {stages.map((s, i) => (
                <div key={i} className="flex items-center gap-1">
                  <div className="flex items-center gap-2 rounded-lg px-3 py-2 border border-astra-border bg-astra-surface-alt min-w-[120px]"
                    style={{ borderLeftColor: STAGE_COLORS[i % STAGE_COLORS.length], borderLeftWidth: 3 }}>
                    <span className="text-[10px] font-bold text-slate-400">#{s.stage_number}</span>
                    <span className="text-xs font-semibold text-slate-200 truncate">{s.name || '(unnamed)'}</span>
                  </div>
                  {i < stages.length - 1 && <ChevronRight className="h-3.5 w-3.5 text-slate-600 shrink-0" />}
                </div>
              ))}
              {stages.length === 0 && (
                <div className="text-xs text-slate-500">No stages — add one below</div>
              )}
            </div>

            {/* Stage cards */}
            <div className="space-y-3">
              {stages.map((stage, idx) => (
                <div key={idx} className="rounded-xl border border-astra-border bg-astra-surface-alt p-4"
                  style={{ borderLeftColor: STAGE_COLORS[idx % STAGE_COLORS.length], borderLeftWidth: 3 }}>
                  <div className="mb-3 flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-300">Stage {stage.stage_number}</span>
                    <div className="flex gap-1">
                      <button onClick={() => moveStage(idx, -1)} disabled={idx === 0}
                        className="p-1 text-slate-500 hover:text-slate-300 disabled:opacity-20"><ArrowUp className="h-3 w-3" /></button>
                      <button onClick={() => moveStage(idx, 1)} disabled={idx === stages.length - 1}
                        className="p-1 text-slate-500 hover:text-slate-300 disabled:opacity-20"><ArrowDown className="h-3 w-3" /></button>
                      <button onClick={() => removeStage(idx)}
                        className="p-1 text-slate-500 hover:text-red-400"><Trash2 className="h-3 w-3" /></button>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                    <div className="col-span-2">
                      <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">Name</label>
                      <input value={stage.name} onChange={e => updateStage(idx, 'name', e.target.value)}
                        className={inputClass} placeholder="e.g. Peer Review" />
                    </div>
                    <div>
                      <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">Required Role</label>
                      <select value={stage.required_role} onChange={e => updateStage(idx, 'required_role', e.target.value)}
                        className={selectClass}>
                        {ROLES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">Approvals Needed</label>
                      <input type="number" min={1} max={10} value={stage.required_count}
                        onChange={e => updateStage(idx, 'required_count', parseInt(e.target.value) || 1)}
                        className={inputClass} />
                    </div>
                    <div>
                      <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">Timeout (hours)</label>
                      <input type="number" min={0} value={stage.timeout_hours}
                        onChange={e => updateStage(idx, 'timeout_hours', parseInt(e.target.value) || 0)}
                        className={inputClass} />
                    </div>
                    <div>
                      <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">Escalate To</label>
                      <select value={stage.auto_escalate_to_role || ''}
                        onChange={e => updateStage(idx, 'auto_escalate_to_role', e.target.value)}
                        className={selectClass}>
                        {ROLES.map(r => <option key={r.value} value={r.value}>{r.label || 'None'}</option>)}
                      </select>
                    </div>
                    <div className="flex items-end gap-4">
                      <label className="flex items-center gap-1.5 text-[11px] text-slate-400 cursor-pointer">
                        <input type="checkbox" checked={stage.require_signature}
                          onChange={e => updateStage(idx, 'require_signature', e.target.checked)}
                          className="rounded border-astra-border" />
                        E-Signature
                      </label>
                      <label className="flex items-center gap-1.5 text-[11px] text-slate-400 cursor-pointer">
                        <input type="checkbox" checked={stage.can_parallel}
                          onChange={e => updateStage(idx, 'can_parallel', e.target.checked)}
                          className="rounded border-astra-border" />
                        Parallel
                      </label>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <button onClick={addStage}
              className="mt-4 flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-astra-border-light py-3 text-xs font-semibold text-slate-500 transition hover:border-blue-500/40 hover:text-blue-400">
              <Plus className="h-3.5 w-3.5" /> Add Stage
            </button>
          </div>
        ) : (
          <div className="flex items-center justify-center rounded-xl border border-astra-border bg-astra-surface py-20">
            <div className="text-center">
              <Shield className="mx-auto mb-3 h-10 w-10 text-slate-600" />
              <p className="text-sm text-slate-400">Select a workflow to edit its stages</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
