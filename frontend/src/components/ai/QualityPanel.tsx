'use client';

/**
 * ASTRA — AI Quality Analysis Panel
 * ====================================
 * File: frontend/src/components/ai/QualityPanel.tsx   ← NEW
 *
 * Reusable component that shows:
 *   - "Run AI Analysis" button (Tier 2 single-requirement)
 *   - Dimension scores as radar chart (SVG)
 *   - Issues list with severity badges
 *   - Suggested rewrites with "Apply" button
 *   - Confidence indicator
 *   - AI feedback buttons (accept/reject per suggestion)
 *
 * Also exports BatchAnalysisPanel for the requirements list page.
 */

import { useState, useCallback } from 'react';
import {
  Sparkles, Loader2, AlertTriangle, CheckCircle, Info,
  ChevronDown, ChevronUp, Copy, ThumbsUp, ThumbsDown,
  Zap, Shield, Target, Layers, GitBranch, Wrench,
  BarChart3,
} from 'lucide-react';
import api from '@/lib/api';

/* ══════════════════════════════════════
   Types
   ══════════════════════════════════════ */

interface QualityIssue {
  severity: string;
  category: string;
  description: string;
  location: string;
  suggestion: string;
}

interface DeepResult {
  overall_score: number;
  dimensions: Record<string, number>;
  issues: QualityIssue[];
  suggested_rewrites: string[];
  verification_approach: string;
  confidence: number;
  analysis_source: string;
  model_used: string;
}

interface BatchResult {
  contradictions: { req_ids: string[]; description: string; severity: string }[];
  redundancies: { req_ids: string[]; description: string; suggestion: string }[];
  gaps: { category: string; description: string; suggestion: string }[];
  completeness_score: number;
  completeness_notes: string;
  confidence: number;
  total_requirements_analyzed: number;
  analysis_source: string;
}

const SEVERITY_STYLES: Record<string, { bg: string; text: string; icon: any }> = {
  critical: { bg: 'bg-red-500/15', text: 'text-red-400', icon: AlertTriangle },
  warning:  { bg: 'bg-amber-500/15', text: 'text-amber-400', icon: AlertTriangle },
  info:     { bg: 'bg-blue-500/15', text: 'text-blue-400', icon: Info },
};

const DIM_ICONS: Record<string, any> = {
  ambiguity: Target, testability: CheckCircle, completeness: Layers,
  atomicity: GitBranch, consistency: Shield, feasibility: Wrench,
};

/* ══════════════════════════════════════
   SVG Radar Chart
   ══════════════════════════════════════ */

function RadarChart({ dimensions }: { dimensions: Record<string, number> }) {
  const keys = ['ambiguity', 'testability', 'completeness', 'atomicity', 'consistency', 'feasibility'];
  const cx = 100, cy = 100, r = 80;
  const n = keys.length;

  const pointForAngle = (angle: number, radius: number) => ({
    x: cx + radius * Math.cos(angle - Math.PI / 2),
    y: cy + radius * Math.sin(angle - Math.PI / 2),
  });

  // Grid rings
  const rings = [0.25, 0.5, 0.75, 1.0];
  const gridPaths = rings.map(scale => {
    const pts = keys.map((_, i) => pointForAngle((2 * Math.PI * i) / n, r * scale));
    return pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ') + ' Z';
  });

  // Data polygon
  const dataPoints = keys.map((k, i) => {
    const val = (dimensions[k] || 0) / 100;
    return pointForAngle((2 * Math.PI * i) / n, r * val);
  });
  const dataPath = dataPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ') + ' Z';

  // Labels
  const labels = keys.map((k, i) => {
    const p = pointForAngle((2 * Math.PI * i) / n, r + 18);
    return { key: k, x: p.x, y: p.y, score: dimensions[k] || 0 };
  });

  return (
    <svg viewBox="0 0 200 200" className="w-full max-w-[220px] mx-auto">
      {/* Grid */}
      {gridPaths.map((d, i) => (
        <path key={i} d={d} fill="none" stroke="#1E293B" strokeWidth="0.5" />
      ))}
      {/* Axis lines */}
      {keys.map((_, i) => {
        const p = pointForAngle((2 * Math.PI * i) / n, r);
        return <line key={i} x1={cx} y1={cy} x2={p.x} y2={p.y} stroke="#1E293B" strokeWidth="0.5" />;
      })}
      {/* Data */}
      <path d={dataPath} fill="rgba(59,130,246,0.15)" stroke="#3B82F6" strokeWidth="1.5" />
      {dataPoints.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r="3" fill="#3B82F6" />
      ))}
      {/* Labels */}
      {labels.map(l => (
        <text key={l.key} x={l.x} y={l.y}
          textAnchor="middle" dominantBaseline="middle"
          className="text-[7px] fill-slate-400 font-semibold">
          {l.key.slice(0, 4)} {l.score}
        </text>
      ))}
    </svg>
  );
}


