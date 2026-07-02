# EDPA V2 — Full End-to-End Test

End-to-end exercise of the entire EDPA V2 stack (`install.sh` → skills → MCP →
engine → reports → CI workflow) against a real, throwaway GitHub sandbox repo
and a local sandbox project under `/tmp/`.

The test simulates two Program Increments (PI-1 and PI-2), each containing
five weekly iterations (10 iterations total), with realistic work patterns
from four team members spanning five roles. Each iteration produces commits,
pull requests, reviews, and comments; the engine derives hours from the
resulting evidence; reports are generated; invariants are verified.

## What the test exercises

| Layer                          | Coverage                                        |
|--------------------------------|-------------------------------------------------|
| `install.sh` (curl-style)      | clean install into empty repo, idempotency      |
| `/edpa:setup` skill            | engine vendoring, config seeding, hook install  |
| `/edpa:add` skill              | id_counters allocation, parent validation       |
| `/edpa:close-iteration` skill  | capacity prep + engine + reports                |
| `/edpa:reports` skill          | timesheets, item costs, snapshots, exports      |
| MCP server (`edpa_*` tools)    | backlog reads/writes, transitions, validate     |
| Engine (`engine.py`)           | gates mode, CW from heuristics, invariants      |
| Heuristics                     | weight derivation across PR/review/comment mix  |
| CI workflow                    | PR-signal materialization (`hybrid`/`real`)     |
| Local hooks                    | post-commit signal emission, validate-on-save   |

## Prerequisites

| Tool / setup            | Requirement                                          |
|-------------------------|------------------------------------------------------|
| `gh` (GitHub CLI)       | logged in (`gh auth status`)                         |
| `gh` token scopes       | `admin:org`, `repo`, `workflow`, `project`           |
| `python3`               | >= 3.10                                              |
| `git`                   | >= 2.30                                              |
| `openssl`               | available on `$PATH` (for `RUN_TAG` generation)      |
| EDPA repo               | available locally; harness auto-detects via `git`    |
| Disk space              | ~200 MB free under `/tmp` (sandbox + logs)           |

`gh auth status` must show the four scopes above. The org owner used for the
sandbox repo (default `technomaton`) must allow the authenticated user to
create repositories.

## Environment variables

| Variable                   | Default                                       | Purpose                                                          |
|----------------------------|-----------------------------------------------|------------------------------------------------------------------|
| `EDPA_E2E_RUN_TAG`         | `YYYYMMDD-HHMMSS-<rand8>` (auto-generated)    | Unique tag for this run (used in repo name + sandbox dir name)   |
| `EDPA_E2E_SANDBOX_DIR`     | `/tmp/edpa-e2e-${RUN_TAG}`                    | Local sandbox project root                                       |
| `EDPA_E2E_GH_OWNER`        | `technomaton`                                 | GitHub org/user that owns the sandbox repo                       |
| `EDPA_E2E_CI_MODE`         | `hybrid`                                      | `hybrid` \| `real` \| `synthetic` — controls PR-signal pathway   |
| `EDPA_E2E_DRY_RUN`         | `0`                                           | `1` to print phase plan without executing                        |
| `EDPA_E2E_KEEP_SANDBOX`    | `0`                                           | `1` to leave `${EDPA_E2E_SANDBOX_DIR}` on disk after the run     |
| `EDPA_REPO_ROOT`           | auto-detected from `git rev-parse`            | Override if running outside the EDPA repo                        |

### CI mode trade-offs

`EDPA_E2E_CI_MODE` is consumed by the agent-driven simulation stages
(07–08 below), not by the automated verification phases:

- `real` — every PR waits for the actual GitHub Action to complete (~5 min
  per PR). Highest fidelity, slowest. Use this for release verification.
- `synthetic` — PR signals are injected directly into the local evidence
  store, bypassing GitHub Actions. Fast, but does not exercise the CI
  workflow itself.
- `hybrid` (default) — PI-1 uses the `real` path (one full PR-signal
  round-trip per PR) to prove the CI workflow works; PI-2 switches to
  `synthetic` injection to keep total runtime reasonable.

## Usage

`run_e2e.sh` executes **only the automated phases** — `phases/*.sh` and
`phases/*.py`, i.e. verification (10–12) plus cleanup (99). The seeding and
simulation stages (01–09) are **Claude-agent-driven** (see "Phases" below)
and must already have populated the sandbox. Pointing the harness at a fresh
or nonexistent sandbox (the default when `EDPA_E2E_SANDBOX_DIR` is unset —
a new `RUN_TAG` is generated) aborts at phase 10 with
`AssertionError: Expected 10 results files, got 0`.

