# §10 — CITADEL Integration API (as built)

**Status:** AS-BUILT REFERENCE — documents only what is implemented in `backend/app/` as of 2026-06-10.
**Audience:** the Python GUI team and the CITADEL-side bundle consumer. This is the fixed API surface both build against.

Sources of truth (read these, not your memory): `app/routers/engineering_{frame,motors,aero,configs}.py`, `app/routers/{catalog,cadport,harold}.py`, `app/services/engineering/*`, `app/services/harold_naming/*`.

---

## Table of contents

1. [Overview & conventions](#1-overview--conventions)
2. [Frame ICD](#2-frame-icd)
3. [Motors](#3-motors)
4. [Aero decks](#4-aero-decks)
5. [Configurations](#5-configurations)
6. [Bundle export](#6-bundle-export)
7. [Catalog (+role)](#7-catalog-role)
8. [Appendix — HAROLD naming service](#8-appendix--harold-naming-service)

---

## 1. Overview & conventions

### 1.1 Base URL

```
http://<host>:8000/api/v1
```

All ASTRA routes below are relative to that prefix (`API_PREFIX = "/api/v1"` in `app/main.py`). HAROLD's own surface (appendix §8) lives elsewhere, at `http://<host>:8030/api/tools/wardstone-harold`.

### 1.2 Authentication

Bearer JWT. Obtain a token via **`POST /api/v1/auth/login`** with an **OAuth2 form body** (`application/x-www-form-urlencoded`, fields `username` and `password` — NOT JSON):

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=mason&password=<password>"
# → {"access_token": "<jwt>", "token_type": "bearer"}
```

```python
import requests
BASE = "http://localhost:8000/api/v1"
tok = requests.post(f"{BASE}/auth/login",
                    data={"username": "mason", "password": "<password>"}).json()
H = {"Authorization": f"Bearer {tok['access_token']}"}
```

Send `Authorization: Bearer <access_token>` on every call. The login response also sets an httpOnly refresh cookie; `POST /auth/refresh` rotates it. `POST /auth/logout` (204) revokes the token's `jti`.

**RBAC:** every engineering read requires any authenticated user. Every engineering **write** (motor ingest/design, aero ingest, config create/revise/clone, bundle export, active-revision selection, catalog role PATCH) requires role `admin`, `project_manager`, or `requirements_engineer` — otherwise **403** with `detail: "Insufficient permissions: …"`.

### 1.3 Error envelope conventions

* Default FastAPI shape: `{"detail": "<string>"}` (404, 403, 409, plain 422s, 503).
* **Structured 422s** put an object in `detail`:
  * Configs validation: `{"detail": {"message": "config validation failed", "errors": [ {code, message, ...}, ... ]}}` (§5.4).
  * Aero deck validation: `{"detail": {"message": "<reason>", "points": [ ... ]}}` — `points` present only for grid/merge conflicts (§4.3).
  * Bundle export: `{"detail": {"message": "<reason>", ...context}}` (e.g. `wpn` of the offending component).
* **503 Service Unavailable** always means **the HAROLD naming authority is unreachable or disabled** (`HAROLD_INTEGRATION_ENABLED=false` behaves identically). There is **no fallback** for the engineering domains — retry when HAROLD is back. Detail string starts with `"HAROLD naming authority unavailable"`.
* 401: missing/invalid/revoked token (`{"detail": "Could not validate credentials"}`).

### 1.4 WPN format

```
WS-<SYS>-P<NNNNNN>-<REV>
```

* `SYS` — 2–3 uppercase letters. Engineering system codes (registered dynamically with HAROLD, category `engineering`): **`MTR`** (Solid Motors), **`AER`** (Aero Decks), **`CFG`** (Vehicle Configurations).
* `NNNNNN` — zero-padded six-digit base index, 1..999999. **HAROLD is the only source of indices**; ASTRA never computes one. Sequences are sequential and gapless per system code.
* `REV` — single revision letter from the **ASME Y14.35 alphabet `ABCDEFGHJKLMNPRTUVWY`** (skips I O Q S X Z, enforced by HAROLD). A revision keeps the base index and bumps the letter (`…-P000004-A` → `…-P000004-B`). Exhausting `Y` is a 409 from HAROLD ("issue a new part number").
* Revisions are **immutable rows** in every engineering domain: there are no update endpoints; new data ⇒ new HAROLD `-REV` ⇒ new row.
* Identity vs revision WPN: aero decks and configs store the **base** WPN (`WS-CFG-P000001`) on the identity and the full WPN (`WS-CFG-P000001-A`) on each revision; lookups by either form work (the routers strip a trailing revision token). Motors store HAROLD's first issued WPN verbatim (including `-A`) as the motor identity `wpn` — use the `wpn` returned by the API.

### 1.5 Component role taxonomy

Closed set, identical in three places (catalog column, config schema, bundle schema) and exchanged verbatim with CADPORT:

```
oml | structure | avionics | payload | propulsion | recovery | ballast | other
```

`oml` flags the airframe (outer mold line) part. Source constants: `app/models/catalog.py::CATALOG_PART_ROLE_TAXONOMY`, `app/schemas/engineering_config.py::ComponentRole`, `app/services/engineering/bundle_schema.py::Role`.

### 1.6 Determinism conventions

Canonical JSON everywhere = `json.dumps(obj, sort_keys=True, separators=(",", ":"))` (bundle manifests additionally use `ensure_ascii=False, allow_nan=False`). All content addressing is lowercase-hex sha256 over canonical JSON bytes.

---

## 2. Frame ICD

The CITADEL Vehicle Body Frame definition every numeric surface references. Key: **`citadel-vehicle-body-frame`**. Not HAROLD-numbered. Revisions are immutable integers (1, 2, …).

Defaults (`app/services/engineering/frame.py`):

| field | default | note |
|---|---|---|
| `datum` | `OML_nose_tip` | **PARAMETERIZED — stakeholder unconfirmed.** A confirmed change lands as a new revision, never an edit. |
| `axes` | `x_fwd_y_right_z_down` | x forward (nose), y right, z down |
| `units` | `SI` | m, kg, kg·m² |
| `rules` | long-form text | one datum for CADPORT `referencePoint_m_B`, component `cg_m_B`, motor CG offsets after placement, aero `refPoint_m_B`; no secondary datums |

### Endpoints

| method | path | notes |
|---|---|---|
| GET | `/engineering/frame-icd/` | current ICD + current (highest-rev) revision; **404 until registered** |
| GET | `/engineering/frame-icd/revisions` | full immutable history, ascending rev |
| POST | `/engineering/frame-icd/` | idempotent ensure/register (returns **200**, not 201). Empty body `{}` registers/returns the canonical frame with defaults. Body fields (`datum`, `axes`, `units`, `rules`, `notes`, all optional) that **differ** from the current revision create a NEW revision at `current_rev + 1`. `null`/omitted = keep current value. |

Response (`FrameIcdResponse`):

```json
{
  "id": 1, "key": "citadel-vehicle-body-frame",
  "name": "CITADEL Vehicle Body Frame",
  "created_at": "...", "created_by_id": 1,
  "current_rev": 1,
  "revision": {
    "id": 1, "frame_icd_id": 1, "rev": 1,
    "datum": "OML_nose_tip", "axes": "x_fwd_y_right_z_down",
    "units": "SI", "rules": "...", "notes": null,
    "created_at": "...", "created_by_id": 1
  }
}
```

Note: the config tracker auto-registers the frame (with defaults) on the first config save (`get_or_register_default_frame`), so a config's `frame_icd_id`/`frame_icd_rev` stamp exists even if nobody ever POSTed here.

---

## 3. Motors

Mounted at `/engineering/motors`. System code `MTR`. Custom verbs use the literal-colon convention: `POST /engineering/motors:ingestCsv` (no slash before the colon).

### 3.1 Endpoints

| method | path | body | response |
|---|---|---|---|
| GET | `/engineering/motors` | — query: `q` (wpn/name ilike), `class` (motor class letter), `skip` (≥0), `limit` (1–200, default 50) | `[MotorListItem]` |
| GET | `/engineering/motors/{wpn}` | — | `MotorResponse` |
| GET | `/engineering/motors/{wpn}/summary` | — | `MotorSummarySheet` |
| GET | `/engineering/motors/{wpn}/revisions/{rev}` | — (`rev` = letter, case-insensitive) | `MotorRevisionDetail` |
| GET | `/engineering/motors/{wpn}/revisions/{rev}/artifact` | — | the raw `astra-motor-artifact/1.0` JSON, verbatim |
| POST | `/engineering/motors:ingestCsv` | multipart: `file` (CSV) | 201 `MotorIngestResponse` |
| POST | `/engineering/motors/{wpn}/revisions:from-csv` | multipart: `file` (CSV) | 201 `MotorIngestResponse` |
| POST | `/engineering/motors:previewDesign` | JSON `MotorDesignInputs` | 200 `DesignPreviewResponse` — solves only, **no persistence, no HAROLD call ever** |
| POST | `/engineering/motors:design` | JSON `{name, inputs, notes?}` | 201 `MotorIngestResponse` |
| POST | `/engineering/motors/{wpn}/revisions:from-design` | JSON `{inputs, notes?}` | 201 `MotorIngestResponse` |
| PUT | `/engineering/motors/{wpn}/active-revision` | JSON `{"rev_letter": "B"}` | `MotorResponse` — ASTRA-side pointer, no HAROLD call; also refreshes the linked catalog part's `mass_kg` to the selected revision's `PropMassInit_kg` and recomputes `motor_class` |

Writes: req-eng+ RBAC. All create/import paths go through HAROLD (503 when down). A malformed CSV is rejected (422) **before** any HAROLD allocation, so bad uploads never consume a ledger index.

### 3.2 CSV ingest flow (`:ingestCsv`)

1. sha256 the upload; decode UTF-8 (BOM tolerated) — non-UTF-8 ⇒ 422.
2. Parse + derive (422 `"Motor CSV ingest failed: …"` on unusable input).
3. **HAROLD filename precheck** — HAROLD decides the canonical display name (the uploader never names the motor). Returned verbatim in `precheck`.
4. Lineage: an existing motor with the same canonical name ⇒ HAROLD issues the next `-REV` of the **same** base index; otherwise a fresh `MTR` allocation (`allocate_and_persist`, gapless on failure). New motors also get a find-or-create `catalog_parts` row (in-house Wardstone supplier, `designation="solid_motor"`, `mass_kg = PropMassInit_kg`).
5. Post-commit `record_use` ledger annotation — **best-effort**: a HAROLD outage here does NOT fail the request; the failure is appended to the response `warnings` instead.

CSV format contract (`motor_ingest.py`; headers matched case/punctuation-insensitively — `"Thrust (N)"` ≡ `thrustn`):

| column kind | aliases (normalized) | unit |
|---|---|---|
| time (required) | `time, times, t, motortimes, timesec, timeseconds` | s |
| thrust (required) | `thrust, thrustn, forcen, fn, force` (N) / `thrustlbf, forcelbf, flbf, thrustlb, forcelb` (lbf, ×4.4482216152605) | N |
| propellant mass remaining | `masskg, propmasskg, propmassremkg, propellantmass, propmassrem, propellantmasskg, propmassremaining` | kg |
| chamber pressure | `pc, pchamberpa, chamberpressurepa, pcpa, chamberpressure, pchamber` (Pa) / `pcpsi, chamberpressurepsi, pchamberpsi` (psi, ×6894.757293168) | Pa |
| nozzle ṁ (cross-check only) | `mdot, mdotkgps, nozzlemdotkgps, nozzlemdot` | kg/s |
| per-grain mass | header or metadata key matching `grain(?:mass)?(\d+)(?:mass)?(?:kg)?` e.g. `GrainMass_3` | kg |

Metadata rides as `# key, value` / `# key: value` comment lines or pre-header `key,value` rows. Total propellant mass keys: `propellantmass, propmasskg, totalpropmass, propmass, propellantmasskg, totalpropellantmasskg, totalpropmasskg`. Grain-mass row-sum is authoritative for total propellant mass (multi-segment first-class). Header row = first row containing a time alias plus ≥1 other alias. Time base shifted to t=0; non-increasing samples dropped with a warning. Burnout tail trimmed at 0.5 % of peak thrust; everything resampled to a uniform 1 kHz grid.

ṁ rule: derived `d(PropMassRem)/dt` (central differences, clamped ≤ 0) is ALWAYS the artifact's ṁ; a nozzle-flow column is a cross-check only (>5 % integral discrepancy ⇒ warning, derived preferred). No mass series ⇒ constant-Isp fallback (`Isp = ∫F dt/(m·g0)`, `ṁ = −F/(Isp·g0)`), which caps the tier at `workable`.

### 3.3 `qualityTier` semantics

| tier | when |
|---|---|
| `excellent` | thrust + mass time-series + chamber pressure all present, all cross-checks pass (mass-burn ≤ 2 %, nozzle-flow ≤ 5 %, raw-vs-resampled impulse ≤ 2 %), AND total propellant mass independently confirmed (grain-mass row-sum or explicit metadata). All design-origin revisions are `excellent`. |
| `good` | minor defaults only — e.g. `PropMassInit_kg` inferred from the first mass sample. |
| `workable` | constant-Isp fallback used, OR chamber pressure missing, OR any cross-check failed. |

`recommended_fidelity` = `"HiFi"` iff tier is `excellent`, else `"Nominal"`. Geometry a bare CSV can never provide (CG offset, inertias, nozzle areas, grain-stack length, σp temperature grid) is always zero-defaulted for csv-origin revisions, listed in `defaultedFields`, and does NOT affect the tier.

### 3.4 Normalized motor artifact — `astra-motor-artifact/1.0`

Returned verbatim by `GET …/revisions/{rev}/artifact` and baked into bundles as `artifacts/<sha256>.motor.json`. All series share the uniform 1 kHz `MotorTime_s` grid (`Ts_s = 0.001`). Content-addressed by sha256 over canonical JSON.

| field | type | unit | notes |
|---|---|---|---|
| `schema` | str | — | `"astra-motor-artifact/1.0"` |
| `MotorTime_s` | float[] | s | uniform grid, t=0 first sample, burnout-trimmed |
| `Thrust_N` | float[] | N | |
| `Mdot_kgps` | float[] | kg/s | **NEGATIVE by convention** (mass leaving) |
| `PropMassRem_kg` | float[] | kg | |
| `PropMassInit_kg` | float | kg | scalar |
| `Pchamber_Pa` | float[] | Pa | zeros + defaulted when CSV had no pressure |
| `PropCGOffset_m_B` | float[] | m | time series, body frame; zeros for csv origin |
| `PropInertiaAxial_kgm2` | float[] | kg·m² | zeros for csv origin |
| `PropInertiaTransverse_kgm2` | float[] | kg·m² | zeros for csv origin |
| `GrainStackLength_m` | float | m | 0.0 for csv origin |
| `BurnTime_s` | float | s | |
| `Ts_s` | float | s | always `0.001` |
| `AreaExit_m2` | float | m² | 0.0 for csv origin |
| `AreaThroat_m2` | float | m² | 0.0 for csv origin |
| `GrainTempGrid_K` | float[3] | K | always `[284.15, 294.15, 304.15]` (cold/nominal/hot) |
| `Thrust_N_byTgrain` | float[3][] | N | 3 rows on the grain-temp grid; csv origin replicates nominal (no σp) |
| `Mdot_kgps_byTgrain` | float[3][] | kg/s | ditto |
| `TotalImpulse_Ns` | float | N·s | |
| `PeakThrust_N` | float | N | |
| `Isp_s` | float | s | g0 = 9.80665 |
| `qualityTier` | str | — | `workable` \| `good` \| `excellent` (§3.3) |
| `defaultedFields` | str[] | — | artifact field names that were defaulted |
| `provenance` | obj | — | `{origin: "csv"|"design", author, createdUtc (ISO-8601 Z), wpn}` + exactly one of `designInputs` (design) / `csvSha256` (csv) |

Motor class letter: NAR/TRA doubling ladder from `TotalImpulse_Ns` (`1/8A` ≤ 0.3125 … `O` ≤ 40960, above ⇒ `"P+"`).

### 3.5 Design-input schema (`MotorDesignInputs`)

`extra="forbid"` — unknown keys are 422. Serialized verbatim into `motor_revisions.design_inputs` and `provenance.designInputs`.

```json
{
  "propellant": {
    "density_kgpm3": 1750.0,        // ρp, kg/m³ (>0)
    "a": 3.8e-5,                    // Saint-Robert coefficient, m/(s·Paⁿ) (>0)
    "n": 0.32,                      // burn-rate exponent, 0<n<1
    "k": 1.21,                      // γ, >1
    "Tc_K": 2900.0,                 // combustion temperature, K (optional*)
    "cstar_mps": 1500.0,            // characteristic velocity, m/s (optional*)
    "sigma_p": 0.0,                 // temperature sensitivity, 1/K (default 0)
    "molar_mass_kgpmol": 0.024      // exhaust molar mass, kg/mol (optional*)
  },
  "grain": {
    "type": "BATES",                // only BATES implemented (finocyl/endburner future)
    "od_m": 0.075, "core_d_m": 0.025, "length_m": 0.12,   // m; core_d_m < od_m
    "segment_count": 8,             // ≥1, identical segments — multi-segment first-class
    "inhibited_ends": 0             // 0|1|2 per segment
  },
  "nozzle": {
    "throat_d_m": 0.012,            // m (>0)
    "exit_d_m": 0.030,              // m (optional**)
    "expansion_ratio": 6.25,        // ε = Ae/At, >1 (optional**)
    "ambient_pressure_pa": 101325.0 // default 101325
  },
  "sim": {                          // optional block, defaults shown
    "web_step_m": 1e-4,
    "grain_temp_K": 294.15
  }
}
```

**Either-or rules (validated, 422 on violation):**

* `propellant` requires `cstar_mps` **OR** (`Tc_K` **AND** `molar_mass_kgpmol`) — so c\* = √(Rᵤ/M·Tc)/Γ is evaluable.
* `nozzle` requires `exit_d_m` **OR** `expansion_ratio`.

`DesignPreviewResponse` (from `:previewDesign`): `time_s, thrust_n, pchamber_pa, mdot_kgps` (sign-flipped to positive for plotting), `prop_mass_rem_kg, total_impulse_ns, peak_thrust_n, burn_time_s, isp_s, prop_mass_init_kg, motor_class, max_pchamber_pa, warnings[]`.

### 3.6 `MotorIngestResponse` (trimmed example)

```json
{
  "motor": {
    "id": 3, "wpn": "WS-MTR-P000003-A", "base_index": 3, "system_code": "MTR",
    "name": "WS01_HotFire_2", "motor_class": "M",
    "active_revision_id": 7, "catalog_part_id": 42,
    "created_at": "...", "updated_at": "...",
    "revisions": [
      {"id": 7, "wpn": "WS-MTR-P000003-A", "rev_letter": "A", "origin": "csv",
       "total_impulse_ns": 7421.5, "peak_thrust_n": 2210.0, "burn_time_s": 4.61,
       "isp_s": 214.2, "quality_tier": "excellent",
       "artifact_sha256": "9f…", "created_utc": "...", "notes": null}
    ]
  },
  "wpn": "WS-MTR-P000003-A",
  "rev_letter": "A",
  "quality_tier": "excellent",
  "recommended_fidelity": "HiFi",
  "warnings": [],
  "defaulted_fields": [],
  "precheck": { "...HAROLD filename-precheck verdict, verbatim (": ":ingestCsv only)" }
}
```

`MotorRevisionDetail` adds `design_inputs`, `source_csv_filename`, `source_csv_sha256`, `defaulted_fields`, `warnings` to the summary. `MotorSummarySheet`: `{wpn, name, motor_class, rev_letter, origin, quality_tier, total_impulse_ns, peak_thrust_n, burn_time_s, isp_s, prop_mass_init_kg, revision_count}`.

---

## 4. Aero decks

Mounted under `/engineering` (paths under `/aero`). System code `AER`. No `catalog_parts` row — decks are engineering data products, not procurable parts.

### 4.1 Endpoints

| method | path | body | response |
|---|---|---|---|
| GET | `/engineering/aero` | query: `q` (wpn/name/oml_wpn), `skip`, `limit` (≤200) | `[AeroDeckSummary]` |
| GET | `/engineering/aero/{wpn}` | `wpn` = base WPN or any revision's full WPN | `AeroDeckDetail` |
| GET | `/engineering/aero/{wpn}/revisions/{rev}` | `rev` = letter or full WPN | `AeroDeckRevisionDetail` (includes the full `deck` JSON) |
| GET | `/engineering/aero/{wpn}/revisions/{rev}/artifact` | — | the deck JSON verbatim, `Content-Disposition: attachment; filename="<wpn>.aero.json"` |
| GET | `/engineering/aero/{wpn}/preview?mach=&alpha=` | `alpha` in degrees | `AeroPreviewResponse` — bilinear interp of every table at (mach, alpha) on the beta/delta slice nearest 0, **current revision**; outside the validity envelope ⇒ 422 |
| POST | `/engineering/aero:ingestSource` | multipart (below) | 201 `AeroIngestResponse` |
| POST | `/engineering/aero/{wpn}/revisions:from-source` | multipart (same minus `name`) | 201 `AeroIngestResponse` |
| PUT | `/engineering/aero/{wpn}/active-revision` | JSON `{"rev_letter": "B"}` (letter or full WPN) | `AeroDeckDetail` |

Ingest multipart form fields: `files` (1..N CSVs, **required**), `name` (optional fallback hint only — HAROLD's precheck decides the canonical name), `oml_wpn`, `sref_m2`, `lref_m`, `ref_point_m_b` ("3 floats, comma/space separated"), `notes`.

Auto-name flow: HAROLD precheck on the first filename → if the canonical name (or a precheck-matched WPN) matches an existing deck, the upload lands as that deck's **next revision** (`is_new_deck: false`); otherwise a fresh `AER` WPN via `allocate_and_persist`. Revision path inherits `Sref_m2`/`Lref_m` from the previous revision when not supplied (recorded in `defaulted_fields`). 409 on persistence uniqueness conflicts (WPN already released back to HAROLD). `record_use` post-commit is **best-effort** (logged, never fails the request, NOT surfaced in warnings).

### 4.2 Ingest CSV format contract (long-form coefficient CSV)

One row per (mach, alpha[, beta][, delta]) point. DATCOM `.out` is declared-future: rejected 422 `"format not yet supported: datcom"`. Headers normalized by lowercasing + stripping all non-alphanumerics, then matched against alias sets:

| axis | aliases | |
|---|---|---|
| `mach` | `mach`, `M` | required |
| `alpha_deg` | `alpha_deg`, `alpha`, `aoa_deg`, `aoa` | required |
| `beta_deg` | `beta_deg`, `beta` | optional, default breakpoint `[0.0]` |
| `delta_deg` | `delta_deg`, `delta` | optional (control), default `[0.0]` |

| coeff | aliases |
|---|---|
| `CA` | `ca`, `cx_axial`, `caxial` |
| `CN` | `cn`, `cnormal` |
| `CY` | `cy` |
| `Cl` | `cl`, `cll`, `c_roll` |
| `Cm` | `cm`, `cpm` |
| `Cn` (yaw moment) | `cn_yaw`, `cln`, `c_yaw` |

**Cn-yaw disambiguation rule (deliberate):** a bare `cn`/`CN` header is ALWAYS the normal-force coefficient CN; the yaw-moment Cn MUST be spelled `cn_yaw`, `cln`, or `c_yaw` (header matching is case-insensitive, so capitalization cannot disambiguate). A bare `cl`/`Cl` is ALWAYS roll moment (no lift coefficient in body axes here). Control derivatives: any header normalizing to `<coeff-alias>delta` (`CN_delta`, `cm_delta`, `cn_yaw_delta`, …) becomes table `<Canonical>_delta`. Unrecognized columns are ignored with a warning; two columns mapping to the same role are a 422.

Comment metadata `# key: value`: `Sref_m2`, `Lref_m`, `refPoint_m_B` (3 floats), `omlWpn`. Unknown `# key: value` keys are preserved verbatim in the deck's `extensions` block (aero-team extensibility hook). Precedence: **form fields override comment metadata**; comment metadata is first-wins across multiple sources (mismatch ⇒ warning).

**Mandatory:** `Sref_m2` and `Lref_m` must resolve from form fields or comments — otherwise 422 `"mandatory reference metadata missing: …"`. `refPoint_m_B` defaults to `[0,0,0]` (recorded in `defaulted_fields`).

### 4.3 Merge + grid semantics

* Sources are unioned point-by-point. The same grid point with the same coefficient differing by **> 1e-9** ⇒ 422 `AeroMergeConflictError` with `points: [{mach, alpha_deg, beta_deg, delta_deg, coefficient, values, sources}]`. Duplicates within tolerance dedup silently.
* Breakpoints = sorted unique values per axis; tables are nested lists in axes order `["mach","alpha_deg","beta_deg","delta_deg"]`.
* Ragged input → 1-D linear interpolation onto the full lattice (alpha axis first, then mach, beta, delta; repeated to fixpoint) with a warning; unfillable cells ⇒ 422 `AeroGridError` listing the missing points.

### 4.4 Deck schema — `astra-aero-deck/1.0`

```json
{
  "schema": "astra-aero-deck/1.0",
  "omlWpn": "WS-MH-P000123-A",
  "Sref_m2": 0.00785,
  "Lref_m": 0.1,
  "refPoint_m_B": [0.0, 0.0, 0.0],
  "frame": "citadel-vehicle-body-frame",
  "axes": ["mach", "alpha_deg", "beta_deg", "delta_deg"],
  "breakpoints": {"mach": [...], "alpha_deg": [...], "beta_deg": [0.0], "delta_deg": [0.0]},
  "tables": {"CA": [[[[...]]]], "CN": ..., "Cm": ..., "CN_delta": ...},
  "derived": {
    "CNalpha_per_deg": [...per mach, may contain null...],
    "Cmalpha_per_deg": [...],
    "alpha_ref_deg": 0.0,
    "staticMargin_proxy": [...]
  },
  "validityEnvelope": {
    "machRange": [m_min, m_max],
    "alphaRange_deg": [a_min, a_max],
    "betaRange_deg": [b_min, b_max]
  },
  "units": "SI/deg",
  "provenance": {
    "sourceFiles": [{"filename": "...", "sha256": "..."}],
    "ingestUtc": "...", "author": "...", "wpn": "WS-AER-P000001-A"
  },
  "extensions": { "any unrecognized # key: value, verbatim": "..." }
}
```

`derived`: CNalpha/Cmalpha per Mach via central differences over alpha at the alpha breakpoint nearest 0° on the beta/delta slice nearest 0 (needs ≥2 alphas; skipped otherwise); `staticMargin_proxy = -Cmalpha/CNalpha` in Lref units (null per Mach where CNalpha ≈ 0; block omitted when either derivative unavailable). Content hash = sha256 over canonical JSON of the whole deck (after the HAROLD WPN is stamped into `provenance.wpn`).

### 4.5 `AeroIngestResponse`

```json
{
  "deck_id": 2, "deck_wpn": "WS-AER-P000002", "wpn": "WS-AER-P000002-B",
  "rev_letter": "B", "name": "ws01_oml_deck", "deck_sha256": "ab…",
  "is_new_deck": false,
  "envelope": {"mach_min": 0.1, "mach_max": 3.0, "alpha_min_deg": -10.0, "alpha_max_deg": 10.0},
  "warnings": [], "defaulted_fields": ["refPoint_m_B"]
}
```

---

## 5. Configurations

Mounted under `/engineering/configs`. System code `CFG`. Save-time validation runs **before** any HAROLD allocation — an invalid config never burns a ledger index.

### 5.1 Endpoints

| method | path | body | response |
|---|---|---|---|
| GET | `/engineering/configs` | query `q`, `skip`, `limit` | `[ConfigSummary]` |
| GET | `/engineering/configs/{wpn}` | — | `ConfigDetail` |
| GET | `/engineering/configs/{wpn}/diff?from=A&to=B` | `from`/`to` = letter or full WPN | structured diff (§5.5) |
| GET | `/engineering/configs/{wpn}/revisions/{rev}` | — | `ConfigRevisionDetail` (the flight card, §5.6) |
| POST | `/engineering/configs` | `ConfigCreate` | 201 `ConfigCreateResponse` |
| POST | `/engineering/configs/{wpn}/revisions` | `ConfigRevisionCreate` (= create minus `name`) | 201 `ConfigCreateResponse` |
| POST | `/engineering/configs/{wpn}:clone` | `{"name": "..."}` — copies the latest revision's content verbatim into a NEW CFG identity | 201 `ConfigCreateResponse` (`is_new_config: true`) |
| PUT | `/engineering/configs/{wpn}/active-revision` | `{"rev_letter": "B"}` | `ConfigDetail` |
| POST | `/engineering/configs/{wpn}/{rev}:exportBundle` | — | 201 `BundleExportResponse` (§6) |
| GET | `/engineering/configs/{wpn}/{rev}/bundles` | — | `[BundleExportSummary]` (§6) |
| GET | `/engineering/configs/{wpn}/{rev}/bundles/{bundle_hash}/manifest` | — | stored manifest JSON (§6) |
| GET | `/engineering/configs/{wpn}/{rev}/bundles/{bundle_hash}/download` | — | bundle zip (§6) |

409 when revising/cloning a config with no revisions, or on persistence uniqueness conflict. `record_use` post-commit is best-effort (logged only).

### 5.2 Create / revise body

```json
{
  "name": "WS01 Flight 3 Config",            // create/clone only, 1..500 chars
  "description": "optional",
  "components": [
    {
      "role": "oml",                           // REQUIRED, closed set (§1.5)
      "wpn": "WS-MH-P000123-A",                // catalog internal_part_number, 1..64
      "rev": "A",                              // optional, ≤8; defaults from the WPN's trailing letter, else "A"
      "name": "optional override",             // defaults from the catalog
      "placement": [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]],  // optional 4×4 row-major homogeneous (CADPORT §6 transform_m); missing ⇒ identity
      "notes": null
    }
  ],
  "aero_binding": {"wpn": "WS-AER-P000002", "rev_letter": "B"},   // optional
  "stage_map": [
    {
      "stageNum": 1,                           // ≥1
      "motorWpn": "WS-MTR-P000003-A",
      "motorRevLetter": "A",
      "ignitionTime_s": 0.0,                   // default 0.0
      "thrustAxis_B": [1.0, 0.0, 0.0],         // default [1,0,0]
      "mcTrialId": null                        // optional string
    }
  ],
  "top_assembly_wpn": null,                    // optional, ≤64
  "astra_baseline_id": null,                   // optional int
  "notes": null
}
```

### 5.3 Save-time validation (all checked before HAROLD)

1. every component `wpn` resolves in the catalog (`internal_part_number`, not soft-deleted);
2. at most one `role: "oml"` component; **exactly one when an aero deck is bound**;
3. the aero binding resolves AND the deck's `omlWpn` equals the `oml` component's WPN (when both present);
4. every stage-map motor wpn + rev letter resolves;
5. frame ICD stamped (idempotent ensure, commits independently);
6. mass-properties roll-up computable (every component has mass + CG in the catalog; parallel-axis about the frame datum `[0,0,0]`; missing inertia tensor tolerated as point mass + warning).

### 5.4 Validation error codes (422 `{message: "config validation failed", errors: [...]}`)

| `code` | extra fields | meaning |
|---|---|---|
| `unknown_component_wpn` | `wpn` | component WPN not in catalog / deleted |
| `multiple_oml_components` | `wpns` | more than one `oml` role |
| `missing_oml_component` | — | aero bound but no `oml` component |
| `unknown_aero_deck` | `wpn`, `rev_letter` | aero binding does not resolve |
| `oml_aero_mismatch` | `deck_oml_wpn`, `component_oml_wpn` | deck is for a different OML |
| `unknown_motor` | `stageNum`, `motorWpn`, `motorRevLetter` | stage motor does not resolve |
| `empty_bom` | — | no components |
| `rollup_not_computable` | `wpn` (per part) or none (zero total mass) | part lacks mass or CG / Σm ≤ 0 |
| `bad_placement` | `wpn` | placement matrix unparseable (not 4×4 / 3×4 / 3×3) |

Every entry also carries a human-readable `message`.

### 5.5 Diff response (`GET …/diff?from=&to=`)

```json
{
  "config_wpn": "WS-CFG-P000001",
  "from_rev": "A", "to_rev": "B",
  "components": {
    "added":   [ {component dict} ],
    "removed": [ {component dict} ],
    "changed": [
      {"wpn": "WS-MH-P000123-A",
       "fields": ["rev", "placement", "role"],          // subset that changed
       "from": {"rev": "A", "placement": null, "role": "structure"},
       "to":   {"rev": "B", "placement": [[...]], "role": "structure"}}
    ]
  },
  "aero_binding": {"from": {...}, "to": {...}},          // null when unchanged
  "stage_map": {"added": [...], "removed": [...],
                "changed": [{"stageNum": 1, "from": {...}, "to": {...}}]},
  "rollup_delta": {"totalMass_kg": -0.45, "cg_m_B": [0.01, 0.0, 0.0]}
}
```

### 5.6 Flight card (`ConfigRevisionDetail`)

```json
{
  "id": 5, "wpn": "WS-CFG-P000001-B", "rev_letter": "B",
  "config_wpn": "WS-CFG-P000001", "config_name": "WS01 Flight 3 Config",
  "description": null, "top_assembly_wpn": null,
  "frame_icd_id": 1, "frame_icd_rev": 1,
  "astra_baseline_id": null,
  "components": [ {role, wpn, rev, name, placement, notes} ],
  "aero_binding": {"wpn": "...", "rev_letter": "B"},
  "stage_map": [ {stageNum, motorWpn, motorRevLetter, ignitionTime_s, thrustAxis_B, mcTrialId} ],
  "rollup": {
    "totalMass_kg": 12.34,
    "cg_m_B": [0.81, 0.0, 0.0],
    "inertia_kgm2_B": [[...],[...],[...]],
    "referencePoint_m_B": [0.0, 0.0, 0.0],
    "method": "parallel_axis"
  },
  "validation": {"warnings": ["component ... treated as a point mass ..."]},
  "notes": null, "created_utc": "..."
}
```

`ConfigCreateResponse`: `{config_id, config_wpn, wpn (full revision WPN, verbatim), rev_letter, name, rollup, validation, is_new_config}`.

---

## 6. Bundle export

`POST /engineering/configs/{wpn}/{rev}:exportBundle` renders an immutable config revision into a **`citadel-config-bundle/1.0`** directory + zip and records a `config_bundle_exports` row. req-eng+ RBAC. 422 (`{message, ...context}`) when a referenced component YAML / aero deck / motor revision no longer resolves.

### 6.1 Bundle directory layout

```
<exports-root>/
  <configWpn>_<configRev>_<bundleHash8>/        # e.g. WS-CFG-P000001_B_3fa9c2d1
    manifest.json                               # canonical JSON bytes
    artifacts/
      <sha256>.massprops.yaml                   # per component: CADPORT §6 YAML, verbatim bytes
      <sha256>.aero.json                        # canonical JSON of the bound deck revision
      <sha256>.motor.json                       # canonical JSON of each stage's motor artifact
  <configWpn>_<configRev>_<bundleHash8>.zip     # sibling zip of the same content
```

Exports root: `$CITADEL_BUNDLE_DIR` if set, else `$UPLOAD_DIR/citadel_bundles` (`UPLOAD_DIR` defaults to `/tmp/astra_uploads`). Artifact filenames are content-addressed `<sha256>.<suffix>` with suffix ∈ `{massprops.yaml, motor.json, aero.json, mesh.glb}` (`mesh.glb` is reserved; not emitted by the current exporter). Identical sha256s are stored once (dedup). Zip is byte-stable: sorted arcnames, fixed (1980-01-01) timestamps, canonical-JSON manifest.

### 6.2 `manifest.json` contract — `citadel-config-bundle/1.0`

Strict (`extra="forbid"` on every block — unknown keys are a schema mismatch; a new field is a new schema version). camelCase, unit-suffixed. Source of truth: `app/services/engineering/bundle_schema.py` (CITADEL mirrors this module).

```json
{
  "schema": "citadel-config-bundle/1.0",
  "bundle": {
    "id": "<uuid4 hex>",
    "createdUtc": "<ISO-8601>",
    "createdBy": "<username>",
    "astraBaselineId": null,
    "astraBaselineRev": null,
    "bundleHash": "<64-hex sha256>"
  },
  "config": {
    "wpn": "WS-CFG-P000001", "name": "...", "rev": "B",
    "description": null, "topAssemblyWpn": null
  },
  "frame": {
    "icdId": "citadel-vehicle-body-frame", "icdRev": 1,
    "datum": "OML_nose_tip", "axes": "x_fwd_y_right_z_down", "units": "SI"
  },
  "massProperties": {
    "totalMass_kg": 12.34,
    "cg_m_B": [0.81, 0.0, 0.0],
    "inertia_kgm2_B": [[...],[...],[...]],
    "referencePoint_m_B": [0.0, 0.0, 0.0],
    "method": "parallel_axis"
  },
  "components": [
    {
      "role": "oml", "wpn": "WS-MH-P000123-A", "rev": "A", "name": "...",
      "mass_kg": 1.2, "cg_m_B": [...], "inertia_kgm2_B": [[...]],
      "placement": {"matrix4x4": [[...]]},          // null when identity
      "artifact": {
        "type": "mass_props_yaml",
        "file": "artifacts/<sha256>.massprops.yaml",
        "sha256": "<64-hex>", "sourceSystem": "CADPORT",
        "ingestUtc": "<ISO-8601>",
        "qualityTier": null, "origin": null, "designProvenanceId": null
      }
    }
  ],
  "aero": {                                          // null when no aero binding
    "wpn": "WS-AER-P000002", "rev": "B", "omlWpn": "WS-MH-P000123-A",
    "Sref_m2": 0.00785, "Lref_m": 0.1, "refPoint_m_B": [0,0,0],
    "validityEnvelope": {"machRange": [...], "alphaRange_deg": [...], "betaRange_deg": [...]},
    "artifact": {"type": "aero_deck", "file": "artifacts/<sha256>.aero.json",
                 "sha256": "...", "sourceSystem": "AstraAero", "ingestUtc": "..."}
  },
  "propulsion": [                                    // null when no stages
    {
      "stageNum": 1, "motorWpn": "WS-MTR-P000003-A", "motorRev": "A",
      "ignitionTime_s": 0.0, "thrustAxis_B": [1,0,0], "mcTrialId": null,
      "artifact": {"type": "motor_curve", "file": "artifacts/<sha256>.motor.json",
                   "sha256": "...", "sourceSystem": "AstraMotor",
                   "qualityTier": "excellent", "origin": "csv", "ingestUtc": "..."}
    }
  ],
  "recommendedFidelity": "HiFi",                     // "HiFi" iff every bound motor rev is 'excellent', else "Nominal"; null when no stages
  "dependencies": [
    {"wpn": "WS-MH-P000123-A", "rev": "A", "sha256": "<artifact sha256>"}
  ],
  "provenance": {
    "harold": {"systemCode": "CFG", "query": "WS-CFG-P000001", "total": 2,
               "entries": [{"wpn": "...", "revision": "B", "status": "active"}]},
    "astra": {"baselineId": null, "exportedBy": "mason", "exportedUtc": "..."}
  }
}
```

**Dependencies lock:** one entry per (wpn, rev, sha256) triple across components + aero + motors, deduplicated. This is the bundle's pin set — CITADEL verifies each `artifacts/<sha256>.*` file against it. `provenance.harold` is best-effort: HAROLD down at export time ⇒ `{}` plus a response warning (`"HAROLD ledger unavailable at export time …; provenance.harold omitted"`) — never fails the export.

### 6.3 Deterministic `bundleHash` rule (exactly as implemented)

`bundleHash` = sha256 of canonical JSON of the manifest with **these and only these** fields normalized (`bundle_export.compute_deterministic_bundle_hash`):

* `bundle.id` → `null`
* `bundle.createdUtc` → `null`
* `bundle.createdBy` → `null`
* `bundle.bundleHash` → `null`
* `provenance` (the **entire** block) → `null`

Everything else — config identity, frame, massProperties, components, aero, propulsion, `recommendedFidelity`, dependencies, and `bundle.astraBaselineId`/`astraBaselineRev` — is covered by the hash. Re-export of the same revision therefore yields the SAME `bundleHash` even though `createdUtc` and the provenance block differ, and idempotently **reuses** the recorded export row (`reused: true`; files re-rendered from the stored manifest only if the zip went missing on disk). `config_bundle_exports` is UNIQUE(config_wpn, rev_letter, bundle_hash).

> Verification note: `bundle_schema.compute_bundle_hash` (nulls only `bundle.bundleHash`) is a separate shared primitive and does NOT reproduce the stored `bundleHash`. To verify a bundle, apply the five-field normalization above, canonical-JSON, sha256, and compare with `bundle.bundleHash`.

### 6.4 Retrieval without re-export

* `GET /engineering/configs/{wpn}/{rev}/bundles` → export history: `[{id, config_wpn, rev_letter, bundle_hash, bundle_dirname, artifact_count, created_utc}]`.
* `GET …/bundles/{bundle_hash}/manifest` → the stored manifest JSON (served from the DB row; no disk access).
* `GET …/bundles/{bundle_hash}/download` → the zip (`application/zip`, filename `<bundle_dirname>.zip`). 404 with `"Bundle zip missing on disk … — re-export to regenerate"` when the file was deleted.

`BundleExportResponse` = `BundleExportSummary` + `{manifest, reused, warnings[]}`.

### 6.5 End-to-end example (login → ingest motor CSV → poll → export → download)

```bash
BASE=http://localhost:8000/api/v1
TOK=$(curl -s -X POST $BASE/auth/login -d "username=mason&password=PW" | jq -r .access_token)
AUTH="Authorization: Bearer $TOK"

# 1) Ingest a motor CSV (HAROLD names it; 503 = HAROLD down, retry later)
curl -s -X POST "$BASE/engineering/motors:ingestCsv" -H "$AUTH" \
  -F "file=@WS01_HotFire_2.csv" | jq '{wpn, rev_letter, quality_tier, warnings}'

# 2) Poll / read back
curl -s -H "$AUTH" "$BASE/engineering/motors/WS-MTR-P000003-A/summary" | jq
curl -s -H "$AUTH" "$BASE/engineering/motors/WS-MTR-P000003-A/revisions/A/artifact" > motor.json

# 3) Export the config bundle (idempotent — same revision => same bundle_hash)
curl -s -X POST -H "$AUTH" \
  "$BASE/engineering/configs/WS-CFG-P000001/B:exportBundle" \
  | jq '{bundle_hash, bundle_dirname, artifact_count, reused, warnings}'

# 4) Download without re-export
HASH=<bundle_hash from step 3>
curl -s -H "$AUTH" -o bundle.zip \
  "$BASE/engineering/configs/WS-CFG-P000001/B/bundles/$HASH/download"
```

```python
import requests
BASE = "http://localhost:8000/api/v1"
tok = requests.post(f"{BASE}/auth/login",
                    data={"username": "mason", "password": "PW"}).json()
H = {"Authorization": f"Bearer {tok['access_token']}"}

# ingest
with open("WS01_HotFire_2.csv", "rb") as f:
    r = requests.post(f"{BASE}/engineering/motors:ingestCsv",
                      headers=H, files={"file": ("WS01_HotFire_2.csv", f, "text/csv")})
r.raise_for_status()                 # 422 = bad CSV, 503 = HAROLD down (no index burned)
ing = r.json()
wpn = ing["wpn"]                     # e.g. WS-MTR-P000003-A

# poll
art = requests.get(f"{BASE}/engineering/motors/{wpn}/revisions/{ing['rev_letter']}/artifact",
                   headers=H).json()
assert art["schema"] == "astra-motor-artifact/1.0"

# export bundle
exp = requests.post(f"{BASE}/engineering/configs/WS-CFG-P000001/B:exportBundle",
                    headers=H).json()

# download
z = requests.get(f"{BASE}/engineering/configs/WS-CFG-P000001/B/bundles/"
                 f"{exp['bundle_hash']}/download", headers=H)
open(f"{exp['bundle_dirname']}.zip", "wb").write(z.content)
```

---

## 7. Catalog (+role)

Catalog router mounts at `/catalog`; the CADPORT bridge endpoints mount at the API root.

### 7.1 `POST /catalog/parts/from-cadport` (the CADPORT import, incl. role)

201 `CatalogPartImportResult`. Idempotent on `content_hash` — a repeat returns the existing row with `deduped: true` and a `warning`, never a duplicate. Body (`CadportPartImport`), key fields:

| field | type | notes |
|---|---|---|
| `cadport_part_id` | str, required | §5 spine UUID |
| `content_hash` | str, required | `sha256:…` from the §6 YAML — the dedup key |
| `source_filename`, `display_name` | str, required | |
| `internal_part_number` | str? | HAROLD WPN (L6) → `catalog_part.internal_part_number` |
| `yaml_filename`, `yaml_content` | str, required | the §6 mass-props YAML, stored verbatim as a supplier document (this is the byte source for bundle `massprops.yaml` artifacts) |
| `mass_kg`, `volume_m3`, `surface_area_m2`, `density_kg_m3` | float | default 0.0 |
| `center_of_mass_m` | float[3] | default `[0,0,0]` |
| `inertia` | `{ixx,iyy,izz,ixy,ixz,iyz}` | defaults 0.0 |
| `material`, `configuration`, `solidworks_version` | str? | |
| `source_format` | str | `'sldprt'` \| `'step'`, default `'sldprt'` |
| `step_material_key`, `mass_source` | str? / str | `mass_source`: `'cad'` \| `'material'` \| `'user_override'` |
| `inertia_revised_via_uniform_scaling` | bool | default false |
| `stl_base64`, `stl_filename` | str? | optional mesh, best-effort |
| `source_files` | `[{kind, filename, sha256, content_base64}]` | `kind`: `'sldprt'`\|`'sldasm'`\|`'step'` |
| `supplier_id` XOR `supplier_name` | int? / str? | exactly one required (400 otherwise; 404 unknown id) |
| **`role`** | str? | one of the §1.5 taxonomy, carried verbatim from `cadport_parts.role`; **422 on a bad value**; `None` when the CADPORT operator never set one |

Result echoes `role` as persisted: `{catalog_part_id, cadport_part_id, part_number, name, supplier_id, supplier_name, internal_part_number, source_document_id, deduped, warning, supplier_created, role}`. A dedup hit returns the **existing** row's role (the incoming role is not applied).

There is also `POST /catalog/pending-imports/from-cadport` (same body shape, lands in the review queue) and `POST /catalog/parts/check-duplicate` (`{content_hash}` → match-or-null).

### 7.2 Parts list / detail — role exposure

* `GET /catalog/parts` (query: `q`, `supplier_id`, `part_class`, `lifecycle_status`, `skip`, `limit` ≤200) → `[CatalogPartSummary]`. **`role` is on the summary** so list views can badge airframe/role chips. There is no `role` query filter.
* `GET /catalog/parts/{part_id}` → `CatalogPartResponse` (extends the summary; includes `role`).

### 7.3 `PATCH /catalog/parts/{part_id}/role`

req-eng+ RBAC. Body: `{"role": "oml"}` — `null` (or empty string) **clears** the role; any non-null value must be in the taxonomy (422 listing the valid values). Pure metadata: no recompute cascade and **no propagation back to CADPORT in v1** (unlike mass/material/supplier/name sync).

Response: `{"part_id": 42, "role": "oml", "is_airframe": true}`.

```bash
curl -s -X PATCH -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"role": "oml"}' "$BASE/catalog/parts/42/role"
```

---

## 8. Appendix — HAROLD naming service

### 8.1 ASTRA-side guarantees (`app/services/harold_naming/`)

* **Sole authority.** Every engineering-domain WPN (MTR/AER/CFG) is HAROLD's response **verbatim**. ASTRA never computes, guesses, or fabricates an index or revision letter.
* **Sequential, gapless.** Allocation goes through `allocate_and_persist`: HAROLD issues → ASTRA persists → commit. On ANY persistence failure ASTRA rolls back and **releases** the WPN back to HAROLD (`DELETE /wpn/{wpn}`) so the sequence stays gapless. Revisions mirror the same release-on-failure pattern.
* **Orphan handling.** If the release itself also fails, ASTRA logs CRITICAL naming the orphan WPN and raises `HaroldOrphanWpnError` — the request fails loudly; manual reconciliation required; ASTRA never silently re-allocates.
* **No fallback.** The catalog's local fallback allocator is FORBIDDEN for engineering domains. HAROLD unreachable, or `HAROLD_INTEGRATION_ENABLED=false`, ⇒ **503** on every engineering create/revise path. Operationally: a 503 means stop and retry when HAROLD is back; nothing was created and no index was consumed.
* **Best-effort annotation.** `record_use` (PATCH metadata onto the ledger entry) runs AFTER successful local persistence; a HAROLD outage there never fails the request. Motors surface the failure in the response `warnings`; aero/configs log it only.
* System codes are auto-registered idempotently (`ensure_system_code`) before the first allocation per code, with name/description from `SYSTEM_CODE_REGISTRY` (MTR = "Solid Motors", AER = "Aero Decks", CFG = "Vehicle Configurations", category `engineering`).

For browser-facing HAROLD operations, prefer ASTRA's proxy at `/api/v1/harold/*` (heartbeat, system-codes, suggest, validate, validate-filename, parts/{id}/reconcile) — it always returns 200 with a `{harold_available, …}` discriminated envelope and applies ASTRA auth. The endpoints below are HAROLD's **own** surface, for tooling that needs direct ledger queries.

### 8.2 HAROLD's own endpoints (used by ASTRA / available to tooling)

Base: `http://<host>:8030/api/tools/wardstone-harold` (HAROLD V2 runs as a WRENCH plugin; no auth of its own — treat as trusted-network only).

| method | path | request | response / notes |
|---|---|---|---|
| POST | `/wpn/issue` | `{system_code, origin_system?, origin_record_id?, display_name?, description?, metadata?}` (metadata ≤ 4 KB JSON, else 413) | 201 ledger entry (below). Allocates the next sequential index for the code. |
| POST | `/wpn/{wpn}/revise` | optional `{origin_system?, origin_record_id?, display_name?, description?, metadata?}` | 201 NEW ledger row `WS-<SYS>-P<same index>-<nextRev>`; next letter = highest existing + 1 along ASME Y14.35 (`A…Y`, skipping I O Q S X Z); exhausting `Y` ⇒ 409; 404 when the base (sys, index) is unknown. Response includes `previous_wpn`. Prior revision row untouched. |
| POST | `/system-codes` | `{code, name, category, description?}` (+ `?actor=` query) | the registrar. 201 `created: true` for a new dynamic code (also seeds its `wpn_sequences` counter at 1); 200 `created: false` for an existing built-in or dynamic code (idempotent; re-registration never mutates the stored record). |
| GET | `/system-codes` | — | `{codes: [{code, category, name, description}], total}` — 21 built-ins ∪ dynamically registered codes (MTR/AER/CFG appear here with category `engineering`). |
| POST | `/filename-precheck` | `{filename, intended_project_id?, intended_part_class?}` | the precheck verdict ASTRA's ingest flows consume: `{filename, astra_available, is_collision, existing_document_id, iteration_stem, iteration_count, existing_iterations[], next_available_iteration, suggested_filename, wpn_suggestion, warnings[], errors[]}`. When ASTRA is unreachable from HAROLD: `{filename, astra_available: false, reason}`. Iteration tokens: `_v<d>`, `-v<d>`, `_<d>`, `(<d>)`. |
| GET | `/ledger` | query `system_code?`, `status?`, `q?` (substring on wpn/display_name/description), `skip` (≥0), `limit` (1–200, default 200) | `{items: [ledger entry], total, skip, limit}` |
| GET | `/ledger/{wpn}` | — | single ledger entry; 404 unknown |
| GET | `/ledger/export?format=csv` | — | full ledger as CSV stream |
| PATCH | `/wpn/{wpn}` | `{display_name?, description?, metadata?}` | metadata is merged server-side — this is what ASTRA's `record_use` calls (it sends `{"metadata": {kind, ...}}`) |
| DELETE | `/wpn/{wpn}` | optional body `{actor?, reason?}` | hard-delete + number reclaim when it is the highest index for its code (sequence rolls back over consecutive missing numbers). ASTRA uses this ONLY for failed-persistence release. |
| POST | `/wpn/validate` | `{wpn}` | `{wpn, is_valid_format, is_issued, errors[], warnings[], parsed?}` — `is_valid_format: false` is a normal result, not an error |
| GET | `/wpn/suggest?system_code=MTR` | — | next-available WPN preview (does NOT allocate) |

Ledger entry shape (`WpnLedgerEntryResponse`) — what ASTRA receives from issue/revise and stores from verbatim:

```json
{
  "id": 17, "wpn": "WS-MTR-P000003-B",
  "system_code": "MTR", "part_number_int": 3, "revision": "B",
  "origin_system": "astra", "origin_record_id": null,
  "display_name": "WS01_HotFire_2", "description": null,
  "metadata_json": {"source": "csv", "sha256": "...", "kind": "motor_revision"},
  "status": "active", "superseded_by": null,
  "issued_at": "...", "retired_at": null,
  "previous_wpn": "WS-MTR-P000003-A"        // revise responses only
}
```
