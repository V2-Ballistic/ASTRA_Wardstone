'use client';

import { usePathname } from 'next/navigation';
import { AuthProvider, useAuth } from '@/lib/auth';
import Sidebar from './Sidebar';
import LoginPage from '@/app/login/page';
import { Loader2 } from 'lucide-react';

function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  // Show loading spinner while checking auth
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-astra-bg">
        <div className="flex flex-col items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-violet-500 text-lg font-extrabold text-white">
            A
          </div>
          <Loader2 className="h-5 w-5 animate-spin text-blue-500" />
        </div>
      </div>
    );
  }

  // Not logged in — show ONLY the login page, no sidebar
  if (!user) {
    return (
      <div className="min-h-screen bg-astra-bg">
        <LoginPage />
      </div>
    );
  }

  // Logged in — show sidebar + content
  return (
    <>
      <Sidebar />
      <main className="ml-60 min-h-screen p-6 lg:p-8">{children}</main>
    </>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <AuthGate>{children}</AuthGate>
    </AuthProvider>
  );
}
