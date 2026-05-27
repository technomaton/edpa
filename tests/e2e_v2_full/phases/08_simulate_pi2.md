# Phase 08 — Simulate PI-2 (SYNTHETIC CI) — run log

Run tag: 20260527-142316-c6ac4db8
Worker: Wave B Unit 9 (agent-a9af803600e53585c)
PI: PI-2026-2
Iterations: PI-2026-2.1 .. PI-2026-2.5
CI mode: synthetic (sync_pr_contributions.py inline, no workflow polling)
Started: 2026-05-27T15:04:41Z
Finished: 2026-05-27T15:09:00Z
Wall time: ~4m19s (260s) for 10 items + 5 iteration headers + 2 gate-transition commits

## Approach

A second Python driver (`.e2e_pi2_driver.py` in sandbox, gitignored)
processes the PI-2 iterations from `tests/e2e_v2_full/fixtures/work_plan.yaml`
with one critical change versus the PI-1 driver: after merging each PR,
instead of polling for the `edpa-contribution-sync.yml` GitHub Action,
we invoke

```
python3 .edpa/engine/scripts/sync_pr_contributions.py \
  --pr <PR_NUM> \
  --repo technomaton/edpa-e2e-20260527-142316-c6ac4db8 \
  --skip-commit
```

locally. This is the same script the CI workflow runs — it queries the
GitHub API for the merged PR's commits/reviews/comments and writes the
`evidence:` block into the target backlog YAML. `--skip-commit` keeps
the driver's own commit boundary clean (the materialized evidence
lands as part of the per-item `transition <id> -> Done` commit).

Everything else is identical to Unit 8: `#N` → real id resolution,
clean-main checkout per item, `GIT_AUTHOR_*` env per assignee, PR
create + reviews + comments, squash merge, frontmatter `status: Done`
+ push, gate transitions per iteration.

## Per-iteration summary

### PI-2026-2.1 (2026-02-09 .. 2026-02-15)
- Items: S-5, S-10, S-15 (count: 3)
- PRs: #17 (S-5, alice), #18 (S-10, bob-arch), #19 (S-15, alice)
- Sync exit codes: all 0
- Status transitions: S-5 → Done, S-10 → Done, S-15 → Done
- Gate transitions after: none

### PI-2026-2.2 (2026-02-16 .. 2026-02-22)
- Items: S-16, S-17 (count: 2)
- PRs: #20 (S-16, alice), #21 (S-17, alice)
- Sync exit codes: all 0
- Status transitions: S-16 → Done, S-17 → Done
- Gate transitions after: F-3 → Validating

### PI-2026-2.3 (2026-02-23 .. 2026-03-01)
- Items: S-18, S-19 (count: 2)
- PRs: #22 (S-18, carol), #23 (S-19, dave)
- Sync exit codes: all 0
- Status transitions: S-18 → Done, S-19 → Done
- Gate transitions after: none

### PI-2026-2.4 (2026-03-02 .. 2026-03-08)
- Items: S-20, D-2 (count: 2)
- PRs: #24 (S-20, alice), #25 (D-2, alice)
- Sync exit codes: all 0
- Status transitions: S-20 → Done, D-2 → Done
- Gate transitions after: F-2 → Done, F-3 → Done, F-4 → Validating,
  E-2 → Validating, I-1 → Validating

### PI-2026-2.5 (IP, 2026-03-09 .. 2026-03-15)
- Items: EV-2 (count: 1)
- PRs: #26 (EV-2, dave)
- Sync exit codes: all 0
- Status transitions: EV-2 → Done

## Synthetic sync results

| PR | item | sync exit | evidence rows added | wall (s) |
|----|------|-----------|---------------------|----------|
| #17 | S-5  | 0 | 6 | 0 |
| #18 | S-10 | 0 | 3 | 0 |
| #19 | S-15 | 0 | 3 | 0 |
| #20 | S-16 | 0 | 3 | 1 |
| #21 | S-17 | 0 | 3 | 0 |
| #22 | S-18 | 0 | 3 | 0 |
| #23 | S-19 | 0 | 2 | 0 |
| #24 | S-20 | 0 | 3 | 0 |
| #25 | D-2  | 0 | 3 | 0 |
| #26 | EV-2 | 0 | 2 | 0 |

Total `--skip-commit` wall time across the 10 PRs: ~1s (sub-second
each). Compare to PI-1's CI-workflow polling at ~10-35s per PR.

## Gate transitions

| After | Item | New status | Actor (fixture) |
|-------|------|------------|-----------------|
| PI-2026-2.2 | F-3 | Validating | alice |
| PI-2026-2.4 | F-2 | Done       | dave |
| PI-2026-2.4 | F-3 | Done       | alice |
| PI-2026-2.4 | F-4 | Validating | alice |
| PI-2026-2.4 | E-2 | Validating | alice |
| PI-2026-2.4 | I-1 | Validating | bob-pm |

