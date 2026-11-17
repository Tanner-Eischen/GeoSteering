import json

from streamlit.testing.v1 import AppTest


def chart_page(*, explicit_revision):
    return AppTest.from_string(f'''
import streamlit as st
import plotly.graph_objects as go
from app.ui.charts import render_chart
annotation = st.text_input("Draft marker", value="Top")
context = st.selectbox("View context", ["well-a:full", "well-a:window", "well-b:full"])
figure = go.Figure(go.Scatter(x=[0, 1], y=[100, 200]))
figure.add_annotation(x=0.5, y=150, text=annotation)
render_chart(
    figure, key="revision_chart", compact=True,
    view_revision=context if {explicit_revision!r} else None,
)
''', default_timeout=20).run()


def figure(app):
    return json.loads(app.get("plotly_chart")[0].proto.spec)


def test_explicit_view_revision_preserves_annotation_edit_zoom_until_context_or_reset_changes():
    app = chart_page(explicit_revision=True)
    initial = figure(app)["layout"]["uirevision"]
    app.text_input[0].set_value("Updated draft top").run()
    updated = figure(app)
    assert updated["layout"]["annotations"][0]["text"] == "Updated draft top"
    assert updated["layout"]["uirevision"] == initial
    app.selectbox[0].set_value("well-a:window").run()
    changed_context = figure(app)["layout"]["uirevision"]
    assert changed_context != initial
    app.button(key="revision_chart_reset").click().run()
    assert figure(app)["layout"]["uirevision"] != changed_context
    assert app.get("plotly_chart")[0].key == "revision_chart_plot_1"
    assert not app.exception


def test_default_view_revision_still_tracks_figure_changes():
    app = chart_page(explicit_revision=False)
    initial = figure(app)["layout"]["uirevision"]
    app.text_input[0].set_value("Updated draft top").run()
    assert figure(app)["layout"]["uirevision"] != initial
    assert not app.exception



def test_viewport_hook_is_opt_in_and_precedes_the_controlled_chart():
    app = chart_page(explicit_revision=True)
    hook = next(item for item in app.get("html") if "__geoSteeringChartViewports" in item.proto.body)
    assert hook.proto.unsafe_allow_javascript is True
    assert '"context": "well-a:full:0"' in hook.proto.body
    controlled = next(
        block for block in app.get("flex_container")
        if any(child.type == "html" for child in block.children.values())
    )
    assert [child.type for child in controlled.children.values()] == ["html", "plotly_chart"]
    default_app = chart_page(explicit_revision=False)
    assert not default_app.get("html")


def test_viewport_context_is_json_encoded_and_cannot_close_script():
    from app.ui.chart_viewport import viewport_container_key, viewport_script
    context = '</script><script>alert("context")</script>'
    key = 'chart"<unsafe>'
    script = viewport_script(key, context)
    assert script.count("</script>") == 1
    assert context not in script
    assert "\\u003c/script\\u003e" in script
    assert "localStorage" not in script
    assert "setInterval" not in script
    assert viewport_container_key(key).startswith("chart_viewport_")
