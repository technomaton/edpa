---
description: Generate visual HTML Kanban board from .edpa/backlog/ YAML files
allowed-tools: Read, Bash
model: sonnet
---

# EDPA Board

Generate a self-contained HTML Kanban snapshot from the local backlog.

## Steps

1. Run the board generator:
```bash
python3 .edpa/engine/scripts/board.py --open
```

2. Pass any arguments the user specified:
   - `--iteration PI-2026-1.4` — filter by iteration
   - `--level story|feature|epic|initiative` — which level to show (default: all levels)
   - `--output /path/to/file.html` — custom output location

3. Report the output path and how many items were rendered.

## What it renders

- **Iteration chip** (header) — surfaces the focused iteration's PI designation
  and date range (e.g. `PI-2026-1 · Iter 4 · 27 Apr – 1 May 2026`), with a
  pulsing dot when that iteration is the active one. It reads
  `.edpa/iterations/*.yaml`, defaults to the active iteration (latest by
  start_date), and updates live as the iteration dropdown changes — so
  `--iteration PI-2026-1.4` initialises it to that iteration. Omitted when the
  project has no `.edpa/iterations/` metadata.
- **Delivery columns** (Planned / In Progress / Done) hold Initiatives, Epics,
  Features, Stories, and Defects, grouped by delivery status and sorted by WSJF.
- **Risks (ROAM) section** — a separate panel below the columns lists Risk
  items keyed on their ROAM disposition (Resolved / Owned / Accepted /
  Mitigated) plus severity. Risks are program-board artefacts whose lifecycle
  is ROAM, not a delivery status, so they are deliberately kept out of the
  status columns. The section is shown on the full board and is omitted when a
  `--level` delivery drill-down is active.