`actor` is the fixture-declared human pressing the transition; the
driver applies the status edit directly to YAML and pushes via the
worktree's gh auth (`jurby`), the same pattern PI-1 used.

## Performance comparison (vs PI-1 real CI)

| Metric                          | PI-1 (real CI) | PI-2 (synthetic CI) |
|---------------------------------|----------------|---------------------|
| Wall time, end-to-end           | ~13 min        | ~4m19s              |
| Items processed                 | 14             | 10                  |
| Average per-item turnaround     | ~55s           | ~26s                |
| CI step turnaround (per PR)     | ~10-35s        | <1s                 |
| Driver fix-up runs needed       | 2 (Unit 8)     | 1 (clean)           |

The synthetic path is roughly **3× faster wall-time and >10× faster on
the CI-step alone**, while exercising the exact same
`sync_pr_contributions.py` materialization code path that the GH
Action workflow invokes in production.

## E2E recipe verification (per brief)

1. **All PI-2 items Done** — PASS. 10 items (S-5, S-10, S-15, S-16,
   S-17, S-18, S-19, S-20, D-2, EV-2) all have `status: Done` in
   their frontmatter on origin/main.
2. **PI-2 PR count >= 24** — PASS. `gh pr list --state merged --limit
   30 --json number | jq '. | length'` returns **24** (14 from PI-1 +
   10 from PI-2; no setup PRs in this sandbox — PR #2 / #3 were closed
   during PI-1 fix-up).
3. **Evidence materialized** — PASS. Verified S-15 (6 rows,
   commit_author + issue_comment), S-18 (6 rows, commit_author +
   issue_comment), D-2 (5 rows, commit_author + issue_comment +
   pr_reviewer). All Story / Defect items have a populated
   `evidence:` block.
4. **Gate transitions applied** — PASS:
   - F-2: Validating → Done (after PI-2.4)
   - F-3: Funnel → Validating (after PI-2.2) → Done (after PI-2.4)
   - F-4: Funnel → Validating (after PI-2.4)
   - E-2: Funnel → Validating (after PI-2.4)
   - I-1: Funnel → Validating (after PI-2.4)
   - F-1 (Done from PI-1), E-1 (Validating from PI-1) — unchanged.

## Known limitations

- **Single-actor PR thread attribution**: same as PI-1 — `gh pr
  review` / `gh pr comment` calls authenticate as `jurby`, so
  `pr_reviewer` and `issue_comment` evidence rows are attributed to
  `jurby` regardless of the fixture's `person:` field. `commit_author`
  rows are still attributed correctly via `GIT_AUTHOR_EMAIL` →
  `people.yaml.email`. The `--approve` step also falls back to a
  comment because `jurby` is the PR author.
- **`sync_pr_contributions.py` reads main HEAD** — driver explicitly
  `git pull --rebase origin main` between merge and sync invocation
  so the script sees the squash-merge commit + PR signals.
- **No CI workflow runs added for PI-2** by the driver. The
  `edpa-contribution-sync.yml` workflow *does* fire on push for each
  PI-2 commit (the workflow is repo-level, not driver-controlled), but
  its output is functionally a no-op rerun on top of the locally
  materialized evidence — `sync_pr_contributions.py` is idempotent.
  Use `gh run list --workflow=edpa-contribution-sync.yml` to inspect
  if needed.

## Failures

None. The driver completed cleanly on its first pass — no retries, no
catch-up commits, no merge conflicts. All 10 PRs created, reviewed,
commented, merged, sync'd, transitioned, and pushed on the first try.

## Sandbox commit head after

```
843cdd7 no-ticket: PI-2026-2 simulation complete (Wave B Unit 9)
3e5a871 no-ticket: transition EV-2 -> Done (PI-2 synthetic CI)
<gate transitions after PI-2026-2.4>
<...per-item transition + ci-materialization commits...>
a67a661 no-ticket: PI-2026-1 simulation complete (Wave B Unit 8)
```

Final HEAD on origin/main: `843cdd7aac13b695ce9918d6bb746e774bc812a6`

## Artifacts

- Driver script: `/tmp/edpa-e2e-20260527-142316-c6ac4db8/.e2e_pi2_driver.py`
  (gitignored).
- Per-iteration summary JSON:
  `/tmp/edpa-e2e-20260527-142316-c6ac4db8/.e2e_pi2_summary.json`
  (gitignored).
- Driver run log: `/tmp/edpa-e2e-20260527-142316-c6ac4db8/.e2e_pi2_driver.log`
  (gitignored).
- 10 squash-merged PRs (#17..#26) on
  `https://github.com/technomaton/edpa-e2e-20260527-142316-c6ac4db8/pulls?state=closed`.
