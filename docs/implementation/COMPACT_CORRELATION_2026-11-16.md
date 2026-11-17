# Compact correlation workspace — 2026-11-16

The earlier Correlation View and Marker Editor tabs separated the chart from
editing. The replacement makes comparison and editing one paired workspace.

## Design

- Correlate & edit places the chart beside marker selection, depth/name/notes,
  Update Marker and Jump to Marker. The chart column remains visible during
  longer edits on wider screens; very narrow screens stack the panels.
- The focused marker well and visible chart group follow each other. One well
  is shown by default for readable editing; View options retains two-/three-well
  comparisons. The Wells selection still determines interpretation evidence.
- Selected saved depths use a teal line. A changed, unsaved depth has a separate
  orange dashed line. Changing fields alone does not write a marker or alter
  the saved interpretation. The preview converts to TVD when that alignment is
  selected, while all edits remain in acquired-survey MD coordinates.
- Add marker is an editor tab; a successful addition returns to Edit marker
  with the new marker selected. Marker list and Delete marker are collapsed
  secondary actions. Duplicate names remain distinguishable by marker IDs.
- View options contains depth/alignment/group/scaling settings. Chart controls
  uses the existing compact popover. Interpretation saving and saved model
  evidence are in a separate Interpretations tab.
- Updating a marker refreshes the selector's formatted label while retaining
  the marker ID. Failures preserve the editable fields and saved data.

The main changes are in `app/pages/correlation_panel.py`, the optional viewport
support in `app/ui/charts.py` / `app/ui/chart_viewport.py`, and scoped chart-column
styling in `app/ui/theme.py`. Marker persistence, data acquisition, model fitting
and saved interpretation contracts remain in their existing services.

## Verification notes

New AppTest cases cover draft/read-only behavior, successful save, failed-save
recovery, linked well/group selection, unchanged all-offset evidence, automatic
new-marker selection, and active-run future-marker isolation. Existing tests
continue to cover duplicate IDs, depth validation, deletion errors and restoring
depth controls after page cleanup.

The initial test run exposed a test injector that patched a column method while
the compact editor now calls the public Streamlit number-input function. The
injector was corrected so out-of-support values are still actually injected and
rejected. The subsequent regression run passed 43 tests; the expanded targeted
run passed 26 tests.

Browser operations use the isolated synthetic UI-verification project created
earlier in this chat. They do not change an operational project. A test marker
was added and edited. CLI inspection confirmed that a 1570-ft draft left the
saved marker at 1550 ft until Update Marker was selected.

The browser test caught an issue not detectable from serialized `uirevision`
alone: Streamlit 1.66 includes the entire figure in its element ID, replacing
the chart on marker changes. Opt-in viewport restoration therefore listens to
Plotly axis-relayout events and restores axis ranges only within the same view
context. State stays in browser memory; no external requests or persistent
browser storage are used. Other charts retain their existing behavior.

Evidence and logs are stored under
`output/verification-compact-correlation-2026-11-16/`. No commit, push or deployment
is part of this change.

## Final browser acceptance

The in-app browser checked the normal 626×651 workspace, a 1280×720 desktop
viewport, and 390×844 phone sizing. The override was removed afterward. At
desktop width, the chart remained at y=64 px while editing, with its bottom at
approximately 610 px. On the phone layout the panels stack, the chart column
is static, and main content width equals scroll width (380 px), with all editor
actions reachable through ordinary page scrolling.

The initial viewport hook still lost the zoom. Live instrumentation identified
the lifecycle/capture issue: the hook now records the actual relayout event
payload, clears canceled animation-frame bookkeeping, and restores only after
the new graph is ready. Temporary instrumentation was removed. A repeated live
test retained the same y tick labels (1550, 1600, 1650 ft) through both a draft
change and Update Marker. Changing to another well cleared that viewport;
Reset view independently restored the configured 1400–1700-ft interval.
The saved selector label refreshed to the new 1590-ft depth.

The restored state consists only of axis ranges/autorange in browser memory,
scoped to the chart and display context. The implementation uses public Plotly
events/relayout and the existing Streamlit HTML API. It has one coalesced
MutationObserver per opted-in chart and no polling. It is checked against the
bundled Streamlit 1.66.1 behavior; other browsers and physical mobile devices
were not accepted in this pass.

The final targeted run passed 16 tests after the viewport fix. JavaScript syntax,
Ruff and whitespace checks passed. The only later source change is legend
spacing, verified live at desktop and phone widths. The final source fingerprint
is `6625ab372e85695b9f4b955f5c7cec26b92e58e2ec379c6e3b9ad0aa0d844e14`.
Screenshots are in the evidence directory's `browser/` subfolder.
