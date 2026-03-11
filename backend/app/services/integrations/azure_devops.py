"""
ASTRA — Azure DevOps Integration Connector
=============================================
File: backend/app/services/integrations/azure_devops.py   ← NEW

Connects to Azure DevOps Services or Server via REST API 7.0.
Maps work items (Epics, Features, User Stories, Tasks) to ASTRA
requirements.  Supports Azure Boards and Test Plans.

Config keys:
  url        — Azure org URL (https://dev.azure.com/{org})
  pat        — Personal Access Token
  org        — Organization name
  project    — Azure DevOps project name
"""

import base64
import logging

import httpx

from app.services.integrations.base import (
    IntegrationConnector, SyncResult, ExternalItem,
)

logger = logging.getLogger("astra.integrations.azure_devops")

API_VERSION = "7.0"


class AzureDevOpsConnector(IntegrationConnector):
    connector_type = "azure_devops"

    def __init__(self, config: dict):
        super().__init__(config)
        self.org_url = config.get("url", "").rstrip("/")
        self.pat = config.get("pat", "")
        self.org = config.get("org", "")

    # ── HTTP ──────────────────────────────────────────────

    def _headers(self) -> dict:
        cred = base64.b64encode(f":{self.pat}".encode()).decode()
        return {
            "Authorization": f"Basic {cred}",
            "Content-Type": "application/json",
        }

    def _api(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.org_url}{path}"
        sep = "&" if "?" in url else "?"
        url += f"{sep}api-version={API_VERSION}"
        with httpx.Client(timeout=30) as client:
            resp = client.request(method, url, headers=self._headers(), **kwargs)
            resp.raise_for_status()
            return resp.json() if resp.content else {}

    # ── Interface ─────────────────────────────────────────

    def test_connection(self) -> bool:
        try:
            data = self._api("GET", "/_apis/projects")
            count = data.get("count", 0)
            logger.info("Azure DevOps connection OK: %d projects", count)
            return True
        except Exception as exc:
            logger.warning("Azure DevOps connection failed: %s", exc)
            return False

    def get_available_projects(self) -> list[dict]:
        try:
            data = self._api("GET", "/_apis/projects")
            return [
                {"key": p["name"], "name": p["name"], "id": p.get("id")}
                for p in data.get("value", [])
            ]
        except Exception:
            return []

    def fetch_items(self, external_project: str, **kwargs) -> list[ExternalItem]:
        """Fetch work items from Azure DevOps via WIQL."""
        wiql = kwargs.get("wiql") or (
            f"SELECT [System.Id] FROM WorkItems "
            f"WHERE [System.TeamProject] = '{external_project}' "
            f"AND [System.State] <> 'Removed' "
            f"ORDER BY [System.Id] ASC"
        )
        max_results = kwargs.get("max_results", 200)

        # Run WIQL query
        result = self._api(
            "POST", f"/{external_project}/_apis/wit/wiql",
            json={"query": wiql},
        )
        work_item_refs = result.get("workItems", [])[:max_results]
        if not work_item_refs:
            return []

        # Batch fetch work item details (max 200 per call)
        ids = [str(ref["id"]) for ref in work_item_refs]
        items: list[ExternalItem] = []

        for batch_start in range(0, len(ids), 200):
            batch = ids[batch_start : batch_start + 200]
            data = self._api(
                "GET",
                f"/_apis/wit/workitems",
                params={"ids": ",".join(batch), "$expand": "relations"},
            )
            for wi in data.get("value", []):
                fields = wi.get("fields", {})
                wi_id = str(wi["id"])
                links = []
                for rel in (wi.get("relations") or []):
                    if "workitems" in (rel.get("url") or ""):
                        link_id = rel["url"].rsplit("/", 1)[-1]
                        links.append({
                            "type": (rel.get("attributes", {}).get("name", "Related")),
                            "target": link_id,
                            "direction": "outward",
                        })

                items.append(ExternalItem(
                    external_id=wi_id,
                    external_url=f"{self.org_url}/{external_project}/_workitems/edit/{wi_id}",
                    title=fields.get("System.Title", ""),
                    description=self._html_to_text(
                        fields.get("System.Description", "")),
                    item_type=fields.get("System.WorkItemType", ""),
                    status=fields.get("System.State", ""),
                    priority=str(fields.get("Microsoft.VSTS.Common.Priority", 3)),
                    attributes={
                        "area_path": fields.get("System.AreaPath", ""),
                        "iteration": fields.get("System.IterationPath", ""),
                        "acceptance_criteria": self._html_to_text(
                            fields.get("Microsoft.VSTS.Common.AcceptanceCriteria", "")),
                    },
                    links=links,
                ))

        return items

    def push_item(self, external_project: str, item: ExternalItem) -> str:
        """Create a work item in Azure DevOps."""
        wi_type = self._astra_type_to_ado(item.item_type)
        operations = [
            {"op": "add", "path": "/fields/System.Title", "value": item.title},
            {"op": "add", "path": "/fields/System.Description",
             "value": f"<p>{item.description}</p>"},
            {"op": "add", "path": "/fields/System.Tags",
             "value": f"astra:{item.external_id}"},
        ]

        resp = self._api(
            "POST",
            f"/{external_project}/_apis/wit/workitems/${wi_type}",
            json=operations,
            headers={**self._headers(), "Content-Type": "application/json-patch+json"},
        )
        return str(resp.get("id", ""))

    def receive_webhook(self, payload: dict) -> dict:
        """
        Process an Azure DevOps Service Hook payload.

        Azure sends events like:
          workitem.created, workitem.updated, workitem.deleted
        """
        resource = payload.get("resource", {})
        event = payload.get("eventType", "")
        wi_id = str(resource.get("id", "unknown"))
        fields = resource.get("fields", {})

        return {
            "event": event,
            "work_item_id": wi_id,
            "title": fields.get("System.Title", ""),
            "state": fields.get("System.State", ""),
            "action": "create" if "created" in event else "update" if "updated" in event else "other",
        }

    # ── Helpers ───────────────────────────────────────────

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Naive HTML tag stripping."""
        if not html:
            return ""
        import re
        text = re.sub(r"<br\s*/?>", "\n", html)
        text = re.sub(r"<[^>]+>", "", text)
        return text.strip()

    @staticmethod
    def _astra_type_to_ado(astra_type: str) -> str:
        return {
            "functional": "User Story", "performance": "User Story",
            "security": "User Story", "interface": "User Story",
            "constraint": "Task", "safety": "Bug",
        }.get(astra_type, "User Story")
