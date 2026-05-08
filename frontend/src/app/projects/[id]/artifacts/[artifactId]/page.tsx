'use client';

/**
 * ASTRA — Source Artifact Detail / Edit Page
 * ==========================================
 * File: frontend/src/app/projects/[id]/artifacts/[artifactId]/page.tsx
 *
 * Shows: metadata, attached file (with upload/replace/download), and
 * the list of requirements that trace back to this artifact.
 */

import { useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft, Edit, Save, Trash2, Download, Upload, FileText, X,
} from 'lucide-react';
import { artifactsAPI } from '@/lib/api';
import {
  ArtifactType,
  ARTIFACT_TYPE_LABELS,
  ARTIFACT_TYPE_COLORS,
  LEVEL_COLORS,
  Requirement,
  SourceArtifact,
} from '@/lib/types';

// Phase 0 Fix 0b Part 3 — autosave the in-progress edit.
import { useFormAutosave } from '@/lib/autosave';
import RestorePromptBanner from '@/components/RestorePromptBanner';

interface EditSourceDraft {
  title: string;
  artifactType: string;
  description: string;
  sourceDate: string;
  participantsText: string;
}

export default function ArtifactDetailPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);
  const artifactId = Number(params.artifactId);

  const [artifact, setArtifact] = useState<SourceArtifact | null>(null);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  // Edit form state
  const [title, setTitle] = useState('');
  const [artifactType, setArtifactType] = useState('document');
  const [description, setDescription] = useState('');
  const [sourceDate, setSourceDate] = useState('');
  const [participantsText, setParticipantsText] = useState('');

  // ── Autosave (only meaningful while editing) ──
  const draftState = useMemo<EditSourceDraft>(() => ({
    title, artifactType, description, sourceDate, participantsText,
  }), [title, artifactType, description, sourceDate, participantsText]);

  const autosave = useFormAutosave<EditSourceDraft>(
    `astra:autosave:source-edit:${artifactId}`,
    draftState,
    { disabled: !editing },
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

  const load = async () => {
    setLoading(true);
    try {
      const [aRes, reqsRes] = await Promise.all([
        artifactsAPI.get(projectId, artifactId),
        artifactsAPI.getRequirements(projectId, artifactId),
      ]);
      const a: SourceArtifact = aRes.data;
      setArtifact(a);
      setRequirements(Array.isArray(reqsRes.data) ? reqsRes.data : []);
      setTitle(a.title);
      setArtifactType(a.artifact_type);
      setDescription(a.description || '');
      setSourceDate(a.source_date ? a.source_date.split('T')[0] : '');
      setParticipantsText((a.participants || []).join(', '));
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load artifact');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [projectId, artifactId]);

  const handleSave = async () => {
    setError('');
    setSaving(true);
    try {
      await artifactsAPI.update(projectId, artifactId, {
        title,
        artifact_type: artifactType,
        description: description || null,
        source_date: sourceDate || null,
        participants: participantsText.split(',').map((s) => s.trim()).filter(Boolean),
      });
      // Phase 0 Fix 0b Part 3: drop the autosaved draft on success.
      autosave.clearDraft();
      setEditing(false);
      await load();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!artifact) return;
    if (!confirm(`Delete artifact "${artifact.artifact_id}"? This cannot be undone.`)) return;
    try {
      await artifactsAPI.delete(projectId, artifactId);
      router.push(`/projects/${projectId}/artifacts`);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Delete failed');
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setError('');
    try {
      await artifactsAPI.uploadFile(projectId, artifactId, f);
      await load();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Upload failed');
    } finally {
      // Reset the file input so re-selecting the same file fires onChange.
      e.target.value = '';
    }
  };

  const handleDownload = async () => {
    try {
      const res = await artifactsAPI.downloadFile(projectId, artifactId);
      const blob = res.data as Blob;
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = artifact?.file_path?.split(/[/\\]/).pop() || 'download';
      a.click();
      window.URL.revokeObjectURL(url);
    } catch {
      setError('Download failed');
    }
  };

  if (loading) {
    return <div className="mx-auto max-w-5xl py-12 text-center text-sm text-slate-500">Loading…</div>;
  }
  if (!artifact) {
    return (
      <div className="mx-auto max-w-5xl">
        <button
          onClick={() => router.push(`/projects/${projectId}/artifacts`)}
          className="mb-4 flex items-center gap-2 text-sm text-slate-500 hover:text-slate-200"
        >
          <ArrowLeft className="h-4 w-4" /> Back to Source Artifacts
        </button>
        <div className="rounded-xl border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-400">
          {error || 'Artifact not found'}
        </div>
      </div>
    );
  }

  const color = ARTIFACT_TYPE_COLORS[artifact.artifact_type as ArtifactType] || '#6B7280';
  const label = ARTIFACT_TYPE_LABELS[artifact.artifact_type as ArtifactType] || artifact.artifact_type;

  return (
    <div className="mx-auto max-w-5xl">
      <button
        onClick={() => router.push(`/projects/${projectId}/artifacts`)}
        className="mb-4 flex items-center gap-2 text-sm text-slate-500 hover:text-slate-200"
      >
        <ArrowLeft className="h-4 w-4" /> Back to Source Artifacts
      </button>

      <div className="mb-6 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="mb-1 flex items-center gap-2">
            <span className="font-mono text-xs text-slate-500">{artifact.artifact_id}</span>
            <span
              className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
              style={{ background: `${color}20`, color }}
            >
              {label}
            </span>
          </div>
          <h1 className="text-xl font-bold tracking-tight text-slate-100">{artifact.title}</h1>
        </div>
        <div className="flex flex-shrink-0 gap-2">
          {!editing && (
            <button
              onClick={() => setEditing(true)}
              className="flex items-center gap-2 rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-1.5 text-xs font-semibold text-slate-300 hover:text-slate-100"
            >
              <Edit className="h-3.5 w-3.5" /> Edit
            </button>
          )}
          <button
            onClick={handleDelete}
            className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-xs font-semibold text-red-400 hover:bg-red-500/20"
          >
            <Trash2 className="h-3.5 w-3.5" /> Delete
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        {/* Main column */}
        <div className="space-y-4 xl:col-span-2">
          <div className="rounded-xl border border-astra-border bg-astra-surface p-6">
            {editing ? (
              <div className="space-y-4">
                {autosave.hasDraft && autosave.draftAge !== null && (
                  <RestorePromptBanner
                    ageMs={autosave.draftAge}
                    onRestore={onRestoreDraft}
                    onDiscard={autosave.clearDraft}
                  />
                )}
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Title"
                  className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
                />
                <select
                  value={artifactType}
                  onChange={(e) => setArtifactType(e.target.value)}
                  className="w-full appearance-none rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
                >
                  {Object.entries(ARTIFACT_TYPE_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={5}
                  placeholder="Description"
                  className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
                />
                <div className="grid grid-cols-2 gap-4">
                  <input
                    type="date"
                    value={sourceDate}
                    onChange={(e) => setSourceDate(e.target.value)}
                    className="rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
                  />
                  <input
                    type="text"
                    value={participantsText}
                    onChange={(e) => setParticipantsText(e.target.value)}
                    placeholder="Participants (comma-separated)"
                    className="rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
                  />
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleSave}
                    disabled={saving}
                    className="flex items-center gap-2 rounded-lg bg-blue-500 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-600 disabled:opacity-40"
                  >
                    <Save className="h-4 w-4" /> {saving ? 'Saving…' : 'Save'}
                  </button>
                  <button
                    onClick={() => { setEditing(false); load(); }}
                    disabled={saving}
                    className="flex items-center gap-2 rounded-lg border border-astra-border bg-astra-surface-alt px-4 py-2 text-sm font-semibold text-slate-300 hover:text-slate-100 disabled:opacity-40"
                  >
                    <X className="h-4 w-4" /> Cancel
                  </button>
                </div>
              </div>
            ) : (
              <>
                <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                  Description
                </h3>
                <p className="whitespace-pre-wrap text-sm text-slate-200">
                  {artifact.description || (
                    <span className="italic text-slate-500">No description</span>
                  )}
                </p>
                {artifact.participants && artifact.participants.length > 0 && (
                  <>
                    <h3 className="mb-2 mt-4 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                      Participants
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {artifact.participants.map((p, i) => (
                        <span
                          key={i}
                          className="rounded bg-astra-surface-alt px-2 py-1 text-xs text-slate-300"
                        >
                          {p}
                        </span>
                      ))}
                    </div>
                  </>
                )}
              </>
            )}
          </div>

          {/* Linked requirements */}
          <div className="rounded-xl border border-astra-border bg-astra-surface p-6">
            <h3 className="mb-3 text-sm font-medium text-slate-200">
              Requirements traced to this artifact ({requirements.length})
            </h3>
            {requirements.length === 0 ? (
              <p className="text-sm italic text-slate-500">
                No requirements link to this artifact yet.
              </p>
            ) : (
              <div className="space-y-1.5">
                {requirements.map((r) => {
                  const lvColor = (LEVEL_COLORS as Record<string, string>)[r.level] || '#6B7280';
                  return (
                    <div
                      key={r.id}
                      onClick={() =>
                        router.push(`/projects/${projectId}/requirements/${r.id}`)
                      }
                      className="flex cursor-pointer items-center gap-3 rounded-lg p-2 hover:bg-astra-surface-alt"
                    >
                      <span
                        className="w-10 rounded px-2 py-0.5 text-center text-[10px] font-bold"
                        style={{ background: `${lvColor}20`, color: lvColor }}
                      >
                        {r.level}
                      </span>
                      <span className="font-mono text-xs text-slate-500">{r.req_id}</span>
                      <span className="flex-1 truncate text-sm text-slate-200">{r.title}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          {/* File attachment */}
          <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
            <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              Attached File
            </h3>
            {artifact.file_path ? (
              <div>
                <div className="mb-3 flex items-center gap-2">
                  <FileText className="h-4 w-4 flex-shrink-0 text-blue-400" />
                  <span className="truncate text-sm text-slate-200">
                    {artifact.file_path.split(/[/\\]/).pop()}
                  </span>
                </div>
                <button
                  onClick={handleDownload}
                  className="mb-2 flex w-full items-center justify-center gap-2 rounded-lg bg-blue-500 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-600"
                >
                  <Download className="h-3.5 w-3.5" /> Download
                </button>
                <label className="block">
                  <span className="mb-1 block text-[10px] text-slate-500">Replace file:</span>
                  <input
                    type="file"
                    onChange={handleFileUpload}
                    accept=".pdf,.docx,.xlsx,.txt,.md,.png,.jpg,.jpeg"
                    className="block w-full text-xs text-slate-300 file:mr-2 file:rounded file:border-0 file:bg-astra-surface-alt file:px-2 file:py-1 file:text-xs file:text-slate-300 file:hover:bg-astra-border"
                  />
                </label>
              </div>
            ) : (
              <label className="block">
                <div className="flex cursor-pointer items-center justify-center gap-2 rounded border-2 border-dashed border-astra-border px-3 py-4 text-xs text-slate-500 hover:border-blue-500/50 hover:text-blue-400">
                  <Upload className="h-4 w-4" /> Upload file
                </div>
                <input
                  type="file"
                  onChange={handleFileUpload}
                  accept=".pdf,.docx,.xlsx,.txt,.md,.png,.jpg,.jpeg"
                  className="hidden"
                />
              </label>
            )}
          </div>

          {/* Metadata */}
          <div className="space-y-2 rounded-xl border border-astra-border bg-astra-surface p-4 text-xs">
            <div>
              <span className="text-slate-500">Source date:</span>{' '}
              <span className="text-slate-200">
                {artifact.source_date
                  ? new Date(artifact.source_date).toLocaleDateString()
                  : '—'}
              </span>
            </div>
            <div>
              <span className="text-slate-500">Created:</span>{' '}
              <span className="text-slate-200">
                {artifact.created_at
                  ? new Date(artifact.created_at).toLocaleDateString()
                  : '—'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
