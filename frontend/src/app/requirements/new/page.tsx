'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  ArrowLeft, Save, Zap, AlertTriangle, CheckCircle, Info,
  ChevronDown, Lightbulb, Shield, Loader2
} from 'lucide-react';
import { requirementsAPI, projectsAPI } from '@/lib/api';
import {
  LEVEL_LABELS, LEVEL_COLORS, PRIORITY_COLORS,
  TYPE_PREFIXES,
  type RequirementType, type Priority, type RequirementLevel, type Requirement
} from '@/lib/types';

// ── Client-side quality checker (mirrors backend NASA Appendix C) ──

const PROHIBITED_TERMS = [
  'flexible', 'easy', 'sufficient', 'safe', 'ad hoc', 'adequate',
  'accommodate', 'user-friendly', 'usable', 'when required',
  'if required', 'appropriate', 'fast', 'portable', 'lightweight',
  'small', 'large', 'maximize', 'minimize', 'robust', 'quickly',
  'easily', 'clearly', 'simply', 'efficiently', 'effectively',
  'reasonable', 'as appropriate', 'etc', 'and/or', 'but not limited to',
  'as needed', 'timely',
];

const AMBIGUOUS_QUANTIFIERS = [
  'some', 'several', 'many', 'few', 'often', 'usually',
  'generally', 'normally', 'approximately', 'about',
  'significant', 'minimal', 'considerable',
];

function checkQualityLocal(statement: string, rationale: string) {
  const warnings: string[] = [];
  const suggestions: string[] = [];
  let score = 100;

  if (!statement || statement.trim().length < 10) {
    return { score: 0, passed: false, warnings: ['Statement is too short'], suggestions: [] };
  }

  const text = statement.trim();
  const textLower = text.toLowerCase();

  // SHALL keyword
  const hasShall = /\bshall\b/i.test(text);
  if (!hasShall && !/\bwill\b/i.test(text) && !/\bshould\b/i.test(text)) {
    warnings.push("Missing 'shall' keyword — requirements must use 'shall'");
    score -= 20;
  }

  // Multiple SHALL
  const shallCount = (text.match(/\bshall\b/gi) || []).length;
  if (shallCount > 1) {
    warnings.push(`Multiple 'shall' (${shallCount}) — split into separate requirements`);
    score -= 15;
  }

  // Prohibited terms
  const found = PROHIBITED_TERMS.filter(t => textLower.includes(t.toLowerCase()));
  if (found.length > 0) {
    warnings.push(`Prohibited terms: ${found.join(', ')}`);
    score -= Math.min(5 * found.length, 25);
  }

  // Ambiguous quantifiers
  const ambig = AMBIGUOUS_QUANTIFIERS.filter(t => new RegExp(`\\b${t}\\b`, 'i').test(text));
  if (ambig.length > 0) {
    suggestions.push(`Ambiguous quantifiers: ${ambig.join(', ')} — use specific values`);
    score -= Math.min(3 * ambig.length, 15);
  }

  // TBD/TBR
  const tbdCount = (text.match(/\bTBD\b/g) || []).length;
  if (tbdCount > 0) {
    warnings.push(`${tbdCount} TBD value(s) — provide resolution plan`);
    score -= 8 * tbdCount;
  }

  // Short/long
  const words = text.split(/\s+/).length;
  if (words < 5) { warnings.push('Too short — may be incomplete'); score -= 10; }
  if (words > 80) { suggestions.push('Very long — consider splitting'); score -= 5; }

  // Rationale
  if (!rationale || rationale.trim().length < 5) {
    suggestions.push('Add a rationale — explain WHY this requirement exists');
    score -= 5;
  }

  // Measurability
  if (hasShall && !/\d+/.test(text)) {
    suggestions.push('No measurable criteria — add quantifiable values when possible');
    score -= 5;
  }

  // Negative
  if (/\bshall\s+not\b/i.test(text)) {
    suggestions.push("Negative requirement — consider restating positively");
    score -= 3;
  }

  score = Math.max(0, Math.min(100, score));
  return { score: Math.round(score), passed: score >= 70 && warnings.length === 0, warnings, suggestions };
}

