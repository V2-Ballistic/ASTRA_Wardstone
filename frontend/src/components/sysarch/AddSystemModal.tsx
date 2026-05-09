'use client';

/**
 * ASTRA — AddSystemModal (TDD-SYSARCH-002 §4 Phase 4)
 * =====================================================
 * Pops a modal to create a new System under the current project.
 * Wires `useFormAutosave` so refresh / session timeout doesn't lose
 * the user's typing.
 */

import { useEffect, useMemo, useState } from 'react';
import { Loader2, X } from 'lucide-react';

import { interfaceAPI } from '@/lib/interface-api';
import type {
  System,
  SystemStatus,
  SystemType,
} from '@/lib/interface-types';
import { useFormAutosave } from '@/lib/autosave';
import RestorePromptBanner from '@/components/RestorePromptBanner';


const SYSTEM_TYPES: SystemType[] = [
  'subsystem', 'lru', 'wru', 'sru', 'sensor_suite', 'actuator_assembly',
  'processor_unit', 'power_system', 'thermal_system', 'structural',
  'ground_segment', 'vehicle', 'payload', 'antenna_system', 'propulsion',
  'guidance_nav_control', 'communication', 'data_handling', 'ordnance',
  'test_equipment', 'external_system', 'software', 'firmware', 'custom',
];

const SYSTEM_STATUSES: SystemStatus[] = [
  'concept', 'preliminary_design', 'detailed_design', 'fabrication',
  'integration', 'qualification_test', 'acceptance_test', 'operational',
  'maintenance', 'retired', 'obsolete',
];


export interface AddSystemModalProps {
  open: boolean;
  projectId: number;
  /** Existing systems for the parent dropdown. */
  systems: System[];
  onClose: () => void;
  onCreated: (system: System) => void;
}


interface DraftState {
  name: string;
  abbreviation: string;
  system_type: SystemType;
  status: SystemStatus;
  parent_system_id: number | null;
  wbs_number: string;
  responsible_org: string;
  description: string;
}


const EMPTY_DRAFT: DraftState = {
  name: '',
  abbreviation: '',
  system_type: 'subsystem',
  status: 'concept',
  parent_system_id: null,
  wbs_number: '',
  responsible_org: '',
  description: '',
};


export default function AddSystemModal({
  open, projectId, systems, onClose, onCreated,
}: AddSystemModalProps) {
  const [draft, setDraft] = useState<DraftState>(EMPTY_DRAFT);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const storageKey = `astra:autosave:system-new:project-${projectId}`;
  const memoDraft = useMemo(() => draft, [draft]);
  const {
    hasDraft, draftAge, restoreDraft, clearDraft,
  } = useFormAutosave<DraftState>(storageKey, memoDraft);

  // Reset transient state when the modal closes.
  useEffect(() => {
    if (!open) {
      setError(null);
      setSubmitting(false);
    }
  }, [open]);

  const submit = async () => {
    if (!draft.name.trim() || draft.name.length < 1) {
      setError('Name is required.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const r = await interfaceAPI.createSystem(projectId, {
        name: draft.name.trim(),
        abbreviation: draft.abbreviation.trim() || undefined,
        system_type: draft.system_type,
        status: draft.status,
        parent_system_id: draft.parent_system_id ?? undefined,
        wbs_number: draft.wbs_number.trim() || undefined,
        responsible_org: draft.responsible_org.trim() || undefined,
        description: draft.description.trim() || undefined,
      });
      clearDraft();
      setDraft(EMPTY_DRAFT);
      onCreated(r.data);
      onClose();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || (e instanceof Error ? e.message : 'Create failed');
      setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
    } finally {
      setSubmitting(false);
    }
  };

  const onRestore = () => {
    const v = restoreDraft();
    if (v) setDraft(v);
  };

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-system-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-lg rounded-xl border border-astra-border bg-astra-surface p-5 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 id="add-system-title" className="text-base font-bold text-slate-100">
            Add System
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            aria-label="Close"
            className="rounded p-1 text-slate-400 hover:bg-astra-surface-alt hover:text-slate-200"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {hasDraft && draftAge !== null && (
          <RestorePromptBanner
            ageMs={draftAge}
            onRestore={onRestore}
            onDiscard={clearDraft}
          />
        )}

        {error && (
          <div role="alert" className="mb-3 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
            {error}
          </div>
        )}

        <div className="space-y-3">
          <div>
            <label htmlFor="sys-name" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Name <span className="text-red-400">*</span>
            </label>
            <input
              id="sys-name"
              type="text"
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              placeholder="Avionics"
              className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="sys-abbr" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Abbreviation
              </label>
              <input
                id="sys-abbr"
                type="text"
                maxLength={16}
                value={draft.abbreviation}
                onChange={(e) => setDraft({ ...draft, abbreviation: e.target.value })}
                placeholder="AVN"
                className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
              />
            </div>
            <div>
              <label htmlFor="sys-type" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Type
              </label>
              <select
                id="sys-type"
                value={draft.system_type}
                onChange={(e) => setDraft({ ...draft, system_type: e.target.value as SystemType })}
                className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
              >
                {SYSTEM_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="sys-status" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Status
              </label>
              <select
                id="sys-status"
                value={draft.status}
                onChange={(e) => setDraft({ ...draft, status: e.target.value as SystemStatus })}
                className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
              >
                {SYSTEM_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="sys-parent" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Parent system
              </label>
              <select
                id="sys-parent"
                value={draft.parent_system_id == null ? '' : String(draft.parent_system_id)}
                onChange={(e) => setDraft({
                  ...draft,
                  parent_system_id: e.target.value === '' ? null : Number(e.target.value),
                })}
                className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
              >
                <option value="">— none —</option>
                {systems.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}{s.abbreviation ? ` (${s.abbreviation})` : ''}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="sys-wbs" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                WBS number
              </label>
              <input
                id="sys-wbs"
                type="text"
                value={draft.wbs_number}
                onChange={(e) => setDraft({ ...draft, wbs_number: e.target.value })}
                placeholder="1.2.3"
                className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
              />
            </div>
            <div>
              <label htmlFor="sys-org" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Responsible org
              </label>
              <input
                id="sys-org"
                type="text"
                value={draft.responsible_org}
                onChange={(e) => setDraft({ ...draft, responsible_org: e.target.value })}
                placeholder="Avionics IPT"
                className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
              />
            </div>
          </div>

          <div>
            <label htmlFor="sys-desc" className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Description
            </label>
            <textarea
              id="sys-desc"
              rows={3}
              value={draft.description}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              className="w-full rounded border border-astra-border bg-astra-bg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"
            />
          </div>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded border border-astra-border px-3 py-1.5 text-xs text-slate-300 hover:bg-astra-surface-alt"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={submitting || !draft.name.trim()}
            className="flex items-center gap-1.5 rounded bg-gradient-to-br from-blue-500 to-violet-500 px-3 py-1.5 text-xs font-semibold text-white hover:shadow-lg disabled:opacity-50"
          >
            {submitting && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
            Add System
          </button>
        </div>
      </div>
    </div>
  );
}
