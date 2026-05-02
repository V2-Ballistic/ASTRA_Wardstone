'use client';
import { useEffect, useState, use } from 'react';
import Link from 'next/link';
import { partsLibraryAPI, projectPartsAPI } from '@/lib/parts-api';
import type {
  LibraryPartSummary, PartType, ProjectPartResponse,
} from '@/lib/parts-types';
import {
  PART_TYPE_COLORS, PART_TYPE_LABELS,
} from '@/lib/parts-types';

export default function ProjectPartsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const projectId = parseInt(id, 10);

  const [parts, setParts] = useState<ProjectPartResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);

  const reload = () => {
    setLoading(true);
    projectPartsAPI
      .list(projectId)
      .then((res) => setParts(res.data))
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (Number.isNaN(projectId)) return;
    reload();
  }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  const onRemove = async (pp: ProjectPartResponse) => {
    if (!confirm(`Remove ${pp.library_part.name} from this project?`)) return;
    try {
      await projectPartsAPI.remove(projectId, pp.id);
      reload();
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: { detail?: string } | string } } };
      const detail = ax?.response?.data?.detail;
      const message = typeof detail === 'string'
        ? detail
        : (detail as { detail?: string })?.detail || 'Remove failed';
      alert(message);
    }
  };

  return (
    <div className="container mx-auto p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Parts</h1>
          <p className="text-sm text-gray-500">
            Library parts associated with this project
          </p>
        </div>
        <button
          onClick={() => setPickerOpen(true)}
          className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          Add Part from Library
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 rounded text-sm text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-sm text-gray-500">Loading…</div>
      ) : parts.length === 0 ? (
        <div className="p-8 text-center text-gray-500 border border-dashed border-gray-300 dark:border-gray-700 rounded">
          No parts in this project. Add some from the library.
        </div>
      ) : (
        <div className="overflow-auto rounded border border-gray-200 dark:border-gray-700">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800/50 text-xs uppercase text-gray-500">
              <tr>
                <th className="px-3 py-2 text-left">Designation</th>
                <th className="px-3 py-2 text-left">WPN</th>
                <th className="px-3 py-2 text-left">Name</th>
                <th className="px-3 py-2 text-left">Type</th>
                <th className="px-3 py-2 text-left">Material</th>
                <th className="px-3 py-2 text-left">Qty</th>
                <th className="px-3 py-2 text-left">System</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {parts.map((pp) => (
                <tr
                  key={pp.id}
                  className={
                    `text-gray-900 dark:text-gray-100 ` +
                    (pp.system_id == null ? 'border-l-4 border-amber-400' : '')
                  }
                >
                  <td className="px-3 py-2">{pp.designation || '—'}</td>
                  <td className="px-3 py-2 font-mono text-xs">
                    <Link
                      href={`/parts-library/${pp.library_part_id}`}
                      className="text-blue-600 hover:underline"
                    >
                      {pp.library_part.wardstone_part_number}
                    </Link>
                  </td>
                  <td className="px-3 py-2 font-medium">{pp.library_part.name}</td>
                  <td className="px-3 py-2">
                    <span className={`text-xs px-2 py-0.5 rounded ${PART_TYPE_COLORS[pp.library_part.part_type]}`}>
                      {PART_TYPE_LABELS[pp.library_part.part_type]}
                    </span>
                  </td>
                  <td className="px-3 py-2">{pp.library_part.material_name || '—'}</td>
                  <td className="px-3 py-2">{pp.quantity}</td>
                  <td className="px-3 py-2">
                    {pp.system_id ? (
                      <span className="text-xs">System #{pp.system_id}</span>
                    ) : (
                      <span className="text-xs text-amber-700">Unassigned</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={() => onRemove(pp)}
                      className="text-xs text-red-600 hover:underline"
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pickerOpen && (
        <LibraryPartPickerModal
          projectId={projectId}
          existingPartIds={new Set(parts.map((p) => p.library_part_id))}
          onClose={() => setPickerOpen(false)}
          onAdded={() => {
            setPickerOpen(false);
            reload();
          }}
        />
      )}
    </div>
  );
}

// ── Picker modal ──────────────────────────────────────────────

function LibraryPartPickerModal({
  projectId,
  existingPartIds,
  onClose,
  onAdded,
}: {
  projectId: number;
  existingPartIds: Set<number>;
  onClose: () => void;
  onAdded: () => void;
}) {
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [partType, setPartType] = useState<PartType | ''>('');
  const [results, setResults] = useState<LibraryPartSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<LibraryPartSummary | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [designation, setDesignation] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 250);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    setLoading(true);
    partsLibraryAPI
      .list({
        status: 'approved',
        part_type: partType || undefined,
        search: debouncedSearch.length >= 2 ? debouncedSearch : undefined,
        limit: 50,
      })
      .then((res) => setResults(res.data))
      .finally(() => setLoading(false));
  }, [partType, debouncedSearch]);

  const onAdd = async () => {
    if (!selected) return;
    setSubmitting(true);
    try {
      await projectPartsAPI.add(projectId, {
        library_part_id: selected.id,
        quantity,
        designation: designation.trim() || undefined,
      });
      onAdded();
    } catch (e: unknown) {
      const ax = e as { response?: { data?: { detail?: { detail?: string } | string } } };
      const detail = ax?.response?.data?.detail;
      const message = typeof detail === 'string'
        ? detail
        : (detail as { detail?: string })?.detail || 'Add failed';
      setErr(message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-3xl mx-4 p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Add Part from Library
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700">✕</button>
        </div>

        <div className="flex gap-2 mb-3">
          <input
            type="text"
            placeholder="Search WPN, name, MPN..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
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
        </div>

        <div className="border border-gray-200 dark:border-gray-700 rounded max-h-72 overflow-auto">
          {loading ? (
            <div className="p-3 text-sm text-gray-500">Loading…</div>
          ) : results.length === 0 ? (
            <div className="p-3 text-sm text-gray-500">No matches.</div>
          ) : (
            <ul className="divide-y divide-gray-200 dark:divide-gray-700">
              {results.map((p) => {
                const already = existingPartIds.has(p.id);
                return (
                  <li
                    key={p.id}
                    onClick={() => !already && setSelected(p)}
                    className={
                      `p-2 flex items-center gap-2 cursor-pointer ` +
                      (selected?.id === p.id
                        ? 'bg-blue-50 dark:bg-blue-900/20 border-l-4 border-blue-500'
                        : 'hover:bg-gray-50 dark:hover:bg-gray-800/50') +
                      (already ? ' opacity-40 cursor-not-allowed' : '')
                    }
                  >
                    <span className="font-mono text-xs text-gray-500">
                      {p.wardstone_part_number}
                    </span>
                    <span className="font-medium text-sm text-gray-900 dark:text-gray-100 flex-1">
                      {p.name}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded ${PART_TYPE_COLORS[p.part_type]}`}>
                      {PART_TYPE_LABELS[p.part_type]}
                    </span>
                    {already && <span className="text-xs text-gray-500">(in project)</span>}
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {selected && (
          <div className="mt-4 grid grid-cols-3 gap-2 items-end">
            <label className="text-xs text-gray-500">
              Quantity
              <input
                type="number"
                min={1}
                value={quantity}
                onChange={(e) => setQuantity(Math.max(1, parseInt(e.target.value, 10) || 1))}
                className="w-full mt-1 px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
              />
            </label>
            <label className="col-span-2 text-xs text-gray-500">
              Designation (optional)
              <input
                type="text"
                value={designation}
                onChange={(e) => setDesignation(e.target.value)}
                placeholder="e.g. HW-J1"
                className="w-full mt-1 px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
              />
            </label>
          </div>
        )}

        {err && (
          <div className="mt-3 p-2 bg-red-50 dark:bg-red-900/20 rounded text-sm text-red-700">
            {err}
          </div>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm rounded border border-gray-300 dark:border-gray-600"
          >
            Cancel
          </button>
          <button
            onClick={onAdd}
            disabled={!selected || submitting}
            className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded disabled:opacity-50"
          >
            {submitting ? 'Adding…' : 'Add to Project'}
          </button>
        </div>
      </div>
    </div>
  );
}
