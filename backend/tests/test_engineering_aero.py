"""API tests for the Aero Decks router (spec §6).

respx-mocks HAROLD's HTTP surface (same pattern as
``test_harold_naming.py`` / ``test_harold_endpoints.py``) and drives
the FastAPI TestClient. Spec properties under test:

  * ingestSource end-to-end: the deck carries HAROLD's issued WPN
    VERBATIM — never self-assigned.
  * lineage match → revision (issue_revision), not a new identity.
  * revision bump keeps the index, bumps the letter.
  * persistence failure → WPN released back to HAROLD (DELETE called).
  * HAROLD down → 503, no fallback.
  * missing Sref → 422 before any allocation.
  * DATCOM .out → 422 "format not yet supported: datcom".
  * revisions are immutable; the artifact is byte-stable.
  * preview interpolation + envelope enforcement.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile

import httpx
import pytest
import respx

from app.config import settings
from app.models.engineering_aero import AeroDeck, AeroDeckRevision  # noqa: F401 — registers tables

_BASE = "http://host.docker.internal:8030"
_PREFIX = f"{_BASE}/api/tools/wardstone-harold"

API = "/api/v1/engineering/aero"
INGEST_URL = "/api/v1/engineering/aero:ingestSource"


@pytest.fixture(autouse=True)
def _pin_settings(monkeypatch):
    monkeypatch.setattr(settings, "HAROLD_BASE_URL", _BASE)
    monkeypatch.setattr(settings, "HAROLD_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setattr(settings, "HAROLD_INTEGRATION_ENABLED", True)


# ── CSV fixtures ────────────────────────────────────────────────────

MACHS = (0.3, 0.8, 1.2)
ALPHAS = (-4.0, 0.0, 4.0, 8.0)


def _make_csv(machs=MACHS, alphas=ALPHAS, *, comments=True, cn_offset=0.0):
    lines = []
    if comments:
        lines += [
            "# Sref_m2: 0.018",
            "# Lref_m: 0.152",
            "# refPoint_m_B: 0.45 0.0 0.0",
        ]
    lines.append("Mach,Alpha_deg,CA,CN,Cm")
    for m in machs:
        for a in alphas:
            ca = 0.3 + 0.1 * m
            cn = 0.05 * a + cn_offset
            cm = -0.02 * a
            lines.append(f"{m},{a},{ca},{cn},{cm}")
    return "\n".join(lines) + "\n"


#: small coefficient CSV — Mach {0.3, 0.8, 1.2} × alpha {-4, 0, 4, 8}
CSV_MAIN = _make_csv()
#: second CSV extending Mach {1.5, 2.0} (no metadata comments)
CSV_EXT = _make_csv(machs=(1.5, 2.0), comments=False)


def _upload(filename, text):
    return ("files", (filename, text, "text/csv"))


# ── HAROLD mocks ────────────────────────────────────────────────────


def _entry(index: int, rev: str = "A") -> dict:
    return {
        "id": index,
        "wpn": f"WS-AER-P{index:06d}-{rev}",
        "system_code": "AER",
        "part_number_int": index,
        "revision": rev,
        "status": "active",
    }


def _mock_syscode():
    return respx.post(f"{_PREFIX}/system-codes").mock(
        return_value=httpx.Response(200, json={
            "code": "AER", "name": "Aero Decks",
            "category": "engineering", "created": False,
        }),
    )


def _mock_precheck(iteration_stem=None):
    """HAROLD's real /filename-precheck shape (see wardstone-harold
    precheck router): it returns ``iteration_stem`` — never
    ``canonical_name``/``canonical_stem`` and no WPN key. A None stem
    exercises the router's filename-stem fallback."""
    return respx.post(f"{_PREFIX}/filename-precheck").mock(
        return_value=httpx.Response(200, json={
            "filename": f"{iteration_stem or 'upload'}.csv",
            "astra_available": True,
            "is_collision": False,
            "iteration_stem": iteration_stem,
            "iteration_count": None,
            "existing_iterations": [],
            "next_available_iteration": 1,
            "suggested_filename": None,
            "wpn_suggestion": None,
            "warnings": [],
            "errors": [],
        }),
    )


