# Phase 08 — Simulate PI-2 (SYNTHETIC injection) — run log

Run tag: 20260527-181051-2c56a6a0
Worker: Wave B Unit 9 (hybrid-mode fast half)
PI: PI-2026-2
Iterations: PI-2026-2.1 .. PI-2026-2.4 (PI-2026-2.5 IP intentionally empty)
CI mode: synthetic — evidence rows injected directly into frontmatter
Started: 2026-05-27T18:41:59Z
Finished: 2026-05-27T18:43:52Z
Wall time: ~28 s on the second pass (4 items + 5 skips + gate transitions)
           ~4 s for the first pass (driver bug — see Failures below)

## Approach

Instead of creating real GitHub PRs and polling
`edpa-contribution-sync.yml`, the driver
(`.e2e_pi2_driver.py` in the sandbox, gitignored via `.e2e_*`) builds
each item's evidence the local way:

1. Checkout main, branch `feature/<slug>`.
2. Per `commits[]`, write the file change + `git commit` with per-person
   `GIT_AUTHOR_NAME` / `GIT_AUTHOR_EMAIL` / `GIT_AUTHOR_DATE`
   resolved from `.edpa/config/people.yaml`. The
   `local_evidence.py` post-commit hook (vendored in
   `.edpa/engine/scripts/`) fires after every commit, detects the item
   ID in the commit message, resolves the person via email lookup, and
   records a `commit_author` evidence row into the item's
   frontmatter, then emits its own `chore(evidence): <id> from <sha>`
   commit on the branch. Same path PI-1 used.
3. `git checkout main && git merge --squash <branch> && git commit`
   (locally, with assignee env vars). The squash commit touches the
   item's backlog file, so the post-commit hook fires once more and
   credits the assignee as `commit_author` for the squash sha too.
4. Synthetic injection: re-read the item's frontmatter and
   **append** `pr_reviewer` (1 row per fixture `reviewers[]` entry
   with `action: approve`) and `issue_comment` (1 row per fixture
   reviewer + 1 row per `comments[]` entry) directly into the
   `evidence[]` list — the same GH-thread signal set the real CI
   workflow materializes. (The `pr_author` signal was removed in
   2.8.0; the author is credited via `commit_author` from steps 2-3.)
   Each row
   uses the canonical EDPA schema
   `{type, person, weight, ref, at, source: synthetic}` matching
   `sync_pr_contributions.py`. `ref` values use
   `_synthetic_<pr>_<seq>` tokens to keep them dedupe-safe and
   distinct from real PR comment/review IDs.
5. Flip `status: Done`, set `closed_at`, write back, commit
   `no-ticket: synth signals + transition <id> -> Done (synthetic PR#<n>)`
   with `EDPA_NO_LOCAL_EVIDENCE=1` to silence the hook.
6. **Push** to `origin/main` immediately (per-item) so the next item's
   `git reset --hard origin/main` doesn't wipe the new commits.
7. After the last item of each iteration: apply the fixture's
   `gate_transitions[]` (commit + push).

Synthetic PR numbers start at 100 (offset above PI-1's real PR
numbers 1..14) and are recorded only inside evidence `ref` strings.
**No GitHub PRs are created during PI-2.**

## Per-iteration summary

