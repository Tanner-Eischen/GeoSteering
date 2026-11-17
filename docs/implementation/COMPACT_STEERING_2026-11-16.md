# Compact steering workspace — 2026-11-16

The previous screen separated the acquired-data charts from evidence entry and
the advance button with status cards, explanatory text and a second preview
area. The operator had to scroll back and forth during each decision.

## Design and changes

The affected implementation is `app/pages/steering_console.py`, with an opt-in
compact mode in `app/ui/charts.py` and scoped sticky-column styling in
`app/ui/theme.py`. No steering, simulation, interpretation or uncertainty engine
contracts changed. Existing unrelated calibration work remains intact.

- A compact run selector/status row precedes three tabs: Steer, History &
  results, and Run setup. Selecting another run opens its working tab;
  completed runs default to review.
- Steer places charts and the command/evidence panel in adjacent columns.
  The command is computed first, so the Path + preview tab shows the currently
  selected causal command beside its controls. Logs remain a separate view in
  the same chart area. Enabled uncertainty information is another chart-area tab.
- Chart navigation is available from a Chart controls popover and the Plotly
  toolbar. The default rendering on other pages is unchanged.
- The chart column stays visible while expanding and scrolling the boundary
  revision form. This uses normal page scrolling without a nested scroll pane.
  At very narrow widths, the panels stack and sticky positioning is disabled.
- Command descriptions and projection results are concise. Boundary revision
  controls are collapsed by default. The advance action remains bound to the
  displayed run, step and interpretation version. Evidence clears after a
  successful step; empty evidence still cannot advance.
- The optional target starts at the acquired inclination for a new step. Its
  value persists across HOLD/BUILD/DROP toggles within that step.
- Setup, provenance, run comparisons, history, evaluation and report export
  remain available in their respective tabs rather than above/below active work.

Risks checked: selected-run binding, historical/legacy mechanics compatibility,
private-truth isolation, preview updates, step submission idempotency, uncertainty
setup, completed-run controls, narrow labels and sticky chart reachability.

## Verification

Local checks use the existing locked CPython 3.12 / Streamlit 1.66.1 environment.
The initial targeted suite passed 12 tests, followed by 43 regression tests
covering steering, preview mechanics, truth isolation, calibration UI, navigation,
decision review and comparison pages. Nine final targeted tests passed after
the run-tab and default-target adjustments. The last change only increases the
preview's top margin to separate its legend from the toolbar; it was checked
live at phone width. Ruff and whitespace checks passed. A full repository-suite
rerun was not required for these presentation changes.

The in-app browser verified the existing narrow desktop viewport, 1280×720 and
390×844. The viewport override was removed after testing. Observed evidence:

- Replay charts, command selection, evidence and advance fit together in the
  current narrow workspace after a short scroll. For the same replay and browser
  width, evidence entry moved from document y≈2264 px to y≈600 px.
- With boundary revision expanded, the chart remained at y=64 px while the
  command fields and advance button were reachable. Its bottom was ≈534 px.
- The chart tools open in a popover without adding a permanent control block.
- A causal BUILD target of 92° updated the next-station geometry beside the
  command. Submitting evidence advanced the isolated test run from MD 2000 to
  2100 ft, cleared the evidence input and retained the workspace/path tab.
- Switching from Run setup to another saved run selected Steer. The replay
  remained at its original step while the causal test run advanced.
- At 390 px width, all four preview legend labels clear the toolbar; the first
  label starts ≈21 px below the toolbar's bottom. Panels stack without forcing
  horizontal page scrolling.
- No browser console errors or warnings were observed. Other browsers and
  physical mobile devices were not tested.

The test operations used the isolated workspace created during the prior UI
verification, not an operational project. No deployment, commit or push occurred.
Evidence is in `output/verification-compact-steering-2026-11-16/`, including test
XML/logs, the source identity and browser screenshots. The final source manifest
fingerprint is `d8546a3eb49d07192cc618d691c18a1fb8a2034eea3da50f173dfdb58a989a2a`.