def _mock_record_use():
    return respx.route(
        method="PATCH",
        url__regex=rf"{re.escape(_PREFIX)}/wpn/.+",
    ).mock(return_value=httpx.Response(200, json=_entry(1)))


def _mock_issue(index=42, rev="A"):
    return respx.post(f"{_PREFIX}/wpn/issue").mock(
        return_value=httpx.Response(201, json=_entry(index, rev)),
    )


def _mock_revise(base_wpn: str, index: int, rev: str):
    return respx.post(f"{_PREFIX}/wpn/{base_wpn}/revise").mock(
        return_value=httpx.Response(201, json=_entry(index, rev)),
    )


def _ingest(client, auth_headers, files, data=None):
    return client.post(
        INGEST_URL, files=files, data=data or {}, headers=auth_headers,
    )


def _standard_ingest(client, auth_headers, index=42):
    """Happy-path single-file ingest with the full HAROLD mock set."""
    _mock_syscode()
    _mock_precheck()
    issue = _mock_issue(index)
    patch = _mock_record_use()
    resp = _ingest(
        client, auth_headers, [_upload("fin_can_aero.csv", CSV_MAIN)],
    )
    return resp, issue, patch


# ══════════════════════════════════════════════════════════════
#  Auth
# ══════════════════════════════════════════════════════════════


def test_list_requires_auth(client):
    assert client.get(API).status_code == 401


# ══════════════════════════════════════════════════════════════
#  Ingest — auto-name flow
# ══════════════════════════════════════════════════════════════


@respx.mock
def test_ingest_source_end_to_end_harold_named(client, auth_headers):
    resp, issue, patch = _standard_ingest(client, auth_headers, index=42)
    assert resp.status_code == 201, resp.text
    body = resp.json()

    # HAROLD's issued WPN VERBATIM — never self-assigned.
    assert issue.called
    assert body["wpn"] == "WS-AER-P000042-A"
    assert body["deck_wpn"] == "WS-AER-P000042"
    assert body["rev_letter"] == "A"
    assert body["is_new_deck"] is True
    # the uploader did not name it: name came from the filename stem
    # (HAROLD's precheck returned no canonical name)
    assert body["name"] == "fin_can_aero"
    # record_use annotated the ledger
    assert patch.called

    # list view: envelope + current rev
    rows = client.get(API, headers=auth_headers).json()
    assert len(rows) == 1
    row = rows[0]
    assert row["wpn"] == "WS-AER-P000042"
    assert row["current_rev"] == "A"
    assert row["mach_min"] == pytest.approx(0.3)
    assert row["mach_max"] == pytest.approx(1.2)
    assert row["alpha_min_deg"] == pytest.approx(-4.0)
    assert row["alpha_max_deg"] == pytest.approx(8.0)

    # detail + revision detail
    detail = client.get(f"{API}/WS-AER-P000042", headers=auth_headers).json()
    assert detail["base_index"] == 42
    assert len(detail["revisions"]) == 1

    rev = client.get(
        f"{API}/WS-AER-P000042/revisions/A", headers=auth_headers,
    ).json()
    assert rev["wpn"] == "WS-AER-P000042-A"
    assert rev["source_filenames"] == ["fin_can_aero.csv"]
    assert rev["sref_m2"] == pytest.approx(0.018)

    # the artifact IS the deck JSON
    art = client.get(
        f"{API}/WS-AER-P000042/revisions/A/artifact", headers=auth_headers,
    )
    assert art.status_code == 200
    assert ".aero.json" in art.headers["content-disposition"]
    deck = art.json()
    assert deck["schema"] == "astra-aero-deck/1.0"
    assert deck["frame"] == "citadel-vehicle-body-frame"
    assert deck["axes"] == ["mach", "alpha_deg", "beta_deg", "delta_deg"]
    assert deck["provenance"]["wpn"] == "WS-AER-P000042-A"
    assert deck["provenance"]["sourceFiles"][0]["filename"] == "fin_can_aero.csv"
    # canonical sha matches the stored deck_sha256
    canonical = json.dumps(deck, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode()).hexdigest() == rev["deck_sha256"]


