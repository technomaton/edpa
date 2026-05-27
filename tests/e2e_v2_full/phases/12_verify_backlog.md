# Phase 12 — Verify Backlog + Iteration State — run log

Run tag: 20260527-142316-c6ac4db8
Worker: Wave C verification worker (agent-aa748e53400f09750)
Sandbox: /tmp/edpa-e2e-20260527-142316-c6ac4db8 @ `e49ffb9`
GitHub: technomaton/edpa-e2e-20260527-142316-c6ac4db8

## Scope

Read-only verification, run in parallel with the other Wave C workers.
Two artifacts: this run log and a sibling `12_verify_backlog.py`
(harness-runnable script that re-derives every number reported here).

## Item counts

Direct scan of `.edpa/backlog/*/*.md` frontmatter, grouped by
`(type, status)`:

| Type        | Status      | Count | Expected |
|-------------|-------------|------:|---------:|
| Initiative  | Validating  |     1 |        1 |
| Epic        | Validating  |     2 |        2 |
| Feature     | Done        |     3 |        3 |
| Feature     | Validating  |     1 |        1 |
| Story       | Done        |    20 |       20 |
| Defect      | Done        |     2 |        2 |
| Event       | Done        |     2 |        2 |
| Risk        | Funnel      |     2 |        2 |
| **Total**   |       —     | **33** | **33** |

All 8 (type, status) buckets match the task spec exactly; no
unexpected combinations were observed.

Spot-checked IDs:

- `I-1` Initiative "EDPA V2 Production Hardening" → Validating
- `E-1`, `E-2` Epics → Validating
- `F-1`, `F-2`, `F-3` Features → Done
- `F-4` Feature → Validating
- `S-1` … `S-20` Stories → all Done
- `D-1`, `D-2` Defects → Done
- `EV-1`, `EV-2` Events → Done
- `R-1`, `R-2` Risks → Funnel (intentionally not transitioned)

## Iteration state

Each `.edpa/iterations/PI-2026-*.yaml` was loaded and inspected:

| Iteration   | status | capacity (h) |
|-------------|--------|-------------:|
| PI-2026-1.1 | closed |          144 |
| PI-2026-1.2 | closed |          144 |
| PI-2026-1.3 | closed |          144 |
| PI-2026-1.4 | closed |          144 |
| PI-2026-1.5 | closed |          144 |
| PI-2026-2.1 | closed |          144 |
| PI-2026-2.2 | closed |          144 |
| PI-2026-2.3 | closed |          144 |
| PI-2026-2.4 | closed |          144 |
| PI-2026-2.5 | closed |          144 |

**Closed: 10/10. Capacity per iteration: 144 h. Both pass.**

Cross-check with `validate_iterations.py`:

```
⚠ [missing_pi_yaml] PI-2026-1: iterations/PI-2026-1.yaml missing — PI metadata derived from iterations
⚠ [missing_pi_yaml] PI-2026-2: iterations/PI-2026-2.yaml missing — PI metadata derived from iterations

0 error(s), 2 warning(s)
exit code: 0
```

The two PI-yaml warnings are expected per the E2E design (the test seeds
iteration YAMLs only; PI rollup YAMLs are optional).

## `backlog.py validate`

```
$ cd /tmp/edpa-e2e-20260527-142316-c6ac4db8 \
  && python3 .edpa/engine/scripts/backlog.py validate
```

Result: **exit 1** (3 errors, 35 warnings).

```
  [PASS]  Story assignees present
  [PASS]  Story JS values present
  [PASS]  Story JS <= 8
  [PASS]  Parent references valid
  [PASS]  Parent type hierarchy
  [PASS]  Iteration assignments
  [PASS]  WSJF consistency
  [PASS]  No duplicate IDs
  [PASS]  CW values valid
  [PASS]  Type fields present
  [FAIL]  Fibonacci values
  [FAIL]  SAFe status values

  Errors:
    x I-1: status 'Validating' is not valid for Initiative
           (valid: Funnel, Reviewing, Analyzing, Ready, Implementing, Done)
    x E-1: status 'Validating' is not valid for Epic
           (valid: Funnel, Reviewing, Analyzing, Ready, Implementing, Done)
    x E-2: status 'Validating' is not valid for Epic
           (valid: Funnel, Reviewing, Analyzing, Ready, Implementing, Done)

  Summary:
    Items:    29  (Initiative/Epic/Feature/Story/Defect — Events + Risks excluded)
    Stories:  20
    Errors:   3
    Warnings: 35
```

