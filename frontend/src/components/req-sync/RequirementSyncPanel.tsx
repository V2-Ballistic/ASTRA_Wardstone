'use client';

/**
 * ASTRA — Sync Lock + Source Links panel
 * ==========================================
 * File: frontend/src/components/req-sync/RequirementSyncPanel.tsx
 * Phase 5 — ASTRA-TDD-INTF-002
 *
 * Drops into the requirement detail page right sidebar. Shows the
 * sync_locked toggle (req_eng+ only) + every RequirementSourceLink.
 */

import { useState, useEffect } from 'react';
import { Lock, Unlock, Loader2, Link2 } from 'lucide-react';
import clsx from 'clsx';

import { reqSyncAPI } from '@/lib/req-sync-api';
import { formatApiError } from '@/lib/errors';
import type {
  RequirementSourceLink,
  SourceEntityType,
} from '@/lib/req-sync-types';

const ENTITY_LABELS: Record<SourceEntityType, string> = {
  system: 'System',
  unit: 'Unit',
  connector: 'Connector',
  pin: 'Pin',
  interface: 'Interface',
  wire_harness: 'Wire Harness',
  wire: 'Wire',
  bus_definition: 'Bus',
  message_definition: 'Message',
  message_field: 'Message Field',
  unit_env_spec: 'Env Spec',
  catalog_part: 'Catalog Part',
  requirement: 'Requirement',
};

interface Props {
  requirementId: number;
  syncLocked: boolean;
  syncLockedReason?: string | null;
  canManageLock: boolean;
  onChange?: () => void;
}

export default function RequirementSyncPanel({
  requirementId, syncLocked, syncLockedReason,
  canManageLock, onChange,
}: Props) {

  const [busy, setBusy] = useState(false);
  const [showLock, setShowLock] = useState(false);
  const [reason, setReason] = useState('');
  const [sources, setSources] = useState<RequirementSourceLink[]>([]);
  const [loadingSources, setLoadingSources] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoadingSources(true);
    reqSyncAPI.getRequirementSources(requirementId)
      .then(r => setSources(r.data.items ?? []))
      .catch(() => setSources([]))
      .finally(() => setLoadingSources(false));
  }, [requirementId]);

  const lock = async () => {
    setBusy(true);
    setError(null);
    try {
      await reqSyncAPI.lockRequirement(requirementId, { reason: reason || undefined });
      setShowLock(false);
      setReason('');
      onChange?.();
    } catch (e: any) {
      setError(formatApiError(e, 'Lock failed'));
    } finally {
      setBusy(false);
    }
  };

  const unlock = async () => {
    setBusy(true);
    setError(null);
    try {
      await reqSyncAPI.unlockRequirement(requirementId);
      onChange?.();
    } catch (e: any) {
      setError(formatApiError(e, 'Unlock failed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
      <h3 className="mb-3 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        <Lock className="h-3 w-3" /> Sync
      </h3>

      {/* Lock state */}
      <div className="mb-3">
        {syncLocked ? (
          <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-2.5">
            <div className="flex items-center gap-2 text-xs font-semibold text-amber-300">
              <Lock className="h-3.5 w-3.5" /> Sync-locked
            </div>
            {syncLockedReason && (
              <div className="mt-1 text-[11px] text-slate-400">{syncLockedReason}</div>
            )}
            {canManageLock && (
              <button
                onClick={unlock}
                disabled={busy}
                className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-md border border-astra-border px-2 py-1 text-[11px] font-semibold text-slate-300 hover:bg-astra-surface-alt disabled:opacity-50"
              >
                <Unlock className="h-3 w-3" /> Unlock
              </button>
            )}
          </div>
        ) : canManageLock ? (
          showLock ? (
            <div className="space-y-2">
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Why are you locking this requirement?"
                rows={2}
                className="w-full rounded-md border border-astra-border bg-astra-surface-alt px-2 py-1.5 text-xs text-slate-200"
              />
              <div className="flex gap-2">
                <button
                  onClick={lock}
                  disabled={busy}
                  className="flex-1 rounded-md bg-amber-500 px-2 py-1.5 text-[11px] font-semibold text-slate-900 hover:bg-amber-400 disabled:opacity-50"
                >
                  Lock
                </button>
                <button
                  onClick={() => { setShowLock(false); setReason(''); }}
                  className="flex-1 rounded-md border border-astra-border px-2 py-1.5 text-[11px] font-semibold text-slate-400 hover:bg-astra-surface-alt"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setShowLock(true)}
              className="flex w-full items-center justify-center gap-1.5 rounded-md border border-astra-border px-2 py-1.5 text-[11px] font-semibold text-slate-300 hover:bg-astra-surface-alt"
            >
              <Lock className="h-3 w-3" /> Lock from auto-sync
            </button>
          )
        ) : (
          <div className="text-[11px] text-slate-500">Auto-sync is enabled (not locked).</div>
        )}
      </div>

      {error && (
        <div className="mb-3 rounded-md border border-rose-500/30 bg-rose-500/10 px-2 py-1.5 text-[11px] text-rose-300">
          {error}
        </div>
      )}

      {/* Source links */}
      <div>
        <h4 className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          <Link2 className="h-3 w-3" /> Source links
        </h4>
        {loadingSources ? (
          <Loader2 className="h-4 w-4 animate-spin text-slate-500" />
        ) : sources.length === 0 ? (
          <div className="text-[11px] text-slate-500">No source links.</div>
        ) : (
          <ul className="space-y-1.5">
            {sources.map(s => (
              <li key={s.id} className="rounded-md border border-astra-border bg-astra-surface-alt p-2 text-[11px]">
                <div className="font-semibold text-slate-200">
                  {ENTITY_LABELS[s.source_entity_type]} #{s.source_entity_id}
                </div>
                <div className="font-mono text-[10px] text-slate-500">
                  {s.template_id} · {s.role}
                </div>
                <div className="text-[10px] text-slate-600">
                  last sync: {s.last_synced_at ? new Date(s.last_synced_at).toLocaleDateString() : '—'}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
