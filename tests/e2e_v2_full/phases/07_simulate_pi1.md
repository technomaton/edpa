# Phase 07 — Simulate PI-1 (REAL CI) — run log

Run tag: 20260527-181051-2c56a6a0
Worker: Wave B Unit 8 (agent on branch fix/e2e-v2-findings)
PI: PI-2026-1
Iterations: PI-2026-1.1 .. PI-2026-1.5
CI mode: real (workflow polling, edpa-contribution-sync.yml)
Started: 2026-05-27T18:24:52Z
Finished: 2026-05-27T18:34:21Z
Wall time: ~9 min 30 sec (single clean pass, no fix-up run needed)

## Approach

A single Python driver (`.e2e_pi1_driver.py` in sandbox, gitignored)
walked the 5 PI-1 iterations in
`tests/e2e_v2_full/fixtures/work_plan.yaml`. For each item it:

1. Resolved `#N` → actual EDPA id via `.e2e_seed_summary.json`
   written by Unit 7 (e.g. `#8`=S-1, `#28`=D-1, `#30`=EV-1).
2. Reset to clean `origin/main`, created `feature/<id>-<slug>` branch.
3. Made 2–3 commits per item using `GIT_AUTHOR_NAME` /
   `GIT_AUTHOR_EMAIL` / `GIT_AUTHOR_DATE` / `GIT_COMMITTER_*` env
   vars derived from `.edpa/config/people.yaml` so the local
   post-commit hook's `local_evidence.py` writes `commit_author`
   evidence with the correct per-assignee `person` field.
4. Pushed branch, created PR via `gh pr create --body-file`, added
   the reviews + comments from the fixture (all as `jurby` per the
   gh-CLI single-user limitation — see Known limitations).
5. `gh pr merge --squash --delete-branch` (with `--admin` fallback
   on conflict — none were hit).
6. Polled `gh run list --workflow=edpa-contribution-sync.yml`
   filtered by `createdAt >= merge_ts` until status=completed.
   No stale-run bug this time.
7. Pulled the resulting evidence commit from main, edited the item's
   frontmatter `status: Done` + `closed_at`, committed
   `no-ticket: transition <id> -> Done` (with
   `EDPA_NO_LOCAL_EVIDENCE=1` to skip the post-commit hook on these
   admin commits) and pushed directly to main.
8. After each iteration, applied `gate_transitions[]` from the
   fixture (parent Feature / Epic frontmatter edits with
   `no-ticket: gate transitions after <iter>`).

## Per-iteration summary

### PI-2026-1.1 (2026-01-05 .. 2026-01-11)
- Items: S-1, S-6, S-11 (count: 3)
- PRs: #1 (S-1, alice), #2 (S-6, dave), #3 (S-11, alice)
- CI workflow runs: 26530487302 (S-1), 26530525367 (S-6),
  26530557141 (S-11) — all success
- Status transitions: S-1 → Done, S-6 → Done, S-11 → Done
- Gate transitions after: none

### PI-2026-1.2 (2026-01-12 .. 2026-01-18)
- Items: S-2, S-7, S-12 (count: 3)
- PRs: #4 (S-2, alice), #5 (S-7, dave), #6 (S-12, alice)
- CI workflow runs: 26530590428 (S-2), 26530621097 (S-7),
  26530660988 (S-12) — all success
- Status transitions: S-2 → Done, S-7 → Done, S-12 → Done
- Gate transitions after: F-1 → Validating

### PI-2026-1.3 (2026-01-19 .. 2026-01-25)
- Items: S-3, S-8, S-13 (count: 3)
- PRs: #7 (S-3, bob-arch), #8 (S-8, alice), #9 (S-13, carol)
- CI workflow runs: 26530698786 (S-3), 26530730678 (S-8),
  26530774962 (S-13) — all success
- Status transitions: S-3 → Done, S-8 → Done, S-13 → Done
- Gate transitions after: none

### PI-2026-1.4 (2026-01-26 .. 2026-02-01)
- Items: S-4, S-9, S-14, D-1 (count: 4)
- PRs: #10 (S-4, carol), #11 (S-9, carol), #12 (S-14, alice),
  #13 (D-1, dave)
- CI workflow runs: 26530813072 (S-4), 26530853018 (S-9),
  26530885587 (S-14), 26530917005 (D-1) — all success
