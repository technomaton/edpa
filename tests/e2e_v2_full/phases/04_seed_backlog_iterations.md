# Phase 04 — Seed Backlog + Iterations (run log)

Run tag: 20260527-181051-2c56a6a0
Sandbox: `/tmp/edpa-e2e-20260527-181051-2c56a6a0`
Repo: `technomaton/edpa-e2e-20260527-181051-2c56a6a0`
Worker: Wave B Unit 7
Started: 2026-05-27T18:15Z
Finished: 2026-05-27T18:24Z
Sandbox HEAD (pushed): `7c4f87f`

## Summary

- 33 backlog items created (1 Initiative + 2 Epics + 4 Features + 20 Stories + 2 Defects + 2 Events + 2 Risks).
- 10 iterations created (PI-2026-1.1..1.5 + PI-2026-2.1..2.5) on Mon-Sun 1-week cadence, 8 delivery + 2 IP.
- Stories + Defects carry `iteration` field from fixture `target_iteration`.
- **All 33 items went through `backlog.py add` CLI path** (incl. Defects/Events/Risks). The c1cbbc2 fix worked
  end-to-end after re-vendoring the engine into the sandbox (see "c1cbbc2 verification" below).
- 33 CLI-path items auto-committed individually by `backlog.py add` (`feat({ID}): {title}`).
  Iteration YAMLs bundled in a single `no-ticket:` commit. One extra `no-ticket:` commit for the engine re-vendor.

## c1cbbc2 verification

The vendored copy of `backlog.py` installed by Unit 6 via `install.sh` was pulled from `main` (EDPA 2.1.2) and
**did not yet include** the c1cbbc2 fix — `--type` choices were still limited to `{Initiative, Epic, Feature, Story}`.
The fix lives in the working tree (`fix/e2e-v2-findings` branch).

When the orchestrator reached item #28 (first Defect), it hit:
```
backlog add: error: argument --type: invalid choice: 'Defect' (choose from 'Initiative', 'Epic', 'Feature', 'Story')
```

Resolution: re-vendor the engine's `backlog.py` from the source-of-truth
(`/Users/jurby/projects/edpa/plugin/edpa/scripts/backlog.py`) into the sandbox
(`/tmp/edpa-e2e-20260527-181051-2c56a6a0/.edpa/engine/scripts/backlog.py`).
The re-vendor is committed as `801b956 no-ticket: re-vendor backlog.py with c1cbbc2 fix (Wave B Unit 7)`.

After the re-vendor, items #28..#33 (D-1, D-2, EV-1, EV-2, R-1, R-2) all went through
the CLI path successfully and auto-committed individually. No direct YAML writes or
manual `id_counters.yaml` bumps were required (unlike the previous run).

**Findings for the EDPA maintainer:**
- c1cbbc2 itself works correctly — Defect/Event/Risk go through `cmd_add` -> MCP handler unchanged.
- Future E2E runs should either (a) release a new tag containing c1cbbc2 before bootstrapping the
  sandbox, or (b) extend `install.sh` to accept a `--from-local-dir` flag so the harness can vendor
  from the working tree instead of GitHub. The current install.sh has no path for this.

## Items created

Mapping `#ref` (fixture position) -> `actual_id` -> type/parent/iteration.

| ref | actual_id | type | parent | iteration |
|-----|-----------|------|--------|-----------|
| #1 | I-1 | Initiative | - | - |
| #2 | E-1 | Epic | I-1 | - |
| #3 | E-2 | Epic | I-1 | - |
| #4 | F-1 | Feature | E-1 | - |
| #5 | F-2 | Feature | E-1 | - |
| #6 | F-3 | Feature | E-2 | - |
| #7 | F-4 | Feature | E-2 | - |
| #8 | S-1 | Story | F-1 | PI-2026-1.1 |
| #9 | S-2 | Story | F-1 | PI-2026-1.2 |
| #10 | S-3 | Story | F-1 | PI-2026-1.3 |
| #11 | S-4 | Story | F-1 | PI-2026-1.4 |
| #12 | S-5 | Story | F-1 | PI-2026-2.1 |
| #13 | S-6 | Story | F-2 | PI-2026-1.1 |
| #14 | S-7 | Story | F-2 | PI-2026-1.2 |
| #15 | S-8 | Story | F-2 | PI-2026-1.3 |
| #16 | S-9 | Story | F-2 | PI-2026-1.4 |
| #17 | S-10 | Story | F-2 | PI-2026-2.1 |
| #18 | S-11 | Story | F-3 | PI-2026-1.1 |
| #19 | S-12 | Story | F-3 | PI-2026-1.2 |
| #20 | S-13 | Story | F-3 | PI-2026-1.3 |
| #21 | S-14 | Story | F-3 | PI-2026-1.4 |
| #22 | S-15 | Story | F-3 | PI-2026-2.1 |
| #23 | S-16 | Story | F-4 | PI-2026-2.2 |
| #24 | S-17 | Story | F-4 | PI-2026-2.2 |
| #25 | S-18 | Story | F-4 | PI-2026-2.3 |
| #26 | S-19 | Story | F-4 | PI-2026-2.3 |
| #27 | S-20 | Story | F-4 | PI-2026-2.4 |
| #28 | D-1 | Defect | F-2 | PI-2026-1.4 |
| #29 | D-2 | Defect | F-3 | PI-2026-2.4 |
| #30 | EV-1 | Event | I-1 | - |
| #31 | EV-2 | Event | I-1 | - |
| #32 | R-1 | Risk | E-1 | - |
| #33 | R-2 | Risk | E-1 | - |

