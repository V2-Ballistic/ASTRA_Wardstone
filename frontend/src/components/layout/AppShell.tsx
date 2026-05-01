'use client';

/**
 * ASTRA — App Shell (WCAG 2.1 AA)
 * ==================================
 * File: frontend/src/components/layout/AppShell.tsx
 *
 * Updated for project-scoped navigation:
 *   - Sidebar handles its own global/project mode switching
 *   - Main content area adjusts for sidebar width
 *   - Login page gets proper landmark structure
 *   - LiveRegionProvider wraps entire app for screen reader announcements
 */

import { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { AuthProvider, useAuth } from '@/lib/auth';
import { LiveRegionProvider } from '@/components/a11y/LiveRegion';
import Sidebar from './Sidebar';
import { Loader2 } from 'lucide-react';

function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  // F-101: when unauthenticated, REDIRECT to /login with the current
  // path captured in `next` rather than rendering <LoginPage /> in
  // place. The pre-fix in-place render meant:
  //   - the URL stayed at the protected route,
  //   - hard-reload of /projects/1 lost context,
  //   - back-button history was corrupted by the LoginPage render.
  // The login flow honours `?next=` and pushes there on success.
  useEffect(() => {
    if (loading) return;
    if (!user && pathname !== '/login') {
      const next = pathname && pathname !== '/' ? `?next=${encodeURIComponent(pathname)}` : '';
      router.replace(`/login${next}`);
    }
  }, [loading, user, pathname, router]);

  // ── Loading state ──
  if (loading) {
    return (
      <div
        className="flex min-h-screen items-center justify-center bg-astra-bg"
        role="status"
        aria-label="Loading application"
      >
        <div className="flex flex-col items-center gap-3">
          <div
            className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-violet-500 text-lg font-extrabold text-white"
            aria-hidden="true"
          >
            A
          </div>
          <Loader2 className="h-5 w-5 animate-spin text-blue-500" aria-hidden="true" />
          <span className="sr-only">Loading ASTRA…</span>
        </div>
      </div>
    );
  }

  // ── Not authenticated and not on /login: render nothing (redirect
  // is in-flight from the effect above). The /login route itself is
  // a top-level page rendered outside AppShell's gate, so user-on-
  // login won't recurse.
  if (!user && pathname !== '/login') {
    return null;
  }

  // ── On /login (authenticated or not), render children directly
  // — no Sidebar wrapper.
  if (pathname === '/login') {
    return <>{children}</>;
  }

  // ── Authenticated ──
  return (
    <>
      <Sidebar />
      <main
        id="main-content"
        role="main"
        className="ml-60 min-h-screen p-6 lg:p-8"
        tabIndex={-1}
      >
        {children}
      </main>
    </>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <LiveRegionProvider>
        <AuthGate>{children}</AuthGate>
      </LiveRegionProvider>
    </AuthProvider>
  );
}
