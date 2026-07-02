---
name: engine
user-invocable: true
description: >
  Run EDPA evidence-driven calculation for an iteration by invoking the
  vendored engine script (.edpa/engine/scripts/engine.py). The engine reads
  the materialized evidence[]/contributors[] persisted in each item's YAML
  (written by the post-commit hook / /edpa:materialize — it does not scan git
  at compute time), computes CW from cw_heuristics, calculates Score and
  DerivedHours, validates invariants, and writes results JSON + XLSX + a
  frozen snapshot. Use when closing an iteration, computing derived hours,
  or running "EDPA výpočet". Produces the input for the reports skill.
license: MIT
compatibility: Python 3.10+, .edpa/config/people.yaml, .edpa/config/cw_heuristics.yaml
allowed-tools: Read Bash(python3 *) Bash(git *) Grep
---

# EDPA Engine — Evidence-Driven Calculation

## What this does

Computes derived hours for all team members for a given iteration by
running the deterministic engine script. Per ADR-003 ("heavy compute /
file generation → directly script"), this skill is a thin wrapper: it
resolves the iteration argument, shells out to
`.edpa/engine/scripts/engine.py`, and interprets the output. It never
re-implements the calculation.

One successful run writes, under `.edpa/`:

| Artifact | Path |
|----------|------|
| Engine results | `reports/iteration-<ID>/edpa_results.json` |
| Excel workbook (Team Summary + Item Costs tabs) | `reports/iteration-<ID>/edpa-results.xlsx` |
| Frozen audit snapshot (content-hashed) | `snapshots/<ID>.json` |

## Arguments

`$ARGUMENTS` = iteration ID (e.g., "PI-2026-1.3") or "latest" for most recent closed iteration.

### Argument resolution (when $ARGUMENTS is empty)

If `$ARGUMENTS` is empty, blank, or "help":

1. Call MCP tool `edpa_iterations` (or read `.edpa/iterations/*.yaml`
   directly). PI/iteration timeline data is reconstructed at runtime
   from those per-PI and per-iteration YAML files — `edpa.yaml` no
   longer carries `pis[]`.
2. Present available iterations with status and dates:
   ```
   Available iterations:
     PI-2026-1.1  [closed]   2026-04-06–2026-04-17
     PI-2026-1.2  [closed]   2026-04-20–2026-05-01
     PI-2026-1.3  [closed]   2026-05-04–2026-05-15
     PI-2026-1.4  [active]   2026-05-18–2026-05-29  <-- suggested
     PI-2026-1.5  [planned]  2026-06-01–2026-06-12  (IP)
   ```
3. **Default suggestion:** the iteration with `status: active`. If none is active, suggest the latest `closed`.
4. Ask user: "Which iteration to compute? [suggested-id]"
5. If user confirms or provides an ID, proceed. If `.edpa/config/edpa.yaml` does not exist, inform user to run `/edpa setup` first.

## Prerequisites

- `.edpa/config/people.yaml` exists (run /edpa:setup first)
- `.edpa/config/cw_heuristics.yaml` exists (seeded by `project_setup.py`;
  a legacy `heuristics.yaml` is still accepted as fallback)
- Backlog items carry `js:` (Job Size) in their YAML — V2 keeps Job Size
  in the backlog files, not in any GitHub field
- The iteration has Done stories/defects/tasks and/or recorded gate
  transitions
- Evidence is materialized in the item YAML (see "Where the signals
  come from" below)

## Run the engine

```bash
python3 .edpa/engine/scripts/engine.py --edpa-root .edpa --iteration <iteration-id>
```

**Never hand-compute.** Do not load config with inline Python, do not
hand-calculate scores or hours, and do not hand-write
`edpa_results.json`. The script is the single deterministic
implementation — it enforces the invariants, stamps the methodology
version into results and snapshot, and produces the XLSX + content-hashed
snapshot the audit trail relies on.

Useful variants:

```bash
# Setup doctor — what is configured, what is missing (read-only)
python3 .edpa/engine/scripts/engine.py --status

# Worked example with built-in sample data (writes no files)
python3 .edpa/engine/scripts/engine.py --demo

# Explain one person's allocation from already-computed results
python3 .edpa/engine/scripts/engine.py --edpa-root .edpa \
  --iteration <iteration-id> --explain <person-id> [--explain-item <item-id>]
```

`--output <path>` overrides the results JSON path.

## Interpret the output

1. **Summary table** — stdout ends with a per-person summary (capacity,
   derived hours, items, invariant status). Relay it to the user.
2. **Invariants** — on a hard invariant failure the engine reports it
   and exits 1 (`all_invariants_passed: false` in the JSON). Report
   which check failed; never "fix" numbers by hand.
3. **Snapshot line** — `Snapshot frozen: …` on first freeze;
   `refreshed (same content, frozen_at updated)` on an identical rerun;
   `new revision (content changed); previous: <ID>.json` when inputs
   changed. Frozen snapshots are immutable — changed reruns create
   `<ID>_rev<N>.json` instead of overwriting.
4. **`Excel export skipped (install openpyxl for XLSX output)`** —
   XLSX needs openpyxl; the JSON results and snapshot are unaffected.

Then:

- Suggest `/edpa:reports <iteration-id>` to render per-person timesheets.
- **Nothing is auto-committed.** The engine only writes files; commit
  the generated `reports/` + `snapshots/` outputs as part of the
  iteration-close batch.

## Background — what the script computes

For reference when explaining results (the script does all of this;
you never re-do it):

- **Pure reader.** The engine reads the materialized `evidence[]` /
  `contributors[]` blocks persisted in each item's YAML. It does not
  scan git (or call `gh`) at compute time — so the report equals the
  persisted state, deterministically, on any machine.
- **CW** comes from `detect_contributors.py` aggregation: additive
  signal weights from `cw_heuristics.yaml`
  (`contribution_score[P, item] = Σ signal_weight`), normalized per
  item so `Σ_persons cw[*, item] = 1.0`. Manual `/contribute` weights
  stack additively. Role labels (owner/key/reviewer/consulted) are
  display-time projections, never stored.
- **Score** per person P:

  ```
  Score[P, done_item]  = JobSize[item]   × CW[P, item]                  # Story / Defect / Task at Done
  Score[P, gate_event] = JobSize[parent] × gate_weight × CW[P, parent]  # Feature/Epic/Initiative transition
  Score[P, activity]   = JobSize[story]  × credit_factor × CW[P, story] # in-flight Story yaml_edit activity
  ```

  When git history records no transitions and no yaml_edit activity,
  only Done-item credit fires — the calculation degenerates gracefully
  to Done-only behaviour (the pre-v1.14 `--mode` selector is gone).
- **Hours**: `DerivedHours[P, item] = (Score[P, item] / Σ Score[P, *]) × Capacity[P]`.
- **Invariants** (hard ones halt the run): `Σ DerivedHours[P, *] =
  Capacity[P] ± 0.01`, share ratios sum to 1.0, no negative hours.
  Missing Job Size warns and skips the item.

### Where the signals come from (not the engine's job)

The post-commit hook (`local_evidence.py`) materializes `commit_author`,
`/contribute`, `yaml_edit`, and `state_transition` signals as each commit
lands. To backfill history, commits made with `EDPA_NO_LOCAL_EVIDENCE=1`,
or signals from another machine, run `/edpa:materialize` (MCP tool
`edpa_materialize`, or `local_evidence.py --materialize --iteration <id>`
/ `--all-iterations`) — idempotent, deduped by `ref`. PR-thread signals
(`pr_reviewer`, `issue_comment`) are materialized by the optional
`edpa-contribution-sync` CI workflow. The engine then just reads the
result.

## Error handling

- Script errors with `--edpa-root or (--iteration + --capacity +
  --heuristics) required` → always pass `--edpa-root .edpa` in a V2
  project (the flag has no default).
- PI id instead of iteration id (e.g. "PI-2026-1" not "PI-2026-1.3") →
  the engine refuses: a PI label would silently drop every item tagged
  `<pi>.N`. Use `/edpa:close-pi <PI>` for PI rollups.
- No items in iteration → "No closed items found for {iteration}.
  Check iteration label."
- Missing Job Size → warn per item, excluded from calculation.
- Person with 0 relevant items → 0h derived (process issue, not math issue).
- Evidence missing / contributors empty → the engine does **not** scan
  git to recover it; run `/edpa:materialize <iteration>` to persist the
  signals into `evidence[]`, then re-run the engine.
