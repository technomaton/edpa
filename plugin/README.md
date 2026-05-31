# EDPA Plugin for Claude Code

This directory contains the installable EDPA plugin for Claude Code and compatible AI coding assistants.

## Installation

### Claude Code (native plugin install — recommended)

```bash
# Via TECHNOMATON Hub marketplace
/plugin marketplace add technomaton/technomaton-hub
/plugin install tm-edpa@technomaton-hub
```

The hub registers `tm-edpa` with `source: {github, repo: technomaton/edpa, path: plugin}`, so the marketplace fetches the plugin payload directly from this directory in the upstream repo — no vendored mirror, no drift.

Or directly from this repo (without going through the hub):

```bash
/plugin marketplace add technomaton/edpa
/plugin install edpa@technomaton-edpa
```

The repo-root `.claude-plugin/marketplace.json` lists the `edpa` plugin with `source: "./plugin"`, so Claude Code fetches just the `plugin/` subtree into `~/.claude/plugins/cache/edpa/` — the rest of the repo (`web/`, `tools/`, `tests/`, `docs/`) stays in the marketplace clone and never enters the plugin runtime.

For maintainer dogfooding against a local clone:

```bash
/plugin marketplace add /Users/<you>/projects/edpa
/plugin install edpa@technomaton-edpa
```

The SessionStart hook in `hooks/hooks.json` calls `edpa/scripts/hooks/install_deps.sh` on first launch, which `pip install`s `requirements.txt` once per plugin install (content-hashed marker in `${CLAUDE_PLUGIN_DATA}`). No manual setup needed.

### Other tools (Cursor, Codex CLI, raw)

```bash
curl -fsSL https://edpa.technomaton.com/install.sh | sh
```

The installer downloads the latest `edpa-plugin.tar.gz` release asset, extracts it into `.claude/`, and seeds `.edpa/` from the templates. After install:

```bash
pip3 install -r .claude/requirements.txt
python3 .claude/edpa/scripts/preflight.py --org <your-org>
```

Then either invoke skills manually (Cursor/Codex pick them up from `.claude/skills/`) or run `python3 .edpa/engine/scripts/project_setup.py --with-ci --with-hooks --with-rules` to provision the local `.edpa/` governance (config, id_counters, CI workflow, git hooks) directly.

## Structure

