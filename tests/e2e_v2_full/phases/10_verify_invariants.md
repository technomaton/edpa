# Phase 10 — Verify Invariants — run log

Run tag: 20260527-142316-c6ac4db8
Worker: Wave C Unit 11 (agent-a2676f0a30fdaee91)
Sandbox: technomaton/edpa-e2e-20260527-142316-c6ac4db8 @ Wave B HEAD
Started: 2026-05-27T15:20Z
Finished: 2026-05-27T15:23Z
Status: PASS

## Scope

Read-only verification (no sandbox mutation) of the artifacts left by Wave B
Units 8-10:

1. Every per-iteration `edpa_results.json` reports `all_invariants_passed=true`,
   per-person `invariant_ok=true`, `team_total == sum(total_derived)`, and
   each person whose `total_derived > 0` lands on `capacity` within tolerance.
2. Every snapshot file in `.edpa/snapshots/` carries `frozen=true` plus a
   `payload_signature` that recomputes byte-for-byte under the engine's own
   hash definition (`hashlib.sha256(payload-minus-generated_at)`).
3. `backlog.py status` exits 0 (smoke sanity check after close).
4. Cross-PI rollups: PI-1 and PI-2 totals.

## Engine invariants

| Iteration   | iter_type | all_invariants_passed | team_total | invariant_ok (all 5 people) |
|-------------|-----------|------------------------|------------|------------------------------|
| PI-2026-1.1 | Iteration | true                   | 64.0h      | yes                          |
| PI-2026-1.2 | Iteration | true                   | 64.0h      | yes                          |
| PI-2026-1.3 | Iteration | true                   | 112.0h     | yes                          |
| PI-2026-1.4 | Iteration | true                   | 104.0h     | yes                          |
| PI-2026-1.5 | IP        | true                   | 0h         | yes                          |
| PI-2026-2.1 | Iteration | true                   | 72.0h      | yes                          |
| PI-2026-2.2 | Iteration | true                   | 40.0h      | yes                          |
| PI-2026-2.3 | Iteration | true                   | 64.0h      | yes                          |
| PI-2026-2.4 | Iteration | true                   | 40.0h      | yes                          |
| PI-2026-2.5 | IP        | true                   | 0h         | yes                          |

Per-person capacity invariant: every person with `total_derived > 0` matches
their `capacity` exactly (drift = 0.0h, tolerance was max(1% × cap, 0.5h)).
People with `total_derived == 0` had no Done items in that iteration and are
exempt from the capacity check.

Sum check: `team_total == sum(total_derived)` for all 10 iterations
(`abs(diff) < 0.01`).

`iteration_type` is `None` in `edpa_results.json` itself, so iteration type
is resolved from `.edpa/iterations/<id>.yaml::iteration.type` to identify
the IP iterations (PI-2026-1.5, PI-2026-2.5).

## Snapshots

| Snapshot                       | frozen | signature prefix     | recomputed match | size   |
|--------------------------------|--------|----------------------|-------------------|--------|
| PI-2026-1.1.json               | true   | df072c7394961483…   | yes               | 2927 B |
| PI-2026-1.1_rev2.json          | true   | cfdc0b2938604e44…   | yes               | 3514 B |
| PI-2026-1.1_rev3.json          | true   | cfdc0b2938604e44…   | yes               | 3514 B |
| PI-2026-1.2.json               | true   | 3d2f8ade24eca8b7…   | yes               | 3512 B |
| PI-2026-1.3.json               | true   | 7934e70b5df66aea…   | yes               | 3510 B |
| PI-2026-1.4.json               | true   | 49972061fcfc236a…   | yes               | 3708 B |
| PI-2026-1.5.json               | true   | cc7151b02c0f24f9…   | yes               | 2927 B |
| PI-2026-2.1.json               | true   | ad3849736e1e3236…   | yes               | 3516 B |
| PI-2026-2.2.json               | true   | 13e891be97b81b70…   | yes               | 3321 B |
| PI-2026-2.3.json               | true   | e9ff722052c31ee1…   | yes               | 3316 B |
| PI-2026-2.4.json               | true   | dfd60473997027a2…   | yes               | 3319 B |
| PI-2026-2.5.json               | true   | 530d16592f140342…   | yes               | 2927 B |

Signature format note: `engine.py::_payload_signature` writes a raw 64-char
hex digest (no `sha256:` prefix). The task spec's `sig.startswith("sha256:")`
check would fail against the actual engine output; the verifier instead
asserts `len == 64` plus a hex character class. Recomputation must exclude
`generated_at`, `payload_signature`, and `frozen_at` because engine hashes
the payload *before* injecting the latter two keys (`engine.py:1247-1268`).
All 12 snapshots recomputed byte-identical to the stored digest.

`_rev2` and `_rev3` share the same `cfdc0b2938604e44…` digest, confirming
that the engine's revision branch is deterministic — same inputs → same
content hash, just an extra file because `engine.py::write_snapshot` writes
a new `_revN` whenever the canonical file already exists with a *different*
prior digest (Unit 10 ran the engine once before populating `contributors[]`,
producing the original `df072c73…` snapshot, then re-ran twice after, both
producing `cfdc0b29…`).

## backlog.py status (cross-check)

`python3 .edpa/engine/scripts/backlog.py status` exits 0. Stdout reports:

- Total 88 SP across 20 Done stories (100% progress, no Implementing/Remaining).
- Hierarchy: 2 Epics, 4 Features, 20 Stories.
- Iteration velocity correctly distributes 88 SP across 8 delivery iterations.

## Aggregate totals

- PI-2026-1 total: 344.0h
- PI-2026-2 total: 216.0h
- Combined: 560.0h

Matches Unit 10's expected ~560h delivery total.

## Verdict

PASS.

- 10/10 `edpa_results.json` files: `all_invariants_passed=true`, per-person
  `invariant_ok=true`, sum identity holds, capacity invariant holds.
- 12/12 snapshots: `frozen=true`, signature recomputes to stored digest.
- `backlog.py status` returns 0.
- Cross-PI totals (344h + 216h = 560h) consistent with Wave B reports.

No mutations made to the sandbox; verification is purely observational.

## Script

```
$ python3 tests/e2e_v2_full/phases/10_verify_invariants.py
# … per-iteration / per-snapshot OK lines …
VERDICT: PASS — 10 iterations, 12 snapshots, PI-1=344.0h PI-2=216.0h total=560.0h
$ echo $?
0
```