// ── Shall Statement Templates ──

const TEMPLATES: Record<string, string> = {
  functional: 'The system shall [verb] [object] when [condition].',
  performance: 'The system shall [verb] [object] within [time/quantity] [units] under [conditions].',
  interface: 'The system shall [send/receive] [data] [to/from] [external system] via [protocol].',
  security: 'The system shall [protect/authenticate/encrypt] [asset] using [method] to prevent [threat].',
  safety: 'The system shall [detect/prevent/mitigate] [hazard] within [time] to ensure [safety condition].',
  environmental: 'The system shall [operate/survive/withstand] [environmental condition] for [duration].',
  reliability: 'The system shall achieve [metric] of [value] over [time period] under [conditions].',
  constraint: 'The system shall [comply with / be limited to] [constraint] as defined by [standard/source].',
};

// ── Score ring component ──

function ScoreRing({ score, size = 80 }: { score: number; size?: number }) {
  const color = score >= 90 ? '#10B981' : score >= 70 ? '#F59E0B' : '#EF4444';
  const radius = (size - 8) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius}
          fill="none" stroke="rgba(100,116,139,0.2)" strokeWidth={4} />
        <circle cx={size / 2} cy={size / 2} r={radius}
          fill="none" stroke={color} strokeWidth={4}
          strokeDasharray={circumference} strokeDashoffset={offset}
          strokeLinecap="round" className="transition-all duration-500" />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-lg font-bold" style={{ color }}>{score}</span>
      </div>
    </div>
  );
}

