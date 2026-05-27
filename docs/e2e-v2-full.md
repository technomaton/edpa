# EDPA V2 — Full End-to-End Test

Comprehensive end-to-end test of EDPA V2 covering install → setup → backlog seeding → 2 PIs × 5 iterations of simulated work → engine + reports → verification.

## Prerequisites

- Python 3.10+ with `pyyaml`, `ruamel.yaml`, `openpyxl` (for XLSX export)
- `gh` CLI authenticated with scopes: `admin:org, repo, workflow, project` (or `delete_repo` if you want true delete instead of archive)
- Write access to `technomaton` GitHub org (or override `EDPA_E2E_GH_OWNER`)
- Local EDPA repo with `install.sh` accessible

## Running

```bash
# All defaults: hybrid CI mode, archive cleanup, fresh RUN_TAG per invocation
bash tests/e2e_v2_full/run_e2e.sh

# Keep sandbox local for inspection after test
EDPA_E2E_KEEP_SANDBOX=1 bash tests/e2e_v2_full/run_e2e.sh

# Synthetic CI mode (skip real workflow polling, ~5x faster)
EDPA_E2E_CI_MODE=synthetic bash tests/e2e_v2_full/run_e2e.sh

# Dry run (print phase plan without executing)
EDPA_E2E_DRY_RUN=1 bash tests/e2e_v2_full/run_e2e.sh
```

## Phases

The orchestrator runs `tests/e2e_v2_full/phases/*.{sh,py}` lexicographically:

| Phase | Purpose |
|-------|---------|
| 01 | Install + seed config (run `install.sh`, seed `.edpa/config/` from fixtures) |
| 04 | Seed backlog + iterations (33 items + 10 iterations via `backlog.py` + direct YAML) |
| 07 | Simulate PI-1 (real CI workflow polling) — 14 items, 14 PRs, ~13 min |
| 08 | Simulate PI-2 (synthetic CI injection) — 10 items, 10 PRs, ~5 min |
| 09 | Close iterations + run engine + generate reports |
| 10 | Verify invariants (all_invariants_passed, snapshot signatures, capacity match) |
| 11 | Verify reports + GH state (timesheets, XLSX, PI summaries, merged PRs, CI runs) |
| 12 | Verify backlog state + generate board snapshot |
| 99 | Cleanup — archive sandbox repo, remove local `/tmp` dir (unless `EDPA_E2E_KEEP_SANDBOX=1`) |

## Known limitations

1. **MCP tools are host-scoped** — `mcp__plugin_edpa_edpa__*` resolve `.edpa/` from the Claude session's host project, not the sandbox cwd. Tests fall back to direct script invocation in the sandbox (`backlog.py`, `engine.py`, `reports.py`). See `docs/mcp.md` "Known limitation: single-project scope per session".
2. **PR reviews + comments fire as the authenticated `gh` user** — multi-person attribution is verified via `commit_author` signals (GIT_AUTHOR_EMAIL override), not PR-thread signals. The PR-thread attribution math is validated separately in `tests/test_e2e_v2_ci_materialization.py` with synthetic JSON events.
3. **Cleanup uses `gh repo archive`** unless your token has `delete_repo` scope (default token lacks it).
4. **`Skill` tool returns instructions text, not execution** — when a subagent invokes a skill via the `Skill` tool, it receives the SKILL.md contents back, not the side-effects of running the skill. The subagent must then **follow** the returned instructions as if they were a user prompt (call Bash, MCP, etc., per the skill's steps). Skill tool is a prompt-templating mechanism, not a function call. Test driver prompts must say "after Skill call, follow the returned instructions; do not treat the response as documentation."

## Findings from initial run (2026-05-27)

- All 10 iterations closed with `all_invariants_passed=true`; total team derived = 560h (PI-1: 240h, PI-2: 320h)
- All 12 snapshots `frozen=true` with valid `payload_signature` (sha256 recomputes byte-for-byte)
- 24 merged sandbox PRs (14 PI-1 + 10 PI-2); 23/24 CI workflow runs `success`
- **REAL V2 BUG SURFACED:** `validate_syntax.py::PORTFOLIO_STATUSES` set excludes `Validating` for Initiative/Epic, but gate transition design (per work_plan.yaml) puts I-1/E-1/E-2 into `Validating` at end-of-PI. `backlog.py validate` exits 1 as a result. **Fixed:** work_plan.yaml now uses portfolio ladder (`Implementing` instead of `Validating` for I/E). The schema stays as-is — portfolio items skip the QA gate by design.
- **CI gap finding:** `evidence[]` is materialized by `sync_pr_contributions.py`, but `contributors[]` is not auto-rebuilt; engine v1.11+ requires `contributors[]`. **Fixed:** close-iteration Stage 2b (`detect_contributors.py --all-items`) is now documented as REQUIRED (not optional) with explicit warning about silent 0h failure mode.
- **`backlog.py add` limit:** CLI accepted only `{Initiative, Epic, Feature, Story}` while MCP server supported all 7 types (Defect/Event/Risk via TYPE_DIRS). **Fixed:** CLI choices extended to match MCP surface.

## Troubleshooting

- **Stuck CI polling:** `gh run list --repo <sandbox-repo> --workflow=edpa-contribution-sync.yml --limit 5` — manual inspection
- **Cleanup token scope error:** `gh auth refresh -h github.com -s delete_repo` to add delete capability (then re-run cleanup)
- **Wave B mid-run failure:** sandbox state is persisted in `/tmp` + GitHub; manual `99_cleanup.sh` resets, then re-run from Wave A merge
