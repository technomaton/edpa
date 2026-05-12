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

Then either invoke skills manually (Cursor/Codex pick them up from `.claude/skills/`) or run `python3 .claude/edpa/scripts/project_setup.py` to provision GitHub Projects + workflows directly.

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
│   ├── edpa-setup/SKILL.md          # → /edpa:setup     — provision GitHub Projects + workflows
│   ├── edpa-engine/SKILL.md         # → /edpa:engine    — evidence-driven calculation
│   ├── edpa-reports/SKILL.md        # → /edpa:reports   — timesheets, exports, snapshots
│   ├── edpa-autocalib/SKILL.md      # → /edpa:autocalib — CW heuristic optimization (Karpathy loop)
│   ├── edpa-sync/SKILL.md           # → /edpa:sync      — GitHub Projects ↔ Git backlog
│   └── edpa-sync-people/SKILL.md    # → /edpa:sync-people — reconcile people.yaml vs collaborators
├── commands/                        # 6 slash commands, flat layout (no edpa/ subdir)
│   ├── setup.md                     # /edpa setup
│   ├── close-iteration.md           # /edpa close-iteration
│   ├── reports.md                   # /edpa reports
│   ├── calibrate.md                 # /edpa calibrate
│   ├── sync.md                      # /edpa sync
│   └── board.md                     # /edpa board
└── edpa/
    ├── scripts/                     # 31 Python modules
    │   ├── engine.py                # Core engine (Score, DerivedHours, invariants)
    │   ├── mcp_server.py            # MCP server for /edpa:status, /edpa:backlog, /edpa:iterations
    │   ├── calibrate_signals.py     # CW signal-weights calibrator (Monte Carlo + coordinate descent)
    │   ├── backlog.py               # Git-native backlog CLI
    │   ├── sync.py                  # GitHub Projects ↔ Git bidirectional sync
    │   ├── sync_collaborators.py    # Collaborator reconciliation (drives /edpa:sync-people)
    │   ├── project_setup.py         # GitHub Project initialization (Stage 0 preflight + provisioning)
    │   ├── project_views.py + create_project_views.py
    │   ├── issue_types.py           # GitHub Issue Types management
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
    │   ├── people.yaml.tmpl         # → .edpa/config/people.yaml (FTE, capacity, github logins)
    │   ├── cw_heuristics.yaml.tmpl  # → .edpa/config/heuristics.yaml
    │   └── project.yaml.tmpl        # → .edpa/config/edpa.yaml
    └── workflows/                   # 11 GitHub Actions, copied to .github/workflows/ by /edpa:setup
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

| Skill (slug) | Slash command | What it does |
|---|---|---|
| `edpa:setup` | `/edpa setup` | Provision GitHub Projects, custom fields, branch-check, copy CI workflows |
| `edpa:engine` | `/edpa close-iteration` | Compute hours from evidence + validate invariants |
| `edpa:reports` | `/edpa reports` | Generate per-person timesheets, snapshots, Excel exports |
| `edpa:autocalib` | `/edpa calibrate` | Auto-calibrate CW heuristics (Monte Carlo + coordinate descent) |
| `edpa:sync` | `/edpa sync` | Bidirectional GitHub Projects ↔ `.edpa/backlog/` sync |
| `edpa:sync-people` | _(no slash command)_ | Reconcile `people.yaml` vs GitHub collaborators |
| _(no skill)_ | `/edpa board` | Generate HTML Kanban snapshot from local backlog |

## Cross-tool compatibility

The plugin ships standard `SKILL.md` files (AgentSkills v1.0 frontmatter), so the markdown payload is consumable beyond Claude Code:

```bash
# Claude Code   — auto-detected from .claude/ (native plugin install)
# Codex CLI     — cp -r .claude/skills/* ~/.codex/skills/
# Cursor        — auto-detected from .claude/skills/
# Gemini CLI    — cp -r .claude/skills/* ~/.gemini/skills/
```

Note: Skills carry the text content (instructions), but Claude Code is the only target that runs `.mcp.json` (MCP servers), `hooks/hooks.json` (PostToolUse + SessionStart), and `${CLAUDE_PLUGIN_ROOT}` script anchoring. On other tools, run the Python CLI scripts manually (`python3 .claude/edpa/scripts/<name>.py`).

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
├── config/                           # people.yaml, heuristics.yaml, edpa.yaml
├── backlog/                          # Work items YAML per level (initiatives/, epics/, features/, stories/)
├── iterations/                       # Iteration & PI definitions
├── reports/                          # Per-iteration timesheets + edpa_results.json
├── snapshots/                        # Frozen iteration snapshots
└── data/                             # Raw evidence cache

.github/workflows/                    # CI — copied here by /edpa:setup (not by install.sh)
└── edpa-*.yml                        # 11 EDPA workflows (prefixed)
```
