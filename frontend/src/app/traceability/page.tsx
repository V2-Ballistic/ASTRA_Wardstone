'use client';

/**
 * ASTRA — Legacy Traceability Redirect
 * =======================================
 * File: frontend/src/app/traceability/page.tsx
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2, AlertTriangle } from 'lucide-react';
import { projectsAPI } from '@/lib/api';

export default function TraceabilityRedirectPage() {
  const router = useRouter();
  const [error, setError] = useState('');

  useEffect(() => {
    projectsAPI.list()
      .then((res) => {
        const projects = res.data || [];
        if (projects.length > 0) {
          router.replace(`/projects/${projects[0].id}/traceability`);
        } else {
          setError('No projects found. Create a project first.');
        }
      })
      .catch(() => {
        setError('Failed to load projects');
      });
  }, [router]);

  if (error) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4">
        <AlertTriangle className="h-8 w-8 text-amber-400" />
        <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 px-6 py-4 text-sm text-amber-400">
          {error}
        </div>
        <button
          onClick={() => router.push('/')}
          className="rounded-lg bg-blue-500 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-600"
        >
          Back to Projects
        </button>
      </div>
    );
  }

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3">
      <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
      <span className="text-sm text-slate-500">Redirecting to traceability…</span>
    </div>
  );
}
