# Phase 10 — Verify Invariants (run log)

Run tag: 20260527-181051-2c56a6a0
Worker: Wave C Unit 11 + coordinator fix-up
Started: 2026-05-27T19:24Z
Finished: 2026-05-27T19:32Z

## Outcome

**PASS** — `verify_invariants.py` exit 0. All 10 iterations integrity-clean.

## Two-phase execution

### First pass (FAIL — stale script constant)

The Wave C agent ran the script as-shipped and it exited 1 with:

```
AssertionError: Expected 10 results files, got 0
```

Root cause: `10_verify_invariants.py:32` hard-coded `SANDBOX = Path('/tmp/edpa-e2e-20260527-142316-c6ac4db8')` — the **previous** run's sandbox, which no longer exists. The script used an absolute path so `cd` had no effect.

The agent reported the issue and performed a manual replay of every assertion against the current sandbox — all checks held.

### Second pass (PASS — after script fix)

Coordinator replaced the hard-coded constant with an env-driven resolver:

```python
def _resolve_sandbox() -> Path:
    explicit = os.environ.get('EDPA_E2E_SANDBOX_DIR')
    if explicit:
        return Path(explicit)
    tag_file = Path('/tmp/edpa-e2e-current-run-tag')
    if tag_file.exists():
        tag = tag_file.read_text().strip()
        if tag:
            return Path(f'/tmp/edpa-e2e-{tag}')
    raise SystemExit('ERROR: cannot resolve sandbox path. ...')

SANDBOX = _resolve_sandbox()
```

Re-run with `EDPA_E2E_SANDBOX_DIR=/tmp/edpa-e2e-20260527-181051-2c56a6a0` exported → exit 0.

## Verification results

```
[1/4] Iteration metadata (type) … 10 iterations loaded (8 Iteration + 2 IP)

[2/4] Verifying edpa_results.json … 10/10 OK
  PI-2026-1.1: team_total=64.0h, people=5, per-person invariant_ok=all
  PI-2026-1.2: team_total=64.0h
  PI-2026-1.3: team_total=112.0h
  PI-2026-1.4: team_total=104.0h
  PI-2026-1.5 (IP): team_total=0h
  PI-2026-2.1: team_total=144.0h
  PI-2026-2.2: team_total=144.0h
  PI-2026-2.3: team_total=112.0h
  PI-2026-2.4: team_total=144.0h
  PI-2026-2.5 (IP): team_total=0h

[3/4] Verifying snapshots … 10/10 OK (frozen=True, signature recomputed match)

[4/4] backlog.py status … exit 0, 88 SP total / 88 Done

Aggregate: PI-1=344h, PI-2=544h, total=888h
```

## Notable observations

- **`all_invariants_passed=true` on FIRST engine pass** (no `_rev2` snapshots) — confirms commit `85cd439` fix (mandatory Stage 2b `detect_contributors.py --all-items`) is working as designed.
- **PI-2 hours higher than the earlier real-CI run**. This is Wave B Unit 9 fixture-coverage variance: synthetic mode adds `pr_reviewer` + `issue_comment` signals that PI-1's real PRs largely lacked (documented in `08_simulate_pi2.md`). Both engine outputs are within capacity and invariant-clean — not a regression. (The aggregate hour figures captured in this log predate the 2.8.0 3-signal model — the `pr_author` weight 3.4 is gone — so a fresh run lands lower; this phase is gated by the invariant checks, not the hour totals.)
- **Per-person capacity invariant holds for every active person** (engine clamps `total_derived ≤ capacity` within tolerance).
- **Snapshot signatures recompute byte-identical** — engine is deterministic for these inputs.

## Issues encountered

- (resolved) Hard-coded SANDBOX path in script line 32 → replaced with env-driven `_resolve_sandbox()`.

## Artifacts

- 10 × `.edpa/reports/iteration-PI-2026-*/edpa_results.json` — all `all_invariants_passed=true`
- 10 × `.edpa/snapshots/PI-2026-*.json` — all frozen, signatures verified

## E2E recipe verification

```
$ EDPA_E2E_SANDBOX_DIR=/tmp/edpa-e2e-20260527-181051-2c56a6a0 \
  python3 tests/e2e_v2_full/phases/10_verify_invariants.py
…
VERDICT: PASS — 10 iterations, 10 snapshots, PI-1=344.0h PI-2=544.0h total=888.0h
$ echo $?
0
```
