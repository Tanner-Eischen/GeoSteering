# Cross-cutting: Quality, disclaimers, and demo packaging

These tasks cut across multiple milestones and should be addressed as soon as the relevant dependency exists.

**Spec refs**: `00`, `01`, `13`, `15`, `14`.

---

## Issue: X-DOC-700 Non-operational disclaimers and assumptions (UI + report)

**Spec refs**: `00` (non-operational disclaimer), `01` (non-goals), `15` (risk mitigations)

**Depends on**
- UI: `M2-UI-100`
- Report: `M6-REP-500`

**Goal**: ensure the tool is clearly framed as training/portfolio software, not ops-ready.

**Subtasks**
- [x] Add always-visible disclaimer in UI (sidebar or header)
- [x] Add cover-page disclaimer in report
- [x] Add “Assumptions and limitations” section in report using content from `01` and `15`

**Deliverables**
- UI disclaimer component + report appendix

**Acceptance checks**
- [x] Disclaimers visible in UI and report

---

## Issue: X-TEST-710 End-to-end demo run test (headless pipeline)

**Spec refs**: `00` SC-1 and SC-2, `13` demo flow, `08` report export

**Depends on**: M1–M6 complete

**Goal**: prove the full pipeline runs deterministically and produces artifacts.

**Subtasks**
- [x] Script to:
  - generate sample data
  - create project
  - import wells
  - create plan
  - run N simulation steps with canned decisions (non-UI)
  - export report
- [x] Assertions:
  - expected files exist
  - KPI values present
  - report exists and non-trivial size

**Deliverables**
- `tests/test_end_to_end_demo.py` and/or `tools/bootstrap_demo_project.py`

**Acceptance checks**
- [x] Satisfies SC-1 and supports SC-2 reproducibility expectations

---

## Issue: X-DOC-720 Demo walkthrough packaging (README + checklist)

**Spec refs**: `13` (demo script), `14` (standard outputs)

**Depends on**: M1–M6

**Goal**: make it easy for reviewers to run and evaluate the MVP.

**Subtasks**
- [x] `README.md` with:
  - install
  - generate sample data
  - import wells
  - run app
  - run report export CLI
- [x] “Demo checklist” matching `13_demo_script_and_storyboard.md`
- [x] Include example outputs paths and what to inspect

**Deliverables**
- README + demo checklist markdown

**Acceptance checks**
- [x] A fresh user can reproduce the demo without manual tweaking
