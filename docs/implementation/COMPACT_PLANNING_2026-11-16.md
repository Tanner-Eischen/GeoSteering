# Compact planning workspace — 2026-11-16

This records the paired-layout revision. The later
[automatic-preview revision](AUTOMATIC_PLANNING_2026-11-16.md) supersedes its
manual Generate Preview workflow.

Planning previously stacked model evidence, all geometry inputs, large metric
cards, charts and save actions. This revision puts inputs and their preview in
one paired workspace without changing the plan generator or saved-plan contract.

## Design and scope

`app/pages/planning.py` now has Plan & preview and Details & data tabs. A compact
interpretation selector remains above the workspace. The preview column sits
beside the input/save panel and stays visible during longer edits on wider
screens. The existing scoped sticky-column rule in `app/ui/theme.py` includes
the new planning workspace. Very narrow screens stack the panels.

Core inputs remain visible; prescribed landing, azimuth and sampling controls
are in Landing & sampling options. Disabled prescribed fields remain rendered
in solved mode to preserve state. Trajectory and Dogleg limits use compact chart
controls and a stable tab identity, so the selected chart survives regeneration.
Model evidence, station tables and detailed exceedances are in Details & data.

Generation remains explicit. Editing inputs retains the last chart with a clear
Previous preview warning. That chart uses its captured name, parameters, DLS
limit and geological model, never a mixture of old stations and new thresholds.
Save, download and steering handoff remain unavailable until regeneration
produces a matching preview. Failed generation clears the old preview. Duplicate
save prevention, model-source validation and project isolation remain intact.

## Verification

- All 35 regression checks passed across planning, preview state, geological
  handoff and app navigation. Fourteen final checks passed after the chart-tab
  identity adjustment. Existing planning tests passed unchanged.
- New tests cover retained stale charts with captured thresholds/evidence,
  regenerated geometry, no writes before Save, failed-generation cleanup,
  cross-project isolation and stale geological source rejection.
- Ruff and whitespace checks passed. The final source fingerprint is
  `184be8ab989bf5d116471aa9cfc8b89ff2142f17ee981a72b9ea91759bd4c7b3`.
- The in-app browser checked the normal 626×651 workspace, 1280×720 desktop and
  390×844 phone sizing. At desktop width the preview remained at y=64 px with
  its bottom near 573 px while editing expanded sampling controls. Phone
  content had equal client and scroll widths (380 px), a static chart column,
  and reachable save/download actions. The viewport override was removed.
- Live edits changed lateral length from 5000 to 3500 ft and DLS limit from 6
  to 8, then 9°/100 ft. The stale chart retained its captured geometry/limit and
  could not be saved. Regeneration preserved the selected Dogleg limits tab.
- Changing spacing to 50 ft produced 111 stations. The reviewed plan was saved
  once, Save Plan became disabled, and its CSV downloaded successfully. Backend
  inspection verifies the downloaded stations and the pinned interpretation.
- No browser console errors or warnings were observed. Other browsers and
  physical mobile devices were not tested; a full repository-suite rerun was
  not performed for these presentation changes.

The browser operations used the prior isolated synthetic UI-test project. A
fresh interpretation was saved because previous marker-editor tests changed its
source evidence; no existing model was silently refitted. Existing unrelated
calibration work is preserved. No commit, push or deployment was performed.

Evidence is under `output/verification-compact-planning-2026-11-16/`, including
test XML/logs, browser screenshots and `verification.json`.

Suggested follow-up automation: package the repeated paired-workspace checks
into a reusable UI-QA skill covering stale data, explicit save boundaries,
sticky chart bounds, narrow-screen scrolling and a browser screenshot.
