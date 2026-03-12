'use client';

/**
 * ASTRA — Requirement Detail (Project-Scoped)
 * ===============================================
 * File: frontend/src/app/projects/[id]/requirements/[reqId]/page.tsx
 *
 * Tabs: [Overview] [Traces] [Impact] [AI Quality] [History] [Comments]
 * AI integrations: Writer launcher, Decompose button, Duplicate checker,
 *   TraceSuggestionsPanel, VerificationSuggestionPanel, Impact preview
 */

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft, Loader2, Edit3, Save, X, CheckCircle, AlertTriangle,
  Clock, GitBranch, Link2, MessageSquare, ChevronRight, Trash2,
  Copy, Sparkles, Zap, Shield, FileText, ChevronDown,
} from 'lucide-react';
import clsx from 'clsx';
import { requirementsAPI } from '@/lib/api';
import {
  STATUS_COLORS, STATUS_LABELS, LEVEL_COLORS, LEVEL_LABELS,
  PRIORITY_COLORS, TYPE_PREFIXES,
  type RequirementStatus, type RequirementLevel, type Priority,
} from '@/lib/types';

// Optional AI APIs — graceful if not present
let aiAPI: any = null;
let aiWriterAPI: any = null;
try { aiAPI = require('@/lib/ai-api').aiAPI; } catch {}
try { aiWriterAPI = require('@/lib/ai-writer-api').aiWriterAPI; } catch {}

// ══════════════════════════════════════
//  Status transitions
// ══════════════════════════════════════

const TRANSITIONS: Record<string, string[]> = {
  draft: ['under_review'],
  under_review: ['approved', 'draft'],
  approved: ['baselined', 'under_review', 'implemented'],
  baselined: ['under_review'],
  implemented: ['verified', 'under_review'],
  verified: ['validated', 'under_review'],
  validated: [],
  deferred: ['draft'],
  deleted: [],
};

// ══════════════════════════════════════
//  Inline Editable Components
// ══════════════════════════════════════