```
plugin/
├── .claude-plugin/
│   ├── plugin.json                  # Plugin manifest (name, version, skills, commands, hooks, mcpServers)
│   └── marketplace.json             # Local marketplace for `/plugin marketplace add` against this dir
├── .mcp.json                        # MCP servers: github + edpa (edpa/scripts/mcp_server.py)
├── requirements.txt                 # Python runtime deps (pyyaml, ruamel.yaml, mcp, openpyxl)
├── hooks/
│   └── hooks.json                   # SessionStart (install_deps) + PostToolUse (validate_on_save, post_commit)
├── skills/                          # 6 skills, auto-discovered. Slug = name: field in SKILL.md frontmatter
│   ├── edpa-setup/SKILL.md          # → /edpa:setup     — provision .edpa/ governance (engine, config, hooks, CI)
│   ├── edpa-add/SKILL.md            # → /edpa:add       — create a backlog item (local-first, id_counters)
│   ├── edpa-engine/SKILL.md         # → /edpa:engine    — evidence-driven calculation
│   ├── edpa-reports/SKILL.md        # → /edpa:reports   — timesheets, exports, snapshots
│   ├── edpa-autocalib/SKILL.md      # → /edpa:autocalib — CW heuristic optimization (Monte Carlo + coord descent)
│   └── edpa-server/SKILL.md         # → /edpa:server    — optional PI-planning HTTP server (experimental)
├── commands/                        # 4 slash commands, flat layout (no edpa/ subdir)
│   ├── close-iteration.md           # → /edpa:close-iteration — capacity prep + engine + reports
│   ├── board.md                     # → /edpa:board          — HTML Kanban snapshot
│   ├── capacity.md                  # → /edpa:capacity       — per-iteration capacity overrides
│   └── server.md                    # → /edpa:server         — start/stop PI-planning server
└── edpa/
    ├── scripts/                     # 31 Python modules
    │   ├── engine.py                # Core engine (Score, DerivedHours, invariants)
    │   ├── mcp_server.py            # MCP server for /edpa:status, /edpa:backlog, /edpa:iterations, /edpa:flow_metrics
    │   ├── calibrate_signals.py     # CW signal-weights calibrator (Monte Carlo + coordinate descent)
    │   ├── backlog.py               # Git-native backlog CLI
    │   ├── detect_contributors.py   # evidence[] → contributors[] (CW shares); /contribute resolution
    │   ├── local_evidence.py        # post-commit: commit_author + /contribute signals → evidence[]
    │   ├── sync_pr_contributions.py # CI: PR review/comment signals (edpa-contribution-sync)
    │   ├── capacity_override.py     # per-iteration capacity overrides (/edpa:capacity)
    │   ├── project_setup.py         # provision .edpa/ governance (config, id_counters, --with-ci/hooks/rules)
    │   ├── traceability.py          # Parent-chain validation
    │   ├── pi_close.py + velocity.py + transitions.py
    │   └── hooks/                   # Shell hook scripts referenced by hooks.json
    │       ├── install_deps.sh      # SessionStart — pip install requirements.txt once
    │       ├── validate_on_save.sh  # PostToolUse Edit|Write — YAML/JSON syntax check
    │       ├── edpa_post_commit.sh  # PostToolUse Bash — commit info
    │       ├── pre-commit           # Git pre-commit (user-installed, not auto-wired)
    │       └── install.sh           # Helper to install pre-commit into .git/hooks/
    ├── schemas/
    │   └── edpa_commit_info.schema.json
    ├── templates/
    │   ├── people.yaml.tmpl         # → .edpa/config/people.yaml (FTE, capacity_per_iteration, github)
    │   ├── edpa.yaml.tmpl           # → .edpa/config/edpa.yaml (project, cadence, naming)
    │   ├── cw_heuristics.yaml.tmpl  # → .edpa/config/cw_heuristics.yaml (signal + gate weights)
    │   └── github-workflows/        # edpa-contribution-sync.yml (installed by --with-ci) + edpa-collision-check.yml
    └── workflows/                   # V1 GH-Projects-era Actions (vestigial); V2 install ships only templates/github-workflows/ above
        ├── edpa-branch-check.yml          # PR branch naming enforcement
        ├── edpa-iteration-close.yml       # Iteration close automation
        ├── edpa-pi-close.yml              # PI close + report generation
        ├── edpa-sync-projects-to-git.yml  # GH Projects → backlog YAMLs (every 30 min during business hours)
        ├── edpa-sync-git-to-projects.yml  # Backlog YAMLs → GH Projects (push hook)
        ├── edpa-validate-item.yml         # YAML schema validation on PR
        ├── edpa-traceability-check.yml    # Parent-chain validation
        ├── edpa-collaborators-sync.yml    # Auto-update people.yaml on collaborator change
        ├── edpa-contributor-detect.yml    # Detect /contribute commands in PRs
        ├── edpa-velocity-track.yml        # PI velocity history
        └── edpa-wsjf-calculate.yml        # WSJF score on backlog
```

## Skills + commands at a glance

V2.1 is **local-first**: everything runs against `.edpa/backlog/` + `git log`.
PR-thread signals (`pr_reviewer`, `issue_comment`) arrive only via the optional
`edpa-contribution-sync` GitHub Action; nothing requires GitHub Projects.

| Skill / command | Invocation | What it does |
|---|---|---|
| `edpa:setup` | `/edpa:setup` | Provision `.edpa/` governance (engine, config, id_counters, hooks, CI) |
| `edpa:add` | `/edpa:add` | Create a backlog item (local-first; ID from id_counters) |
| `edpa:engine` | `/edpa:engine` | Compute hours from local git evidence + validate invariants |
| `edpa:reports` | `/edpa:reports` | Per-person timesheets, per-item cost, snapshots, Excel |
| `edpa:autocalib` | `/edpa:autocalib` | Auto-calibrate CW heuristics (Monte Carlo + coordinate descent) |
| `edpa:server` | `/edpa:server` | Optional PI-planning HTTP server (experimental) |
| `/edpa:close-iteration` | command | Capacity prep + engine + reports for an iteration |
| `/edpa:capacity` | command | Per-iteration per-person capacity overrides (PTO, overtime) |
| `/edpa:board` | command | HTML Kanban snapshot from local backlog |

