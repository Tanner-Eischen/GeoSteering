# Title
Epic C: Multiwell Correlation Panel

## Objective
Provide a side-by-side multiwell log panel where the user can:
- Display multiple wells aligned by depth basis (MD in MVP)
- Pick and edit markers (tops/bases) on each well
- Compare signatures across wells and document ties

This is the key "StarSteer skill" showcase module.

## Functional requirements
### P0
- Choose a set of wells to display (minimum 3)
- Choose curves to display per well (at least GR and RES)
- Display wells in columns with aligned depth axis
- Marker picking:
  - Add marker: click depth or input depth value
  - Edit marker: drag or edit numeric depth
  - Delete marker
  - Marker attributes: name, depth, notes
- Persist markers per well in project state

### P1
- Marker set templates (save/load marker lists for reuse)
- Well alignment offsets (simple depth shift per well)
  - User can apply a scalar shift to visually align a marker across wells

### P2 (optional helper)
- Similarity hint:
  - compute cross-correlation between GR curves in a window around a selected marker
  - suggest a likely tie depth in another well (does not auto-apply)

## Data model
- Each well has `markers: List[Marker]`
- Marker fields:
  - `marker_id` (uuid)
  - `name` (string)
  - `md_ft` (float)
  - `color` (optional)
  - `notes` (optional)
  - `created_at`, `updated_at`

## UX requirements
- Bulk operations:
  - add the same marker name to all wells at specified depths (optional)
- Marker list table:
  - sorted by depth
  - quick jump to marker depth
- Auditability:
  - changes to markers should be trackable (at least last updated timestamp)

## Plot constraints
- Streamlit + Plotly recommended:
  - a subplot per well or separate charts stacked horizontally
  - shared y-axis depth range
- If Plotly horizontal layout becomes awkward in Streamlit, allow vertical stacking but preserve alignment cues:
  - show consistent depth scale and marker labels

## Edge cases
- Very different depth ranges across wells
- Missing curves in some wells
- Dense markers causing label overlap (implement label thinning or hover labels)

## Acceptance tests
### Test C1: Marker CRUD persistence
Given markers created in UI
When project is saved and reopened
Then markers are present with identical values

### Test C2: Alignment shift
Given a well with an applied shift
When correlation panel renders
Then the displayed curve is shifted consistently and markers reflect shift only in display (not in stored md_ft unless explicitly chosen)

### Test C3: Multiwell display minimum
Given 3 offset wells
When correlation panel loads
Then all 3 are visible with GR tracks and aligned depth axis

## Definition of Done
- Multiwell correlation panel usable for a demo
- Marker operations are stable and persisted
- Panel can generate snapshot images for report export
