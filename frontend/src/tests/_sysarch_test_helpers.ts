// Helper factored out of the page component so the unit test can
// exercise it without rendering the whole tree. Mirrors the function
// inline in
// frontend/src/app/projects/[id]/system-architecture/page.tsx.

interface SysLite {
  id: number;
  parent_system_id: number | null;
}

export function computeHierarchyDepthForTest(systems: SysLite[]): number {
  if (!systems.length) return 0;
  const byId = new Map<number, SysLite>();
  for (const s of systems) byId.set(s.id, s);
  const depthOf = (sys: SysLite, seen: Set<number>): number => {
    if (sys.parent_system_id == null) return 1;
    if (seen.has(sys.id)) return 1;
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
