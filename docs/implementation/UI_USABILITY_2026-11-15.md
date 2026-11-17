# Workbench usability revision — 2026-11-15

The workbench had competing header/scroll styling, a long sidebar that buried
project setup and imports, dense side-by-side charts, and controls whose state
did not reliably match the operation being saved. This revision changes the
operator workflow and fixes the associated state errors.

## Scope and design

- The app shell groups navigation by preparation, interpretation/steering,
  review/export and reference studies. Project setup and import have full-width
  pages and permanent sidebar entry points. A compact project context replaces
  the repeated global hero above each page.
- The theme leaves header positioning and scrolling to Streamlit, removes
  dataframe overflow clipping, wraps long metric/button text, and responds to
  available main-content width when the sidebar is open. No remote font request
  is required. The repository's Streamlit theme supplies matching native colors.
- Import supports single-well file selection and batch folder paths. Both show
  a review step, validation messages and persistent per-well outcomes. The
  uploader stages only the recognized filenames in a temporary directory and
  uses the existing scientific importer. Duplicate names and repeated uploads
  are blocked in the workflow. It does not change survey/log/QC contracts.
- Data QC exposes warnings as readable text per well and downloads the full
  summary. Dashboard organizes the next actions by workflow stage.
- Main inspection charts expose Pan, Box zoom, Reset view and optional wheel
  zoom. Page scrolling is the default wheel behavior. Depth windows exclude
  off-window overlays; empty selections and unsupported windows give actionable
  messages. Large correlation selections are displayed in groups of three
  without changing the selected evidence used to save an interpretation.
- Correlation uses acquired MD/TVD limits, marker-specific editor state and a
  pre-render callback for jumping to a marker. Scientific source selection and
  saved interpretation pinning remain in the existing services.
- Planning inputs are reactive. Every relevant input and model belongs to the
  preview request, so editing inputs invalidates save/download until a new
  preview succeeds. A failed generation clears the old preview. Duplicate save
  is disabled, and CSV stations download directly.
- Steering presents acquired observations in full-width tabs followed by command
  controls. History and provenance follow the active work. New-run calibration
  controls, causal limits, run pinning and withheld-data restrictions remain.
- Project switching clears import, viewer, chart and command state in addition
  to the existing derived-state prefixes.

## Verification and limits

Verification uses the existing locked CPython 3.12 environment at
`output/verification-gs06-2026-11-15/installed-env`. AppTest executes the actual
Streamlit page handlers in process; it does not operate a browser. Uploaded-file
tests supply upload objects because AppTest does not automate the file picker.
The source manifest is regenerated through `tools.release_provenance` after
source changes, with no bypass of provenance checks.

The verification runtime is CPython 3.12.11, Streamlit 1.66.1 and Plotly 6.6.0.
The final 109-file application/tools manifest verifies fingerprint
`4282664dd94e5758e42d600cb0743b5f14b5a8b7fd06a36996d20675ff5cd7b0`.

The initial integrated run passed 50 tests across app navigation, imports,
charts, planning, project switching, steering, interpretation handoff and
withheld-data isolation. Final regression artifacts belong under
`output/verification-ui-2026-11-15/`.

The full regression suite passed 386 tests in 607.92 seconds at fingerprint
`eea37191d045c7a7a15798f80aa599f5e1e0dac9a7e86e5a7793218cde5dc69b`.
The only subsequent application changes make single-sample traces visible in
log tracks, correlation and the well-viewer trajectory. The final targeted run
covers those figures, chart operations, every app route and withheld-data
isolation. An initial new trajectory test incorrectly assumed the standard
replay fixture had only one station; it was corrected to explicitly represent
single-station acquired support. The original failure log is retained. All 25
final targeted tests passed in 30.53 seconds. Repository Ruff and whitespace
checks passed.

A separate loaded-project test visits all 14 routes through the actual app
shell without exceptions and verifies that all project files remain byte-for-byte
unchanged. A fresh headless local server at `http://127.0.0.1:8524` returns HTTP
200 with `ok` from its health endpoint. This checks startup, not visual rendering.
The existing local server was left running. The new process ID and logs are in
the same verification directory.

The initial pass did not open or inspect a browser, under the initial user
restriction. The user subsequently authorized the in-app browser; the additional
verification and corrections are recorded below.
This work does not establish field performance or change the scientific-study
results. Existing calibration work in this checkout is preserved. No commit,
push or deployment is part of this revision.

## Authorized in-app browser follow-up

Live checks used the Codex in-app browser at 1280×720, 900×900 and 390×844.
The browser viewport was restored afterward, and the app tab was left open.
A new isolated synthetic case-study workspace was created for import, replay
and planning operations; existing user projects were not used for mutations.

The browser pass found and corrected five issues:

1. Streamlit's heading rule overrode the compact title. A more specific selector
   now produces a 27.2-pixel desktop title with no extra heading padding; the
   main horizontal margins are reduced to 32 pixels.
2. Three correlation tracks were cramped at narrow widths. Operators can select
   one, two or three visible tracks; only the first shares the depth-axis title.
   Saving an interpretation still uses all selected offsets.
3. Upload results hid details inside narrow table cells. Single-well results now
   use a wrapping details panel, and file-status labels fit the preview table.
4. Leaving Correlation removed its widget values but retained its context key,
   so returning initialized both depth limits to zero. Missing widget values
   now recover acquired depth bounds. A page-switch regression covers this.
5. Sidebar navigation retained the old page's scroll offset. A navigation-only
   helper uses the supported Streamlit HTML API to scroll the main container to
   the header after tab layout effects. Its script contains only an internal
   numeric revision, never project/user text. Same-page control changes do not
   trigger the helper.

Observed operations: wheel scrolling over a graph, box zoom, switching back to
pan without losing zoom, full-range reset, single-track mobile correlation,
four-file upload (37 survey stations, 3,601 log rows, three markers), duplicate
import protection, replay advancement from 2,000 to 2,050 ft, stale-preview
blocking, plan generation/save and actual CSV download. The downloaded plan
has 61 stations and satisfies its 6°/100 ft dogleg limit within floating-point
tolerance. Page navigation ended at main scroll offset zero; a pointer-driven
chart mode change retained the measured 515.33-pixel offset. No browser console
errors or warnings were recorded.

The final source fingerprint is
`588374273c4c793386f0f734416e6142b2d9c5ac7cc1b8fab19741c0a7eb7987`.
Forty-two workflow tests passed after the depth fix, followed by seven navigation
tests after the scroll helper. Ruff and whitespace checks passed. An earlier
follow-up test run encountered the source-manifest guard while another fix was
being written; the stable-source rerun passed without bypassing that guard.
Evidence is in `output/verification-ui-2026-11-15/browser-verification.json` and
`browser/*.jpg`. Other browsers, physical mobile devices and every individual
page were not manually tested.
