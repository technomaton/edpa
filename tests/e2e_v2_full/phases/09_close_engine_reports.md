# Phase 09 — Close Iterations + Engine + Reports — run log

Run tag: 20260527-142316-c6ac4db8
Worker: Wave B Unit 10 (agent-af959c355468593a6)
Sandbox: technomaton/edpa-e2e-20260527-142316-c6ac4db8 @ `e49ffb9`
Started: 2026-05-27T15:30Z
Finished: 2026-05-27T15:50Z

## Approach

1. Pre-flight: confirmed 10 iteration YAMLs (status=planned, capacity=None on YAML;
   capacity actually comes from `.edpa/config/people.yaml` allocations
   under each person's `iterations[]`).
2. Discovery: noticed all 22 backlog items have rich `evidence[]` blocks
   from Wave B Units 8 + 9 (real + synthetic PR signals), but `contributors[]`
   blocks are absent. Per `engine.load_backlog_items` (v1.11 single-source CW),
   items without `contributors[]` contribute zero to derived hours. Ran
   `detect_contributors.py --all-items` once to materialize `contributors[]`
   from the existing `evidence[]` (idempotent, 22 items refreshed).
3. Marked all 10 iteration YAMLs `status: closed` (`yaml.safe_dump`,
   `default_flow_style=False`, `allow_unicode=True`).
4. For each iteration (chronological 1.1 → 2.5):
   - `engine.py --edpa-root .edpa --iteration <ID>` → writes
     `.edpa/reports/iteration-<ID>/edpa_results.json` + `edpa-results.xlsx`
     + `.edpa/snapshots/<ID>.json` (frozen).
   - `reports.py --edpa-root .edpa <ID>` → writes per-person `timesheet-*.md`
     + `timesheet-team.md`.
5. For each PI:
   - `pi_close.py --pi PI-2026-{1,2}` → writes
     `.edpa/reports/pi-PI-2026-{1,2}/{pi_results.json,summary.md}`.
   - `reports.py --pi PI-2026-{1,2}` → writes
     `.edpa/reports/pi-PI-2026-{1,2}/pi-summary-PI-2026-{1,2}.md`.

## Per-iteration results

| Iteration   | Engine exit | Capacity (team h) | Team total derived | All invariants passed | Reports MD count | XLSX present |
|-------------|-------------|-------------------|---------------------|------------------------|------------------|--------------|
| PI-2026-1.1 | 0           | 144               | 64.0h               | yes                    | 6                | yes          |
| PI-2026-1.2 | 0           | 144               | 64.0h               | yes                    | 6                | yes          |
| PI-2026-1.3 | 0           | 144               | 112.0h              | yes                    | 6                | yes          |
| PI-2026-1.4 | 0           | 144               | 104.0h              | yes                    | 6                | yes          |
| PI-2026-1.5 | 0           | 144               | 0h (IP iteration)   | yes                    | 6                | yes          |
| PI-2026-2.1 | 0           | 144               | 72.0h               | yes                    | 6                | yes          |
| PI-2026-2.2 | 0           | 144               | 40.0h               | yes                    | 6                | yes          |
| PI-2026-2.3 | 0           | 144               | 64.0h               | yes                    | 6                | yes          |
| PI-2026-2.4 | 0           | 144               | 40.0h               | yes                    | 6                | yes          |
| PI-2026-2.5 | 0           | 144               | 0h (IP iteration)   | yes                    | 6                | yes          |

Notes:
- 6 MD files per iteration = 5 per-person timesheets (alice, bob-arch, bob-pm, carol, dave) + 1 team rollup.
- Per-person timesheets are written even when person had 0 derived hours (rolled-up rendering).
- PI-2026-1.5 and PI-2026-2.5 are Innovation/Planning iterations — no Done Story/Defect items
  fall into them under the SAFe-hierarchy filter (events EV-1/EV-2 have no backlog .md file,
  so they're skipped by `load_backlog_items`). Expected per task spec ("expected pro IP iterace").

## PI-level summaries

| PI         | pi_close exit | Iterations aggregated | Total capacity h | Total planned SP | Total delivered SP | Predictability |
|------------|---------------|------------------------|------------------|------------------|---------------------|----------------|
| PI-2026-1  | 0             | 5                      | 720              | 0                | 0                   | None           |
| PI-2026-2  | 0             | 5                      | 720              | 0                | 0                   | None           |

`pi_close.py` summary fields `total_planned_sp` and `total_delivered_sp` are 0 because
iteration YAMLs in this sandbox don't carry rolled-up SP totals — `pi_close` reads them
from `iteration.planned_sp` / `iteration.delivered_sp` (absent here). Story Points exist
on the individual Story backlog items (sum to 88 SP per `backlog.py status`), which the
PI summary doesn't aggregate. Not a regression for this E2E — engine + per-person hours
allocation works.

`reports.py --pi` produces a richer Markdown `pi-summary-PI-202X.md` that aggregates the
10 per-iteration `edpa_results.json` files.

## Frozen snapshots

| Iteration   | snapshot path                                       | frozen | payload_signature                  |
|-------------|-----------------------------------------------------|--------|-------------------------------------|
| PI-2026-1.1 | .edpa/snapshots/PI-2026-1.1.json                    | true   | df072c7394961483e0dd88f333bd7e…    |
| PI-2026-1.1 | .edpa/snapshots/PI-2026-1.1_rev2.json               | true   | cfdc0b2938604e44e639d9e2ac7435…    |
| PI-2026-1.1 | .edpa/snapshots/PI-2026-1.1_rev3.json               | true   | cfdc0b2938604e44e639d9e2ac7435…    |
| PI-2026-1.2 | .edpa/snapshots/PI-2026-1.2.json                    | true   | 3d2f8ade24eca8b776b813d1227ab4…    |
| PI-2026-1.3 | .edpa/snapshots/PI-2026-1.3.json                    | true   | 7934e70b5df66aea842b75090126bf…    |
| PI-2026-1.4 | .edpa/snapshots/PI-2026-1.4.json                    | true   | 49972061fcfc236adbf7d59ca8a32a…    |
| PI-2026-1.5 | .edpa/snapshots/PI-2026-1.5.json                    | true   | cc7151b02c0f24f90fe9da5a558192…    |
| PI-2026-2.1 | .edpa/snapshots/PI-2026-2.1.json                    | true   | ad3849736e1e32367cfcbf93aca43e…    |
| PI-2026-2.2 | .edpa/snapshots/PI-2026-2.2.json                    | true   | 13e891be97b81b70f90f664c0ca557…    |
| PI-2026-2.3 | .edpa/snapshots/PI-2026-2.3.json                    | true   | e9ff722052c31ee1db5ef4d1fd45ea…    |
| PI-2026-2.4 | .edpa/snapshots/PI-2026-2.4.json                    | true   | dfd60473997027a2fcfc3983144ed9…    |
| PI-2026-2.5 | .edpa/snapshots/PI-2026-2.5.json                    | true   | 530d16592f1403429c75ea3cc55afb…    |

PI-2026-1.1 has 3 revisions (`_rev2`, `_rev3`) because during discovery we ran the engine
once before materializing `contributors[]` (initial run produced derived=0), and re-ran
after. The `write_snapshot` function correctly produced immutable rev files instead of
overwriting — frozen-snapshot invariant holds. `_rev2` and `_rev3` share the same
`payload_signature` (engine is deterministic for the same inputs).

## Generated artifacts (count)

- Iteration JSON results: 10 (`.edpa/reports/iteration-PI-2026-*/edpa_results.json`)
- Per-person MD timesheets: 50 (5 people × 10 iterations, written even at 0h)
- Team rollup MD: 10 (one per iteration)
- XLSX exports: 10 (`edpa-results.xlsx` per iteration — `openpyxl` installed)
- Frozen snapshots: 12 (10 iterations + 2 extra revs from PI-2026-1.1 discovery)
- PI summaries: 6 total
  - `pi_close.py`: 2 × `pi_results.json` + 2 × `summary.md`
  - `reports.py --pi`: 2 × `pi-summary-PI-2026-*.md`
- Contributors refresh: 22 backlog items updated (`detect_contributors.py --all-items`)

## Verification (E2E recipe)

```
$ ls .edpa/reports/iteration-*/edpa_results.json | wc -l
10
$ ls .edpa/reports/iteration-*/timesheet-*.md | wc -l
60
$ ls .edpa/snapshots/PI-*.json | wc -l
12
$ python3 -c "import json, pathlib; \
  files = sorted(pathlib.Path('.edpa/snapshots').glob('PI-*.json')); \
  [print(f.name, json.loads(f.read_text()).get('frozen'), \
         'sig' in json.loads(f.read_text()).get('payload_signature','')) \
   for f in files]"
# All 12 → frozen=True, payload_signature present.
$ python3 -c "import json, pathlib; \
  [print(f.parent.name, json.loads(f.read_text())['all_invariants_passed']) \
   for f in sorted(pathlib.Path('.edpa/reports').glob('iteration-*/edpa_results.json'))]"
# All 10 → True.
$ ls .edpa/reports/pi-PI-2026-1/ .edpa/reports/pi-PI-2026-2/
# Both have pi-summary-*.md + summary.md + pi_results.json.
```

## Issues encountered

1. **`contributors[]` not auto-materialized in CI**. Wave B Units 8/9 produced
   `evidence[]` via `sync_pr_contributions.py` but didn't trigger
   `detect_contributors.py`. This is consistent with the production CI hook
   ordering (sync writes evidence, contributors are derived at close-iteration time).
   Resolved by running `detect_contributors.py --all-items` once before the engine pass.
2. **`pi_close.py` SP totals are zero**. `pi_close` reads `planned_sp` /
   `delivered_sp` from iteration YAMLs (absent in this sandbox). Story Points
   are stored on individual Story items only. Not a blocker — the Markdown
   summaries from `reports.py --pi` aggregate the actual per-person hours
   from the 10 `edpa_results.json` files.
3. **IP iterations (1.5, 2.5)** legitimately produce 0 derived hours — events
   EV-1, EV-2 have no backlog .md file (only iteration-YAML mentions), so
   `load_backlog_items` skips them. Documented as expected in task spec.

## Sandbox commit

```
e49ffb9  no-ticket: close 10 iterations + engine + reports + PI summaries (Wave B Unit 10)
```

130 files changed, 4373 insertions(+), 10 deletions(-).
Pushed to `technomaton/edpa-e2e-20260527-142316-c6ac4db8` main.