Type totals: Initiative 1, Epic 2, Feature 4, Story 20, Defect 2, Event 2, Risk 2 = 33.

## Iterations created

| id | type | status | start | end | items count |
|----|------|--------|-------|-----|-------------|
| PI-2026-1.1 | Iteration | planned | 2026-01-05 | 2026-01-11 | 3 |
| PI-2026-1.2 | Iteration | planned | 2026-01-12 | 2026-01-18 | 3 |
| PI-2026-1.3 | Iteration | planned | 2026-01-19 | 2026-01-25 | 3 |
| PI-2026-1.4 | Iteration | planned | 2026-01-26 | 2026-02-01 | 4 (S-4 + S-9 + S-14 + D-1) |
| PI-2026-1.5 | IP        | planned | 2026-02-02 | 2026-02-08 | 0 |
| PI-2026-2.1 | Iteration | planned | 2026-02-09 | 2026-02-15 | 3 |
| PI-2026-2.2 | Iteration | planned | 2026-02-16 | 2026-02-22 | 2 |
| PI-2026-2.3 | Iteration | planned | 2026-02-23 | 2026-03-01 | 2 |
| PI-2026-2.4 | Iteration | planned | 2026-03-02 | 2026-03-08 | 2 (S-20 + D-2) |
| PI-2026-2.5 | IP        | planned | 2026-03-09 | 2026-03-15 | 0 |

Mapping `fixture.type` -> on-disk `type`: `delivery` -> `Iteration`, `ip` -> `IP`
(MCP schema enum `{Iteration, IP}` capitalized — fixture is lowercase).

Capacity: each iteration `planning.capacity = 144` (= alice 40 + bob-arch 32 + bob-pm 8 + carol 40 + dave 24).

Iteration YAML schema written (matches MCP `_handle_iteration_create` output + fixture metadata):
```yaml
iteration:
  id: PI-2026-1.1
  pi: PI-2026-1
  start_date: '2026-01-05'
  end_date: '2026-01-11'
  type: Iteration
  weeks: 1
  status: planned
  planning:
    capacity: 144
    planned_sp: 0
  notes: First delivery iteration of PI-1
```

## Verifications

- `find .edpa/backlog -name '*.md' | wc -l` -> `33` (target: 33) **PASS**
- `ls .edpa/iterations/*.yaml | wc -l` -> `10` (target: 10) **PASS**
- `python3 .edpa/engine/scripts/backlog.py validate`:
  - `Items: 29  Stories: 20  Errors: 0  Warnings: 35` **PASS** (exit 0)
  - Warnings are Fibonacci-only WSJF advisories on Stories with non-Fibonacci `rr_oe` values
    (fixture intentionally uses 4, 6 to exercise the warning channel) and `person_unused`
    no-op flags. Items count 29 = backlog.py only walks initiatives/epics/features/stories/defects
    (events/risks are tracked but skipped by validator scope — known engine behavior).
- `python3 .edpa/engine/scripts/validate_iterations.py`:
  `0 error(s), 2 warning(s)` **PASS** (warnings: missing `PI-2026-1.yaml` / `PI-2026-2.yaml`
  PI-metadata files — these are optional; PI metadata is derived from iterations).
- `backlog.py status`: Total 88 SP, 20 stories, 2 Epics, 4 Features. **PASS**
- Sandbox pushed: commit `7c4f87f` on `origin/main`. **PASS**

