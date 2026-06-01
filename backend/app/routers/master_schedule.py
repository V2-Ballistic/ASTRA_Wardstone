"""ASTRA — Master Schedule integration router (v2).

Mounted at ``/api/v1`` via main.py's optional-routers loop. The v2
rewire makes ASTRA's project_id the source of truth — there is no
"link" step. The plugin keys all schedules by ``astra_project_id``, so
this router is a pure proxy: each endpoint forwards to the WRENCH
plugin's ``/projects/{astra_project_id}/...`` surface.

Endpoints (all under /api/v1):
  GET  /projects/{id}/schedule/overview      — milestone + CPLI/BEI summary
  GET  /projects/{id}/schedule/program       — does this project have a schedule?
  GET  /projects/{id}/schedule/gantt         — full Gantt data
  GET  /projects/{id}/schedule/critical-path — CP task list
  GET  /projects/{id}/schedule/dcma          — 14-point report

All endpoints proxy via httpx to ``host.docker.internal:8030``. ASTRA
never crosses origins from the browser; the browser hits ASTRA and
ASTRA hits the plugin.

The legacy v1 link table (``schedule_project_links``) is no longer
consulted — the connection is automatic because ``astra_project_id``
IS the key. The table is harmless if left in place (cascades on
project delete).
"""

from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, User
from app.services.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Master Schedule"])

WRENCH_BASE = os.environ.get(
    "WRENCH_BASE_URL", "http://host.docker.internal:8030"
)
WRENCH_PREFIX = "/api/tools/master-schedule"
TIMEOUT = float(os.environ.get("WRENCH_TIMEOUT_S", "10.0"))


def _proxy_get(suffix: str) -> dict:
    """GET ``{WRENCH_BASE}/api/tools/master-schedule{suffix}``.

    Wraps the response in a uniform shape:
        {available: true,  data: ...}  on success
        {available: false, reason: ..., data: null}  on failure
    """
    with httpx.Client(timeout=TIMEOUT) as client:
        try:
            r = client.get(f"{WRENCH_BASE}{WRENCH_PREFIX}{suffix}")
            if r.status_code == 404:
                # 404 means the plugin says "no schedule for this project"
                # — distinct from "plugin offline".
                return {"available": True, "has_schedule": False, "data": None}
            r.raise_for_status()
            return {"available": True, "has_schedule": True, "data": r.json()}
        except httpx.HTTPError as exc:
            logger.warning("master-schedule proxy failed: %s", exc)
            return {
                "available": False, "has_schedule": False,
                "reason": "unreachable", "data": None,
            }


def _ensure_project_exists(db: Session, project_id: int) -> Project:
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "project not found")
    return p


@router.get("/projects/{project_id}/schedule/program")
def get_program(
    project_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Does this project have a schedule yet?"""
    _ensure_project_exists(db, project_id)
    return _proxy_get(f"/projects/{project_id}/program")


@router.get("/projects/{project_id}/schedule/overview")
def overview(
    project_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Milestones + DCMA + margin in one round-trip."""
    _ensure_project_exists(db, project_id)
    with httpx.Client(timeout=TIMEOUT) as client:
        try:
            prog = client.get(f"{WRENCH_BASE}{WRENCH_PREFIX}/projects/{project_id}/program")
            if prog.status_code != 200:
                return {"available": False, "has_schedule": False, "data": None}
            prog_body = prog.json()
            if not prog_body.get("has_schedule"):
                return {"available": True, "has_schedule": False, "data": None}
            l1 = client.get(f"{WRENCH_BASE}{WRENCH_PREFIX}/projects/{project_id}/reports/l1").json()
            dcma = client.get(f"{WRENCH_BASE}{WRENCH_PREFIX}/projects/{project_id}/schedule/dcma").json()
            margin = client.get(f"{WRENCH_BASE}{WRENCH_PREFIX}/projects/{project_id}/reports/margin-burndown").json()
            return {
                "available": True,
                "has_schedule": True,
                "data": {
                    "program": prog_body["program"],
                    "milestones": l1.get("milestones", []),
                    "dcma": dcma,
                    "margin": margin,
                },
            }
        except httpx.HTTPError as exc:
            logger.warning("master-schedule overview failed: %s", exc)
            return {
                "available": False, "has_schedule": False,
                "reason": "unreachable", "data": None,
            }


@router.get("/projects/{project_id}/schedule/gantt")
def gantt(
    project_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    _ensure_project_exists(db, project_id)
    return _proxy_get(f"/projects/{project_id}/schedule/gantt-data")


@router.get("/projects/{project_id}/schedule/critical-path")
def critical_path(
    project_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    _ensure_project_exists(db, project_id)
    return _proxy_get(f"/projects/{project_id}/schedule/critical-path")


@router.get("/projects/{project_id}/schedule/dcma")
def dcma(
    project_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    _ensure_project_exists(db, project_id)
    return _proxy_get(f"/projects/{project_id}/schedule/dcma")


@router.get("/projects/{project_id}/schedule/imp")
def imp_tree(
    project_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """IMP hierarchy for the Milestones outline tab."""
    _ensure_project_exists(db, project_id)
    return _proxy_get(f"/projects/{project_id}/imp")
