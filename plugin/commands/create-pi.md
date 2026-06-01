---
description: Create the PI-level metadata file (.edpa/iterations/PI-YYYY-N.yaml) — the parent record of a Planning Interval
allowed-tools: Read, Bash
model: sonnet
---

# EDPA Create PI

Create the **PI-level metadata file** `.edpa/iterations/<PI-YYYY-N>.yaml`
(top-level `pi:` block) — the parent record for a Planning Interval. EDPA
reconstructs the PI list at runtime from `iterations/*.yaml`
(`_pi_loader.derive_pis`); without a `pi:` file the loader still works but
warns `missing_pi_yaml` and derives PI metadata from the child iterations —
so you lose explicit `status` / `pi_iterations` / dates.

This wraps `create_pi.py`, the single source of behavior (the same engine the
`edpa_pi_create` MCP tool calls). It does **NOT** create the child iterations —
add those afterwards with `edpa_iteration_create` (`<PI>.1 … .N`, last `type: IP`).

> **Filename gotcha:** the loader globs `*.yaml` only. A `PI-2026-1.yml` (short
> extension) is silently ignored. The script always writes `.yaml`.

## Arguments

`$ARGUMENTS` — the PI id plus optional flags:
- **id** (required) — PI-level, e.g. `PI-2026-2` (NOT an iteration id `PI-2026-2.1`)
- `--start YYYY-MM-DD` / `--end YYYY-MM-DD` — PI window (optional)
- `--weeks N` — iteration cadence in weeks (default 1)
- `--iterations N` — planned number of iterations in the PI (optional)
- `--status planning|active|closed` — default `planning`
- `--no-commit` — write the file but skip the git commit

Examples:
- `PI-2026-2`
- `PI-2026-2 --start 2026-06-02 --end 2026-09-06 --weeks 1 --iterations 5 --status active`

## Steps

1. Parse `$ARGUMENTS`. Require a PI-level id (`PI-YYYY-N`, no `.iteration`
   suffix). If the user gave an iteration id, tell them to use
   `edpa_iteration_create` instead — this command creates the PI parent only.

2. Run the script:
   ```bash
   python3 .edpa/engine/scripts/create_pi.py <id> [--start …] [--end …] \
     [--weeks N] [--iterations N] [--status …]
   ```
   It validates the id, refuses to overwrite an existing PI, writes the `pi:`
   block atomically, runs continuity validation, and auto-commits
   `chore(pi): create <id>` (pass `--no-commit` to skip).

3. Report the created file, then suggest next steps:
   - Create the child iterations `<id>.1 … <id>.N` via `edpa_iteration_create`
     (the last one usually `type: IP`).
   - Mark the running iteration `status: active` when it starts.

## Notes

- **Status lifecycle:** `planning → active → closed`. A PI's status is
  otherwise derived from its iterations (`_pi_status_from_iterations`): active
  if any iteration is active, closed once all are.
- For per-iteration files use `edpa_iteration_create`; to close an iteration
  use `/edpa:close-iteration`.
- This command does not scaffold iterations by design — one explicit PI record,
  iterations added deliberately.
