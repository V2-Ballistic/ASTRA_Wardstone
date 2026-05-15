# CADPORT-REBUILD-003 — Completion notes

TDD-3 of the CADPORT rebuild program. The ASTRA-side experience:
CADPORT assemblies are visible and interactive inside Mechanical
Interfaces — schematic CAD view, component breakdown, missing-part
detection (L8), full linkage navigation (L9). **Completes the
CADPORT rebuild program (TDD-1 → TDD-2 → TDD-3).**

**Status: shipped green. Phases 1–6 complete. ASTRA-only. Full
autonomous run.** Date: 2026-05-15. Live data: the Bloon Popper
assembly + 4 parts that TDD-2 imported.

---

## Commit ladder (ASTRA `V2-Ballistic/ASTRA_Wardstone`, main)

```
9852fec phase-1(cadport-rebuild-003): enrich cadport-assemblies for the UI
4379590 phase-2/3/4(cadport-rebuild-003): Assemblies tab + detail + iso view
f5c23d6 phase-5(cadport-rebuild-003): linkage visibility everywhere
<this>  phase-6(cadport-rebuild-003): E2E verification + completion notes
```

CADPORT / HAROLD repos: untouched (gotcha #6 — ASTRA-only TDD).

---

## What shipped, by phase

### Phase 1 — backend enrichment (no new endpoint, AD-6)

Extended the TDD-2 `GET /cadport-assemblies[/{id}]`:
- `CadportComponentResult` += wpn, display_name, mass_kg, material,
  transform (4×4 parsed from transform_json), part_yaml_document_id,
  **project_part_exists / project_part_id** (the L8 missing-parts
  signal).
- `CadportAssemblyResult` += project_name, content_hash,
  center_of_mass, solidworks_version, assembly_yaml_filename.
- `_assembly_result` batch-loads catalog_parts + the project's
  project_parts (2 queries, not 2N).

### Phase 2 — Assemblies tab + list (L9)

`Tab` union extended on `/projects/[id]/mechanical-interfaces`
(AD-1 — peer of overview/joints/parts-with-joints, same `?tab=`
URL pattern). `components/cadport/AssembliesTab.tsx` list view:
table (assembly / source_file / mass / components / SW), row →
detail, "Import Assembly" → CADPORT workspace, empty state. ASTRA
dark aesthetic (AD-5/8).

### Phase 3 — assembly detail + L8

Metadata card (mass, components, project, CG, content_hash,
assembly_id) + assembly-YAML download; amber missing-parts banner;
component breakdown table with WPN / mass / material / per-row
"In project" badge vs "Add to project" action. The action posts to
`POST /projects/{id}/parts/` (AD-3 — existing endpoint, **L8**),
re-fetches, the badge flips green and the iso component recolours.

### Phase 4 — schematic isometric view (AD-2/AD-7)

Pure-SVG isometric projection `x'=(x−z)cos30, y'=(x+z)sin30−y`
from the transform_json translation. Boxes sized from mass
(schematic — disclaimer shown), painter's-algorithm depth sort,
3-face shaded cubes. Hover/select → tooltip (name, WPN, mass,
material, project status); green = in-project, amber = missing;
legend.

### Phase 5 — linkage visibility

Two targeted additive endpoints (AD-6):
- `GET /catalog/parts/{id}/cadport` → is_cadport, cadport_part_id,
  content_hash, wpn, yaml_document_id, solidworks_version,
  imported_at, every assembly the part is in.
- `GET /projects/{id}/cadport-part-ids` → {catalog_part_id:
  assembly_name} for the project-parts badges.

Catalog-part-detail page gains a "CADPORT extraction" section
(WPN / SW / imported / hash + §6 YAML download + "Appears in
assemblies" list, each deep-linking the Assemblies tab).
Project-parts BomLineCard gains a blue "CADPORT: <assembly>" pill
linking the Assemblies tab. YAML is one click away from the part
detail, the assembly detail, and the component table (AD-4 —
existing supplier_documents file route everywhere).

### Phase 6 — E2E

All 7 walkthrough steps verified against the live Bloon Popper
data (consolidated API run):

| Step | Result |
|------|--------|
| 1 Assemblies tab list | 2 bloon-popper rows for project 1 |
| 2 Assembly detail | 4 components, 23.076 kg, DEF-bloon-popper.yaml |
| 3 Iso view input | 4/4 components carry a 4×4 transform |
| 4 Component identity | WPN + mass + cleaned material per part |
| 5 L8 missing→add | add catalog_part 3 → project_part #1 → project_part_exists flips True; other 3 stay missing (both states demonstrable) |
| 6 Catalog-part linkage | part 4 → is_cadport, WPN WS-ST-P000002-A, yaml doc, 2 assemblies |
| 7 Project-parts badge map | {3,4,5,6 → bloon-popper} |

Frontend (Next dev, hot-reload): mechanical-interfaces,
catalog/parts/[id], projects/[id]/parts all compile clean (HTTP
200, no errors).

---

## Linkage model — program complete (CADPORT_REBUILD_PROGRAM.md §5)

| Link | TDD | Status |
|------|-----|--------|
| L1 part YAML ↔ Part | 1 | ✅ |
| L2 assembly YAML ↔ Assembly | 1 | ✅ |
| L3 assembly YAML → part YAMLs | 1 | ✅ |
| L4 Part ↔ catalog_part | 2 | ✅ |
| L5 Part ↔ Supplier (Wardstone) | 2 | ✅ |
| L6 Part ↔ HAROLD WPN | 2 | ✅ |
| L7 Assembly ↔ Project | 2 | ✅ |
| **L8 Part ↔ project_parts** | **3** | ✅ "Add to project" |
| **L9 Assembly ↔ Mech-Interfaces** | **3** | ✅ Assemblies tab |

The full spine is navigable end to end: project → Mechanical
Interfaces → Assemblies tab → assembly detail (iso view +
components) → catalog part detail (CADPORT section + YAML) → its
assemblies → back to the tab; project-parts page badges CADPORT
rows; YAML downloadable at every node.

---

## Known cosmetic follow-ups (non-blocking, carried from TDD-2)

- Two `bloon-popper` rows in the Assemblies list — TDD-2's E2E
  imported the assembly twice (two distinct extraction events,
  same content_hash, different assembly_id UUIDs). Honest, not a
  bug; a dedup-on-content_hash for assemblies (parts already dedup)
  would tidy the list. Out of TDD-3 scope (UI only).
- The schematic iso view sizes boxes from mass, not real geometry
  (AD-2 — we only have placement transforms, not BREP). Disclaimer
  is shown in-view.

## Standing-rule / gotcha audit

- AD-1 Assemblies tab as a peer in the existing page (not a new
  route): ✅.
- AD-2 schematic iso, disclaimer shown: ✅.
- AD-3 L8 via existing `POST /projects/{id}/parts/`: ✅ (no new
  endpoint).
- AD-4 YAML via existing supplier_documents file route: ✅.
- AD-6 backend changes targeted/additive, no parallel paths: ✅.
- AD-7 pure SVG (no Three.js — not in the bundle anyway): ✅.
- gotcha #1 tab pattern matched (?tab= + isTab + tablist): ✅.
- gotcha #6 CADPORT/WRENCH side untouched: ✅.
- gotcha #7 used the live TDD-2 data, no re-extract: ✅.
- gotcha #8 ASTRA dark aesthetic throughout: ✅.

No hard-stop conditions hit. The CADPORT rebuild program (TDD-1
extraction engine → TDD-2 ASTRA/HAROLD integration → TDD-3 ASTRA
experience) is complete.
