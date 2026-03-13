'use client';

/**
 * ASTRA — New Requirement Form (Project-Scoped)
 * ================================================
 * File: frontend/src/app/projects/[id]/requirements/new/page.tsx
 *
 * AI integrations:
 *   1. DuplicateChecker below statement (debounced 800ms)
 *   2. AI Writer launcher button
 *   3. "Generate Rationale" button
 *   4. Live quality score preview
 *   5. Parent selector with hierarchy tree
 */

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft, Save, Loader2, ChevronDown, Sparkles, Wand2,
  AlertTriangle, BookOpen, Search, ChevronRight, X,
} from 'lucide-react';
import {
  LEVEL_COLORS, LEVEL_LABELS, PRIORITY_COLORS,
  type RequirementType, type RequirementLevel, type Priority, type Requirement,
} from '@/lib/types';
import { requirementsAPI, projectsAPI } from '@/lib/api';

// Optional AI
let aiAPI: any = null;
let aiWriterAPI: any = null;
try { aiAPI = require('@/lib/ai-api').aiAPI; } catch {}
try { aiWriterAPI = require('@/lib/ai-writer-api').aiWriterAPI; } catch {}

// ── Score ring ──
function ScoreRing({ score, size = 70 }: { score: number; size?: number }) {
  const color = score >= 90 ? '#10B981' : score >= 70 ? '#F59E0B' : '#EF4444';
  const r = (size - 8) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(100,116,139,0.2)" strokeWidth={4} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={4}
          strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round" className="transition-all duration-500" />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-lg font-bold" style={{ color }}>{score}</span>
      </div>
    </div>
  );
}

