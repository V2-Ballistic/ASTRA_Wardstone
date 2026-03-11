"""
ASTRA — Integration Connectors Package
========================================
File: backend/app/services/integrations/__init__.py   ← NEW
"""

from app.services.integrations.base import IntegrationConnector, SyncResult
from app.services.integrations.jira import JiraConnector
from app.services.integrations.azure_devops import AzureDevOpsConnector
from app.services.integrations.doors import DoorsConnector

CONNECTOR_REGISTRY: dict[str, type[IntegrationConnector]] = {
    "jira": JiraConnector,
    "azure_devops": AzureDevOpsConnector,
    "doors": DoorsConnector,
}

__all__ = [
    "IntegrationConnector", "SyncResult", "CONNECTOR_REGISTRY",
    "JiraConnector", "AzureDevOpsConnector", "DoorsConnector",
]