## Iteration distribution check

Wave A plan target — 2-3 items per delivery iter, 4 at PI-1.4 (mid-PI
defect lands), 2 at PI-2.4 (mid-PI defect again). Actual:

```
PI-2026-1.1   3   (S-1 + S-6 + S-11)
PI-2026-1.2   3   (S-2 + S-7 + S-12)
PI-2026-1.3   3   (S-3 + S-8 + S-13)
PI-2026-1.4   4   (S-4 + S-9 + S-14 + D-1)   <- mid-PI defect
PI-2026-1.5   0   (IP)
PI-2026-2.1   3   (S-5 + S-10 + S-15)
PI-2026-2.2   2   (S-16 + S-17)
PI-2026-2.3   2   (S-18 + S-19)
PI-2026-2.4   2   (S-20 + D-2)              <- mid-PI defect
PI-2026-2.5   0   (IP)
```

Matches fixture target shape (8 delivery iters carry 22 items =
20 Stories + 2 Defects; 2 IP iters empty).

## Issues encountered

1. **MCP cwd resolution (known)** — `mcp__plugin_edpa_edpa__*` tools resolve `.edpa/` from
   the host project (`/Users/jurby/projects/edpa`), not the sandbox cwd. Documented in commit
   `7f369bf`. Workaround: call vendored engine scripts directly via subprocess from inside
   the sandbox so `find_repo_root()` walks from the sandbox cwd.

2. **Vendored engine staleness (new — fixed in-flight)** — Unit 6 installed via
   `install.sh` which pulls from GitHub `main` (2.1.2). The c1cbbc2 fix is on the working
   `fix/e2e-v2-findings` branch and not yet merged to `main`, so the vendored `backlog.py`
   in the sandbox did not have the all-7-types fix. Worked around by re-vendoring the file
   from the working tree (`cp /Users/jurby/projects/edpa/plugin/edpa/scripts/backlog.py
   /tmp/.../.edpa/engine/scripts/backlog.py`) and committing as a clearly labeled
   `no-ticket:` commit. After the re-vendor, all Defect/Event/Risk creates went through
   the CLI path with no further intervention.

3. **No `id_counters.yaml` manual bumps needed** — previous run had to manually edit
   `id_counters.yaml` because Defect/Event/Risk were written via direct YAML. This run
   used the CLI exclusively, so `id_counter.py` allocated all IDs cleanly and the counter
   advanced naturally (I:1, E:2, F:4, S:20, D:2, EV:2, R:2).

## MCP attempts

None — per Unit 6 finding, MCP `edpa_item_create` / `edpa_iteration_create` cannot target
the sandbox (resolves `.edpa/` from host repo). All writes went through the vendored
engine scripts (subprocess `python3 .edpa/engine/scripts/backlog.py add ...`) plus direct
YAML write for the 10 iteration files.

## Tooling artifacts (sandbox-local, not committed)

- `.e2e_seed.py` — first orchestrator pass (items #1..#27 succeeded, #28 failed on
  stale `backlog.py`).
- `.e2e_seed_resume.py` — resume pass (items #28..#33 + all 10 iterations).
- `.e2e_seed_summary.json` — ref-to-id map persisted between phases.

These live in the sandbox working tree only; the `.gitignore` pattern `.e2e_*`
(installed by Unit 6) excludes them from commits.

## Sandbox commits

```
7c4f87f no-ticket: seed 10 iteration YAMLs (Wave B Unit 7)
2f3364b feat(R-2): Multi-role person attribution edge cases
689899b feat(R-1): GitHub API rate limit blocks large iterations
c868bd1 feat(EV-2): Compliance review for evidence storage
61d05e0 feat(EV-1): PI-1 retro session
438efc8 feat(D-2): XLSX export truncates long item titles
c19f982 feat(D-1): Engine fails on empty iteration with custom calendar
801b956 no-ticket: re-vendor backlog.py with c1cbbc2 fix (Wave B Unit 7)
d39b368 feat(S-20): Docs + sample CSV in docs/examples/
... (S-19..S-1, F-4..F-1, E-2..E-1, I-1)
bc20d80 no-ticket: install EDPA engine + seed config (Wave B Unit 6)
624bb31 initial: sandbox bootstrap for 20260527-181051-2c56a6a0
```

Total: 35 new commits added by Unit 7 (33 `feat({ID}):` + 1 re-vendor + 1 iteration bundle).
All pushed to `origin/main` (HEAD: `7c4f87f`).
