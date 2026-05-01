"""
ASTRA — Reactive Requirement Sync Engine (Phase 5, ASTRA-TDD-INTF-002)
=======================================================================

Detects when source data (System, Unit, Wire, Bus, etc.) has been edited
in a way that invalidates an auto-generated requirement, and either
auto-applies the new content (low-risk statuses) or surfaces a
RequirementSyncProposal for reviewer action (higher-risk statuses).

Public surface:
    - render_requirement (renderer)
    - fan_out_for_entity, decide_action (fan_out)
    - register_sync_listeners (listener)
"""

from app.services.req_sync.renderer import (  # noqa: F401
    RenderedRequirement,
    render_requirement,
)
from app.services.req_sync.fan_out import (  # noqa: F401
    SyncAction,
    decide_action,
    fan_out_for_entity,
)
from app.services.req_sync.listener import (  # noqa: F401
    register_sync_listeners,
)
