/**
 * ASTRA — Verification Suggestion Panel
 * ========================================
 * File: frontend/src/components/ai/VerificationSuggestionPanel.tsx   ← NEW
 *
 * Shows AI-suggested verification method and criteria.
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  ClipboardCheck, Sparkles, Loader2, ChevronDown, ChevronUp,
  FlaskConical, FileSearch, Eye, Monitor, Check,
} from 'lucide-react';
import { aiAPI, type VerificationSuggestion } from '@/lib/ai-api';

interface VerificationSuggestionPanelProps {
  requirementId: number;
  onApply?: (method: string, criteria: string) => void;
}

const METHOD_CONFIG: Record<string, { icon: any; label: string; color: string }> = {
  test: { icon: FlaskConical, label: 'Test', color: 'text-emerald-400 bg-emerald-500/10' },
  analysis: { icon: FileSearch, label: 'Analysis', color: 'text-blue-400 bg-blue-500/10' },
  inspection: { icon: Eye, label: 'Inspection', color: 'text-amber-400 bg-amber-500/10' },
  demonstration: { icon: Monitor, label: 'Demonstration', color: 'text-violet-400 bg-violet-500/10' },
};

export default function VerificationSuggestionPanel({
  requirementId,
  onApply,
}: VerificationSuggestionPanelProps) {
  const [loading, setLoading] = useState(false);
  const [suggestion, setSuggestion] = useState<VerificationSuggestion | null>(null);
  const [expanded, setExpanded] = useState(true);
  const [applied, setApplied] = useState(false);
  const [error, setError] = useState('');

  const loadSuggestion = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await aiAPI.getVerificationSuggestion(requirementId);
      setSuggestion(res.data);
    } catch (err: any) {
      if (err.response?.status !== 404) {
        setError('Failed to load suggestion');
      }
    } finally {
      setLoading(false);
    }
  }, [requirementId]);

  useEffect(() => {
    loadSuggestion();
  }, [loadSuggestion]);

  const handleApply = () => {
    if (suggestion && onApply) {
      onApply(suggestion.suggested_method, suggestion.suggested_criteria);
      setApplied(true);
    }
  };

  if (!suggestion?.ai_available && !loading) return null;

  const method = suggestion?.suggested_method || '';
  const config = METHOD_CONFIG[method] || METHOD_CONFIG.test;
  const Icon = config.icon;

  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-4 py-3 text-left transition hover:bg-astra-surface-hover"
      >
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-500/10">
            <ClipboardCheck className="h-3.5 w-3.5 text-amber-400" />
          </div>
          <span className="text-sm font-semibold text-slate-200">
            Suggested Verification
          </span>
          {suggestion && !applied && (
            <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold text-amber-400">
              AI
            </span>
          )}
          {applied && (
            <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold text-emerald-400">
              Applied
            </span>
          )}
        </div>
        {expanded ? (
          <ChevronUp className="h-4 w-4 text-slate-500" />
        ) : (
          <ChevronDown className="h-4 w-4 text-slate-500" />
        )}
      </button>

      {expanded && (
        <div className="border-t border-astra-border px-4 py-3">
          {loading ? (
            <div className="flex items-center gap-2 py-4 text-sm text-slate-400">
              <Loader2 className="h-4 w-4 animate-spin text-amber-400" />
              Analyzing requirement for verification approach…
            </div>
          ) : suggestion ? (
            <div className="space-y-3">
              {/* Method recommendation */}
              <div className="flex items-center gap-3">
                <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${config.color}`}>
                  <Icon className="h-5 w-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-slate-200">
                      {config.label}
                    </span>
                    <span className="text-[10px] font-mono text-slate-500">
                      {Math.round(suggestion.confidence * 100)}% confidence
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400">
                    {suggestion.method_rationale}
                  </p>
                </div>
              </div>

              {/* Criteria */}
              <div>
                <h4 className="mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  Verification Criteria
                </h4>
                <p className="text-[11px] leading-relaxed text-slate-300">
                  {suggestion.suggested_criteria}
                </p>
              </div>

              {/* Success conditions */}
              {suggestion.success_conditions.length > 0 && (
                <div>
                  <h4 className="mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                    Success Conditions
                  </h4>
                  <ul className="space-y-1">
                    {suggestion.success_conditions.map((cond, i) => (
                      <li key={i} className="flex items-start gap-1.5 text-[11px] text-slate-400">
                        <Check className="mt-0.5 h-3 w-3 shrink-0 text-emerald-500/60" />
                        {cond}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Apply button */}
              {onApply && !applied && (
                <button
                  onClick={handleApply}
                  className="flex items-center gap-1.5 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-[11px] font-semibold text-amber-400 transition hover:bg-amber-500/20"
                >
                  <Sparkles className="h-3 w-3" />
                  Apply This Verification Method
                </button>
              )}
            </div>
          ) : (
            <div className="py-3 text-center text-[11px] text-slate-500">
              No verification suggestion available.
            </div>
          )}

          {error && (
            <div className="mt-2 text-[10px] text-red-400">{error}</div>
          )}
        </div>
      )}
    </div>
  );
}
