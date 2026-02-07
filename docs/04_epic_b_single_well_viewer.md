# Title
Epic B: Single Well Viewer (Logs + Trajectory)

## Objective
Implement a fast and clear log viewer for one well that supports:
- Track-style plots for selected curves
- Depth navigation (zoom/pan)
- Overlay of markers
- Display of bit position when in simulation mode

## Functional requirements
### P0
- Select a well
- Plot at least two tracks:
  - Track 1: GR
  - Track 2: Resistivity (log scale display)
- Depth axis aligned across tracks
- Marker overlay:
  - horizontal lines at marker depths
  - label markers
- Show computed trajectory profile:
  - MD vs TVD
- Bit position indicator:
  - a horizontal line at current revealed depth (MD)

### P1
- Custom track templates (save/load)
- Toggle curve normalization per track

### P2
- Derived curves (moving average) for display only

## UX requirements
- Depth range selection: full, last N feet, custom interval
- Pan/zoom must remain responsive for typical LAS sizes (up to ~1e6 samples total across curves)
- Avoid re-parsing LAS on every UI rerun (cache normalized parquet)

## Plotting requirements
- Use a plotting library that can:
  - draw multiple aligned axes
  - support interactive zoom and pan (Plotly recommended for Streamlit)
- Resistivity track should support log scale and handle nonpositive values safely:
  - clip <= 0 to NaN for log display
  - indicate clipped count in UI

## Inputs and outputs
Inputs:
- Normalized logs (parquet)
- Markers (json)
- Trajectory (parquet)
Outputs:
- No new files required; this is a UI view
- Optional exported screenshot for report module

## Edge cases
- Missing GR or RES curves (viewer should degrade gracefully)
- Markers outside the log depth range
- Curves with different sampling steps

## Acceptance tests
### Test B1: Render baseline tracks
Given a well with GR and RES
When opening the viewer
Then both tracks render with aligned depth axis

### Test B2: Marker overlay
Given a marker at md_ft within plot range
When viewer renders
Then the marker line appears and label is visible

### Test B3: Bit position indicator
Given simulation state with current_bit_md_ft
When viewer renders
Then a bit position indicator is visible at that depth

## Definition of Done
- Viewer works for active well and offset wells
- Performance acceptable on sample dataset
- Viewer can produce images used by report export
