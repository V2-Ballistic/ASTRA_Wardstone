'use client';

/**
 * ASTRA — New Source Artifact Form
 * =================================
 * File: frontend/src/app/projects/[id]/artifacts/new/page.tsx
 */

import { useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Save, Loader2 } from 'lucide-react';
import { artifactsAPI } from '@/lib/api';
import { ARTIFACT_TYPE_LABELS } from '@/lib/types';

// Phase 0 Fix 0b Part 3 — recover unsaved drafts on session timeout.
import { useFormAutosave } from '@/lib/autosave';
import RestorePromptBanner from '@/components/RestorePromptBanner';

interface NewSourceDraft {
  title: string;
  artifactType: string;
  description: string;
  sourceDate: string;
  participantsText: string;
}

export default function NewArtifactPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);

  const [title, setTitle] = useState('');
  const [artifactType, setArtifactType] = useState<string>('document');
  const [description, setDescription] = useState('');
  const [sourceDate, setSourceDate] = useState('');
  const [participantsText, setParticipantsText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // ── Autosave (text fields only — files cannot be persisted to localStorage) ──
  const draftState = useMemo<NewSourceDraft>(() => ({
    title, artifactType, description, sourceDate, participantsText,
  }), [title, artifactType, description, sourceDate, participantsText]);

  const autosave = useFormAutosave<NewSourceDraft>(
    `astra:autosave:source-new:project-${projectId}`,
    draftState,
  );

  const onRestoreDraft = () => {
    const draft = autosave.restoreDraft();
    if (!draft) return;
    setTitle(draft.title);
    setArtifactType(draft.artifactType);
    setDescription(draft.description);
    setSourceDate(draft.sourceDate);
    setParticipantsText(draft.participantsText);
    autosave.clearDraft();
  };

  const canSave = title.trim().length >= 3;

  const handleSave = async () => {
    if (!canSave) {
      setError('Title is required (min 3 characters)');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const created = await artifactsAPI.create(projectId, {
        title: title.trim(),
        artifact_type: artifactType,
        description: description.trim() || undefined,
        source_date: sourceDate || undefined,
        participants: participantsText
          ? participantsText.split(',').map((s) => s.trim()).filter(Boolean)
          : [],
      });

      if (file) {
        try {
          await artifactsAPI.uploadFile(projectId, created.data.id, file);
        } catch (e: any) {
          // The artifact was created — surface the upload error but don't lose the row.
          setError(
            'Artifact created but file upload failed: ' +
              (e?.response?.data?.detail || 'unknown error') +
              ". Open the artifact to retry the upload.",
          );
          router.push(`/projects/${projectId}/artifacts/${created.data.id}`);
          return;
        }
      }

      // Phase 0 Fix 0b Part 3: drop the autosaved draft on success.
      autosave.clearDraft();
      router.push(`/projects/${projectId}/artifacts/${created.data.id}`);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to create artifact');
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl">
      <button
        onClick={() => router.push(`/projects/${projectId}/artifacts`)}
        className="mb-4 flex items-center gap-2 text-sm text-slate-500 hover:text-slate-200"
      >
        <ArrowLeft className="h-4 w-4" /> Back to Source Artifacts
      </button>

      <h1 className="mb-1 text-xl font-bold tracking-tight">New Source Artifact</h1>
      <p className="mb-6 text-sm text-slate-500">
        Document the origin of one or more requirements (MRD, SOW, contract clause, meeting notes…).
      </p>

      {autosave.hasDraft && autosave.draftAge !== null && (
        <RestorePromptBanner
          ageMs={autosave.draftAge}
          onRestore={onRestoreDraft}
          onDiscard={autosave.clearDraft}
        />
      )}

      <div className="space-y-4 rounded-xl border border-astra-border bg-astra-surface p-6">
        <div>
          <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Title <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g., Mission Requirements Document v2.1"
            className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
          />
        </div>

        <div>
          <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Type <span className="text-red-400">*</span>
          </label>
          <select
            value={artifactType}
            onChange={(e) => setArtifactType(e.target.value)}
            className="w-full appearance-none rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2.5 pr-8 text-sm text-slate-200 outline-none focus:border-blue-500/50"
          >
            {Object.entries(ARTIFACT_TYPE_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Description
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            placeholder="Brief description of what this artifact contains and how it relates to the project…"
            className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              Source Date
            </label>
            <input
              type="date"
              value={sourceDate}
              onChange={(e) => setSourceDate(e.target.value)}
              className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              Participants
            </label>
            <input
              type="text"
              value={participantsText}
              onChange={(e) => setParticipantsText(e.target.value)}
              placeholder="Comma-separated names"
              className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
            />
          </div>
        </div>

        <div>
          <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Attach File <span className="font-normal text-slate-600">(optional)</span>
          </label>
          <input
            type="file"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            accept=".pdf,.docx,.xlsx,.txt,.md,.png,.jpg,.jpeg"
            className="block w-full text-sm text-slate-300 file:mr-3 file:rounded file:border-0 file:bg-blue-500 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-white file:hover:bg-blue-600"
          />
          <p className="mt-1 text-[10px] text-slate-500">
            PDF, DOCX, XLSX, TXT, MD, or images up to 50 MB.
          </p>
        </div>

        {error && (
          <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        )}

        <div className="flex gap-3 pt-2">
          <button
            onClick={handleSave}
            disabled={!canSave || saving}
            className="flex items-center gap-2 rounded-lg bg-blue-500 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-600 disabled:opacity-40"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            {saving ? 'Saving…' : 'Create Artifact'}
          </button>
          <button
            onClick={() => router.push(`/projects/${projectId}/artifacts`)}
            disabled={saving}
            className="rounded-lg border border-astra-border bg-astra-surface-alt px-4 py-2.5 text-sm font-semibold text-slate-300 hover:text-slate-100 disabled:opacity-40"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
