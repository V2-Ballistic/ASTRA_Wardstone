'use client';
/**
 * CADPORT-REBUILD-004 Phase 4 — real-geometry assembly viewer.
 *
 * Replaces the schematic SVG iso view with Three.js: each component's
 * binary STL (exported by the bridge during extraction, served by
 * ASTRA via /catalog/documents/{id}/file) is loaded, placed by its
 * 4×4 transform, colour-coded by project membership, and made
 * clickable for identify. OrbitControls for orbit/zoom/pan; dark
 * aerospace background (AD-8 #0f1724); ambient + directional lights.
 *
 * AD-7: a component with no STL (export failed / pre-STL extraction)
 * falls back to a schematic box sized from its mass — so a partial
 * mesh set still renders a complete assembly. If WebGL is entirely
 * unavailable the parent swaps in the legacy SVG view (`fallback`).
 *
 * three addons are imported from three/examples/jsm/** (ESM); the
 * `three` package is in next.config transpilePackages so they resolve.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { cadportAPI, type CadportComponent } from '@/lib/cadport-api';

const COLOR_IN_PROJECT = 0x3fb950; // green — matches the SVG legend
const COLOR_MISSING = 0xd29922; // amber
const BG = 0x0f1724;

export function isWebGLAvailable(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const c = document.createElement('canvas');
    return !!(
      window.WebGLRenderingContext &&
      (c.getContext('webgl2') || c.getContext('webgl'))
    );
  } catch {
    return false;
  }
}

const cleanMaterial = (m: string | null) =>
  !m ? '—' : m.includes('|') ? m.split('|').slice(-2, -1)[0] || m : m;
const fmt = (n: number | null | undefined, d = 4) =>
  n == null ? '—' : Number(n).toFixed(d);

interface Props {
  components: CadportComponent[];
  selected: string | null;
  onSelect: (id: string | null) => void;
  fallback: React.ReactNode;
}

export default function AssemblyViewer({
  components,
  selected,
  onSelect,
  fallback,
}: Props) {
  const webgl = useMemo(() => isWebGLAvailable(), []);
  const mountRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>(
    'loading',
  );
  const [meshCount, setMeshCount] = useState(0);
  const [boxCount, setBoxCount] = useState(0);

  // Per-mesh material refs so the `selected` effect can re-highlight
  // without rebuilding the scene.
  const matsRef = useRef<Map<string, { mat: any; base: number }>>(new Map());
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    if (!webgl || !mountRef.current) return;
    const mount = mountRef.current;
    let disposed = false;
    let raf = 0;
    let renderer: any;
    let controls: any;
    let ro: ResizeObserver | null = null;
    const cleanups: Array<() => void> = [];

    (async () => {
      const THREE = await import('three');
      const { STLLoader } = await import(
        'three/examples/jsm/loaders/STLLoader.js'
      );
      const { OrbitControls } = await import(
        'three/examples/jsm/controls/OrbitControls.js'
      );
      if (disposed) return;

      const width = mount.clientWidth || 720;
      const height = 420;

      const scene = new THREE.Scene();
      scene.background = new THREE.Color(BG);

      const camera = new THREE.PerspectiveCamera(
        45,
        width / height,
        0.001,
        10000,
      );

      renderer = new THREE.WebGLRenderer({ antialias: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.setSize(width, height);
      mount.appendChild(renderer.domElement);

      scene.add(new THREE.AmbientLight(0xffffff, 0.65));
      const key = new THREE.DirectionalLight(0xffffff, 0.85);
      key.position.set(1, 1.4, 1);
      scene.add(key);
      const fill = new THREE.DirectionalLight(0xffffff, 0.35);
      fill.position.set(-1, -0.6, -1);
      scene.add(fill);

      controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;

      const loader = new STLLoader();

      // ── Build placement matrix from the 4×4 (row-major, CITADEL
      // body frame, metres). Same decode as the SVG iso view: the
      // translation is column 3, rows 0-2.
      const placement = (t: number[][] | null) => {
        const m = new THREE.Matrix4();
        if (t && t.length >= 4) {
          m.set(
            t[0][0], t[0][1], t[0][2], t[0][3],
            t[1][0], t[1][1], t[1][2], t[1][3],
            t[2][0], t[2][1], t[2][2], t[2][3],
            0, 0, 0, 1,
          );
        }
        return m;
      };

      type Built = {
        c: CadportComponent;
        geom: any;
        isBox: boolean;
        mat4: any;
      };
      const built: Built[] = [];
      let meshes = 0;
      let boxes = 0;

      await Promise.all(
        components.map(async (c) => {
          const mat4 = placement(c.transform);
          if (c.stl_document_id != null) {
            try {
              const buf = await cadportAPI.fetchDocumentBuffer(
                c.stl_document_id,
              );
              const geom = loader.parse(buf);
              geom.computeVertexNormals();
              built.push({ c, geom, isBox: false, mat4 });
              meshes += 1;
              return;
            } catch {
              /* fall through to box */
            }
          }
          // AD-7 fallback box, half-size estimated from mass.
          const mkg = c.mass_kg ?? 1;
          const s = Math.cbrt(Math.max(mkg, 0.05)) * 0.06 + 0.04;
          const geom = new THREE.BoxGeometry(s * 2, s * 2, s * 2);
          built.push({ c, geom, isBox: true, mat4 });
          boxes += 1;
        }),
      );
      if (disposed) return;

      // ── Unit reconciliation. Transforms are in metres (SW API).
      // SW STL SaveAs exports geometry in the document's units, which
      // for these parts is typically millimetres → a 1000× mismatch
      // that would make every part overlap into one blob. Detect it:
      // if the median real-mesh size dwarfs the translation spread,
      // the meshes are mm — bake a 0.001 scale into the geometry so
      // geometry and placement share one unit. Boxes are already in
      // metres so they're excluded from the estimate.
      const tmpBox = new THREE.Box3();
      const sizes: number[] = [];
      for (const b of built) {
        if (b.isBox) continue;
        b.geom.computeBoundingBox();
        const sz = new THREE.Vector3();
        b.geom.boundingBox.getSize(sz);
        sizes.push(Math.max(sz.x, sz.y, sz.z));
      }
      const trans = built.map((b) => {
        const v = new THREE.Vector3();
        v.setFromMatrixPosition(b.mat4);
        return v;
      });
      let tspread = 0;
      for (let i = 0; i < trans.length; i++)
        for (let j = i + 1; j < trans.length; j++)
          tspread = Math.max(tspread, trans[i].distanceTo(trans[j]));
      let geoScale = 1;
      if (sizes.length) {
        sizes.sort((a, b) => a - b);
        const medSize = sizes[Math.floor(sizes.length / 2)];
        if (medSize > 8 * Math.max(tspread, 1e-6)) geoScale = 0.001;
      }

      // ── Materials + meshes.
      const matsMap = new Map<string, { mat: any; base: number }>();
      const pickMeshes: any[] = [];
      const group = new THREE.Group();
      for (const b of built) {
        if (geoScale !== 1 && !b.isBox)
          b.geom.scale(geoScale, geoScale, geoScale);
        const base = b.c.project_part_exists
          ? COLOR_IN_PROJECT
          : COLOR_MISSING;
        const mat = new THREE.MeshStandardMaterial({
          color: base,
          metalness: 0.1,
          roughness: 0.65,
          flatShading: b.isBox,
        });
        const mesh = new THREE.Mesh(b.geom, mat);
        mesh.applyMatrix4(b.mat4);
        mesh.userData.cadportId = b.c.cadport_part_id || b.c.instance_name;
        group.add(mesh);
        pickMeshes.push(mesh);
        if (b.c.cadport_part_id)
          matsMap.set(b.c.cadport_part_id, { mat, base });
      }
      scene.add(group);
      matsRef.current = matsMap;

      // ── Frame the camera on the assembly bounds.
      tmpBox.setFromObject(group);
      const center = new THREE.Vector3();
      const size = new THREE.Vector3();
      tmpBox.getCenter(center);
      tmpBox.getSize(size);
      const maxDim = Math.max(size.x, size.y, size.z) || 1;
      const dist = (maxDim / (2 * Math.tan((Math.PI * 45) / 360))) * 1.6;
      camera.position.set(
        center.x + dist * 0.8,
        center.y + dist * 0.6,
        center.z + dist * 0.9,
      );
      camera.near = Math.max(maxDim / 1000, 1e-4);
      camera.far = dist * 100;
      camera.updateProjectionMatrix();
      controls.target.copy(center);
      controls.update();

      // ── Click-to-identify.
      const raycaster = new THREE.Raycaster();
      const ndc = new THREE.Vector2();
      const onClick = (ev: MouseEvent) => {
        const r = renderer.domElement.getBoundingClientRect();
        ndc.x = ((ev.clientX - r.left) / r.width) * 2 - 1;
        ndc.y = -((ev.clientY - r.top) / r.height) * 2 + 1;
        raycaster.setFromCamera(ndc, camera);
        const hit = raycaster.intersectObjects(pickMeshes, false)[0];
        onSelectRef.current(hit ? hit.object.userData.cadportId : null);
      };
      renderer.domElement.addEventListener('click', onClick);
      cleanups.push(() =>
        renderer.domElement.removeEventListener('click', onClick),
      );

      ro = new ResizeObserver(() => {
        const w = mount.clientWidth || width;
        renderer.setSize(w, height);
        camera.aspect = w / height;
        camera.updateProjectionMatrix();
      });
      ro.observe(mount);

      const tick = () => {
        controls.update();
        renderer.render(scene, camera);
        raf = requestAnimationFrame(tick);
      };
      tick();

      setMeshCount(meshes);
      setBoxCount(boxes);
      setStatus('ready');

      cleanups.push(() => {
        for (const b of built) b.geom.dispose();
        for (const m of pickMeshes) m.material.dispose();
        scene.clear();
      });
    })().catch(() => {
      if (!disposed) setStatus('error');
    });

    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      ro?.disconnect();
      controls?.dispose?.();
      cleanups.forEach((fn) => fn());
      if (renderer) {
        renderer.dispose();
        renderer.domElement?.parentNode?.removeChild(renderer.domElement);
      }
    };
    // Rebuild only when the component set changes (transforms/ids).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [components, webgl]);

  // Re-highlight on selection change without rebuilding the scene.
  useEffect(() => {
    matsRef.current.forEach(({ mat, base }, id) => {
      const on = id === selected;
      mat.color.setHex(on ? 0xffffff : base);
      mat.emissive?.setHex(on ? 0x333333 : 0x000000);
    });
  }, [selected]);

  if (!webgl) return <>{fallback}</>;

  const sel =
    components.find((c) => c.cadport_part_id === selected) ?? null;

  return (
    <div className="rounded-xl border border-astra-border bg-astra-surface p-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wide text-slate-500">
          Assembly geometry — SolidWorks STL, placed by component transforms
        </span>
        <span className="text-[10px] text-slate-600">
          {meshCount} mesh{meshCount === 1 ? '' : 'es'}
          {boxCount > 0 && ` · ${boxCount} box fallback`} · orbit / zoom
        </span>
      </div>
      <div className="relative">
        <div
          ref={mountRef}
          className="w-full overflow-hidden rounded-lg"
          style={{ height: 420, background: '#0f1724' }}
        />
        {status === 'loading' && (
          <div className="absolute inset-0 flex items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-blue-500" />
          </div>
        )}
        {status === 'error' && (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-red-300">
            Failed to load assembly geometry
          </div>
        )}
        {sel && (
          <div className="pointer-events-none absolute left-3 top-3 rounded-lg border border-astra-border bg-astra-surface-alt/95 px-3 py-2 text-xs shadow-lg">
            <div className="font-semibold text-slate-100">
              {sel.display_name}
            </div>
            <div className="mt-1 space-y-0.5 font-mono text-[11px] text-slate-400">
              <div>WPN: {sel.wpn ?? '—'}</div>
              <div>mass: {fmt(sel.mass_kg, 4)} kg</div>
              <div>material: {cleanMaterial(sel.material)}</div>
              <div>
                mesh: {sel.stl_document_id != null ? 'STL' : 'box (no mesh)'}
              </div>
              <div
                className={
                  sel.project_part_exists
                    ? 'text-green-400'
                    : 'text-amber-400'
                }
              >
                {sel.project_part_exists
                  ? 'in project'
                  : 'not added to project'}
              </div>
            </div>
          </div>
        )}
      </div>
      <div className="mt-2 flex items-center gap-4 text-[10px] text-slate-500">
        <span className="flex items-center gap-1">
          <span
            className="inline-block h-2.5 w-2.5 rounded-sm"
            style={{ background: '#3FB950' }}
          />{' '}
          in project
        </span>
        <span className="flex items-center gap-1">
          <span
            className="inline-block h-2.5 w-2.5 rounded-sm"
            style={{ background: '#D29922' }}
          />{' '}
          not added
        </span>
        <span className="text-slate-600">click a part to identify</span>
      </div>
    </div>
  );
}
