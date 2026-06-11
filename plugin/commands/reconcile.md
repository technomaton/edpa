---
description: Reconcile git delivery evidence with backlog status (find shipped-but-not-Done items)
allowed-tools: Read, Bash
model: sonnet
---

# EDPA Reconcile

Find backlog items whose git evidence disagrees with their `status:` — work
that merged but still sits in Funnel/Backlog (velocity under-reports it), and
Done items with no commit evidence. `$ARGUMENTS` (optional): `--apply`,
`--branch <name>`, `--stale-days <n>`.

## How evidence works

Only commit **subjects** on the main branch count (`feat(S-42): …` CC scope or
a bare `S-42` in the subject). Body mentions and auto-prefixed commits
(`chore(evidence):`, `Merge`, …) never count. Suggestion rules:

- evidence contained in a release tag → **Done**
- latest evidence quiet ≥ stale-days (default 3) → **Done** (`closed_at` = evidence date)
- fresh evidence, item not yet Implementing → **Implementing**
- Feature/Epic/Initiative are never auto-suggested Done (rollup/human call)

## Steps

1. Run the read-only report via the `edpa_reconcile` MCP tool (or
   `python3 .edpa/engine/scripts/reconcile.py --json`). Pass `branch` /
   `stale_days` if the user gave them.

2. Show the result as a table: `ID | current → suggested | reason | evidence`.
   List phantoms ("Done without evidence") separately — they are review-only,
   often legitimate (bundle commits, docs-only delivery).

3. If there is no drift, say so and stop.

4. If the user wants the changes applied (said `--apply`, or confirms when you
   ask once): transition each stuck item via the `edpa_item_transition` MCP
   tool (it validates the workflow and stamps `closed_at`). Do NOT edit the
   YAML by hand.

5. Commit the transitions:
   ```bash
   git add .edpa/backlog/
   git commit -m "chore(<first-item-id>): reconcile backlog status with git evidence (<n> items)"
   ```

6. Report: `<n> reconciled, <m> phantoms left for review`. Suggest re-running
   `/edpa:reconcile` after the next release tag.

## What NOT to do

- Do NOT mark phantoms Done→Funnel or "fix" them automatically — they need a
  human decision.
- Do NOT count body mentions as evidence (the tool already doesn't) — bulk
  commits enumerate IDs they don't deliver.
