'use client';

/**
 * ASTRA — Source Artifacts (List Page)
 * =====================================
 * Per-project list of contractual / reference documents that
 * requirements (especially L0) trace back to.
 *
 * File: frontend/src/app/projects/[id]/artifacts/page.tsx
 */

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Plus, Search, FileText, Download } from 'lucide-react';
import { artifactsAPI, projectsAPI } from '@/lib/api';
import {
  ArtifactType,
  ARTIFACT_TYPE_LABELS,
  ARTIFACT_TYPE_ICONS,
  ARTIFACT_TYPE_COLORS,
  SourceArtifactWithStats,
} from '@/lib/types';

export default function ArtifactsListPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);

  const [projectCode, setProjectCode] = useState('');
  const [artifacts, setArtifacts] = useState<SourceArtifactWithStats[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<string>('');

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    projectsAPI.get(projectId)
      .then((res) => { if (mounted) setProjectCode(res.data.code); })
      .catch(() => {});
    artifactsAPI.listWithStats(projectId)
      .then((res) => {
        if (mounted) setArtifacts(Array.isArray(res.data) ? res.data : []);
      })
      .catch(() => { if (mounted) setArtifacts([]); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [projectId]);

  const filtered = artifacts.filter((a) => {
    if (typeFilter && a.artifact_type !== typeFilter) return false;
    if (search) {
      const s = search.toLowerCase();
      return (
        a.title.toLowerCase().includes(s) ||
        a.artifact_id.toLowerCase().includes(s) ||
        (a.description || '').toLowerCase().includes(s)
      );
    }
    return true;
  });

  return (
    <div className="mx-auto max-w-7xl">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Source Artifacts</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            {projectCode ? `${projectCode} · ` : ''}
            Documents, standards, and references that requirements trace back to.
          </p>
        </div>
        <button
          onClick={() => router.push(`/projects/${projectId}/artifacts/new`)}
          className="flex items-center gap-2 rounded-lg bg-blue-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-600"
        >
          <Plus className="h-4 w-4" />
          New Artifact
        </button>
      </div>

      {/* Filters */}
      <div className="mb-4 flex gap-3">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            placeholder="Search by title, ID, or description…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-astra-border bg-astra-surface py-2 pl-10 pr-3 text-sm text-slate-200 placeholder:text-slate-500 outline-none focus:border-blue-500/50"
          />
        </div>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded-lg border border-astra-border bg-astra-surface px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
        >
          <option value="">All Types</option>
          {Object.entries(ARTIFACT_TYPE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      </div>

      {/* Results */}
      {loading ? (
        <div className="py-12 text-center text-sm text-slate-500">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-astra-border bg-astra-surface py-12 text-center">
          <FileText className="mx-auto mb-3 h-12 w-12 text-slate-600" />
          <h3 className="font-medium text-slate-200">No source artifacts yet</h3>
          <p className="mx-auto mb-4 mt-1 max-w-md text-sm text-slate-500">
            Source artifacts capture the origin of requirements (MRDs, SOWs, contract clauses, meeting notes).
          </p>
          <button
            onClick={() => router.push(`/projects/${projectId}/artifacts/new`)}
            className="rounded-lg bg-blue-500 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-600"
          >
            Create the first one
          </button>
        </div>
      ) : (
        <div className="grid gap-3">
          {filtered.map((a) => {
            const color = ARTIFACT_TYPE_COLORS[a.artifact_type as ArtifactType] || '#6B7280';
            const icon = ARTIFACT_TYPE_ICONS[a.artifact_type as ArtifactType] || '📄';
            const label = ARTIFACT_TYPE_LABELS[a.artifact_type as ArtifactType] || a.artifact_type;
            return (
              <div
                key={a.id}
                onClick={() => router.push(`/projects/${projectId}/artifacts/${a.id}`)}
                className="cursor-pointer rounded-xl border border-astra-border bg-astra-surface p-4 transition-all hover:border-blue-500/50 hover:bg-astra-surface-alt"
              >
                <div className="flex items-start gap-4">
                  <div
                    className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-lg text-2xl"
                    style={{ background: `${color}20` }}
                  >
                    {icon}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex items-center gap-2">
                      <span className="font-mono text-xs text-slate-500">{a.artifact_id}</span>
                      <span
                        className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
                        style={{ background: `${color}20`, color }}
                      >
                        {label}
                      </span>
                    </div>
                    <h3 className="mb-1 truncate font-medium text-slate-200">{a.title}</h3>
                    {a.description && (
                      <p className="mb-2 line-clamp-2 text-sm text-slate-500">{a.description}</p>
                    )}
                    <div className="flex items-center gap-4 text-xs text-slate-500">
                      {a.l0_requirement_count > 0 && (
                        <span className="font-semibold text-red-400">
                          {a.l0_requirement_count} L0 req{a.l0_requirement_count !== 1 ? 's' : ''}
                        </span>
                      )}
                      <span>
                        {a.total_requirement_count} total req{a.total_requirement_count !== 1 ? 's' : ''} traced
                      </span>
                      {a.file_path && (
                        <span className="flex items-center gap-1 text-blue-400">
                          <Download className="h-3 w-3" /> File attached
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
