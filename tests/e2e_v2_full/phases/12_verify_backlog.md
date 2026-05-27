# Phase 12 — Verify Backlog + Iteration State (run log)

Run tag: 20260527-181051-2c56a6a0
Worker: Wave C Unit 13 + coordinator fix-up
Started: 2026-05-27T19:24Z
Finished: 2026-05-27T19:32Z

## Outcome

**PASS** — `verify_backlog.py` exit 0. Backlog end-state matches the post-`3cb8ff1` portfolio gate ladder; all 10 iterations are at lifecycle `status=closed`; board snapshot built successfully.

## Two-phase execution

### First pass (script FAIL / data PASS)

The Wave C agent ran the script as-shipped and it exited 1 with two distinct issues:

1. **Stale `EXPECTED_COUNTS`** (lines 55-64) — predated commit `3cb8ff1`. The constants expected `Initiative`/`Epic` at status `Validating`, but the post-`3cb8ff1` portfolio gate ladder transitions them through `Implementing` instead.
2. **Wrong YAML key for iteration status** (line 157) — read `data["iteration"]["status"]` which is the planning state (always `planned`), instead of the root `data["status"]` which is the lifecycle state (becomes `closed` at iteration close).

The sandbox itself was already in the correct state:
- I-1, E-1, E-2 → `Implementing` (portfolio ladder per `3cb8ff1`)
- F-1, F-2, F-3 → `Done`; F-4 → `Validating`
- All 10 iterations at lifecycle `status=closed`

### Second pass (PASS — after script fix)

Coordinator applied three edits to `12_verify_backlog.py`:

1. Updated `EXPECTED_COUNTS` to the post-`3cb8ff1` end state:
   ```python
   EXPECTED_COUNTS = {
       ("Initiative", "Implementing"): 1,
       ("Epic", "Implementing"): 2,
       ("Feature", "Done"): 3,
       ("Feature", "Validating"): 1,
       ("Story", "Done"): 20,
       ("Defect", "Done"): 2,
       ("Event", "Done"): 1,
       ("Event", "Funnel"): 1,  # EV-2 never reaches Done
       ("Risk", "Funnel"): 2,
   }
   ```
2. Fixed iteration status lookup to read the root `data["status"]` key.
3. Added a doc note about the dual-status schema (`iteration.status` = planning, `status` = lifecycle).

Re-run → exit 0.

## Verification results

```
Sandbox: /private/tmp/edpa-e2e-20260527-181051-2c56a6a0
RUN_TAG: 20260527-181051-2c56a6a0

=== 1. Backlog item counts ===
Backlog items found: 33 (expected 33)

Type         Status         Found  Expected  Verdict
------------ -------------- -----  --------  -------
Defect       Done               2         2  OK
Epic         Implementing       2         2  OK
Event        Done               1         1  OK
Event        Funnel             1         1  OK
Feature      Done               3         3  OK
Feature      Validating         1         1  OK
Initiative   Implementing       1         1  OK
Risk         Funnel             2         2  OK
Story        Done              20        20  OK

Total items: 33 (expected 33) — OK

=== 2. backlog.py validate ===
  Items: 29, Stories: 20, Errors: 0, Warnings: 35
  No errors. Backlog is valid (with warnings).
  (warnings = fixture-driven non-Fibonacci WSJF values; expected)
  exit code: 0

=== 3. Iteration state ===
  PI-2026-1.1.yaml: status=closed
  …
  PI-2026-2.5.yaml: status=closed
  Iterations closed: 10/10 (expected 10/10) — OK

=== 3b. validate_iterations.py ===
  0 error(s), 2 warning(s) (missing PI metadata YAMLs — derived from iterations, expected)
  exit code: 0

=== 5. Board snapshot ===
  Output: /tmp/edpa-e2e-board-20260527-181051-2c56a6a0.html
  Size: 40248 bytes
  Item cards rendered: 29
  Distinct iterations referenced: 8

=== Verdict ===
  counts: PASS
  iterations: PASS
  board: PASS
  validate (soft): exit=0
  validate_iterations (soft): exit=0
Phase 12: PASS
```

## Notable observations — `3cb8ff1` portfolio fix verified end-to-end

- **`backlog.py validate` now reports 0 errors** (previously had 3 errors). The portfolio items at `Implementing` are accepted by `SAFe status values` check, whereas the pre-`3cb8ff1` `Validating` state failed validation.
- **All three portfolio items** (I-1, E-1, E-2) are at `Implementing`, none at the disallowed `Validating` rung.
- **Delivery items** still use the full ladder: F-1/F-2/F-3 at `Done`, F-4 at `Validating`.

## Issues encountered

- (resolved) `EXPECTED_COUNTS` predated `3cb8ff1` → updated to match post-fix end state.
- (resolved) `check_iterations()` read wrong YAML key → switched to root `data["status"]`.
- (resolved) `RUN_TAG`/`SANDBOX` defaults pointed at previous run → fall back to `/tmp/edpa-e2e-current-run-tag` file.

## Artifacts

- `/tmp/edpa-e2e-board-20260527-181051-2c56a6a0.html` — 29-card kanban (Initiative/Epic/Feature/Story/Defect; Events + Risks excluded by design)
- 33 backlog `.md` files (`.edpa/backlog/`)
- 10 iteration YAMLs (`.edpa/iterations/PI-2026-*.yaml`)

## E2E recipe verification

```
$ EDPA_E2E_SANDBOX_DIR=/tmp/edpa-e2e-20260527-181051-2c56a6a0 \
  EDPA_E2E_RUN_TAG=20260527-181051-2c56a6a0 \
  python3 tests/e2e_v2_full/phases/12_verify_backlog.py
…
Phase 12: PASS
$ echo $?
0
```
