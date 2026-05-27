# Phase 11 — Verify Reports + GH State (run log)

Run tag: 20260527-181051-2c56a6a0
Worker: Wave C Unit 12 + coordinator fix-up
Started: 2026-05-27T19:24Z
Finished: 2026-05-27T19:32Z

## Outcome

**PASS** — `verify_reports.py` exit 0. All report artifacts present + GitHub state matches expected for hybrid CI mode.

## Two-phase execution

### First pass (script FAIL / data PASS)

The Wave C agent ran the script with env overrides (`EDPA_E2E_SANDBOX_DIR` + `EDPA_E2E_GH_REPO`) and it correctly resolved the sandbox + repo. All artifact assertions passed, but the script exited 1 because:

```
merged PR count 14 != expected 24
```

Root cause: `EXPECTED_MERGED_PRS = 24` was hard-coded for a full-real-CI run (14 PI-1 + 10 PI-2). This run is **hybrid** (PI-1 real, PI-2 synthetic) so only PI-1's 14 PRs are real. The data is correct; the constant was stale.

### Second pass (PASS — after script fix)

Coordinator made `EXPECTED_MERGED_PRS` CI-mode-aware:

```python
def _expected_merged_prs() -> int:
    mode = os.environ.get("EDPA_E2E_CI_MODE", "hybrid").lower()
    return {"real": 24, "hybrid": 14, "synthetic": 0}.get(mode, 14)

EXPECTED_MERGED_PRS = _expected_merged_prs()
```

Also updated `DEFAULT_SANDBOX` / `DEFAULT_REPO` to fall back to `/tmp/edpa-e2e-current-run-tag` (written by coordinator pre-flight), and refreshed the docstring (no longer claims "12 = 10 + 2 revisions" — post-`85cd439` runs produce exactly 10 base snapshots).

Re-run with `EDPA_E2E_CI_MODE=hybrid` exported → exit 0.

## Verification results

```
Phase 11 — verify reports + GH state
Sandbox : /tmp/edpa-e2e-20260527-181051-2c56a6a0
GH repo : technomaton/edpa-e2e-20260527-181051-2c56a6a0

Iteration artifacts:
Iteration      MDs JSON XLSX  team_h inv_ok issues
PI-2026-1.1      5    0  yes    64.0    yes 0
PI-2026-1.2      5    0  yes    64.0    yes 0
PI-2026-1.3      5    0  yes   112.0    yes 0
PI-2026-1.4      5    0  yes   104.0    yes 0
PI-2026-1.5      5    0  yes     0.0    yes 0
PI-2026-2.1      5    0  yes   144.0    yes 0
PI-2026-2.2      5    0  yes   144.0    yes 0
PI-2026-2.3      5    0  yes   112.0    yes 0
PI-2026-2.4      5    0  yes   144.0    yes 0
PI-2026-2.5      5    0  yes     0.0    yes 0

PI summaries:
  PI-2026-1: ['pi-summary-PI-2026-1.md', 'summary.md']
  PI-2026-2: ['pi-summary-PI-2026-2.md', 'summary.md']

Frozen snapshots: 10

GitHub state:
  merged PRs           : 14   (hybrid mode → only PI-1 creates real PRs)
  CI workflow runs     : {'success': 14}
  repo isArchived      : False

Result: PASS (0 failures)
```

## Artifact counts

| Artifact | Found | Expected (hybrid) |
|---|---|---|
| Per-person timesheets (`.md`) | 50 (5 people × 10 iters) | 50 |
| Team rollup timesheets | 10 | 10 |
| XLSX exports | 10 | 10 |
| `edpa_results.json` per iteration | 10 | 10 |
| Frozen snapshots | **10** | 10 (no `_rev2`/`_rev3` — `85cd439` fix held) |
| PI summary `summary.md` (pi_close.py) | 2 | 2 |
| PI rich `pi-summary-PI-*.md` (reports.py --pi) | 2 | 2 |
| Merged PRs on GH | 14 | 14 (PI-1 only in hybrid) |
| CI workflow runs (all success) | 14 | ≥14 |
| Repo isArchived | False | False (Wave D archives later) |

## Notable observations

- **Zero `_rev2`/`_rev3` snapshots** = commit `85cd439` (mandatory Stage 2b) verified end-to-end. Previous run produced 12 snapshots (10 + 2 PI-2026-1.1 revisions due to discovery-time recompute); this run produces exactly 10.
- **All 14 CI workflow runs are `success`** — no flaky failures, no timeouts.
- **XLSX exports all parse cleanly** with the expected `['Team Summary', 'Item Costs']` sheets.

## Issues encountered

- (resolved) `EXPECTED_MERGED_PRS=24` was stale; replaced with CI-mode-aware function.
- (resolved) `DEFAULT_SANDBOX`/`DEFAULT_REPO` defaulted to previous run's path; now fall back to `/tmp/edpa-e2e-current-run-tag`.
- (resolved) Docstring claimed 12 expected snapshots ("10 + 2 revisions"); updated to reflect post-`85cd439` reality.

## E2E recipe verification

```
$ EDPA_E2E_SANDBOX_DIR=/tmp/edpa-e2e-20260527-181051-2c56a6a0 \
  EDPA_E2E_GH_REPO=technomaton/edpa-e2e-20260527-181051-2c56a6a0 \
  EDPA_E2E_CI_MODE=hybrid \
  python3 tests/e2e_v2_full/phases/11_verify_reports.py
…
Result: PASS (0 failures)
$ echo $?
0
```
