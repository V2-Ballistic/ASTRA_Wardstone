"""
ASTRA — Report Generation Package
===================================
File: backend/app/services/reports/__init__.py   ← NEW

Central registry so the router can look up generators by name.
"""

from app.services.reports.base import ReportGenerator, ReportOutput
from app.services.reports.traceability_matrix import TraceabilityMatrixReport
from app.services.reports.requirements_spec import RequirementsSpecReport
from app.services.reports.quality_report import QualityReport
from app.services.reports.compliance_matrix import ComplianceMatrixReport
from app.services.reports.status_dashboard import StatusDashboardReport
from app.services.reports.change_history import ChangeHistoryReport
from app.services.reports.icd_report import ICDReport


REPORT_REGISTRY: dict[str, type[ReportGenerator]] = {
    "traceability-matrix": TraceabilityMatrixReport,
    "requirements-spec": RequirementsSpecReport,
    "quality": QualityReport,
    "compliance": ComplianceMatrixReport,
    "status-dashboard": StatusDashboardReport,
    "change-history": ChangeHistoryReport,
    "icd": ICDReport,
}

__all__ = [
    "ReportGenerator", "ReportOutput", "REPORT_REGISTRY",
]
