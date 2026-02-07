# Milestone 7 (Optional): Mapping and gridding

This milestone is explicitly optional and should only begin after a stable MVP demo exists.

**Spec refs**: optional skill in `02_skill_to_feature_mapping.md`, optional milestone in `12_milestones_and_delivery_plan.md`.

---

## Issue: M7-ALG-600 IDW gridding from control points

**Spec refs**: optional mapping idea, consistent with `02` and `12`

**Depends on**: stable control point data from interpretation versions

**Goal**: compute a simple surface from control points as a portfolio differentiator.

**Subtasks**
- [ ] Implement IDW grid generation from (x, y, z) control points
- [ ] Define grid extents and resolution (configurable)
- [ ] Export grid as CSV
- [ ] Unit tests on synthetic control points

**Deliverables**
- `app/alg/gridding_idw.py`

**Acceptance checks**
- [ ] Surface generation produces stable output and passes unit tests

---

## Issue: M7-UI-610 Mapping page (optional)

**Spec refs**: optional extension; keep scope minimal

**Depends on**: `M7-ALG-600`

**Goal**: visualize surfaces and export them.

**Subtasks**
- [ ] Render before/after surface maps (heatmap)
- [ ] Overlay control points
- [ ] Export grid CSV
- [ ] Add report hooks (optional)

**Deliverables**
- `app/pages/mapping.py` (optional), report inclusion hook
