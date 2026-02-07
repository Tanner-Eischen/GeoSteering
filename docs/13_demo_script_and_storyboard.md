# Title
Demo Script and Storyboard

## Objective
Provide a repeatable demo that mirrors the ops workflow and produces a compelling recorded walkthrough.

## Demo prerequisites
- Sample project with:
  - 3 offset wells: surveys + logs + some pre-defined markers (optional)
  - 1 active well: survey + logs
- A saved plan and a baseline interpretation version v0

## Storyboard (10 to 15 minutes)
### Part 1: Project and data readiness (1 to 2 min)
- Open project
- Show wells loaded and QC screen
- Highlight curves present and depth coverage

### Part 2: Correlation panel (3 to 4 min)
- Open correlation panel with 3 offset wells
- Display GR and RES
- Add or adjust 2 to 4 markers that define the expected zone boundaries or key tops
- Save markers
- Explain ties briefly using curve signatures and uncertainty

### Part 3: Planning (2 to 3 min)
- Open planning screen
- Show target window definition and max DLS
- Generate plan and show:
  - MD vs TVD plot
  - DLS vs MD plot
- Export plan CSV

### Part 4: Steering simulation (4 to 6 min)
- Open steering console
- Configure step size (example 100 ft)
- Run 5 to 10 steps:
  - Each step: show active log window and compare to offsets
  - Update interpretation once or twice (create v1, v2)
  - Log a decision each step (hold/build/drop)
  - Show KPI updates

### Part 5: Report export (1 to 2 min)
- Export PDF report
- Open report and quickly scroll:
  - plan summary
  - correlation snapshot
  - decision table
  - KPI summary

## Demo success criteria
- No crashes
- All actions are traceable in saved project state
- The exported PDF is complete and presentable

## Optional "challenge mode"
- Start with a deliberately wrong pre-job top/base model
- Show how early markers and log signatures force a correction
- Use KPI improvement as evidence of correct steering

## Definition of Done
- A demo can be executed by following this script without improvisation
- Screen recordings can be created without manual data tweaks
