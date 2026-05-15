'use client';
/**
 * CADPORT-REBUILD-003 — Assemblies tab (L9) + assembly detail + the
 * schematic isometric CAD view (Phases 2-4).
 *
 * Lives inside the Mechanical Interfaces page as a peer tab (AD-1).
 * ASTRA dark aerospace aesthetic (AD-5/AD-8): bg-astra-surface,
 * border-astra-border, rounded-xl cards, blue accents.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, ArrowLeft, Box, Boxes, CheckCircle, Download,
  Loader2, Plus, RefreshCw, ExternalLink,
} from 'lucide-react';
import clsx from 'clsx';

import { cadportAPI, type CadportAssembly, type CadportComponent } from '@/lib/cadport-api';
import { formatApiError } from '@/lib/errors';

const fmt = (n: number | null | undefined, d = 4) =>
  n == null ? '—' : Number(n).toFixed(d);
const cleanMaterial = (m: string | null) =>
  !m ? '—' : m.includes('|') ? m.split('|').slice(-2, -1)[0] || m : m;

export default function AssembliesTab({ projectId }: { projectId: number }) {
  const [list, setList] = useState<CadportAssembly[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPk, setSelectedPk] = useState<number | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    cadportAPI
      .listAssemblies(projectId)
      .then((r) => setList(r.data))
      .catch((e) => setError(formatApiError(e)))
      .finally(() => setLoading(false));
  }, [projectId]);

  useEffect(() => { reload(); }, [reload]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-5 w-5 animate-spin text-blue-500" aria-label="Loading" />
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
        {error}
      </div>
    );
  }
  if (selectedPk != null) {
    return (
      <AssemblyDetail
        pk={selectedPk}
        projectId={projectId}
        onBack={() => { setSelectedPk(null); reload(); }}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-100">CADPORT Assemblies</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            SolidWorks assemblies extracted via CADPORT and linked to this project.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={reload}
            className="flex items-center gap-1.5 rounded-lg border border-astra-border bg-astra-surface px-3 py-1.5 text-xs text-slate-300 hover:text-slate-100"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </button>
          <a
            href="http://localhost:3030/cadport"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 rounded-lg border border-blue-500/40 bg-blue-500/10 px-3 py-1.5 text-xs font-semibold text-blue-300 hover:bg-blue-500/20"
          >
            <ExternalLink className="h-3.5 w-3.5" /> Import Assembly
          </a>
        </div>
      </div>

      {list.length === 0 ? (
        <div className="rounded-xl border border-astra-border bg-astra-surface p-10 text-center">
          <Boxes className="mx-auto h-9 w-9 text-slate-600" />
          <p className="mt-3 text-sm text-slate-300">No assemblies imported for this project</p>
          <p className="mt-1 text-xs text-slate-500">
            Extract a SolidWorks assembly in CADPORT and import it to ASTRA.
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-astra-border">
          <table className="w-full text-sm">
            <thead className="bg-astra-surface-alt text-[10px] uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2.5 text-left font-medium">Assembly</th>
                <th className="px-4 py-2.5 text-left font-medium">Source file</th>
                <th className="px-4 py-2.5 text-right font-medium">Total mass</th>
                <th className="px-4 py-2.5 text-right font-medium">Components</th>
                <th className="px-4 py-2.5 text-left font-medium">SW</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-astra-border">
              {list.map((a) => (
                <tr
                  key={a.id}
                  onClick={() => setSelectedPk(a.id)}
                  className="cursor-pointer bg-astra-surface hover:bg-astra-surface-hover"
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Boxes className="h-4 w-4 text-blue-400" />
                      <span className="font-medium text-slate-100">{a.display_name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-400">{a.source_file}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-300">
                    {fmt(a.total_mass_kg, 3)} kg
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-300">
                    {a.component_count}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-500">
                    {a.solidworks_version ?? '—'}
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

// ─────────────────────────────────────────────────────────────────
//  Assembly detail
// ─────────────────────────────────────────────────────────────────

function AssemblyDetail({
  pk, projectId, onBack,
}: { pk: number; projectId: number; onBack: () => void }) {
  const [asm, setAsm] = useState<CadportAssembly | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState<number | null>(null);
  const [selectedComp, setSelectedComp] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    cadportAPI
      .getAssembly(pk)
      .then((r) => setAsm(r.data))
      .catch((e) => setError(formatApiError(e)))
      .finally(() => setLoading(false));
  }, [pk]);

  useEffect(() => { load(); }, [load]);

  const addToProject = async (c: CadportComponent) => {
    if (c.catalog_part_id == null) return;
    setAdding(c.catalog_part_id);
    try {
      await cadportAPI.addPartToProject(projectId, c.catalog_part_id, c.display_name ?? undefined);
      load(); // re-fetch → project_part_exists flips, warning clears
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setAdding(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-5 w-5 animate-spin text-blue-500" />
      </div>
    );
  }
  if (error || !asm) {
    return (
      <div className="space-y-3">
        <button onClick={onBack} className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to assemblies
        </button>
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
          {error ?? 'Assembly not found'}
        </div>
      </div>
    );
  }

  const missing = asm.components.filter((c) => !c.project_part_exists && c.catalog_part_id != null);

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to assemblies
      </button>

      {/* Metadata card */}
      <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Boxes className="h-5 w-5 text-blue-400" />
              <h2 className="text-lg font-semibold text-slate-100">{asm.display_name}</h2>
            </div>
            <p className="mt-1 font-mono text-xs text-slate-500">{asm.source_file}</p>
          </div>
          {asm.assembly_yaml_document_id != null && (
            <button
              type="button"
              onClick={() =>
                cadportAPI.downloadDocument(
                  asm.assembly_yaml_document_id as number,
                  asm.assembly_yaml_filename ?? `${asm.display_name}.yaml`,
                )
              }
              className="flex items-center gap-1.5 rounded-lg border border-blue-500/40 bg-blue-500/10 px-3 py-1.5 text-xs font-semibold text-blue-300 hover:bg-blue-500/20"
            >
              <Download className="h-3.5 w-3.5" /> {asm.assembly_yaml_filename ?? 'Assembly YAML'}
            </button>
          )}
        </div>
        <div className="mt-4 grid grid-cols-2 gap-x-8 gap-y-2 text-xs md:grid-cols-4">
          <Meta label="Total mass" value={`${fmt(asm.total_mass_kg, 4)} kg`} />
          <Meta label="Components" value={String(asm.component_count)} />
          <Meta label="Project" value={asm.project_code ? `${asm.project_code} — ${asm.project_name}` : String(asm.project_id)} />
          <Meta label="SolidWorks" value={asm.solidworks_version ?? '—'} />
          <Meta label="CG (m)" value={asm.center_of_mass.map((v) => v.toFixed(3)).join(', ')} />
          <Meta label="content_hash" value={(asm.content_hash ?? '—').replace('sha256:', '').slice(0, 16) + '…'} mono />
          <Meta label="assembly_id" value={asm.assembly_id.slice(0, 8) + '…'} mono />
        </div>
      </div>

      {/* Rollup Mass Properties (CADPORT-REBUILD-003 fix #3) */}
      {asm.inertia && (
        <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
          <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
            Mass Properties
            <span className="ml-1 font-mono text-[10px] normal-case text-slate-600">
              rollup · CITADEL body frame · SI
            </span>
          </h3>
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
              <Meta label="Total mass" value={`${fmt(asm.total_mass_kg, 6)} kg`} mono />
              <Meta label="CG x (m)" value={fmt(asm.center_of_mass[0], 6)} mono />
              <Meta label="CG y (m)" value={fmt(asm.center_of_mass[1], 6)} mono />
              <Meta label="CG z (m)" value={fmt(asm.center_of_mass[2], 6)} mono />
            </div>
            <div>
              <div className="mb-1.5 text-[10px] uppercase tracking-wide text-slate-600">
                Inertia tensor (kg·m², about CG)
              </div>
              <table className="w-full font-mono text-[11px] tabular-nums text-slate-300">
                <tbody>
                  <tr><ITd v={asm.inertia.ixx} /><ITd v={asm.inertia.ixy} /><ITd v={asm.inertia.ixz} /></tr>
                  <tr><ITd v={asm.inertia.ixy} /><ITd v={asm.inertia.iyy} /><ITd v={asm.inertia.iyz} /></tr>
                  <tr><ITd v={asm.inertia.ixz} /><ITd v={asm.inertia.iyz} /><ITd v={asm.inertia.izz} /></tr>
                </tbody>
              </table>
              {asm.principal_moments_kg_m2?.length === 3 && (
                <div className="mt-3">
                  <div className="mb-1 text-[10px] uppercase tracking-wide text-slate-600">
                    Principal moments (kg·m²)
                  </div>
                  <div className="font-mono text-[11px] tabular-nums text-slate-300">
                    {asm.principal_moments_kg_m2.map((m) => m.toExponential(6)).join('  ·  ')}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Missing parts banner */}
      {missing.length > 0 && (
        <div className="flex items-center gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-300">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>
            {missing.length} of {asm.components.length} components are not yet added to this
            project. Use “Add to project” below to create the project_part link (L8).
          </span>
        </div>
      )}

      {/* Schematic isometric view */}
      <IsometricView
        components={asm.components}
        selected={selectedComp}
        onSelect={setSelectedComp}
      />

      {/* Component breakdown */}
      <div className="overflow-hidden rounded-xl border border-astra-border">
        <div className="border-b border-astra-border bg-astra-surface-alt px-4 py-2.5 text-[10px] uppercase tracking-wide text-slate-500">
          Component breakdown
        </div>
        <table className="w-full text-sm">
          <thead className="bg-astra-surface-alt text-[10px] uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2.5 text-left font-medium">Part</th>
              <th className="px-4 py-2.5 text-left font-medium">WPN</th>
              <th className="px-4 py-2.5 text-left font-medium">Instance</th>
              <th className="px-4 py-2.5 text-right font-medium">Mass</th>
              <th className="px-4 py-2.5 text-right font-medium">Qty</th>
              <th className="px-4 py-2.5 text-left font-medium">Material</th>
              <th className="px-4 py-2.5 text-left font-medium">Project</th>
              <th className="px-4 py-2.5 text-right font-medium">YAML</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-astra-border">
            {asm.components.map((c) => {
              const isSel = selectedComp === c.cadport_part_id;
              return (
                <tr
                  key={c.cadport_part_id || c.instance_name}
                  onMouseEnter={() => setSelectedComp(c.cadport_part_id)}
                  className={clsx('bg-astra-surface', isSel && 'bg-astra-surface-hover')}
                >
                  <td className="px-4 py-3">
                    {c.catalog_part_id != null ? (
                      <a
                        href={`/catalog/parts/${c.catalog_part_id}`}
                        className="flex items-center gap-1.5 font-medium text-blue-300 hover:text-blue-200"
                      >
                        <Box className="h-3.5 w-3.5" /> {c.display_name}
                      </a>
                    ) : (
                      <span className="flex items-center gap-1.5 text-slate-300">
                        <Box className="h-3.5 w-3.5" /> {c.display_name}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-400">{c.wpn ?? '—'}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-500">{c.instance_name}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-300">{fmt(c.mass_kg, 4)} kg</td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-300">{c.quantity}</td>
                  <td className="px-4 py-3 text-xs text-slate-400">{cleanMaterial(c.material)}</td>
                  <td className="px-4 py-3">
                    {c.project_part_exists ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-green-500/15 px-2 py-0.5 text-[10px] font-medium text-green-300">
                        <CheckCircle className="h-3 w-3" /> In project
                      </span>
                    ) : c.catalog_part_id != null ? (
                      <button
                        onClick={() => addToProject(c)}
                        disabled={adding === c.catalog_part_id}
                        className="inline-flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-300 hover:bg-amber-500/20"
                      >
                        {adding === c.catalog_part_id
                          ? <Loader2 className="h-3 w-3 animate-spin" />
                          : <Plus className="h-3 w-3" />}
                        Add to project
                      </button>
                    ) : (
                      <span className="text-[10px] text-slate-600">no catalog link</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {c.part_yaml_document_id != null ? (
                      <button
                        type="button"
                        onClick={() =>
                          cadportAPI.downloadDocument(
                            c.part_yaml_document_id as number,
                            `${c.wpn ?? c.display_name ?? 'part'}.yaml`,
                          )
                        }
                        className="inline-flex items-center gap-1 text-xs text-blue-300 hover:text-blue-200"
                      >
                        <Download className="h-3 w-3" /> YAML
                      </button>
                    ) : (
                      <span className="text-xs text-slate-600">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Meta({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-slate-600">{label}</div>
      <div className={clsx('mt-0.5 text-slate-200', mono && 'font-mono text-xs')}>{value}</div>
    </div>
  );
}

function ITd({ v }: { v: number | null | undefined }) {
  const txt =
    v == null || Number.isNaN(v)
      ? '—'
      : Math.abs(v) !== 0 && (Math.abs(v) < 1e-3 || Math.abs(v) >= 1e6)
        ? v.toExponential(6)
        : v.toFixed(6);
  return <td className="px-2 py-1 text-right">{txt}</td>;
}

// ─────────────────────────────────────────────────────────────────
//  Schematic isometric view (AD-2 / AD-7 — pure SVG)
// ─────────────────────────────────────────────────────────────────

const COS30 = Math.cos(Math.PI / 6);
const SIN30 = Math.sin(Math.PI / 6);

function IsometricView({
  components, selected, onSelect,
}: {
  components: CadportComponent[];
  selected: string | null;
  onSelect: (id: string | null) => void;
}) {
  // Extract translation (col 3, rows 0-2) from each 4x4 transform.
  // transform_m is row-major [[r,r,r,tx],[r,r,r,ty],[r,r,r,tz],[0,0,0,1]].
  const placed = useMemo(() => {
    return components.map((c) => {
      const t = c.transform;
      const pos = t && t.length >= 3
        ? [Number(t[0][3]) || 0, Number(t[1][3]) || 0, Number(t[2][3]) || 0]
        : [0, 0, 0];
      // Box half-size estimated from mass (schematic only — AD-2).
      const m = c.mass_kg ?? 1;
      const s = Math.cbrt(Math.max(m, 0.05)) * 0.06 + 0.05;
      return { c, pos, s };
    });
  }, [components]);

  const { project, bounds } = useMemo(() => {
    const proj = (x: number, y: number, z: number) => ({
      sx: (x - z) * COS30,
      sy: (x + z) * SIN30 - y,
    });
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const { pos, s } of placed) {
      for (const dx of [-s, s]) for (const dy of [-s, s]) for (const dz of [-s, s]) {
        const p = proj(pos[0] + dx, pos[1] + dy, pos[2] + dz);
        minX = Math.min(minX, p.sx); maxX = Math.max(maxX, p.sx);
        minY = Math.min(minY, p.sy); maxY = Math.max(maxY, p.sy);
      }
    }
    if (!isFinite(minX)) { minX = -1; maxX = 1; minY = -1; maxY = 1; }
    return { project: proj, bounds: { minX, maxX, minY, maxY } };
  }, [placed]);

  const W = 720, H = 360, PAD = 40;
  const spanX = bounds.maxX - bounds.minX || 1;
  const spanY = bounds.maxY - bounds.minY || 1;
  const scale = Math.min((W - 2 * PAD) / spanX, (H - 2 * PAD) / spanY);
  const tx = (sx: number) => PAD + (sx - bounds.minX) * scale;
  const ty = (sy: number) => PAD + (sy - bounds.minY) * scale;

  // Painter's algorithm — draw far (low x+z) first.
  const ordered = [...placed].sort(
    (a, b) => (a.pos[0] + a.pos[2]) - (b.pos[0] + b.pos[2]),
  );

  const cube = (cx: number, cy: number, cz: number, s: number) => {
    const v = (x: number, y: number, z: number) => {
      const p = project(x, y, z);
      return `${tx(p.sx)},${ty(p.sy)}`;
    };
    const top = `${v(cx - s, cy + s, cz - s)} ${v(cx + s, cy + s, cz - s)} ${v(cx + s, cy + s, cz + s)} ${v(cx - s, cy + s, cz + s)}`;
    const left = `${v(cx - s, cy + s, cz + s)} ${v(cx + s, cy + s, cz + s)} ${v(cx + s, cy - s, cz + s)} ${v(cx - s, cy - s, cz + s)}`;
    const right = `${v(cx + s, cy + s, cz - s)} ${v(cx + s, cy + s, cz + s)} ${v(cx + s, cy - s, cz + s)} ${v(cx + s, cy - s, cz - s)}`;
    return { top, left, right };
  };

  const sel = placed.find((p) => p.c.cadport_part_id === selected)?.c ?? null;

  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wide text-slate-500">
          Schematic assembly view — component positions from SolidWorks transforms
        </span>
        <span className="text-[10px] text-slate-600">
          isometric · {placed.length} components · sizes estimated from mass
        </span>
      </div>
      <div className="relative">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full"
          style={{ background: '#0B0F19', borderRadius: 8 }}
          onMouseLeave={() => onSelect(null)}
        >
          {ordered.map(({ c, pos, s }) => {
            const f = cube(pos[0], pos[1], pos[2], s);
            const inProj = c.project_part_exists;
            const isSel = c.cadport_part_id === selected;
            // green-ish if in project, amber if missing; brighten on select.
            const base = inProj ? '#3FB950' : '#D29922';
            const op = isSel ? 1 : 0.78;
            return (
              <g
                key={c.cadport_part_id || c.instance_name}
                onMouseEnter={() => onSelect(c.cadport_part_id)}
                style={{ cursor: 'pointer' }}
              >
                <polygon points={f.top} fill={base} opacity={op} stroke={isSel ? '#fff' : '#0B0F19'} strokeWidth={isSel ? 2 : 0.5} />
                <polygon points={f.left} fill={base} opacity={op * 0.62} stroke={isSel ? '#fff' : '#0B0F19'} strokeWidth={isSel ? 2 : 0.5} />
                <polygon points={f.right} fill={base} opacity={op * 0.8} stroke={isSel ? '#fff' : '#0B0F19'} strokeWidth={isSel ? 2 : 0.5} />
              </g>
            );
          })}
        </svg>
        {sel && (
          <div className="pointer-events-none absolute left-3 top-3 rounded-lg border border-astra-border bg-astra-surface-alt/95 px-3 py-2 text-xs shadow-lg">
            <div className="font-semibold text-slate-100">{sel.display_name}</div>
            <div className="mt-1 space-y-0.5 font-mono text-[11px] text-slate-400">
              <div>WPN: {sel.wpn ?? '—'}</div>
              <div>mass: {fmt(sel.mass_kg, 4)} kg</div>
              <div>material: {cleanMaterial(sel.material)}</div>
              <div className={sel.project_part_exists ? 'text-green-400' : 'text-amber-400'}>
                {sel.project_part_exists ? 'in project' : 'not added to project'}
              </div>
            </div>
          </div>
        )}
      </div>
      <div className="mt-2 flex items-center gap-4 text-[10px] text-slate-500">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: '#3FB950' }} /> in project
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: '#D29922' }} /> not added
        </span>
      </div>
    </div>
  );
}
