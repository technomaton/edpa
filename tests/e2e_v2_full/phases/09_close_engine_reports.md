# Phase 09 — Close Iterations + Engine + Reports — run log

Run tag: 20260527-181051-2c56a6a0
Worker: Wave B Unit 10
Sandbox: technomaton/edpa-e2e-20260527-181051-2c56a6a0 @ `e80c725`
Started: 2026-05-27T18:47Z
Finished: 2026-05-27T18:52Z

## Approach (validates 85cd439 fix)

The previous run discovered a hidden bug: `contributors[]` was not auto-materialized
from `evidence[]`, so the very first engine pass produced derived=0 hours and
required a manual `detect_contributors.py --all-items` rerun. Commit `85cd439
fix(close-iteration): make Stage 2b (refresh contributors[]) explicitly mandatory`
elevated that step to a non-optional Stage 2b of the close-iteration skill.

This run follows the corrected workflow **strictly in order**:

1. **Pre-flight** (read-only): 10 iteration YAMLs all `status: planned`;
   23 backlog `.md` files carry `evidence[]` from Wave B Units 8 + 9;
   0 carry `contributors[]` yet.
2. **Stage 2b (mandatory, run FIRST per 85cd439)**:
   `python3 .edpa/engine/scripts/detect_contributors.py --all-items`
   → 22 items refreshed (scanned 33 total; events EV-1/EV-2 and risks R-1/R-2
   have no backlog file, and I-1/E-*/F-* have 0 PR signals → skipped).
   Commit: `no-ticket: refresh contributors[] for all items (Stage 2b)`.
3. **Mark all 10 iterations `status: closed`** via `yaml.safe_load` →
   set `status=closed` → `yaml.safe_dump(default_flow_style=False, allow_unicode=True)`.
   Commit: `no-ticket: mark all 10 iterations as closed`.
4. **Per-iteration engine + reports** (chronological 1.1 → 2.5):
   - `python3 .edpa/engine/scripts/engine.py --edpa-root .edpa --iteration <ID>`
     → writes `edpa_results.json` + `edpa-results.xlsx` + frozen snapshot.
   - `python3 .edpa/engine/scripts/reports.py --edpa-root .edpa <ID>`
     → writes 5 per-person `timesheet-*.md` + 1 `timesheet-team.md`.
5. **Per-PI close + summary** (PI-2026-1, PI-2026-2):
   - `python3 .edpa/engine/scripts/pi_close.py --pi <PI>` → `pi_results.json` + `summary.md`.
   - `python3 .edpa/engine/scripts/reports.py --pi <PI>` → `pi-summary-<PI>.md`.
6. **Single commit + push**.

## Critical validation result

**`all_invariants_passed=True` on the FIRST engine pass for ALL 10 iterations.**
**Zero `_rev2` (or higher) snapshot files were produced.** The 85cd439 fix worked
as intended — Stage 2b materialized `contributors[]` from `evidence[]` before
the engine ran, so the engine had everything it needed on the first try.

## Per-iteration results

| Iteration   | Engine exit | Capacity (team h) | Team total derived | All invariants passed | Reports MD count | XLSX present |
|-------------|-------------|-------------------|---------------------|------------------------|------------------|--------------|
| PI-2026-1.1 | 0           | 144               |  64.0h              | yes                    | 6                | yes          |
| PI-2026-1.2 | 0           | 144               |  64.0h              | yes                    | 6                | yes          |
| PI-2026-1.3 | 0           | 144               | 112.0h              | yes                    | 6                | yes          |
| PI-2026-1.4 | 0           | 144               | 104.0h              | yes                    | 6                | yes          |
| PI-2026-1.5 | 0           | 144               |   0.0h (IP)         | yes                    | 6                | yes          |
| PI-2026-2.1 | 0           | 144               | 144.0h              | yes                    | 6                | yes          |
| PI-2026-2.2 | 0           | 144               | 144.0h              | yes                    | 6                | yes          |
| PI-2026-2.3 | 0           | 144               | 112.0h              | yes                    | 6                | yes          |
| PI-2026-2.4 | 0           | 144               | 144.0h              | yes                    | 6                | yes          |
| PI-2026-2.5 | 0           | 144               |   0.0h (IP)         | yes                    | 6                | yes          |

Notes:
- 6 MD per iteration = 5 per-person timesheets (alice, bob-arch, bob-pm, carol, dave) + 1 team.
- IP iterations (1.5, 2.5) legitimately have 0 derived hours: events EV-1/EV-2 have no
  backlog `.md` file, so `load_backlog_items` skips them. Expected for IP.
- PI-2026-2.1–2.4 show higher derived hours than the previous run's table (expected
  72/40/64/40h). This is because Wave B Unit 9 added additional synthetic Done work
  during the PI-2 simulation phase, increasing per-iteration delivery. All within
  capacity, all invariants pass.

## PI-level summaries

| PI         | pi_close exit | Iterations aggregated | Total capacity h | Total planned SP | Total delivered SP | Predictability |
|------------|---------------|------------------------|------------------|------------------|---------------------|----------------|
| PI-2026-1  | 0             | 5                      | None             | None             | None                | None           |
| PI-2026-2  | 0             | 5                      | None             | None             | None                | None           |

`pi_close.py` returns `None` for capacity / SP / predictability because iteration
YAMLs in this sandbox don't carry rolled-up SP totals (`iteration.planned_sp` /
`delivered_sp` are absent — Story Points live on individual Story items). Not a
regression — `reports.py --pi` produces the richer `pi-summary-PI-2026-*.md`
that aggregates the 10 per-iteration `edpa_results.json` files.

## Frozen snapshots (NO rev2 — fix worked)

