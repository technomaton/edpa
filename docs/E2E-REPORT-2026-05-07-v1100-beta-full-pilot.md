# E2E Report — v1.10.0-beta full pilot simulation

- **Date:** 2026-05-07
- **Plugin version under test:** 1.10.0-beta (commit `4266852`, tag `v1.10.0-beta`)
- **Sandbox:** `technomaton/edpa-e2e-test` (private), GH Project #49 ("EDPA-E2E-Pilot 1778160610")
- **Workspace:** `/tmp/edpa-pilot-e2e-1778160610/` (4 commits in local repo, mirrored to sandbox)
- **Operator:** Jaroslav Urbánek (with Claude Code Opus 4.7 as runner)
- **Result:** **PASS** — all 5 iteration closes + override flows + PI rollup produced expected artifacts; invariants OK on every run.

This report supersedes the partial coverage of the automated suite
(`pytest -m e2e`, 32/32 PASS) by exercising the full pilot lifecycle —
backlog hierarchy, status transitions, capacity overrides via the new
v1.10 skill chain, all reports artifacts, PI aggregation.

## Coverage matrix

| Behavior | Automated suite | This run | Verdict |
|----------|-----------------|----------|---------|
| Stage 0 preflight (gh scopes, org, Issue Types, git config, people.yaml ↔ org members) | indirect | direct (`--check-only` against real org, 7/7 PASS) | ✅ |
| GH Project create + 21 fields + Iteration field with 5 options | partial (1 iteration) | full (5 iteration options) | ✅ |
| `create_project_views.py` (5 GH UI views) | not exercised | **not exercised** — requires Playwright + interactive login (known gap) | ⚠ |
| Hierarchy 4 levels (Initiative → Epic → Feature → Story) with sub-issue links | partial (1+1+0+2) | full (1+2+4+10 = 17 GH issues, 16 sub-issue links) | ✅ |
| Strict schema validation (`validate_syntax.py --strict`) | unit | direct (`All files valid`) | ✅ |
| Sync push → 17 issues created in GH | yes | yes (assignees, iteration field, JS, status all set) | ✅ |
| Engine `gates` mode per iteration | partial | 5/5 iterations, all invariants PASS | ✅ |
| Capacity override mid-iteration (`--prep-only` semantics via `capacity_override.py --add`) | none (only unit tests) | direct (jurby vacation -12h on PI-1.3) | ✅ |
| Capacity override delta (`+N` overtime) | none | direct (turyna +4h on PI-1.5 IP) | ✅ |
| Engine respects iteration-level `people:` overrides | unit (35 tests) | direct (8h capacity → 8h derived for jurby; 44h for turyna) | ✅ |
| Reports skill — per-person `timesheet-<id>.md` | none in real suite | 4 timesheets × 5 iterations = 20 files | ✅ |
| Reports skill — `timesheet-team.md` | none | 5 team rollups | ✅ |
| Engine `edpa-results.xlsx` consolidated workbook (Team Summary + Item Costs tabs) | unit | 5 workbooks, both tabs present, headers correct | ✅ |
| Frozen snapshot per iteration | partial | 5 iteration snapshots + 1 PI snapshot + 3 revs (re-runs) | ✅ |
| A/B simple vs gates | none | 0h delta, no person `gates < simple` | ✅ |
| PI close — engine on PI-level | none | runs (TEAM TOTAL 0h expected — stories live on iteration files) | ✅ |
| PI close — `reports.py --pi` | none | aggregates 5 iterations into `pi-summary-PI-2026-1.md` | ✅ |
| Auto-commit (setup state, sync push, override) | sync only | yes — 4 commits in workspace git log | ✅ |

## Setup phase artifacts

```
GH Project #49: https://github.com/orgs/technomaton/projects/49
  Title: "EDPA-E2E-Pilot 1778160610"
  Fields: 21 (default 11 + EDPA custom 10)
  Custom: Job Size, BV, TC, RR, WSJF, Team, Initiative/Epic/Feature/Story Status, Iteration
  Iteration options: PI-2026-1.1, PI-2026-1.2, PI-2026-1.3, PI-2026-1.4, PI-2026-1.5
GH Issues: 17 total
  Initiative: 1 (I-1)
  Epic:       2 (E-1, E-2)
  Feature:    4 (F-1..F-4)
  Story:     10 (S-1..S-10)
Sub-issue links: 16 (each non-Initiative item linked to its parent)
```

## Stage 0 preflight (against live org)

```
[1] Toolchain                                       ✓ all green
[2] GitHub CLI authentication                       ✓ jurby + 4 scopes
[3] Org access (technomaton)                        ✓ 5 members visible
[4] Target repo (technomaton/edpa-e2e-test)         ✓ default=main
[5] Org-level Issue Types                           ✓ 6/6 present
[6] Local git config                                ✓ user.name + email set
[7] people.yaml github logins vs technomaton org    ✓ all 4 logins are members
✓ ready — every check passed
```

