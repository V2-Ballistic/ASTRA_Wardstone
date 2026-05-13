'use client';

/**
 * ASTRA — Catalog Pending Imports (list page)
 * ============================================
 * File: frontend/src/app/catalog/pending-imports/page.tsx
 *
 * CLEANUP-002 Phase 3: this list page exists at /catalog/pending-imports
 * so the parts-library/pending-imports → catalog/pending-imports 308
 * redirect lands somewhere real. Phase 0 found that /catalog only
 * had /pending-imports/[id]/page.tsx — no list. Ported minimally
 * from the legacy parts-library list, but reads the catalog API
 * (PendingCatalogImport rows) instead of the legacy parts-library API.
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, Loader2 } from 'lucide-react';

import { catalogAPI } from '@/lib/catalog-api';
import { formatApiError } from '@/lib/errors';
import {
  type PendingCatalogImport,
  PENDING_IMPORT_STATUS_LABELS,
} from '@/lib/catalog-types';

export default function CatalogPendingImportsListPage() {
  const [imports, setImports] = useState<PendingCatalogImport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    catalogAPI
      .listPendingImports()
      .then((res) => {
        setImports(res.data);
        setError(null);
      })
      .catch((err) => {
        setError(formatApiError(err, 'Failed to load pending imports'));
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="container mx-auto p-6">
      <div className="mb-6">
        <Link href="/catalog" className="text-xs text-blue-400 hover:underline">
          ← Catalog
        </Link>
        <h1 className="mt-2 text-2xl font-bold text-slate-100">
          Pending STEP Imports
        </h1>
        <p className="text-sm text-slate-500">
          STEP files awaiting review and approval.
        </p>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 rounded border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-400">
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" /> {error}
        </div>
      )}

      {!loading && !error && imports.length === 0 && (
        <div className="rounded border border-dashed border-astra-border p-8 text-center text-sm text-slate-500">
          No pending imports.
        </div>
      )}

      {!loading && imports.length > 0 && (
        <div className="overflow-auto rounded border border-astra-border">
          <table className="w-full text-sm">
            <thead className="bg-astra-surface text-xs uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-3 py-2 text-left">ID</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-left">Proposed name</th>
                <th className="px-3 py-2 text-left">Part number</th>
                <th className="px-3 py-2 text-left">Created</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-astra-border">
              {imports.map((p) => {
                const data = p.extracted_data ?? {};
                const proposedName = (data.name as string) || '—';
                const partNumber = (data.part_number as string) || '—';
                return (
                  <tr key={p.id} className="text-slate-200 hover:bg-astra-surface/60">
                    <td className="px-3 py-2 font-mono text-xs">{p.id}</td>
                    <td className="px-3 py-2 text-xs">
                      {PENDING_IMPORT_STATUS_LABELS[p.status] ?? p.status}
                    </td>
                    <td className="px-3 py-2">{proposedName}</td>
                    <td className="px-3 py-2 font-mono text-xs">{partNumber}</td>
                    <td className="px-3 py-2 text-xs">
                      {new Date(p.created_at).toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <Link
                        href={`/catalog/pending-imports/${p.id}`}
                        className="text-xs text-blue-400 hover:underline"
                      >
                        Review →
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
