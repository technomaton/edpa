# Changelog

## Unreleased

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
