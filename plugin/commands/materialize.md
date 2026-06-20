---
description: Materialize git-derived signals into evidence[] so the report equals the persisted snapshot
allowed-tools: Read, Bash
model: sonnet
---

# EDPA Materialize

Persist git-derived signals into each item's `evidence:` block so the engine
report derives **only** from the materialized snapshot — never from an
in-memory git re-scan. `$ARGUMENTS`: the iteration ID (e.g. `PI-2026-1.3`).

This is the reconcile/catch-up path: it writes the signals the post-commit hook
would have written but didn't (commits made with `EDPA_NO_LOCAL_EVIDENCE=1`,
history predating the hook, commits from another machine). It is **idempotent**
— each signal is keyed by its commit-hash `ref`, so re-running adds nothing.

## What it writes (Phase 1)

- **`state_transition`** — one per backlog `status:` change in the iteration
  window: `from_status` → `to_status`, `person` (commit author), `at`
  (author date), `ref` = `commit/<hash>/<id>/<from>-><to>`. **`weight: 0`** —
  it is an analytics record (delivery lead time, time-in-state), so it never
  changes `contributors[]` / cw.

## Steps

1. Require an iteration ID in `$ARGUMENTS`. If missing, ask for it.

2. Run the `edpa_materialize` MCP tool with `iteration: <id>` (or
   `python3 .edpa/engine/scripts/local_evidence.py --materialize --iteration <id>`).
   It scans the window, writes `evidence:` and creates one `chore(evidence):`
   commit.

3. Report the tool's summary: `<n> item(s) updated (<m> transitions scanned)`.
   If 0 items updated, evidence is already in sync — say so.

4. Recompute contributors + report so the snapshot is consistent:
   ```bash
   python3 .edpa/engine/scripts/detect_contributors.py --all-items
   ```
   then re-run the engine for that iteration. (Closing the iteration via
   `/edpa:close-iteration` runs the same C7.6 refresh.)

## What NOT to do

- Do NOT edit `evidence:` / `contributors:` by hand — let the tool write them.
- Do NOT pass `EDPA_NO_LOCAL_EVIDENCE=1` to materialize; it is the explicit
  catch-up path and ignores that flag by design.