@respx.mock
def test_ingest_reupload_same_name_creates_revision_not_new_deck(
    client, auth_headers,
):
    resp, issue, _ = _standard_ingest(client, auth_headers, index=42)
    assert resp.status_code == 201
    assert issue.call_count == 1

    # second upload of the same canonical name → lineage match →
    # issue_revision (same index, next letter); NOT a fresh allocation
    revise = _mock_revise("WS-AER-P000042-A", 42, "B")
    resp2 = _ingest(
        client, auth_headers, [_upload("fin_can_aero.csv", CSV_MAIN)],
    )
    assert resp2.status_code == 201, resp2.text
    body = resp2.json()
    assert revise.called
    assert issue.call_count == 1          # no second allocation
    assert body["is_new_deck"] is False
    assert body["wpn"] == "WS-AER-P000042-B"
    assert body["deck_wpn"] == "WS-AER-P000042"  # index kept


@respx.mock
def test_ingest_iteration_stem_lineage_match_creates_revision(
    client, auth_headers,
):
    """HAROLD's precheck returns ``iteration_stem`` (its filename
    parse). When that stem equals an existing deck's canonical name —
    e.g. uploading ``fin_can_aero_v2.csv`` after ``fin_can_aero.csv``
    — the ingest must land as the next revision of that deck
    (issue_revision), NOT a fresh allocation."""
    resp, issue, _ = _standard_ingest(client, auth_headers, index=42)
    assert resp.status_code == 201
    assert resp.json()["name"] == "fin_can_aero"
    assert issue.call_count == 1

    # New upload, different filename, but HAROLD's iteration_stem
    # matches the existing deck's canonical name.
    _mock_precheck(iteration_stem="fin_can_aero")
    revise = _mock_revise("WS-AER-P000042-A", 42, "B")
    resp2 = _ingest(
        client, auth_headers, [_upload("fin_can_aero_v2.csv", CSV_MAIN)],
    )
    assert resp2.status_code == 201, resp2.text
    body = resp2.json()
    assert revise.called
    assert issue.call_count == 1          # no second allocation
    assert body["is_new_deck"] is False
    assert body["wpn"] == "WS-AER-P000042-B"
    assert body["deck_wpn"] == "WS-AER-P000042"  # index kept
    assert body["name"] == "fin_can_aero"


@respx.mock
def test_ingest_missing_sref_is_422_before_any_allocation(
    client, auth_headers,
):
    _mock_syscode()
    _mock_precheck()
    # NOTE: /wpn/issue deliberately NOT mocked — if the handler tried
    # to allocate, respx would explode the test.
    resp = _ingest(
        client, auth_headers,
        [_upload("bare.csv", _make_csv(comments=False))],
    )
    assert resp.status_code == 422
    assert "Sref_m2" in json.dumps(resp.json())


@respx.mock
def test_ingest_datcom_out_rejected(client, auth_headers):
    resp = _ingest(
        client, auth_headers, [_upload("missile.out", "DATCOM…")],
    )
    assert resp.status_code == 422
    assert "format not yet supported: datcom" in json.dumps(resp.json())


@respx.mock
def test_ingest_harold_down_is_503(client, auth_headers):
    respx.post(f"{_PREFIX}/filename-precheck").mock(
        side_effect=httpx.ConnectError("connection refused"),
    )
    resp = _ingest(
        client, auth_headers, [_upload("fin_can_aero.csv", CSV_MAIN)],
    )
    assert resp.status_code == 503


