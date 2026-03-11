/**
 * ASTRA — AI Writing Assistant
 * ===============================
 * File: frontend/src/components/ai/AIWritingAssistant.tsx   ← NEW
 * Path: C:\Users\Mason\Documents\ASTRA\frontend\src\components\ai\AIWritingAssistant.tsx
 *
 * A sliding drawer panel accessible from requirement create/edit forms.
 * Three modes:
 *   1. Convert  — paste stakeholder prose, extract structured requirements
 *   2. Improve  — get AI suggestions to fix quality issues
 *   3. Decompose — break a high-level req into sub-requirements
 *
 * Also includes: rationale generation, verification criteria generation.
 * All AI-generated content is clearly labeled.
 */

'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import {
  Sparkles, X, Loader2, ChevronRight, Check, Copy,
  FileText, Wand2, GitBranch, ClipboardCheck, BookOpen,
  AlertTriangle, CheckCircle, ChevronDown, ChevronUp,
  Plus, Trash2, Edit3, ArrowRight, Lightbulb, Zap,
} from 'lucide-react';
import {
  aiWriterAPI,
  type GeneratedRequirement,
  type RewriteSuggestion,
  type DecomposeResponse,
  type VerificationCriteria,
} from '@/lib/ai-writer-api';

// ══════════════════════════════════════
//  Types
// ══════════════════════════════════════

type WriterMode = 'convert' | 'improve' | 'decompose';

interface AIWritingAssistantProps {
  isOpen: boolean;
  onClose: () => void;
  /** Called when user wants to apply a generated/improved statement */
  onApplyStatement?: (statement: string, title?: string, rationale?: string) => void;
  /** Called when user wants to create multiple requirements (from prose or decompose) */
  onBatchCreate?: (requirements: GeneratedRequirement[]) => void;
  /** Called when user wants to apply a generated rationale */
  onApplyRationale?: (rationale: string) => void;
  /** Current form state for context */
  currentStatement?: string;
  currentTitle?: string;
  currentRationale?: string;
  currentLevel?: string;
  currentType?: string;
  currentIssues?: string[];
  projectContext?: string;
}

// ══════════════════════════════════════
//  Launcher Button (exported separately)
// ══════════════════════════════════════

export function AIWriterLauncher({
  onClick,
  compact = false,
}: {
  onClick: () => void;
  compact?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex items-center gap-1.5 rounded-lg border border-violet-500/30 bg-violet-500/8 px-2.5 py-1.5 text-[11px] font-semibold text-violet-400 transition-all hover:border-violet-500/50 hover:bg-violet-500/15 hover:shadow-md hover:shadow-violet-500/10"
    >
      <Sparkles className="h-3.5 w-3.5 transition-transform group-hover:scale-110" />
      {!compact && 'AI Assistant'}
    </button>
  );
}

// ══════════════════════════════════════
//  Main Component
// ══════════════════════════════════════