## Multi-developer setup — ID collision handling

When teams have multiple devs creating backlog items in parallel branches, ID collisions are possible (both allocate `S-5` before either's PR merges). EDPA ships **four defense layers** plus a semi-automatic recovery tool:

| Layer | Where | Trigger | Tool |
|---|---|---|---|
| 5 — pre-commit hook | local | `git commit` | `validate_ids.py --staged` (blocks commit on inconsistencies) |
| 6 — pre-push hook | local | `git push` | `validate_ids.py --pre-push` (blocks push if ID exists upstream) |
| 7 — CI workflow | server | PR open/sync | `edpa-collision-check.yml` (comments on PR + fails check) |
| Recovery | local | after conflict | `renumber_collisions.py --apply` (renames + updates parents + bumps counter) |

**Quick setup** (one-time per project):

```bash
# Local hooks
python3 .edpa/engine/scripts/project_setup.py --with-hooks

# CI workflow
cp .edpa/engine/templates/github-workflows/edpa-collision-check.yml \
   .github/workflows/edpa-collision-check.yml
```

Full guide with decision tree, common collision shapes (single / multi / parent-chain / cascading), recovery flow, and troubleshooting: [`docs/dev-collisions.md`](../docs/dev-collisions.md).

## Cross-tool compatibility

The plugin ships standard `SKILL.md` files (Claude Code Agent Skill frontmatter — portable Markdown + YAML), so the markdown payload is consumable beyond Claude Code:

```bash
# Claude Code   — auto-detected from .claude/ (native plugin install)
# Codex CLI     — cp -r .claude/skills/* ~/.codex/skills/
# Cursor        — auto-detected from .claude/skills/
# Gemini CLI    — cp -r .claude/skills/* ~/.gemini/skills/
```

Note: Skills carry the text content (instructions), but Claude Code is the only target that runs `.mcp.json` (MCP servers), `hooks/hooks.json` (PostToolUse + SessionStart), and `${CLAUDE_PLUGIN_ROOT}` script anchoring. On other tools, run the Python CLI scripts manually (`python3 .claude/edpa/scripts/<name>.py`).

### MCP tools provided by `mcp_server.py`

| Tool | What it does |
|------|-------------|
| `edpa_status` | Project governance summary (PI, iteration, team) |
| `edpa_backlog` | Query backlog items with filters |
| `edpa_iterations` | List iterations with status/dates |
| `edpa_people` | Capacity registry lookup |
| `edpa_item` | Single item detail |
| `edpa_validate` | Schema + invariant validation |
| `edpa_sync_people` | Collaborator reconciliation |
| `edpa_flow_metrics` | Cycle time, throughput, and open-item age computed from `created_at`/`closed_at` timestamp fields |

## Target project layout (after install)

```
.claude/                              # Plugin payload (matches plugin/ structure)
├── .claude-plugin/plugin.json
├── .mcp.json
├── requirements.txt
├── hooks/hooks.json
├── skills/                           # 6 SKILL.md
├── commands/                         # 6 slash commands (flat)
└── edpa/                             # Python engine, schemas, templates, workflows

.edpa/                                # Project data (created by install.sh / /edpa:setup)
├── config/                           # people.yaml, cw_heuristics.yaml, edpa.yaml, id_counters.yaml
├── backlog/                          # Work items (.md frontmatter) per level (initiatives/, epics/, features/, stories/, defects/, …)
├── iterations/                       # Iteration & PI definitions
├── reports/                          # Per-iteration timesheets + edpa_results.json
├── snapshots/                        # Frozen iteration snapshots
└── data/                             # Raw evidence cache

.github/workflows/                    # CI — copied here by /edpa:setup (not by install.sh)
└── edpa-*.yml                        # 11 EDPA workflows (prefixed)
```
