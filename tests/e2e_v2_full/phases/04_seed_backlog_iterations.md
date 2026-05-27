# Phase 04 — Seed Backlog + Iterations (run log)

Run tag: 20260527-142316-c6ac4db8
Sandbox: `/tmp/edpa-e2e-20260527-142316-c6ac4db8`
Repo: `technomaton/edpa-e2e-20260527-142316-c6ac4db8`
Worker: Wave B Unit 7

## Summary

- 33 backlog items created (1 Initiative + 2 Epics + 4 Features + 20 Stories + 2 Defects + 2 Events + 2 Risks).
- 10 iterations created (PI-2026-1.1..1.5 + PI-2026-2.1..2.5) on Mon-Sun 1-week cadence, 8 delivery + 2 IP.
- Stories + Defects carry `iteration` field from fixture `target_iteration`.
- 27 CLI-path items auto-committed individually by `backlog.py add`
  (`feat({ID}): {title}`). Defects/Events/Risks + iterations bundled
  in a single `no-ticket:` commit at the end.

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
| PI-2026-1.4 | Iteration | planned | 2026-01-26 | 2026-02-01 | 4 (S-9 + S-4 + S-14 + D-1) |
| PI-2026-1.5 | IP        | planned | 2026-02-02 | 2026-02-08 | 0 |
| PI-2026-2.1 | Iteration | planned | 2026-02-09 | 2026-02-15 | 3 |
| PI-2026-2.2 | Iteration | planned | 2026-02-16 | 2026-02-22 | 2 |
| PI-2026-2.3 | Iteration | planned | 2026-02-23 | 2026-03-01 | 2 |
| PI-2026-2.4 | Iteration | planned | 2026-03-02 | 2026-03-08 | 2 (S-20 + D-2) |
| PI-2026-2.5 | IP        | planned | 2026-03-09 | 2026-03-15 | 0 |

Mapping `fixture.type` -> on-disk `type`: `delivery` -> `Iteration`, `ip` -> `IP`
(MCP schema enum `{Iteration, IP}` capitalized).

Capacity: each iteration `planning.capacity = 144` (= alice 40 + bob-arch 32 + bob-pm 8 + carol 40 + dave 24).

## Verifications

- `find .edpa/backlog -name '*.md' | wc -l` -> `33` (target: 33) PASS
- `ls .edpa/iterations/*.yaml | wc -l` -> `10` (target: 10) PASS
- `python3 .edpa/engine/scripts/backlog.py validate`:
  - `Items: 29  Stories: 20  Errors: 0  Warnings: 35` PASS (exit 0)
  - Warnings are Fibonacci-only WSJF advisories on Stories S-6/S-8/S-9
    (fixture intentionally uses non-Fibonacci values like 6, 4) and
    `person_unused` no-op flags. Items count 29 = backlog.py only
    walks initiatives/epics/features/stories/defects (events/risks
    are tracked but skipped by validator scope — known engine
    behavior, not a Wave B problem).
- `python3 .edpa/engine/scripts/validate_iterations.py`:
  `0 error(s), 2 warning(s)` PASS (warnings: missing
  `PI-2026-1.yaml` / `PI-2026-2.yaml` PI metadata files — derived
  from iterations, expected per current setup).
- `backlog.py status`: Total 88 SP, 20 stories, 2 Epics, 4 Features.
- Sandbox pushed: commit `82e1cbc` on `origin/main`.

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

1. MCP `mcp__plugin_edpa_edpa__*` tools resolve `.edpa/` from host
   project (`/Users/jurby/projects/edpa`), not the sandbox cwd —
   confirmed during Unit 6 and reproduced when we considered driving
   item creation via MCP. Workaround per task brief: call vendor-ed
   engine scripts directly (`.edpa/engine/scripts/backlog.py add`)
   which honour `find_repo_root()` walking from cwd.
2. `backlog.py add` CLI supports only `{Initiative, Epic, Feature,
   Story}` — Defects, Events, Risks written via direct YAML
   frontmatter (canonical key order matches `mcp_server._handle_item_create`).
3. `id_counters.yaml` had to be bumped manually for direct-write
   types so a future `backlog.py add Defect/Event/Risk` (if added
   later) wouldn't collide with our manually allocated IDs.

## MCP attempts

None — MCP `edpa_item_create` / `edpa_iteration_create` could not be
used per Unit 6 finding (server cwd points at host repo). All writes
went through the vendor-ed engine scripts plus direct file I/O.

## Tooling artifacts (sandbox-local, not committed)

- `.e2e_seed.py` — one-shot orchestrator that drove all three phases
  (CLI items, direct YAML items, iteration YAMLs).
- `.e2e_seed_summary.json` — ref-to-id map persisted between phases.

These live in the sandbox repo working tree only; the test harness
treats them as run-local scratch and the seed commit excludes them.

## Sandbox commits

```
82e1cbc no-ticket: seed defects/events/risks + 10 iterations (Wave B Unit 7)
48fa9f0 feat(S-20): Docs + sample CSV in docs/examples/
...
ab66ab2 feat(I-1): EDPA V2 Production Hardening
aea4bfb no-ticket: install EDPA engine + seed config (Wave B Unit 6)
6c0fc8e initial: sandbox bootstrap for 20260527-142316-c6ac4db8
```

3rd commit after Unit 7 baseline: `82e1cbc` (the seed commit itself).