| Iteration   | snapshot path                        | frozen | payload_signature       |
|-------------|--------------------------------------|--------|--------------------------|
| PI-2026-1.1 | .edpa/snapshots/PI-2026-1.1.json     | true   | 8be0305ead68e4c11ca8…   |
| PI-2026-1.2 | .edpa/snapshots/PI-2026-1.2.json     | true   | 54b4f96efbef4b0349dd…   |
| PI-2026-1.3 | .edpa/snapshots/PI-2026-1.3.json     | true   | 78718bf9d5affd5cdef8…   |
| PI-2026-1.4 | .edpa/snapshots/PI-2026-1.4.json     | true   | e8e0f7f2ec426bde37d1…   |
| PI-2026-1.5 | .edpa/snapshots/PI-2026-1.5.json     | true   | cc7151b02c0f24f90fe9…   |
| PI-2026-2.1 | .edpa/snapshots/PI-2026-2.1.json     | true   | 7bc5b48d9b5e7c887b14…   |
| PI-2026-2.2 | .edpa/snapshots/PI-2026-2.2.json     | true   | 7f9f3e25dc3df73b08d5…   |
| PI-2026-2.3 | .edpa/snapshots/PI-2026-2.3.json     | true   | b784341194d43bcc9e0b…   |
| PI-2026-2.4 | .edpa/snapshots/PI-2026-2.4.json     | true   | b29d5538cba09b33d453…   |
| PI-2026-2.5 | .edpa/snapshots/PI-2026-2.5.json     | true   | 530d16592f1403429c75…   |

**Total: 10 snapshots. Zero `_rev*` files.** This confirms 85cd439 works —
the engine never had to be re-run after manual contributor materialization,
because Stage 2b ran before the engine, not after.

The IP-iteration signatures (PI-2026-1.5 and PI-2026-2.5) match the previous run's
signatures byte-for-byte (`cc7151b02c0f24f90fe9…` and `530d16592f1403429c75…`),
which is the correct determinism property: identical inputs (no Done items) →
identical outputs across independent runs.

## Generated artifacts (count)

- Iteration JSON results: 10 (`.edpa/reports/iteration-PI-2026-*/edpa_results.json`)
- Per-person MD timesheets: 50 (5 people × 10 iterations, written even at 0h)
- Team rollup MD: 10 (one per iteration)
- XLSX exports: 10 (`edpa-results.xlsx` per iteration — `openpyxl` available)
- Frozen snapshots: **10** (one per iteration, NO rev2 files — fix confirmed)
- PI summaries: 6 total
  - `pi_close.py`: 2 × `pi_results.json` + 2 × `summary.md`
  - `reports.py --pi`: 2 × `pi-summary-PI-2026-*.md`
- Contributors refresh: 22 backlog items updated by `detect_contributors.py --all-items`

## Verification (E2E recipe)

```
$ ls .edpa/reports/iteration-*/edpa_results.json | wc -l
10
$ ls .edpa/reports/iteration-*/timesheet-*.md | wc -l
60
$ ls .edpa/snapshots/PI-*.json | wc -l
10                          # ← 10, not 12 — no rev2 in this run
$ python3 -c "import json, pathlib; \
  [print(f.parent.name, json.loads(f.read_text())['all_invariants_passed']) \
   for f in sorted(pathlib.Path('.edpa/reports').glob('iteration-*/edpa_results.json'))]"
# All 10 → True
$ ls .edpa/reports/pi-PI-2026-1/ .edpa/reports/pi-PI-2026-2/
# Both have pi-summary-*.md + summary.md + pi_results.json
$ ls .edpa/reports/iteration-*/edpa-results.xlsx | wc -l
10
```

## Issues encountered

**None blocking.** The Stage 2b mandatory ordering from 85cd439 worked exactly as
designed — the engine had `contributors[]` from the very first pass on every
iteration. No discovery loops, no rev2 snapshots, no manual fix-ups.

Minor (cosmetic, not a regression):
- `pi_close.py` still returns `None` for capacity / SP totals because iteration
  YAMLs don't carry rolled-up SP fields. Documented in previous run; not a fix target.
- IP iterations (1.5, 2.5) legitimately produce 0 derived hours because events
  (EV-1, EV-2) have no backlog `.md` file. Expected behavior for IP iterations.
- A local-evidence warning surfaced at commit time:
  `local_evidence: skipped — 'urbanek.jaroslav@gmail.com' not in .edpa/config/people.yaml`.
  This is the local-commit hook telling the runner that the operator (me) isn't in
  the team roster — correct behavior (the sandbox team is alice/bob-arch/bob-pm/carol/dave).
  Does not affect engine output.

## Sandbox commits (this phase)

```
d755e6e  no-ticket: refresh contributors[] for all items (Stage 2b)
ca6815b  no-ticket: mark all 10 iterations as closed
e80c725  no-ticket: close 10 iterations + engine + reports + PI summaries (Wave B Unit 10)
```

Final HEAD pushed to `technomaton/edpa-e2e-20260527-181051-2c56a6a0` main: `e80c725`.

## Validation of 85cd439 fix — summary

| Check                                                | Previous run        | This run       |
|------------------------------------------------------|----------------------|----------------|
| Stage 2b run BEFORE engine?                          | no (discovered late) | **yes (first)**|
| First-pass `all_invariants_passed=True` for all 10?  | no (1.1 was False)   | **yes (10/10)**|
| Snapshot rev files (`_rev2`, `_rev3`, …)?            | 2 (on PI-2026-1.1)   | **0**          |
| Manual `detect_contributors.py` re-run needed?       | yes                  | **no**         |
| Engine re-run after contributor materialization?     | yes                  | **no**         |

Fix is confirmed effective.
