'use client';

/**
 * Phase 0 (CLAUDE_CODE_PROMPT_PHASE0 §Fix 0b Part 3)
 * ===================================================
 * Top-of-form banner that asks the user whether to restore an unsaved
 * draft picked up from localStorage by `useFormAutosave`.
 */

import { Clock } from 'lucide-react';

interface Props {
  ageMs: number;
  onRestore: () => void;
  onDiscard: () => void;
}

function formatAge(ms: number): string {
  if (ms < 60_000) return 'a few seconds';
  const minutes = Math.round(ms / 60_000);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'}`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'}`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? '' : 's'}`;
}

export default function RestorePromptBanner({ ageMs, onRestore, onDiscard }: Props) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3"
    >
      <div className="flex items-center gap-2 text-xs text-amber-200">
        <Clock className="h-4 w-4 text-amber-400" aria-hidden="true" />
        <span>
          Found unsaved changes from <strong>{formatAge(ageMs)}</strong> ago.
        </span>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onDiscard}
          className="text-[11px] font-semibold text-slate-400 hover:text-slate-200 px-2 py-1"
        >
          Discard
        </button>
        <button
          type="button"
          onClick={onRestore}
          className="rounded-lg bg-gradient-to-r from-blue-600 to-violet-600 px-3 py-1.5 text-[11px] font-semibold text-white hover:from-blue-500 hover:to-violet-500"
        >
          Restore
        </button>
      </div>
    </div>
  );
}
