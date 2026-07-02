---
name: reports
user-invocable: true
description: >
  Generate EDPA timesheets and PI summaries by invoking the vendored reports
  script (.edpa/engine/scripts/reports.py). Renders per-person
  timesheet-<person>.md files and the timesheet-team.md rollup from engine
  results, plus pi-summary-<PI>.md aggregation in --pi mode. Use when user
  asks for "reports", "výkazy", "timesheets", or "PI summary". Requires
  /edpa:engine results (edpa_results.json) as input.
license: MIT
compatibility: Python 3.10+, .edpa/reports/iteration-<ID>/edpa_results.json (from /edpa:engine)
allowed-tools: Read Bash(python3 *) Bash(git *)
---

# EDPA Reports — Timesheet & PI Summary Generation

## What this does

Renders the human-readable EDPA artifacts from engine results by
running the deterministic reports script. Per ADR-003 ("heavy compute /
file generation → directly script"), this skill is a thin wrapper: it
resolves the argument, shells out to `.edpa/engine/scripts/reports.py`,
and summarizes what was written. It never hand-renders a timesheet —
the script's Markdown is stable and diffable across reruns.

## Arguments

`$ARGUMENTS` = iteration ID (e.g., "PI-2026-1.3"), or "pi <PI-ID>" for PI-level aggregation.

### Argument resolution (when $ARGUMENTS is empty)

If `$ARGUMENTS` is empty, blank, or "help":

1. Call MCP tool `edpa_iterations` (or read `.edpa/iterations/*.yaml`
   directly). PI/iteration timeline data is reconstructed at runtime
   from those per-PI and per-iteration YAML files — `edpa.yaml` no
   longer carries `pis[]`.
2. Check which iterations already have results in
   `.edpa/reports/iteration-<ID>/edpa_results.json`.
3. Present options:
   ```
   Available iterations:
     PI-2026-1.1  [closed]   2026-04-06–2026-04-17   results: yes
     PI-2026-1.2  [closed]   2026-04-20–2026-05-01   results: yes
     PI-2026-1.3  [closed]   2026-05-04–2026-05-15   results: yes
     PI-2026-1.4  [active]   2026-05-18–2026-05-29   results: no (run engine first)

   Other options:
     "pi <PI-ID>"   PI-level aggregation across that PI's iterations with results
   ```
4. **Default suggestion:** the latest `closed` iteration that has `edpa_results.json`.
5. Ask user: "Generate reports for which iteration? [suggested-id]"
6. If `.edpa/` does not exist, inform user to run `/edpa setup` first.

## Prerequisites

- `.edpa/reports/iteration-<ID>/edpa_results.json` exists (run
  `/edpa:engine <iteration-id>` first)

## Run the script

Per-iteration timesheets:

```bash
python3 .edpa/engine/scripts/reports.py <iteration-id>
```

PI-level aggregation:

```bash
python3 .edpa/engine/scripts/reports.py --pi <PI-ID>
```

Options: `--edpa-root <path>` (default `.edpa`), `--out <dir>` to
override the output directory.

**Never hand-render.** Do not read `edpa_results.json` and write
timesheet Markdown yourself — the script is the single canonical
renderer (stable columns, capacity-override annotations, role
projection). Hand-rendered output drifts and breaks diff checks.

## Output artifacts

### Iteration mode → `.edpa/reports/iteration-<ID>/`

- **`timesheet-<person>.md`** — one per person in the results:
  iteration, methodology (version stamped by the engine), capacity
  (with baseline/override detail when a capacity override was
  recorded), derived hours, invariant status, and an item table
  (`Item | Level | Role | JS | CW | Score | Ratio | Hours`). The Role
  column is a display-time projection from evidence signal types
  (owner / key / reviewer / consulted).
- **`timesheet-team.md`** — team rollup: methodology, planning factor,
  team capacity vs. team derived, one row per person (an Override
  column appears only when at least one override was applied).

The script prints every file it wrote with per-person derived hours —
relay that list to the user.

### PI mode → `.edpa/reports/pi-<PI-ID>/`

- **`pi-summary-<PI-ID>.md`** — per-person capacity/derived totals
  across all iterations of the PI that have results, plus a
  per-iteration breakdown (team totals, invariants).

### Related artifacts (produced by /edpa:engine, not this skill)

- `edpa-results.xlsx` (Team Summary + Item Costs tabs) — per-item cost
  allocation lives in the Item Costs tab.
- Frozen snapshot `.edpa/snapshots/<ID>.json` — immutable,
  content-hashed; changed engine reruns create `<ID>_rev<N>.json`
  revisions instead of overwriting.

For a "who paid for item X" question, use the Item Costs XLSX tab, or:

```bash
python3 .edpa/engine/scripts/engine.py --edpa-root .edpa \
  --iteration <iteration-id> --explain <person-id> --explain-item <item-id>
```

## Flow metrics

For lightweight analytics without a full engine run, use the `edpa_flow_metrics` MCP tool. It computes cycle time (median days from `created_at` to `closed_at`), throughput (items closed per week), and open-item age from the timestamp fields populated by sync. No `edpa_results.json` required — it reads backlog YAML directly.

## Error handling

- Missing `edpa_results.json` → the script exits with an error; run
  `/edpa:engine <iteration-id>` first.
- `--pi` finds no `iteration-<PI>.*` results directories → run the
  engine for at least one iteration of that PI first.
- `Invariant: FAIL` on a timesheet → the engine recorded an invariant
  violation for that person; re-run `/edpa:engine` and investigate with
  `--explain` before distributing timesheets.
- **Nothing is auto-committed.** Commit the generated timesheets (and
  PI summary) as part of the iteration-close batch.