// ── Duplicate results ──
function DuplicateResults({ duplicates, loading }: { duplicates: any[]; loading: boolean }) {
  if (loading) return (
    <div className="flex items-center gap-2 text-xs text-slate-500 py-2">
      <Loader2 className="h-3 w-3 animate-spin" /> Checking for duplicates…
    </div>
  );
  if (duplicates.length === 0) return null;
  return (
    <div className="mt-2 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
      <div className="flex items-center gap-2 mb-2">
        <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
        <span className="text-xs font-semibold text-amber-300">
          {duplicates.length} similar requirement{duplicates.length !== 1 ? 's' : ''} found
        </span>
      </div>
      <div className="space-y-1.5">
        {duplicates.slice(0, 5).map((d: any, i: number) => (
          <div key={i} className="flex items-center gap-2 text-xs">
            <span className="font-mono text-blue-400">{d.req_id}</span>
            <span className="flex-1 truncate text-slate-400">{d.title || d.statement?.substring(0, 60)}</span>
            <span className="text-amber-400 font-semibold">{(d.similarity_score * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ══════════════════════════════════════
//  Main Page
// ══════════════════════════════════════

export default function NewRequirementPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);
  const p = `/projects/${projectId}`;

  // Form state
  const [title, setTitle] = useState('');
  const [statement, setStatement] = useState('');
  const [rationale, setRationale] = useState('');
  const [reqType, setReqType] = useState<RequirementType>('functional');
  const [priority, setPriority] = useState<Priority>('medium');
  const [level, setLevel] = useState<RequirementLevel>('L1');
  const [parentId, setParentId] = useState<number | null>(null);

  // Project
  const [projectCode, setProjectCode] = useState('');
  const [allRequirements, setAllRequirements] = useState<Requirement[]>([]);
  const [parentSearch, setParentSearch] = useState('');
  const [showParentPicker, setShowParentPicker] = useState(false);

  // Quality
  const [quality, setQuality] = useState<any>({ score: 0, passed: false, warnings: [], suggestions: [] });

  // Duplicates
  const [duplicates, setDuplicates] = useState<any[]>([]);
  const [checkingDups, setCheckingDups] = useState(false);

  // Rationale generation
  const [generatingRationale, setGeneratingRationale] = useState(false);

  // UI
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // ── Load project + existing requirements ──
  useEffect(() => {
    projectsAPI.get(projectId).then((res) => setProjectCode(res.data.code)).catch(() => {});
    requirementsAPI.list(projectId, { limit: 200 })
      .then((res) => setAllRequirements(Array.isArray(res.data) ? res.data : []))
      .catch(() => {});
  }, [projectId]);

  // ── Live quality scoring (debounced 300ms) ──
  useEffect(() => {
    const t = setTimeout(() => {
      if (statement.trim().length > 5) {
        requirementsAPI.qualityCheck(statement, title, rationale)
          .then((res) => setQuality(res.data))
          .catch(() => {});
      } else {
        setQuality({ score: 0, passed: false, warnings: [], suggestions: [] });
      }
    }, 300);
    return () => clearTimeout(t);
  }, [statement, title, rationale]);

  // ── Duplicate check (debounced 800ms) ──
  useEffect(() => {
    if (!statement || statement.trim().length < 15 || !aiAPI) {
      setDuplicates([]);
      return;
    }
    setCheckingDups(true);
    const t = setTimeout(() => {
      aiAPI.checkDuplicate(statement, projectId, title)
        .then((res: any) => {
          setDuplicates(res.data?.similar_requirements || []);
        })
        .catch(() => setDuplicates([]))
        .finally(() => setCheckingDups(false));
    }, 800);
    return () => { clearTimeout(t); setCheckingDups(false); };
  }, [statement, projectId, title]);

  // ── Auto-suggest level from parent ──
  useEffect(() => {
    if (parentId) {
      const parent = allRequirements.find((r) => r.id === parentId);
      if (parent?.level) {
        const num = parseInt(parent.level.replace('L', ''));
        if (num < 5) setLevel(`L${num + 1}` as RequirementLevel);
      }
    }
  }, [parentId, allRequirements]);

  // ── Generate rationale ──
  const handleGenerateRationale = async () => {
    if (!aiWriterAPI || !statement) return;
    setGeneratingRationale(true);
    try {
      const res = await aiWriterAPI.generateRationale(statement, { title, req_type: reqType });
      if (res.data?.rationale) setRationale(res.data.rationale);
    } catch {}
    setGeneratingRationale(false);
  };

  // ── Save ──
  const handleSave = async () => {
    if (!projectId) return;
    setError('');
    setSaving(true);
    try {
      await requirementsAPI.create(projectId, {
        title, statement, rationale: rationale || undefined,
        req_type: reqType, priority, level,
        parent_id: parentId || undefined,
      });
      router.push(`${p}/requirements`);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create requirement');
    }
    setSaving(false);
  };

  const canSave = title.trim().length >= 3 && statement.trim().length >= 10;
  const filteredParents = allRequirements.filter((r) => {
    if (!parentSearch) return true;
    const s = parentSearch.toLowerCase();
    return r.req_id.toLowerCase().includes(s) || r.title.toLowerCase().includes(s);
  });
  const selectedParent = parentId ? allRequirements.find((r) => r.id === parentId) : null;

  return (
    <div className="mx-auto max-w-5xl">
      {/* Header */}
      <div className="mb-6 flex items-center gap-4">
        <button onClick={() => router.push(`${p}/requirements`)}
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-astra-border text-slate-400 transition hover:text-slate-200">
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="flex-1">
          <h1 className="text-xl font-bold tracking-tight">New Requirement</h1>
          <p className="mt-0.5 text-sm text-slate-500">{projectCode} · Creating new requirement</p>
        </div>
        {/* AI Writer launcher */}
        <button onClick={() => router.push(`${p}/ai`)}
          className="flex items-center gap-1.5 rounded-lg border border-violet-500/30 bg-violet-500/10 px-3 py-2 text-[11px] font-semibold text-violet-400 hover:bg-violet-500/20">
          <Sparkles className="h-3.5 w-3.5" /> AI Assistant
        </button>
        <button onClick={handleSave} disabled={!canSave || saving}
          className="flex items-center gap-2 rounded-lg bg-blue-500 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-600 disabled:opacity-40">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          {saving ? 'Saving…' : 'Save Requirement'}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">{error}</div>
      )}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        {/* Left: Form */}
        <div className="space-y-5 xl:col-span-2">
          {/* Classification */}
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">Level</label>
              <div className="flex gap-1.5">
                {(['L1', 'L2', 'L3', 'L4', 'L5'] as RequirementLevel[]).map((l) => (
                  <button key={l} onClick={() => setLevel(l)}
                    className={`flex-1 rounded-lg py-2 text-xs font-bold transition-all ${
                      level === l ? 'text-white shadow-lg' : 'border border-astra-border bg-astra-surface text-slate-400 hover:border-blue-500/30'
                    }`}
                    style={level === l ? { background: LEVEL_COLORS[l] } : {}}>
                    {l}
                  </button>
                ))}
              </div>
              <div className="mt-1 text-[10px] text-slate-500">{LEVEL_LABELS[level]}</div>
            </div>
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">Type</label>
              <select value={reqType} onChange={(e) => setReqType(e.target.value as RequirementType)}
                className="w-full appearance-none rounded-lg border border-astra-border bg-astra-surface px-3 py-2.5 pr-8 text-sm text-slate-200 outline-none focus:border-blue-500/50">
                {['functional', 'performance', 'interface', 'security', 'safety', 'environmental', 'reliability', 'constraint', 'maintainability', 'derived'].map((t) => (
                  <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">Priority</label>
              <div className="flex gap-1.5">
                {(['critical', 'high', 'medium', 'low'] as Priority[]).map((pr) => (
                  <button key={pr} onClick={() => setPriority(pr)}
                    className={`flex-1 rounded-lg py-2.5 text-[11px] font-bold capitalize transition-all ${
                      priority === pr ? 'text-white' : 'border border-astra-border bg-astra-surface text-slate-400'
                    }`}
                    style={priority === pr ? { background: PRIORITY_COLORS[pr] } : {}}>
                    {pr}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Title */}
          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">Title</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g., Target Detection System"
              className="w-full rounded-lg border border-astra-border bg-astra-surface px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50 placeholder:text-slate-600" />
          </div>

          {/* Statement */}
          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">Requirement Statement</label>
            <textarea value={statement} onChange={(e) => setStatement(e.target.value)} rows={4}
              placeholder="The system shall…"
              className="w-full rounded-lg border border-astra-border bg-astra-surface px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50 placeholder:text-slate-600" />
            {/* Duplicate checker results */}
            <DuplicateResults duplicates={duplicates} loading={checkingDups} />
          </div>

          {/* Rationale */}
          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Rationale</label>
              <button onClick={handleGenerateRationale}
                disabled={generatingRationale || !statement.trim()}
                className="flex items-center gap-1 text-[10px] font-semibold text-violet-400 hover:text-violet-300 disabled:opacity-50">
                {generatingRationale ? <Loader2 className="h-3 w-3 animate-spin" /> : <BookOpen className="h-3 w-3" />}
                {generatingRationale ? 'Generating…' : 'Generate Rationale'}
              </button>
            </div>
            <textarea value={rationale} onChange={(e) => setRationale(e.target.value)} rows={3}
              placeholder="Explain why this requirement is needed…"
              className="w-full rounded-lg border border-astra-border bg-astra-surface px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50 placeholder:text-slate-600" />
          </div>

          {/* Parent Selector */}
          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">Parent Requirement</label>
            {selectedParent ? (
              <div className="flex items-center gap-2 rounded-lg border border-blue-500/20 bg-blue-500/5 px-3 py-2">
                <span className="text-xs font-bold" style={{ color: LEVEL_COLORS[(selectedParent.level || 'L1') as RequirementLevel] }}>
                  {selectedParent.level}
                </span>
                <span className="font-mono text-xs text-blue-400">{selectedParent.req_id}</span>
                <span className="flex-1 truncate text-xs text-slate-300">{selectedParent.title}</span>
                <button onClick={() => setParentId(null)} className="text-slate-500 hover:text-slate-300"><X className="h-3.5 w-3.5" /></button>
              </div>
            ) : (
              <div className="relative">
                <div className="flex items-center gap-2 rounded-lg border border-astra-border bg-astra-surface px-3 py-2 cursor-pointer"
                  onClick={() => setShowParentPicker(!showParentPicker)}>
                  <Search className="h-3.5 w-3.5 text-slate-500" />
                  <input value={parentSearch} onChange={(e) => { setParentSearch(e.target.value); setShowParentPicker(true); }}
                    placeholder="Search parent requirement…" onClick={(e) => e.stopPropagation()}
                    className="flex-1 bg-transparent text-sm text-slate-200 outline-none placeholder:text-slate-600" />
                </div>
                {showParentPicker && (
                  <div className="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded-lg border border-astra-border bg-astra-surface shadow-xl">
                    {filteredParents.slice(0, 20).map((r) => (
                      <button key={r.id} onClick={() => { setParentId(r.id); setShowParentPicker(false); setParentSearch(''); }}
                        className="flex w-full items-center gap-2 px-3 py-2 text-left transition hover:bg-astra-surface-hover">
                        <span className="text-[9px] font-bold" style={{ color: LEVEL_COLORS[(r.level || 'L1') as RequirementLevel] }}>{r.level}</span>
                        <span className="font-mono text-xs text-blue-400">{r.req_id}</span>
                        <span className="flex-1 truncate text-xs text-slate-300">{r.title}</span>
                      </button>
                    ))}
                    {filteredParents.length === 0 && (
                      <div className="px-3 py-4 text-center text-xs text-slate-500">No matching requirements</div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right: Quality Preview + Info */}
        <div className="space-y-4">
          {/* Quality Ring */}
          <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
            <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Quality Preview</h3>
            <div className="flex justify-center mb-3">
              <ScoreRing score={quality.score} />
            </div>
            <div className="text-center text-[10px] text-slate-500 mb-3">
              {quality.score >= 90 ? 'Excellent — NASA Compliant' : quality.score >= 70 ? 'Acceptable' : quality.score > 0 ? 'Needs Improvement' : 'Enter a statement'}
            </div>
            {quality.warnings?.length > 0 && (
              <div className="space-y-1 mb-2">
                {quality.warnings.map((w: string, i: number) => (
                  <div key={i} className="flex items-start gap-1.5 text-[10px] text-amber-400">
                    <AlertTriangle className="h-3 w-3 mt-0.5 flex-shrink-0" /> {w}
                  </div>
                ))}
              </div>
            )}
            {quality.suggestions?.length > 0 && (
              <div className="space-y-1">
                {quality.suggestions.map((s: string, i: number) => (
                  <div key={i} className="flex items-start gap-1.5 text-[10px] text-blue-400">
                    <Sparkles className="h-3 w-3 mt-0.5 flex-shrink-0" /> {s}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Writing Tips */}
          <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
            <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">NASA Appendix C Tips</h3>
            <ul className="space-y-1.5 text-[10px] text-slate-400">
              <li>• Use "shall" for mandatory requirements</li>
              <li>• Include measurable acceptance criteria</li>
              <li>• Avoid vague terms: flexible, adequate, user-friendly</li>
              <li>• One requirement per "shall" statement</li>
              <li>• No TBD/TBR values in final baselines</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
