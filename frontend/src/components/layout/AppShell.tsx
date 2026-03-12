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

import { usePathname } from 'next/navigation';
import { AuthProvider, useAuth } from '@/lib/auth';
import { LiveRegionProvider } from '@/components/a11y/LiveRegion';
import Sidebar from './Sidebar';
import LoginPage from '@/app/login/page';
import { Loader2 } from 'lucide-react';

function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

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

  // ── Not authenticated ──
  if (!user) {
    return (
      <div className="min-h-screen bg-astra-bg">
        <LoginPage />
      </div>
    );
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