@respx.mock
def test_ingest_persistence_failure_releases_wpn(
    client, auth_headers, db_session, test_user,
):
    # Occupy the base-WPN slot so the local persist hits the UNIQUE
    # constraint AFTER HAROLD has issued the WPN.
    db_session.add(AeroDeck(
        wpn="WS-AER-P000001", base_index=1, system_code="AER",
        name="occupier", created_by_id=test_user.id,
    ))
    db_session.commit()

    _mock_syscode()
    _mock_precheck()
    _mock_issue(index=1)
    delete = respx.delete(f"{_PREFIX}/wpn/WS-AER-P000001-A").mock(
        return_value=httpx.Response(200, json={
            "deleted_wpn": "WS-AER-P000001-A",
            "reclaimed": True, "new_next_index": 1,
        }),
    )

    resp = _ingest(
        client, auth_headers, [_upload("fresh.csv", CSV_MAIN)],
    )
    assert resp.status_code == 409
    assert delete.called  # WPN handed back — AER sequence stays gapless
    # no half-persisted revision
    assert db_session.query(AeroDeckRevision).count() == 0


@respx.mock
def test_ingest_multiple_files_merged_envelope(client, auth_headers):
    _mock_syscode()
    _mock_precheck()
    _mock_issue(index=7)
    _mock_record_use()
    resp = _ingest(
        client, auth_headers,
        [_upload("deck_lo.csv", CSV_MAIN), _upload("deck_hi.csv", CSV_EXT)],
    )
    assert resp.status_code == 201, resp.text
    env = resp.json()["envelope"]
    assert env["mach_min"] == pytest.approx(0.3)
    assert env["mach_max"] == pytest.approx(2.0)


