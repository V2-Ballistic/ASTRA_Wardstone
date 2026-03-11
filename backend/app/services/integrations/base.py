"""
ASTRA — Integration Connector Base
=====================================
File: backend/app/services/integrations/base.py   ← NEW

Abstract base class for all ALM tool connectors.  Each connector
implements connect, test, sync-from, sync-to, and project listing.

The field-mapping helpers convert between ASTRA's schema and the
external tool's schema using a JSON mapping configuration.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models import Requirement, Project, TraceLink


# ══════════════════════════════════════
#  Data structures
# ══════════════════════════════════════

class SyncResult(BaseModel):
    """Returned by every sync operation."""
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)
    sync_timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: dict = Field(default_factory=dict)


class ExternalItem(BaseModel):
    """Normalised representation of an item from an external tool."""
    external_id: str
    external_url: str = ""
    title: str = ""
    description: str = ""
    item_type: str = ""          # epic, story, task, module-object, work-item
    status: str = ""
    priority: str = ""
    attributes: dict = Field(default_factory=dict)
    links: list[dict] = Field(default_factory=list)


# ══════════════════════════════════════
#  Default field mapping
# ══════════════════════════════════════

DEFAULT_FIELD_MAPPING = {
    # external_field → astra_field
    "title": "title",
    "description": "statement",
    "priority": "priority",
    "status": "status",
    "type": "req_type",
}

# Priority normalisation
PRIORITY_MAP = {
    # Jira
    "highest": "critical", "high": "high", "medium": "medium",
    "low": "low", "lowest": "low",
    # Azure DevOps
    "1": "critical", "2": "high", "3": "medium", "4": "low",
    # DOORS
    "mandatory": "critical", "desirable": "high", "optional": "medium",
}

STATUS_MAP = {
    # Jira
    "to do": "draft", "in progress": "under_review",
    "done": "approved", "closed": "approved",
    # Azure DevOps
    "new": "draft", "active": "under_review",
    "resolved": "approved", "closed": "approved",
    # DOORS
    "proposed": "draft", "approved": "approved",
    "implemented": "implemented", "verified": "verified",
}


# ══════════════════════════════════════
#  Abstract connector
# ══════════════════════════════════════

class IntegrationConnector(ABC):
    """
    Every ALM connector inherits from this and implements the five
    abstract methods below.  Connectors are stateless: pass config
    to __init__ and call methods as needed.
    """

    connector_type: str = "base"

    def __init__(self, config: dict):
        """
        Config dict typically contains:
          url, username/email, api_token/password, org, project_key, ...
        """
        self.config = config
        self.field_mapping = config.get("field_mapping", DEFAULT_FIELD_MAPPING)

    # ── Abstract interface ──────────────────────────────

    @abstractmethod
    def test_connection(self) -> bool:
        """Return True if the external system is reachable and credentials work."""
        ...

    @abstractmethod
    def get_available_projects(self) -> list[dict]:
        """List projects / modules available in the external system."""
        ...

    @abstractmethod
    def fetch_items(self, external_project: str, **kwargs) -> list[ExternalItem]:
        """Fetch items from the external system."""
        ...

    @abstractmethod
    def push_item(self, external_project: str, item: ExternalItem) -> str:
        """Push a single item to the external system.  Returns external_id."""
        ...

    @abstractmethod
    def receive_webhook(self, payload: dict) -> dict:
        """Process an incoming webhook event and return a summary."""
        ...

    # ── Shared sync logic ───────────────────────────────

    def sync_requirements_from(
        self, db: Session, project_id: int, external_project: str,
        user_id: int, **kwargs,
    ) -> SyncResult:
        """Import from external → ASTRA."""
        result = SyncResult()
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            result.errors.append(f"ASTRA project {project_id} not found")
            return result

        try:
            items = self.fetch_items(external_project, **kwargs)
        except Exception as exc:
            result.errors.append(f"Fetch failed: {exc}")
            return result

        from app.services.quality_checker import check_requirement_quality, generate_requirement_id
        from sqlalchemy import func

        for ext in items:
            # Check if already imported (by external URL or a tag in rationale)
            existing = db.query(Requirement).filter(
                Requirement.project_id == project_id,
                Requirement.rationale.contains(f"[EXT:{ext.external_id}]"),
            ).first()

            mapped = self._map_to_astra(ext)

            if existing:
                changed = False
                for field in ("title", "statement", "priority", "status"):
                    new_val = mapped.get(field)
                    if new_val and str(getattr(existing, field, "")) != str(new_val):
                        setattr(existing, field, new_val)
                        changed = True
                if changed:
                    existing.version = (existing.version or 1) + 1
                    result.updated += 1
                else:
                    result.skipped += 1
            else:
                req_type = mapped.get("req_type", "functional")
                count = db.query(func.count(Requirement.id)).filter(
                    Requirement.project_id == project_id,
                    Requirement.req_type == req_type,
                ).scalar() or 0
                req_id = generate_requirement_id(project.code, req_type, count + 1)
                quality = check_requirement_quality(
                    mapped.get("statement", ""), mapped.get("title", ""), "")

                rationale = mapped.get("rationale", "") or ""
                rationale += f"\n[EXT:{ext.external_id}] {ext.external_url}"

                req = Requirement(
                    req_id=req_id,
                    title=mapped.get("title", ext.external_id),
                    statement=mapped.get("statement", "Imported requirement"),
                    rationale=rationale.strip(),
                    req_type=req_type,
                    priority=mapped.get("priority", "medium"),
                    status="draft",
                    project_id=project_id,
                    owner_id=user_id,
                    created_by_id=user_id,
                    quality_score=quality.get("score", 0),
                )
                db.add(req)
                result.created += 1

        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            result.errors.append(f"DB commit failed: {exc}")

        return result

    def sync_requirements_to(
        self, db: Session, project_id: int, external_project: str,
        user_id: int, **kwargs,
    ) -> SyncResult:
        """Export from ASTRA → external."""
        result = SyncResult()
        reqs = (
            db.query(Requirement)
            .filter(Requirement.project_id == project_id, Requirement.status != "deleted")
            .order_by(Requirement.req_id)
            .all()
        )

        for req in reqs:
            ext_item = self._map_from_astra(req)
            try:
                ext_id = self.push_item(external_project, ext_item)
                if not (req.rationale or "").endswith(f"[EXT:{ext_id}]"):
                    req.rationale = (req.rationale or "") + f"\n[EXT:{ext_id}]"
                result.created += 1
            except Exception as exc:
                result.errors.append(f"{req.req_id}: {exc}")

        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            result.errors.append(f"DB commit failed: {exc}")

        return result

    # ── Mapping helpers ─────────────────────────────────

    def _map_to_astra(self, ext: ExternalItem) -> dict:
        """Convert an external item to ASTRA field values using field_mapping."""
        mapped: dict[str, Any] = {}
        reverse_map = {v: k for k, v in self.field_mapping.items()}

        if "title" in self.field_mapping.values():
            mapped["title"] = ext.title
        if "statement" in self.field_mapping.values():
            mapped["statement"] = ext.description or ext.title
        if "priority" in self.field_mapping.values():
            mapped["priority"] = PRIORITY_MAP.get(ext.priority.lower(), "medium")
        if "status" in self.field_mapping.values():
            mapped["status"] = STATUS_MAP.get(ext.status.lower(), "draft")
        if "req_type" in self.field_mapping.values():
            mapped["req_type"] = self._map_type(ext.item_type)

        # Copy any extra mapped attributes
        for ext_field, astra_field in self.field_mapping.items():
            if astra_field not in mapped and ext_field in ext.attributes:
                mapped[astra_field] = ext.attributes[ext_field]

        return mapped

    def _map_from_astra(self, req: Requirement) -> ExternalItem:
        """Convert an ASTRA requirement to an ExternalItem for pushing."""
        def _ev(v):
            return v.value if hasattr(v, "value") else str(v) if v else ""

        return ExternalItem(
            external_id=req.req_id,
            title=req.title,
            description=req.statement,
            item_type=_ev(req.req_type),
            status=_ev(req.status),
            priority=_ev(req.priority),
            attributes={"rationale": req.rationale or "", "quality_score": req.quality_score or 0},
        )

    @staticmethod
    def _map_type(ext_type: str) -> str:
        type_map = {
            "epic": "functional", "story": "functional", "task": "functional",
            "bug": "constraint", "test": "functional",
            "feature": "functional", "user story": "functional",
            "product backlog item": "functional",
            "heading": "functional", "information": "functional",
        }
        return type_map.get(ext_type.lower(), "functional")
