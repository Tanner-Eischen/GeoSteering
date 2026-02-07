# Title
Risks, Failure Modes, and Mitigations

## Objective
Prevent credibility-killing problems and scope blowups.

## Risk 1: Depth reference confusion
Failure mode:
- Logs, markers, and trajectory are in mixed bases (MD vs TVD), causing incorrect in-zone metrics and misleading plots.

Mitigation:
- Enforce canonical basis:
  - logs and markers stored in MD (ft)
  - vertical computations use TVD derived from trajectory
- Display basis labels everywhere
- Validate conversions and raise clear errors

## Risk 2: Unstable or non-deterministic simulation state
Failure mode:
- Streamlit reruns cause state to reset or diverge.
- Results change across runs.

Mitigation:
- Centralize state in project files and explicit simulation_state.json
- Pure functions for computations
- Deterministic step transitions
- Unit tests asserting deterministic outputs

## Risk 3: Plot performance issues
Failure mode:
- Large LAS files cause UI freezing or timeouts.

Mitigation:
- Cache normalized logs in parquet
- Decimate for display, keep full-res for computations
- Limit default plot window to a manageable depth span

## Risk 4: Overfitting to messy public data
Failure mode:
- Public LAS or surveys contain quirks that derail the demo.

Mitigation:
- Provide a synthetic dataset generator that produces a clean demo dataset with known truth
- Then optionally provide an additional "real data" example

## Risk 5: Interpretation model too complex
Failure mode:
- Building a full surface model adds complexity and bugs.

Mitigation:
- Use piecewise linear 2D along-lateral model for MVP
- Optional mapping module only after MVP gates pass

## Risk 6: Credibility gap from missing auditability
Failure mode:
- No traceability from decisions to interpretations and data.

Mitigation:
- Append-only decision logs
- Immutable interpretation versions with rationale
- Link every decision to a version id

## Risk 7: Scope creep into streaming ingestion
Failure mode:
- WITSML or live data pipelines balloon effort.

Mitigation:
- Explicit MVP non-goal
- If needed, implement only a CSV replay adapter later

## Definition of Done
- Each risk has a visible mitigation implemented in code or UI
- Demo can be executed without known failure modes