## Per-iteration close summary

| Iter | Stories Done | Override applied | TEAM TOTAL | Invariants |
|------|--------------|------------------|------------|-----------|
| PI-2026-1.1 | S-1, S-2 | none | 80h / 130h baseline | ✅ |
| PI-2026-1.2 | S-3, S-4, S-5 | none | 130h / 130h | ✅ |
| PI-2026-1.3 | S-6, S-7 | jurby vacation -12h (`--add`) | 78h / **118h** (vs 130 baseline) | ✅ |
| PI-2026-1.4 | S-8, S-9 | none | 130h / 130h | ✅ |
| PI-2026-1.5 (IP) | S-10 | turyna +4h overtime (`+4` delta) | 20h / **134h** (vs 130 baseline) | ✅ |

**Override verification.** On PI-2026-1.3 the override `jurby:
capacity_per_iteration: 8.0` is reflected in:
- Engine output: `Jaroslav Urbánek    Arch    8.0h    8.0h    1    OK`
- timesheet-jurby.md: `8.0h`
- frozen snapshot retains `capacity_baseline` + `capacity_override.note`

On PI-2026-1.5 the override `turyna: capacity_per_iteration: 44.0` is
reflected in:
- Engine output: `Martin Turyna    Dev    44.0h    0h    0    OK`
  (turyna had no contribution on S-10 — derived 0h, capacity 44h, invariant
  still OK because no over-allocation)

## PI-2026-1 rollup

`pi-summary-PI-2026-1.md` aggregates all 5 iterations:

| Person | Capacity Σ | Derived Σ | Iterations |
|--------|------------|-----------|------------|
| Jaroslav Urbánek | 88.0h | 68.0h | 5 |
| Martin Turyna | 204.0h (incl. +4h IP overtime) | 120.0h | 5 |
| M. Turyna II | 200h | 160.0h | 5 |
| Sir Turbis | 150h | 90.0h | 5 |

Capacity Σ for Turyna = 40 + 40 + 40 + 40 + 44 = **204h** ✅ (override applied)
Capacity Σ for Jurby = 20 + 20 + 8 + 20 + 20 = **88h** ✅ (override applied)

Per-iteration team_totals: 80, 130, 78, 130, 20 = **438h delivered** vs
total team capacity 642h (88+204+200+150) → 68 % delivery ratio.

## A/B simple vs gates (PI-2026-1.2)

| Person | simple | gates | Δ |
|--------|--------|-------|---|
| Jaroslav Urbánek | 20.0h | 20.0h | +0.0h |
| Martin Turyna | 40.0h | 40.0h | +0.0h |
| M. Turyna II | 40.0h | 40.0h | +0.0h |
| Sir Turbis | 30.0h | 30.0h | +0.0h |

Both modes derive identical hours because the only evidence source in
this synthetic backlog is `contributors[].as/cw` declarations (no real
GitHub commit/PR/review activity). With real evidence, gates mode adds
prep credit at status transitions (Backlog → Implementing →
Implemented → Done) which simple ignores. Acceptance criterion *"no
person `gates` < `simple`"* trivially satisfied.

## edpa-results.xlsx (v1.10 consolidated workbook)

Verified on every iteration:

```
Sheets: ['Team Summary', 'Item Costs']

Team Summary tab (e.g. PI-2026-1.1):
  row1: 'EDPA 1.10.0-beta — PI-2026-1.1'  (merged A1:G1)
  row2: 'Project: EDPA E2E Pilot Simulation'
  row3: (blank)
  row4: ['Person','Role','FTE','Capacity (h)','Derived (h)','Items','OK']
  rows5-8: per-person rows
  row9: TOTAL

Item Costs tab:
  row1: 'EDPA 1.10.0-beta — PI-2026-1.1 — Per-Item Allocation'
  row2: (blank)
  row3: ['Item','Level','JS','Person','CW','Score','Ratio','Hours']
  rows4+: per-item-person
```

Old `summary.xlsx` and `item-costs.xlsx` are gone from output dirs —
clean v1.10 layout.

## Issues found during E2E (none blocking)

1. **`--non-interactive` mode in `project_setup.py` skips
   `create_project_views.py` invocation.** The setup script logs
   "non-interactive mode — skipping (run create_project_views.py
   manually)". Acceptable today (Playwright requires interactive
   login), but should surface as a `--no-views` flag or auto-skip with
   stronger message that it's expected behavior.
2. **Cosmetic regression in setup STEP 3 output:** "field-create
   failed" prints for fields that *do* get created on the second pass
   (idempotent retry). Verified post-setup that all 21 fields exist.
   Misleading log message; fix is one-liner in `project_setup.py`.
3. **`backlog.py add` does not accept `--contributor` flags.** RFC
   v1.10 wasn't claiming this, but the kashealth runbook examples used
   `--contributor` syntax which is invalid. Worked around by
   patching contributors into YAML directly. Either add the flag or
   correct the runbook.
