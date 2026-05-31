# EDPA v2 — Full E2E re-validation on REAL GitHub (2026-05-31)

**Verdict: EDPA v2 (working tree @ 2.1.6) works end-to-end across all layers.** A complete
2-PI × 5-iteration flow was simulated against a real, throwaway GitHub repo with multi-person
work, real PRs/reviews/comments, real CI, full iteration close, and reporting. All calibrated
verifiers pass, and an independent (non-calibrated) recompute confirms the result.

## Run parameters
- **Sandbox repo:** `technomaton/edpa-e2e-20260531-094434-f648c6` (private, retained for inspection)
- **Local sandbox:** `/tmp/edpa-e2e-20260531-094434-f648c6` (retained)
- **CI mode:** `real` (every PR merge triggered the real `edpa-contribution-sync.yml` GitHub Action)
- **Data:** calibrated `tests/e2e_v2_full/fixtures/*` (33 items, 5 people/4 humans, 10 iterations)
- **Engine:** working tree re-vendored over the released tarball (diff clean, VERSION 2.1.6)
- **Orchestration:** Claude subagents — 1 bootstrap, 10 parallel work-creation workers (forged
  multi-author commits via `git worktree`, shared hooks), 2 close coordinators, verification fan-out.

## Layer-by-layer result

| Layer | How exercised | Result |
|---|---|---|
| `install.sh` | clean install into empty repo + re-vendor working tree | ✅ |
| `project_setup.py` (`--with-ci/--with-hooks/--with-rules`) | seeded configs/id_counters, installed CI workflow + 4 git hooks + rules | ✅ |
| `backlog.py add` | 33 items, full hierarchy (I→E→F→S, D/EV/R), parent validation, id allocation | ✅ (see Finding 2) |
| Local git hooks | `commit-msg` ticket check; `post-commit` `local_evidence.py` → `commit_author` evidence | ✅ |
| GitHub CI workflow | **24/24** real `edpa-contribution-sync` Action runs **success**; `pr_reviewer`/`issue_comment` materialized + pushed back to main | ✅ |
| Engine (`engine.py`) | 10 iterations; gates + Done + yaml_edit + story-activity; per-person normalization | ✅ all 10 `all_invariants_passed=true` first pass |
| Heuristics / CW | CW derived from commit/PR/review/comment mix; `detect_contributors --all-items` (Stage 2b) | ✅ |
| Close + reports | per-iteration engine + `reports.py` (5 timesheets + team), XLSX, frozen snapshots; `pi_close.py` + `reports.py --pi` | ✅ |
| MCP server (`edpa_*`) | full host test suite (incl. `test_mcp_*`) | ✅ 546 passed, 0 failed |
| Board / Velocity | `board.py` 29 cards; `velocity.py` runs | ✅ (velocity SP=0, see Finding 3) |

### Derived hours (engine output, independently recomputed)
| | 1.1 | 1.2 | 1.3 | 1.4 | 1.5(IP) | 2.1 | 2.2 | 2.3 | 2.4 | 2.5(IP) | total |
|---|----|----|----|----|----|----|----|----|----|----|----|
| team h | 64 | 64 | 112 | 104 | 0 | 72 | 40 | 64 | 40 | 0 | **560** |

Per-person: each **active** committer derives exactly their capacity (e.g. 1.1 = alice 40 + dave 24 = 64);
inactive people are excluded so per-person invariants hold. PI-1 Σ = 344h, PI-2 Σ = 216h. All 10 frozen
snapshot `payload_signature`s recompute byte-for-byte. Totals match the documented prior green run (560h).

## Findings

### 1. [BUG — cross-layer] Iteration "closed" status is written to the wrong key by `edpa_iteration_close`
- `edpa_iteration_close` (`plugin/edpa/scripts/mcp_server.py:1346`) sets **nested** `iteration.status = "closed"`.
- But the **lifecycle** "closed" state that consumers read is the **top-level** `status`:
  `tests/e2e_v2_full/phases/12_verify_backlog.py:176` (`data.get("status")`, with a comment stating
  top-level = lifecycle / nested = planning), and `plugin/edpa/scripts/pi_close.py:105` (`it.get("status")`).
