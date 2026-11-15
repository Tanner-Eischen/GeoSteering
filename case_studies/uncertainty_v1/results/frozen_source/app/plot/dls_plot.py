from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def build_dls_figure(stations: pd.DataFrame, max_dls_deg_per_100ft: float) -> go.Figure:
    fig = go.Figure(
        data=[
            go.Scatter(
                x=stations["md_ft"],
                y=stations["dls_deg_per_100ft"],
                mode="lines",
                name="DLS",
                line={"color": "#d84315"},
            )
        ]
    )
    fig.add_hline(y=max_dls_deg_per_100ft, line_dash="dash", line_color="#c62828")
    fig.update_layout(height=360, xaxis_title="MD (ft)", yaxis_title="DLS (deg/100ft)")
    return fig

