'use client';

/**
 * ASTRA — System Architecture page (TDD-SYSARCH-002 §4)
 * =======================================================
 * Three tabs (`?tab=arch|systems|units`, default `arch`) with a
 * project-scoped stat strip above. Replaces the prior placeholder.
 *
 * Phase 5 wires the architecture force graph (currently a placeholder
 * "graph coming next" pending Phase 5 commit).
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import {
  Boxes, Cpu, Layers3, Link2, Loader2, Network,
} from 'lucide-react';
import clsx from 'clsx';

import { interfaceAPI } from '@/lib/interface-api';
import { formatApiError } from '@/lib/errors';
import type { System, UnitSummary } from '@/lib/interface-types';
import SystemsListTab from '@/components/sysarch/SystemsListTab';
import UnitsListTab from '@/components/sysarch/UnitsListTab';
import SystemArchGraph from '@/components/sysarch/SystemArchGraph';


type Tab = 'arch' | 'systems' | 'units';
const TABS: Tab[] = ['arch', 'systems', 'units'];


function isTab(s: string | null | undefined): s is Tab {
  return s === 'arch' || s === 'systems' || s === 'units';
}


function StatCard({
  icon: Icon, label, value, color, subText,
}: {
  icon: typeof Boxes;
  label: string;
  value: string | number;
  color: string;
  subText?: string;
}) {
  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{label}</p>
          <p className="mt-1.5 text-2xl font-bold tabular-nums text-slate-100">{value}</p>
          {subText && <p className="text-[10px] text-slate-500">{subText}</p>}
        </div>
        <div className="rounded-lg p-2" style={{ background: `${color}20` }}>
          <Icon className="h-4 w-4" style={{ color }} aria-hidden="true" />
        </div>
      </div>
    </div>
  );
}


// Compute the longest parent chain across all systems, client-side.
// Returns 1 for a flat list of unconnected systems, 0 if the list is
// empty.
function computeHierarchyDepth(systems: System[]): number {
  if (!systems.length) return 0;
  const byId = new Map<number, System>();
  for (const s of systems) byId.set(s.id, s);
  const depthOf = (sys: System, seen: Set<number>): number => {
    if (sys.parent_system_id == null) return 1;
    if (seen.has(sys.id)) return 1; // cycle guard
    const parent = byId.get(sys.parent_system_id);
    if (!parent) return 1;
    seen.add(sys.id);
    return 1 + depthOf(parent, seen);
  };
  let max = 1;
  for (const s of systems) {
    const d = depthOf(s, new Set());
    if (d > max) max = d;
  }
  return max;
}


export default function SystemArchitecturePage() {
  const params = useParams();
  const projectId = Number(params?.id);
  const router = useRouter();
  const searchParams = useSearchParams();
  const tabParam = searchParams?.get('tab') ?? null;
  const tab: Tab = isTab(tabParam) ? tabParam : 'arch';

  const [systems, setSystems] = useState<System[]>([]);
  const [units, setUnits] = useState<UnitSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      interfaceAPI.listSystems(projectId, 'flat'),
      interfaceAPI.listUnits(projectId, { limit: 200 }),
    ])
      .then(([sysRes, unitRes]) => {
        setSystems(sysRes.data);
        setUnits(unitRes.data);
      })
      .catch((e) => {
        setError(formatApiError(e, 'Failed to load project data'));
      })
      .finally(() => setLoading(false));
  }, [projectId]);

  useEffect(() => { fetchStats(); }, [fetchStats]);

  // ── Stat strip values ──
  const totalSystems = systems.length;
  const totalUnits = units.length;
  const linkedUnits = useMemo(
    () => units.filter((u) => u.catalog_part_id != null).length,
    [units],
  );
  const hierarchyDepth = useMemo(() => computeHierarchyDepth(systems), [systems]);

  const setTab = (next: Tab) => {
    const sp = new URLSearchParams(searchParams?.toString() || '');
    sp.set('tab', next);
    router.replace(`/projects/${projectId}/system-architecture?${sp.toString()}`);
  };

  return (
    <div>
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
            <Network className="h-6 w-6 text-blue-400" aria-hidden="true" />
            System Architecture
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Cross-cutting view of systems, units, and the connections between them.
          </p>
        </div>
      </div>

      {error && (
        <div role="alert" className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
          {error}
        </div>
      )}

      {/* Stat strip (matches the Projects-dashboard pattern) */}
      <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={Boxes}
          label="Systems"
          value={loading ? '—' : totalSystems}
          color="#3B82F6"
        />
        <StatCard
          icon={Cpu}
          label="Units"
          value={loading ? '—' : totalUnits}
          color="#A78BFA"
        />
        <StatCard
          icon={Link2}
          label="Catalog Linked"
          value={loading ? '—' : linkedUnits}
          subText={totalUnits > 0 ? `${linkedUnits} of ${totalUnits} units` : undefined}
          color="#10B981"
        />
        <StatCard
          icon={Layers3}
          label="Hierarchy Depth"
          value={loading ? '—' : hierarchyDepth}
          color="#F59E0B"
        />
      </div>

      {/* Tabs */}
      <div role="tablist" aria-label="System Architecture sections" className="mb-4 flex gap-1 border-b border-astra-border">
        {TABS.map((t) => {
          const active = tab === t;
          const labels: Record<Tab, string> = {
            arch: 'Architecture',
            systems: 'Systems',
            units: 'Units',
          };
          return (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={active}
              aria-controls={`sysarch-panel-${t}`}
              id={`sysarch-tab-${t}`}
              onClick={() => setTab(t)}
              className={clsx(
                'flex items-center gap-1.5 rounded-t-lg border-b-2 px-4 py-2 text-xs font-semibold transition',
                active
                  ? 'border-blue-400 text-blue-300'
                  : 'border-transparent text-slate-400 hover:text-slate-200',
              )}
            >
              {labels[t]}
            </button>
          );
        })}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-5 w-5 animate-spin text-blue-500" aria-label="Loading" />
        </div>
      ) : (
        <div id={`sysarch-panel-${tab}`} role="tabpanel" aria-labelledby={`sysarch-tab-${tab}`}>
          {tab === 'arch' && (
            <SystemArchGraph
              projectId={projectId}
              onAddSystem={() => setTab('systems')}
            />
          )}
          {tab === 'systems' && <SystemsListTab projectId={projectId} />}
          {tab === 'units' && <UnitsListTab projectId={projectId} />}
        </div>
      )}
    </div>
  );
}
