import json

from streamlit.testing.v1 import AppTest


def compact_chart():
    return AppTest.from_string('''
import streamlit as st
import plotly.graph_objects as go
from app.ui.charts import render_chart
scale = st.number_input("Scale", value=1)
render_chart(
    go.Figure(go.Scatter(x=[0, 1], y=[0, scale])),
    key="compact_chart", compact=True, help_text="Graph help stays with its controls.",
)
''', default_timeout=20).run()


def test_compact_chart_keeps_controls_and_guidance_in_popover():
    app = compact_chart()
    assert not app.exception
    popover = app.get("popover")[0]
    assert popover.proto.popover.label == "Chart controls"
    assert popover.radio[0].label == "Drag to"
    assert popover.checkbox[0].label == "Wheel zoom"
    assert popover.button[0].label == "Reset view"
    assert popover.caption[0].value == "Graph help stays with its controls."
    assert not popover.get("plotly_chart")
    assert not any(child.type == "caption" for child in app.main.children.values())
    assert len(app.get("plotly_chart")) == 1
    assert json.loads(app.get("plotly_chart")[0].proto.config)["scrollZoom"] is False


def test_compact_interaction_changes_preserve_view_and_reset_remains_explicit():
    app = compact_chart()

    def layout():
        return json.loads(app.get("plotly_chart")[0].proto.spec)["layout"]

    initial = layout()["uirevision"]
    app.radio(key="compact_chart_drag").set_value("Box zoom").run()
    assert layout()["dragmode"] == "zoom"
    assert layout()["uirevision"] == initial
    app.checkbox(key="compact_chart_wheel").check().run()
    assert json.loads(app.get("plotly_chart")[0].proto.config)["scrollZoom"] is True
    assert layout()["uirevision"] == initial
    app.number_input[0].set_value(2).run()
    changed = layout()["uirevision"]
    assert changed != initial
    app.button(key="compact_chart_reset").click().run()
    assert layout()["uirevision"] != changed
    assert app.get("plotly_chart")[0].key == "compact_chart_plot_1"
    assert not app.exception
