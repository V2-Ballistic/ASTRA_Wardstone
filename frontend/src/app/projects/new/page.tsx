/**
 * ASTRA — Create Project Page
 * ==============================
 * File: frontend/src/app/projects/new/page.tsx
 * Path: C:\Users\Mason\Documents\ASTRA\frontend\src\app\projects\new\page.tsx
 */

'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ArrowLeft, Save, Loader2, FolderPlus, Rocket,
  AlertTriangle, CheckCircle, Info,
} from 'lucide-react';
import { projectsAPI } from '@/lib/api';

const TEMPLATES = [
  {
    name: 'Blank Project',
    code: '',
    description: '',
    icon: '📄',
    hint: 'Start from scratch with an empty project.',
  },
  {
    name: 'Aerospace / Defense',
    code: 'DEF',
    description: 'Satellite-deployed missile defense system requiring hierarchical requirements decomposition across five levels (L1–L5) with full traceability per NASA SE Handbook and MIL-STD-882E.',
    icon: '🛰️',
    hint: 'NASA / DoD standards, 5-level hierarchy.',
  },
  {
    name: 'Medical Device',
    code: 'MED',
    description: 'Class II/III medical device requiring FDA 21 CFR Part 820 compliance with design controls, risk management per ISO 14971, and full verification/validation traceability.',
    icon: '🏥',
    hint: 'FDA 21 CFR 820, ISO 14971, IEC 62304.',
  },
  {
    name: 'Automotive',
    code: 'AUTO',
    description: 'ADAS/autonomous driving system requiring ISO 26262 functional safety compliance with ASIL decomposition and full requirements traceability from vehicle to component level.',
    icon: '🚗',
    hint: 'ISO 26262, ASPICE, AUTOSAR.',
  },
];

export default function CreateProjectPage() {
  const router = useRouter();

  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [selectedTemplate, setSelectedTemplate] = useState<number | null>(null);

  const codeValid = /^[A-Z0-9_-]{2,20}$/.test(code);
  const nameValid = name.trim().length >= 3;
  const canSave = codeValid && nameValid && !saving;

  const applyTemplate = (idx: number) => {
    const t = TEMPLATES[idx];
    setSelectedTemplate(idx);
    if (t.code && !code) setCode(t.code);
    if (t.description) setDescription(t.description);
  };

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true);
    setError('');
    try {
      await projectsAPI.create({
        code: code.toUpperCase(),
        name: name.trim(),
        description: description.trim() || undefined,
      });
      router.push('/');
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      if (typeof detail === 'string') {
        setError(detail);
      } else if (Array.isArray(detail)) {
        setError(detail.map((d: any) => d.msg).join('; '));
      } else {
        setError('Failed to create project');
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl">
      {/* Header */}
      <div className="mb-8 flex items-center gap-4">
        <button
          onClick={() => router.push('/')}
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-astra-border text-slate-400 transition hover:border-blue-500/30 hover:text-slate-200"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="flex-1">
          <h1 className="text-xl font-bold tracking-tight text-white">Create New Project</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            Set up a new systems engineering project with requirements tracking
          </p>
        </div>
      </div>

      {error && (
        <div className="mb-5 flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Template Picker */}
      <div className="mb-6">
        <label className="mb-2.5 block text-[10px] font-bold uppercase tracking-widest text-slate-500">
          Quick Start Template
        </label>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {TEMPLATES.map((t, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => applyTemplate(idx)}
              className={`rounded-xl border p-3.5 text-left transition-all ${
                selectedTemplate === idx
                  ? 'border-blue-500/50 bg-blue-500/8 shadow-md shadow-blue-500/10'
                  : 'border-astra-border bg-astra-surface hover:border-slate-600 hover:bg-astra-surface-hover'
              }`}
            >
              <div className="mb-2 text-2xl">{t.icon}</div>
              <div className="text-xs font-semibold text-slate-200">{t.name}</div>
              <div className="mt-0.5 text-[10px] leading-snug text-slate-500">{t.hint}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Form */}
      <div className="space-y-5 rounded-2xl border border-astra-border bg-astra-surface p-6">
        {/* Project Code */}
        <div>
          <label className="mb-1.5 flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-slate-500">
            Project Code
            <span className="font-normal normal-case tracking-normal text-slate-600">
              — unique identifier, 2-20 chars
            </span>
          </label>
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9_-]/g, ''))}
            placeholder="e.g., ASTRA-001, DEF-SAT, MED-PUMP"
            maxLength={20}
            className={`w-full rounded-lg border bg-astra-bg px-4 py-2.5 text-sm font-mono font-semibold tracking-wide text-slate-200 placeholder:text-slate-600 focus:outline-none transition ${
              code.length > 0
                ? codeValid
                  ? 'border-emerald-500/40 focus:border-emerald-500/60'
                  : 'border-red-500/40 focus:border-red-500/60'
                : 'border-astra-border focus:border-blue-500/50'
            }`}
          />
          {code.length > 0 && !codeValid && (
            <div className="mt-1 text-[10px] text-red-400">
              Must be 2-20 characters: uppercase letters, numbers, hyphens, underscores only
            </div>
          )}
        </div>

        {/* Project Name */}
        <div>
          <label className="mb-1.5 block text-[10px] font-bold uppercase tracking-widest text-slate-500">
            Project Name
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g., Satellite Missile Defense System"
            maxLength={255}
            className="w-full rounded-lg border border-astra-border bg-astra-bg px-4 py-2.5 text-sm text-slate-200 placeholder:text-slate-600 focus:border-blue-500/50 focus:outline-none transition"
          />
        </div>

        {/* Description */}
        <div>
          <label className="mb-1.5 flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-slate-500">
            Description
            <span className="font-normal normal-case tracking-normal text-slate-600">— optional</span>
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe the project scope, applicable standards (NASA, DO-178C, ISO 26262), system context, and key engineering domains..."
            rows={5}
            className="w-full rounded-lg border border-astra-border bg-astra-bg px-4 py-2.5 text-sm leading-relaxed text-slate-200 placeholder:text-slate-600 focus:border-blue-500/50 focus:outline-none resize-none transition"
          />
        </div>

        {/* Info box */}
        <div className="flex items-start gap-2.5 rounded-lg border border-blue-500/10 bg-blue-500/5 px-4 py-3">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-blue-400/60" />
          <div className="text-[11px] leading-relaxed text-slate-400">
            After creating the project, you can add requirements, set up traceability links,
            create baselines, and configure team access. The project code will be used as a prefix
            for all requirement IDs (e.g., <span className="font-mono text-blue-400">{code || 'CODE'}-FR-001</span>).
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-between border-t border-astra-border pt-5">
          <button
            onClick={() => router.push('/')}
            className="rounded-lg border border-astra-border px-4 py-2 text-xs font-semibold text-slate-400 transition hover:bg-astra-surface-hover hover:text-slate-200"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={!canSave}
            className="flex items-center gap-2 rounded-lg bg-blue-500 px-6 py-2.5 text-sm font-semibold text-white shadow-lg shadow-blue-500/20 transition hover:bg-blue-600 hover:shadow-blue-500/30 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Rocket className="h-4 w-4" />
            )}
            {saving ? 'Creating…' : 'Create Project'}
          </button>
        </div>
      </div>
    </div>
  );
}
