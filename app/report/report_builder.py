"""PDF exports pinned to explicit runs, plans, observations and metric snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.io.project_store import read_json
from app.report.context import report_context, report_markers
from app.report.snapshots import generate_report_snapshots
from app.services.decisions import load_decisions
from app.services.interpretations import get_latest_interpretation


def build_report(
    project_root, *, run_id=None, plan_id=None, include_wells=None, include_steps=None, strict=False
) -> Path:
    context = report_context(
        project_root, run_id=run_id, plan_id=plan_id, include_wells=include_wells, include_steps=include_steps
    )
    root, scope = context["root"], context["scope"]
    project, state = context["project"], context["state"]
    mode = context["config"].get("mode", "replay")
    snapshots = generate_report_snapshots(
        root,
        run_id=context["run_id"],
        plan_id=context["plan"]["plan_id"] if context["plan"] else None,
        include_wells=include_wells,
        include_steps=include_steps,
        strict=strict,
    )
    suffix = f"_{context['run_id']}" if context["run_id"] else ""
    out = root / "exports" / f"report_{project.name.replace(' ', '_')}{suffix}.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    styles["Normal"].fontSize = 8
    styles["Normal"].leading = 11
    story = []

    def text(value, style="Normal"):
        story.append(Paragraph(escape(str(value)), styles[style]))

    def heading(value):
        story.append(Spacer(1, 9))
        text(value, "Heading2")

    def table(rows, widths=None):
        cells = [[Paragraph(escape(str(cell)), styles["Normal"]) for cell in row] for row in rows]
        obj = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
        obj.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5edf3")),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(obj)

    def figure(name, height=175):
        if name in snapshots:
            story.append(Spacer(1, 7))
            story.append(Image(str(snapshots[name]), width=480, height=height, kind="proportional"))

    text("Geosteering Under Structural Uncertainty", "Title")
    text(f"Project: {project.name}")
    text(
        f"Synthetic {mode} run and simplified causal comparison. Training and portfolio tool; not validated for live operations."
    )
    text(f"Run ID: {context['run_id'] or 'legacy project'}")
    text(
        f"Status: {'COMPLETE' if state.get('complete') else 'PARTIAL / exploratory'}; revealed MD (ft): {context['revealed_md_ft']}"
    )
    manifest = read_json(scope / "manifest.json", default={})
    comparison_file = scope / "evaluation" / "comparison.json"
    if state.get("complete") and comparison_file.exists():
        completed_comparison = read_json(comparison_file)["runs"]
        hold = completed_comparison["hold"]["metrics"]
        guided = completed_comparison["guided"]["metrics"]
        heading("Measured result")
        text(
            f"Over the same {hold['evaluated_length_ft']:.0f}-ft lateral, HOLD placed {hold['percent_in_zone']:.2f}% "
            f"({hold['in_zone_length_ft']:.1f} ft) in zone; the observation-guided causal policy placed "
            f"{guided['percent_in_zone']:.2f}% ({guided['in_zone_length_ft']:.1f} ft) in zone. "
            f"Lateral DLS violation counts: HOLD {hold['dls_violation_count']}, guided {guided['dls_violation_count']}. "
            "This controlled synthetic result relies on the disclosed signed layer calibration. "
            "Replay recommendations did not change the recorded path."
        )
    if strict and not manifest:
        raise ValueError("Strict report requires a saved run provenance manifest")
    for key in ("scenario_version", "seed", "code_revision", "dirty_working_tree", "coordinate_reference"):
        if key in manifest:
            text(f"{key}: {manifest[key]}")

    heading("Data summary and QC")
    rows = [["Well", "Curves", "QC valid", "Warnings"]]
    for well in context["wells"]:
        qc = well.qc_summary or {}
        rows.append(
            [
                well.name,
                ", ".join(sorted(well.curve_inventory)),
                qc.get("valid"),
                "; ".join(w.get("message", "") for w in qc.get("warnings", [])),
            ]
        )
    table(rows, [100, 80, 60, 240])
    if manifest.get("input_hashes"):
        heading("Input provenance (SHA-256)")
        selected_names = {well.name for well in context["wells"]}
        for name, digest in manifest["input_hashes"].items():
            parts = Path(name).parts
            if include_wells is None or "wells" not in parts or parts[parts.index("wells") + 1] in selected_names:
                text(f"{name}: {digest}")

    heading("Correlation and markers")
    text(
        "Offset formation picks constrain a regional estimate in shared along-track x and local TVD. Active observations and markers are limited to the saved revealed depth."
    )
    rows = [["Well", "Marker", "MD (ft)"]]
    for well in context["wells"]:
        for marker in report_markers(context, well.well_id):
            if (
                well.well_id == context["active_well_id"]
                and context["revealed_md_ft"] is not None
                and marker.md_ft > context["revealed_md_ft"]
            ):
                continue
            rows.append([well.name, marker.name, f"{marker.md_ft:.2f}"])
    table(rows, [160, 200, 120])
    figure("correlation_snapshot", 200)

    heading("Pre-spud plan and DLS")
    plan = context["plan"]
    if plan:
        text(f"Plan name: {plan['name']}; Plan ID: {plan['plan_id']}")
        text(
            f"Max DLS constraint: {plan['dls_max_deg_per_100ft']} degrees/100 ft; exceedance count: {len(plan.get('dls_exceedances', []))}"
        )
    else:
        text("No saved plan selected.")
    figure("plan_profile", 150)
    figure("dls_profile", 150)

    heading("Steering decisions and KPI results")
    if mode == "causal":
        text(
            "Applied commands change the acquired synthetic trajectory under bounded DLS. Estimated metrics are frozen at each reveal using the cited interpretation, and exclude the build/landing interval."
        )
    else:
        text(
            "Replay recommendations do not change the recorded trajectory. Estimated metrics are frozen at each reveal using the cited interpretation, and exclude the build/landing interval."
        )
    decisions = load_decisions(scope)
    if include_steps is not None:
        decisions = [d for d in decisions if d.step_index in include_steps]
    rows = [["Step", "MD interval (ft)", "Action", "Evidence / interpretation version"]]
    for decision in decisions:
        rows.append(
            [
                decision.step_index,
                f"{decision.md_from_ft:.0f}-{decision.md_to_ft:.0f}",
                decision.recommendation.action,
                f"{decision.observations}; version {decision.interpretation_version_id}",
            ]
        )
    table(rows, [30, 75, 50, 325])
    if context["run_id"]:
        from app.services.run_metrics import load_run_metrics

        metrics = load_run_metrics(root, run_id=context["run_id"])
        if include_steps is not None:
            metrics = [m for m in metrics if m["step_index"] in include_steps]
        rows = [["Step", "Revealed MD (ft)", "Estimated in-zone (%)", "Mean center distance (ft)"]]
        for metric in metrics:
            rows.append(
                [
                    metric["step_index"],
                    f"{metric['revealed_md_ft']:.0f}",
                    f"{metric['percent_in_zone']:.3f}",
                    f"{metric['avg_center_distance']:.3f}",
                ]
            )
        table(rows, [35, 100, 150, 195])
    figure("kpi_trend", 145)
    figure("decision_timeline", 130)

    heading("Final interpretation")
    interpretation = get_latest_interpretation(scope)
    if interpretation:
        text(f"Interpretation version: {interpretation.version_id}; rationale: {interpretation.rationale}")
        text(
            f"Assumed uncertainty band (ft): {interpretation.uncertainty.band_tvd_ft}. This scenario-assumed range is not a calibrated statistical confidence interval."
        )
    else:
        text("No interpretation history found.")
    figure("interpretation_overlay", 175)

    heading("Independent evaluation")
    evaluation = scope / "evaluation" / "replay.json"
    comparison_path = scope / "evaluation" / "comparison.json"
    if state.get("complete") and evaluation.exists():
        result = json.loads(evaluation.read_text(encoding="utf-8"))
        if mode == "causal":
            text(
                "Withheld geological truth was used only after the causal run completed. The acquired path reflects applied bounded commands."
            )
        else:
            text(
                "Withheld geological truth was used only after the replay completed. Replay evaluation measures interpretation and fixed-path placement, not steering efficacy."
            )
        for key, value in result.items():
            text(f"{key}: {value}")
        if comparison_path.exists():
            comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
            rows = [["Causal strategy", "True in-zone (%)", "In-zone / evaluated length (ft)", "Maximum lateral DLS"]]
            for name, run in comparison["runs"].items():
                metric = run["metrics"]
                rows.append(
                    [
                        name,
                        f"{metric['percent_in_zone']:.3f}",
                        f"{metric['in_zone_length_ft']:.1f} / {metric['evaluated_length_ft']:.1f}",
                        f"{metric['max_dls_deg_per_100ft']:.4f}",
                    ]
                )
            table(rows, [80, 90, 180, 130])
        figure("strategy_comparison", 180)
    elif strict and state.get("complete"):
        raise ValueError("Completed strict report requires independent evaluation")
    else:
        text(
            "Withheld truth evaluation unavailable until completion. This partial report contains estimated metrics only."
        )

    heading("Assumptions and limitations")
    text(
        "Synthetic calibration: GR = 80 + 2*(TVD - target center) API, clipped to 20-160 API, with 0.6 API Gaussian noise. This deliberately signed layer signal is known to the synthetic operator; real gamma-ray inversion does not generally provide this information. Saturation cannot identify an exact center and is logged as unresolved evidence."
    )
    text(
        "Scoring: estimated zones use exact piecewise-linear MD interval integration. Nonlinear withheld geology uses at most 1-ft intervals with boundary-crossing interpolation; reference refinement to 0.1 ft changes in-zone results by less than 0.001 percentage points. The final-point indicator is not an interval-length percentage."
    )
    text(
        "Coordinates: feet; MD along the well, local TVD positive down, along-track x eastward. Minimum-curvature integration uses survey inclination and azimuth. Layer metrics are length weighted over the lateral interval with an explicit evaluated-length denominator."
    )
    text(
        "The operator baseline uses offset picks only. Subsequent interpretations may use only revealed active measurements. Geological truth remains fixed and is isolated from live interpretations and recommendations."
    )
    text(
        "Causal trials share geology, initial state, seed and trajectory constraints. HOLD/BUILD/DROP use a simplified bounded kinematic response. Report measured outcomes, including failure; no production drilling, sensor physics or operational safety claims are made."
    )
    text(
        "Idealized 2D geology and synthetic GR/resistivity response; sparse offsets and assumed uncertainty. No real-time telemetry or WITSML support. Numerical summaries are reproducible; PDF timestamps and run identifiers can differ."
    )
    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#56616c"))
        canvas.drawString(54, 30, "GeoSteering | Synthetic scientific case study")
        canvas.drawRightString(558, 30, f"Page {document.page}")
        canvas.restoreState()

    SimpleDocTemplate(
        str(out), pagesize=letter, title="GeoSteering scientific case study",
        leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=48,
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    return out
