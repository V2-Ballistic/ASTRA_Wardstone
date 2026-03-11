"""
ASTRA — Status Dashboard Report
==================================
File: backend/app/services/reports/status_dashboard.py   ← NEW

Project status snapshot including:
  - Requirement counts by status, type, priority, level
  - Verification progress
  - Traceability coverage
  - Baseline history
  - Recent activity timeline (last 30 changes)

Format: PDF (reportlab)
"""

import io
from datetime import datetime
from collections import Counter

from sqlalchemy.orm import Session

from app.models import (
    Requirement, Verification, TraceLink, Baseline,
    RequirementHistory, User,
)
from app.services.reports.base import ReportGenerator, ReportOutput


class StatusDashboardReport(ReportGenerator):
    name = "status-dashboard"
    supported_formats = ["pdf"]

    def generate(self, project_id: int, db: Session, options: dict | None = None) -> ReportOutput:
        project = self._get_project(db, project_id)
        reqs = self._get_requirements(db, project_id)
        req_ids = [r.id for r in reqs]
        links = self._get_trace_links(db, req_ids)
        verifs = self._get_verifications(db, req_ids)
        baselines = db.query(Baseline).filter(
            Baseline.project_id == project_id
        ).order_by(Baseline.created_at.desc()).limit(10).all()
        history = self._get_history(db, req_ids)[:30]

        # Counts
        by_status = Counter(self._enum_val(r.status) for r in reqs)
        by_type = Counter(self._enum_val(r.req_type) for r in reqs)
        by_priority = Counter(self._enum_val(r.priority) for r in reqs)
        by_level = Counter(self._enum_val(r.level) if hasattr(r, "level") else "L1" for r in reqs)

        # Verification
        v_pass = sum(1 for rid, vl in verifs.items() for v in vl if self._enum_val(v.status) == "pass")
        v_fail = sum(1 for rid, vl in verifs.items() for v in vl if self._enum_val(v.status) == "fail")
        v_planned = sum(1 for rid, vl in verifs.items() for v in vl if self._enum_val(v.status) == "planned")
        v_total = sum(len(vl) for vl in verifs.values())

        # Traceability
        linked = set()
        for l in links:
            if l.source_type == "requirement":
                linked.add(l.source_id)
            if l.target_type == "requirement":
                linked.add(l.target_id)
        trace_pct = round(len(linked) / len(req_ids) * 100, 1) if req_ids else 0

        # Quality
        scores = [r.quality_score or 0 for r in reqs]
        avg_quality = round(sum(scores) / len(scores), 1) if scores else 0
        pass_count = sum(1 for s in scores if s >= 70)

        summary = {
            "project": project.code,
            "total": len(reqs),
            "generated_at": datetime.utcnow().isoformat(),
        }

        return self._to_pdf(
            project, reqs, by_status, by_type, by_priority, by_level,
            v_pass, v_fail, v_planned, v_total,
            trace_pct, linked, avg_quality, pass_count,
            baselines, history, db, summary,
        )

    def _to_pdf(self, project, reqs, by_status, by_type, by_priority, by_level,
                v_pass, v_fail, v_planned, v_total,
                trace_pct, linked, avg_quality, pass_count,
                baselines, history, db, summary) -> ReportOutput:
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
        )
        from reportlab.lib.styles import getSampleStyleSheet

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=LETTER)
        styles = getSampleStyleSheet()
        el = []

        dark = colors.Color(0.12, 0.16, 0.22)
        grid = colors.Color(0.8, 0.8, 0.8)
        base_style = [
            ("BACKGROUND", (0, 0), (-1, 0), dark),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, grid),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ]

        # ── Title ──
        el.append(Paragraph(
            f"<b>Project Status Dashboard — {project.code}</b>", styles["Title"]))
        el.append(Paragraph(
            f"{project.name} | {summary['generated_at']}", styles["Normal"]))
        el.append(Spacer(1, 20))

        # ── Key Metrics ──
        el.append(Paragraph("<b>Key Metrics</b>", styles["Heading2"]))
        kpi = [
            ["Metric", "Value"],
            ["Total Requirements", str(len(reqs))],
            ["Traceability Coverage", f"{trace_pct}%"],
            ["Avg Quality Score", str(avg_quality)],
            ["Quality Pass Rate", f"{round(pass_count/len(reqs)*100,1) if reqs else 0}%"],
            ["Verification Records", str(v_total)],
            ["Baselines", str(len(baselines))],
        ]
        el.append(Table(kpi, colWidths=[3*inch, 2*inch],
                        style=TableStyle(base_style)))
        el.append(Spacer(1, 16))

        # ── By Status ──
        el.append(Paragraph("<b>Requirements by Status</b>", styles["Heading2"]))
        status_data = [["Status", "Count"]] + [[k, str(v)] for k, v in sorted(by_status.items())]
        el.append(Table(status_data, colWidths=[3*inch, 1.5*inch],
                        style=TableStyle(base_style)))
        el.append(Spacer(1, 12))

        # ── By Type ──
        el.append(Paragraph("<b>Requirements by Type</b>", styles["Heading2"]))
        type_data = [["Type", "Count"]] + [[k, str(v)] for k, v in sorted(by_type.items())]
        el.append(Table(type_data, colWidths=[3*inch, 1.5*inch],
                        style=TableStyle(base_style)))
        el.append(Spacer(1, 12))

        # ── By Priority ──
        el.append(Paragraph("<b>Requirements by Priority</b>", styles["Heading2"]))
        pri_data = [["Priority", "Count"]] + [[k, str(v)] for k, v in sorted(by_priority.items())]
        el.append(Table(pri_data, colWidths=[3*inch, 1.5*inch],
                        style=TableStyle(base_style)))
        el.append(Spacer(1, 12))

        # ── Verification ──
        el.append(Paragraph("<b>Verification Progress</b>", styles["Heading2"]))
        ver_data = [
            ["Status", "Count"],
            ["Pass", str(v_pass)],
            ["Fail", str(v_fail)],
            ["Planned", str(v_planned)],
            ["In Progress", str(v_total - v_pass - v_fail - v_planned)],
        ]
        el.append(Table(ver_data, colWidths=[3*inch, 1.5*inch],
                        style=TableStyle(base_style)))

        # ── Baselines ──
        el.append(PageBreak())
        el.append(Paragraph("<b>Baseline History</b>", styles["Heading2"]))
        if baselines:
            bl_data = [["Baseline", "Requirements", "Date"]]
            for bl in baselines:
                bl_data.append([
                    bl.name,
                    str(bl.requirements_count if hasattr(bl, "requirements_count") else "—"),
                    self._ts(bl.created_at),
                ])
            el.append(Table(bl_data, colWidths=[3*inch, 1.2*inch, 1.8*inch],
                            style=TableStyle(base_style)))
        else:
            el.append(Paragraph("No baselines recorded.", styles["Normal"]))
        el.append(Spacer(1, 16))

        # ── Recent Activity ──
        el.append(Paragraph("<b>Recent Activity (last 30 changes)</b>", styles["Heading2"]))
        if history:
            act_data = [["Date", "Req", "Field", "By"]]
            for h in history[:30]:
                req = db.query(Requirement).filter(Requirement.id == h.requirement_id).first()
                user = db.query(User).filter(User.id == h.changed_by_id).first() if h.changed_by_id else None
                act_data.append([
                    self._ts(h.changed_at),
                    req.req_id if req else "?",
                    h.field_changed or "—",
                    user.full_name if user else "System",
                ])
            el.append(Table(act_data, repeatRows=1,
                            colWidths=[1.5*inch, 1.2*inch, 2*inch, 1.5*inch],
                            style=TableStyle(base_style + [("FONTSIZE", (0,0),(-1,-1), 8)])))
        else:
            el.append(Paragraph("No recent activity.", styles["Normal"]))

        doc.build(el)
        return ReportOutput(
            content=buf.getvalue(),
            filename=f"Status_{project.code}_{datetime.utcnow().strftime('%Y%m%d')}.pdf",
            content_type="application/pdf",
            metadata=summary,
        )