@respx.mock
def test_ingest_merge_conflict_is_422_with_points(client, auth_headers):
    _mock_syscode()
    _mock_precheck()
    # overlaps CSV_MAIN only at Mach 0.8, with CN shifted by +0.01
    conflicting = _make_csv(machs=(0.8, 2.0), comments=False, cn_offset=0.01)
    resp = _ingest(
        client, auth_headers,
        [_upload("deck_a.csv", CSV_MAIN), _upload("deck_b.csv", conflicting)],
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "merge conflict" in detail["message"]
    assert detail["points"]
    assert all(p["mach"] == pytest.approx(0.8) for p in detail["points"])


# ══════════════════════════════════════════════════════════════
#  Revisions
# ══════════════════════════════════════════════════════════════


@respx.mock
def test_revision_from_source_bumps_letter_keeps_index(
    client, auth_headers,
):
    resp, _, _ = _standard_ingest(client, auth_headers, index=42)
    assert resp.status_code == 201
    revise = _mock_revise("WS-AER-P000042-A", 42, "B")

    resp2 = client.post(
        f"{API}/WS-AER-P000042/revisions:from-source",
        files=[_upload("fin_can_aero_m2.csv", CSV_EXT)],
        headers=auth_headers,
    )
    assert resp2.status_code == 201, resp2.text
    body = resp2.json()
    assert revise.called
    assert body["wpn"] == "WS-AER-P000042-B"   # HAROLD verbatim
    assert body["rev_letter"] == "B"
    assert body["deck_wpn"] == "WS-AER-P000042"  # index stable
    # Sref/Lref inherited from rev A (CSV_EXT has no comments)
    assert "Sref_m2" in body["defaulted_fields"]
    assert "Lref_m" in body["defaulted_fields"]

    detail = client.get(f"{API}/WS-AER-P000042", headers=auth_headers).json()
    assert [r["rev_letter"] for r in detail["revisions"]] == ["A", "B"]
    assert detail["current_rev"] == "B"        # newest auto-activates
    assert detail["mach_min"] == pytest.approx(1.5)
    assert detail["mach_max"] == pytest.approx(2.0)

    rev_b = client.get(
        f"{API}/WS-AER-P000042/revisions/B", headers=auth_headers,
    ).json()
    assert rev_b["sref_m2"] == pytest.approx(0.018)  # inherited value


@respx.mock
def test_revisions_are_immutable(client, auth_headers):
    resp, _, _ = _standard_ingest(client, auth_headers, index=42)
    assert resp.status_code == 201
    sha_a = resp.json()["deck_sha256"]
    art_a_before = client.get(
        f"{API}/WS-AER-P000042/revisions/A/artifact", headers=auth_headers,
    ).json()

    _mock_revise("WS-AER-P000042-A", 42, "B")
    resp2 = client.post(
        f"{API}/WS-AER-P000042/revisions:from-source",
        files=[_upload("v2.csv", CSV_EXT)],
        headers=auth_headers,
    )
    assert resp2.status_code == 201

    # rev A is untouched: identical artifact, identical sha
    art_a_after = client.get(
        f"{API}/WS-AER-P000042/revisions/A/artifact", headers=auth_headers,
    ).json()
    assert art_a_after == art_a_before
    rev_a = client.get(
        f"{API}/WS-AER-P000042/revisions/A", headers=auth_headers,
    ).json()
    assert rev_a["deck_sha256"] == sha_a

    # and there is NO mutation surface for a persisted revision
    assert client.patch(
        f"{API}/WS-AER-P000042/revisions/A",
        json={"notes": "sneaky edit"}, headers=auth_headers,
    ).status_code == 405
    assert client.put(
        f"{API}/WS-AER-P000042/revisions/A",
        json={"notes": "sneaky edit"}, headers=auth_headers,
    ).status_code == 405


@respx.mock
def test_set_active_revision(client, auth_headers):
    resp, _, _ = _standard_ingest(client, auth_headers, index=42)
    assert resp.status_code == 201
    _mock_revise("WS-AER-P000042-A", 42, "B")
    assert client.post(
        f"{API}/WS-AER-P000042/revisions:from-source",
        files=[_upload("v2.csv", CSV_EXT)],
        headers=auth_headers,
    ).status_code == 201

    # pin back to A
    resp3 = client.put(
        f"{API}/WS-AER-P000042/active-revision",
        json={"rev_letter": "A"},
        headers=auth_headers,
    )
    assert resp3.status_code == 200, resp3.text
    body = resp3.json()
    assert body["current_rev"] == "A"
    assert body["mach_max"] == pytest.approx(1.2)  # rev A envelope again

    # unknown letter → 404
    assert client.put(
        f"{API}/WS-AER-P000042/active-revision",
        json={"rev_letter": "Z"},
        headers=auth_headers,
    ).status_code == 404


# ══════════════════════════════════════════════════════════════
#  Preview
# ══════════════════════════════════════════════════════════════


@respx.mock
def test_preview_interpolation(client, auth_headers):
    resp, _, _ = _standard_ingest(client, auth_headers, index=42)
    assert resp.status_code == 201

    r = client.get(
        f"{API}/WS-AER-P000042/preview",
        params={"mach": 0.55, "alpha": 2.0},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rev_letter"] == "A"
    # fixture coefficients are (bi)linear → interpolation is exact:
    # CA = 0.3 + 0.1·M, CN = 0.05·α, Cm = -0.02·α
    assert body["values"]["CA"] == pytest.approx(0.3 + 0.1 * 0.55)
    assert body["values"]["CN"] == pytest.approx(0.1)
    assert body["values"]["Cm"] == pytest.approx(-0.04)


@respx.mock
def test_preview_outside_envelope_is_422(client, auth_headers):
    resp, _, _ = _standard_ingest(client, auth_headers, index=42)
    assert resp.status_code == 201
    r = client.get(
        f"{API}/WS-AER-P000042/preview",
        params={"mach": 3.0, "alpha": 0.0},
        headers=auth_headers,
    )
    assert r.status_code == 422
    assert "envelope" in json.dumps(r.json())


def _make_beta_delta_csv():
    """Full mach × alpha × beta × delta grid; CN = 0.05·α + 0.03·δ,
    CY = 0.02·β (multilinear → interpolation is exact)."""
    lines = ["# Sref_m2: 0.018", "# Lref_m: 0.152",
             "mach,alpha,beta_deg,delta_deg,CN,CY"]
    for m in (0.5, 1.0):
        for a in (0.0, 4.0):
            for b in (-4.0, 0.0, 4.0):
                for d in (0.0, 10.0):
                    lines.append(
                        f"{m},{a},{b},{d},{0.05 * a + 0.03 * d},"
                        f"{0.02 * b}"
                    )
    return "\n".join(lines) + "\n"


@respx.mock
def test_preview_with_explicit_beta_delta_params(client, auth_headers):
    _mock_syscode()
    _mock_precheck()
    _mock_issue(index=9)
    _mock_record_use()
    resp = _ingest(
        client, auth_headers,
        [_upload("bd_deck.csv", _make_beta_delta_csv())],
    )
    assert resp.status_code == 201, resp.text

    # explicit beta/delta → full multilinear lookup
    r = client.get(
        f"{API}/WS-AER-P000009/preview",
        params={"mach": 0.75, "alpha": 2.0, "beta": 1.0, "delta": 5.0},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["beta_deg"] == pytest.approx(1.0)
    assert body["delta_deg"] == pytest.approx(5.0)
    assert body["values"]["CN"] == pytest.approx(0.05 * 2.0 + 0.03 * 5.0)
    assert body["values"]["CY"] == pytest.approx(0.02 * 1.0)

    # omitted beta/delta → nearest-0 slice (historical behavior kept)
    r2 = client.get(
        f"{API}/WS-AER-P000009/preview",
        params={"mach": 0.5, "alpha": 4.0},
        headers=auth_headers,
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["beta_deg"] == pytest.approx(0.0)
    assert body2["delta_deg"] == pytest.approx(0.0)
    assert body2["values"]["CN"] == pytest.approx(0.2)
    assert body2["values"]["CY"] == pytest.approx(0.0)

    # beta outside the validity envelope → 422
    r3 = client.get(
        f"{API}/WS-AER-P000009/preview",
        params={"mach": 0.5, "alpha": 0.0, "beta": 30.0},
        headers=auth_headers,
    )
    assert r3.status_code == 422
    assert "beta" in json.dumps(r3.json())


# ══════════════════════════════════════════════════════════════
#  Source file download
# ══════════════════════════════════════════════════════════════


@respx.mock
def test_source_download_single_file_is_verbatim_csv(
    client, auth_headers,
):
    resp, _, _ = _standard_ingest(client, auth_headers, index=42)
    assert resp.status_code == 201
    r = client.get(
        f"{API}/WS-AER-P000042/revisions/A/source", headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert 'filename="fin_can_aero.csv"' in r.headers["content-disposition"]
    assert r.text == CSV_MAIN  # byte-for-byte as uploaded


@respx.mock
def test_source_download_zip_for_multiple_files(client, auth_headers):
    _mock_syscode()
    _mock_precheck()
    _mock_issue(index=7)
    _mock_record_use()
    resp = _ingest(
        client, auth_headers,
        [_upload("deck_lo.csv", CSV_MAIN), _upload("deck_hi.csv", CSV_EXT)],
    )
    assert resp.status_code == 201, resp.text

    r = client.get(
        f"{API}/WS-AER-P000007/revisions/A/source", headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    assert 'filename="WS-AER-P000007-A.sources.zip"' \
        in r.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert sorted(zf.namelist()) == ["deck_hi.csv", "deck_lo.csv"]
        assert zf.read("deck_lo.csv").decode() == CSV_MAIN
        assert zf.read("deck_hi.csv").decode() == CSV_EXT

    # unknown revision → 404
    assert client.get(
        f"{API}/WS-AER-P000007/revisions/Z/source", headers=auth_headers,
    ).status_code == 404