/* ══════════════════════════════════════
   Single Requirement AI Panel
   ══════════════════════════════════════ */

interface QualityPanelProps {
  requirementId?: number;
  statement: string;
  title?: string;
  rationale?: string;
  onApplyRewrite?: (text: string) => void;
}

export default function QualityPanel({
  requirementId, statement, title = '', rationale = '', onApplyRewrite,
}: QualityPanelProps) {
  const [result, setResult] = useState<DeepResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const [error, setError] = useState('');

  const runAnalysis = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.post('/requirements/quality-check/deep', {
        statement, title, rationale,
      });
      setResult(res.data);
    } catch (e: any) {
      setError(e.response?.data?.detail || 'AI analysis failed');
    }
    setLoading(false);
  }, [statement, title, rationale]);

  const sendFeedback = async (suggestionType: string, text: string, accepted: boolean) => {
    if (!requirementId) return;
    try {
      await api.post(`/requirements/${requirementId}/ai-feedback`, {
        requirement_id: requirementId,
        suggestion_type: suggestionType,
        suggestion_text: text,
        accepted,
      });
    } catch { /* ignore */ }
  };

  const scoreColor = (s: number) =>
    s >= 80 ? 'text-emerald-400' : s >= 60 ? 'text-amber-400' : 'text-red-400';

  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface">
      {/* Header */}
      <button onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between p-4 text-left">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-violet-400" />
          <span className="text-sm font-bold text-slate-200">AI Quality Analysis</span>
          {result && (
            <span className={`ml-2 text-xs font-bold ${scoreColor(result.overall_score)}`}>
              {result.overall_score.toFixed(0)}
            </span>
          )}
          {result?.analysis_source === 'regex_fallback' && (
            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[9px] font-bold text-amber-400">
              Regex Only
            </span>
          )}
        </div>
        {expanded ? <ChevronUp className="h-4 w-4 text-slate-500" /> : <ChevronDown className="h-4 w-4 text-slate-500" />}
      </button>

      {expanded && (
        <div className="border-t border-astra-border p-4">
          {/* Run button */}
          {!result && (
            <button onClick={runAnalysis} disabled={loading || !statement}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-violet-500 py-2.5 text-sm font-semibold text-white transition hover:bg-violet-600 disabled:opacity-50">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              {loading ? 'Analyzing…' : 'Run AI Analysis'}
            </button>
          )}

          {error && (
            <div className="mt-3 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
              {error}
            </div>
          )}

          {result && (
            <div className="space-y-4">
              {/* Score + confidence */}
              <div className="flex items-center justify-between">
                <div>
                  <span className={`text-3xl font-bold ${scoreColor(result.overall_score)}`}>
                    {result.overall_score.toFixed(0)}
                  </span>
                  <span className="text-sm text-slate-500"> / 100</span>
                </div>
                <div className="text-right text-[10px] text-slate-500">
                  Confidence: {(result.confidence * 100).toFixed(0)}%
                  {result.model_used && <> · {result.model_used}</>}
                </div>
              </div>

              {/* Radar chart */}
              {result.dimensions && Object.keys(result.dimensions).length > 0 && (
                <RadarChart dimensions={result.dimensions} />
              )}

              {/* Dimension scores */}
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(result.dimensions || {}).map(([key, score]) => {
                  const Icon = DIM_ICONS[key] || Shield;
                  return (
                    <div key={key} className="flex items-center gap-2 rounded-lg bg-astra-surface-alt p-2">
                      <Icon className="h-3.5 w-3.5 text-slate-400" />
                      <span className="flex-1 text-[11px] text-slate-300 capitalize">{key}</span>
                      <span className={`text-xs font-bold ${scoreColor(score)}`}>{score}</span>
                    </div>
                  );
                })}
              </div>

              {/* Issues */}
              {result.issues.length > 0 && (
                <div>
                  <h4 className="mb-2 text-xs font-bold text-slate-300">Issues ({result.issues.length})</h4>
                  <div className="space-y-1.5">
                    {result.issues.map((issue, i) => {
                      const style = SEVERITY_STYLES[issue.severity] || SEVERITY_STYLES.info;
                      const SevIcon = style.icon;
                      return (
                        <div key={i} className={`rounded-lg p-2.5 ${style.bg}`}>
                          <div className="flex items-start gap-2">
                            <SevIcon className={`h-3.5 w-3.5 shrink-0 mt-0.5 ${style.text}`} />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-1.5 mb-0.5">
                                <span className={`text-[10px] font-bold uppercase ${style.text}`}>{issue.severity}</span>
                                <span className="text-[10px] text-slate-500">· {issue.category}</span>
                              </div>
                              <p className="text-xs text-slate-300">{issue.description}</p>
                              {issue.location && (
                                <p className="mt-1 text-[10px] text-slate-500 italic">"{issue.location}"</p>
                              )}
                              {issue.suggestion && (
                                <p className="mt-1 text-[10px] text-blue-400">Suggestion: {issue.suggestion}</p>
                              )}
                            </div>
                            <div className="flex gap-0.5 shrink-0">
                              <button onClick={() => sendFeedback('issue', issue.description, true)}
                                className="p-1 text-slate-600 hover:text-emerald-400" title="Helpful">
                                <ThumbsUp className="h-3 w-3" />
                              </button>
                              <button onClick={() => sendFeedback('issue', issue.description, false)}
                                className="p-1 text-slate-600 hover:text-red-400" title="Not helpful">
                                <ThumbsDown className="h-3 w-3" />
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Verification approach */}
              {result.verification_approach && (
                <div className="rounded-lg bg-emerald-500/10 p-3">
                  <div className="mb-1 text-[10px] font-bold text-emerald-400">Recommended Verification</div>
                  <p className="text-xs text-slate-300">{result.verification_approach}</p>
                </div>
              )}

              {/* Suggested rewrites */}
              {result.suggested_rewrites.length > 0 && (
                <div>
                  <h4 className="mb-2 text-xs font-bold text-slate-300">Suggested Rewrites</h4>
                  <div className="space-y-2">
                    {result.suggested_rewrites.map((rw, i) => (
                      <div key={i} className="rounded-lg border border-astra-border bg-astra-surface-alt p-3">
                        <p className="text-xs text-slate-200 leading-relaxed mb-2">{rw}</p>
                        <div className="flex items-center gap-2">
                          <span className="rounded-full bg-violet-500/10 px-2 py-0.5 text-[9px] font-bold text-violet-400">
                            AI-generated
                          </span>
                          {onApplyRewrite && (
                            <button onClick={() => { onApplyRewrite(rw); sendFeedback('rewrite', rw, true); }}
                              className="flex items-center gap-1 rounded-lg bg-blue-500 px-2.5 py-1 text-[10px] font-semibold text-white hover:bg-blue-600">
                              <Copy className="h-3 w-3" /> Apply
                            </button>
                          )}
                          <button onClick={() => sendFeedback('rewrite', rw, true)}
                            className="p-1 text-slate-600 hover:text-emerald-400"><ThumbsUp className="h-3 w-3" /></button>
                          <button onClick={() => sendFeedback('rewrite', rw, false)}
                            className="p-1 text-slate-600 hover:text-red-400"><ThumbsDown className="h-3 w-3" /></button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Re-run */}
              <button onClick={runAnalysis} disabled={loading}
                className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-astra-border py-2 text-xs font-semibold text-slate-400 transition hover:text-slate-200 disabled:opacity-50">
                {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                Re-run Analysis
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}


/* ══════════════════════════════════════
   Batch Analysis Panel (for list page)
   ══════════════════════════════════════ */

interface BatchPanelProps {
  projectId: number;
}

export function BatchAnalysisPanel({ projectId }: BatchPanelProps) {
  const [result, setResult] = useState<BatchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const runBatch = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.post('/requirements/quality-check/batch', {
        project_id: projectId,
      });
      setResult(res.data);
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Batch analysis failed');
    }
    setLoading(false);
  };

  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-violet-400" />
          <h3 className="text-sm font-bold text-slate-200">Cross-Requirement Analysis</h3>
        </div>
        <button onClick={runBatch} disabled={loading}
          className="flex items-center gap-1.5 rounded-lg bg-violet-500 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-violet-600 disabled:opacity-50">
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
          {loading ? 'Analyzing…' : 'Analyze All'}
        </button>
      </div>

      {error && (
        <div className="mb-3 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</div>
      )}

      {result && (
        <div className="space-y-4">
          {/* Overview */}
          <div className="flex items-center gap-4">
            <div>
              <span className="text-2xl font-bold text-slate-200">{result.completeness_score}</span>
              <span className="text-xs text-slate-500"> / 100 completeness</span>
            </div>
            <div className="text-[10px] text-slate-500">
              {result.total_requirements_analyzed} requirements · Confidence {(result.confidence * 100).toFixed(0)}%
              {result.analysis_source !== 'ai' && (
                <span className="ml-1 text-amber-400">({result.analysis_source})</span>
              )}
            </div>
          </div>

          {result.completeness_notes && (
            <p className="text-xs text-slate-400 leading-relaxed">{result.completeness_notes}</p>
          )}

          {/* Contradictions */}
          {result.contradictions.length > 0 && (
            <div>
              <h4 className="mb-2 text-xs font-bold text-red-400">
                Contradictions ({result.contradictions.length})
              </h4>
              {result.contradictions.map((c, i) => (
                <div key={i} className="mb-1.5 rounded-lg bg-red-500/10 p-2.5 text-xs text-slate-300">
                  <span className="font-mono text-red-400">{c.req_ids.join(' ↔ ')}</span>: {c.description}
                </div>
              ))}
            </div>
          )}

          {/* Redundancies */}
          {result.redundancies.length > 0 && (
            <div>
              <h4 className="mb-2 text-xs font-bold text-amber-400">
                Redundancies ({result.redundancies.length})
              </h4>
              {result.redundancies.map((r, i) => (
                <div key={i} className="mb-1.5 rounded-lg bg-amber-500/10 p-2.5 text-xs text-slate-300">
                  <span className="font-mono text-amber-400">{r.req_ids.join(' ≈ ')}</span>: {r.description}
                  {r.suggestion && <p className="mt-1 text-blue-400">→ {r.suggestion}</p>}
                </div>
              ))}
            </div>
          )}

          {/* Gaps */}
          {result.gaps.length > 0 && (
            <div>
              <h4 className="mb-2 text-xs font-bold text-blue-400">
                Coverage Gaps ({result.gaps.length})
              </h4>
              {result.gaps.map((g, i) => (
                <div key={i} className="mb-1.5 rounded-lg bg-blue-500/10 p-2.5 text-xs text-slate-300">
                  <span className="font-semibold text-blue-400">[{g.category}]</span> {g.description}
                  {g.suggestion && <p className="mt-1 text-slate-400 italic">Suggested: {g.suggestion}</p>}
                </div>
              ))}
            </div>
          )}

          {result.contradictions.length === 0 && result.redundancies.length === 0 && result.gaps.length === 0 && (
            <div className="flex items-center gap-2 text-xs text-emerald-400">
              <CheckCircle className="h-4 w-4" /> No contradictions, redundancies, or gaps detected
            </div>
          )}
        </div>
      )}
    </div>
  );
}
