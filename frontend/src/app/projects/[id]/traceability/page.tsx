'use client';

/**
 * ASTRA — Traceability (Project-Scoped)
 * ========================================
 * File: frontend/src/app/projects/[id]/traceability/page.tsx
 *
 * Three tabs: [Matrix] [Graph] [AI Suggestions]
 * AI Suggestions shows pending trace suggestions with bulk accept/reject.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  Loader2, RefreshCw, Grid3X3, GitBranch, AlertTriangle, CheckCircle,
  FileText, Shield, Link2, ChevronRight, Sparkles, Check, X, Eye,
} from 'lucide-react';
import clsx from 'clsx';
import { traceabilityAPI, projectsAPI, requirementsAPI } from '@/lib/api';
import {
  STATUS_COLORS, STATUS_LABELS, LEVEL_COLORS,
  type RequirementStatus, type RequirementLevel,
} from '@/lib/types';

// Optional AI
let aiAPI: any = null;
try { aiAPI = require('@/lib/ai-api').aiAPI; } catch {}

// ── Coverage bar ──
function CoverageBar({ label, value, pct, total, color }: {
  label: string; value: number; pct: number; total: number; color: string;
}) {
  return (
    <div className="flex-1">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[11px] text-slate-400">{label}</span>
        <span className="text-[11px] font-bold" style={{ color }}>{value}/{total} ({pct}%)</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-astra-surface-alt">
        <div className="h-full rounded-full transition-all duration-700" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

// ── Matrix cell ──
function MatrixCell({ count, hasItems }: { count: number; hasItems: boolean }) {
  return (
    <div className="flex items-center justify-center">
      <span className={clsx('rounded-full px-2.5 py-0.5 text-[11px] font-bold',
        hasItems ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/10 text-red-400/60')}>
        {count}
      </span>
    </div>
  );
}

// ── AI Suggestion card ──
function SuggestionCard({ suggestion, selected, onToggle }: {
  suggestion: any; selected: boolean; onToggle: () => void;
}) {
  return (
    <div className={clsx(
      'flex items-center gap-3 rounded-xl border p-4 transition',
      selected ? 'border-blue-500/30 bg-blue-500/5' : 'border-astra-border bg-astra-surface hover:border-blue-500/20'
    )}>
      <button onClick={onToggle}
        className={clsx('flex h-5 w-5 items-center justify-center rounded border transition',
          selected ? 'border-blue-500 bg-blue-500 text-white' : 'border-slate-600')}>
        {selected && <Check className="h-3 w-3" />}
      </button>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-mono text-xs font-semibold text-blue-400">{suggestion.target_req_id}</span>
          <span className="rounded-full bg-astra-surface-alt px-2 py-0.5 text-[9px] font-semibold text-slate-400 capitalize">
            {suggestion.suggested_link_type}
          </span>
          <span className="text-[10px] font-semibold text-violet-400">
            {(suggestion.confidence * 100).toFixed(0)}% confidence
          </span>
        </div>
        <p className="text-xs text-slate-400 truncate">{suggestion.target_title || suggestion.explanation}</p>
        {suggestion.explanation && (
          <p className="mt-1 text-[10px] text-slate-500 line-clamp-2">{suggestion.explanation}</p>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  Main Page
// ══════════════════════════════════════

type ViewMode = 'matrix' | 'graph' | 'suggestions';

export default function TraceabilityPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);

  const [projectCode, setProjectCode] = useState('');
  const [viewMode, setViewMode] = useState<ViewMode>('matrix');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Data
  const [matrixData, setMatrixData] = useState<any[]>([]);
  const [coverage, setCoverage] = useState<any>(null);
  const [graphData, setGraphData] = useState<{ nodes: any[]; edges: any[] }>({ nodes: [], edges: [] });

  // AI Suggestions
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [selectedSuggs, setSelectedSuggs] = useState<Set<number>>(new Set());

  // ── Fetch core data ──
  const fetchData = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError('');
    try {
      const [matRes, covRes, graphRes, projRes] = await Promise.all([
        traceabilityAPI.getMatrix(projectId),
        traceabilityAPI.getCoverage(projectId),
        traceabilityAPI.getGraph(projectId),
        projectsAPI.get(projectId).catch(() => null),
      ]);
      setMatrixData(matRes.data.matrix || []);
      setCoverage(covRes.data);
      setGraphData(graphRes.data || { nodes: [], edges: [] });
      if (projRes?.data) setProjectCode(projRes.data.code);
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Failed to load traceability data');
    }
    setLoading(false);
  }, [projectId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // ── Fetch AI suggestions ──
  const fetchSuggestions = useCallback(async () => {
    if (!projectId || !aiAPI) return;
    setSuggestionsLoading(true);
    try {
      // Fetch requirements, then get suggestions for each (batch)
      const reqsRes = await requirementsAPI.list(projectId, { limit: 200 });
      const reqs = Array.isArray(reqsRes.data) ? reqsRes.data : [];
      const allSuggs: any[] = [];
      // Fetch for first 20 requirements to keep it reasonable
      const batch = reqs.slice(0, 20);
      const results = await Promise.allSettled(
        batch.map((r: any) => aiAPI.getTraceSuggestions(r.id, projectId))
      );
      results.forEach((res: any) => {
        if (res.status === 'fulfilled' && res.value?.data?.suggestions) {
          allSuggs.push(...res.value.data.suggestions.map((s: any, i: number) => ({
            ...s, _idx: allSuggs.length + i,
            source_req_id: res.value.data.req_id,
          })));
        }
      });
      setSuggestions(allSuggs);
    } catch {}
    setSuggestionsLoading(false);
  }, [projectId]);

  // Load suggestions when tab selected
  useEffect(() => {
    if (viewMode === 'suggestions' && suggestions.length === 0) fetchSuggestions();
  }, [viewMode, fetchSuggestions, suggestions.length]);

  // ── Selection ──
  const toggleSugg = (idx: number) => {
    setSelectedSuggs((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx); else next.add(idx);
      return next;
    });
  };
  const selectAllSuggs = () => setSelectedSuggs(new Set(suggestions.map((_, i) => i)));
  const clearSuggSelection = () => setSelectedSuggs(new Set());

  // ── Accept selected ──
  const handleAcceptSelected = async () => {
    const toAccept = suggestions.filter((_, i) => selectedSuggs.has(i));
    for (const s of toAccept) {
      try {
        await traceabilityAPI.createLink({
          source_type: 'requirement', source_id: s.source_id,
          target_type: s.target_type || 'requirement', target_id: s.target_id,
          link_type: s.suggested_link_type || 'dependency',
          description: `AI suggested: ${s.explanation || ''}`.substring(0, 500),
        });
        if (s.suggestion_id && aiAPI) {
          await aiAPI.submitFeedback(s.suggestion_id, 'accepted').catch(() => {});
        }
      } catch {}
    }
    // Remove accepted from list
    setSuggestions((prev) => prev.filter((_, i) => !selectedSuggs.has(i)));
    setSelectedSuggs(new Set());
    await fetchData(); // Refresh matrix/coverage
  };

  // ── Reject selected ──
  const handleRejectSelected = async () => {
    const toReject = suggestions.filter((_, i) => selectedSuggs.has(i));
    for (const s of toReject) {
      if (s.suggestion_id && aiAPI) {
        await aiAPI.submitFeedback(s.suggestion_id, 'rejected').catch(() => {});
      }
    }
    setSuggestions((prev) => prev.filter((_, i) => !selectedSuggs.has(i)));
    setSelectedSuggs(new Set());
  };

  const total = coverage?.total || matrixData.length || 0;

  if (loading) return <div className="flex min-h-[60vh] items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-blue-500" /></div>;

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Traceability</h1>
          <p className="mt-1 text-sm text-slate-500">{projectCode} · Requirements verification traceability</p>
        </div>
        <button onClick={fetchData} className="rounded-full border border-astra-border p-2 text-slate-400 transition hover:text-slate-200">
          <RefreshCw className="h-3.5 w-3.5" />
        </button>
      </div>

      {error && <div className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">{error}</div>}

      {/* Coverage Summary */}
      {coverage && total > 0 && (
        <div className="mb-6 rounded-xl border border-astra-border bg-astra-surface p-5">
          <h3 className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            <Shield className="h-3.5 w-3.5 text-blue-400" /> Traceability Coverage
          </h3>
          <div className="flex gap-6">
            <CoverageBar label="Source Artifacts" value={coverage.with_source || 0} pct={coverage.with_source_pct || 0} total={total} color="#10B981" />
            <CoverageBar label="Children" value={coverage.with_children || 0} pct={coverage.with_children_pct || 0} total={total} color="#3B82F6" />
            <CoverageBar label="Verification" value={coverage.with_verification || 0} pct={coverage.with_verification_pct || 0} total={total} color="#8B5CF6" />
            <CoverageBar label="Orphans" value={coverage.orphans || 0} pct={coverage.orphan_pct || 0} total={total} color="#EF4444" />
          </div>
        </div>
      )}

      {/* View tabs */}
      <div className="mb-4 flex items-center gap-3">
        <div className="flex rounded-lg border border-astra-border overflow-hidden">
          {([
            { key: 'matrix' as ViewMode, icon: Grid3X3, label: 'Matrix' },
            { key: 'graph' as ViewMode, icon: GitBranch, label: 'Graph' },
            { key: 'suggestions' as ViewMode, icon: Sparkles, label: 'AI Suggestions' },
          ]).map((tab) => (
            <button key={tab.key} onClick={() => setViewMode(tab.key)}
              className={clsx('flex items-center gap-1.5 px-4 py-2 text-xs font-semibold transition',
                viewMode === tab.key ? 'bg-blue-500 text-white' : 'bg-astra-surface text-slate-400 hover:text-slate-200')}>
              <tab.icon className="h-3.5 w-3.5" /> {tab.label}
              {tab.key === 'suggestions' && suggestions.length > 0 && (
                <span className="rounded-full bg-violet-500/20 px-1.5 py-0.5 text-[9px] font-bold text-violet-400">
                  {suggestions.length}
                </span>
              )}
            </button>
          ))}
        </div>
        <span className="text-[11px] text-slate-500">{total} requirements · {graphData.edges.length} links</span>
      </div>

      {/* ── Matrix View ── */}
      {viewMode === 'matrix' && (
        matrixData.length === 0 ? (
          <div className="rounded-xl border border-dashed border-astra-border-light bg-astra-surface-alt py-16 text-center">
            <FileText className="mx-auto mb-3 h-8 w-8 text-slate-600" />
            <p className="text-sm text-slate-500">No requirements to display. Create requirements first.</p>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-astra-border bg-astra-surface">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-astra-border bg-astra-surface-alt text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  <th className="px-4 py-3">Req ID</th>
                  <th className="px-2 py-3">Lvl</th>
                  <th className="px-4 py-3">Title</th>
                  <th className="px-4 py-3 text-center">Status</th>
                  <th className="px-4 py-3 text-center">Sources</th>
                  <th className="px-4 py-3 text-center">Children</th>
                  <th className="px-4 py-3 text-center">V&V</th>
                  <th className="px-4 py-3 text-center">Total</th>
                </tr>
              </thead>
              <tbody>
                {matrixData.map((row) => {
                  const lvl = (row.level || 'L1') as RequirementLevel;
                  const sc = STATUS_COLORS[row.status as RequirementStatus];
                  const hasNoTraces = row.source_artifact_count === 0 && row.children_count === 0 && row.verification_count === 0;
                  const hasAll = row.source_artifact_count > 0 && row.children_count > 0 && row.verification_count > 0;
                  return (
                    <tr key={row.id} className={clsx('border-b border-astra-border/50 transition hover:bg-astra-surface-hover cursor-pointer',
                      hasNoTraces ? 'bg-red-500/[0.03]' : hasAll ? 'bg-emerald-500/[0.02]' : '')}
                      onClick={() => router.push(`/requirements/${row.id}`)}>
                      <td className="px-4 py-2.5"><span className="font-mono text-xs font-semibold text-blue-400">{row.req_id}</span></td>
                      <td className="px-2 py-2.5">
                        <span className="rounded-full px-1.5 py-0.5 text-[9px] font-bold" style={{ background: `${LEVEL_COLORS[lvl]}20`, color: LEVEL_COLORS[lvl] }}>{lvl}</span>
                      </td>
                      <td className="px-4 py-2.5"><span className="text-[13px] text-slate-200 truncate block max-w-[300px]">{row.title}</span></td>
                      <td className="px-4 py-2.5 text-center">
                        <span className="inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold" style={{ background: sc?.bg, color: sc?.text }}>
                          {STATUS_LABELS[row.status as RequirementStatus] || row.status}
                        </span>
                      </td>
                      <td className="px-4 py-2.5"><MatrixCell count={row.source_artifact_count} hasItems={row.source_artifact_count > 0} /></td>
                      <td className="px-4 py-2.5"><MatrixCell count={row.children_count} hasItems={row.children_count > 0} /></td>
                      <td className="px-4 py-2.5"><MatrixCell count={row.verification_count} hasItems={row.verification_count > 0} /></td>
                      <td className="px-4 py-2.5 text-center"><span className="text-xs font-semibold text-slate-400">{row.total_links}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {/* Footer */}
            <div className="border-t border-astra-border px-4 py-3 flex items-center gap-6 bg-astra-surface-alt">
              <span className="text-[11px] text-slate-500">{matrixData.length} requirements</span>
              <div className="flex items-center gap-1.5">
                <div className="h-2 w-2 rounded-full bg-emerald-400" />
                <span className="text-[11px] text-slate-500">{matrixData.filter((r) => r.source_artifact_count > 0 && r.children_count > 0 && r.verification_count > 0).length} fully traced</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="h-2 w-2 rounded-full bg-red-400" />
                <span className="text-[11px] text-slate-500">{matrixData.filter((r) => r.source_artifact_count === 0 && r.children_count === 0 && r.verification_count === 0).length} no traces</span>
              </div>
            </div>
          </div>
        )
      )}

      {/* ── Graph View ── */}
      {viewMode === 'graph' && (
        <div className="rounded-xl border border-astra-border bg-astra-surface p-8 text-center">
          <GitBranch className="mx-auto mb-3 h-10 w-10 text-slate-600" />
          <h3 className="text-sm font-semibold text-slate-300 mb-1">Interactive Graph View</h3>
          <p className="text-xs text-slate-500">
            {graphData.nodes.length} nodes · {graphData.edges.length} edges
          </p>
          <p className="mt-2 text-[10px] text-slate-600">
            Full D3 force graph available in the original /traceability page. Use Matrix or AI Suggestions for now.
          </p>
        </div>
      )}

      {/* ── AI Suggestions View ── */}
      {viewMode === 'suggestions' && (
        <div>
          {/* Bulk action bar */}
          {selectedSuggs.size > 0 && (
            <div className="mb-4 flex items-center gap-3 rounded-xl border border-blue-500/20 bg-blue-500/5 px-4 py-3">
              <span className="text-xs font-semibold text-blue-300">{selectedSuggs.size} selected</span>
              <div className="flex-1" />
              <button onClick={handleAcceptSelected}
                className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-1.5 text-[11px] font-semibold text-white hover:bg-emerald-600">
                <Check className="h-3 w-3" /> Accept Selected
              </button>
              <button onClick={handleRejectSelected}
                className="flex items-center gap-1.5 rounded-lg border border-red-500/30 px-3 py-1.5 text-[11px] font-semibold text-red-400 hover:bg-red-500/10">
                <X className="h-3 w-3" /> Reject Selected
              </button>
              <button onClick={clearSuggSelection}
                className="rounded-lg p-1.5 text-slate-500 hover:text-slate-300">
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}

          {/* Controls */}
          <div className="mb-4 flex items-center gap-3">
            <button onClick={fetchSuggestions} disabled={suggestionsLoading}
              className="flex items-center gap-1.5 rounded-lg border border-violet-500/30 bg-violet-500/10 px-3 py-1.5 text-[11px] font-semibold text-violet-400 hover:bg-violet-500/20 disabled:opacity-50">
              {suggestionsLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
              {suggestionsLoading ? 'Scanning…' : 'Rescan'}
            </button>
            {suggestions.length > 0 && (
              <button onClick={selectedSuggs.size === suggestions.length ? clearSuggSelection : selectAllSuggs}
                className="rounded-lg border border-astra-border px-3 py-1.5 text-[11px] font-semibold text-slate-400 hover:text-slate-200">
                {selectedSuggs.size === suggestions.length ? 'Deselect All' : 'Select All'}
              </button>
            )}
            <span className="text-[11px] text-slate-500">{suggestions.length} suggestion{suggestions.length !== 1 ? 's' : ''}</span>
          </div>

          {/* Suggestions list */}
          {suggestionsLoading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="h-6 w-6 animate-spin text-violet-400" />
            </div>
          ) : suggestions.length === 0 ? (
            <div className="rounded-xl border border-dashed border-astra-border-light bg-astra-surface-alt py-16 text-center">
              <Sparkles className="mx-auto mb-3 h-8 w-8 text-slate-600" />
              <h3 className="text-sm font-semibold text-slate-300 mb-1">No AI Suggestions</h3>
              <p className="text-xs text-slate-500">
                AI semantic analysis hasn't found any missing trace links, or the embedding provider isn't configured.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {/* Group by source requirement */}
              {(() => {
                const grouped: Record<string, any[]> = {};
                suggestions.forEach((s, i) => {
                  const key = s.source_req_id || `req-${s.source_id}`;
                  if (!grouped[key]) grouped[key] = [];
                  grouped[key].push({ ...s, _globalIdx: i });
                });
                return Object.entries(grouped).map(([reqId, items]) => (
                  <div key={reqId}>
                    <div className="mb-2 flex items-center gap-2">
                      <span className="font-mono text-xs font-semibold text-blue-400">{reqId}</span>
                      <span className="text-[10px] text-slate-500">{items.length} suggestion{items.length !== 1 ? 's' : ''}</span>
                    </div>
                    <div className="space-y-2 ml-4 mb-4">
                      {items.map((s) => (
                        <SuggestionCard key={s._globalIdx} suggestion={s}
                          selected={selectedSuggs.has(s._globalIdx)}
                          onToggle={() => toggleSugg(s._globalIdx)} />
                      ))}
                    </div>
                  </div>
                ));
              })()}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
