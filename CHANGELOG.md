# Changelog

## Unreleased

## 1.4.0-beta — 2026-05-05

Minor release. **Default cadence changes** for freshly initialized
projects only — existing `.edpa/config/people.yaml` files keep their
explicit `iteration_weeks` / `pi_weeks` settings; no migration is
required. The release also bundles every `## Unreleased` change since
1.3.2-beta (engine + plugin-wide hardening, MCP integration tests,
`sync add-iteration`, MCP load_yaml LRU cache, README walkthrough,
testing-strategy appendix).

### Changed (BREAKING for fresh installs only)
- **Default cadence is now AI-native: 1-week iterations, 5-week PI
  (4 delivery + 1 IP).** The IP iteration absorbs leftover work,
  debt, prioritization, and PI planning itself — compressible to a
  single day with AI-assisted ceremonies. Classic SAFe (2-week
  iteration / 10-week PI) is still fully supported; set
  `cadence.iteration_weeks: 2` and `cadence.pi_weeks: 10` in
  `people.yaml` to opt out. Default `capacity_per_iteration` values
  in the template halved accordingly (FTE × 40 for 1-week instead
  of FTE × 80 for 2-week).
- `project_setup.py` writes `pis[0].iteration_weeks: 1` for new
  setups (was `2`). Existing projects re-running setup keep their
  explicit value.
- Documentation updated: `docs/playbook.md`, `docs/quick-start.md`,
  `README.md` walkthrough show 1-week defaults with re-captured
  engine output (60h team total instead of 120h). The
  `docs/examples/capacity-small-team.yaml` reference is preserved
  as a classic-SAFe variant with a pointer to the new default.
- `mcp_server.py` legacy fallbacks (`iteration_weeks: 2` when the
  field is missing entirely from a v0.x bundled config) stay at
  `2` — they protect pre-1.0 installs from invariant breaks.

### Why this default

5-week PI matches AI-native team velocity better than 10 weeks. A
PM running CW analysis weekly produces tighter feedback loops than
biweekly; the gates allocation model (default since 1.1) was
already calibrated for high-frequency status transitions. The
classic-SAFe default predates EDPA's gates mode and the AI Studio
context — both push toward shorter cycles.



### Documentation
- `README.md` — replaced the terse 5-step Quick Start with a
  guided "First 5 minutes" walkthrough: install → edit `people.yaml`
  → seed a toy iteration + two stories → close iteration → generate
  timesheets. Every code block is copy-pasteable; every output
  block is real (captured from a fresh `/tmp` install end-to-end,
  not hand-edited). Reads like a tutorial; the older "see RUNBOOK.md
  for X" pattern still works as the next-step list at the bottom.
  Acceptance criterion from `TODO.md`: someone can read just the
  walkthrough and produce a working toy iteration on a fresh repo.
  Verified.

### Performance
- `mcp_server.load_yaml` — bounded LRU cache keyed by `(path,
  st_mtime_ns)`. Cap: 64 entries. Repeated MCP `tools/call`
  invocations against an unchanged `.edpa/backlog/` no longer
  re-parse every YAML file from scratch; touching a file
  invalidates only that entry. Measured on a 100-item backlog:
  cold 28.17 ms/call → warm 0.56 ms/call (≈ 50× speedup). The hot
  path inside a single Claude Code session — "what's in PI-X?"
  followed by repeated drill-down questions — was the explicit
  motivation. 6 new tests cover hit/miss, mtime invalidation,
  disappeared-file recovery, bounded eviction, LRU recency, and
  end-to-end handler benefit.

### Added
- `tests/test_mcp_integration.py` — 16 live JSON-RPC stdio roundtrip
  tests. Spawns `mcp_server.py` as a subprocess, drives the wire
  protocol Claude Code / Cursor / Codex use, asserts on serverInfo
  version, tool advertisement (5 tools), tool dispatch (status,
  item lookup, path-traversal rejection across 7 bad inputs), and
  stderr log discipline (INFO call_tool / WARNING rejected). Skipped
  on Windows and when `mcp` is missing. Default test marker — runs
  in the normal `pytest tests/` suite. Catches regressions where
  `Server(name, version=…)` upstream signature drifts, where the
  plugin path resolution breaks, or where the server crashes during
  initialize handshake.
