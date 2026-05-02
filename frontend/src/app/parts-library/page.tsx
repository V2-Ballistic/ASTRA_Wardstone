'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { partsLibraryAPI } from '@/lib/parts-api';
import type {
  LibraryPartSummary, MaterialClass, PartStatus, PartType,
} from '@/lib/parts-types';
import {
  PART_STATUS_COLORS, PART_TYPE_COLORS, PART_TYPE_LABELS,
} from '@/lib/parts-types';
import { StepUploadModal } from '@/components/parts/StepUploadModal';

export default function PartsLibraryPage() {
  const router = useRouter();
  const [parts, setParts] = useState<LibraryPartSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [partType, setPartType] = useState<PartType | ''>('');
  const [status, setStatus] = useState<PartStatus | ''>('approved');
  const [materialClass, setMaterialClass] = useState<MaterialClass | ''>('');
  const [uploadOpen, setUploadOpen] = useState(false);

  // Debounce search input (300 ms)
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    partsLibraryAPI
      .list({
        part_type: partType || undefined,
        status: status || undefined,
        material_class: materialClass || undefined,
        search: debouncedSearch.length >= 2 ? debouncedSearch : undefined,
        limit: 200,
      })
      .then((res) => {
        if (cancelled) return;
        setParts(res.data);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.response?.data?.detail || 'Failed to load parts');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [partType, status, materialClass, debouncedSearch]);

  const onUploadSuccess = (pendingImportId: number) => {
    setUploadOpen(false);
    router.push(`/parts-library/pending-imports/${pendingImportId}`);
  };

  const onDuplicateExisting = (partId: number) => {
    setUploadOpen(false);
    router.push(`/parts-library/${partId}`);
  };

  return (
    <div className="container mx-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Parts Library
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Global cross-project parts database
          </p>
        </div>
        <div className="flex gap-2">
          <Link
            href="/parts-library/pending-imports"
            className="px-3 py-1.5 text-sm rounded border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            Pending Imports
          </Link>
          <button
            onClick={() => setUploadOpen(true)}
            className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Upload STEP File
          </button>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap gap-2 items-center">
        <input
          type="text"
          placeholder="Search WPN, name, MPN, manufacturer..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-64 px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
        />
        <select
          value={partType}
          onChange={(e) => setPartType((e.target.value as PartType) || '')}
          className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
        >
          <option value="">All types</option>
          {Object.entries(PART_TYPE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <select
          value={status}
          onChange={(e) => setStatus((e.target.value as PartStatus) || '')}
          className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
        >
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="under_review">Under Review</option>
          <option value="approved">Approved</option>
          <option value="superseded">Superseded</option>
          <option value="obsolete">Obsolete</option>
        </select>
        <select
          value={materialClass}
          onChange={(e) =>
            setMaterialClass((e.target.value as MaterialClass) || '')
          }
          className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
        >
          <option value="">Any material</option>
          <option value="aluminum">Aluminum</option>
          <option value="titanium">Titanium</option>
          <option value="steel">Steel</option>
          <option value="stainless_steel">Stainless Steel</option>
          <option value="nickel_alloy">Nickel Alloy</option>
          <option value="polymer">Polymer</option>
          <option value="composite">Composite</option>
          <option value="ceramic">Ceramic</option>
          <option value="other">Other</option>
        </select>
      </div>

      {loading && (
        <div className="text-sm text-gray-500 dark:text-gray-400 p-4">
          Loading parts...
        </div>
      )}

      {error && !loading && (
        <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded">
          <p className="text-sm text-red-800 dark:text-red-200">{error}</p>
        </div>
      )}

      {!loading && !error && parts.length === 0 && (
        <div className="p-8 text-center text-gray-500 dark:text-gray-400 border border-dashed border-gray-300 dark:border-gray-700 rounded">
          {debouncedSearch || partType || materialClass
            ? 'No parts match your filters.'
            : 'No parts in the library. Upload a STEP file to get started.'}
        </div>
      )}

      {!loading && !error && parts.length > 0 && (
        <div className="overflow-auto rounded border border-gray-200 dark:border-gray-700">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800/50">
              <tr className="text-left text-xs uppercase text-gray-500 dark:text-gray-400">
                <th className="px-3 py-2">WPN</th>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Material</th>
                <th className="px-3 py-2">Manufacturer</th>
                <th className="px-3 py-2">MPN</th>
                <th className="px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {parts.map((p) => (
                <tr
                  key={p.id}
                  onClick={() => router.push(`/parts-library/${p.id}`)}
                  className="cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 text-gray-900 dark:text-gray-100"
                >
                  <td className="px-3 py-2 font-mono text-xs">
                    {p.wardstone_part_number}
                  </td>
                  <td className="px-3 py-2 font-medium">{p.name}</td>
                  <td className="px-3 py-2">
                    <span className={`text-xs px-2 py-0.5 rounded ${PART_TYPE_COLORS[p.part_type]}`}>
                      {PART_TYPE_LABELS[p.part_type]}
                    </span>
                  </td>
                  <td className="px-3 py-2">{p.material_name || '—'}</td>
                  <td className="px-3 py-2">{p.manufacturer_name || '—'}</td>
                  <td className="px-3 py-2 font-mono text-xs">
                    {p.manufacturer_part_number || '—'}
                  </td>
                  <td className="px-3 py-2">
                    <span className={`text-xs px-2 py-0.5 rounded ${PART_STATUS_COLORS[p.status]}`}>
                      {p.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <StepUploadModal
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onSuccess={onUploadSuccess}
        onDuplicateExistingPart={onDuplicateExisting}
      />
    </div>
  );
}
