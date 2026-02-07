from __future__ import annotations

from typing import Mapping, Sequence

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def build_correlation_figure(
    logs_by_well: Mapping[str, pd.DataFrame],
    markers_by_well: Mapping[str, Sequence[dict]] | None = None,
    curves: Sequence[str] | None = None,
    depth_min: float | None = None,
    depth_max: float | None = None,
    display_shifts_ft: Mapping[str, float] | None = None,
) -> go.Figure:
    well_names = list(logs_by_well.keys())
    if not well_names:
        fig = go.Figure()
        fig.update_layout(title="No wells selected")
        return fig

    selected_curves = list(curves or ["GR", "RES"])
    shifts = display_shifts_ft or {}
    markers_by_well = markers_by_well or {}

    fig = make_subplots(rows=1, cols=len(well_names), shared_yaxes=True, subplot_titles=well_names)
    for i, well_name in enumerate(well_names, start=1):
        df = logs_by_well[well_name].copy().sort_values("md_ft")
        if depth_min is not None:
            df = df[df["md_ft"] >= float(depth_min)]
        if depth_max is not None:
            df = df[df["md_ft"] <= float(depth_max)]
        shift = float(shifts.get(well_name, 0.0))
        y = df["md_ft"] + shift

        for curve in selected_curves:
            if curve not in df.columns:
                continue
            fig.add_trace(
                go.Scatter(x=df[curve], y=y, mode="lines", name=f"{well_name}:{curve}", showlegend=False),
                row=1,
                col=i,
            )

        for marker in markers_by_well.get(well_name, []):
            y_val = float(marker["md_ft"]) + shift
            fig.add_hline(
                y=y_val,
                line_dash="dot",
                line_color="#9e9e9e",
                row=1,
                col=i,
                annotation_text=str(marker.get("name", "")),
                annotation_position="top left",
            )

        fig.update_xaxes(title_text="/".join([c for c in selected_curves if c in df.columns]), row=1, col=i)

    fig.update_yaxes(autorange="reversed", title_text="MD (ft)")
    fig.update_layout(height=780, margin={"l": 32, "r": 16, "t": 64, "b": 32})
    return fig

