---
description: Close an EDPA iteration (capacity prep + engine + reports)
allowed-tools: Read, Write, Bash, Grep
model: sonnet
---

# Close Iteration

Close iteration `$ARGUMENTS`.

## Argument forms

- `<iteration-id>` — full close: prep step + engine + reports + commit
- `<iteration-id> --prep-only` — capacity-override prep only, no engine
- `<iteration-id> --skip-prep` — skip the override prompt (engine + reports only)

Examples: `PI-2026-1.3`, `PI-2026-1.3 --prep-only`, `PI-2026-1 --skip-prep`.

## Stage 1 — Capacity-override prep (v1.10.0+)

Before running the engine, ask whether anyone had non-baseline
capacity this iteration (PTO, sick leave, overtime, onboarding ramp).

**Skip Stage 1** when:
- The iteration argument is a PI-level id (no `.<n>` suffix, e.g.
  `PI-2026-1` not `PI-2026-1.3`) — overrides live on the per-iteration
  files, not the PI rollup.
- `$ARGUMENTS` contains `--skip-prep`.
- The iteration's `status:` is already `closed` — that's an immutable
  audit state; surface a warning and stop unless `--skip-prep` is also
  set.

**Run Stage 1** otherwise:

1. List current overrides for transparency:
   ```bash
   python3 .edpa/engine/scripts/capacity_override.py <iteration-id> --list
   ```

2. Ask the user:
   > Did anyone have non-baseline capacity this iteration?
   > (PTO, sick leave, overtime, onboarding ramp)
   > [add / done / list]

3. If `add`, drive the interactive flow once per override:
   ```bash
   python3 .edpa/engine/scripts/capacity_override.py <iteration-id> --add
   ```
   The script auto-commits each override with an audit message
   (`<iteration-id>: capacity override <person> -> <hours>h (<note>)`).
   Loop until the user picks `done`.

4. If `$ARGUMENTS` contains `--prep-only`, stop here. Print:
   > prep complete — iteration NOT closed; re-run without
   > `--prep-only` to close.
   Then exit.

## Stage 2 — Engine + reports

Skip Stage 1 to here when `--skip-prep` or for closed iterations
already audited.

### Stage 2a (V2-only) — Mid-flight PR sync

If `.github/workflows/edpa-contribution-sync.yml` is installed (V2
project with CI materialization, per ADR-013), refresh the YAML signals
for any **open** PRs mentioning items in this iteration. The CI
workflow only commits on `pull_request:closed` by default, so open PRs
at close time would otherwise leave their evidence outside the engine's
view.

For each open PR referencing items in the closing iteration:

```bash
python3 .edpa/engine/scripts/sync_pr_contributions.py \
  --pr <PR_NUMBER> --rebuild --skip-commit
```

The `--skip-commit` flag writes the YAML in-process so engine sees
current state without spamming the git log with mid-iteration commits.
After Stage 2 completes, decide whether to commit those YAML changes
(the close commit batch is the natural place).

Skip this stage if `EDPA_NO_GH=1` is set or the workflow file is absent.

### Stage 2b — Refresh contributors[] (V2.1 C7.6)

Before invoking the engine, refresh `contributors[]` on **every**
backlog item that has accumulated `evidence[]` signals since the
last close. Without this step, Feature/Epic/Initiative gate events
inherit a stale `contributors[]` snapshot (typically set when the
LBC was first written) — the engine then credits whoever happened
to be in that early snapshot, not the people who actually moved
the item through its lifecycle in this iteration.

```bash
python3 .edpa/engine/scripts/detect_contributors.py --all-items
```

Idempotent: items without `evidence[]` are no-ops. Cost is trivial
(<1s for typical backlogs). Auto-commits as `chore(contributors): …`
follow-up.

### Stage 2c — Engine + reports

Invoke the existing skills in sequence:

1. `edpa-engine` — computes derived hours from delivery evidence
   (commits, PRs, reviews) plus any capacity overrides recorded in
   Stage 1. Writes `edpa_results.json` and `edpa-results.xlsx`
   (Team Summary + Item Costs tabs).
2. `edpa-reports` — generates per-person `timesheet-<id>.md` files,
   the team rollup `timesheet-team.md`, and freezes the audit
   snapshot under `.edpa/snapshots/<iteration-id>.json`.

Engine + reports already auto-commit the results, so no extra
commit at this layer.

## Closed-iteration safety

If the iteration's `status:` is already `closed`:
- For full close or `--skip-prep`: warn that you are re-running and
  ask for explicit confirmation. Closed snapshots are immutable —
  re-running engine produces a new revision file (`<id>_rev<n>.json`)
  rather than overwriting.
- For `--prep-only`: refuse outright. Closed iterations cannot accept
  new overrides.