- Status transitions: S-4 → Done, S-9 → Done, S-14 → Done,
  D-1 → Done
- Gate transitions after: F-1 → Done, F-2 → Validating,
  E-1 → Implementing (per 3cb8ff1 portfolio fix — was
  Validating in the pre-fix world, now Implementing because
  Initiative/Epic use the portfolio ladder which omits the
  Validating gate)

### PI-2026-1.5 (IP, 2026-02-02 .. 2026-02-08)
- Items: EV-1 (count: 1)
- PRs: #14 (EV-1, bob-pm)
- CI workflow runs: 26530949034 (EV-1) — success
- Status transitions: EV-1 → Done
- Notes: IP iteration as expected — light, single Event,
  no Story load.

## CI workflow results

Total runs against `edpa-contribution-sync.yml`: 14
Conclusion summary (from `gh run list --workflow=
edpa-contribution-sync.yml --limit 25 --json conclusion --jq
'.[] | .conclusion' | sort | uniq -c`): `14 success`.

| PR | item | assignee | run_id | conclusion |
|----|------|----------|--------|------------|
| #1 | S-1 | alice | 26530487302 | success |
| #2 | S-6 | dave | 26530525367 | success |
| #3 | S-11 | alice | 26530557141 | success |
| #4 | S-2 | alice | 26530590428 | success |
| #5 | S-7 | dave | 26530621097 | success |
| #6 | S-12 | alice | 26530660988 | success |
| #7 | S-3 | bob-arch | 26530698786 | success |
| #8 | S-8 | alice | 26530730678 | success |
| #9 | S-13 | carol | 26530774962 | success |
| #10 | S-4 | carol | 26530813072 | success |
| #11 | S-9 | carol | 26530853018 | success |
| #12 | S-14 | alice | 26530885587 | success |
| #13 | D-1 | dave | 26530917005 | success |
| #14 | EV-1 | bob-pm | 26530949034 | success |

Average per-item wall time end-to-end (branch create → CI
completion → Done commit pushed): ~40 seconds. The polling loop
filtered by `createdAt >= merge_ts` so each item picked up its own
CI run rather than the previous item's stale completed run (the bug
Run 1 of the previous Wave B Unit 8 had to fix in a Run 2 pass).
This unit completed in a single clean pass.

## E2E recipe verification (per brief)

1. **All PI-1 items Done** — PASS. 14 items
   (S-1, S-2, S-3, S-4, S-6, S-7, S-8, S-9, S-11, S-12, S-13,
   S-14, D-1, EV-1) all have `status: Done` in their frontmatter
   on origin/main.
2. **CI workflow ≥ all success** — PASS. 14 success runs
   (matches expected count exactly; no failures).
3. **Evidence materialized with correct attribution** — PASS.
   Verified S-3 (bob-arch), S-4 (carol), D-1 (dave): each has
   `commit_author` evidence rows with the correct assignee
   `person` field. Sample:
   ```
   S-3: commit_author/bob-arch  (×3, one per work commit)
   S-4: commit_author/carol     (×3)
   D-1: commit_author/dave      (×2)
   ```
4. **Gate transitions** — PASS:
   - F-1: Funnel → Validating (after PI-1.2) → Done (after PI-1.4)
   - F-2: Funnel → Validating (after PI-1.4)
   - E-1: Funnel → **Implementing** (after PI-1.4) — confirms
     the 3cb8ff1 portfolio-ladder fix (would have failed schema
     validation pre-fix because Initiative/Epic ladder has no
     Validating step)
   - F-3, F-4, E-2, I-1: still Funnel (their transitions land
     in PI-2, out of scope for this phase)
5. **Sandbox HEAD pushed to origin/main** — PASS. HEAD is
   `d7141ba6570e5e620852f10988568538cd49e5b6`, matches
   `origin/main`.

## Known limitations exercised

- **PR-thread signal attribution → jurby**. Every
  `gh pr review` and `gh pr comment` call authenticates as
  `jurby` (sole gh CLI session). The CI workflow's
  `sync_pr_contributions.py` honestly records the GitHub actor,
  so all `pr_reviewer` and `issue_comment` rows in the materialized
  evidence carry `person: jurby`. Brief explicitly flagged this:
  "evidence materializace ověřuje workflow execution +
  sync_pr_contributions.py shape, ne per-person attribution pro
  PR-thread signály." Test value retained: the workflow itself
  runs, the script's output shape is exercised, the
  materialize-and-commit loop is end-to-end real.
