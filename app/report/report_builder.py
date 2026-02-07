from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.alg.kpi import compute_kpis
from app.io.project_store import load_project, read_json
from app.report.snapshots import generate_report_snapshots
from app.services.decisions import load_decisions
from app.services.interpretations import get_latest_interpretation
from app.services.markers import load_markers
from app.services.project_data import load_project_and_wells, load_well_frames


def _table_from_rows(rows: list[list[object]], col_widths: Iterable[float] | None = None) -> Table:
    table = Table(rows, colWidths=col_widths)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0e0e0")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def build_report(project_root: str | Path) -> Path:
    root = Path(project_root)
    project = load_project(root)
    snapshots = generate_report_snapshots(root)
    out_path = root / "exports" / f"report_{project.name.replace(' ', '_')}.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Geosteering Workbench MVP Report", styles["Title"]))
    story.append(Paragraph(f"Project: {project.name}", styles["Normal"]))
    story.append(Paragraph("Training and portfolio tool. Not validated for live operations.", styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Data summary and QC", styles["Heading2"]))
    _, wells = load_project_and_wells(root)
    qc_rows = [["Well", "Curves", "QC Valid", "Warnings"]]
    for well in wells:
        qc = well.qc_summary or {}
        qc_rows.append(
            [
                well.name,
                ", ".join(sorted(well.curve_inventory.keys())),
                str(qc.get("valid")),
                "; ".join([w.get("message", "") for w in qc.get("warnings", [])]),
            ]
        )
    story.append(_table_from_rows(qc_rows))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Correlation and markers", styles["Heading2"]))
    if "correlation_snapshot" in snapshots:
        story.append(Image(str(snapshots["correlation_snapshot"]), width=500, height=300))
        story.append(Spacer(1, 6))
    marker_rows = [["Well", "Marker", "MD (ft)"]]
    for well in wells:
        markers = load_markers(root, well.well_id)
        for marker in markers:
            marker_rows.append([well.name, marker.name, f"{marker.md_ft:.2f}"])
    if len(marker_rows) == 1:
        marker_rows.append(["-", "-", "-"])
    story.append(_table_from_rows(marker_rows))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Pre-spud plan and DLS", styles["Heading2"]))
    plan_jsons = sorted((root / "plans").glob("*.json"))
    if plan_jsons:
        latest_plan = read_json(plan_jsons[-1])
        story.append(Paragraph(f"Plan name: {latest_plan['name']}", styles["Normal"]))
        story.append(Paragraph(f"Max DLS: {latest_plan['dls_max_deg_per_100ft']}", styles["Normal"]))
        exceed = latest_plan.get("dls_exceedances", [])
        story.append(Paragraph(f"DLS exceedance count: {len(exceed)}", styles["Normal"]))
    else:
        story.append(Paragraph("No saved plan found.", styles["Normal"]))
    if "plan_profile" in snapshots:
        story.append(Image(str(snapshots["plan_profile"]), width=500, height=220))
    if "dls_profile" in snapshots:
        story.append(Image(str(snapshots["dls_profile"]), width=500, height=220))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Steering decisions and KPI results", styles["Heading2"]))
    decisions = load_decisions(root)
    decision_rows = [["Step", "MD from", "MD to", "Action", "Interpretation Version", "Observations"]]
    for d in decisions:
        decision_rows.append(
            [
                d.step_index,
                f"{d.md_from_ft:.1f}",
                f"{d.md_to_ft:.1f}",
                d.recommendation.action,
                d.interpretation_version_id,
                d.observations,
            ]
        )
    if len(decision_rows) == 1:
        decision_rows.append(["-", "-", "-", "-", "-", "-"])
    story.append(_table_from_rows(decision_rows))
    if "kpi_trend" in snapshots:
        story.append(Image(str(snapshots["kpi_trend"]), width=500, height=180))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Final interpretation", styles["Heading2"]))
    latest_interp = get_latest_interpretation(root)
    if latest_interp:
        interp_rows = [["MD (ft)", "Top TVD (ft)", "Base TVD (ft)"]]
        max_len = max(len(latest_interp.top_control_points), len(latest_interp.base_control_points))
        for i in range(max_len):
            top = latest_interp.top_control_points[i] if i < len(latest_interp.top_control_points) else None
            base = latest_interp.base_control_points[i] if i < len(latest_interp.base_control_points) else None
            interp_rows.append(
                [
                    f"{(top.md_ft if top else base.md_ft):.1f}" if (top or base) else "-",
                    f"{top.tvd_ft:.2f}" if top else "-",
                    f"{base.tvd_ft:.2f}" if base else "-",
                ]
            )
        story.append(_table_from_rows(interp_rows))

        if project.active_well_id:
            traj = load_well_frames(root, project.active_well_id)["trajectory"]
            kpi = compute_kpis(
                trajectory_df=traj,
                top_control_points=latest_interp.top_control_points,
                base_control_points=latest_interp.base_control_points,
                md_from_ft=float(traj["md_ft"].min()),
                md_to_ft=float(traj["md_ft"].max()),
                step_ft=1.0,
            )
            story.append(Paragraph(f"Percent in zone: {kpi.percent_in_zone:.2f}", styles["Normal"]))
            story.append(Paragraph(f"Avg center distance (ft): {kpi.avg_center_distance:.2f}", styles["Normal"]))
    else:
        story.append(Paragraph("No interpretation history found.", styles["Normal"]))
    if "interpretation_overlay" in snapshots:
        story.append(Image(str(snapshots["interpretation_overlay"]), width=500, height=220))

    story.append(Spacer(1, 12))
    story.append(Paragraph("Assumptions and limitations", styles["Heading2"]))
    story.append(Paragraph("Logs and markers use MD (ft); vertical metrics use TVD (ft).", styles["Normal"]))
    story.append(Paragraph("Single-user local MVP with deterministic synthetic data workflow.", styles["Normal"]))
    story.append(Paragraph("No real-time streaming or WITSML support in MVP.", styles["Normal"]))

    doc = SimpleDocTemplate(str(out_path), pagesize=letter, title=f"Report {project.name}")
    doc.build(story)
    return out_path

