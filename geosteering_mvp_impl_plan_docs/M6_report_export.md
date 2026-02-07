# Milestone 6: Report export (PDF)

**Primary purpose**: produce a reproducible PDF report that becomes the primary portfolio artifact.

**Spec refs**: `08_epic_f_report_export.md`, `14_templates_and_standard_outputs.md`, plus `00/01/15` for disclaimers and assumptions.

---

## Issue: M6-REP-500 Report rendering strategy + skeleton PDF

**Spec refs**: `08` (reproducibility), `14` (report outline), `00` (disclaimer)

**Depends on**: `M1-IO-030` (load state), plus at least one plot module

**Goal**: generate a headless PDF with required section headers.

**Subtasks**
- [x] Choose report backend (recommended: ReportLab)
- [x] Implement `build_report(project_root) -> pdf_path`
- [x] Create cover page with non-operational disclaimer
- [x] Add required section headers as placeholders

**Deliverables**
- `app/report/report_builder.py`

**Acceptance checks**
- [x] Headless report generation produces a non-empty PDF

---

## Issue: M6-PLOT-510 Deterministic plot snapshots for reports

**Spec refs**: `08` (deterministic plots), `14` (plot templates)

**Depends on**: plot modules from M2–M5

**Goal**: render Plotly figures to stable PNGs for embedding.

**Subtasks**
- [x] Add Plotly-to-PNG renderer (recommend `kaleido`)
- [x] Generate required images:
  - correlation snapshot
  - plan MD vs TVD
  - DLS vs MD
  - interpretation overlay
  - KPI plot
- [x] Fixed image sizes and axis ranges where feasible

**Deliverables**
- `app/report/snapshots.py`

**Acceptance checks**
- [x] Same saved project produces the same figures and values (visual identity preferred but at minimum stable content)

---

## Issue: M6-REP-520 Populate report sections with real content

**Spec refs**: `08` required sections, `14` templates

**Depends on**: `M6-REP-500`, `M6-PLOT-510`, plus completed M3–M5 state

**Goal**: a complete, portfolio-ready report.

**Subtasks**
- [x] Data summary and QC table
- [x] Planning section:
  - parameters
  - plots
  - DLS exceedance table
- [x] Correlation section:
  - snapshot
  - marker tables
- [x] Steering section:
  - decision log table
  - KPI summary
  - final interpretation control points
- [x] Assumptions and limitations appendix

**Deliverables**
- Completed `report_builder` with full content

**Acceptance checks**
- [x] Meets `08` P0 content requirements

---

## Issue: M6-REP-530 CLI report export

**Spec refs**: `08` Test F1, `12` milestone gate

**Depends on**: `M6-REP-520`

**Goal**: generate report from CLI (no Streamlit).

**Subtasks**
- [x] Implement `tools/export_report.py`:
  - `python -m tools.export_report <project_root>`
- [x] Output to `exports/report_<project_name>.pdf`

**Deliverables**
- Report export CLI tool

**Acceptance checks**
- [x] F1 passes: creates PDF with expected sections

---

## Issue: M6-TEST-540 Report reproducibility tests

**Spec refs**: `08` F1 + optional F2

**Depends on**: `M6-REP-530`

**Goal**: ensure report generation is stable and verifiable.

**Subtasks**
- [x] Test report export produces non-trivial PDF
- [x] Test PDF includes required section headers (text extraction or heuristic)
- [x] Optional: normalized hash test (strip PDF metadata before hashing)

**Deliverables**
- `tests/test_report_export.py`

**Acceptance checks**
- [x] Milestone 6 gate in `12` satisfied
