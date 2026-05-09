'use client';

/**
 * ASTRA — SystemArchGraph (TDD-SYSARCH-002 Phase 5)
 * ===================================================
 * Phase 4 ships a structural placeholder so the System Architecture
 * page compiles end-to-end. Phase 5 replaces this body with the
 * pure-TypeScript force-directed cluster graph (systems as
 * rounded-rect containers, units as circles, pan/zoom/click).
 */

import { useEffect, useState } from 'react';
import { Loader2, Network, Plus } from 'lucide-react';

import { sysarchAPI } from '@/lib/sysarch-api';
import type { SystemArchGraphResponse } from '@/lib/sysarch-types';


export interface SystemArchGraphProps {
  projectId: number;
  /** Phase 4 hands a callback that switches the page tab to Systems
   *  so the empty-state CTA flows the user toward AddSystemModal. */
  onAddSystem: () => void;
}


export default function SystemArchGraph({ projectId, onAddSystem }: SystemArchGraphProps) {
  const [graph, setGraph] = useState<SystemArchGraphResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    sysarchAPI.getGraph(projectId)
      .then((r) => { if (!cancelled) setGraph(r.data); })
      .catch((e) => {
        if (cancelled) return;
        const detail = e?.response?.data?.detail || e?.message || 'Failed to load graph';
        setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [projectId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-5 w-5 animate-spin text-blue-500" aria-label="Loading graph" />
      </div>
    );
  }

  if (error) {
    return (
      <div role="alert" className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
        {error}
      </div>
    );
  }

  if (!graph || graph.systems.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-astra-border bg-astra-surface px-6 py-16 text-center">
        <Network className="mx-auto mb-3 h-10 w-10 text-slate-600" aria-hidden="true" />
        <p className="mb-2 text-sm text-slate-300">
          Define your first system to start building the architecture.
        </p>
        <p className="mb-5 text-xs text-slate-500">
          Systems become container nodes; the units inside each system render as
          circles, and Interface / WireHarness rows draw the connection edges.
        </p>
        <button
          type="button"
          onClick={onAddSystem}
          className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-br from-blue-500 to-violet-500 px-3 py-1.5 text-xs font-semibold text-white hover:shadow-lg"
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add System
        </button>
      </div>
    );
  }

  // Phase 4 placeholder — replaced by the SVG force simulation in Phase 5.
  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface px-6 py-12 text-center">
      <Network className="mx-auto mb-3 h-10 w-10 text-blue-400" aria-hidden="true" />
      <p className="text-sm text-slate-300">
        Architecture graph: {graph.systems.length} system{graph.systems.length === 1 ? '' : 's'},{' '}
        {graph.units.length} unit{graph.units.length === 1 ? '' : 's'},{' '}
        {graph.edges.length} edge{graph.edges.length === 1 ? '' : 's'}.
      </p>
      <p className="mt-2 text-xs text-slate-500">
        Force-directed cluster rendering ships in Phase 5.
      </p>
    </div>
  );
}
