# Title
MVP Scope and Non-Goals

## Scope statement
The MVP is a single-user local application implementing a narrow but complete geosteering workflow centered on:
- LAS and survey ingestion
- Multiwell correlation panel with marker picking
- Target line planning with DLS constraint checks
- Simulated real-time steering with interpretation versioning and decision logging
- PDF report export with key plots and tables

## In-scope (P0)
### Data
- Import LAS logs (at minimum GR and one resistivity curve)
- Import survey data (MD, inclination, azimuth)
- Support multiple wells (minimum 4: 3 offsets + 1 active)
- Persist project state to disk

### Interpretation and steering
- Marker picking per well and persistence
- Create a pre-spud interpretation baseline (v0)
- Stepwise simulation that reveals active well logs progressively
- Update interpretation with user-entered control points or adjustments
- Maintain an append-only decision log

### Planning
- Target line builder driven by simple inputs
- Compute DLS between plan stations and warn if DLS exceeds user limit
- Export the plan as CSV

### Reporting
- Export a reproducible PDF report that includes:
  - Plan summary
  - Correlation panel snapshot
  - Steering decisions
  - KPI summary

## Out-of-scope (explicit non-goals for MVP)
- Real-time data streaming or WITSML ingestion
- Multi-user collaboration, roles, permissions
- Seismic volume ingestion and interpretation
- Image log interpretation
- Automated geosteering recommendations beyond simple constraint checks
- Enterprise data formats beyond LAS and CSV
- Cloud hosting, authentication, APIs

## De-scoping rules (guardrails)
If an implementation request increases complexity without increasing portfolio signal, it is rejected in MVP:
- Any feature requiring time-depth synchronization with drilling events
- Anything involving vendor-specific real-time feed quirks
- Anything requiring 3D volumetric interpretation

## MVP assumptions (must be documented in UI)
- Canonical depth basis: MD for logs; TVD computed from trajectory is used for in-zone evaluation (configurable later).
- Active well is a single well per simulation run.
- Logs are depth-indexed (no time-index logs).
- The geosteering model is 2D along-lateral (function of MD), not a full 3D surface model.

## Extensibility hooks (allowed if low-cost)
- A "replay from CSV" data adapter interface (stub)
- Optional helper algorithms that produce suggestions but do not auto-apply changes
- A mapping module placeholder that can be added later
