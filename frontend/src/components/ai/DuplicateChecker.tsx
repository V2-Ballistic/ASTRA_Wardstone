/**
 * ASTRA — Duplicate Checker Component
 * ======================================
 * File: frontend/src/components/ai/DuplicateChecker.tsx   ← NEW
 *
 * Inline component for the requirement creation form.
 * After the user types a statement, auto-checks for duplicates
 * (debounced) and shows similar existing requirements.
 */

'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { AlertTriangle, CheckCircle, Loader2, Link2, X, Sparkles } from 'lucide-react';
import { aiAPI, type SimilarRequirement } from '@/lib/ai-api';

interface DuplicateCheckerProps {
  statement: string;
  projectId: number | null;
  title?: string;
  onLinkToExisting?: (requirementId: number) => void;
  debounceMs?: number;
}

export default function DuplicateChecker({
  statement,
  projectId,
  title = '',
  onLinkToExisting,
  debounceMs = 800,
}: DuplicateCheckerProps) {
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<SimilarRequirement[]>([]);
  const [isDuplicate, setIsDuplicate] = useState(false);
  const [aiAvailable, setAiAvailable] = useState(true);
  const [dismissed, setDismissed] = useState(false);
  const [error, setError] = useState('');
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  const checkDuplicates = useCallback(async (text: string) => {
    if (!projectId || text.length < 15) {
      setResults([]);
      setIsDuplicate(false);
      return;
    }

    setLoading(true);
    setError('');

    try {
      const res = await aiAPI.checkDuplicate(text, projectId, title);
      setResults(res.data.similar_requirements);
      setIsDuplicate(res.data.is_likely_duplicate);
      setAiAvailable(res.data.ai_available);
      setDismissed(false);
    } catch (err: any) {
      if (err.response?.status === 404) {
        setAiAvailable(false);
      } else {
        setError('Duplicate check failed');
      }
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, [projectId, title]);

  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    if (statement.length < 15) {
      setResults([]);
      setIsDuplicate(false);
      return;
    }

    debounceRef.current = setTimeout(() => {
      checkDuplicates(statement);
    }, debounceMs);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [statement, checkDuplicates, debounceMs]);

  // Don't render if AI unavailable or no project
  if (!aiAvailable || !projectId) return null;

  // Dismissed state
  if (dismissed && results.length > 0) {
    return (
      <button
        type="button"
        onClick={() => setDismissed(false)}
        className="mt-2 flex items-center gap-1.5 text-[11px] text-amber-400/60 transition hover:text-amber-400"
      >
        <Sparkles className="h-3 w-3" />
        {results.length} similar requirement{results.length !== 1 ? 's' : ''} found — click to review
      </button>
    );
  }

  // Loading indicator
  if (loading) {
    return (
      <div className="mt-2 flex items-center gap-2 text-[11px] text-slate-400">
        <Loader2 className="h-3 w-3 animate-spin text-blue-400" />
        Checking for similar requirements…
      </div>
    );
  }

  // No results
  if (results.length === 0 && statement.length >= 15 && !loading) {
    return (
      <div className="mt-2 flex items-center gap-1.5 text-[11px] text-emerald-400/70">
        <CheckCircle className="h-3 w-3" />
        No similar requirements found
      </div>
    );
  }

  if (results.length === 0) return null;

  return (
    <div className={`mt-3 rounded-lg border p-3 ${
      isDuplicate
        ? 'border-amber-500/30 bg-amber-500/5'
        : 'border-blue-500/20 bg-blue-500/5'
    }`}>
      {/* Header */}
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isDuplicate ? (
            <AlertTriangle className="h-4 w-4 text-amber-400" />
          ) : (
            <Sparkles className="h-4 w-4 text-blue-400" />
          )}
          <span className="text-xs font-semibold text-slate-200">
            {isDuplicate
              ? 'Potential Duplicate Detected'
              : 'Similar Existing Requirements'}
          </span>
          <span className="rounded-full bg-slate-700/50 px-2 py-0.5 text-[10px] text-slate-400">
            {results.length} found
          </span>
        </div>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="rounded p-1 text-slate-500 transition hover:bg-slate-700/50 hover:text-slate-300"
          aria-label="Dismiss suggestions"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Results */}
      <div className="space-y-2">
        {results.map((sim) => (
          <div
            key={sim.requirement_id}
            className="rounded-md border border-slate-700/50 bg-slate-800/30 p-2.5"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[11px] font-semibold text-blue-400">
                    {sim.req_id}
                  </span>
                  <SimilarityBadge score={sim.similarity_score} />
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-slate-400">
                  {sim.statement}
                </p>
                {sim.explanation && (
                  <p className="mt-1 text-[10px] italic text-slate-500">
                    {sim.explanation}
                  </p>
                )}
              </div>
              {onLinkToExisting && (
                <button
                  type="button"
                  onClick={() => onLinkToExisting(sim.requirement_id)}
                  className="flex shrink-0 items-center gap-1 rounded-md border border-blue-500/30 bg-blue-500/10 px-2 py-1 text-[10px] font-semibold text-blue-400 transition hover:bg-blue-500/20"
                >
                  <Link2 className="h-3 w-3" />
                  Link
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Actions */}
      <div className="mt-2 flex items-center gap-3 border-t border-slate-700/30 pt-2">
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="text-[10px] font-medium text-slate-400 transition hover:text-slate-200"
        >
          This is not a duplicate — continue creating
        </button>
      </div>

      {error && (
        <div className="mt-1 text-[10px] text-red-400">{error}</div>
      )}
    </div>
  );
}


function SimilarityBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color =
    pct >= 95 ? 'text-red-400 bg-red-500/15 border-red-500/30'
    : pct >= 85 ? 'text-amber-400 bg-amber-500/15 border-amber-500/30'
    : 'text-blue-400 bg-blue-500/15 border-blue-500/30';

  return (
    <span className={`rounded-full border px-1.5 py-0 text-[9px] font-bold ${color}`}>
      {pct}% match
    </span>
  );
}
