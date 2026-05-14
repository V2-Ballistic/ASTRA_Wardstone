/**
 * Phase 0 (CLAUDE_CODE_PROMPT_PHASE0 §Fix 0b Part 3)
 * ===================================================
 * Debounced autosave of a form-state object to localStorage. Used to
 * recover unsaved work when the session times out, the user reloads,
 * or the browser crashes.
 *
 * Storage shape: { value: T, savedAt: number }
 * Key convention: `astra:autosave:<form-name>:<scope>`
 *
 * SSR-safe: every localStorage access is window-guarded.
 *
 * Scope creep guard — DO NOT use this hook in:
 *   - login forms
 *   - password-change forms
 *   - the auth/refresh flow
 */

import { useEffect, useMemo, useRef, useState } from 'react';

export interface AutosaveOptions {
  /** Debounce window before flushing state to localStorage. Default 1500 ms. */
  debounceMs?: number;
  /** Discard drafts older than this. Default 7 days. */
  ttlMs?: number;
  /** When true, skip writes (handy when you know the form is empty). */
  disabled?: boolean;
}

export interface AutosaveResult<T> {
  /** True when a non-expired draft was found at mount. */
  hasDraft: boolean;
  /** Milliseconds since the draft was saved, or null. */
  draftAge: number | null;
  /** Returns the stored value (without modifying state). null if no draft. */
  restoreDraft: () => T | null;
  /** Removes the draft. Always call this from your form's onSubmit success. */
  clearDraft: () => void;
}

const DEFAULT_DEBOUNCE_MS = 1500;
const DEFAULT_TTL_MS = 7 * 24 * 60 * 60 * 1000;

interface StoredEnvelope<T> {
  value: T;
  savedAt: number;
}

/** Best-effort empty check — empty string, empty array, empty object → "empty". */
function isEmptyShape(value: unknown): boolean {
  if (value == null) return true;
  if (typeof value === 'string') return value.trim() === '';
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === 'object') {
    return Object.values(value as Record<string, unknown>).every(isEmptyShape);
  }
  return false;
}

function safeRead<T>(key: string): StoredEnvelope<T> | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredEnvelope<T>;
    if (typeof parsed.savedAt !== 'number') return null;
    return parsed;
  } catch {
    return null;
  }
}

function safeWrite<T>(key: string, env: StoredEnvelope<T>): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(key, JSON.stringify(env));
  } catch {
    // Quota exceeded / storage disabled — best-effort only.
  }
}

function safeRemove(key: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    // ignore
  }
}

export function useFormAutosave<T extends object>(
  storageKey: string,
  state: T,
  options: AutosaveOptions = {},
): AutosaveResult<T> {
  const debounceMs = options.debounceMs ?? DEFAULT_DEBOUNCE_MS;
  const ttlMs = options.ttlMs ?? DEFAULT_TTL_MS;
  const disabled = !!options.disabled;

  const [hasDraft, setHasDraft] = useState(false);
  const [draftAge, setDraftAge] = useState<number | null>(null);
  const cleared = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── On mount: check for an existing draft and TTL-expire it. ──
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const env = safeRead<T>(storageKey);
    if (!env) {
      setHasDraft(false);
      setDraftAge(null);
      return;
    }
    const age = Date.now() - env.savedAt;
    if (age > ttlMs) {
      safeRemove(storageKey);
      setHasDraft(false);
      setDraftAge(null);
      return;
    }
    setHasDraft(true);
    setDraftAge(age);
    // intentional: re-runs only on storageKey change
  }, [storageKey, ttlMs]);

  // ── Debounced write on every state change. ──
  useEffect(() => {
    if (disabled || cleared.current) return;
    if (typeof window === 'undefined') return;
    if (isEmptyShape(state)) return;

    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      safeWrite<T>(storageKey, { value: state, savedAt: Date.now() });
    }, debounceMs);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [state, storageKey, debounceMs, disabled]);

  return useMemo<AutosaveResult<T>>(() => ({
    hasDraft,
    draftAge,
    restoreDraft: () => {
      const env = safeRead<T>(storageKey);
      return env ? env.value : null;
    },
    clearDraft: () => {
      cleared.current = true;
      safeRemove(storageKey);
      setHasDraft(false);
      setDraftAge(null);
    },
  }), [hasDraft, draftAge, storageKey]);
}