- 155 tests pass (was 139 before this entry); 6 e2e deselected.
- `sync add-iteration <ID>` subcommand. After setup, when a new
  iteration YAML lands in `.edpa/iterations/`, the GitHub Project
  `Iteration` SINGLE_SELECT field doesn't know about it yet — `sync
  push` then fails with `no option_id for 'Iteration':'<ID>'`. The
  new subcommand fetches the field's current options, merges in the
  new one, calls `updateProjectV2Field` GraphQL mutation, and
  persists the new option_id back to `edpa.yaml`. Drops the `TBD`
  placeholder automatically when the first real iteration is added.
  Idempotent. `--color` (default GRAY), `--dry-run`. Verified live
  against `technomaton/edpa-e2e-test`: TBD purged, push of a story
  with `iteration: PI-2026-1.5` succeeded immediately after.
- Docs/RUNBOOK section updated.

### Changed (plugin-wide hardening pass — backport of v1.3 MCP rigor)
- `engine.py`, `sync.py`, `evaluate_cw.py`, and `pi_close.py` —
  `load_yaml` / `load_json` helpers now return `None` on failure
  instead of letting `OSError` / `yaml.YAMLError` /
  `json.JSONDecodeError` bubble up unhandled. Errors print to stderr
  so stdout (which downstream tools may parse) stays clean. Callers
  that already wrapped these in `try/except Exception` now check for
  `None` directly — same behavior, less catch-all.
- Replaced two `except Exception` blocks in `engine.py` with specific
  exception types. Same hardening pass MCP got in v1.3 —
  `KeyboardInterrupt` and `SystemExit` now propagate as they should.
- `validate_on_save.sh` hook — removed the `2>&1` stderr→stdout
  redirect that was making validation errors render as if they were
  tool output rather than diagnostics. Errors now stay on stderr;
  Claude Code shows them as diagnostics. Internal hook errors also
  surface on stderr now (were silently swallowed).
- Audit passes left two `except Exception` blocks in place:
  `mcp_server.call_tool` (intentional crash-safety wrapper around
  every JSON-RPC dispatch) and four in `create_project_views.py`
  (Playwright async patterns where any failure → fall through is
  the right shape). Both documented in code.
- 139/139 tests still pass.

## 1.3.2-beta — 2026-05-05

Surface fixes for `edpa_status` post-setup output. Caught in the
synthetic skill-driven E2E run as findings F3 and F4
(see `docs/E2E-SKILLS-TEST-PLAN.md`). Tag-only patch — engine,
sync, and reports are byte-identical.

### Fixed
- **F3** — `mcp_server._handle_status` read `project.name` from
  `people.yaml`, which has never had a `project:` section in any
  shipped template. Result: `edpa_status` always reported
  `"project": "unknown"` regardless of what `/edpa:setup` was given.
  Now reads from `edpa.yaml` (where the setting actually lives) and
  falls back to `people.yaml` only for legacy v0.x bundled configs.
- **F4** — `project_setup.py` persisted `sync.field_ids` and
  `sync.option_ids` after a successful setup but never wrote the
  matching `pis[]` array to `edpa.yaml`. Result: `edpa_status` and
  `edpa_iterations` reported `iterations_total: 0` immediately after
  setup, even though `.edpa/iterations/*.yaml` files were on disk
  the whole time. Setup now derives `pis[]` from those YAML files
  and writes them on the same persistence pass.
- `project_setup.py` also writes `project.name` from the
  `--project-title` argument when the template placeholder is still
  in place. Respects a name the user has set by hand.

### Verified live
Fresh setup → MCP `edpa_status` returns the actual project name,
`current_pi`, `iterations_total > 0`, and `active_iteration` — no
"unknown" fallbacks.

## 1.3.1-beta — 2026-05-05

Installer hot-fix on top of [v1.3.0-beta](https://github.com/technomaton/edpa/releases/tag/v1.3.0-beta).
Tag-only patch — engine, sync, MCP server, and reports are byte-identical.
Only `install.sh` is materially different.

### Fixed
- `install.sh` now installs the `mcp` Python SDK alongside `pyyaml`. Without
  this the MCP server (`plugin/edpa/scripts/mcp_server.py`) failed to start
  on a fresh `curl install.sh | sh` against the system python. The graceful
  import error in v1.3.0-beta said "ERROR: 'mcp' package required" and
  exited cleanly, but Claude Code clients silently fell back to `Bash + grep`
  because the MCP tools never advertised. Caught in the synthetic
  skill-driven E2E run on 2026-05-05; finding F1 in `docs/E2E-SKILLS-TEST-PLAN.md`.
- `install.sh` also installs `openpyxl` so the engine's Excel export and the
  `/edpa:reports` skill produce `item-costs.xlsx` and `pi-summary.xlsx`
  out of the box. Without it the engine printed "Excel export skipped" on
  every iteration close and reports lost the spreadsheet variant.

### Notes
- Both packages mirror the existing pattern: try `pip3 install ... --break-system-packages`,
  fall back to `pip3 install ...` for venv'd environments. No new system
  prerequisites — same Python 3.10+, same pip3 expectation.
- `web/public/install.sh` re-synced with the repo-root version (tracked
  drift from 2026-03-28 was fixed in 1.2.1; this release keeps them
  in lockstep).

## 1.3.0-beta — 2026-05-05

Production-quality MCP server. The server existed since 1.0.0-beta as a
prototype but had a relative plugin path, no input validation, no logging,
and unversioned identity. v1.3 makes it usable as a real Claude Code /
Cursor / Codex CLI tool surface against `.edpa/` data.

See `docs/mcp.md` for the full reference.

### Added
- `docs/mcp.md` — operator and integrator guide for the MCP server
  (tools, resources, env vars, security model, troubleshooting).
- `tests/test_mcp_server.py` grew from 36 to 48 tests:
  `TestItemIdValidation`, `TestCallToolErrorHandling`,
  `TestServerIdentity`, `TestLoggingSetup`. Live `subprocess` smoke
  test against the JSON-RPC stdio transport verified separately.

### Changed
- `plugin/.mcp.json` registers the EDPA server via
  `${CLAUDE_PLUGIN_ROOT}/edpa/scripts/mcp_server.py`. Previously a
  relative `.claude/edpa/scripts/mcp_server.py` path broke whenever
  the MCP client launched from a subdirectory.
- `plugin/.mcp.json` reads `GITHUB_PERSONAL_ACCESS_TOKEN` from the
  environment instead of shipping a literal empty string.
- `plugin/edpa/scripts/mcp_server.py`:
  - Server identity now carries the plugin version
    (`Server("edpa", version=…)`) read from `plugin.json`. MCP clients
    surface this in their connection panel.
  - Stderr `logging.Logger` named `edpa.mcp`; every `call_tool`
    invocation logged with arguments. `EDPA_LOG_LEVEL` and
    `EDPA_LOG_FILE` env vars control verbosity / mirroring. stdout
    stays clean for JSON-RPC.
  - `mcp` and `pyyaml` import errors exit with a one-line install
    hint instead of a stack trace.
  - `load_yaml` catches only `yaml.YAMLError` / `OSError`; bare
    `except` removed so `KeyboardInterrupt` propagates.
  - `call_tool` wraps every dispatch in a `try` so handler bugs
    return a `TextContent` `ERROR: internal error ...` rather than
    closing the JSON-RPC session.

### Fixed
- `edpa_item` accepted any string. A request like
  `{"item_id": "../etc/passwd"}` would skip the prefix lookup
  (returning "not found") rather than rejecting at the validator.
  Now `item_id` must match `^[A-Z]-\d{1,9}$`; anything else returns
  `ERROR: invalid item_id ...` before touching the filesystem.

### Dev tooling (carried from Unreleased)
- `requirements-dev.txt` now uses `-r requirements.txt` and adds
  `jsonschema` + `openpyxl` so a fresh `pip install -r
  requirements-dev.txt` runs the full test suite instead of
  silently skipping the schema-strictness and MCP groups.
- `pytest tests/ -m "not e2e"`: **139 passed**, 0 skipped, 0 errors
  (was 84 passed + 7 skipped + 1 collection error in 1.2.1-beta).
  The 6 e2e tests stay opt-in (real GitHub API, destructive
  to sandbox).
- `test_consistency.test_requirements_exist` now accepts a
  transitive `-r requirements.txt` include instead of demanding a
  literal `pyyaml` line in every requirements file.

## 1.2.1-beta — 2026-05-05

Installer hot-fix on top of 1.1.0-beta. No engine, sync, or report
changes — only `install.sh` is materially different.

### Fixed
- `install.sh` now seeds `.edpa/config/edpa.yaml` from
  `project.yaml.tmpl` alongside `heuristics.yaml` and `people.yaml`.
  Previously the template was bundled in `plugin/edpa/templates/` but
  never copied, so `engine --status` on a fresh install reported
  `✗ edpa.yaml not found` until `/edpa:setup` ran. No functional
  block — `setup` would still create the file — just a confusing
  onboarding hint.
- `install.sh` resolves the latest release with prerelease awareness.
  GitHub's `/releases/latest` API and `gh release download` without
  an explicit tag both skip prereleases, so while every release is
  `-beta` they returned 404 and the installer silently fell back to
  a `main` branch clone. The gh path now uses `gh release list
  --limit 1` to find the most recent tag (any release type); the
  curl path uses `/releases` (plural) and picks the first matching
  asset.

## 1.1.0-beta — 2026-05-05

### Changed (BREAKING for fresh installs only)
- **`--mode gates` is now the default** for `engine.py` and the
  `calculation_mode` field in `project.yaml.tmpl`. Existing
  `.edpa/config/edpa.yaml` files keep their explicit setting; only
  newly initialized projects pick up the new default. To stay on
  simple, set `governance.calculation_mode: simple` in
  `.edpa/config/edpa.yaml` or pass `--mode simple` on the command
  line.
- Validated against `technomaton/edpa-simulation-gates` (8 iterations,
  6-person virtual team, 156 git transitions, 30 Monte Carlo runs):
  avg MAD 7.8 % vs ground truth, 0.3 percentage points spread under
  ±20 % CW perturbation. See that repo's `reports/RESULTS.md` for
  the full validation report.

### Added
- `sync setup-refresh` subcommand — re-discovers field IDs, option
  IDs, and the issue map from an existing GitHub Project. Useful
  when checking out the project on a new machine or after manual
  GitHub edits.
- `tests/test_e2e_sync.py` — five end-to-end tests against a real
  GitHub sandbox repo (opt-in via `pytest -m e2e`). Covers the full
  chain: project setup → push creates issues → manual GitHub UI
  status change → pull updates YAML + commits → engine
  `--mode gates` reads the transition.
- `docs/RUNBOOK.md` — operational runbook for every `/edpa:*` slash
  command with prerequisites, expected output, common failure modes,
  and a 5-minute end-to-end smoke test.

### Fixed
- `project_setup.py` now persists `field_ids`, `option_ids`, and an
  `issue_map.yaml` so `sync push` can target real GitHub fields.
  Previously `gh project item-edit` was called with empty IDs.
- `sync push` works against a real GitHub Project: creates missing
  issues, sets fields with correct typing (NUMBER vs SINGLE_SELECT),
  mirrors status `→ Done` to `gh issue close`, and links parent/child
  via `addSubIssue`. Previously `push` was only validated against
  mock data.
- `sync pull` reads per-level typed status fields
  (Initiative/Epic/Feature/Story Status) instead of GitHub's default
  `Status` field, so SAFe workflow transitions actually round-trip.
- `project_setup.py` always creates the `Iteration` field (with a
  `TBD` placeholder option when no iteration YAMLs exist yet). Without
  this, every subsequent `sync push` of an item with `iteration:` set
  failed with `no field_id for 'Iteration'` and there was no recovery
  path short of recreating the project.
- `sync.compute_diff` no longer wipes a local `iteration:` value when
  the GitHub Project has no Iteration field or no value for the item.
  Previously every pull cleared local iteration tags whenever the
  field was lazily missing on GH.

## 1.0.0-beta — 2026-03-29

First public beta. Plugin-first distribution, restructured directories.

### Breaking Changes (vs internal v2.x)
- Installation via `curl -fsSL https://edpa.technomaton.com/install.sh | sh`
- All scripts moved: `scripts/edpa_engine.py` -> `.claude/edpa/scripts/engine.py`
- All config moved: `config/capacity.yaml` -> `.edpa/config/capacity.yaml`
- Heuristics renamed: `config/cw_heuristics.yaml` -> `.edpa/config/heuristics.yaml`
- Reports, snapshots, data moved under `.edpa/` prefix
- Claude Code skills/commands moved from `claude-code/` to `.claude/` (standard plugin location)

### Added
- `install.sh` — shell installer (detects `.claude/`, downloads release, copies plugin)
- `plugin/` directory — single source of truth for installable EDPA plugin
- **edpa-sync** skill — 5th skill for GitHub Projects <-> Git backlog synchronization
- `/edpa sync` command
- `plugin/.claude-plugin/plugin.json` — plugin manifest

### Changed
- Source reorganized: `plugin/` contains all installable assets (scripts, templates, workflows, skills, commands)
- `.edpa/` restructured: `config/`, `backlog/`, `reports/`, `snapshots/`, `data/`
- README, SETUP, CONTRIBUTING updated for new paths and installation method

### Removed
- GitHub template approach (`gh repo create --template`)
- `config/*.tmpl` files at repo root (moved to `plugin/edpa/templates/`)
- `scripts/` directory at repo root (moved to `plugin/edpa/scripts/`)

### Migration
| Old path | New path |
|----------|----------|
| `scripts/edpa_engine.py` | `.claude/edpa/scripts/engine.py` |
| `scripts/evaluate_cw.py` | `.claude/edpa/scripts/evaluate_cw.py` |
| `scripts/edpa_sync.py` | `.claude/edpa/scripts/sync.py` |
| `scripts/edpa_backlog.py` | `.claude/edpa/scripts/backlog.py` |
| `scripts/edpa_issue_types.py` | `.claude/edpa/scripts/issue_types.py` |
| `scripts/edpa_project_setup.py` | `.claude/edpa/scripts/project_setup.py` |
| `config/capacity.yaml` | `.edpa/config/capacity.yaml` |
| `config/cw_heuristics.yaml` | `.edpa/config/heuristics.yaml` |
| `config/project.yaml` | `.edpa/config/project.yaml` |
| `reports/` | `.edpa/reports/` |
| `snapshots/` | `.edpa/snapshots/` |
| `data/` | `.edpa/data/` |

## 2.0.0 — 2026-03-25

Multi-contract engine + role_overrides fix. **BREAKING CHANGE.**

### Breaking Changes
- Engine now applies `role_overrides` from `cw_heuristics.yaml` (was ignored in v1.x)
- CW values change for non-Dev roles: Arch reviewer 0.25→0.30, PM consulted 0.15→0.20, BO consulted 0.15→0.30
- Demo data: Alice split into alice-arch (40h) + alice-pm (20h)
- Person interface: new optional fields (`contract`, `evidence_scope`, `evidence_default`)

### Added
- `evidence_scope` per contract — route Git signals to correct contract via fnmatch patterns
- Multi-contract demo in `--demo` mode (Alice-Arch + Alice-PM)
- 3 new tests: `test_multi_contract_isolation`, `test_role_overrides_applied`, `test_evidence_scope_routing`
- `docs/migration-v2.md` — migration guide v1.x → v2.0
- TypeScript Person interface: `contract?`, `evidence_scope?`, `evidence_default?`

### Fixed
- **CRITICAL:** `role_overrides` from Monte Carlo calibration now applied in `compute_cw()`
  (was declared in config but ignored by engine since v1.0)

## 1.2.0 — 2026-03-25

Multi-role support + production readiness audit.

### Added
- Multi-role/multi-contract support: one person can have multiple entries with different roles, FTEs, and capacities (e.g., `urbanek-arch` + `urbanek-pm`)
- File-per-item backlog structure (`.edpa/initiatives/`, `epics/`, `features/`, `stories/`)
- `edpa_backlog.py add` command for creating new items from CLI
- `requirements.txt` (pyyaml) and `requirements-dev.txt` (pytest)
- Complete E2E playbook (`docs/playbook.md`, 1200+ lines)
- Production readiness audit fixes (score 73→90+)

### Changed
- Backlog: monolithic `backlog.yaml` → individual YAML files per item
- `.edpa/config.yaml`: hardcoded org → placeholder values
- Plugin version: 2.2.0 → 1.1.0 → 1.2.0
- Evidence principle documented: all commits are delivery evidence (no filtering)

### Removed
- `web/dist/` and `web/.vercel/` from git tracking
- Hardcoded GitHub Issue Type ID fallback

### Fixed
- `.gitignore`: added dist/, .vercel/, .env*
- Relative paths in Claude Code skill docs

## 1.1.0 — 2026-03-22

Migration from GitHub labels to native Issue Types. Branch `v1` preserves v1.0.

### Breaking Changes
- Work items now use **native GitHub Issue Types** instead of labels
- `edpa_project_setup.py` no longer creates Epic/Feature/Story/Initiative labels
- Project view filters changed from `label:Epic` to `type:Epic`
- Custom field "Issue Type" (SINGLE_SELECT) removed from Projects — redundant with native types

### Added
- `scripts/edpa_issue_types.py` — CLI for org-level Issue Type management (list, setup, assign, migrate)
- Native Issue Types on org: Initiative (PINK), Epic (PURPLE), Feature (BLUE), Story (GREEN), Defect (RED), Task (YELLOW)
- Enabler as label (SAFe classification: Business vs Enabler Epic/Feature/Story)
- `edpa_issue_types.py migrate` — bulk migration from labels to native types on existing repos
- `issue_types` section in `config/project.yaml.tmpl` and `.edpa/config.yaml`

### Changed
- `edpa_project_setup.py` — Issue creation uses GraphQL `updateIssueIssueType` instead of `--label`
- `edpa_sync.py` — `parse_gh_item_type()` reads native `issueType.name` first, labels as fallback
- `edpa_project_views.py` — view filters: `type:Epic`, `type:Feature`, `type:Story`
- `create_project_views.py` — same filter migration
- Default Bug type renamed to Defect via `updateIssueType` mutation
- Default Feature type description updated: "Musí se vejít do Planning Intervalu"
- Documentation: `github-project-setup.md`, `github-setup.md`, methodology pages (CS + EN)

### Removed
- Label creation for Initiative, Epic, Feature, Story, Bug in project setup
- Custom field "Issue Type" from GitHub Projects (native types replace it)

## 1.0.0 — 2026-03-21

EDPA v1.0.0 — first public release with calibrated CW heuristics.

### Added
- Public website at [edpa.technomaton.com](https://edpa.technomaton.com) (Astro, 14 pages, CS + EN)
- Interactive dashboard (generic + kashealth case study)
- 20-slide presentation (generic + kashealth)
- Full methodology documentation with sticky sidebar TOC
- Evaluation page: 302 verification checks (102 scenarios × per-person)
- Monte Carlo CW calibration (1000 scenarios, 68k records, p<0.001)
- Calibrated `role_overrides` in `cw_heuristics.yaml.tmpl`
- Git-native backlog management (`.edpa/backlog.yaml` + CLI)
- GitHub Projects ↔ Git sync (`edpa_sync.py` + GitHub Actions)
- SAFe 6 Epic Hypothesis Statements in backlog
- Full simulation repo ([edpa-simulation](https://github.com/technomaton/edpa-simulation))
- Simulation: 2 PIs, 10 iterations, 510 commits, realistic delivery variance (57-118%)
- Auto-calibration with Karpathy loop (MAD reduction 19.2%)
- Mobile hamburger menu, back-to-top button, ARIA accessibility
- Search/filter on evaluation page
- Responsive dashboard tables
- Vercel Analytics integration

### Changed
- Version: v2.2 → v1.0.0 across all files
- CW heuristics calibrated from Monte Carlo: reviewer 0.25→0.30, consulted 0.15→0.25
- Role-specific overrides: BO consulted 0.30, PM consulted 0.20, Arch reviewer 0.30
- TECHNOMATON Group → TECHNOMATON with link to technomaton.com
- Font sizes increased across website and presentation

## 0.0.1 — 2026-03-21

Initial open-source release as standalone repository (extracted from TECHNOMATON Hub).

### Added
- Standalone Python engine (`scripts/edpa_engine.py`) with `--demo` mode
- Claude Code skills: edpa-setup, edpa-engine, edpa-reports, edpa-autocalib
- Claude Code commands: `/edpa setup`, `/edpa close-iteration`, `/edpa reports`, `/edpa calibrate`
- GitHub Actions: branch naming check, iteration close workflow
- GitHub issue templates: Epic, Feature, Story
- Configuration templates: capacity.yaml, cw_heuristics.yaml, project.yaml
- CW evaluator for auto-calibration (`scripts/evaluate_cw.py`)
- Invariant validation tests (10 tests)
- Full documentation (11 docs)

### Origin
- Extracted from [TECHNOMATON Hub](https://github.com/technomaton/technomaton-hub) `packs/tm-governance`
