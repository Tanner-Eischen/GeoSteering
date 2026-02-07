# Backlog Overview and Execution Order

This plan is dependency-ordered to minimize thrash and maximize early proof-of-life.

## Milestones (aligned to `12_milestones_and_delivery_plan.md`)
1. **M1 Data ingestion + persistence baseline**
2. **M2 Single well viewer**
3. **M3 Correlation panel + marker CRUD**
4. **M4 Planning (target line + DLS)**
5. **M5 Steering simulation console**
6. **M6 Report export**
7. **M7 Optional mapping/gridding**
8. **X Cross-cutting quality + demo packaging**

## Critical path to a credible MVP demo
1) M1 schemas + persistence + ingestion + QC + tests  
2) M2 well viewer (for log inspection and later report plots)  
3) M3 correlation and marker persistence  
4) M4 planning outputs and DLS validation  
5) M5 simulation with interpretation versioning, decision log, KPIs  
6) M6 report export (headless, reproducible)  
7) X end-to-end demo script + README

## Recommended AI-agent execution order
1) `M1-REPO-001` → `M1-DATA-010` → `M1-MODEL-020` → `M1-IO-030`  
2) `M1-ALG-040` → `M1-IO-050` → `M1-IO-060` → `M1-QC-070` → `M1-IO-080` → `M1-TEST-090`  
3) `M2-UI-100` → `M2-PLOT-110` → `M2-UI-120`  
4) `M3-MODEL-200` → `M3-PLOT-210` → `M3-UI-220` → `M3-TEST-230`  
5) `M4-PLAN-300` → `M4-MODEL-310` → `M4-PLOT-320` → `M4-UI-330` → `M4-TEST-340`  
6) `M5-SIM-400` → `M5-ALG-410` → `M5-MODEL-420` → `M5-MODEL-430` → `M5-ALG-440` → `M5-PLOT-450` → `M5-UI-460` → `M5-TEST-470`  
7) `M6-REP-500` → `M6-PLOT-510` → `M6-REP-520` → `M6-REP-530` → `M6-TEST-540`  
8) `X-DOC-700` → `X-TEST-710` → `X-DOC-720`

## Issue sizing rule (recommended)
- One PR implements **1–3 tasks** (e.g., `M5-ALG-440` + tests).
- Every PR includes at least one of:
  - a unit test
  - a CLI entrypoint that exercises the feature
  - a UI page demo of the module

## Done definition (global)
Use `00_mvp_goal_and_success_criteria.md` “Definition of Done” as the overarching gate.
