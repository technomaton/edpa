# Changelog

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
