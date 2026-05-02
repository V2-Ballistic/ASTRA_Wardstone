'use client';
import { useEffect, useState, use } from 'react';
import Link from 'next/link';
import {
  mechanicalJointsAPI, projectPartsAPI,
} from '@/lib/parts-api';
import type {
  JointStatus, JointType, MechanicalJointResponse,
  ProjectPartResponse,
} from '@/lib/parts-types';
import { JOINT_STATUS_COLORS, JOINT_TYPE_LABELS } from '@/lib/parts-types';

export default function MechanicalInterfacesPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const projectId = parseInt(id, 10);

  const [joints, setJoints] = useState<MechanicalJointResponse[]>([]);
  const [projectParts, setProjectParts] = useState<ProjectPartResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState<JointStatus | ''>('');
  const [typeFilter, setTypeFilter] = useState<JointType | ''>('');

  const reload = () => {
    setLoading(true);
    Promise.all([
      mechanicalJointsAPI.list(projectId, {
        status: statusFilter || undefined,
        joint_type: typeFilter || undefined,
        limit: 200,
      }),
      projectPartsAPI.list(projectId, { limit: 200 }),
    ])
      .then(([j, p]) => {
        setJoints(j.data);
        setProjectParts(p.data);
        setError(null);
      })
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (Number.isNaN(projectId)) return;
    reload();
  }, [projectId, statusFilter, typeFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  const onApprove = async (joint: MechanicalJointResponse) => {
    if (!confirm(`Approve joint ${joint.joint_id}? This will generate auto-requirements.`)) return;
    try {
      await mechanicalJointsAPI.approve(projectId, joint.joint_id);
      reload();
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: { detail?: string } | string } } };
      const detail = ax?.response?.data?.detail;
      const message = typeof detail === 'string'
        ? detail
        : (detail as { detail?: string })?.detail || 'Approve failed';
      alert(message);
    }
  };

  const onDelete = async (joint: MechanicalJointResponse) => {
    const isActive = joint.status === 'active';
    if (isActive && !confirm(
      `Joint ${joint.joint_id} is ACTIVE. Force-deleting it will mark linked auto-requirements for review. Continue?`,
    )) return;
    if (!isActive && !confirm(`Delete draft joint ${joint.joint_id}?`)) return;

    try {
      await mechanicalJointsAPI.delete(projectId, joint.joint_id, isActive);
      reload();
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: { detail?: string } | string } } };
      const detail = ax?.response?.data?.detail;
      const message = typeof detail === 'string'
        ? detail
        : (detail as { detail?: string })?.detail || 'Delete failed';
      alert(message);
    }
  };

  const partLabel = (ppId: number) => {
    const pp = projectParts.find((p) => p.id === ppId);
    if (!pp) return `#${ppId}`;
    return pp.designation || pp.library_part.name;
  };

  return (
    <div className="container mx-auto p-6">
      <div className="flex justify-between items-center mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Mechanical Interfaces
          </h1>
          <p className="text-sm text-gray-500">
            Joints between project parts (bolted, sealed, press-fit, etc.)
          </p>
        </div>
        <button
          onClick={() => setCreateOpen(true)}
          disabled={projectParts.length < 2}
          title={projectParts.length < 2 ? 'Need at least 2 project parts to create a joint' : ''}
          className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
        >
          Add Joint
        </button>
      </div>

      <div className="rounded-lg border border-dashed border-gray-300 dark:border-gray-600 p-6 text-center mb-4 text-sm text-gray-500">
        3D assembly view available after Phase 4. Upload an assembly STEP file
        to auto-detect mating joints (when pythonOCC is available).
      </div>

      <div className="flex gap-2 mb-4">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter((e.target.value as JointStatus) || '')}
          className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
        >
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="active">Active</option>
          <option value="superseded">Superseded</option>
        </select>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter((e.target.value as JointType) || '')}
          className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
        >
          <option value="">All types</option>
          {Object.entries(JOINT_TYPE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      </div>

      {error && (
        <div className="mb-3 p-3 bg-red-50 dark:bg-red-900/20 rounded text-sm text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-sm text-gray-500">Loading…</div>
      ) : joints.length === 0 ? (
        <div className="p-8 text-center text-gray-500 border border-dashed border-gray-300 dark:border-gray-700 rounded">
          No mechanical joints in this project yet.
        </div>
      ) : (
        <div className="overflow-auto rounded border border-gray-200 dark:border-gray-700">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800/50 text-xs uppercase text-gray-500">
              <tr>
                <th className="px-3 py-2 text-left">Joint ID</th>
                <th className="px-3 py-2 text-left">Type</th>
                <th className="px-3 py-2 text-left">Part A</th>
                <th className="px-3 py-2 text-left">Part B</th>
                <th className="px-3 py-2 text-left">Fastener</th>
                <th className="px-3 py-2 text-left">Count</th>
                <th className="px-3 py-2 text-left">Torque</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {joints.map((j) => (
                <tr key={j.id} className="text-gray-900 dark:text-gray-100">
                  <td className="px-3 py-2 font-mono text-xs">{j.joint_id}</td>
                  <td className="px-3 py-2">{JOINT_TYPE_LABELS[j.joint_type]}</td>
                  <td className="px-3 py-2">{partLabel(j.part_a_id)}</td>
                  <td className="px-3 py-2">{partLabel(j.part_b_id)}</td>
                  <td className="px-3 py-2">
                    {j.fastener_part ? (
                      <Link
                        href={`/parts-library/${j.fastener_part.id}`}
                        className="text-xs font-mono text-blue-600 hover:underline"
                      >
                        {j.fastener_part.wardstone_part_number}
                      </Link>
                    ) : '—'}
                  </td>
                  <td className="px-3 py-2">{j.fastener_count ?? '—'}</td>
                  <td className="px-3 py-2 text-xs">
                    {j.torque_nominal_nm ? `${j.torque_nominal_nm} N·m` : '—'}
                  </td>
                  <td className="px-3 py-2">
                    <span className={`text-xs px-2 py-0.5 rounded ${JOINT_STATUS_COLORS[j.status]}`}>
                      {j.status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right space-x-2">
                    {j.status === 'draft' && (
                      <button
                        onClick={() => onApprove(j)}
                        className="text-xs text-green-600 hover:underline"
                      >
                        Approve
                      </button>
                    )}
                    {j.status !== 'superseded' && (
                      <button
                        onClick={() => onDelete(j)}
                        className="text-xs text-red-600 hover:underline"
                      >
                        Delete
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {createOpen && (
        <CreateJointModal
          projectId={projectId}
          projectParts={projectParts}
          onClose={() => setCreateOpen(false)}
          onCreated={() => {
            setCreateOpen(false);
            reload();
          }}
        />
      )}
    </div>
  );
}

// ── Create Joint modal ────────────────────────────────────────

function CreateJointModal({
  projectId, projectParts, onClose, onCreated,
}: {
  projectId: number;
  projectParts: ProjectPartResponse[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [jointType, setJointType] = useState<JointType>('bolted');
  const [partAId, setPartAId] = useState<number | ''>('');
  const [partBId, setPartBId] = useState<number | ''>('');
  const [fastenerCount, setFastenerCount] = useState('');
  const [torqueNom, setTorqueNom] = useState('');
  const [torqueMin, setTorqueMin] = useState('');
  const [torqueMax, setTorqueMax] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    if (!partAId || !partBId || partAId === partBId) {
      setErr('Select two different parts.');
      return;
    }
    setSubmitting(true);
    try {
      await mechanicalJointsAPI.create(projectId, {
        joint_type: jointType,
        part_a_id: typeof partAId === 'number' ? partAId : parseInt(partAId, 10),
        part_b_id: typeof partBId === 'number' ? partBId : parseInt(partBId, 10),
        fastener_count: fastenerCount
          ? parseInt(fastenerCount, 10) || undefined
          : undefined,
        torque_nominal_nm: torqueNom || undefined,
        torque_min_nm: torqueMin || undefined,
        torque_max_nm: torqueMax || undefined,
      });
      onCreated();
    } catch (e: unknown) {
      const ax = e as { response?: { data?: { detail?: { detail?: string } | string } } };
      const detail = ax?.response?.data?.detail;
      const message = typeof detail === 'string'
        ? detail
        : (detail as { detail?: string })?.detail || 'Create failed';
      setErr(message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-lg mx-4 p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Create Mechanical Joint
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700">✕</button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-500">Joint type</label>
            <select
              value={jointType}
              onChange={(e) => setJointType(e.target.value as JointType)}
              className="w-full mt-1 px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
            >
              {Object.entries(JOINT_TYPE_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs text-gray-500">
              Part A
              <select
                value={partAId}
                onChange={(e) => setPartAId(e.target.value ? parseInt(e.target.value, 10) : '')}
                className="w-full mt-1 px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
              >
                <option value="">— select —</option>
                {projectParts.map((pp) => (
                  <option key={pp.id} value={pp.id}>
                    {pp.designation || pp.library_part.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-gray-500">
              Part B
              <select
                value={partBId}
                onChange={(e) => setPartBId(e.target.value ? parseInt(e.target.value, 10) : '')}
                className="w-full mt-1 px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
              >
                <option value="">— select —</option>
                {projectParts.map((pp) => (
                  <option key={pp.id} value={pp.id}>
                    {pp.designation || pp.library_part.name}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {jointType === 'bolted' && (
            <>
              <div className="grid grid-cols-2 gap-2">
                <label className="text-xs text-gray-500">
                  Fastener count
                  <input
                    type="number"
                    min={1}
                    value={fastenerCount}
                    onChange={(e) => setFastenerCount(e.target.value)}
                    className="w-full mt-1 px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
                  />
                </label>
                <label className="text-xs text-gray-500">
                  Torque (nominal, N·m)
                  <input
                    type="text"
                    value={torqueNom}
                    onChange={(e) => setTorqueNom(e.target.value)}
                    placeholder="e.g. 9.8"
                    className="w-full mt-1 px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
                  />
                </label>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <label className="text-xs text-gray-500">
                  Torque (min, N·m)
                  <input
                    type="text"
                    value={torqueMin}
                    onChange={(e) => setTorqueMin(e.target.value)}
                    className="w-full mt-1 px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
                  />
                </label>
                <label className="text-xs text-gray-500">
                  Torque (max, N·m)
                  <input
                    type="text"
                    value={torqueMax}
                    onChange={(e) => setTorqueMax(e.target.value)}
                    className="w-full mt-1 px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
                  />
                </label>
              </div>
            </>
          )}
        </div>

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
            onClick={submit}
            disabled={submitting || !partAId || !partBId || partAId === partBId}
            className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded disabled:opacity-50"
          >
            {submitting ? 'Creating…' : 'Create joint'}
          </button>
        </div>
      </div>
    </div>
  );
}
