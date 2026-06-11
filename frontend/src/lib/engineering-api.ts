// ══════════════════════════════════════════════════════════════
//  ASTRA — Engineering API Client (Motors + Aero + Configs)
//  Typed Axios calls for /api/v1/engineering/* endpoints.
//
//  File: frontend/src/lib/engineering-api.ts
//  ASTRA_CONFIG_ECOSYSTEM_BUILD_SPEC §4/§5/§6/§8/§9.
//
//  Notes:
//    - Bearer auth is automatic (lib/api interceptor).
//    - Write ops require admin | project_manager |
//      requirements_engineer (backend RBAC); the UI mirrors this with
//      useHasRole(...) gating.
//    - HAROLD outages surface as 503 with a string `detail` — render
//      it via formatApiError so the user sees the real reason.
//    - Google-style `:verb` collection actions are literal path
//      suffixes (e.g. POST /engineering/motors:ingestCsv).
//    - Multipart: the shared axios instance defaults Content-Type to
//      application/json; we pass 'multipart/form-data' explicitly so
//      axios swaps in the correctly bounded form-data header (same
//      gotcha as catalogAPI.uploadStep).
// ══════════════════════════════════════════════════════════════

import api from './api';
import type {
  AeroDeckArtifact,
  AeroDeckDetail,
  AeroDeckRevisionDetail,
  AeroDeckSummary,
  AeroIngestResponse,
  AeroPreviewResponse,
  BundleExportResponse,
  BundleExportSummary,
  ConfigCreateBody,
  ConfigCreateResponse,
  ConfigDetail,
  ConfigDiff,
  ConfigRevisionCreateBody,
  ConfigRevisionDetail,
  ConfigSummary,
  DesignPreviewResponse,
  MotorArtifact,
  MotorDesignInputs,
  MotorIngestResponse,
  MotorListItem,
  MotorResponse,
  MotorRevisionDetail,
  MotorSummarySheet,
} from './engineering-types';

const BASE = '/engineering';

const MULTIPART = { headers: { 'Content-Type': 'multipart/form-data' } };

function enc(wpn: string): string {
  return encodeURIComponent(wpn);
}

/** Optional form fields for aero source ingest. */
export interface AeroIngestOptions {
  name?: string;
  oml_wpn?: string;
  sref_m2?: number;
  lref_m?: number;
  ref_point_m_b?: string;
  notes?: string;
}

/** Object-URL save of an authed blob response (same pattern as
 *  cadportAPI.downloadDocument / downloadConfigBundle). */
