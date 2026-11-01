"""Deterministic, browser-free report figures rendered with Matplotlib Agg."""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from app.alg.interpretation_model import evaluate_piecewise_linear
from app.report.context import report_context, report_markers
from app.services.decisions import load_decisions
from app.services.interpretations import get_latest_interpretation
from app.services.project_data import load_well_frames


def _metrics(context):
    from app.services.run_metrics import load_run_metrics

    rows = load_run_metrics(context["root"], run_id=context["run_id"])
    selected = context["include_steps"]
    if selected is not None:
        rows = [r for r in rows if r["step_index"] in selected]
    return rows


def generate_report_snapshots(
    project_root, *, run_id=None, plan_id=None, include_wells=None, include_steps=None, strict=False
):
    context = report_context(
        project_root, run_id=run_id, plan_id=plan_id, include_wells=include_wells, include_steps=include_steps
    )
    root, scope = context["root"], context["scope"]
    outdir = scope / "cache" / "report_snapshots"
    outdir.mkdir(parents=True, exist_ok=True)
    outputs = {}

    def save(name, fig):
        fig.tight_layout()
        path = outdir / f"{name}.png"
        try:
            fig.savefig(path, dpi=150, metadata={"Software": "GeoSteering Matplotlib Agg"})
        finally:
            plt.close(fig)
        if not path.is_file() or path.stat().st_size < 1000:
            raise RuntimeError(f"Missing or empty required figure: {name}")
        outputs[name] = path

    # Correlation is plotted in shared TVD; active measurements are bounded below.
    wells = context["wells"]
    if wells:
        fig, axes = plt.subplots(1, len(wells), figsize=(10, 4), squeeze=False)
        for ax, well in zip(axes[0], wells):
            frames = load_well_frames(root, well.well_id, run_id=context["run_id"])
            logs, traj = frames["logs"], frames["trajectory"]
            limit = context["revealed_md_ft"] if well.well_id == context["active_well_id"] else None
            if limit is not None:
                logs = logs[logs.md_ft <= limit]
                traj = traj[traj.md_ft <= limit]
            if len(logs) and len(traj):
                tvd = np.interp(logs.md_ft, traj.md_ft, traj.tvd_ft)
                ax.plot(logs.GR, tvd, lw=0.7, color="#244b7a")
                for marker in report_markers(context, well.well_id):
                    if limit is None or marker.md_ft <= limit:
                        y = np.interp(marker.md_ft, traj.md_ft, traj.tvd_ft)
                        ax.axhline(y, lw=0.7, color="#b44f32")
                        ax.annotate(marker.name, (0, y), fontsize=6)
            ax.set(title=well.name, xlabel="GR (API)", ylabel="TVD (ft, positive down)")
            marker_depths = [
                np.interp(m.md_ft, traj.md_ft, traj.tvd_ft)
                for m in report_markers(context, well.well_id)
                if len(traj) and (limit is None or m.md_ft <= limit)
            ]
            if marker_depths:
                ax.set_ylim(min(marker_depths) - 60.0, max(marker_depths) + 60.0)
            ax.invert_yaxis()
        fig.suptitle("Observed logs and geological marker constraints")
        save("correlation_snapshot", fig)

    plan = context["plan"]
    if plan:
        stations = pd.read_parquet(root / plan["stations_path"])
        fig, ax = plt.subplots(figsize=(10, 3))
        ax.plot(stations.md_ft, stations.tvd_ft, color="#244b7a")
        ax.set(xlabel="Planned MD (ft)", ylabel="TVD (ft)", title=f"Plan: {plan['name']}")
        ax.invert_yaxis()
        save("plan_profile", fig)
        fig, ax = plt.subplots(figsize=(10, 3))
        ax.plot(stations.md_ft, stations.dls_deg_per_100ft)
        ax.axhline(plan["dls_max_deg_per_100ft"], color="#b44f32", ls="--", label="DLS limit")
        ax.set(xlabel="Planned MD (ft)", ylabel="DLS (degrees/100 ft)", title="Planned dogleg severity")
        ax.legend()
        save("dls_profile", fig)

    interpretation = get_latest_interpretation(scope)
    if interpretation and context["active_well_id"] in {well.well_id for well in wells}:
        traj = load_well_frames(root, context["active_well_id"], run_id=context["run_id"])["trajectory"]
        limit = context["revealed_md_ft"]
        if limit is not None:
            traj = traj[traj.md_ft <= limit]
        lateral_start = context["config"].get("lateral_start_md_ft")
        if lateral_start is not None:
            traj = traj[traj.md_ft >= lateral_start]
        if len(traj):
            spatial = all(getattr(cp, "x_ft", None) is not None for cp in interpretation.top_control_points)
            query = traj["x_ft" if "x_ft" in traj else "east_ft"] if spatial else traj.md_ft
            top = evaluate_piecewise_linear(interpretation.top_control_points, query)
            base = evaluate_piecewise_linear(interpretation.base_control_points, query)
            fig, ax = plt.subplots(figsize=(10, 3.5))
            ax.fill_between(query, top, base, color="#b7d4b2", alpha=0.6, label="Estimated target")
            causal = context["config"].get("mode") == "causal"
            ax.plot(
                query,
                traj.tvd_ft,
                color="#244b7a",
                label="Acquired causal trajectory" if causal else "Revealed recorded trajectory",
            )
            ax.set(
                xlabel="Along-track x (ft)" if spatial else "MD (ft)",
                ylabel="TVD (ft)",
                title="Causal trajectory and estimated target"
                if causal
                else "Interpretation replay: recommendations do not change the recorded path",
            )
            ax.invert_yaxis()
            ax.legend(fontsize=7)
            save("interpretation_overlay", fig)

    rows = _metrics(context) if context["run_id"] else []
    if rows:
        fig, ax = plt.subplots(figsize=(10, 3))
        ax.plot([r["step_index"] for r in rows], [r["percent_in_zone"] for r in rows], marker=".")
        ax.set(
            xlabel="Replay step",
            ylabel="Estimated lateral in-zone (%)",
            ylim=(-2, 102),
            title="Persisted decision-time metrics (each original interpretation version)",
        )
        save("kpi_trend", fig)
    decisions = load_decisions(scope)
    if context["include_steps"] is not None:
        decisions = [d for d in decisions if d.step_index in context["include_steps"]]
    if decisions:
        fig, ax = plt.subplots(figsize=(10, 2.5))
        codes = {"DROP": -1, "HOLD": 0, "BUILD": 1}
        ax.step([d.step_index for d in decisions], [codes[d.recommendation.action] for d in decisions], where="mid")
        ax.set(
            xlabel="Replay step",
            yticks=[-1, 0, 1],
            yticklabels=["DROP", "HOLD", "BUILD"],
            title="Recorded recommendations and evidence timeline",
        )
        save("decision_timeline", fig)

    comparison_path = scope / "evaluation" / "comparison.json"
    if context["state"].get("complete") and comparison_path.exists():
        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        fig, axes = plt.subplots(1, 2, figsize=(10, 3.5))
        runs = comparison["runs"]
        truth_path = scope / "evaluation" / "truth_profile.json"
        if truth_path.exists():
            truth = json.loads(truth_path.read_text(encoding="utf-8"))
            axes[0].fill_between(
                truth["x_ft"],
                truth["top_tvd_ft"],
                truth["base_tvd_ft"],
                color="#b7d4b2",
                alpha=0.6,
                label="Withheld true target",
            )
        strategy_colors = {"hold": "#b44f32", "guided": "#244b7a"}
        ordered_names = [name for name in ("hold", "guided") if name in runs]
        for name in ordered_names:
            run = runs[name]
            traj = pd.DataFrame(run["trajectory"])
            traj = traj[traj.md_ft >= context["config"].get("lateral_start_md_ft", 2000.0)]
            axes[0].plot(traj["x_ft"], traj.tvd_ft, label=name, color=strategy_colors[name])
        axes[0].invert_yaxis()
        axes[0].set(xlabel="Along-track x (ft)", ylabel="TVD (ft)", title="Controlled causal trajectories")
        axes[0].legend()
        axes[1].bar(ordered_names, [runs[name]["metrics"]["percent_in_zone"] for name in ordered_names], color=[strategy_colors[name] for name in ordered_names])
        axes[1].set(ylabel="True lateral in-zone (%)", ylim=(0, 105), title="Independent final evaluation")
        save("strategy_comparison", fig)

    if strict:
        required = {
            "correlation_snapshot",
            "plan_profile",
            "dls_profile",
            "interpretation_overlay",
            "kpi_trend",
            "decision_timeline",
        }
        if context["state"].get("complete"):
            required.add("strategy_comparison")
        missing = required - outputs.keys()
        if missing:
            raise RuntimeError(f"Required report figures missing: {sorted(missing)}")
    return outputs
