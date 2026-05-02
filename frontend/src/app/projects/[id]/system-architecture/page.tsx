'use client';
import Link from 'next/link';
import { useParams } from 'next/navigation';

/**
 * ASTRA-SPEC-PARTS-001 §5.6 — System Architecture tab.
 *
 * Phase 3 placeholder: full force-graph overview (Systems, Parts,
 * Electrical Interfaces, Mechanical Joints) is deferred per
 * PARTS_BUILD_LOG.md. This page exists so the new sidebar nav entry
 * resolves and points users to the existing Systems and Unit views.
 */
export default function SystemArchitecturePage() {
  const params = useParams();
  const id = params?.id as string;
  return (
    <div className="container mx-auto p-6">
      <h1 className="text-xl font-bold tracking-tight text-slate-200 mb-2">
        System Architecture
      </h1>
      <p className="text-sm text-slate-500 mb-6">
        Cross-cutting view of systems, parts, and interfaces.
      </p>

      <div className="rounded-xl border border-dashed border-astra-border bg-astra-surface p-8 text-center">
        <p className="text-sm text-slate-400 mb-2">
          The combined force-graph overview is on the roadmap.
        </p>
        <p className="text-xs text-slate-500 mb-4">
          In the meantime, manage Systems and Units in the existing tabs:
        </p>
        <div className="flex justify-center gap-2 text-xs">
          <Link
            href={`/projects/${id}/interfaces`}
            className="rounded-lg border border-astra-border px-3 py-1.5 text-slate-300 hover:bg-astra-surface-alt"
          >
            Electrical Interfaces (Systems / Units / Harnesses)
          </Link>
          <Link
            href={`/projects/${id}/parts`}
            className="rounded-lg border border-astra-border px-3 py-1.5 text-slate-300 hover:bg-astra-surface-alt"
          >
            Parts
          </Link>
          <Link
            href={`/projects/${id}/mechanical-interfaces`}
            className="rounded-lg border border-astra-border px-3 py-1.5 text-slate-300 hover:bg-astra-surface-alt"
          >
            Mechanical Interfaces
          </Link>
        </div>
      </div>
    </div>
  );
}