### Finding: Wave B gate transitions vs. schema

The engine schema (`.edpa/engine/scripts/validate_syntax.py`) defines:

- `PORTFOLIO_STATUSES = {Funnel, Reviewing, Analyzing, Ready, Implementing, Done}` — for Initiative and Epic.
- `DELIVERY_STATUSES = {Funnel, Analyzing, Backlog, Implementing, Validating, Deploying, Releasing, Done}` — for Feature, Story, and Defect.

Wave B transitioned `I-1`, `E-1`, and `E-2` to `Validating` (commit
`2eabb8a` "gate transitions after PI-2026-2.4") as part of staging the
PI close. That status is **not** a portfolio status, so the validator
rejects it. This is a real divergence between the test scenario and
the schema — neither side is incontestably right:

- The task spec (Phase 12) explicitly lists `Initiative,Validating: 1`
  and `Epic,Validating: 2` as expected — i.e. the scenario *intends*
  these portfolio items to be in Validating.
- The schema rejects that combination.

The 35 Fibonacci warnings are also Wave B–seeded non-Fibonacci `bv`,
`tc`, and `rr_oe` values (e.g. `bv=10`, `tc=6`, `rr_oe=4`). They are
warnings, not errors, and do not change the exit code.

**Decision for Phase 12:** capture the validate output verbatim, do
not promote it to a phase failure. The hard invariants are (a) the
count distribution per the task spec, (b) all iterations closed, and
(c) board renders. All three pass. The validate divergence is logged
here so future runs can decide whether to (i) update the gate ladder,
(ii) constrain Wave B to portfolio-legal transitions, or (iii) adjust
the schema.

## MCP tool attempts (confirmed host-scope limitation)

Each MCP tool was invoked live from this verification session. The
EDPA MCP server is wired into the host repo (`/Users/jurby/projects/edpa`),
not the sandbox under `/tmp/`, so every response below reflects the
**host repo** state, not the sandbox state. This is the documented Unit 6
limitation and matches the task spec's expectation.

### `edpa_status` (no args)

```json
{
  "project": "Medical Platform & Datovy e-shop",
  "current_pi": "PI-2026-1",
  "iterations_total": 5,
  "iterations_closed": 3,
  "active_iteration": "PI-2026-1.4",
  "team_size": 9,
  "total_capacity_per_iteration": 400,
  "cadence": "1-week iterations, 5-week PI (5 iterations)"
}
```

Host project is "Medical Platform & Datovy e-shop", 9 people,
400 h/iter — distinct from the sandbox's "EDPA V2 Sandbox" (4 humans /
5 contracts, 144 h/iter). Limitation confirmed.

### `edpa_iterations` (status=closed)

Returns 3 iterations (PI-2026-1.1, 1.2, 1.3) with start dates 2026-04-06
through 2026-04-24 — the host repo's cadence, not the sandbox's
2026-01-05 onwards. Sandbox has 10 closed iterations (1.1–1.5, 2.1–2.5),
host has 3.

### `edpa_validate` (no args)

```json
{ "ok": true, "pi_count": 2, "iteration_count": 10,
  "errors": [], "warnings": [ /* 7 person_no_github, 2 person_unused */ ] }
```

Reports 2 PIs / 10 iterations for the host project. Returns `ok: true`
because the host's `validate_iterations.py` only checks iteration YAMLs,
not backlog statuses — distinct from the sandbox-side
`backlog.py validate` finding above.

### `edpa_people` (no args)

