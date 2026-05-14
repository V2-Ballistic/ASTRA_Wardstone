'use client';

/**
 * Next.js error boundary for the App Router. Catches any thrown
 * error during render or in a useEffect of a descendant route +
 * surfaces a real diagnostic message instead of the blank-screen
 * the previous "no boundary" state produced.
 *
 * Production mode in particular suppresses the dev-overlay so an
 * unhandled crash inside a page component would otherwise render an
 * empty <main> against the slate-950 layout background. The user-
 * visible symptom of that ("blank dark blue, nothing renders") was
 * the immediate motivator for adding this file.
 *
 * See https://nextjs.org/docs/app/building-your-application/routing/error-handling
 */

import { useEffect } from 'react';

export default function GlobalRouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log to the browser console + (in prod) any error-tracking sink
    // hooked up later. Cheap insurance until a real Sentry / log
    // pipeline lands.
    // eslint-disable-next-line no-console
    console.error('[error.tsx] caught', error);
  }, [error]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center px-4">
      <div className="max-w-xl w-full rounded-xl border border-rose-500/30 bg-rose-950/30 p-6 shadow-xl">
        <h1 className="text-lg font-semibold text-rose-200">
          Something went wrong on this page.
        </h1>
        <p className="mt-2 text-sm text-slate-300">
          ASTRA caught a render-time error before it could be shown
          inline. The page can&apos;t recover automatically; reload or
          retry below. If this persists, copy the message and file a
          bug.
        </p>
        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950 p-3">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">
            Error
          </div>
          <code className="block text-xs text-rose-300 break-words">
            {error?.message || String(error)}
          </code>
          {error?.digest && (
            <>
              <div className="mt-3 text-[10px] uppercase tracking-wider text-slate-500 mb-1">
                Digest
              </div>
              <code className="block text-[11px] font-mono text-slate-400">
                {error.digest}
              </code>
            </>
          )}
        </div>
        <div className="mt-5 flex items-center gap-2">
          <button
            type="button"
            onClick={reset}
            className="px-3 py-1.5 rounded-md border border-cyan-500/40 bg-cyan-500/10 text-cyan-200 hover:bg-cyan-500/20 text-sm"
          >
            Try again
          </button>
          <button
            type="button"
            onClick={() => window.location.assign('/')}
            className="px-3 py-1.5 rounded-md border border-slate-700 text-slate-300 hover:border-slate-500 text-sm"
          >
            Home
          </button>
        </div>
      </div>
    </div>
  );
}