export default function NewRequirementPage() {
  const router = useRouter();

  // Form state
  const [title, setTitle] = useState('');
  const [statement, setStatement] = useState('');
  const [rationale, setRationale] = useState('');
  const [reqType, setReqType] = useState<RequirementType>('functional');
  const [priority, setPriority] = useState<Priority>('medium');
  const [level, setLevel] = useState<RequirementLevel>('L1');
  const [parentId, setParentId] = useState<number | null>(null);

  // Project state
  const [projectId, setProjectId] = useState<number | null>(null);
  const [projectCode, setProjectCode] = useState('');

  // Parent requirements for picker
  const [allRequirements, setAllRequirements] = useState<Requirement[]>([]);
  const [parentSearch, setParentSearch] = useState('');
  const [showParentPicker, setShowParentPicker] = useState(false);

  // Quality state
  const [quality, setQuality] = useState({ score: 0, passed: false, warnings: [] as string[], suggestions: [] as string[] });

  // UI state
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [showTemplate, setShowTemplate] = useState(false);

  // Load project + existing requirements for parent picker
  useEffect(() => {
    projectsAPI.list().then((res) => {
      if (res.data.length > 0) {
        setProjectId(res.data[0].id);
        setProjectCode(res.data[0].code);
        // Load all requirements for parent picker
        requirementsAPI.list(res.data[0].id, { limit: 200 }).then((rRes) => {
          setAllRequirements(rRes.data);
        });
      }
    });
  }, []);

  // Real-time quality scoring with debounce
  useEffect(() => {
    const timer = setTimeout(() => {
      if (statement.trim().length > 5) {
        setQuality(checkQualityLocal(statement, rationale));
      } else {
        setQuality({ score: 0, passed: false, warnings: [], suggestions: [] });
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [statement, rationale]);

  // Auto-suggest level based on parent
  useEffect(() => {
    if (parentId) {
      const parent = allRequirements.find(r => r.id === parentId);
      if (parent?.level) {
        const levelNum = parseInt(parent.level.replace('L', ''));
        if (levelNum < 5) {
          setLevel(`L${levelNum + 1}` as RequirementLevel);
        }
      }
    }
  }, [parentId, allRequirements]);

  // Insert template
  const insertTemplate = () => {
    const template = TEMPLATES[reqType] || TEMPLATES.functional;
    setStatement(template);
    setShowTemplate(false);
  };

  // Filtered parents for picker
  const filteredParents = allRequirements.filter(r => {
    if (!parentSearch) return true;
    const s = parentSearch.toLowerCase();
    return r.req_id.toLowerCase().includes(s) || r.title.toLowerCase().includes(s);
  });

  // Save
  const handleSave = async () => {
    if (!projectId) return;
    setError('');
    setSaving(true);
    try {
      await requirementsAPI.create(projectId, {
        title,
        statement,
        rationale: rationale || undefined,
        req_type: reqType,
        priority,
        level,
        parent_id: parentId || undefined,
      });
      router.push('/requirements');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create requirement');
    } finally {
      setSaving(false);
    }
  };

  const selectedParent = parentId ? allRequirements.find(r => r.id === parentId) : null;
  const canSave = title.trim().length >= 3 && statement.trim().length >= 10;

  return (
    <div className="mx-auto max-w-5xl">
      {/* Header */}
      <div className="mb-6 flex items-center gap-4">
        <button onClick={() => router.push('/requirements')}
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-astra-border text-slate-400 transition hover:border-blue-500/30 hover:text-slate-200">
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="flex-1">
          <h1 className="text-xl font-bold tracking-tight">New Requirement</h1>
          <p className="mt-0.5 text-sm text-slate-500">{projectCode} · Creating new requirement</p>
        </div>
        <button onClick={handleSave} disabled={!canSave || saving}
          className="flex items-center gap-2 rounded-lg bg-blue-500 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          {saving ? 'Saving...' : 'Save Requirement'}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">{error}</div>
      )}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        {/* ── Left: Form ── */}
        <div className="space-y-5 xl:col-span-2">

          {/* Classification Row */}
          <div className="grid grid-cols-3 gap-4">
            {/* Level */}
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">Level</label>
              <div className="flex gap-1.5">
                {(['L1', 'L2', 'L3', 'L4', 'L5'] as RequirementLevel[]).map((l) => (
                  <button key={l} onClick={() => setLevel(l)}
                    className={`flex-1 rounded-lg py-2 text-xs font-bold transition-all ${
                      level === l
                        ? 'text-white shadow-lg'
                        : 'border border-astra-border bg-astra-surface text-slate-400 hover:border-blue-500/30'
                    }`}
                    style={level === l ? { background: LEVEL_COLORS[l], boxShadow: `0 4px 12px ${LEVEL_COLORS[l]}33` } : {}}>
                    {l}
                  </button>
                ))}
              </div>
              <div className="mt-1 text-[10px] text-slate-500">{LEVEL_LABELS[level]}</div>
            </div>

            {/* Type */}
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">Type</label>
              <div className="relative">
                <select value={reqType} onChange={(e) => setReqType(e.target.value as RequirementType)}
                  className="w-full appearance-none rounded-lg border border-astra-border bg-astra-surface px-3 py-2.5 pr-8 text-sm text-slate-200 outline-none transition focus:border-blue-500/50">
                  <option value="functional">Functional (FR)</option>
                  <option value="performance">Performance (PR)</option>
                  <option value="interface">Interface (IR)</option>
                  <option value="security">Security (SR)</option>
                  <option value="safety">Safety (SAF)</option>
                  <option value="environmental">Environmental (ER)</option>
                  <option value="reliability">Reliability (RL)</option>
                  <option value="constraint">Constraint (CR)</option>
                  <option value="maintainability">Maintainability (MR)</option>
                  <option value="derived">Derived (DR)</option>
                </select>
                <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
              </div>
            </div>

            {/* Priority */}
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">Priority</label>
              <div className="flex gap-1.5">
                {(['critical', 'high', 'medium', 'low'] as Priority[]).map((p) => (
                  <button key={p} onClick={() => setPriority(p)}
                    className={`flex-1 rounded-lg py-2.5 text-[11px] font-bold capitalize transition-all ${
                      priority === p
                        ? 'text-white'
                        : 'border border-astra-border bg-astra-surface text-slate-400 hover:border-blue-500/30'
                    }`}
                    style={priority === p ? { background: PRIORITY_COLORS[p] } : {}}>
                    {p}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Parent Requirement */}
          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              Parent Requirement <span className="font-normal text-slate-600">(optional)</span>
            </label>
            {selectedParent ? (
              <div className="flex items-center gap-2 rounded-lg border border-astra-border bg-astra-surface px-3 py-2.5">
                <span className="rounded-full px-2 py-0.5 text-[10px] font-bold"
                  style={{ background: `${LEVEL_COLORS[selectedParent.level as RequirementLevel]}20`, color: LEVEL_COLORS[selectedParent.level as RequirementLevel] }}>
                  {selectedParent.level}
                </span>
                <span className="font-mono text-xs font-semibold text-blue-400">{selectedParent.req_id}</span>
                <span className="flex-1 truncate text-sm text-slate-300">{selectedParent.title}</span>
                <button onClick={() => { setParentId(null); setShowParentPicker(false); }}
                  className="text-xs text-red-400 hover:text-red-300">Remove</button>
              </div>
            ) : (
              <div className="relative">
                <input
                  value={parentSearch}
                  onChange={(e) => { setParentSearch(e.target.value); setShowParentPicker(true); }}
                  onFocus={() => setShowParentPicker(true)}
                  placeholder="Search by ID or title to link a parent..."
                  className="w-full rounded-lg border border-astra-border bg-astra-surface px-3 py-2.5 text-sm text-slate-200 outline-none transition placeholder:text-slate-600 focus:border-blue-500/50"
                />
                {showParentPicker && (
                  <div className="absolute left-0 right-0 top-full z-50 mt-1 max-h-48 overflow-y-auto rounded-lg border border-astra-border bg-astra-surface shadow-xl">
                    {filteredParents.length === 0 ? (
                      <div className="px-3 py-4 text-center text-xs text-slate-500">No matching requirements</div>
                    ) : (
                      filteredParents.slice(0, 10).map((r) => (
                        <button key={r.id}
                          onClick={() => { setParentId(r.id); setParentSearch(''); setShowParentPicker(false); }}
                          className="flex w-full items-center gap-2 px-3 py-2 text-left transition hover:bg-astra-surface-hover">
                          <span className="rounded-full px-1.5 py-0.5 text-[9px] font-bold"
                            style={{ background: `${LEVEL_COLORS[r.level as RequirementLevel]}20`, color: LEVEL_COLORS[r.level as RequirementLevel] }}>
                            {r.level}
                          </span>
                          <span className="font-mono text-[11px] font-semibold text-blue-400">{r.req_id}</span>
                          <span className="flex-1 truncate text-xs text-slate-300">{r.title}</span>
                        </button>
                      ))
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Title */}
          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">Title</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g., Autonomous Guidance Trajectory Correction"
              className="w-full rounded-lg border border-astra-border bg-astra-surface px-3 py-2.5 text-sm text-slate-200 outline-none transition placeholder:text-slate-600 focus:border-blue-500/50" />
          </div>

          {/* Statement */}
          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Requirement Statement
              </label>
              <button onClick={() => setShowTemplate(!showTemplate)}
                className="flex items-center gap-1 text-[11px] font-semibold text-blue-400 hover:text-blue-300">
                <Lightbulb className="h-3 w-3" /> Template
              </button>
            </div>

            {showTemplate && (
              <div className="mb-2 rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
                <div className="mb-1.5 text-[11px] font-semibold text-blue-400">
                  {(TYPE_PREFIXES[reqType] || 'GR')} Template:
                </div>
                <div className="mb-2 font-mono text-xs text-slate-300">
                  {TEMPLATES[reqType] || TEMPLATES.functional}
                </div>
                <button onClick={insertTemplate}
                  className="rounded-md bg-blue-500 px-3 py-1 text-[11px] font-semibold text-white hover:bg-blue-600">
                  Insert Template
                </button>
              </div>
            )}

            <textarea value={statement} onChange={(e) => setStatement(e.target.value)}
              rows={4}
              placeholder="The system shall..."
              className="w-full rounded-lg border border-astra-border bg-astra-surface px-3 py-2.5 text-sm leading-relaxed text-slate-200 outline-none transition placeholder:text-slate-600 focus:border-blue-500/50 resize-none" />
            <div className="mt-1 text-[10px] text-slate-600">
              {statement.split(/\s+/).filter(Boolean).length} words · Use "shall" for mandatory requirements
            </div>
          </div>

          {/* Rationale */}
          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              Rationale <span className="font-normal text-slate-600">(recommended)</span>
            </label>
            <textarea value={rationale} onChange={(e) => setRationale(e.target.value)}
              rows={3}
              placeholder="Explain WHY this requirement exists — what problem does it solve or what need does it address?"
              className="w-full rounded-lg border border-astra-border bg-astra-surface px-3 py-2.5 text-sm leading-relaxed text-slate-200 outline-none transition placeholder:text-slate-600 focus:border-blue-500/50 resize-none" />
          </div>
        </div>

        {/* ── Right: Quality Panel ── */}
        <div className="space-y-4">
          {/* Score Card */}
          <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
            <h3 className="mb-4 flex items-center gap-2 text-sm font-bold text-slate-200">
              <Shield className="h-4 w-4 text-blue-400" /> NASA Quality Score
            </h3>
            <div className="flex items-center justify-center py-2">
              <ScoreRing score={quality.score} size={100} />
            </div>
            <div className="mt-3 text-center">
              {quality.score === 0 ? (
                <span className="text-xs text-slate-500">Start typing to see quality score</span>
              ) : quality.passed ? (
                <span className="flex items-center justify-center gap-1 text-xs font-semibold text-emerald-400">
                  <CheckCircle className="h-3.5 w-3.5" /> Passes NASA Appendix C
                </span>
              ) : (
                <span className="flex items-center justify-center gap-1 text-xs font-semibold text-amber-400">
                  <AlertTriangle className="h-3.5 w-3.5" /> Needs improvement
                </span>
              )}
            </div>
          </div>

          {/* Warnings */}
          {quality.warnings.length > 0 && (
            <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4">
              <h4 className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-red-400">
                <AlertTriangle className="h-3.5 w-3.5" /> Warnings
              </h4>
              <ul className="space-y-2">
                {quality.warnings.map((w, i) => (
                  <li key={i} className="text-xs leading-relaxed text-red-300/80">{w}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Suggestions */}
          {quality.suggestions.length > 0 && (
            <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
              <h4 className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-amber-400">
                <Info className="h-3.5 w-3.5" /> Suggestions
              </h4>
              <ul className="space-y-2">
                {quality.suggestions.map((s, i) => (
                  <li key={i} className="text-xs leading-relaxed text-amber-300/80">{s}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Auto-generated ID Preview */}
          <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
            <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Preview</h4>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-[11px] text-slate-500">ID Format</span>
                <span className="font-mono text-xs font-semibold text-blue-400">
                  {TYPE_PREFIXES[reqType] || 'GR'}-{projectCode}-###
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[11px] text-slate-500">Level</span>
                <span className="text-xs font-semibold" style={{ color: LEVEL_COLORS[level] }}>{LEVEL_LABELS[level]}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[11px] text-slate-500">Priority</span>
                <span className="text-xs font-semibold capitalize" style={{ color: PRIORITY_COLORS[priority] }}>{priority}</span>
              </div>
              {selectedParent && (
                <div className="flex justify-between">
                  <span className="text-[11px] text-slate-500">Parent</span>
                  <span className="font-mono text-xs text-blue-400">{selectedParent.req_id}</span>
                </div>
              )}
            </div>
          </div>

          {/* Quick tips */}
          <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
            <h4 className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              <Zap className="h-3 w-3 text-amber-400" /> Writing Tips
            </h4>
            <ul className="space-y-1.5 text-[11px] leading-relaxed text-slate-400">
              <li>• Use <span className="font-semibold text-slate-300">"shall"</span> for mandatory requirements</li>
              <li>• One requirement = one testable statement</li>
              <li>• Include measurable acceptance criteria</li>
              <li>• Avoid ambiguous terms (adequate, fast, etc.)</li>
              <li>• Always provide a rationale</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
