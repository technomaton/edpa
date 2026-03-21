# Changelog

## 2.2.0 — 2026-03-21

Initial open-source release as standalone repository.

### Added
- Standalone Python engine (`scripts/edpa_engine.py`) with `--demo` mode
- Claude Code skills: edpa-setup, edpa-engine, edpa-reports, edpa-autocalib
- Claude Code commands: `/edpa setup`, `/edpa close-iteration`, `/edpa reports`, `/edpa calibrate`
- GitHub Actions: branch naming check, iteration close workflow
- GitHub issue templates: Epic, Feature, Story
- PR template with EDPA evidence section
- GitHub MCP server configuration (`.mcp.json`)
- Full documentation: methodology, evidence detection, dual-view, audit trail, auto-calibration, cadence, GitHub setup, FAQ, quick start
- Configuration templates: capacity.yaml, cw_heuristics.yaml, project.yaml
- CW evaluator script for auto-calibration (`scripts/evaluate_cw.py`)
- Worked examples: sample iteration, small team config, ground truth sample
- Invariant validation tests

### Origin
- Extracted from [TECHNOMATON Hub](https://github.com/technomaton/technomaton-hub) `packs/tm-governance`
- Based on EDPA v2.2 methodology by Jaroslav Urbanek