function saveBlob(data: BlobPart, filename: string): void {
  const url = window.URL.createObjectURL(new Blob([data]));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

/** Pull the server-suggested filename out of Content-Disposition. */
function dispositionFilename(headers: Record<string, unknown>): string | null {
  const cd = String(headers?.['content-disposition'] ?? '');
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
  return m ? decodeURIComponent(m[1]) : null;
}

function aeroForm(files: File[], opts?: AeroIngestOptions): FormData {
  const fd = new FormData();
  files.forEach((f) => fd.append('files', f));
  if (opts?.name) fd.append('name', opts.name);
  if (opts?.oml_wpn) fd.append('oml_wpn', opts.oml_wpn);
  if (opts?.sref_m2 !== undefined) fd.append('sref_m2', String(opts.sref_m2));
  if (opts?.lref_m !== undefined) fd.append('lref_m', String(opts.lref_m));
  if (opts?.ref_point_m_b) fd.append('ref_point_m_b', opts.ref_point_m_b);
  if (opts?.notes) fd.append('notes', opts.notes);
  return fd;
}

export const engineeringAPI = {

  // ══════════════════════════════════════
  //  §5 Motors — reads
  // ══════════════════════════════════════

  listMotors: (params?: {
    q?: string;
    class?: string;
    skip?: number;
    limit?: number;
  }) =>
    api.get<MotorListItem[]>(`${BASE}/motors`, { params }),

  getMotor: (wpn: string) =>
    api.get<MotorResponse>(`${BASE}/motors/${enc(wpn)}`),

  getMotorSummary: (wpn: string) =>
    api.get<MotorSummarySheet>(`${BASE}/motors/${enc(wpn)}/summary`),

  getMotorRevision: (wpn: string, rev: string) =>
    api.get<MotorRevisionDetail>(
      `${BASE}/motors/${enc(wpn)}/revisions/${enc(rev)}`,
    ),

  /** The §5.4 normalized `*.motor.json` artifact (big JSON — 1 kHz
   *  time series). */
  getMotorArtifact: (wpn: string, rev: string) =>
    api.get<MotorArtifact>(
      `${BASE}/motors/${enc(wpn)}/revisions/${enc(rev)}/artifact`,
    ),

  /** Stored source CSV of a csv-origin revision — authed blob fetch +
   *  object-URL save. 404s on design-origin revisions. */
  downloadMotorRevisionSource: async (wpn: string, rev: string) => {
    const res = await api.get(
      `${BASE}/motors/${enc(wpn)}/revisions/${enc(rev)}/source`,
      { responseType: 'blob' },
    );
    const filename = dispositionFilename(
      res.headers as Record<string, unknown>,
    ) ?? `${wpn}-${rev}-source.csv`;
    saveBlob(res.data as BlobPart, filename);
  },

  // ══════════════════════════════════════
  //  §5.2 Motors — CSV ingest (HAROLD names it)
  // ══════════════════════════════════════

  /** Drag-drop CSV → motor + HAROLD WPN + qualityTier + warnings.
   *  503 (with detail) when HAROLD is down. */
  ingestMotorCsv: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return api.post<MotorIngestResponse>(
      `${BASE}/motors:ingestCsv`, fd, MULTIPART,
    );
  },

  /** New CSV data for an EXISTING motor → next -REV, same base index. */
  addMotorRevisionFromCsv: (wpn: string, file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return api.post<MotorIngestResponse>(
      `${BASE}/motors/${enc(wpn)}/revisions:from-csv`, fd, MULTIPART,
    );
  },

  // ══════════════════════════════════════
  //  §5.3 Motors — parametric design
  // ══════════════════════════════════════

  /** Solver run WITHOUT persisting or naming — live design-page plots.
   *  Invalid inputs → 422 with a string detail. Never calls HAROLD. */
  previewMotorDesign: (inputs: MotorDesignInputs) =>
    api.post<DesignPreviewResponse>(`${BASE}/motors:previewDesign`, inputs),

  /** Create a NEW designed motor (HAROLD allocates the WPN). */
  createMotorDesign: (body: {
    name: string;
    inputs: MotorDesignInputs;
    notes?: string | null;
  }) =>
    api.post<MotorIngestResponse>(`${BASE}/motors:design`, body),

  /** Solver re-run for an EXISTING motor → next -REV. */
  addMotorRevisionFromDesign: (wpn: string, body: {
    inputs: MotorDesignInputs;
    notes?: string | null;
  }) =>
    api.post<MotorIngestResponse>(
      `${BASE}/motors/${enc(wpn)}/revisions:from-design`, body,
    ),

  /** Select the published revision (ASTRA-side pointer; no HAROLD). */
  setMotorActiveRevision: (wpn: string, rev_letter: string) =>
    api.put<MotorResponse>(
      `${BASE}/motors/${enc(wpn)}/active-revision`, { rev_letter },
    ),

  // ══════════════════════════════════════
  //  §6 Aero decks — reads
  // ══════════════════════════════════════

  listAeroDecks: (params?: { q?: string; skip?: number; limit?: number }) =>
    api.get<AeroDeckSummary[]>(`${BASE}/aero`, { params }),

  getAeroDeck: (wpn: string) =>
    api.get<AeroDeckDetail>(`${BASE}/aero/${enc(wpn)}`),

  getAeroDeckRevision: (wpn: string, rev: string) =>
    api.get<AeroDeckRevisionDetail>(
      `${BASE}/aero/${enc(wpn)}/revisions/${enc(rev)}`,
    ),

  /** The normalized `*.aero.json` deck, served verbatim. */
  getAeroDeckArtifact: (wpn: string, rev: string) =>
    api.get<AeroDeckArtifact>(
      `${BASE}/aero/${enc(wpn)}/revisions/${enc(rev)}/artifact`,
    ),

  /** Stored source file(s) of a deck revision — a single CSV, or a
   *  zip when the revision merged several sources. */
  downloadAeroRevisionSource: async (wpn: string, rev: string) => {
    const res = await api.get(
      `${BASE}/aero/${enc(wpn)}/revisions/${enc(rev)}/source`,
      { responseType: 'blob' },
    );
    const headers = res.headers as Record<string, unknown>;
    const ct = String(headers?.['content-type'] ?? '');
    const ext = ct.includes('zip') ? 'zip' : 'csv';
    const filename = dispositionFilename(headers)
      ?? `${wpn}-${rev}-source.${ext}`;
    saveBlob(res.data as BlobPart, filename);
  },

  /** Interpolated coefficients at (mach, alpha) on the current rev. */
  previewAeroDeck: (wpn: string, mach: number, alpha: number) =>
    api.get<AeroPreviewResponse>(`${BASE}/aero/${enc(wpn)}/preview`, {
      params: { mach, alpha },
    }),

  // ══════════════════════════════════════
  //  §6 Aero decks — ingest (HAROLD names it)
  // ══════════════════════════════════════

  /** Drag-drop 1..N coefficient CSVs → deck named + ingested
   *  automatically (new deck or next revision of a lineage match). */
  ingestAeroSource: (files: File[], opts?: AeroIngestOptions) =>
    api.post<AeroIngestResponse>(
      `${BASE}/aero:ingestSource`, aeroForm(files, opts), MULTIPART,
    ),

  /** Explicit new revision of an existing deck from fresh sources. */
  addAeroRevisionFromSource: (
    wpn: string,
    files: File[],
    opts?: AeroIngestOptions,
  ) =>
    api.post<AeroIngestResponse>(
      `${BASE}/aero/${enc(wpn)}/revisions:from-source`,
      aeroForm(files, opts),
      MULTIPART,
    ),

  setAeroActiveRevision: (wpn: string, rev_letter: string) =>
    api.put<AeroDeckDetail>(
      `${BASE}/aero/${enc(wpn)}/active-revision`, { rev_letter },
    ),

  // ══════════════════════════════════════
  //  §8 Configurations — reads
  // ══════════════════════════════════════

  listConfigs: (params?: { q?: string; skip?: number; limit?: number }) =>
    api.get<ConfigSummary[]>(`${BASE}/configs`, { params }),

  getConfig: (wpn: string) =>
    api.get<ConfigDetail>(`${BASE}/configs/${enc(wpn)}`),

  /** Full resolved revision incl. the stored roll-up — the on-screen
   *  flight card. `rev` may be a letter ('B') or a full WPN. */
  getConfigRevision: (wpn: string, rev: string) =>
    api.get<ConfigRevisionDetail>(
      `${BASE}/configs/${enc(wpn)}/revisions/${enc(rev)}`,
    ),

  /** Structured diff between two revisions (components added /
   *  removed / changed, aero / stage-map changes, roll-up delta). */
  diffConfigRevisions: (wpn: string, from: string, to: string) =>
    api.get<ConfigDiff>(`${BASE}/configs/${enc(wpn)}/diff`, {
      params: { from, to },
    }),

  // ══════════════════════════════════════
  //  §8 Configurations — writes (HAROLD names them)
  // ══════════════════════════════════════

  /** Validate → roll up → HAROLD allocates the CFG WPN → revision A.
   *  Save-time validation failures arrive as 422 with a structured
   *  {message, errors:[{code,...}]} detail — render each error. */
  createConfig: (body: ConfigCreateBody) =>
    api.post<ConfigCreateResponse>(`${BASE}/configs`, body),

  /** New IMMUTABLE revision (same body minus the name). */
  createConfigRevision: (wpn: string, body: ConfigRevisionCreateBody) =>
    api.post<ConfigCreateResponse>(
      `${BASE}/configs/${enc(wpn)}/revisions`, body,
    ),

  /** Clone the latest revision's content into a NEW config identity
   *  (fresh CFG WPN). */
  cloneConfig: (wpn: string, name: string) =>
    api.post<ConfigCreateResponse>(
      `${BASE}/configs/${enc(wpn)}:clone`, { name },
    ),

  /** Select the active revision (ASTRA-side pointer; no HAROLD). */
  setConfigActiveRevision: (wpn: string, rev_letter: string) =>
    api.put<ConfigDetail>(
      `${BASE}/configs/${enc(wpn)}/active-revision`, { rev_letter },
    ),

  // ══════════════════════════════════════
  //  §9 Configurations — CITADEL bundle export
  // ══════════════════════════════════════

  /** Export the revision as a citadel-config-bundle directory + zip.
   *  Deterministic — a re-export idempotently reuses the recorded
   *  export row (`reused: true`). */
  exportConfigBundle: (wpn: string, rev: string) =>
    api.post<BundleExportResponse>(
      `${BASE}/configs/${enc(wpn)}/${enc(rev)}:exportBundle`,
    ),

  /** Export history for a revision — retrievable WITHOUT re-export. */
  listConfigBundles: (wpn: string, rev: string) =>
    api.get<BundleExportSummary[]>(
      `${BASE}/configs/${enc(wpn)}/${enc(rev)}/bundles`,
    ),

  /** The stored manifest JSON of a historical export. */
  getConfigBundleManifest: (wpn: string, rev: string, bundleHash: string) =>
    api.get<Record<string, unknown>>(
      `${BASE}/configs/${enc(wpn)}/${enc(rev)}/bundles/${enc(bundleHash)}/manifest`,
    ),

  /** Bundle zip download — authed axios blob fetch + object-URL save
   *  (same pattern as cadportAPI.downloadDocument). */
  downloadConfigBundle: async (
    wpn: string,
    rev: string,
    bundleHash: string,
    dirname: string,
  ) => {
    const res = await api.get(
      `${BASE}/configs/${enc(wpn)}/${enc(rev)}/bundles/${enc(bundleHash)}/download`,
      { responseType: 'blob' },
    );
    const url = window.URL.createObjectURL(new Blob([res.data as BlobPart]));
    const a = document.createElement('a');
    a.href = url;
    a.download = `${dirname}.zip`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  },
};