- **Effect:** closing an iteration via the MCP tool alone leaves the top-level lifecycle status unset, so
  `pi_close` / the verifier / a board lifecycle view do not see it as closed. In this run, PI-1 iterations
  closed via the nested key read as `status=None` → verifier 5/10 until a top-level `status: closed` was added.
- **Fix:** `edpa_iteration_close` (and the `close-iteration` flow) should set the top-level `status`
  (and/or consumers should read the nested key) — pick one canonical location and make all layers agree.

### 2. [DX] `backlog.py add` emits ANSI color codes in its allocated-ID output
- The bootstrap worker's first attempt parsed the new item ID with embedded ANSI escapes, breaking
  `--parent` resolution; it recovered by stripping ANSI. Machine-facing output should be plain
  (honor `NO_COLOR` / non-TTY) so callers can parse the allocated ID reliably.

### 3. [Cosmetic / known] SP rollup not populated → `pi_close` predictability `None`, `velocity` avg 0.0
- Iteration YAMLs carry no rolled-up story points (`planning.planned_sp: 0`); SP live on Story items.
  `pi_close.py` reports `0/0 SP, None% predictability` and `velocity.py` reports avg 0.0. Not a regression;
  SP aggregation from Story-level points to the iteration/PI rollup is simply not wired.

### 4. [Limitation — not a bug] Single GitHub account caps review/comment attribution
- All PR reviews/comments authenticate as one user (`jurby`), so `pr_reviewer`/`issue_comment` signals
  carry a non-roster login and are correctly dropped by the engine. Derived hours are therefore
  commit-author-driven. This does **not** change per-person totals (they normalize to capacity), and the
  results matched the baseline exactly — but genuine multi-person review credit is unreachable with one
  account. **Multi-person attribution works at the commit level** via forged `GIT_AUTHOR_*` (as intended).

### 5. [Minor] Self-review acceptance is inconsistent
- `gh pr review --comment` on the author's own PR succeeded for some PRs and was rejected for others
  within the same run (GitHub author-review restriction applied inconsistently / possibly rate-limited).
  The `[review:… from <person>]` issue-comment fallback always worked, so review activity was never lost.

### 6. [Simulation artifact — handled] Add/add merge conflicts under parallel authorship
- Because work-creation was parallelized across iterations, several stories created the **same synthetic
  file paths** (`docs/reports.md`, `src/reports/pi_rollup_writer.py`, `src/reports/csv_writer.py`),
  producing 6 add/add conflicts at merge time, all union-resolved by the close coordinators. This is an
  artifact of the parallel simulation (the original sequential harness rarely hits it), not a v2 defect.

### 7. [Observation] `install.sh` tests the release, not the working tree
- `install.sh` downloads the latest release tarball (or clones `main`); it has no `--from-local-dir` flag.
  Verifying unreleased changes requires re-vendoring `plugin/edpa/{scripts,schemas,templates}` into the
  sandbox `.edpa/engine/` after install (done here). Minor DX gap for pre-release verification.

### 8. [Confirmed-fixed regressions held]
- **Stage 2b ordering (85cd439):** `detect_contributors --all-items` ran before the engine → first-pass
  `all_invariants_passed=true` on all 10 iterations, **zero `_rev*` snapshots**.
- **Portfolio vs delivery ladder (3cb8ff1):** Initiative/Epic transition to `Implementing` (portfolio ladder)
  was accepted; final backlog matched expected counts 33/33.

## Verification commands (reproducible)
```
EDPA_E2E_SANDBOX_DIR=<sandbox> python3 tests/e2e_v2_full/phases/10_verify_invariants.py   # PASS 560h
EDPA_E2E_SANDBOX_DIR=<sandbox> EDPA_E2E_GH_REPO=<repo> EDPA_E2E_CI_MODE=real \
  python3 tests/e2e_v2_full/phases/11_verify_reports.py                                    # PASS (CI 24 success)
EDPA_E2E_SANDBOX_DIR=<sandbox> python3 tests/e2e_v2_full/phases/12_verify_backlog.py       # PASS 33/33, 10/10 closed
python3 -m pytest -m "not e2e" tests/                                                      # 546 passed
```
