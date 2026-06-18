---
description: Close a Program Increment — verify iterations closed, flip pi.status, write the PI rollup (.edpa/reports/pi-<PI>/)
allowed-tools: Read, Bash
model: sonnet
---

# EDPA Close PI

Close a **Program Increment**: verify every child iteration is `closed`, flip the
PI-level `pi.status` to `closed` in `.edpa/iterations/<PI>.yaml`, and (re)write the
PI **rollup report** — `.edpa/reports/pi-<PI>/pi_results.json` + `summary.md`
(aggregated SP, predictability, per-person derived hours, completed Features).

This wraps `pi_close.py`, the single source of behavior (the same engine the
`edpa_pi_close` MCP tool calls). It is the PI-level counterpart to
`/edpa:create-pi` — and is distinct from `/edpa:close-iteration`, which closes a
single **iteration** (`<PI>.<n>`) and runs the engine + reports for it.

> **Close iterations first.** A PI rolls up its iterations — so close each
> `<PI>.1 … <PI>.N` via `/edpa:close-iteration` before closing the PI. The guard
> refuses a PI with any open iteration unless you pass `--force`.

## Arguments

`$ARGUMENTS` — the PI id plus optional flags:
- **id** (required) — PI-level, e.g. `PI-2026-1` (NOT an iteration id `PI-2026-1.3`)
- `--force` — roll up even if some iterations are still open (skips the guard)
- `--no-commit` — write the files but skip the git commit

Examples:
- `PI-2026-1`
- `PI-2026-1 --force`

## Steps

1. Parse `$ARGUMENTS`. Require a PI-level id (`PI-YYYY-N`, no `.iteration`
   suffix). If the user gave an iteration id, tell them to use
   `/edpa:close-iteration` instead — this command closes the PI rollup, not a
   single iteration.

2. Run the script:
   ```bash
   python3 .edpa/engine/scripts/pi_close.py --pi <id> --close
   ```
   It validates the id, refuses a PI with any open iteration (unless `--force`),
   flips `pi.status` to `closed` atomically, writes the rollup
   (`pi_results.json` + `summary.md`), and auto-commits `chore(pi): close <id>`
   (pass `--no-commit` to skip).

3. Report the rollup summary (iterations, planned/delivered SP, predictability,
   per-person derived hours, completed Features) and the written files. If the
   guard fired, list the open iterations and suggest
   `/edpa:close-iteration <PI>.<n>` for each — or `--force` to roll up anyway.

## Notes

- **Status lifecycle:** `planning → active → closed`. Closing the PI sets the
  explicit `pi.status`; the rollup aggregates only the closed iterations'
  results, so an open iteration left out (via `--force`) under-reports.
- **Re-runnable.** Safe to re-run after closing a late iteration — it
  regenerates the rollup; the status flip is a no-op once already `closed`.
- To close a single iteration (capacity prep + engine + reports + frozen
  snapshot) use `/edpa:close-iteration`; to create the PI parent use
  `/edpa:create-pi`.

## What NOT to do

- **Don't hand-edit `pi.status` or the rollup files** — go through `pi_close.py`
  so id validation, the iteration guard, atomic write, and commit stay on one
  path (the same path as the `edpa_pi_close` MCP tool).
- **Don't close a PI with open iterations** without understanding `--force`: the
  rollup only sums closed iterations, so it will under-report SP and hours.
- **Don't pass an iteration id** (`PI-2026-1.3`) — that's `/edpa:close-iteration`.
