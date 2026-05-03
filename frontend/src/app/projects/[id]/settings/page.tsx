'use client';

/**
 * ASTRA — Project Settings (with Auto-Req Approval Toggle)
 * ============================================================
 * File: frontend/src/app/projects/[id]/settings/page.tsx
 *
 * Sections:
 *   1. General — project name, description
 *   2. Interface Module — auto-requirement approval toggle
 *   3. Danger Zone — archive (placeholder)
 *
 * The toggle calls: PATCH /api/v1/projects/{id}
 *   with { auto_req_approval_required: true/false }
 */

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import {
  Settings, Loader2, Save, AlertTriangle, CheckCircle,
  Cable, Sparkles, ToggleLeft, ToggleRight,
} from 'lucide-react';
import { projectsAPI } from '@/lib/api';
import api from '@/lib/api';

export default function ProjectSettingsPage() {
  const params = useParams();
  const projectId = Number(params.id);

  const [project, setProject] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving]   = useState(false);
  const [msg, setMsg]         = useState('');

  // General
  const [name, setName]               = useState('');
  const [description, setDescription] = useState('');
  const [code, setCode]               = useState('');

  // Interface toggle
  const [autoReqApproval, setAutoReqApproval] = useState(true);
  const [togglingApproval, setTogglingApproval] = useState(false);

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(''), 4000); };

  // ── Load project ──
  useEffect(() => {
    projectsAPI.get(projectId).then(r => {
      const p = r.data;
      setProject(p);
      setName(p.name);
      setDescription(p.description || '');
      setCode(p.code);
      // Load toggle value — defaults to true if field doesn't exist yet
      setAutoReqApproval(p.auto_req_approval_required !== false);
    }).catch(() => {}).finally(() => setLoading(false));
  }, [projectId]);

  // ── Save general settings ──
  const handleSaveGeneral = async () => {
    setSaving(true);
    try {
      await api.patch(`/projects/${projectId}`, { name, description });
      flash('Settings saved');
    } catch (e: any) {
      flash(e?.response?.data?.detail || 'Save failed');
    }
    setSaving(false);
  };

  // ── Toggle auto-req approval ──
  const handleToggleApproval = async () => {
    const newValue = !autoReqApproval;
    setTogglingApproval(true);
    try {
      await api.patch(`/projects/${projectId}`, {
        auto_req_approval_required: newValue,
      });
      setAutoReqApproval(newValue);
      flash(newValue
        ? 'Enabled — auto-requirements will require manual approval'
        : 'Disabled — auto-requirements will be created directly as draft');
    } catch (e: any) {
      flash(e?.response?.data?.detail || 'Failed to update setting');
    }
    setTogglingApproval(false);
  };

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-xl font-bold tracking-tight">Project Settings</h1>
        <p className="mt-0.5 text-sm text-slate-500">{code} · Configuration and preferences</p>
      </div>

      {/* Toast */}
      {msg && (
        <div className={`mb-4 rounded-lg border px-4 py-3 text-xs flex items-center gap-2 ${
          msg.includes('fail') || msg.includes('error')
            ? 'border-red-500/20 bg-red-500/10 text-red-400'
            : 'border-emerald-500/20 bg-emerald-500/10 text-emerald-400'
        }`}>
          {msg.includes('fail') || msg.includes('error')
            ? <AlertTriangle className="h-3.5 w-3.5" />
            : <CheckCircle className="h-3.5 w-3.5" />}
          {msg}
        </div>
      )}

      {/* ── Section 1: General ── */}
      <div className="rounded-xl border border-astra-border bg-astra-surface p-5 mb-6">
        <h2 className="text-sm font-bold text-slate-200 mb-4 flex items-center gap-2">
          <Settings className="h-4 w-4 text-slate-500" /> General
        </h2>

        <div className="space-y-4">
          <div>
            <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">
              Project Code
            </label>
            <input value={code} disabled
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-400 cursor-not-allowed" />
            <p className="mt-1 text-[10px] text-slate-600">Project codes cannot be changed after creation.</p>
          </div>

          <div>
            <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">
              Project Name
            </label>
            <input value={name} onChange={e => setName(e.target.value)}
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
          </div>

          <div>
            <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block">
              Description
            </label>
            <textarea value={description} onChange={e => setDescription(e.target.value)} rows={3}
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50 resize-none" />
          </div>

          <div className="flex justify-end">
            <button onClick={handleSaveGeneral} disabled={saving}
              className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-40">
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
              Save Changes
            </button>
          </div>
        </div>
      </div>

      {/* ── Section 2: Interface Module Settings ── */}
      <div className="rounded-xl border border-astra-border bg-astra-surface p-5 mb-6">
        <h2 className="text-sm font-bold text-slate-200 mb-4 flex items-center gap-2">
          <Cable className="h-4 w-4 text-blue-400" /> Interface Module
        </h2>

        <div className="rounded-lg border border-astra-border bg-astra-bg p-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1.5">
                <Sparkles className="h-4 w-4 text-violet-400" />
                <h3 className="text-sm font-semibold text-slate-200">
                  Require manual approval for auto-generated requirements
                </h3>
              </div>

              {autoReqApproval ? (
                <div className="space-y-1.5">
                  <p className="text-[12px] text-slate-400 leading-relaxed">
                    When enabled, auto-generated interface requirements go to the
                    Auto Requirements review page for approval before being added to the project.
                    Engineers must explicitly approve or reject each generated requirement.
                  </p>
                  <div className="flex items-center gap-2 pt-1">
                    <div className="h-2 w-2 rounded-full bg-emerald-400" />
                    <span className="text-[11px] font-semibold text-emerald-400">
                      ENABLED — Manual approval required
                    </span>
                  </div>
                  <p className="text-[10px] text-slate-500">
                    The &quot;Auto Requirements&quot; item appears in the sidebar under AI Tools.
                    Requirements are created with status &quot;pending_review&quot;.
                  </p>
                </div>
              ) : (
                <div className="space-y-1.5">
                  <p className="text-[12px] text-slate-400 leading-relaxed">
                    When disabled, auto-generated requirements are created directly in &quot;draft&quot; status.
                    No review step is needed — requirements immediately appear in the main requirements list.
                    Trace links are auto-created at generation time.
                  </p>
                  <div className="flex items-center gap-2 pt-1">
                    <div className="h-2 w-2 rounded-full bg-slate-500" />
                    <span className="text-[11px] font-semibold text-slate-500">
                      DISABLED — Direct creation as draft
                    </span>
                  </div>
                  <p className="text-[10px] text-slate-500">
                    The &quot;Auto Requirements&quot; sidebar item is hidden.
                    Requirements are created with status &quot;draft&quot; and trace links are auto-created.
                  </p>
                </div>
              )}
            </div>

            <button onClick={handleToggleApproval} disabled={togglingApproval}
              className="flex-shrink-0 mt-1 transition-transform hover:scale-105 disabled:opacity-50">
              {togglingApproval ? (
                <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
              ) : autoReqApproval ? (
                <ToggleRight className="h-10 w-10 text-emerald-400" />
              ) : (
                <ToggleLeft className="h-10 w-10 text-slate-600" />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* ── Section 3: Danger Zone ── */}
      <div className="rounded-xl border border-red-500/20 bg-astra-surface p-5">
        <h2 className="text-sm font-bold text-red-400 mb-4 flex items-center gap-2">
          <AlertTriangle className="h-4 w-4" /> Danger Zone
        </h2>
        <p className="text-[12px] text-slate-400 mb-3">
          These actions are irreversible. Please proceed with caution.
        </p>
        <button disabled
          className="rounded-lg border border-red-500/20 px-4 py-2 text-xs font-semibold text-red-400 opacity-50 cursor-not-allowed">
          Archive Project (coming soon)
        </button>
      </div>
    </div>
  );
}
