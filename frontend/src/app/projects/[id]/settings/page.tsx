'use client';

/**
 * ASTRA — Project Settings
 * File: frontend/src/app/projects/[id]/settings/page.tsx
 */

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Settings, Loader2, Save, Users, Shield, Database, AlertTriangle, CheckCircle } from 'lucide-react';
import { projectsAPI } from '@/lib/api';
import api from '@/lib/api';

export default function ProjectSettingsPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);

  const [project, setProject] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [code, setCode] = useState('');

  useEffect(() => {
    projectsAPI.get(projectId).then(r => {
      const p = r.data;
      setProject(p); setName(p.name); setDescription(p.description || ''); setCode(p.code);
    }).catch(() => {}).finally(() => setLoading(false));
  }, [projectId]);

  const handleSave = async () => {
    setSaving(true); setMsg('');
    try {
      await api.patch(`/projects/${projectId}`, { name, description });
      setMsg('Settings saved');
      setTimeout(() => setMsg(''), 3000);
    } catch (e: any) { setMsg(e.response?.data?.detail || 'Save failed'); }
    setSaving(false);
  };

  if (loading) return <div className="flex min-h-[60vh] items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-blue-500" /></div>;

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6">
        <h1 className="text-xl font-bold tracking-tight">Project Settings</h1>
        <p className="mt-0.5 text-sm text-slate-500">{code} · Configuration and team management</p>
      </div>

      {msg && (
        <div className={`mb-4 rounded-lg border px-4 py-3 text-xs ${msg.includes('fail') ? 'border-red-500/20 bg-red-500/10 text-red-400' : 'border-emerald-500/20 bg-emerald-500/10 text-emerald-400'}`}>
          {msg}
        </div>
      )}

      <div className="space-y-6">
        {/* General */}
        <div className="rounded-xl border border-astra-border bg-astra-surface p-6">
          <h2 className="mb-4 text-sm font-bold text-slate-200">General</h2>
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">Project Code</label>
              <input value={code} disabled className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2.5 text-sm text-slate-400 outline-none opacity-60" />
              <p className="mt-1 text-[10px] text-slate-500">Project code cannot be changed after creation.</p>
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">Name</label>
              <input value={name} onChange={(e) => setName(e.target.value)} className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">Description</label>
              <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <button onClick={handleSave} disabled={saving} className="flex items-center gap-2 rounded-lg bg-blue-500 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-600 disabled:opacity-50">
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />} {saving ? 'Saving…' : 'Save Changes'}
            </button>
          </div>
        </div>

        {/* System Info */}
        <div className="rounded-xl border border-astra-border bg-astra-surface p-6">
          <h2 className="mb-4 text-sm font-bold text-slate-200">System Information</h2>
          <div className="space-y-2 font-mono text-xs">
            {[['API', 'http://localhost:8000'], ['Database', 'PostgreSQL 16'], ['Frontend', 'Next.js 14 / React 18'], ['Backend', 'FastAPI / Python 3.12'], ['Version', 'ASTRA v1.0.0']].map(([k, v]) => (
              <div key={k} className="flex justify-between border-b border-astra-border py-2 last:border-0">
                <span className="text-slate-500">{k}</span><span className="text-slate-300">{v}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