### PI-2026-2.1 (2026-02-09 .. 2026-02-15)
- Items: S-5 (alice, synth PR#100), S-10 (bob-arch, synth PR#101),
  S-15 (alice, synth PR#102) — count: 3
- Status transitions: S-5 → Done, S-10 → Done, S-15 → Done
- Gate transitions after: none

### PI-2026-2.2 (2026-02-16 .. 2026-02-22)
- Items: S-16 (alice, synth PR#103), S-17 (alice, synth PR#104) —
  count: 2
- Status transitions: S-16 → Done, S-17 → Done
- Gate transitions after: F-3 → Validating

### PI-2026-2.3 (2026-02-23 .. 2026-03-01)
- Items: S-18 (carol, synth PR#105), S-19 (dave, synth PR#106) —
  count: 2
- Status transitions: S-18 → Done, S-19 → Done
- Gate transitions after: none

### PI-2026-2.4 (2026-03-02 .. 2026-03-08)
- Items: S-20 (alice, synth PR#107), D-2 (alice, synth PR#108) —
  count: 2
- Status transitions: S-20 → Done, D-2 → Done
- Gate transitions after: F-2 → Done, F-3 → Done, F-4 → Validating,
  E-2 → **Implementing**, I-1 → **Implementing** (portfolio gate
  ladder per 3cb8ff1 — no `Validating` for Initiative/Epic)

### PI-2026-2.5 (IP, 2026-03-09 .. 2026-03-15)
- Items: **none** — EV-2 is an Event item with no `iteration:` field
  in its frontmatter and is out of the synthetic story/defect loop
  per the Wave B Unit 9 brief.
- Status transitions: none
- Gate transitions after: none (fixture has no entries after 2.5)

Total: 9 items → all Done (8 Stories + 1 Defect).

## Synthetic evidence summary

Per-item evidence shape after the run (read straight from
`.edpa/backlog/`):

| Item | status | evidence rows | types present |
|------|--------|---------------|---------------|
| S-5  | Done   | 7  | commit_author, pr_reviewer, issue_comment |
| S-10 | Done   | 8  | commit_author, pr_reviewer, issue_comment |
| S-15 | Done   | 9  | commit_author, pr_reviewer, issue_comment |
| S-16 | Done   | 11 | commit_author, pr_reviewer, issue_comment |
| S-17 | Done   | 8  | commit_author, pr_reviewer, issue_comment |
| S-18 | Done   | 9  | commit_author, pr_reviewer, issue_comment |
| S-19 | Done   | 6  | commit_author, pr_reviewer, issue_comment |
| S-20 | Done   | 8  | commit_author, pr_reviewer, issue_comment |
| D-2  | Done   | 7  | commit_author, pr_reviewer, issue_comment |

The S-16 row count (11) is higher than peers because it inherited
3 stale `issue_comment` rows from PI-1's D-1 PR — D-1's body
explicitly mentions S-16 ("cross-checked with S-9 regression test
(S-16 in fixture)"), so the PI-1 CI workflow picked it up and
attributed jurby's review/comment threads. The skip heuristic
(`if any(e.type == "commit_author") for e in evidence`) correctly
processed S-16 in PI-2 anyway since none of those PI-1 rows are
`commit_author`.

Every item satisfies the brief's recipe row: ≥1 `commit_author`
row + reviewer/comment rows per fixture.

## Gate transitions applied (end-of-run snapshot)

| Item | Status | Notes |
|------|--------|-------|
| F-1  | Done           | from PI-1 (Wave B Unit 8) |
| F-2  | Done           | after PI-2026-2.4 |
| F-3  | Done           | after PI-2026-2.4 (briefly Validating after 2.2) |
| F-4  | Validating     | after PI-2026-2.4 |
| E-1  | Implementing   | from PI-1 (Wave B Unit 8) |
| E-2  | **Implementing** | after PI-2026-2.4 — portfolio ladder (3cb8ff1) |
| I-1  | **Implementing** | after PI-2026-2.4 — portfolio ladder (3cb8ff1) |

E-2 and I-1 transition to `Implementing` (not `Validating`) per the
portfolio gate-ladder fix 3cb8ff1 (`Initiative` / `Epic` types do
not have a `Validating` step). The fixture already encodes this
correctly and the driver applies it as-is.

## Performance comparison

| Metric                          | PI-1 (real CI) | PI-2 (synthetic) |
|---------------------------------|----------------|------------------|
| Wall time per item              | ~55 s (CI poll) | ~2 s             |
| GitHub PRs created              | 14             | 0                |
| `edpa-contribution-sync.yml` runs | 14           | 0 (unchanged)    |
| Evidence types attributed       | commit_author + issue_comment | commit_author + pr_reviewer + issue_comment |

The synthetic path is roughly **25× faster per item** and emits the
same GH-thread signal set the CI workflow does — `pr_reviewer` and
`issue_comment` (the `pr_author` signal was removed in 2.8.0; the
author is credited locally via `commit_author`). The remaining shape
difference vs PI-1 is `pr_reviewer` coverage: PI-1's real PRs carried
few approving reviews, so PI-2's synthetic reviewers add `pr_reviewer`
(weight 2.17) signals that nudge PI-2 contributors' CW shares slightly
higher.

## E2E recipe verification (per brief)

1. **All PI-2 items Done** — PASS. 9 items
   (S-5, S-10, S-15, S-16, S-17, S-18, S-19, S-20, D-2) all show
   `status: Done` + `closed_at` on origin/main.
2. **Evidence shape** — PASS. Each item carries
   ≥1 `commit_author` (from local hook), ≥1 `pr_reviewer`
   (synthetic), ≥1 `issue_comment` (synthetic).
3. **Gate transitions** — PASS. F-3 → Done, F-4 → Validating,
   E-2 → Implementing, I-1 → Implementing. (Brief mentions
   "F-4 → Done" — the **fixture** says `Validating`, and the brief
   says "from fixture", so Validating is correct.)
4. **Sandbox HEAD pushed** — PASS. HEAD =
   `59c02243280124a39ed1ba4c7a1d8d07f16cc1c6`; `git status`
   reports clean working tree, up-to-date with origin/main.
5. **No PI-2 GitHub PRs** — PASS.
   `gh pr list --state all --json number --jq '[.[] | select(.number > 14) | .number]'`
   returns `[]`.
6. **`edpa-contribution-sync.yml` run count unchanged at 14** —
   PASS. `gh run list --workflow=edpa-contribution-sync.yml --json conclusion --jq '[.[] | .conclusion] | length'`
   still returns `14` (PI-1 only). The workflow is triggered
   exclusively by `pull_request: types: [closed]`, and PI-2 creates
   zero pull requests — so no new runs queue.

## Failures

**First-pass driver bug** (recoverable, fully resolved by re-run):

The initial driver pushed only at end-of-iteration. The
per-item `git reset --hard origin/main` then wiped the previous
item's commits before they ever reached origin, so only the LAST
item of each iteration (S-15, S-17, S-19, D-2) survived. The
first 5 items (S-5, S-10, S-16, S-18, S-20) ended up still at
`Funnel` status with no evidence.

Fixed by moving the `git push origin main` from
end-of-iteration to immediately after each item's transition commit.
The skip heuristic (`if any(e.type == "commit_author") for e in
evidence`) made the second pass idempotent: items already at Done
with `commit_author` evidence are short-circuited; items missing
`commit_author` are re-processed and pushed.

**Cosmetic side-effect of the recovery**: the first-pass
end-of-iter-2.4 gate-transition commit landed before the second
pass, then the second pass re-applied F-3 → Validating after iter
2.2 (because that's what the fixture says) and then F-3 → Done
again after iter 2.4. The end state is correct (F-3 → Done) but
F-3's git log shows a Done→Validating→Done flutter mid-history.
Not a correctness issue — gate ladder is informational metadata,
not a state machine the engine reads sequentially.

## Sandbox HEAD after the run

```
59c0224 no-ticket: gate transitions after PI-2026-2.4 (F-3->Done)
adfde0c no-ticket: synth signals + transition S-20 -> Done (synthetic PR#107)
1c2eb6b no-ticket: gate transitions after PI-2026-2.2 (F-3->Validating)
4a4ee0a no-ticket: synth signals + transition S-16 -> Done (synthetic PR#103)
db89b8c no-ticket: synth signals + transition S-10 -> Done (synthetic PR#101)
6c0bce8 no-ticket: synth signals + transition S-5 -> Done (synthetic PR#100)
ebbd734 no-ticket: gate transitions after PI-2026-2.4 (F-2->Done, F-3->Done, F-4->Validating, E-2->Implementing, I-1->Implementing)
99c7e2f no-ticket: synth signals + transition D-2 -> Done (synthetic PR#108)
2577681 chore(evidence): D-2,PI-2 from e31f6d5
e31f6d5 D-2: fix XLSX export truncation of long titles (#108)
d9d929e no-ticket: synth signals + transition S-19 -> Done (synthetic PR#106)
…
d7141ba no-ticket: transition EV-1 -> Done   <-- PI-1 end (Wave B Unit 8)
```

Final HEAD on origin/main:
`59c02243280124a39ed1ba4c7a1d8d07f16cc1c6`

## Artifacts

- Driver script:
  `/tmp/edpa-e2e-20260527-181051-2c56a6a0/.e2e_pi2_driver.py`
  (gitignored).
- Driver run log:
  `/tmp/edpa-e2e-20260527-181051-2c56a6a0/.e2e_pi2_driver.log`
  (gitignored, both passes appended).
- Per-iteration summary JSON:
  `/tmp/edpa-e2e-20260527-181051-2c56a6a0/.e2e_pi2_summary.json`
  (gitignored, captures the second pass only — the pass that
  actually completed without wiping).
- **Zero** GitHub PRs created on
  `https://github.com/technomaton/edpa-e2e-20260527-181051-2c56a6a0/`
  for PI-2.
- Sandbox HEAD pushed to origin/main —
  `59c02243280124a39ed1ba4c7a1d8d07f16cc1c6`.
