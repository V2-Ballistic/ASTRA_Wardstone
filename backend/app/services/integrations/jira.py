"""
ASTRA — Jira Integration Connector
=====================================
File: backend/app/services/integrations/jira.py   ← NEW

Connects to Jira Cloud or Server via REST API v3/v2.
Supports bidirectional sync and incoming webhooks.

Config keys:
  url        — Jira instance URL (https://company.atlassian.net)
  email      — Jira account email
  api_token  — Jira API token (Cloud) or password (Server)
  project_key — default Jira project key (e.g. "REQ")
"""

import base64
import json
import logging
from typing import Any

import httpx

from app.services.integrations.base import (
    IntegrationConnector, SyncResult, ExternalItem,
    STATUS_MAP, PRIORITY_MAP,
)

logger = logging.getLogger("astra.integrations.jira")


class JiraConnector(IntegrationConnector):
    connector_type = "jira"

    def __init__(self, config: dict):
        super().__init__(config)
        self.base_url = config.get("url", "").rstrip("/")
        self.email = config.get("email", "")
        self.api_token = config.get("api_token", "")
        self._is_cloud = "atlassian.net" in self.base_url

    # ── HTTP helpers ──────────────────────────────────────

    def _headers(self) -> dict:
        # Jira Cloud uses Basic auth with email:api_token
        cred = base64.b64encode(f"{self.email}:{self.api_token}".encode()).decode()
        return {
            "Authorization": f"Basic {cred}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _api(self, method: str, path: str, **kwargs) -> dict:
        api_version = "3" if self._is_cloud else "2"
        url = f"{self.base_url}/rest/api/{api_version}{path}"
        with httpx.Client(timeout=30) as client:
            resp = client.request(method, url, headers=self._headers(), **kwargs)
            resp.raise_for_status()
            return resp.json() if resp.content else {}

    # ── Interface implementation ──────────────────────────

    def test_connection(self) -> bool:
        try:
            data = self._api("GET", "/myself")
            logger.info("Jira connection OK: %s", data.get("displayName", "?"))
            return True
        except Exception as exc:
            logger.warning("Jira connection failed: %s", exc)
            return False

    def get_available_projects(self) -> list[dict]:
        try:
            data = self._api("GET", "/project")
            return [
                {"key": p["key"], "name": p["name"], "id": p.get("id")}
                for p in data
            ]
        except Exception as exc:
            logger.error("Failed to list Jira projects: %s", exc)
            return []

    def fetch_items(self, external_project: str, **kwargs) -> list[ExternalItem]:
        """Fetch issues from a Jira project using JQL."""
        jql = kwargs.get("jql") or f"project = {external_project} ORDER BY key ASC"
        max_results = kwargs.get("max_results", 200)
        start = 0
        items: list[ExternalItem] = []

        while True:
            data = self._api("GET", "/search", params={
                "jql": jql,
                "startAt": start,
                "maxResults": min(100, max_results - len(items)),
                "fields": "summary,description,status,priority,issuetype,issuelinks",
            })

            for issue in data.get("issues", []):
                fields = issue.get("fields", {})
                ext = ExternalItem(
                    external_id=issue["key"],
                    external_url=f"{self.base_url}/browse/{issue['key']}",
                    title=fields.get("summary", ""),
                    description=self._extract_description(fields.get("description")),
                    item_type=self._safe_name(fields.get("issuetype", {})),
                    status=self._safe_name(fields.get("status", {})),
                    priority=self._safe_name(fields.get("priority", {})),
                    links=self._extract_links(fields.get("issuelinks", [])),
                )
                items.append(ext)

            total = data.get("total", 0)
            start += len(data.get("issues", []))
            if start >= total or start >= max_results:
                break

        return items

    def push_item(self, external_project: str, item: ExternalItem) -> str:
        """Create or update a Jira issue."""
        # Check if the issue already exists (by ASTRA req_id in labels)
        jql = f'project = {external_project} AND labels = "astra:{item.external_id}"'
        search = self._api("GET", "/search", params={"jql": jql, "maxResults": 1})
        existing = search.get("issues", [])

        if existing:
            # Update
            issue_key = existing[0]["key"]
            self._api("PUT", f"/issue/{issue_key}", json={
                "fields": {
                    "summary": item.title,
                    "description": self._build_description(item.description),
                },
            })
            return issue_key
        else:
            # Create
            payload: dict[str, Any] = {
                "fields": {
                    "project": {"key": external_project},
                    "summary": item.title,
                    "description": self._build_description(item.description),
                    "issuetype": {"name": self._astra_type_to_jira(item.item_type)},
                    "labels": [f"astra:{item.external_id}"],
                },
            }
            resp = self._api("POST", "/issue", json=payload)
            return resp.get("key", "")

    def receive_webhook(self, payload: dict) -> dict:
        """
        Process a Jira webhook payload.

        Jira sends events like:
          jira:issue_created, jira:issue_updated, jira:issue_deleted

        Returns a summary dict that the router stores as a sync log.
        """
        event = payload.get("webhookEvent", "")
        issue = payload.get("issue", {})
        key = issue.get("key", "unknown")
        fields = issue.get("fields", {})

        return {
            "event": event,
            "issue_key": key,
            "summary": fields.get("summary", ""),
            "status": self._safe_name(fields.get("status", {})),
            "action": "create" if "created" in event else "update" if "updated" in event else "other",
        }

    # ── Helpers ───────────────────────────────────────────

    @staticmethod
    def _safe_name(obj: dict | str | None) -> str:
        if isinstance(obj, dict):
            return obj.get("name", "")
        return str(obj) if obj else ""

    def _extract_description(self, desc: Any) -> str:
        """Handle both ADF (Cloud v3) and plain text (Server v2)."""
        if desc is None:
            return ""
        if isinstance(desc, str):
            return desc
        # ADF document → extract text from content blocks
        if isinstance(desc, dict):
            return self._adf_to_text(desc)
        return str(desc)

    def _adf_to_text(self, node: dict) -> str:
        """Recursively extract text from Atlassian Document Format."""
        text = ""
        if node.get("type") == "text":
            text += node.get("text", "")
        for child in node.get("content", []):
            text += self._adf_to_text(child)
        if node.get("type") in ("paragraph", "heading", "listItem"):
            text += "\n"
        return text

    def _build_description(self, text: str) -> dict | str:
        """Build ADF for Cloud, plain text for Server."""
        if self._is_cloud:
            return {
                "type": "doc",
                "version": 1,
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": text}]}
                ],
            }
        return text

    @staticmethod
    def _extract_links(issue_links: list) -> list[dict]:
        result = []
        for link in issue_links:
            if "outwardIssue" in link:
                result.append({
                    "type": link.get("type", {}).get("name", ""),
                    "target": link["outwardIssue"]["key"],
                    "direction": "outward",
                })
            if "inwardIssue" in link:
                result.append({
                    "type": link.get("type", {}).get("name", ""),
                    "target": link["inwardIssue"]["key"],
                    "direction": "inward",
                })
        return result

    @staticmethod
    def _astra_type_to_jira(astra_type: str) -> str:
        return {
            "functional": "Story", "performance": "Story",
            "security": "Story", "interface": "Story",
            "constraint": "Task", "safety": "Story",
        }.get(astra_type, "Story")