export default function AIWritingAssistant({
  isOpen,
  onClose,
  onApplyStatement,
  onBatchCreate,
  onApplyRationale,
  currentStatement = '',
  currentTitle = '',
  currentRationale = '',
  currentLevel = 'L1',
  currentType = 'functional',
  currentIssues = [],
  projectContext = '',
}: AIWritingAssistantProps) {
  const [mode, setMode] = useState<WriterMode>('convert');
  const [aiAvailable, setAiAvailable] = useState(true);

  // Check AI status on open
  useEffect(() => {
    if (isOpen) {
      aiWriterAPI.getStatus().then(res => {
        setAiAvailable(res.data.available);
      }).catch(() => setAiAvailable(false));
      // Default to 'improve' if we have an existing statement
      if (currentStatement && currentStatement.length > 10) {
        setMode('improve');
      }
    }
  }, [isOpen, currentStatement]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-y-0 right-0 z-40 flex">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/30 backdrop-blur-[2px]" onClick={onClose} />

      {/* Drawer */}
      <div className="relative ml-auto flex h-full w-full max-w-xl flex-col border-l border-astra-border bg-astra-bg shadow-2xl shadow-black/40">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-astra-border px-5 py-3.5">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 shadow-lg shadow-violet-500/20">
              <Sparkles className="h-4 w-4 text-white" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white">AI Writing Assistant</h2>
              <p className="text-[10px] text-slate-500">INCOSE · NASA Appendix C · IEEE 29148</p>
            </div>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-700/50 hover:text-slate-300">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* AI Unavailable Banner */}
        {!aiAvailable && (
          <div className="mx-4 mt-3 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2">
            <div className="flex items-center gap-2 text-[11px] text-amber-400">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              AI provider not configured. Set <code className="rounded bg-slate-800 px-1 text-[9px]">AI_PROVIDER</code> in your environment.
            </div>
          </div>
        )}

        {/* Mode Tabs */}
        <div className="flex border-b border-astra-border px-4 pt-3">
          {([
            { key: 'convert' as const, icon: FileText, label: 'Convert Prose' },
            { key: 'improve' as const, icon: Wand2, label: 'Improve' },
            { key: 'decompose' as const, icon: GitBranch, label: 'Decompose' },
          ]).map(tab => (
            <button
              key={tab.key}
              onClick={() => setMode(tab.key)}
              className={`flex items-center gap-1.5 border-b-2 px-3.5 pb-2.5 text-[11px] font-semibold transition ${
                mode === tab.key
                  ? 'border-violet-500 text-violet-400'
                  : 'border-transparent text-slate-500 hover:text-slate-300'
              }`}
            >
              <tab.icon className="h-3.5 w-3.5" />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {mode === 'convert' && (
            <ConvertProsePanel
              projectContext={projectContext}
              targetLevel={currentLevel}
              onApplyStatement={onApplyStatement}
              onBatchCreate={onBatchCreate}
              disabled={!aiAvailable}
            />
          )}
          {mode === 'improve' && (
            <ImprovePanel
              currentStatement={currentStatement}
              currentTitle={currentTitle}
              currentRationale={currentRationale}
              currentIssues={currentIssues}
              projectContext={projectContext}
              onApplyStatement={onApplyStatement}
              onApplyRationale={onApplyRationale}
              disabled={!aiAvailable}
            />
          )}
          {mode === 'decompose' && (
            <DecomposePanel
              currentStatement={currentStatement}
              currentTitle={currentTitle}
              currentLevel={currentLevel}
              currentType={currentType}
              projectContext={projectContext}
              onBatchCreate={onBatchCreate}
              disabled={!aiAvailable}
            />
          )}
        </div>
      </div>
    </div>
  );
}


// ══════════════════════════════════════
//  Convert Prose Panel
// ══════════════════════════════════════

function ConvertProsePanel({
  projectContext,
  targetLevel,
  onApplyStatement,
  onBatchCreate,
  disabled,
}: {
  projectContext: string;
  targetLevel: string;
  onApplyStatement?: (statement: string, title?: string, rationale?: string) => void;
  onBatchCreate?: (requirements: GeneratedRequirement[]) => void;
  disabled: boolean;
}) {
  const [prose, setProse] = useState('');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<GeneratedRequirement[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [error, setError] = useState('');
  const [warnings, setWarnings] = useState<string[]>([]);

  const handleExtract = async () => {
    if (!prose.trim() || disabled) return;
    setLoading(true);
    setError('');
    try {
      const res = await aiWriterAPI.convertProse(prose, {
        project_context: projectContext,
        target_level: targetLevel,
      });
      setResults(res.data.requirements);
      setSelected(new Set(res.data.requirements.map((_, i) => i)));
      setWarnings(res.data.warnings);
      if (!res.data.ai_available) {
        setError('AI provider not available');
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Extraction failed');
    } finally {
      setLoading(false);
    }
  };

  const toggleSelect = (idx: number) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
  };

  const handleCreateSelected = () => {
    const selectedReqs = results.filter((_, i) => selected.has(i));
    if (selectedReqs.length === 1 && onApplyStatement) {
      const r = selectedReqs[0];
      onApplyStatement(r.statement, r.title, r.rationale);
    } else if (selectedReqs.length > 0 && onBatchCreate) {
      onBatchCreate(selectedReqs);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="mb-1.5 flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">
          <FileText className="h-3 w-3" />
          Paste Stakeholder Input
        </label>
        <textarea
          value={prose}
          onChange={e => setProse(e.target.value)}
          placeholder={"Paste meeting notes, emails, specification text, or any stakeholder input here...\n\nExample:\n\"The missile tracking system needs to detect targets within 500km range. It should respond within 2 seconds of detection. The operator needs a visual display showing all tracked objects. We need to handle at least 50 simultaneous targets.\""}
          rows={8}
          className="w-full rounded-lg border border-astra-border bg-astra-surface px-3 py-2.5 text-[12px] leading-relaxed text-slate-200 placeholder:text-slate-600 focus:border-violet-500/50 focus:outline-none resize-none"
        />
        <div className="mt-1 flex items-center justify-between">
          <span className="text-[10px] text-slate-600">{prose.length} / 20,000 characters</span>
          <button
            onClick={handleExtract}
            disabled={prose.trim().length < 10 || loading || disabled}
            className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-violet-600 to-fuchsia-600 px-3.5 py-1.5 text-[11px] font-semibold text-white shadow-lg shadow-violet-500/20 transition hover:shadow-violet-500/30 disabled:opacity-40"
          >
            {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Zap className="h-3 w-3" />}
            {loading ? 'Extracting…' : 'Extract Requirements'}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-[11px] text-red-400">{error}</div>
      )}

      {warnings.length > 0 && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-400">
          {warnings.map((w, i) => <div key={i}>{w}</div>)}
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-300">
              Extracted {results.length} requirement{results.length !== 1 ? 's' : ''}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setSelected(new Set(results.map((_, i) => i)))}
                className="text-[10px] text-violet-400 hover:underline"
              >
                Select all
              </button>
              <button
                onClick={() => setSelected(new Set())}
                className="text-[10px] text-slate-500 hover:underline"
              >
                Clear
              </button>
            </div>
          </div>

          {results.map((req, idx) => (
            <ExtractedReqCard
              key={idx}
              req={req}
              index={idx}
              isSelected={selected.has(idx)}
              onToggle={() => toggleSelect(idx)}
              onApply={() => onApplyStatement?.(req.statement, req.title, req.rationale)}
              onEdit={(field, value) => {
                setResults(prev => {
                  const next = [...prev];
                  next[idx] = { ...next[idx], [field]: value };
                  return next;
                });
              }}
            />
          ))}

          {/* Batch action */}
          {selected.size > 0 && (
            <button
              onClick={handleCreateSelected}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 py-2 text-xs font-semibold text-white transition hover:bg-emerald-500"
            >
              <Plus className="h-3.5 w-3.5" />
              {selected.size === 1 ? 'Apply to Form' : `Create ${selected.size} Requirements`}
            </button>
          )}
        </div>
      )}
    </div>
  );
}


// ══════════════════════════════════════
//  Improve Panel
// ══════════════════════════════════════

function ImprovePanel({
  currentStatement,
  currentTitle,
  currentRationale,
  currentIssues,
  projectContext,
  onApplyStatement,
  onApplyRationale,
  disabled,
}: {
  currentStatement: string;
  currentTitle: string;
  currentRationale: string;
  currentIssues: string[];
  projectContext: string;
  onApplyStatement?: (statement: string, title?: string, rationale?: string) => void;
  onApplyRationale?: (rationale: string) => void;
  disabled: boolean;
}) {
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<RewriteSuggestion[]>([]);
  const [rationaleLoading, setRationaleLoading] = useState(false);
  const [generatedRationale, setGeneratedRationale] = useState('');
  const [error, setError] = useState('');

  const handleImprove = async () => {
    if (!currentStatement || disabled) return;
    setLoading(true);
    setError('');
    try {
      const res = await aiWriterAPI.improve(currentStatement, {
        title: currentTitle,
        rationale: currentRationale,
        issues: currentIssues,
        domain_context: projectContext,
      });
      setSuggestions(res.data.suggestions);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Improvement failed');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateRationale = async () => {
    if (!currentStatement || disabled) return;
    setRationaleLoading(true);
    try {
      const res = await aiWriterAPI.generateRationale(currentStatement, {
        title: currentTitle,
      });
      setGeneratedRationale(res.data.rationale);
    } catch { /* silent */ }
    finally { setRationaleLoading(false); }
  };

  const hasStatement = currentStatement && currentStatement.length >= 5;

  return (
    <div className="space-y-4">
      {/* Current statement preview */}
      {hasStatement ? (
        <div className="rounded-lg border border-astra-border bg-astra-surface p-3">
          <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">Current Statement</div>
          <p className="text-[12px] leading-relaxed text-slate-300">{currentStatement}</p>
          {currentIssues.length > 0 && (
            <div className="mt-2 space-y-1">
              {currentIssues.map((issue, i) => (
                <div key={i} className="flex items-start gap-1.5 text-[10px] text-amber-400">
                  <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                  {issue}
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-slate-700 p-6 text-center">
          <Wand2 className="mx-auto mb-2 h-6 w-6 text-slate-600" />
          <p className="text-xs text-slate-500">Type a requirement statement in the form first, then use this panel to improve it.</p>
        </div>
      )}

      {/* Action buttons */}
      {hasStatement && (
        <div className="flex gap-2">
          <button
            onClick={handleImprove}
            disabled={loading || disabled}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-gradient-to-r from-violet-600 to-fuchsia-600 py-2 text-[11px] font-semibold text-white shadow-lg shadow-violet-500/20 transition hover:shadow-violet-500/30 disabled:opacity-40"
          >
            {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Wand2 className="h-3 w-3" />}
            {loading ? 'Improving…' : 'Get AI Suggestions'}
          </button>
          {!currentRationale && (
            <button
              onClick={handleGenerateRationale}
              disabled={rationaleLoading || disabled}
              className="flex items-center gap-1.5 rounded-lg border border-astra-border bg-astra-surface px-3 py-2 text-[11px] font-semibold text-slate-300 transition hover:bg-astra-surface-hover disabled:opacity-40"
            >
              {rationaleLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <BookOpen className="h-3 w-3" />}
              Rationale
            </button>
          )}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-[11px] text-red-400">{error}</div>
      )}

      {/* Improvement suggestions */}
      {suggestions.length > 0 && (
        <div className="space-y-3">
          <div className="text-xs font-semibold text-slate-300">{suggestions.length} Suggestion{suggestions.length !== 1 ? 's' : ''}</div>
          {suggestions.map((sugg, idx) => (
            <SuggestionCard
              key={idx}
              suggestion={sugg}
              index={idx}
              originalStatement={currentStatement}
              onApply={() => onApplyStatement?.(sugg.rewritten_statement)}
            />
          ))}
        </div>
      )}

      {/* Generated rationale */}
      {generatedRationale && (
        <div className="rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
          <div className="mb-1.5 flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-blue-400">
              <BookOpen className="h-3 w-3" />
              Generated Rationale
              <AIBadge />
            </div>
            <button
              onClick={() => onApplyRationale?.(generatedRationale)}
              className="flex items-center gap-1 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-400 transition hover:bg-emerald-500/20"
            >
              <Check className="h-3 w-3" />
              Apply
            </button>
          </div>
          <p className="text-[11px] leading-relaxed text-slate-300">{generatedRationale}</p>
        </div>
      )}
    </div>
  );
}


// ══════════════════════════════════════
//  Decompose Panel
// ══════════════════════════════════════

function DecomposePanel({
  currentStatement,
  currentTitle,
  currentLevel,
  currentType,
  projectContext,
  onBatchCreate,
  disabled,
}: {
  currentStatement: string;
  currentTitle: string;
  currentLevel: string;
  currentType: string;
  projectContext: string;
  onBatchCreate?: (requirements: GeneratedRequirement[]) => void;
  disabled: boolean;
}) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DecomposeResponse | null>(null);
  const [error, setError] = useState('');

  const LEVEL_NEXT: Record<string, string> = { L1: 'L2', L2: 'L3', L3: 'L4', L4: 'L5' };
  const targetLevel = LEVEL_NEXT[currentLevel] || 'L2';

  const handleDecompose = async () => {
    if (!currentStatement || disabled) return;
    setLoading(true);
    setError('');
    try {
      const res = await aiWriterAPI.decompose(currentStatement, {
        title: currentTitle,
        current_level: currentLevel,
        req_type: currentType,
        project_context: projectContext,
      });
      setResult(res.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Decomposition failed');
    } finally {
      setLoading(false);
    }
  };

  const hasStatement = currentStatement && currentStatement.length >= 5;

  return (
    <div className="space-y-4">
      {hasStatement ? (
        <div className="rounded-lg border border-astra-border bg-astra-surface p-3">
          <div className="mb-1 flex items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Parent ({currentLevel})</span>
            <ArrowRight className="h-3 w-3 text-slate-600" />
            <span className="text-[10px] font-bold uppercase tracking-wider text-violet-400">Children ({targetLevel})</span>
          </div>
          <p className="text-[12px] leading-relaxed text-slate-300">{currentStatement}</p>
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-slate-700 p-6 text-center">
          <GitBranch className="mx-auto mb-2 h-6 w-6 text-slate-600" />
          <p className="text-xs text-slate-500">Open an existing requirement to decompose it into sub-requirements.</p>
        </div>
      )}

      {hasStatement && (
        <button
          onClick={handleDecompose}
          disabled={loading || disabled}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-gradient-to-r from-violet-600 to-fuchsia-600 py-2 text-[11px] font-semibold text-white shadow-lg shadow-violet-500/20 transition hover:shadow-violet-500/30 disabled:opacity-40"
        >
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <GitBranch className="h-3 w-3" />}
          {loading ? 'Decomposing…' : `Generate ${targetLevel} Sub-Requirements`}
        </button>
      )}

      {error && (
        <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-[11px] text-red-400">{error}</div>
      )}

      {result && result.sub_requirements.length > 0 && (
        <div className="space-y-2">
          {result.decomposition_rationale && (
            <div className="rounded-lg border border-violet-500/10 bg-violet-500/5 px-3 py-2 text-[11px] text-violet-300">
              <Lightbulb className="mb-0.5 inline h-3 w-3" /> {result.decomposition_rationale}
            </div>
          )}

          <div className="text-xs font-semibold text-slate-300">
            {result.sub_requirements.length} Sub-Requirements ({result.target_level})
          </div>

          {result.sub_requirements.map((req, idx) => (
            <ExtractedReqCard
              key={idx}
              req={req}
              index={idx}
              isSelected={true}
              onToggle={() => {}}
              onApply={() => {}}
              onEdit={(field, value) => {
                setResult(prev => {
                  if (!prev) return prev;
                  const next = { ...prev, sub_requirements: [...prev.sub_requirements] };
                  next.sub_requirements[idx] = { ...next.sub_requirements[idx], [field]: value };
                  return next;
                });
              }}
              compact
            />
          ))}

          <button
            onClick={() => onBatchCreate?.(result.sub_requirements)}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 py-2 text-xs font-semibold text-white transition hover:bg-emerald-500"
          >
            <Plus className="h-3.5 w-3.5" />
            Create All {result.sub_requirements.length} as Children
          </button>
        </div>
      )}
    </div>
  );
}


// ══════════════════════════════════════
//  Extracted Requirement Card
// ══════════════════════════════════════

function ExtractedReqCard({
  req,
  index,
  isSelected,
  onToggle,
  onApply,
  onEdit,
  compact = false,
}: {
  req: GeneratedRequirement;
  index: number;
  isSelected: boolean;
  onToggle: () => void;
  onApply: () => void;
  onEdit: (field: string, value: string) => void;
  compact?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);

  const TYPE_COLORS: Record<string, string> = {
    functional: 'text-blue-400 bg-blue-500/10 border-blue-500/30',
    performance: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
    interface: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/30',
    safety: 'text-red-400 bg-red-500/10 border-red-500/30',
    security: 'text-rose-400 bg-rose-500/10 border-rose-500/30',
    environmental: 'text-green-400 bg-green-500/10 border-green-500/30',
    reliability: 'text-violet-400 bg-violet-500/10 border-violet-500/30',
    constraint: 'text-slate-400 bg-slate-500/10 border-slate-500/30',
  };

  return (
    <div className={`rounded-lg border bg-astra-surface transition ${
      isSelected ? 'border-violet-500/30' : 'border-astra-border opacity-60'
    }`}>
      <div className="flex items-start gap-2.5 p-3">
        {!compact && (
          <input
            type="checkbox"
            checked={isSelected}
            onChange={onToggle}
            className="mt-1 h-3.5 w-3.5 rounded border-slate-600 bg-slate-800 text-violet-500 focus:ring-violet-500/30"
          />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5 mb-1">
            <AIBadge />
            <span className={`rounded-full border px-1.5 py-0 text-[9px] font-bold ${TYPE_COLORS[req.req_type] || TYPE_COLORS.functional}`}>
              {req.req_type}
            </span>
            <span className="rounded-full bg-slate-700/40 px-1.5 py-0 text-[9px] font-bold text-slate-400">
              {req.level}
            </span>
            <span className="rounded-full bg-slate-700/40 px-1.5 py-0 text-[9px] text-slate-500">
              {Math.round(req.confidence * 100)}%
            </span>
          </div>

          {/* Editable title */}
          {editing === 'title' ? (
            <input
              autoFocus
              value={req.title}
              onChange={e => onEdit('title', e.target.value)}
              onBlur={() => setEditing(null)}
              onKeyDown={e => e.key === 'Enter' && setEditing(null)}
              className="mb-1 w-full rounded border border-violet-500/30 bg-astra-bg px-2 py-1 text-[11px] font-semibold text-slate-200 outline-none"
            />
          ) : (
            <div
              onClick={() => setEditing('title')}
              className="mb-1 cursor-text text-[11px] font-semibold text-slate-200 hover:text-white"
            >
              {req.title || 'Click to add title'}
            </div>
          )}

          {/* Editable statement */}
          {editing === 'statement' ? (
            <textarea
              autoFocus
              value={req.statement}
              onChange={e => onEdit('statement', e.target.value)}
              onBlur={() => setEditing(null)}
              rows={3}
              className="w-full rounded border border-violet-500/30 bg-astra-bg px-2 py-1 text-[11px] text-slate-300 outline-none resize-none"
            />
          ) : (
            <p
              onClick={() => setEditing('statement')}
              className="cursor-text text-[11px] leading-relaxed text-slate-400 hover:text-slate-300"
            >
              {req.statement || 'Click to add statement'}
            </p>
          )}

          {/* Expand for details */}
          <button
            onClick={() => setExpanded(!expanded)}
            className="mt-1.5 flex items-center gap-1 text-[10px] text-slate-500 hover:text-slate-300"
          >
            {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            {expanded ? 'Less' : 'Details'}
          </button>

          {expanded && (
            <div className="mt-2 space-y-2 border-t border-astra-border pt-2">
              {req.rationale && (
                <div>
                  <span className="text-[9px] font-bold uppercase text-slate-500">Rationale</span>
                  <p className="text-[10px] text-slate-400">{req.rationale}</p>
                </div>
              )}
              {req.source_fragment && (
                <div>
                  <span className="text-[9px] font-bold uppercase text-slate-500">Source</span>
                  <p className="text-[10px] italic text-slate-500">"{req.source_fragment}"</p>
                </div>
              )}
              {req.notes && (
                <div>
                  <span className="text-[9px] font-bold uppercase text-slate-500">Notes</span>
                  <p className="text-[10px] text-slate-500">{req.notes}</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


// ══════════════════════════════════════
//  Suggestion Card (Improve mode)
// ══════════════════════════════════════

function SuggestionCard({
  suggestion,
  index,
  originalStatement,
  onApply,
}: {
  suggestion: RewriteSuggestion;
  index: number;
  originalStatement: string;
  onApply: () => void;
}) {
  return (
    <div className="rounded-lg border border-astra-border bg-astra-surface p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] font-bold text-slate-400">Option {index + 1}</span>
          <AIBadge />
          {suggestion.quality_delta && (
            <span className="rounded-full bg-emerald-500/10 px-1.5 py-0 text-[9px] font-bold text-emerald-400">
              {suggestion.quality_delta}
            </span>
          )}
        </div>
        <button
          onClick={onApply}
          className="flex items-center gap-1 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[10px] font-semibold text-emerald-400 transition hover:bg-emerald-500/20"
        >
          <Check className="h-3 w-3" />
          Apply
        </button>
      </div>

      {/* Statement with changes highlighted */}
      <p className="text-[12px] leading-relaxed text-slate-200">
        {suggestion.rewritten_statement}
      </p>

      {/* Changes made */}
      {suggestion.changes_made.length > 0 && (
        <div className="mt-2 space-y-0.5">
          {suggestion.changes_made.map((change, i) => (
            <div key={i} className="flex items-start gap-1.5 text-[10px] text-emerald-400/80">
              <CheckCircle className="mt-0.5 h-3 w-3 shrink-0" />
              {change}
            </div>
          ))}
        </div>
      )}

      {suggestion.explanation && (
        <p className="mt-1.5 text-[10px] italic text-slate-500">{suggestion.explanation}</p>
      )}
    </div>
  );
}


// ══════════════════════════════════════
//  AI Generated Badge
// ══════════════════════════════════════

function AIBadge() {
  return (
    <span className="inline-flex items-center gap-0.5 rounded-full bg-violet-500/15 px-1.5 py-0 text-[8px] font-bold uppercase tracking-wider text-violet-400">
      <Sparkles className="h-2 w-2" />
      AI
    </span>
  );
}