Returns the 9 host-repo people (urbanek, tuma, turyna, matousek, pm,
d1, d2, do, ux1). Sandbox has 5 entries (alice, bob-arch, bob-pm,
carol, dave). Different roster.

### `edpa_backlog` (no args)

Returns 37 items rooted at host-repo Initiative `I-1` "Medical Platform
& Datovy e-shop" with Stories S-200…S-226 and Features F-100/F-101/
F-102/F-110/F-111/F-120 — sandbox uses S-1…S-20 and F-1…F-4. ID
namespaces collide on `I-1` but the titles differ, so the host-vs-
sandbox split is unambiguous.

### `edpa_flow_metrics` (iteration=PI-2026-1.1)

Returns 7 host items: throughput 4 done, 3 open. cycle_time stats are
null because the host repo has not yet run a timestamp sync. Sandbox
flow metrics would require running the MCP tool inside the sandbox
context, which is the limitation we are documenting.

**Conclusion (per task spec section 4):** MCP tools return host-repo
data, NOT sandbox data. This is documented behavior per Unit 6 — no
test failure here.

## Board snapshot

```
$ cd /tmp/edpa-e2e-20260527-142316-c6ac4db8 \
  && python3 .edpa/engine/scripts/board.py \
       --output /tmp/edpa-e2e-board-20260527-142316-c6ac4db8.html
Board written to /tmp/edpa-e2e-board-20260527-142316-c6ac4db8.html  (29 items loaded)
```

| Metric                         | Value                                                  |
|--------------------------------|--------------------------------------------------------|
| Path                           | `/tmp/edpa-e2e-board-20260527-142316-c6ac4db8.html`    |
| Size                           | 40 248 bytes                                           |
| MD5                            | `440f6919dee562a3d09ca32339b76bac`                     |
| Item cards rendered            | 29 (=1 Initiative + 2 Epics + 4 Features + 20 Stories + 2 Defects) |
| Events + Risks rendered        | 0 (board.py excludes both type dirs by design)         |
| Distinct iterations referenced | 8 (PI-2026-1.1…1.4 + 2.1…2.4 — 1.5 and 2.5 had no stories) |

The two IP iterations (PI-2026-1.5 and PI-2026-2.5) have zero Story
items assigned in this run (per the Wave B simulation), so the board
naturally omits them. Initiative/Epic/Feature cards do render.

## Direct-script flow metrics

The engine ships flow metrics only via the MCP entry point (no
standalone CLI script). Since MCP is host-scoped (see section
above), sandbox-side flow metrics cannot be computed without wiring
the server at the sandbox path. The engine pass during Wave B Unit 10
already wrote `edpa_results.json` for every iteration, so per-person
hour allocations are available for downstream reports. Flow metrics
proper remain out of scope for this verification phase and are
covered by `tests/test_mcp_flow_metrics.py` at the host level.

## Hard invariants (Phase 12 gate)

| Invariant                   | Result |
|-----------------------------|--------|
| 33 items, distribution OK   | PASS   |
| 10/10 iterations closed     | PASS   |
| board.py produces HTML > 1 KB with all 29 cards | PASS |

## Soft observations (informational, not gates)

| Observation                                  | Status                                                            |
|----------------------------------------------|-------------------------------------------------------------------|
| `backlog.py validate` exit                   | 1 — 3 errors (Initiative/Epic 'Validating'), 35 Fibonacci warnings |
| `validate_iterations.py` exit                | 0 — 2 missing-PI-yaml warnings (expected per E2E design)          |
| MCP tools return host repo data              | confirmed — Unit 6 documented limitation                          |

## Verdict

**Phase 12: PASS.**

All hard invariants pass. The validate divergence and MCP host-scoping
are surfaced for the test maintainer but do not block Phase 12.

## Files produced

- `tests/e2e_v2_full/phases/12_verify_backlog.py` (harness-runnable)
- `tests/e2e_v2_full/phases/12_verify_backlog.md` (this log)
- `/tmp/edpa-e2e-board-20260527-142316-c6ac4db8.html` (board snapshot)