function EditableText({ label, value, onSave, multiline, showQuality, rationale }:
  { label: string; value: string; onSave: (v: string) => void; multiline?: boolean; showQuality?: boolean; rationale?: string }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [quality, setQuality] = useState<any>(null);

  useEffect(() => { setDraft(value); }, [value]);

  // Live quality check
  useEffect(() => {
    if (!showQuality || !editing) return;
    const t = setTimeout(() => {
      if (draft.trim().length > 5) {
        requirementsAPI.qualityCheck(draft, label === 'Title' ? draft : '', rationale || '')
          .then((res) => setQuality(res.data))
          .catch(() => {});
      }
    }, 500);
    return () => clearTimeout(t);
  }, [draft, editing, showQuality, rationale, label]);

  if (editing) {
    return (
      <div className="rounded-xl border border-blue-500/30 bg-astra-surface p-4">
        <div className="mb-2 flex items-center justify-between">
          <label className="text-[10px] font-semibold uppercase tracking-wider text-blue-400">{label}</label>
          <div className="flex gap-1.5">
            <button onClick={() => { onSave(draft); setEditing(false); }}
              className="flex items-center gap-1 rounded-md bg-blue-500 px-2.5 py-1 text-[10px] font-semibold text-white hover:bg-blue-600">
              <Save className="h-3 w-3" /> Save
            </button>
            <button onClick={() => { setDraft(value); setEditing(false); }}
              className="rounded-md border border-astra-border px-2 py-1 text-[10px] text-slate-400 hover:text-slate-200">
              <X className="h-3 w-3" />
            </button>
          </div>
        </div>
        {multiline ? (
          <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={4}
            className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
        ) : (
          <input value={draft} onChange={(e) => setDraft(e.target.value)}
            className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
        )}
        {quality && showQuality && (
          <div className="mt-2 flex items-center gap-3">
            <span className="text-[10px] font-semibold" style={{ color: quality.score >= 80 ? '#10B981' : quality.score >= 60 ? '#F59E0B' : '#EF4444' }}>
              Score: {quality.score}
            </span>
            {quality.warnings?.length > 0 && (
              <span className="text-[10px] text-amber-400">{quality.warnings.length} warning{quality.warnings.length !== 1 ? 's' : ''}</span>
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="group cursor-pointer rounded-xl border border-astra-border bg-astra-surface p-4 transition hover:border-blue-500/20" onClick={() => setEditing(true)}>
      <div className="mb-1.5 flex items-center justify-between">
        <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{label}</label>
        <Edit3 className="h-3 w-3 text-slate-600 opacity-0 transition group-hover:opacity-100 group-hover:text-blue-400" />
      </div>
      <p className={clsx('text-sm leading-relaxed', value ? 'text-slate-200' : 'text-slate-600 italic')}>
        {value || `No ${label.toLowerCase()} set`}
      </p>
    </div>
  );
}

function EditableSelect({ label, value, options, onSave, colorMap }:
  { label: string; value: string; options: { value: string; label: string }[]; onSave: (v: string) => void; colorMap?: Record<string, any> }) {
  const [editing, setEditing] = useState(false);
  if (editing) {
    return (
      <div>
        <span className="text-[11px] text-slate-500">{label}</span>
        <div className="mt-1 flex flex-wrap gap-1">
          {options.map((o) => (
            <button key={o.value} onClick={() => { onSave(o.value); setEditing(false); }}
              className={clsx('rounded-full px-2.5 py-1 text-[10px] font-semibold transition',
                value === o.value ? 'ring-2 ring-blue-500' : 'border border-astra-border hover:border-blue-500/30'
              )}
              style={colorMap?.[o.value] ? { background: colorMap[o.value]?.bg, color: colorMap[o.value]?.text } : {}}>
              {o.label}
            </button>
          ))}
        </div>
      </div>
    );
  }
  const sc = colorMap?.[value];
  return (
    <div className="group flex items-center justify-between cursor-pointer" onClick={() => setEditing(true)}>
      <span className="text-[11px] text-slate-500">{label}</span>
      <div className="flex items-center gap-1.5">
        {sc && <div className="h-2 w-2 rounded-full" style={{ background: sc?.text || sc }} />}
        <span className="text-xs font-semibold" style={{ color: sc?.text || sc || '#94A3B8' }}>
          {options.find((o) => o.value === value)?.label || value}
        </span>
        <Edit3 className="h-3 w-3 text-slate-600 opacity-0 group-hover:opacity-100 group-hover:text-blue-400" />
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  History Entry
// ══════════════════════════════════════

function HistoryEntry({ entry }: { entry: any }) {
  const labels: Record<string, string> = {
    title: 'Title', statement: 'Statement', rationale: 'Rationale', status: 'Status',
    priority: 'Priority', level: 'Level', req_type: 'Type', created: 'Created',
  };
  const label = labels[entry.field_changed] || entry.field_changed;
  const isCreation = entry.field_changed === 'created';

  return (
    <div className="flex gap-3 border-b border-astra-border py-3 last:border-0">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-astra-surface-alt">
        {isCreation ? <CheckCircle className="h-3.5 w-3.5 text-emerald-400" /> : <Edit3 className="h-3.5 w-3.5 text-blue-400" />}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-200">{entry.changed_by}</span>
          <span className="text-[10px] text-slate-500">v{entry.version}</span>
        </div>
        {isCreation ? (
          <div className="mt-0.5 text-xs text-slate-400">{entry.change_description}</div>
        ) : (
          <div className="mt-1">
            <span className="text-[11px] font-semibold text-slate-400">{label}: </span>
            {entry.old_value && <span className="text-[11px] text-red-400/70 line-through mr-1">{String(entry.old_value).substring(0, 80)}</span>}
            <span className="text-[11px] text-emerald-400">{String(entry.new_value).substring(0, 80)}</span>
          </div>
        )}
      </div>
      <div className="shrink-0 text-[10px] text-slate-500 whitespace-nowrap">
        {entry.changed_at ? new Date(entry.changed_at).toLocaleString() : ''}
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  Comment
// ══════════════════════════════════════

function CommentItem({ comment, onReply }: { comment: any; onReply: (id: number) => void }) {
  const initials = comment.author_name
    ? comment.author_name.split(' ').map((n: string) => n[0]).join('').toUpperCase().slice(0, 2) : '??';
  return (
    <div className="flex gap-3 py-3 border-b border-astra-border/50 last:border-0">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500/30 to-violet-500/30 text-[9px] font-bold text-blue-300">
        {initials}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-200">{comment.author_name || comment.author_username}</span>
          <span className="text-[10px] text-slate-500">{comment.created_at ? new Date(comment.created_at).toLocaleString() : ''}</span>
        </div>
        <p className="mt-1 text-xs text-slate-300 leading-relaxed">{comment.content}</p>
        <button onClick={() => onReply(comment.id)} className="mt-1 text-[10px] text-blue-400 hover:text-blue-300">Reply</button>
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  AI Quality Tab Content
// ══════════════════════════════════════

function AIQualityTab({ req, projectId }: { req: any; projectId: number }) {
  const [deepQuality, setDeepQuality] = useState<any>(null);
  const [verification, setVerification] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const runAnalysis = async () => {
    setLoading(true);
    try {
      const [qRes, vRes] = await Promise.all([
        requirementsAPI.qualityCheck(req.statement, req.title, req.rationale || ''),
        aiAPI?.getVerificationSuggestion(req.id).catch(() => null),
      ]);
      setDeepQuality(qRes.data);
      setVerification(vRes?.data || null);
    } catch {}
    setLoading(false);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold text-slate-400">AI Quality Analysis</h4>
        <button onClick={runAnalysis} disabled={loading}
          className="flex items-center gap-1.5 rounded-lg bg-violet-500/10 border border-violet-500/30 px-3 py-1.5 text-[11px] font-semibold text-violet-400 hover:bg-violet-500/20 disabled:opacity-50">
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
          {loading ? 'Analyzing…' : 'Run Analysis'}
        </button>
      </div>

      {deepQuality && (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <span className="text-2xl font-bold" style={{ color: deepQuality.score >= 80 ? '#10B981' : deepQuality.score >= 60 ? '#F59E0B' : '#EF4444' }}>
              {deepQuality.score}
            </span>
            <span className="text-xs text-slate-400">/ 100</span>
            <span className={clsx('rounded-full px-2 py-0.5 text-[10px] font-semibold',
              deepQuality.passed ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400')}>
              {deepQuality.passed ? 'PASS' : 'NEEDS WORK'}
            </span>
          </div>
          {deepQuality.warnings?.length > 0 && (
            <div className="space-y-1">
              <h5 className="text-[10px] font-semibold text-amber-400 uppercase tracking-wider">Warnings</h5>
              {deepQuality.warnings.map((w: string, i: number) => (
                <div key={i} className="flex items-start gap-2 text-xs text-amber-300">
                  <AlertTriangle className="h-3 w-3 mt-0.5 flex-shrink-0" /> {w}
                </div>
              ))}
            </div>
          )}
          {deepQuality.suggestions?.length > 0 && (
            <div className="space-y-1">
              <h5 className="text-[10px] font-semibold text-blue-400 uppercase tracking-wider">Suggestions</h5>
              {deepQuality.suggestions.map((s: string, i: number) => (
                <div key={i} className="flex items-start gap-2 text-xs text-blue-300">
                  <Sparkles className="h-3 w-3 mt-0.5 flex-shrink-0" /> {s}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {verification && (
        <div className="rounded-xl border border-astra-border bg-astra-surface-alt p-4 mt-4">
          <h5 className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-2">AI Verification Suggestion</h5>
          <div className="space-y-2">
            <div><span className="text-[10px] text-slate-500">Method:</span> <span className="text-xs font-semibold text-slate-200 capitalize">{verification.suggested_method}</span></div>
            <div><span className="text-[10px] text-slate-500">Rationale:</span> <span className="text-xs text-slate-300">{verification.method_rationale}</span></div>
            {verification.suggested_criteria && (
              <div><span className="text-[10px] text-slate-500">Criteria:</span> <span className="text-xs text-slate-300">{verification.suggested_criteria}</span></div>
            )}
            <div className="text-[10px] text-slate-500">Confidence: <span className="font-semibold text-blue-400">{(verification.confidence * 100).toFixed(0)}%</span></div>
          </div>
        </div>
      )}

      {!deepQuality && !loading && (
        <div className="py-8 text-center text-xs text-slate-500">
          Click "Run Analysis" to check this requirement against NASA Appendix C guidelines
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════
//  Impact Tab Content
// ══════════════════════════════════════

function ImpactTab({ req }: { req: any }) {
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [changeDesc, setChangeDesc] = useState('');

  const runImpact = async () => {
    setLoading(true);
    try {
      const res = await require('@/lib/api').default.post('/impact/analyze', {
        requirement_id: req.id,
        change_description: changeDesc || `Analyzing impact for ${req.req_id}`,
      });
      setReport(res.data);
    } catch {}
    setLoading(false);
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">Change Description</label>
        <input value={changeDesc} onChange={(e) => setChangeDesc(e.target.value)}
          placeholder="Describe the proposed change…"
          className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
      </div>
      <button onClick={runImpact} disabled={loading}
        className="flex items-center gap-1.5 rounded-lg bg-blue-500 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-600 disabled:opacity-50">
        {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Zap className="h-3.5 w-3.5" />}
        {loading ? 'Analyzing…' : 'Run Impact Analysis'}
      </button>

      {report && (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <span className={clsx('rounded-full px-3 py-1 text-xs font-bold',
              report.risk_level === 'high' ? 'bg-red-500/15 text-red-400' :
              report.risk_level === 'medium' ? 'bg-amber-500/15 text-amber-400' :
              'bg-emerald-500/15 text-emerald-400')}>
              {report.risk_level?.toUpperCase()} RISK
            </span>
            <span className="text-xs text-slate-400">
              {report.direct_impacts?.length || 0} direct · {report.indirect_impacts?.length || 0} indirect
            </span>
          </div>
          {report.ai_summary && (
            <p className="text-xs text-slate-300 leading-relaxed">{report.ai_summary}</p>
          )}
          {report.direct_impacts?.length > 0 && (
            <div>
              <h5 className="text-[10px] font-semibold text-slate-400 uppercase mb-1">Direct Impacts</h5>
              {report.direct_impacts.map((imp: any, i: number) => (
                <div key={i} className="flex items-center gap-2 py-1 text-xs text-slate-300">
                  <div className="h-1.5 w-1.5 rounded-full bg-red-400" />
                  {imp.entity_type}: {imp.identifier || imp.entity_id} — {imp.impact_description}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {!report && !loading && (
        <div className="py-8 text-center text-xs text-slate-500">
          Run an impact analysis to see which requirements, verifications, and baselines would be affected by changes.
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════
//  Traces Tab Content
// ══════════════════════════════════════

function TracesTab({ req, children }: { req: any; children: any[] }) {
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [loadingSugg, setLoadingSugg] = useState(false);

  const loadSuggestions = async () => {
    if (!aiAPI) return;
    setLoadingSugg(true);
    try {
      const res = await aiAPI.getTraceSuggestions(req.id);
      setSuggestions(res.data?.suggestions || []);
    } catch {}
    setLoadingSugg(false);
  };

  useEffect(() => { loadSuggestions(); }, [req.id]);

  return (
    <div className="space-y-4">
      {/* Existing traces */}
      <div>
        <h4 className="text-xs font-semibold text-slate-400 mb-2">
          Existing Links ({req.trace_count || 0})
        </h4>
        {(req.trace_count || 0) === 0 ? (
          <p className="text-xs text-slate-500">No trace links yet. Create them from the Traceability page.</p>
        ) : (
          <p className="text-xs text-slate-400">{req.trace_count} trace link{req.trace_count !== 1 ? 's' : ''} — view full details on Traceability page.</p>
        )}
      </div>

      {/* Children */}
      {children.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-slate-400 mb-2">Children ({children.length})</h4>
          <div className="space-y-1">
            {children.map((child: any) => {
              const cL = (child.level?.value || child.level || 'L1') as RequirementLevel;
              const cS = (child.status?.value || child.status) as RequirementStatus;
              const cSc = STATUS_COLORS[cS];
              return (
                <Link key={child.id} href={`/requirements/${child.id}`}
                  className="flex items-center gap-3 rounded-lg p-2 transition hover:bg-astra-surface-hover">
                  <span className="rounded-full px-1.5 py-0.5 text-[9px] font-bold" style={{ background: `${LEVEL_COLORS[cL]}20`, color: LEVEL_COLORS[cL] }}>{cL}</span>
                  <span className="font-mono text-xs font-semibold text-blue-400">{child.req_id}</span>
                  <span className="flex-1 truncate text-sm text-slate-300">{child.title}</span>
                  <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold" style={{ background: cSc?.bg, color: cSc?.text }}>{STATUS_LABELS[cS]}</span>
                </Link>
              );
            })}
          </div>
        </div>
      )}

      {/* AI Suggestions */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-xs font-semibold text-slate-400">AI Suggested Links</h4>
          <button onClick={loadSuggestions} disabled={loadingSugg}
            className="text-[10px] text-violet-400 hover:text-violet-300">
            {loadingSugg ? 'Loading…' : 'Refresh'}
          </button>
        </div>
        {suggestions.length > 0 ? (
          <div className="space-y-2">
            {suggestions.map((s, i) => (
              <div key={i} className="flex items-center gap-3 rounded-lg border border-astra-border bg-astra-surface-alt p-3">
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-semibold text-slate-200">{s.target_req_id}</div>
                  <div className="text-[10px] text-slate-500 truncate">{s.target_title || s.explanation}</div>
                </div>
                <span className="text-[10px] text-slate-500 capitalize">{s.suggested_link_type}</span>
                <span className="text-[10px] font-semibold text-blue-400">{(s.confidence * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-slate-500">{loadingSugg ? 'Checking for suggestions…' : 'No AI suggestions available.'}</p>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  Main Page
// ══════════════════════════════════════

type TabKey = 'overview' | 'traces' | 'impact' | 'quality' | 'history' | 'comments';

export default function RequirementDetailPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);
  const reqId = Number(params.reqId);

  const [req, setReq] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [comments, setComments] = useState<any[]>([]);
  const [children, setChildren] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saveMsg, setSaveMsg] = useState('');
  const [activeTab, setActiveTab] = useState<TabKey>('overview');

  // Comments
  const [commentText, setCommentText] = useState('');
  const [replyTo, setReplyTo] = useState<number | null>(null);
  const [postingComment, setPostingComment] = useState(false);

  // AI Writer drawer
  const [writerOpen, setWriterOpen] = useState(false);
  const [writerMode, setWriterMode] = useState<'convert' | 'improve' | 'decompose'>('improve');

  // ── Fetch ──
  const fetchData = useCallback(async () => {
    if (!reqId) return;
    setLoading(true);
    try {
      const [rr, hr, cr] = await Promise.all([
        requirementsAPI.get(reqId),
        requirementsAPI.getHistory(reqId),
        requirementsAPI.getComments(reqId),
      ]);
      setReq(rr.data);
      setHistory(hr.data.history || []);
      setComments(cr.data.comments || []);
      setChildren(rr.data.children || []);
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Failed to load');
    }
    setLoading(false);
  }, [reqId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const saveField = async (field: string, value: any) => {
    try {
      await requirementsAPI.update(reqId, { [field]: value });
      setSaveMsg(`${field} updated`);
      setTimeout(() => setSaveMsg(''), 2000);
      await fetchData();
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Save failed');
    }
  };

  const handlePostComment = async () => {
    if (!commentText.trim()) return;
    setPostingComment(true);
    try {
      await requirementsAPI.postComment(reqId, commentText.trim(), replyTo || undefined);
      setCommentText('');
      setReplyTo(null);
      const cr = await requirementsAPI.getComments(reqId);
      setComments(cr.data.comments || []);
    } catch {}
    setPostingComment(false);
  };

  const handleDelete = async () => {
    if (!confirm(`Soft-delete ${req.req_id}? This can be restored.`)) return;
    try {
      await requirementsAPI.delete(reqId);
      router.push(`/projects/${projectId}/requirements`);
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Delete failed');
    }
  };

  const handleClone = async () => {
    try {
      const res = await requirementsAPI.clone(reqId);
      router.push(`/requirements/${res.data.id}`);
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Clone failed');
    }
  };

  // ── Loading ──
  if (loading) return <div className="flex min-h-[60vh] items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-blue-500" /></div>;
  if (error && !req) return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4">
      <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-6 py-4 text-sm text-red-400">{error}</div>
      <button onClick={() => router.push(`/projects/${projectId}/requirements`)}
        className="flex items-center gap-2 rounded-lg bg-blue-500 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-600">
        <ArrowLeft className="h-4 w-4" /> Back
      </button>
    </div>
  );
  if (!req) return null;

  const status = (req.status?.value || req.status) as RequirementStatus;
  const level = (req.level?.value || req.level || 'L1') as RequirementLevel;
  const priority = (req.priority?.value || req.priority) as Priority;
  const sc = STATUS_COLORS[status];
  const isDeleted = status === 'deleted';
  const allowedStatuses = [status, ...(TRANSITIONS[status] || [])];

  const tabs: { key: TabKey; label: string; icon: any; count: number }[] = [
    { key: 'overview', label: 'Overview', icon: FileText, count: 0 },
    { key: 'traces', label: 'Traces', icon: Link2, count: (req.trace_count || 0) + children.length },
    { key: 'impact', label: 'Impact', icon: Zap, count: 0 },
    { key: 'quality', label: 'AI Quality', icon: Sparkles, count: 0 },
    { key: 'history', label: 'History', icon: Clock, count: history.length },
    { key: 'comments', label: 'Comments', icon: MessageSquare, count: comments.length },
  ];

  const topComments = comments.filter((c) => !c.parent_id);
  const repliesMap: Record<number, any[]> = {};
  comments.filter((c) => c.parent_id).forEach((c) => {
    if (!repliesMap[c.parent_id]) repliesMap[c.parent_id] = [];
    repliesMap[c.parent_id].push(c);
  });

  return (
    <div className="mx-auto max-w-6xl">
      {/* Header */}
      <div className="mb-6 flex items-center gap-3">
        <button onClick={() => router.push(`/projects/${projectId}/requirements`)}
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-astra-border text-slate-400 transition hover:text-slate-200">
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3">
            <span className="rounded-full px-2 py-0.5 text-[10px] font-bold" style={{ background: `${LEVEL_COLORS[level]}20`, color: LEVEL_COLORS[level] }}>{level}</span>
            <span className="font-mono text-lg font-bold text-blue-400">{req.req_id}</span>
            <span className="inline-flex rounded-full px-2.5 py-0.5 text-[10px] font-semibold" style={{ background: sc?.bg, color: sc?.text }}>
              {STATUS_LABELS[status] || status}
            </span>
          </div>
          <h1 className="mt-0.5 text-lg font-bold text-slate-100 truncate">{req.title}</h1>
        </div>
        <div className="flex items-center gap-2">
          {/* Decompose */}
          <button onClick={() => { setWriterMode('decompose'); setWriterOpen(true); }}
            className="flex items-center gap-1.5 rounded-lg border border-violet-500/30 bg-violet-500/10 px-3 py-2 text-[11px] font-semibold text-violet-400 hover:bg-violet-500/20">
            <GitBranch className="h-3.5 w-3.5" /> Decompose
          </button>
          {/* AI Writer */}
          <button onClick={() => { setWriterMode('improve'); setWriterOpen(true); }}
            className="flex items-center gap-1.5 rounded-lg border border-astra-border px-3 py-2 text-[11px] font-semibold text-slate-400 hover:text-slate-200">
            <Sparkles className="h-3.5 w-3.5 text-violet-400" /> AI Improve
          </button>
          {/* Clone */}
          <button onClick={handleClone} className="rounded-lg border border-astra-border p-2 text-slate-400 hover:text-slate-200">
            <Copy className="h-3.5 w-3.5" />
          </button>
          {/* Delete */}
          {!isDeleted && (
            <button onClick={handleDelete} className="rounded-lg border border-red-500/20 p-2 text-red-400/60 hover:text-red-400 hover:bg-red-500/10">
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {saveMsg && (
        <div className="mb-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-4 py-2 text-xs text-emerald-400 flex items-center gap-2">
          <CheckCircle className="h-3.5 w-3.5" /> {saveMsg}
        </div>
      )}
      {isDeleted && (
        <div className="mb-4 rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-3 text-xs text-red-400">
          This requirement has been deleted. Click Restore to recover.
        </div>
      )}

      {/* 2-column layout */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        {/* Left: Tabs */}
        <div className="xl:col-span-2">
          {/* Tab bar */}
          <div className="rounded-xl border border-astra-border bg-astra-surface">
            <div className="flex border-b border-astra-border overflow-x-auto">
              {tabs.map((tab) => {
                const Icon = tab.icon;
                return (
                  <button key={tab.key} onClick={() => setActiveTab(tab.key)}
                    className={clsx('flex items-center gap-1.5 px-4 py-3 text-xs font-semibold transition-all border-b-2 whitespace-nowrap',
                      activeTab === tab.key ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-500 hover:text-slate-300')}>
                    <Icon className="h-3.5 w-3.5" /> {tab.label}
                    {tab.count > 0 && (
                      <span className={clsx('rounded-full px-1.5 py-0.5 text-[10px] font-bold',
                        activeTab === tab.key ? 'bg-blue-500/20 text-blue-400' : 'bg-astra-surface-alt text-slate-500')}>
                        {tab.count}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            <div className="p-5">
              {/* Overview */}
              {activeTab === 'overview' && (
                <div className="space-y-4">
                  <EditableText label="Title" value={req.title || ''} onSave={(v) => saveField('title', v)} />
                  <EditableText label="Requirement Statement" value={req.statement || ''} onSave={(v) => saveField('statement', v)} multiline showQuality rationale={req.rationale || ''} />
                  <EditableText label="Rationale" value={req.rationale || ''} onSave={(v) => saveField('rationale', v)} multiline />
                </div>
              )}

              {/* Traces */}
              {activeTab === 'traces' && <TracesTab req={req} children={children} />}

              {/* Impact */}
              {activeTab === 'impact' && <ImpactTab req={req} />}

              {/* AI Quality */}
              {activeTab === 'quality' && <AIQualityTab req={req} projectId={projectId} />}

              {/* History */}
              {activeTab === 'history' && (
                history.length === 0
                  ? <div className="py-8 text-center text-sm text-slate-500">No change history yet</div>
                  : <div className="max-h-[500px] overflow-y-auto">{history.map((h) => <HistoryEntry key={h.id} entry={h} />)}</div>
              )}

              {/* Comments */}
              {activeTab === 'comments' && (
                <div>
                  {topComments.length === 0 ? (
                    <div className="py-8 text-center text-sm text-slate-500">No comments yet. Start the discussion.</div>
                  ) : (
                    <div className="max-h-[400px] overflow-y-auto">
                      {topComments.map((c) => (
                        <div key={c.id}>
                          <CommentItem comment={c} onReply={setReplyTo} />
                          {repliesMap[c.id]?.map((r) => (
                            <div key={r.id} className="ml-10">
                              <CommentItem comment={r} onReply={setReplyTo} />
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>
                  )}
                  {/* Comment input */}
                  <div className="mt-4 flex gap-2">
                    <input value={commentText} onChange={(e) => setCommentText(e.target.value)}
                      placeholder={replyTo ? `Replying to #${replyTo}…` : 'Add a comment…'}
                      onKeyDown={(e) => e.key === 'Enter' && handlePostComment()}
                      className="flex-1 rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
                    <button onClick={handlePostComment} disabled={!commentText.trim() || postingComment}
                      className="rounded-lg bg-blue-500 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-600 disabled:opacity-50">
                      {postingComment ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Post'}
                    </button>
                    {replyTo && (
                      <button onClick={() => setReplyTo(null)} className="text-xs text-slate-500 hover:text-slate-300">Cancel</button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right sidebar */}
        <div className="space-y-4">
          {/* Quality score */}
          <div className="rounded-xl border border-astra-border bg-astra-surface p-5 text-center">
            <div className="text-3xl font-bold" style={{ color: req.quality_score >= 80 ? '#10B981' : req.quality_score >= 60 ? '#F59E0B' : '#EF4444' }}>
              {req.quality_score}
            </div>
            <div className="mt-0.5 text-[10px] text-slate-500">Quality Score</div>
          </div>

          {/* Properties */}
          <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
            <h3 className="mb-4 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Properties</h3>
            <div className="space-y-4">
              <EditableSelect label="Status" value={status}
                options={allowedStatuses.map((s) => ({ value: s, label: STATUS_LABELS[s as RequirementStatus] || s }))}
                onSave={(v) => saveField('status', v)} colorMap={STATUS_COLORS} />
              <EditableSelect label="Priority" value={priority}
                options={['critical', 'high', 'medium', 'low'].map((p) => ({ value: p, label: p.charAt(0).toUpperCase() + p.slice(1) }))}
                onSave={(v) => saveField('priority', v)} />
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-slate-500">Version</span>
                <span className="font-mono text-xs font-semibold text-slate-300">v{req.version}</span>
              </div>
              {req.parent_id && (
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-slate-500">Parent</span>
                  <Link href={`/requirements/${req.parent_id}`} className="font-mono text-xs font-semibold text-blue-400 hover:text-blue-300">#{req.parent_id}</Link>
                </div>
              )}
            </div>
          </div>

          {/* Stats */}
          <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
            <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Stats</h3>
            <div className="grid grid-cols-2 gap-3">
              <div className="text-center"><div className="text-lg font-bold text-slate-100">{children.length}</div><div className="text-[10px] text-slate-500">Children</div></div>
              <div className="text-center"><div className="text-lg font-bold text-blue-400">{req.trace_count || 0}</div><div className="text-[10px] text-slate-500">Traces</div></div>
              <div className="text-center"><div className="text-lg font-bold text-slate-100">{history.length}</div><div className="text-[10px] text-slate-500">Changes</div></div>
              <div className="text-center"><div className="text-lg font-bold text-slate-100">{comments.length}</div><div className="text-[10px] text-slate-500">Comments</div></div>
            </div>
          </div>

          {/* Timeline */}
          <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
            <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Timeline</h3>
            <div className="space-y-2.5">
              <div><div className="text-[10px] text-slate-500">Created</div><div className="text-xs text-slate-300">{req.created_at ? new Date(req.created_at).toLocaleString() : '—'}</div></div>
              <div><div className="text-[10px] text-slate-500">Last Modified</div><div className="text-xs text-slate-300">{req.updated_at ? new Date(req.updated_at).toLocaleString() : '—'}</div></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
