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

- `real` — every PR waits for the actual GitHub Action to complete (~5 min
  per PR). Highest fidelity, slowest. Use this for release verification.
- `synthetic` — PR signals are injected directly into the local evidence
  store, bypassing GitHub Actions. Fast, but does not exercise the CI
  workflow itself.
- `hybrid` (default) — PI-1 uses the `real` path (one full PR-signal
  round-trip per PR) to prove the CI workflow works; PI-2 switches to
  `synthetic` injection to keep total runtime reasonable.

## Usage

```bash
# Default run (auto-generated RUN_TAG, /tmp sandbox, hybrid CI)
bash tests/e2e_v2_full/run_e2e.sh

# Dry-run — print the phase plan, execute nothing
EDPA_E2E_DRY_RUN=1 bash tests/e2e_v2_full/run_e2e.sh

# Synthetic-only (fastest; no GitHub Action wait)
EDPA_E2E_CI_MODE=synthetic bash tests/e2e_v2_full/run_e2e.sh

# Keep the sandbox dir for post-mortem inspection
EDPA_E2E_KEEP_SANDBOX=1 bash tests/e2e_v2_full/run_e2e.sh

# Inspect available options
bash tests/e2e_v2_full/run_e2e.sh --help
```

The harness sources phase scripts from `tests/e2e_v2_full/phases/` and
executes them in lexicographic order. Each phase is either a `.sh`
(bash) or `.py` (python3) file. Missing phases are reported as `[SKIP]`
without failing the run.

## Phases

| Phase | Purpose                                                                                |
|-------|----------------------------------------------------------------------------------------|
| 01    | Preflight — check `gh auth`, python version, git version, free disk                    |
| 02    | Sandbox prep — create `${EDPA_E2E_SANDBOX_DIR}`, init git, write `README.md`           |
| 03    | Install EDPA via local `install.sh` (`EDPA_FORCE_INSTALL=1`)                           |
| 04    | Seed people, edpa.yaml, heuristics; install git hooks                                  |
| 05    | Create GitHub sandbox repo (`${GH_OWNER}/edpa-e2e-${RUN_TAG}`); push initial commit    |
| 06    | Run `/edpa:setup` flow (project_setup.py); persist `field_ids` + `issue_map`           |
| 10    | PI-1 backlog plant — initiatives, epics, features, stories via `/edpa:add` + MCP        |
| 11    | PI-1 iteration 1 — work simulation (4 people, branches, commits, PRs, reviews)         |
| 12    | PI-1 iteration 2 — work simulation                                                     |
| 13    | PI-1 iteration 3 — work simulation                                                     |
| 14    | PI-1 iteration 4 — work simulation                                                     |
| 15    | PI-1 iteration 5 — work simulation + PI-1 close                                        |
| 16    | PI-1 reports — timesheets, item costs, snapshot, XLSX export                           |
| 17    | PI-1 invariants — assert `All invariants passed: YES`, capacity sums match             |
| 20    | PI-2 backlog plant — next-PI items, parent linkage to PI-1 carry-overs                 |
| 21    | PI-2 iteration 1 — work simulation                                                     |
| 22    | PI-2 iteration 2 — work simulation                                                     |
| 23    | PI-2 iteration 3 — work simulation                                                     |
| 24    | PI-2 iteration 4 — work simulation                                                     |
| 25    | PI-2 iteration 5 — work simulation + PI-2 close                                        |
| 26    | PI-2 reports — timesheets, item costs, snapshot, XLSX export                           |
| 27    | PI-2 invariants — assert `All invariants passed: YES`, capacity sums match             |
| 90    | Cross-PI checks — velocity report, flow metrics, calibration readiness                 |
| 95    | Snapshot diff — confirm PI-1 snapshot still verifies (hash chain)                      |
| 99    | Cleanup — archive sandbox repo, remove local sandbox unless `KEEP_SANDBOX=1`           |

Numbered gaps (`07–09`, `18–19`, `28–89`, `91–94`, `96–98`) are reserved
for future phases. Missing phase files are silently skipped, so the
plan above can grow without breaking older runners.

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
