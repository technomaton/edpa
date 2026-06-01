---
name: edpa:create-pi
user-invocable: true
description: >
  Create the PI-level metadata file .edpa/iterations/<PI-YYYY-N>.yaml (the
  top-level `pi:` block) — the parent record of a Planning Interval. Use when
  the user wants to "create / start a PI", "založ PI", or "new planning
  interval". Delegates to create_pi.py — the single source of behavior, also
  exposed as the edpa_pi_create MCP tool. Validates the id, refuses to
  overwrite, writes the pi: block, runs continuity validation, and
  auto-commits. Does NOT scaffold the child iterations.
license: MIT
compatibility: Python 3.10+, MCP edpa server
allowed-tools: Read Bash(python3 *) Bash(git *)
---

# EDPA Create PI — Planning Interval metadata

## What this does

Writes `.edpa/iterations/<PI-YYYY-N>.yaml` with a top-level `pi:` block. EDPA
reconstructs the PI list at runtime from `iterations/*.yaml`
(`_pi_loader.derive_pis`) — there is no `pis[]` block in `edpa.yaml`. Two file
shapes share that directory:

- `PI-2026-1.yaml`   → PI-level metadata (`pi:`)         ← this skill
- `PI-2026-1.1.yaml` → per-iteration data (`iteration:`)  ← `edpa_iteration_create`

Without the `pi:` file the loader still builds the PI but emits a
`missing_pi_yaml` warning and derives metadata (status, weeks, count, dates)
from the iterations — so you can't declare the planned shape or force status.

This is the single source of behavior used by both the `edpa_pi_create` MCP
tool and the `/edpa:create-pi` command.

## Gotchas

- **`.yaml`, never `.yml`** — the loader globs `*.yaml`; a `.yml` is silently
  ignored. The script always writes `.yaml`.
- **PI-level id only** — `PI-YYYY-N` (e.g. `PI-2026-2`). An iteration id like
  `PI-2026-2.1` is rejected; create iterations with `edpa_iteration_create`.
- **Status lifecycle** `planning → active → closed`. A PI's status is otherwise
  derived from its iterations (`_pi_status_from_iterations`).

## Steps

1. Parse the request for the PI id + optional `--start` / `--end` / `--weeks` /
   `--iterations` / `--status`. If the user gave an iteration id (`.N` suffix),
   redirect them to `edpa_iteration_create` — this skill creates the PI parent.

2. Run:
   ```bash
   python3 .edpa/engine/scripts/create_pi.py <id> \
     [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--weeks N] \
     [--iterations N] [--status planning|active|closed]
   ```
   The script validates, refuses to overwrite, writes the `pi:` block
   atomically, runs `validate_iterations.py` for continuity feedback, and
   auto-commits `chore(pi): create <id>` (pass `--no-commit` to skip the commit).

3. Report the created file and suggest next steps:
   - Add child iterations `<id>.1 … <id>.N` via `edpa_iteration_create`
     (the last one usually `type: IP`).
   - Set the running iteration `status: active` when it starts.

## What NOT to do

- **Don't hand-write the PI file** — go through `create_pi.py` so id validation,
  the `pi:` shape, atomic write, and commit stay on one path (the same path as
  the `edpa_pi_create` MCP tool).
- **Don't use a `.yml` extension** — it's silently ignored by the loader.
- **Don't scaffold iterations here** — that's `edpa_iteration_create`, by design.
