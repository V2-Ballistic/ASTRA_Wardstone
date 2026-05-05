'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { partsLibraryAPI } from '@/lib/parts-api';
import type { PendingPartsImportResponse } from '@/lib/parts-types';

export default function PendingImportsListPage() {
  const [imports, setImports] = useState<PendingPartsImportResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    partsLibraryAPI
      .listPendingImports()
      .then((res) => {
        setImports(res.data);
        setError(null);
      })
      .catch((err) => {
        setError(err?.response?.data?.detail || 'Failed to load pending imports');
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="container mx-auto p-6">
      <div className="mb-6">
        <Link href="/parts-library" className="text-xs text-blue-600 hover:underline">
          ← Parts Library
        </Link>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mt-2">
          Pending STEP Imports
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          STEP files awaiting review and approval
        </p>
      </div>

      {loading && <div className="text-sm text-gray-500">Loading…</div>}
      {error && (
        <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded text-sm text-red-700">
          {error}
        </div>
      )}

      {!loading && !error && imports.length === 0 && (
        <div className="p-8 text-center text-gray-500 border border-dashed border-gray-300 dark:border-gray-700 rounded">
          No pending imports.
        </div>
      )}

      {!loading && imports.length > 0 && (
        <div className="overflow-auto rounded border border-gray-200 dark:border-gray-700">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800/50 text-xs uppercase text-gray-500">
              <tr>
                <th className="px-3 py-2 text-left">ID</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-left">Proposed Name</th>
                <th className="px-3 py-2 text-left">Type</th>
                <th className="px-3 py-2 text-left">Low-confidence fields</th>
                <th className="px-3 py-2 text-left">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {imports.map((p) => (
                <tr
                  key={p.id}
                  className="hover:bg-gray-50 dark:hover:bg-gray-800/50 text-gray-900 dark:text-gray-100"
                >
                  <td className="px-3 py-2 font-mono text-xs">{p.id}</td>
                  <td className="px-3 py-2">{p.status}</td>
                  <td className="px-3 py-2">{(p.proposed_data?.name as string) || '—'}</td>
                  <td className="px-3 py-2">{(p.proposed_data?.part_type as string) || '—'}</td>
                  <td className="px-3 py-2 text-xs">
                    {p.low_confidence_fields?.length || 0}
                  </td>
                  <td className="px-3 py-2 text-xs">
                    {new Date(p.created_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-2">
                    <Link
                      href={`/parts-library/pending-imports/${p.id}`}
                      className="text-xs text-blue-600 hover:underline"
                    >
                      Review →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
