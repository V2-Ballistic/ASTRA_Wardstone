"""HAROLD nomenclature integration — client + service helpers.

TDD-HAROLD-001 (Path A). All calls to HAROLD originate from this
package; the browser never talks to HAROLD directly. The router layer
in `app/routers/harold.py` proxies through these functions.

HAROLD itself runs as a plugin inside WRENCH (v0.2.0) at the configured
`HAROLD_BASE_URL`. Invocation is always:

    POST /api/tools/{slug}/runs   body={"inputs": {...}}
    → 200 {runId, slug, inputs, output, success, elapsed_ms, error, ...}

Behavior when HAROLD is disabled / unreachable:
  * `client.heartbeat()` returns a HeartbeatResult with `reachable=False`
  * Other functions raise `HaroldUnavailableError`.
  * Endpoints catch and return a structured `{harold_available: false}`
    payload so the UI hides the HAROLD affordances gracefully.
"""

from .errors import HaroldUnavailableError, HaroldInvalidResponseError
from .service import (
    HeartbeatResult, SystemCode,
    heartbeat, list_system_codes, suggest_wpn_from_text,
)

__all__ = [
    "HaroldUnavailableError",
    "HaroldInvalidResponseError",
    "HeartbeatResult",
    "SystemCode",
    "heartbeat",
    "list_system_codes",
    "suggest_wpn_from_text",
]
