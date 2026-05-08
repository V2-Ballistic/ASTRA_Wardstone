'use client';

/**
 * Phase 0 (CLAUDE_CODE_PROMPT_PHASE0 §Fix 0b Part 2)
 * ===================================================
 * Idle-timeout watchdog. After T-warn minutes of no activity, shows a
 * modal: "You'll be signed out in 5 minutes due to inactivity. Stay
 * signed in?" After T-timeout minutes (no warning click), force logout.
 *
 * Activity sources:
 *   - mousedown / keydown
 *   - successful API call (custom 'astra:api-call' event from
 *     auth-refresh.ts)
 *
 * TTL is read from env vars (NEXT_PUBLIC_SESSION_WARN_MIN /
 * _SESSION_TIMEOUT_MIN). Defaults: 25 / 30.
 */

import { useEffect, useRef, useState } from 'react';
import { Clock, ShieldCheck } from 'lucide-react';

import { explicitLogout, explicitRefresh } from '@/lib/auth-refresh';

const ACTIVITY_EVENTS = ['mousedown', 'keydown'] as const;
const API_CALL_EVENT = 'astra:api-call';

function parseMinutes(raw: string | undefined, fallback: number): number {
  if (!raw) return fallback;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

export default function SessionMonitor() {
  const [warningOpen, setWarningOpen] = useState(false);
  const [staying, setStaying] = useState(false);
  const lastActivityRef = useRef<number>(Date.now());
  const tickerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const warnMin = parseMinutes(process.env.NEXT_PUBLIC_SESSION_WARN_MIN, 25);
  const timeoutMin = parseMinutes(process.env.NEXT_PUBLIC_SESSION_TIMEOUT_MIN, 30);
  const warnMs = warnMin * 60 * 1000;
  const timeoutMs = timeoutMin * 60 * 1000;

  useEffect(() => {
    const onActivity = () => {
      lastActivityRef.current = Date.now();
      if (warningOpen) setWarningOpen(false);
    };

    ACTIVITY_EVENTS.forEach((ev) => window.addEventListener(ev, onActivity, { passive: true }));
    window.addEventListener(API_CALL_EVENT, onActivity);

    tickerRef.current = setInterval(() => {
      const idle = Date.now() - lastActivityRef.current;
      if (idle >= timeoutMs) {
        // Force logout; redirects to /login.
        explicitLogout().finally(() => {
          window.location.href = '/login';
        });
        return;
      }
      if (idle >= warnMs && !warningOpen) {
        setWarningOpen(true);
      }
    }, 30 * 1000); // every 30s — fast enough for a 5-minute warning window

    return () => {
      ACTIVITY_EVENTS.forEach((ev) => window.removeEventListener(ev, onActivity));
      window.removeEventListener(API_CALL_EVENT, onActivity);
      if (tickerRef.current) clearInterval(tickerRef.current);
    };
  }, [warnMs, timeoutMs, warningOpen]);

  if (!warningOpen) return null;

  const onStaySignedIn = async () => {
    setStaying(true);
    try {
      await explicitRefresh();
      lastActivityRef.current = Date.now();
      setWarningOpen(false);
    } catch {
      // Refresh failed — fall through to logout.
      await explicitLogout();
      window.location.href = '/login';
    } finally {
      setStaying(false);
    }
  };

  const minutesLeft = Math.max(1, Math.round((timeoutMs - (Date.now() - lastActivityRef.current)) / 60000));

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="session-warning-title"
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 backdrop-blur-sm"
    >
      <div className="rounded-xl border border-astra-border bg-astra-surface p-6 max-w-md mx-4 shadow-2xl">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-amber-500/15 p-2">
            <Clock className="h-5 w-5 text-amber-400" aria-hidden="true" />
          </div>
          <h2 id="session-warning-title" className="text-base font-bold text-slate-100">
            Inactive session
          </h2>
        </div>
        <p className="mt-3 text-sm text-slate-300">
          You&apos;ll be signed out in about {minutesLeft} minute{minutesLeft === 1 ? '' : 's'} due to
          inactivity. Any unsaved form data will be preserved.
        </p>
        <div className="mt-5 flex justify-end">
          <button
            type="button"
            onClick={onStaySignedIn}
            disabled={staying}
            className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-blue-600 to-violet-600 px-4 py-2 text-xs font-semibold text-white hover:from-blue-500 hover:to-violet-500 disabled:opacity-50"
          >
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
            {staying ? 'Refreshing…' : 'Stay signed in'}
          </button>
        </div>
      </div>
    </div>
  );
}
