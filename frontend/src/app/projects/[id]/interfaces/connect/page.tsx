'use client';

/**
 * ASTRA — Connection Builder Page (INTF-002 Phase 4 — spec §16)
 * ===============================================================
 * File: frontend/src/app/projects/[id]/interfaces/connect/page.tsx
 *
 * Hosts the <ConnectionBuilder> wizard for the current project. Reads
 * `?source=<unitId>&target=<unitId>` query string for pre-pick, and on a
 * successful commit navigates back to the parent interfaces page with a
 * toast hint via the URL.
 */

import { useEffect } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { ArrowLeft, Cable } from 'lucide-react';

import ConnectionBuilder from '@/components/connection-builder/ConnectionBuilder';

export default function ConnectPage() {
  const params = useParams();
  const router = useRouter();
  const search = useSearchParams();

  const projectId = Number(params?.id);
  const sourceQ = Number(search?.get('source')) || undefined;
  const targetQ = Number(search?.get('target')) || undefined;

  useEffect(() => {
    if (Number.isNaN(projectId)) {
      router.replace('/projects');
    }
  }, [projectId, router]);

  function back() {
    router.push(`/projects/${projectId}/interfaces`);
  }

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-6">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={back}
          className="inline-flex items-center gap-1 rounded border border-astra-border px-2 py-1 text-xs text-slate-300 hover:bg-astra-bg-3"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back
        </button>
        <h1 className="flex items-center gap-2 text-lg font-semibold text-slate-100">
          <Cable className="h-5 w-5 text-blue-400" />
          Connection Builder
        </h1>
      </div>

      <p className="text-xs text-slate-400">
        Wire two units together using the three-way auto-validated suggestion
        engine. Source / target name match · pin direction compatibility · LRU
        endpoint validation. Direction conflicts and ambiguous matches are
        surfaced so you can resolve them before committing the harness.
      </p>

      <ConnectionBuilder
        projectId={projectId}
        initialSourceUnitId={sourceQ}
        initialTargetUnitId={targetQ}
        onCommitted={(harnessId) => {
          router.push(
            `/projects/${projectId}/interfaces/harness/${harnessId}?committed=1`,
          );
        }}
        onCancel={back}
      />
    </div>
  );
}
