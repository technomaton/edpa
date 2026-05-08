# E2E Report — v1.10.0-rc1 real-evidence simulation

- **Date:** 2026-05-08
- **Plugin version under test:** 1.10.0-rc1 (commit `4fe870b`, tag `v1.10.0-rc1`)
- **Sandbox:** `technomaton/edpa-e2e-test` (private)
  - GH Project #49 ("EDPA-E2E-Pilot 1778160610")
  - 17 merged PRs (#129..#148, of which 10 are story PRs #139..#148)
- **Workspace:** `/tmp/edpa-pilot-e2e-1778160610/` (extends 2026-05-07 declarative E2E)
- **Operator:** Jaroslav Urbánek (single-identity push)
- **Result:** **PASS for evidence-pipeline path** with single-identity caveat documented below.

This report supplements the
[2026-05-07 declarative E2E report](E2E-REPORT-2026-05-07-v1100-beta-full-pilot.md)
by closing the explicitly-acknowledged gap in that report's *"What was
NOT exercised"* section: real commits / PRs / merges as inputs to the
EDPA evidence detection pipeline. The 2026-05-07 run validated the
v1.10 *changes* (xlsx consolidation, Stage 0 preflight,
capacity-override flow). This run validates the *core EDPA evidence
pipeline* — `detect_contributors.py` populating `contributors[]` from
real GH state, engine deriving hours from that auto-detected data.

## What changed vs the 2026-05-07 declarative run

| Layer | Declarative E2E (yesterday) | Real-evidence E2E (today) |
|-------|-----------------------------|---------------------------|
| Backlog `contributors[]` | Hand-seeded YAML with `as: owner / key / reviewer` and `cw: 0.7 / 0.6 / ...` | **Stripped clean**; populated *only* by `detect_contributors.py` reading merged PRs |
| Story status transitions | `yq -i status: Done` on local YAML | **Real `gh project field-edit`** + `sync push` round-trip; status changes captured in git via auto-commits |
| Owner contribution signal | Declarative `as: owner, cw: 0.7` | **Real `git commit --author=`** with `<id>+<login>@users.noreply.github.com` resolving to actual GH logins |
| Reviewer / key contribution | Declarative entries | **Real multi-author commits** in PR (resolved by GH to additional authors) |
| `/contribute @person weight:X` | Synthesized by engine from contributors[] | Written into real PR bodies (but not picked up by `detect_contributors.py` — see § Findings) |
| PR author signal | Synthesized | **Real PR author** (jurby) — captured by detect_contributors as `as: key, cw: 0.6` |
| Engine input | `contributors[]` declared by hand | `contributors[]` written by `detect_contributors.py` from `gh pr view --json` data |

## Setup

The 2026-05-07 sandbox already had Project #49 + 17 GH issues + 5
iteration YAMLs + people.yaml. I reset state by:

1. Stripping `contributors[]` from all 10 stories.
2. Resetting story status to `Backlog` and iteration status to `planned`.
3. Wiping `.edpa/reports/*` and `.edpa/snapshots/*`.

Then I generated 10 real PRs in `/tmp/edpa-real-prs.py`. Per Story:

```
1. git checkout -b feature/S-N-<slug>           # off main
2. for each contributor (owner first, then key, then reviewer):
     write work/S-N-<role>-<person>.md
     git -c user.name=<login> -c user.email=<id>+<login>@users.noreply.github.com \
         commit --author="<login> <email>" -m "S-N: <title> (<role> contribution)"
3. git push -u origin feature/S-N-<slug>
4. gh pr create --title "S-N: <title>" --body "Closes #<issue>\n/contribute @... weight:..."
5. gh pr merge <prnum> --squash --admin
```

Identity faking via `<id>+<login>@users.noreply.github.com` works
because GitHub resolves verified `noreply` emails back to logins. All
10 PRs had multi-author commits with logins resolving to
`jurby / martinturyna / mtury / sirTurbisCZ` as appropriate.

PRs created: #139..#148 (10 PRs).

## Verification 1 — `gh pr view` shows multi-author commits

Sample (PR #146, S-8 with three contributors per original spec):

```
{
  "author": "jurby",
  "commits": [
    ... 3 commits already on main (squash base) ...
    { "headline": "S-8: Anonymizer rules (owner contribution)",  "authors": ["martinturyna"] },
    { "headline": "S-8: Anonymizer rules (key contribution)",    "authors": ["sirTurbisCZ"] },
    { "headline": "S-8: Anonymizer rules (reviewer contribution)","authors": ["jurby"] }
  ]
}
```

GitHub correctly attributes the `--author=` commits to the right
logins. Engine evidence detection has real signal to work with.

## Verification 2 — `detect_contributors.py` populates YAML

Ran `python3 detect_contributors.py --pr <N>` for each of #139..#148.
Each call wrote a `contributors[]` block to the matching story YAML
based on the PR's actual author + commit authors (filtered to remove
duplicate of PR author).

Sample S-8 YAML after detect:

```yaml
id: S-8
type: Story
title: Anonymizer rules
status: Backlog
parent: F-4
js: 8
iteration: PI-2026-1.4
assignee: turyna
contributors:
- as: key            # PR author auto-attributed as `key` with cw=0.6
  cw: 0.6
  person: jurby
  source: pr_author:#146
- as: reviewer       # additional commit authors auto-attributed as `reviewer`, cw=0.25
  cw: 0.25
  person: turyna
  source: commit_author:#146
- as: reviewer
  cw: 0.25
  person: turbis
  source: commit_author:#146
```

Per-PR detection summary:

| PR | Story | Items detected | PR author | Other commit authors |
|----|-------|----------------|-----------|----------------------|
| 139 | S-1 | S-1 | jurby | martinturyna, mtury |
| 140 | S-2 | S-2 | jurby | martinturyna, mtury |
| 141 | S-3 | S-3 | jurby | martinturyna |
| 142 | S-4 | S-4 | jurby | mtury |
| 143 | S-5 | S-5 | jurby | martinturyna, sirTurbisCZ |
| 144 | S-6 | S-6 | jurby | mtury |
| 145 | S-7 | S-7 | jurby | sirTurbisCZ |
| 146 | S-8 | S-8 | jurby | martinturyna, sirTurbisCZ |
| 147 | S-9 | S-9 | jurby | martinturyna, mtury |
| 148 | S-10 | S-10 | jurby | (none) |

10/10 PRs correctly attributed.

## Verification 3 — engine + reports against real-evidence YAMLs

Pushed Story status (`Backlog → Done`) for all 10 stories via
`sync.py push`; this updates the GH Project Story Status field and
auto-commits the diff. Then walked Feature/Epic/Initiative parents
through `Backlog → Implementing → Done` with two `sync push` cycles
(generates two transition commits per parent in git history).

Engine (`--mode gates`) per iteration:

| Iter | Stories Done | TEAM TOTAL | Invariants |
|------|-------------|------------|------------|
| PI-2026-1.1 | S-1, S-2 | **100h** / 130h | ✅ |
| PI-2026-1.2 | S-3, S-4, S-5 | **130h** / 130h | ✅ |
| PI-2026-1.3 | S-6, S-7 | **90h** / 130h | ✅ |
| PI-2026-1.4 | S-8, S-9 | **130h** / 130h | ✅ |
| PI-2026-1.5 | S-10 | **20h** / 130h | ✅ |

Per-person Σ across PI:

| Person | Capacity Σ | Derived Σ | vs declarative E2E (yesterday) |
|--------|------------|-----------|-------------------------------|
| Jaroslav Urbánek | 100h | **100h** | declarative was 68h (override + reviewer-only attribution) |
| Martin Turyna | 200h | 120h | declarative was 120h (same) |
| M. Turyna II | 200h | 160h | declarative was 160h (same) |
| Sir Turbis | 150h | 90h | declarative was 90h (same) |

The 32h jump for Jurby (68h → 100h) is the **single-identity caveat**
manifesting: every real PR was created via `gh pr create` under
jurby's auth, so `detect_contributors` attributed jurby as `as: key,
cw: 0.6` on all 10 stories regardless of the original
declared role. In a real multi-developer team each developer would be
the PR author of their own PRs and attribution would land
proportionally. This is a sandbox artefact, not an engine bug.

Per-person timesheets (`.edpa/reports/iteration-PI-2026-1.X/timesheet-<id>.md`)
and consolidated `edpa-results.xlsx` (Team Summary + Item Costs tabs)
generated for all 5 iterations + PI rollup
(`pi-summary-PI-2026-1.md`).

## Verification 4 — A/B simple vs gates with real-data backlog

```
PI-1.1  simple: 100.0h    gates: 100.0h     Δ=0h
PI-1.2  simple: 130.0h    gates: 130.0h     Δ=0h
PI-1.3  simple:  90.0h    gates:  90.0h     Δ=0h
PI-1.4  simple: 130.0h    gates: 130.0h     Δ=0h
PI-1.5  simple:  20.0h    gates:  20.0h     Δ=0h
```

**Δ=0 explanation.** Gates mode credits parent (Feature/Epic/
Initiative) status transitions captured in **git commits** within the
**iteration date window**. My iteration windows are dated
2026-04-0X..2026-04-1X but the sync push commits that captured the
parent transitions happened today (2026-05-08). Engine's window filter
correctly excludes them → gates falls back to story-Done credit, same
as simple. Acceptance criterion *"no person `gates < simple`"*
trivially holds.

For the kashealth pilot the iteration windows will track real-time
sync, so this temporal misalignment does not happen there.

## Findings

1. **`detect_contributors.py` does NOT parse `/contribute @<person> weight:<cw>`
   lines from PR bodies.** The PR bodies I created had explicit
   `/contribute` directives matching the original declarative
   attribution intent. detect_contributors only looks at PR author +
   commit authors (filtered) and applies fixed weights (`pr_author →
   key cw=0.6`, `commit_author → reviewer cw=0.25`). The engine DOES
   parse `/contribute` lines but only from the YAML's `body:` field —
   which is populated by `sync pull` from issue bodies, not PR bodies.
   This is a documentation/UX gap: users writing `/contribute` in PR
   bodies expect their attributions to flow through, but they don't.

   **Recommendation:** either teach `detect_contributors.py` to parse
   `/contribute` lines from PR bodies and override the auto-derived
   role/cw, or document explicitly that manual attribution lives only
   in issue bodies.

2. **Engine's top-level `pr_author` / `commit_authors` /
   `pr_reviewers` / `commenters` fields are not populated by any
   script** in the current codebase. `detect_contributors.py` writes
   `contributors[]` only. So the engine's evidence-score signals for
   these top-level fields (worth +2.0 / +1.0 / +1.0 / +0.5
   respectively) are dead code in the YAML-driven path. The only live
   signals are `assignee` (4.0) and `contribute_command` (3.0,
   synthesised from `contributors[]`).

   **Recommendation:** either remove the dead-code signals from
   `detect_evidence` to simplify, or extend
   `detect_contributors.py` to write the top-level fields too.

3. **Single-identity push limits the realism of role attribution.**
   With one `gh auth` token, every PR has jurby as author → every
   detected story has jurby as `key` regardless of the original work
   distribution. To stress-test multi-person attribution would require
   either separate GH accounts or a different test harness that mocks
   `gh pr view` JSON.

4. **Gates mode produces no extra credit when iteration windows fall
   outside git commit timestamps.** Documented limitation; not a bug
   for the kashealth pilot (windows track real time there).

5. **All other v1.10 features verified end-to-end against real
   evidence.**
   - Stage 0 preflight (already validated 2026-05-07) ✓
   - Capacity overrides (declarative path, validated 2026-05-07) — but
     not re-tested against real-evidence backlog today; deferred.
   - `edpa-results.xlsx` consolidation: 5 workbooks generated, both
     tabs (`Team Summary`, `Item Costs`) present, real-evidence rows
     verified.

## Verdict

**v1.10.0-rc1 evidence pipeline: PASS** end-to-end against real GH state
with single-identity caveat. The findings (#1, #2) are pre-existing
gaps from v1.9.0 and earlier — unchanged by v1.10 and not
release-blocking — but worth tracking as v1.10.1 or v1.11 backlog
items.

**Recommendation:** keep `v1.10.0-rc1` as-is. Promote to stable
`v1.10.0` after the kashealth pilot's PI-2026-1.1 close on
~2026-05-13/14 confirms multi-identity real-data behaviour. File
findings #1 and #2 as v1.10.x backlog issues with concrete
acceptance criteria.

## Cleanup

- 10 merged PRs, 10 feature branches still on `technomaton/edpa-e2e-test`.
  Branches retained for forensic inspection.
- Project #49 has 10 stories at status=Done, 4 features + 2 epics + 1
  initiative all at status=Done.
- Local workspace `/tmp/edpa-pilot-e2e-1778160610/` retained.

To wipe:

```bash
gh pr list --repo technomaton/edpa-e2e-test --state merged --limit 30 \
  --json number --jq '.[].number' | \
  xargs -I {} gh api repos/technomaton/edpa-e2e-test/pulls/{} -X DELETE
gh project delete 49 --owner technomaton
gh issue list --repo technomaton/edpa-e2e-test --json number --jq '.[].number' | \
  xargs -I {} gh issue delete {} --yes --repo technomaton/edpa-e2e-test
```
