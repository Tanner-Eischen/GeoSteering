# Automatic planning preview — 2026-11-16

Planning now generates a preview for valid initial inputs and refreshes it when
an input is committed with Enter, focus loss, or a stepper control. The Generate
Preview button has been removed. The paired layout and selected chart tab remain.

The change is scoped to `app/pages/planning.py` and its planning workspace tests.
The plan generator, geological solver and plan persistence services are unchanged.
Save Plan remains the explicit persistence boundary.

The page compares the project, current input request and model-validation status.
An unchanged valid preview is reused, including its saved ID. Chart controls,
unrelated reruns and the post-save rerun do not recompute it. Invalid requests
clear the preview/save eligibility and cache their validation result until inputs
change. Corrected inputs recover automatically. Model sources are still validated
on each render, so an invalid source cannot leave a solved preview saveable.
Required numeric inputs are checked for missing/non-finite values before calling
the existing solver. Native Streamlit numeric fields can restore their default
on clearing; the server boundary nevertheless rejects None, NaN and infinity.

Verification:

- All 40 selected regression tests passed, covering automatic refresh, current
  geometry and DLS data, no project writes before Save, invalid/recovered inputs,
  cached failures, unchanged reruns, explicit duplicate-safe Save, current model
  pinning, source invalidation, cross-project isolation and navigation.
- The in-app browser changed lateral length from 3500 to 4500 ft and observed
  the preview update from 111 to 131 stations without a Generate click. Enter
  applied a DLS-limit change from 9 to 10°/100 ft while retaining the DLS tab.
- Clearing the plan name removed the chart and save/download actions; entering
  a valid name restored them automatically. No plan was saved during this live
  test, and all six existing plan files remained byte-for-byte unchanged.
- Ruff passed. No browser console errors or warnings were observed. No viewport
  override was used, and the updated app was left open.

Evidence is under `output/verification-auto-planning-2026-11-16/`. The browser
used the existing isolated synthetic UI-test project. No commit, push or
deployment was performed. The final source fingerprint is
`56b4069723f66e75b0915d6195da3130df9bfcdb90782690d1d231dc9a1b1fd8`.