```bash
# Verify an existing, seeded sandbox
EDPA_E2E_SANDBOX_DIR=/tmp/edpa-e2e-<run-tag> bash tests/e2e_v2_full/run_e2e.sh

# Dry-run — print the phase plan, execute nothing
EDPA_E2E_DRY_RUN=1 bash tests/e2e_v2_full/run_e2e.sh

# Keep the sandbox dir for post-mortem inspection after verification
EDPA_E2E_KEEP_SANDBOX=1 EDPA_E2E_SANDBOX_DIR=/tmp/edpa-e2e-<run-tag> \
  bash tests/e2e_v2_full/run_e2e.sh

# Inspect available options
bash tests/e2e_v2_full/run_e2e.sh --help
```

The verification phases resolve the sandbox from `EDPA_E2E_SANDBOX_DIR`, with
a fallback to the run tag recorded in `/tmp/edpa-e2e-current-run-tag` (written
by the coordinator pre-flight of an agent-driven run).

The harness discovers files under `tests/e2e_v2_full/phases/` and runs them in
lexicographic order; only `.sh` (bash) and `.py` (python3) files are executed —
the `.md` files alongside them are run logs, not scripts. Missing phases are
reported as `[SKIP]` without failing the run.

## Phases

Two kinds of entries live in `phases/`:

- **Agent-driven stages (01–09)** — seeding and simulation performed by
  Claude agents following the fixture plans in `fixtures/`
  (`backlog_plan.yaml`, `work_plan.yaml`, `iterations.yaml`, `people.yaml`,
  `edpa.yaml`). The `phases/0*.md` files are **run logs** of the completed
  2026-05-27 wave-orchestrated run (run tag `20260527-181051-2c56a6a0`), kept
  as the reference record of how the sandbox was built — `run_e2e.sh` skips
  them (not `.sh`/`.py`). Re-running these stages means driving a Claude
  session through the same playbook, not executing a script.
- **Automated phases (10–12, 99)** — re-runnable verification scripts plus
  cleanup, executed by `run_e2e.sh`. Phases 10–12 also have `.md` twins:
  run logs from the same 2026-05-27 run.

| Stage | File(s)                            | Kind        | Purpose                                                             |
|-------|------------------------------------|-------------|----------------------------------------------------------------------|
| 01    | `01_install_seed.md`               | agent (log) | Install EDPA into the sandbox, seed config, install git hooks        |
| 04    | `04_seed_backlog_iterations.md`    | agent (log) | Plant backlog + iteration files from `fixtures/backlog_plan.yaml`    |
| 07    | `07_simulate_pi1.md`               | agent (log) | Simulate PI-1 work — branches, commits, PRs (`real` CI signals)      |
| 08    | `08_simulate_pi2.md`               | agent (log) | Simulate PI-2 work (`synthetic` CI signals)                          |
| 09    | `09_close_engine_reports.md`       | agent (log) | Close all 10 iterations; run engine, reports, snapshots              |
| 10    | `10_verify_invariants.py` (+ log)  | automated   | Engine invariants + snapshot signature verification (read-only)      |
| 11    | `11_verify_reports.py` (+ log)     | automated   | Timesheets, JSON results, frozen snapshots, XLSX exports present + consistent |
| 12    | `12_verify_backlog.py` (+ log)     | automated   | Backlog + iteration end-state (item/status distribution, `validate`, board) |
| 99    | `99_cleanup.sh`                    | automated   | Archive sandbox repo; remove local sandbox unless `KEEP_SANDBOX=1`   |

## Cleanup

The harness uses `gh repo archive` rather than `gh repo delete`, because
the default token typically does not have the `delete_repo` scope.
Archived repos remain visible on GitHub but cannot be pushed to or
forked. To fully delete them, run manually with a token that has the
`delete_repo` scope:

```bash
gh repo delete "${EDPA_E2E_GH_OWNER}/edpa-e2e-${RUN_TAG}" --yes
```

The local sandbox under `${EDPA_E2E_SANDBOX_DIR}` is removed at the end
of a successful run unless `EDPA_E2E_KEEP_SANDBOX=1`.

## Limits and caveats

- **PI-1 with `real` CI** spends most wall-clock time waiting for GitHub
  Actions. Expect ~5 min per PR; PI-1 generates ~12-20 PRs (depends on
  story count). Plan for ~60-90 min wall-clock in `real` mode.
- **PI-2 with `synthetic` CI** completes in seconds — useful for asserting
  multi-PI report aggregation without re-paying the GitHub Action cost.
- **Hybrid mode is the recommended default** — it proves the CI pipeline
  end-to-end at least once per run while keeping total runtime under
  ~30 min.
- **The test is destructive within its sandbox** — both the GitHub repo
  (`${GH_OWNER}/edpa-e2e-${RUN_TAG}`) and the local `${SANDBOX_DIR}` are
  freshly created and torn down per run. `RUN_TAG` ensures no two runs
  collide.
- **No emoji or interactive prompts.** The harness exits non-zero on the
  first phase failure; rerun a single phase by deleting downstream
  artifacts and re-invoking just that phase's script directly.
