---
description: Mark an EDPA iteration as active (single active iteration per PI)
allowed-tools: Read, Bash, mcp__plugin_edpa_edpa__edpa_iterations, mcp__plugin_edpa_edpa__edpa_iteration_activate
model: sonnet
---

# EDPA Activate Iteration

Mark iteration `$ARGUMENTS` as **active** — the iteration the team is
currently delivering. EDPA allows **at most one active iteration per PI**,
so activating one automatically demotes any other currently-active iteration
in the same PI back to `planned`.

This wraps the `edpa_iteration_activate` MCP tool — the single write layer
(ADR-002). It writes YAML only; it does **not** run the engine or generate
reports (finish an iteration with `/edpa:close-iteration`).

## Argument form

- `<iteration-id>` — the iteration to activate, e.g. `PI-2026-1.3`.

The PI is derived from the iteration id (`PI-2026-1.3` → `PI-2026-1`).

## What it does

Calling `edpa_iteration_activate` with `{ "id": "<iteration-id>" }`:

1. Sets both the nested `iteration.status` and the top-level `status` to
   `active` (the same dual-write `edpa_iteration_close` uses, so
   loader-lifted readers and top-level consumers — board, reports, the
   audit verifier — all agree the iteration is active).
2. Demotes any **other** currently-active iteration in the same PI back to
   `planned`. Closed iterations are never touched (that state is terminal),
   and nothing is closed here (closing stamps the delivery block).

The response reports the activated `id`, its `pi`, and the list of
`deactivated` sibling iterations.

## Steps

1. **(Optional) Show current lifecycle** so the state change is transparent:

   Call `edpa_iterations` (filter `status: active`) to see which iteration,
   if any, is currently active in the PI.

2. **Activate** the target iteration:

   Call `edpa_iteration_activate` with the iteration id, e.g.
   `{ "id": "PI-2026-1.3" }`.

3. **Confirm** the result to the user — echo the activated iteration and any
   siblings that were demoted to `planned`.

## Notes

- Activating an iteration that does not exist returns an error — create it
  first with `edpa_iteration_create`.
- A PI-level metadata file (top-level `pi:` block, e.g. `PI-2026-1.yaml`) is
  not an iteration; the tool refuses it. Manage PI status with
  `/edpa:create-pi` / `/edpa:close-pi`.
- Re-running for an already-active iteration is a safe no-op.
