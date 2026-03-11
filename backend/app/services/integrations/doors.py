"""
ASTRA — IBM DOORS Next Generation Connector
=============================================
File: backend/app/services/integrations/doors.py   ← NEW

Connects to DOORS Next Generation (DNG) via the OSLC REST API.
Supports ReqIF XML import as a fallback for environments that
restrict direct API access.

Config keys:
  url            — DOORS NG server URL (https://doors.company.com)
  username       — DOORS account
  password       — DOORS password
  project_area   — DOORS project area URI
  use_reqif      — If true, use ReqIF file import instead of OSLC API
"""

import logging
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from app.services.integrations.base import (
    IntegrationConnector, SyncResult, ExternalItem,
)

logger = logging.getLogger("astra.integrations.doors")

# OSLC namespaces
NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dcterms": "http://purl.org/dc/terms/",
    "oslc": "http://open-services.net/ns/core#",
    "oslc_rm": "http://open-services.net/ns/rm#",
    "reqif": "http://www.omg.org/spec/ReqIF/20110401/reqif.xsd",
}


class DoorsConnector(IntegrationConnector):
    connector_type = "doors"

    def __init__(self, config: dict):
        super().__init__(config)
        self.base_url = config.get("url", "").rstrip("/")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.project_area = config.get("project_area", "")
        self.use_reqif = config.get("use_reqif", False)
        self._session_cookie: str | None = None

    # ── Authentication ────────────────────────────────────

    def _authenticate(self) -> dict:
        """Perform DOORS NG form-based auth and get session cookie."""
        if self._session_cookie:
            return {"Cookie": self._session_cookie, "Accept": "application/rdf+xml"}

        auth_url = f"{self.base_url}/auth/j_security_check"
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.post(auth_url, data={
                "j_username": self.username,
                "j_password": self.password,
            })
            cookies = resp.cookies
            self._session_cookie = "; ".join(
                f"{k}={v}" for k, v in cookies.items()
            )

        return {
            "Cookie": self._session_cookie,
            "Accept": "application/rdf+xml",
            "OSLC-Core-Version": "2.0",
        }

    def _api(self, method: str, url: str, **kwargs) -> httpx.Response:
        headers = self._authenticate()
        with httpx.Client(timeout=60) as client:
            resp = client.request(method, url, headers=headers, **kwargs)
            resp.raise_for_status()
            return resp

    # ── Interface ─────────────────────────────────────────

    def test_connection(self) -> bool:
        try:
            headers = self._authenticate()
            catalog_url = f"{self.base_url}/rm/discovery/catalog"
            with httpx.Client(timeout=30) as client:
                resp = client.get(catalog_url, headers=headers)
                resp.raise_for_status()
            logger.info("DOORS NG connection OK")
            return True
        except Exception as exc:
            logger.warning("DOORS NG connection failed: %s", exc)
            return False

    def get_available_projects(self) -> list[dict]:
        """List project areas from the OSLC service catalog."""
        try:
            catalog_url = f"{self.base_url}/rm/discovery/catalog"
            resp = self._api("GET", catalog_url)
            root = ET.fromstring(resp.text)

            projects = []
            for sp in root.findall(".//oslc:ServiceProvider", NS):
                title = sp.find("dcterms:title", NS)
                about = sp.get(f"{{{NS['rdf']}}}about", "")
                projects.append({
                    "key": about,
                    "name": title.text if title is not None else about.rsplit("/", 1)[-1],
                    "id": about,
                })
            return projects
        except Exception as exc:
            logger.error("Failed to list DOORS projects: %s", exc)
            return []

    def fetch_items(self, external_project: str, **kwargs) -> list[ExternalItem]:
        """
        Fetch requirements from a DOORS module.
        If use_reqif is True, parses a ReqIF XML file path from kwargs instead.
        """
        if self.use_reqif:
            reqif_path = kwargs.get("reqif_path", "")
            if reqif_path:
                return self._parse_reqif(reqif_path)
            return []

        return self._fetch_via_oslc(external_project, **kwargs)

    def push_item(self, external_project: str, item: ExternalItem) -> str:
        """Create a requirement in DOORS via OSLC."""
        creation_factory = self._get_creation_factory(external_project)
        if not creation_factory:
            raise ValueError("No OSLC creation factory found for this project area")

        rdf = f"""<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="{NS['rdf']}"
         xmlns:dcterms="{NS['dcterms']}"
         xmlns:oslc_rm="{NS['oslc_rm']}">
  <oslc_rm:Requirement>
    <dcterms:title>{self._xml_escape(item.title)}</dcterms:title>
    <dcterms:description>{self._xml_escape(item.description)}</dcterms:description>
    <dcterms:identifier>{self._xml_escape(item.external_id)}</dcterms:identifier>
  </oslc_rm:Requirement>
</rdf:RDF>"""

        headers = self._authenticate()
        headers["Content-Type"] = "application/rdf+xml"
        with httpx.Client(timeout=30) as client:
            resp = client.post(creation_factory, headers=headers, content=rdf)
            resp.raise_for_status()

        # The Location header contains the URI of the new resource
        return resp.headers.get("Location", item.external_id)

    def receive_webhook(self, payload: dict) -> dict:
        """DOORS NG doesn't have native webhooks — this is a placeholder
        for TRS (Tracked Resource Set) polling or event push."""
        return {
            "event": "doors_event",
            "detail": "DOORS NG integration uses TRS polling, not webhooks",
            "action": "poll",
        }

    # ── OSLC Fetching ─────────────────────────────────────

    def _fetch_via_oslc(self, project_area_uri: str, **kwargs) -> list[ExternalItem]:
        """Query DOORS via OSLC with oslc.where or oslc.select."""
        max_results = kwargs.get("max_results", 200)

        # Get the query capability from the service provider
        query_base = self._get_query_capability(project_area_uri)
        if not query_base:
            logger.warning("No OSLC query capability found")
            return []

        params = {
            "oslc.pageSize": str(min(100, max_results)),
            "oslc.select": "dcterms:title,dcterms:description,dcterms:identifier,"
                           "oslc_rm:implementedBy",
        }

        items: list[ExternalItem] = []
        page_url = f"{query_base}"

        while page_url and len(items) < max_results:
            resp = self._api("GET", page_url, params=params)
            root = ET.fromstring(resp.text)

            for req in root.findall(".//oslc_rm:Requirement", NS):
                about = req.get(f"{{{NS['rdf']}}}about", "")
                title_el = req.find("dcterms:title", NS)
                desc_el = req.find("dcterms:description", NS)
                id_el = req.find("dcterms:identifier", NS)

                # Extract links
                links = []
                for link_el in req.findall("oslc_rm:implementedBy", NS):
                    target = link_el.get(f"{{{NS['rdf']}}}resource", "")
                    if target:
                        links.append({"type": "implementedBy", "target": target, "direction": "outward"})

                items.append(ExternalItem(
                    external_id=id_el.text if id_el is not None else about,
                    external_url=about,
                    title=title_el.text if title_el is not None else "",
                    description=desc_el.text if desc_el is not None else "",
                    item_type="requirement",
                    status="proposed",
                    priority="medium",
                    links=links,
                ))

            # OSLC paging: look for oslc:nextPage
            next_page = root.find(".//oslc:nextPage", NS)
            if next_page is not None:
                page_url = next_page.get(f"{{{NS['rdf']}}}resource", "")
                params = {}  # params are embedded in the next-page URL
            else:
                break

        return items

    def _get_query_capability(self, project_area_uri: str) -> str | None:
        """Find the OSLC query capability URL for requirements."""
        resp = self._api("GET", project_area_uri)
        root = ET.fromstring(resp.text)
        for qc in root.findall(".//oslc:queryCapability/oslc:QueryCapability", NS):
            resource_type = qc.find("oslc:resourceType", NS)
            if resource_type is not None:
                rt = resource_type.get(f"{{{NS['rdf']}}}resource", "")
                if "Requirement" in rt:
                    qb = qc.find("oslc:queryBase", NS)
                    if qb is not None:
                        return qb.get(f"{{{NS['rdf']}}}resource", "")
        return None

    def _get_creation_factory(self, project_area_uri: str) -> str | None:
        """Find the OSLC creation factory URL for requirements."""
        resp = self._api("GET", project_area_uri)
        root = ET.fromstring(resp.text)
        for cf in root.findall(".//oslc:creationFactory/oslc:CreationFactory", NS):
            resource_type = cf.find("oslc:resourceType", NS)
            if resource_type is not None:
                rt = resource_type.get(f"{{{NS['rdf']}}}resource", "")
                if "Requirement" in rt:
                    creation = cf.find("oslc:creation", NS)
                    if creation is not None:
                        return creation.get(f"{{{NS['rdf']}}}resource", "")
        return None

    # ── ReqIF Import ──────────────────────────────────────

    def _parse_reqif(self, file_path: str) -> list[ExternalItem]:
        """Parse a ReqIF XML file and extract requirements."""
        items: list[ExternalItem] = []
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()

            # ReqIF namespace varies; try common ones
            reqif_ns = ""
            for ns_uri in ["http://www.omg.org/spec/ReqIF/20110401/reqif.xsd",
                           "http://www.omg.org/spec/ReqIF/20110401"]:
                if root.tag.startswith(f"{{{ns_uri}}}"):
                    reqif_ns = ns_uri
                    break

            ns = {"reqif": reqif_ns} if reqif_ns else {}
            prefix = f"{{{reqif_ns}}}" if reqif_ns else ""

            for spec_obj in root.iter(f"{prefix}SPEC-OBJECT"):
                identifier = spec_obj.get("IDENTIFIER", "")
                long_name = spec_obj.get("LONG-NAME", "")
                desc = spec_obj.get("DESC", "")

                # Try to extract attribute values
                title = long_name or identifier
                statement = desc

                for val in spec_obj.iter(f"{prefix}ATTRIBUTE-VALUE-STRING"):
                    the_val = val.get("THE-VALUE", "")
                    # Heuristic: longest string is likely the statement
                    if len(the_val) > len(statement):
                        statement = the_val
                    elif not title or len(the_val) < len(title):
                        title = the_val

                items.append(ExternalItem(
                    external_id=identifier,
                    external_url="",
                    title=title,
                    description=statement,
                    item_type="requirement",
                    status="proposed",
                    priority="medium",
                    attributes={"doors_long_name": long_name},
                ))

        except Exception as exc:
            logger.error("ReqIF parse failed: %s", exc)

        return items

    @staticmethod
    def _xml_escape(text: str) -> str:
        return (text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))
