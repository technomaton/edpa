---
description: Manage PI objectives (set / remove) and team confidence votes for the PI planning board
allowed-tools: Read, Bash
model: sonnet
---

# EDPA Objectives

Manage PI objectives and team confidence votes. `$ARGUMENTS` is `<action> [options]`.

## Actions at a glance

| Action | What it does |
|---|---|
| `set <pi> <team> <kind> "<title>" [--bv N] [--status S]` | Add or update an objective |
| `remove <pi> <team> <kind> "<title>"` | Delete an objective |
| `vote <pi> <team> <confidence>` | Set team confidence (1–5) |
| `show <pi>` | Display all objectives for the PI |

**kind**: `committed` or `stretch`  
**confidence**: 1 (low) — 5 (high)  
**status**: `planned` (default) | `in_progress` | `done`  
**bv**: 1–10 (default 5)

Examples:
- `set PI-2026-1 alpha committed "Deliver OMOP parser" --bv 8`
- `set PI-2026-1 alpha stretch "Automate regression tests" --status in_progress`
- `remove PI-2026-1 alpha committed "Old objective"`
- `vote PI-2026-1 alpha 4`
- `show PI-2026-1`

## Steps

### `set`

1. Parse PI, team, kind, title (all required). Optional `--bv N` and `--status S`.

2. Call `edpa_objective_set`:
   ```
   edpa_objective_set(pi="<pi>", team="<team>", kind="<kind>", title="<title>",
                      bv=<bv>, status="<status>")
   ```

3. Auto-commit:
   ```bash
   git add .edpa/pi-objectives/
   git commit -m "chore(pi-objectives): set <kind> objective for <team> in <pi>"
   ```

4. Offer to refresh the PI board:
   > Objective saved. Re-render the PI planning board? (`/edpa:pi-planning <pi>`)

### `remove`

1. Parse PI, team, kind, title (all required).

2. Call `edpa_objective_remove`:
   ```
   edpa_objective_remove(pi="<pi>", team="<team>", kind="<kind>", title="<title>")
   ```

3. Auto-commit:
   ```bash
   git add .edpa/pi-objectives/
   git commit -m "chore(pi-objectives): remove <kind> objective for <team> in <pi>"
   ```

### `vote`

1. Parse PI, team (required), confidence 1–5 (required — ask if missing).

2. Call `edpa_confidence_vote`:
   ```
   edpa_confidence_vote(pi="<pi>", team="<team>", confidence=<N>)
   ```

3. Auto-commit:
   ```bash
   git add .edpa/pi-objectives/
   git commit -m "chore(pi-objectives): confidence vote <N> for <team> in <pi>"
   ```

### `show`

1. Parse PI (required).

2. Read `.edpa/pi-objectives/<pi>.yaml` directly (Read tool). Display objectives
   grouped by team → kind (committed first, then stretch). Include BV, status,
   and per-team confidence vote.

## Notes

- Objectives live in `.edpa/pi-objectives/<pi>.yaml`. If the file does not exist,
  `edpa_objective_set` creates it automatically.
- The PI planning board renders these files under the "Objectives" tab —
  re-render with `/edpa:pi-planning <pi>` after significant changes.
- `bv` defaults to 5 when omitted; `status` defaults to `planned`.
- Committing to `pi-objectives/` does NOT count as delivery evidence for the engine —
  objectives are planning artefacts, not scored deliverables.
