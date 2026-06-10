"""ASTRA -> CADPORT outbound HTTP client.

CADPORT-TDD-ASTRA-BRIDGE-001 Phase 3 §3.4. Tiny synchronous helper —
the only callers (the pending-import approve handler and the catalog
PATCH /mass + /material handlers) are themselves sync, and mixing
async into sync FastAPI handlers buys nothing for this 3-call
surface.

  link_catalog_part(cadport_part_id, catalog_part_id)
    → backfills cadport_parts.catalog_part_id on the CADPORT side
      after ASTRA approves a pending import. One-shot; the back-link
      never changes once written.

  sync_mass_to_cadport(cadport_part_id, mass_kg)
    → propagates a public-PATCH mass edit on ASTRA into the matching
      cadport_parts row. Called at the END of a successful local
      update so the local commit isn't gated on CADPORT being up.

  sync_material_to_cadport(cadport_part_id, material)
    → symmetric for material edits.

All three calls are best-effort: connection / timeout / HTTP failures
are logged at WARNING and swallowed. The local update has already
committed by the time we call here — losing the propagation should
not surface to the user as an error.

The /sync-from-* endpoints on the CADPORT side are the loop-breakers:
they update cadport_parts WITHOUT calling back to ASTRA, so a sync
operation here cannot bounce indefinitely.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _base_url() -> str:
    return settings.CADPORT_BASE_URL.rstrip("/")


def _timeout() -> httpx.Timeout:
    return httpx.Timeout(settings.CADPORT_TIMEOUT_SECONDS)


def _enabled() -> bool:
    return bool(getattr(settings, "CADPORT_INTEGRATION_ENABLED", True))


def _post_json(path: str, body: dict) -> Optional[dict]:
    """Sync POST. Returns parsed JSON on 2xx, None on any failure
    (logged at WARNING). Never raises — the caller has already
    committed locally and propagation is best-effort."""
    if not _enabled():
        logger.debug("CADPORT integration disabled; skipping %s", path)
        return None
    url = f"{_base_url()}{path}"
    try:
        with httpx.Client(timeout=_timeout()) as http:
            resp = http.post(url, json=body)
    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        logger.warning("CADPORT unreachable for %s: %s", path, exc)
        return None
    except httpx.HTTPError as exc:
        logger.warning("CADPORT HTTP error for %s: %s", path, exc)
        return None
    if resp.status_code >= 400:
        logger.warning(
            "CADPORT %s returned %d: %s", path, resp.status_code,
            resp.text[:300],
        )
        return None
    try:
        return resp.json()
    except ValueError:
        logger.warning("CADPORT %s returned non-JSON body", path)
        return None


def link_catalog_part(
    cadport_part_id: str, catalog_part_id: int,
) -> Optional[dict]:
    """Tell CADPORT that the cadport_parts row with part_id == X is
    now linked to ASTRA's catalog_parts.id == Y. CADPORT writes that
    back-link onto its row so subsequent CADPORT-side mass edits know
    where to propagate. Called once, on successful pending-import
    approve."""
    return _post_json(
        f"/parts/{cadport_part_id}/link-catalog",
        {"catalog_part_id": int(catalog_part_id)},
    )


def sync_mass_to_cadport(
    cadport_part_id: str, mass_kg: Optional[float],
) -> Optional[dict]:
    """Propagate a public PATCH /mass edit from ASTRA into CADPORT.
    The CADPORT handler stamps last_sync_origin='astra' and does NOT
    call back — that's how the loop is broken."""
    body: dict = {"mass_kg": mass_kg}
    return _post_json(
        f"/parts/{cadport_part_id}/sync-from-astra",
        body,
    )


def sync_material_to_cadport(
    cadport_part_id: str,
    material: Optional[str],
    density_kg_m3: Optional[float] = None,
) -> Optional[dict]:
    """Propagate a public material edit from ASTRA into CADPORT. The
    optional density is passed alongside so CADPORT can refresh its
    density column in lockstep when the material key resolves to a
    known density on the ASTRA side."""
    body: dict = {"material": material}
    if density_kg_m3 is not None:
        body["density_kg_m3"] = float(density_kg_m3)
    return _post_json(
        f"/parts/{cadport_part_id}/sync-from-astra",
        body,
    )


def sync_supplier_to_cadport(
    cadport_part_id: str,
    *,
    supplier_id: int,
    supplier_name: str,
) -> Optional[dict]:
    """CADPORT-TDD-LIFECYCLE-001 Phase 2: propagate an ASTRA-side
    supplier change into CADPORT. CADPORT stores the resolved id
    (and clears the proposed_supplier_name)."""
    return _post_json(
        f"/parts/{cadport_part_id}/sync-from-astra",
        {"supplier_id": int(supplier_id), "supplier_name": supplier_name},
    )


def sync_name_to_cadport(
    cadport_part_id: str, *, display_name: str,
) -> Optional[dict]:
    """CADPORT-TDD-LIFECYCLE-001 Phase 2: propagate a public name
    edit from ASTRA into CADPORT. The CADPORT row's display_name
    is the human-facing name; it also drives the §6 YAML's source_file
    re-emit."""
    return _post_json(
        f"/parts/{cadport_part_id}/sync-from-astra",
        {"display_name": display_name},
    )


def sync_delete_to_cadport(cadport_part_id: str) -> Optional[dict]:
    """CADPORT-TDD-LIFECYCLE-001 Phase 3 §3.2: propagate an ASTRA-side
    delete into CADPORT. The CADPORT handler removes the
    cadport_parts row + its on-disk sources + its YAML blob, and
    does NOT call ASTRA back (loop-breaker).

    Best-effort: failure here logs at WARNING and does not roll back
    the ASTRA-side soft-delete."""
    return _post_json(
        f"/parts/{cadport_part_id}/sync-delete-from-astra",
        {},
    )
