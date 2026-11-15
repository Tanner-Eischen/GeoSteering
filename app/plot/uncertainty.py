import numpy as np
import plotly.graph_objects as go


def ensemble_figure(forecast, trajectory):
    x = forecast["x_ft"]
    fig = go.Figure()
    weights = np.asarray(forecast["weights"])
    indices = np.unique(np.searchsorted(np.cumsum(weights), (np.arange(24) + 0.5) / 24).clip(0, len(weights) - 1))
    for index, member in enumerate(indices):
        fig.add_trace(go.Scatter(x=x, y=forecast["members"]["center_tvd_ft"][member],
                                 name="Weighted model samples", legendgroup="samples", showlegend=index == 0,
                                 line={"color": "rgba(65,110,127,0.18)", "width": 1}, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=forecast["center"]["q05"], showlegend=False,
                             line={"width": 0}, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=forecast["center"]["q95"], name="90% model interval · center",
                             fill="tonexty", fillcolor="rgba(15,118,110,0.18)", line={"width": 0}))
    fig.add_trace(go.Scatter(x=x, y=forecast["center"]["q50"], name="Median center",
                             line={"color": "#0f766e", "width": 3}))
    for boundary, name in (("top", "Median top"), ("base", "Median base")):
        fig.add_trace(go.Scatter(x=x, y=forecast[boundary]["q50"], name=name,
                                 line={"color": "#b7791f", "dash": "dot"}))
    if not trajectory.empty:
        xcol = "x_ft" if "x_ft" in trajectory else "east_ft"
        path = trajectory.loc[trajectory[xcol] >= float(trajectory[xcol].iloc[-1]) - 250]
        fig.add_trace(go.Scatter(x=path[xcol], y=path.tvd_ft, mode="lines+markers", name="Acquired path",
                                 line={"color": "#234b65", "width": 3}, marker={"size": 5}))
    fig.update_layout(height=490, margin={"t": 15, "b": 175},
                      legend={"orientation": "h", "y": -0.4, "yanchor": "top"},
                      xaxis_title="Along-section x (ft)")
    fig.update_yaxes(autorange="reversed", title="TVD (ft), positive down")
    return fig