4. **Empty `.edpa/sync_state.json` makes sync.py crash with
   `'NoneType' has no attribute 'get'`.** Workaround: seed file as
   `{}` (which is what `install.sh` does). Should add defensive load.
5. **Engine in simple/full mode requires `status: Done`** before
   crediting hours. Documented in source comment, not in user-facing
   docs. Add note to methodology.
6. **`backlog.py add Initiative --js 0`** is rejected by strict
   validator (`js must be > 0`). Initiatives in real life often have
   no Job Size estimate at I-level. Either relax validator for
   Initiatives or document the requirement.

## What was NOT exercised (acknowledged gaps)

- **`create_project_views.py`** — Playwright + persistent profile +
  manual GH login required. Not run in this E2E. Was last verified in
  v1.9.0 pilot prep.
- **Real commit / PR / review evidence as gates inputs.** Backlog
  used declarative `contributors:` YAML field only; no synthesized
  commits or PRs. Engine's evidence detection (assignee, /contribute,
  pr_author, commit_authors, pr_reviewers, commenters) ran against
  the synthetic data without real GitHub activity. For the real
  kashealth pilot this is the dominant signal source.
- **`/edpa:close-iteration --prep-only` invoked through the
  Claude-Code slash command surface.** Underlying script
  (`capacity_override.py --add --non-interactive`) was exercised; the
  user-facing slash flow is interpreted text in
  `plugin/commands/edpa/close-iteration.md`, not directly executable
  in the E2E harness.
- **MCP integration during a live close.** Covered by 16 unit tests
  but not by this E2E walk.
- **Auto-calibration (`/edpa:calibrate`).** Out of scope; needs ≥20
  manual-CW ground-truth records.

## Cleanup

Sandbox state at end of run:
- GH Project #49 still exists (visible at
  https://github.com/orgs/technomaton/projects/49) — left in place for
  manual inspection. Delete via `gh project delete 49 --owner technomaton`.
- 17 GH issues still open in `technomaton/edpa-e2e-test`. Wipe via
  `gh issue list ... | xargs -I {} gh issue delete {}` or use the
  `wipe_repo_issues + wipe_e2e_projects` helpers in
  `tests/test_e2e_sync.py`.
- Local workspace `/tmp/edpa-pilot-e2e-1778160610/` retained for
  forensic inspection. Safe to `rm -rf` after report review.

## Verdict

**v1.10.0-beta passes full pilot E2E.** All four release-shipped
features (xlsx consolidation, Stage 0 preflight, capacity override
helper, runbook trim) function correctly through the complete
iteration close cycle. Six minor issues found are cosmetic / docs /
edge cases and don't block kashealth pilot kickoff.

**Recommendation:** promote `v1.10.0-beta` → `v1.10.0-rc1` after
fixing items 2 (cosmetic log) and 4 (sync_state seed). Items 1 (views
in non-interactive), 3 (--contributor flag), 5 (status=Done docs), 6
(Initiative js=0) → backlog for v1.10.1 / v1.11.

## Reproducibility

```bash
# 1. Replay this E2E (creates new GH Project, ~10 min wall-clock):
TS=$(date +%s)
WS=/tmp/edpa-pilot-e2e-$TS
mkdir -p "$WS" && cd "$WS"
git init -q -b main && echo "sandbox" > README.md
git add . && git commit -qm init
git remote add origin https://github.com/technomaton/edpa-e2e-test.git
git push -uf origin main

cp -r ~/projects/edpa/plugin "$WS/.claude"
mkdir -p .edpa/{config,iterations,backlog/{initiatives,epics,features,stories},reports,snapshots}
echo '{}' > .edpa/sync_state.json
# Seed people.yaml, edpa.yaml, heuristics.yaml, 5 iteration YAMLs, backlog (see report § "Setup phase artifacts")

# 2. Stage 0 preflight (against real org)
python3 .claude/edpa/scripts/project_setup.py --org technomaton --repo edpa-e2e-test --check-only --non-interactive

# 3. Provisioning
python3 .claude/edpa/scripts/project_setup.py --org technomaton --repo edpa-e2e-test \
  --project-title "EDPA-E2E-Pilot $TS" --non-interactive --skip-preflight

# 4. Sync backlog
python3 .claude/edpa/scripts/sync.py push

# 5. Per iteration N in 1..5:
#    - mark iteration's stories status:Done in YAML
#    - python3 .claude/edpa/scripts/engine.py --edpa-root .edpa --iteration PI-2026-1.N --mode gates --output ...
#    - python3 .claude/edpa/scripts/reports.py PI-2026-1.N
#    - mark iteration.status: closed
# (Special: 1.3 with capacity_override jurby 8h; 1.5 with capacity_override turyna +4)

# 6. PI close
python3 .claude/edpa/scripts/engine.py --edpa-root .edpa --iteration PI-2026-1 --mode gates --output ...
python3 .claude/edpa/scripts/reports.py --pi PI-2026-1
```
