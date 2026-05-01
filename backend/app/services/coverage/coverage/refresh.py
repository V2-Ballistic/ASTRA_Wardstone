"""
ASTRA — Coverage MV Refresh Service
=====================================
File: backend/app/services/coverage/refresh.py
                                              ← NEW (Phase 6, ASTRA-TDD-INTF-002)

Wraps ``REFRESH MATERIALIZED VIEW [CONCURRENTLY] mv_requirement_source_coverage``
so callers don't have to remember the SQL or how to recover from a missing
unique index. CONCURRENTLY avoids locking concurrent SELECTs against the MV
but requires the unique index that alembic 0025 already creates.

Wire-in points
--------------

* :mod:`app.routers.req_sync` — the bulk-accept handler calls
  :func:`refresh_coverage_mv` ONCE after the transaction commits, not per
  proposal (one MV refresh per row would dominate latency at 200/req).
* APScheduler periodic — registered in ``app.main`` lifespan, every 10 min.
  If APScheduler is not installed the registration logs and returns; the
  refresh still works on demand from any caller.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

logger = logging.getLogger("astra.coverage.refresh")

_MV_NAME = "mv_requirement_source_coverage"


def refresh_coverage_mv(db: Session, concurrent: bool = True) -> bool:
    """Refresh the coverage materialized view.

    Returns ``True`` on success, ``False`` if the MV doesn't exist (e.g.,
    SQLite test env or pre-0025 deployment) — callers can ignore the return
    value safely; misses are also logged at debug level.

    Tries CONCURRENTLY first when *concurrent=True* (no lock on readers).
    Falls back to a non-concurrent refresh if CONCURRENTLY raises (which
    happens on the very first refresh, before the MV has data, in some PG
    versions).
    """
    sql_concurrent = f"REFRESH MATERIALIZED VIEW CONCURRENTLY {_MV_NAME}"
    sql_blocking = f"REFRESH MATERIALIZED VIEW {_MV_NAME}"

    try:
        if concurrent:
            try:
                db.execute(text(sql_concurrent))
                db.commit()
                return True
            except (OperationalError, ProgrammingError) as exc:
                # CONCURRENTLY can fail on first refresh ("cannot refresh
                # materialized view ... concurrently"). Fall through to
                # blocking refresh.
                logger.debug(
                    "CONCURRENTLY refresh failed (%s); retrying blocking", exc,
                )
                db.rollback()
        db.execute(text(sql_blocking))
        db.commit()
        return True
    except (OperationalError, ProgrammingError) as exc:
        # MV doesn't exist (SQLite test env / pre-0025 deployment).
        logger.debug("MV refresh skipped — %s not present (%s)", _MV_NAME, exc)
        try:
            db.rollback()
        except Exception:
            pass
        return False
    except Exception as exc:  # pragma: no cover
        logger.warning("Unexpected MV refresh failure: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return False


# ══════════════════════════════════════════════════════════════
#  Periodic refresh — APScheduler hook (best-effort)
# ══════════════════════════════════════════════════════════════

_scheduler: Optional[object] = None  # APScheduler instance, if available


def start_periodic_refresh(interval_minutes: int = 10) -> None:
    """Schedule a background coverage MV refresh every *interval_minutes*.

    No-op if APScheduler isn't installed. Designed to be called from the
    FastAPI lifespan event so the scheduler dies cleanly with the process.
    Idempotent — calling more than once just re-schedules.
    """
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.info(
            "APScheduler not installed — coverage MV will refresh on demand only "
            "(bulk-accept path) instead of every %d minutes", interval_minutes,
        )
        return
    if _scheduler is not None:
        return
    from app.database import SessionLocal

    def _job() -> None:
        session = SessionLocal()
        try:
            refresh_coverage_mv(session, concurrent=True)
        finally:
            session.close()

    sched = BackgroundScheduler(daemon=True)
    sched.add_job(_job, "interval", minutes=interval_minutes,
                  id="coverage_mv_refresh", replace_existing=True)
    sched.start()
    _scheduler = sched
    logger.info(
        "Coverage MV periodic refresh scheduled every %d min", interval_minutes,
    )


def stop_periodic_refresh() -> None:
    """Shut the scheduler down — call from FastAPI lifespan teardown."""
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover
            pass
        _scheduler = None