- **commit_author attribution → assignee** (works correctly).
  For every commit we set `GIT_AUTHOR_NAME` / `GIT_AUTHOR_EMAIL`
  / `GIT_COMMITTER_*` from `people.yaml`. The local post-commit
  hook's `local_evidence.py` honors that, so the resulting
  `commit_author` evidence rows carry the actual per-assignee
  `person` field (`alice`, `dave`, `carol`, `bob-arch`,
  `bob-pm`).
- **Driver review.--approve fallback**: GitHub's API refuses to
  let the PR author approve their own PR. Driver logs each failure
  as `review --approve failed (...); fallback to comment` and posts
  a prefixed comment (e.g. `[review:approve from bob-arch] Looks
  good`) via `gh pr comment` so the reviewer's intent is still in
  the PR thread and the CI sync workflow still picks up the
  `issue_comment` signal. Logged for all 14 PRs (every PR had at
  least one such reviewer); no PR ended up with zero comments.
- **chore(evidence) commits in feature branches**: the local
  post-commit hook creates follow-up `chore(evidence): S-X from
  <sha>` commits after each `commit_author`-emitting commit. These
  get squashed into the single PR commit on merge, so they don't
  break anything, and their material reaches main via the squashed
  evidence in the per-item frontmatter. PR #1 commit list visible
  in the PR shows 3 work commits + 3 chore(evidence) commits —
  the squash collapses them into one.
- **MCP tools not used** (out of scope: they target the host
  project `/Users/jurby/projects/edpa`, not the sandbox).
- **Sequencing**: items processed strictly sequentially (one PR
  open at a time). Real teams would parallel-PR, but sequential
  matches the squash-merge-on-merge-train mental model and made
  conflict handling trivial. No merge conflicts encountered.

## Failures

None. Single clean pass, no fix-up run needed.

The previous Wave B Unit 8 (run tag 20260527-142316-c6ac4db8)
needed two passes due to:
- Driver log file accidentally tracked into work tree (fixed by
  Unit 7's `.gitignore` of `.e2e_*`; this run inherited that
  protection).
- Skip heuristic `if fm.get("evidence")` falsely skipped D-1
  because cross-references from S-9's PR body had already created
  `issue_comment` evidence on D-1 (D-1 was mentioned in S-9's PR
  body). This run uses the tightened heuristic
  `if any(e.type == 'commit_author' for e in evidence)` per
  the brief — only skip when the item's OWN work commits have
  been recorded. D-1 processed cleanly as PR #13 on the first
  try.
- Status transitions not surviving iteration reset (the `git
  reset --hard origin/main` at the start of each item wiped
  prior frontmatter edits). This run pushes the
  `transition <id> -> Done` commit to main immediately after
  each item, so it survives subsequent resets.

## Sandbox commit head after

```
d7141ba no-ticket: transition EV-1 -> Done
27bb2b3 chore(ci-materialization): PR#14 signals
cd53044 EV-1: PI-1 retro session record (#14)
bf3eec1 no-ticket: gate transitions after PI-2026-1.4 (F-1->Done, F-2->Validating, E-1->Implementing)
3a2db26 no-ticket: transition D-1 -> Done
55dcdd4 chore(ci-materialization): PR#13 signals
6e7e299 D-1: fix engine on empty iteration with custom calendar (#13)
dcfd841 no-ticket: transition S-14 -> Done
```

Final HEAD on origin/main: `d7141ba6570e5e620852f10988568538cd49e5b6`

## Artifacts

- Driver script:
  `/tmp/edpa-e2e-20260527-181051-2c56a6a0/.e2e_pi1_driver.py`
  (gitignored, kept for Unit 9 in case Wave B re-runs PI-2 with
  the same pattern).
- Per-iteration summary JSON:
  `/tmp/edpa-e2e-20260527-181051-2c56a6a0/.e2e_pi1_summary.json`
  (gitignored).
- Driver run log: `/tmp/edpa-e2e-pi1-driver.log` (outside sandbox
  to avoid the work-tree pollution issue the previous run hit).
- 14 squash-merged PRs on
  `https://github.com/technomaton/edpa-e2e-20260527-181051-2c56a6a0/pulls?state=closed`.
