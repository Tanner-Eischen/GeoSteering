from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def build_plan_profile_figure(stations: pd.DataFrame) -> go.Figure:
    fig = go.Figure(
        data=[
            go.Scatter(
                x=stations["md_ft"],
                y=stations["tvd_ft"],
                mode="lines",
                name="Plan profile",
                line={"color": "#1b5e20"},
            )
        ]
    )
    fig.update_layout(height=360, xaxis_title="MD (ft)", yaxis_title="TVD (ft)")
    return fig

