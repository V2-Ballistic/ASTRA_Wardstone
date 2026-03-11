/**
 * ASTRA — Trace Suggestions Panel
 * ==================================
 * File: frontend/src/components/ai/TraceSuggestionsPanel.tsx   ← NEW
 *
 * Shows AI-suggested trace links on the requirement detail page.
 * One-click "Create Link" for each suggestion, with accept/reject actions.
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Network, Sparkles, Loader2, ChevronDown, ChevronUp,
  Check, X, ExternalLink, ArrowRight,
} from 'lucide-react';
import { aiAPI, type TraceSuggestion } from '@/lib/ai-api';
import { traceabilityAPI } from '@/lib/api';

interface TraceSuggestionsPanelProps {
  requirementId: number;
  projectId: number;
  onLinkCreated?: () => void;
}

const LINK_TYPE_LABELS: Record<string, string> = {
  derives: 'Derives From',
  refines: 'Refined By',
  satisfies: 'Satisfies',
  related_to: 'Related To',
  verifies: 'Verified By',
};

const LINK_TYPE_COLORS: Record<string, string> = {
  derives: 'text-violet-400 bg-violet-500/10 border-violet-500/30',
  refines: 'text-sky-400 bg-sky-500/10 border-sky-500/30',
  satisfies: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
  related_to: 'text-slate-400 bg-slate-500/10 border-slate-500/30',
  verifies: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
};

export default function TraceSuggestionsPanel({
  requirementId,
  projectId,
  onLinkCreated,
}: TraceSuggestionsPanelProps) {
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<TraceSuggestion[]>([]);
  const [aiAvailable, setAiAvailable] = useState(true);
  const [expanded, setExpanded] = useState(true);
  const [creating, setCreating] = useState<number | null>(null);
  const [error, setError] = useState('');

  const loadSuggestions = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await aiAPI.getTraceSuggestions(requirementId, projectId);
      setSuggestions(res.data.suggestions);
      setAiAvailable(res.data.ai_available);
    } catch (err: any) {
      if (err.response?.status !== 404) {
        setError('Failed to load suggestions');
      }
      setAiAvailable(false);
    } finally {
      setLoading(false);
    }
  }, [requirementId, projectId]);

  useEffect(() => {
    loadSuggestions();
  }, [loadSuggestions]);

  const handleCreateLink = async (suggestion: TraceSuggestion) => {
    setCreating(suggestion.target_id);
    try {
      await traceabilityAPI.createLink({
        source_type: 'requirement',
        source_id: requirementId,
        target_type: suggestion.target_type,
        target_id: suggestion.target_id,
        link_type: suggestion.suggested_link_type,
        description: `AI-suggested (${Math.round(suggestion.confidence * 100)}% confidence)`,
      });

      // Remove from list
      setSuggestions((prev) => prev.filter((s) => s.target_id !== suggestion.target_id));

      // Submit feedback if suggestion has an ID
      if (suggestion.suggestion_id) {
        try {
          await aiAPI.submitFeedback(suggestion.suggestion_id, 'accepted');
        } catch { /* non-critical */ }
      }

      onLinkCreated?.();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create link');
    } finally {
      setCreating(null);
    }
  };

  const handleDismiss = async (suggestion: TraceSuggestion) => {
    setSuggestions((prev) => prev.filter((s) => s.target_id !== suggestion.target_id));
    if (suggestion.suggestion_id) {
      try {
        await aiAPI.submitFeedback(suggestion.suggestion_id, 'dismissed');
      } catch { /* non-critical */ }
    }
  };

  if (!aiAvailable) return null;

  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-4 py-3 text-left transition hover:bg-astra-surface-hover"
      >
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-violet-500/10">
            <Sparkles className="h-3.5 w-3.5 text-violet-400" />
          </div>
          <span className="text-sm font-semibold text-slate-200">
            Suggested Trace Links
          </span>
          {suggestions.length > 0 && (
            <span className="rounded-full bg-violet-500/15 px-2 py-0.5 text-[10px] font-bold text-violet-400">
              {suggestions.length}
            </span>
          )}
        </div>
        {expanded ? (
          <ChevronUp className="h-4 w-4 text-slate-500" />
        ) : (
          <ChevronDown className="h-4 w-4 text-slate-500" />
        )}
      </button>

      {/* Content */}
      {expanded && (
        <div className="border-t border-astra-border px-4 py-3">
          {loading ? (
            <div className="flex items-center gap-2 py-4 text-sm text-slate-400">
              <Loader2 className="h-4 w-4 animate-spin text-violet-400" />
              Analyzing semantic relationships…
            </div>
          ) : suggestions.length === 0 ? (
            <div className="py-3 text-center text-[11px] text-slate-500">
              No trace link suggestions at this time.
              <button onClick={loadSuggestions} className="ml-1 text-blue-400 hover:underline">
                Refresh
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              {suggestions.map((sugg) => (
                <div
                  key={`${sugg.target_type}-${sugg.target_id}`}
                  className="rounded-lg border border-slate-700/40 bg-slate-800/20 p-3"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-[11px] font-semibold text-blue-400">
                          {sugg.target_req_id}
                        </span>
                        <span className={`rounded-full border px-1.5 py-0 text-[9px] font-bold ${
                          LINK_TYPE_COLORS[sugg.suggested_link_type] || LINK_TYPE_COLORS.related_to
                        }`}>
                          {LINK_TYPE_LABELS[sugg.suggested_link_type] || sugg.suggested_link_type}
                        </span>
                        <ConfidenceBadge score={sugg.confidence} />
                      </div>
                      <p className="mt-1 text-[11px] text-slate-400">
                        {sugg.target_title}
                      </p>
                      {sugg.explanation && (
                        <p className="mt-1 text-[10px] italic text-slate-500">
                          {sugg.explanation}
                        </p>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex shrink-0 items-center gap-1">
                      <button
                        onClick={() => handleCreateLink(sugg)}
                        disabled={creating === sugg.target_id}
                        className="flex items-center gap-1 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-[10px] font-semibold text-emerald-400 transition hover:bg-emerald-500/20 disabled:opacity-50"
                      >
                        {creating === sugg.target_id ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <Check className="h-3 w-3" />
                        )}
                        Link
                      </button>
                      <button
                        onClick={() => handleDismiss(sugg)}
                        className="rounded-md border border-slate-600/30 p-1 text-slate-500 transition hover:bg-slate-700/50 hover:text-slate-300"
                        aria-label="Dismiss suggestion"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
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


function ConfidenceBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color =
    pct >= 80 ? 'text-emerald-400'
    : pct >= 60 ? 'text-amber-400'
    : 'text-slate-400';

  return (
    <span className={`text-[9px] font-mono font-bold ${color}`}>
      {pct}%
    </span>
  );
}
