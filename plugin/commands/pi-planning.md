---
description: Generate the self-contained PI planning / overview HTML (program board, objectives, ROAM, portfolio, capacity) — a read-only projection of .edpa/, much broader than /edpa:reports
allowed-tools: Read, Bash
model: sonnet
---

# EDPA PI Planning

Generate a **self-contained, read-only PI planning / overview** page for a
Planning Interval: program board (teams × iterations), PI objectives, ROAM
risks, portfolio rollup, WSJF, capacity. It is a single portable `.html` with
all data baked in — no server, no Node, no network — that opens in any browser
on any machine with the EDPA (Python) engine.

This wraps `pi_planning.py`, the single source of behavior (the same engine the
`edpa_pi_board` MCP tool calls). It reads `.edpa/` and injects the versioned
`window.__EDPA__` snapshot into the prebuilt UI bundle.

> **Read-only by design.** The page never writes back. To change the plan, edit
> `.edpa/` (via the `edpa_item_*` / `edpa_iteration_*` MCP tools or directly)
> and **re-run this command** to re-render. State lives in git, not the HTML.

## Arguments

`$ARGUMENTS` — optional:
- **PI id** (optional) — e.g. `PI-2026-1`. Omit to use the default
  (planning > active > first PI).
- `--open` — open the generated file in the default browser afterwards.
- `--output <path>` — write somewhere other than the default report path.

Examples:
- *(no args)* — default PI
- `PI-2026-1`
- `PI-2026-1 --open`

## Steps

1. Parse `$ARGUMENTS` into an optional PI id and flags.

2. Run the script:
   ```bash
   python3 .edpa/engine/scripts/pi_planning.py [PI-YYYY-N] [--open]
   ```
   It discovers the repo root, builds the snapshot (people, iterations,
   backlog, objectives), injects it into the vendored
   `.edpa/engine/assets/pi-bundle.html`, and writes
   `.edpa/reports/pi-<PI>/pi-<PI>.html`.

3. Report the generated path and the summary line (PI, item/people counts,
   objectives, schema version). If `--open` was not passed, tell the user they
   can open the file directly or re-run with `--open`.

## Notes

- **Differs from `/edpa:reports`:** `reports` is the backward-looking
  per-iteration accounting (timesheets, hours, audit). This is the
  forward-looking, program-level planning picture for a whole PI.
- **Regenerable + repeatable:** same `.edpa/` → same HTML. Commit it, email it,
  open it offline — it is a deterministic artifact.
- **Bundle missing?** If the script reports the bundle was not found, the engine
  was vendored before this feature shipped — re-run `/edpa:setup` (or
  `python3 .edpa/engine/scripts/project_setup.py`) to vendor
  `assets/pi-bundle.html`.

## What NOT to do

- **Don't hand-edit the generated `.html`** — it is overwritten on every run.
  Edit `.edpa/` and re-render.
- **Don't expect writes from the page** — it is a read-only projection. Mutations
  go through the `edpa_*` MCP write tools + git.
