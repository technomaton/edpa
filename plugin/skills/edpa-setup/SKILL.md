---
name: setup
user-invocable: false
description: >
  Initialize EDPA governance for a project. Creates GitHub Projects with custom fields,
  work item hierarchy (Initiative→Epic→Feature→Story), capacity registry, project
  configuration, and copies CI workflows into .github/. Use when starting a new project
  or onboarding EDPA.
license: MIT
compatibility: GitHub CLI (gh), Python 3.10+
allowed-tools: Read Write Bash(gh *) Bash(git *) Bash(mkdir *) Bash(python3 *) Bash(cp *) Bash(touch *)
metadata:
  author: Jaroslav Urbánek
  version: 1.0.0
  domain: governance
  phase: setup
  standard: AgentSkills v1.0
---

# EDPA Setup — Project Initialization

## What this does

Initializes EDPA governance for a GitHub-based project. Produces a **clean** target project that consumes the plugin from `${CLAUDE_PLUGIN_ROOT}` (Claude Code's plugin cache) — does NOT vendor plugin scripts/templates/workflows into the project's `.claude/` directory. CI workflows install the plugin ephemerally on the runner via `install.sh`, so the project repo stays free of plugin payload.

After running, the project layout is:

```
<project>/
├── .edpa/
│   ├── config/
│   │   ├── edpa.yaml         # project metadata, governance, naming, issue types
│   │   └── people.yaml       # cadence + teams + people
│   ├── backlog/{initiatives,epics,features,stories}/
│   ├── iterations/, reports/, snapshots/, data/
│   ├── changelog.jsonl
│   └── sync_state.json
└── .github/workflows/
    └── edpa-*.yml            # 11 CI workflows (lazy-install plugin on runner)
```

No `.claude/edpa/`. Scripts/templates/workflows live in `${CLAUDE_PLUGIN_ROOT}` for Claude Code, and are installed ephemerally on CI runners by the workflows themselves.

## Arguments

`$ARGUMENTS` = project name (e.g., "Medical Platform")

### Argument resolution (when $ARGUMENTS is empty)

If `$ARGUMENTS` is empty, blank, or "help":

1. Check if `.edpa/config/edpa.yaml` exists (re-initialization scenario):
   - If yes, read `project.name` and present: "EDPA is already initialized for **{name}**. Re-run setup? [y/N]"
   - If re-running, use existing project name as default.
2. If `.edpa/` does not exist (fresh setup):
   - Read the git remote to infer project name: `git remote get-url origin` → extract repo name
   - Present: "Initialize EDPA for project: **{inferred-name}**? Or enter a different name."
3. Ask user to confirm or provide project name before proceeding.

## Steps

### 0. Stage 0 — Preflight readiness check

Run the preflight script. It verifies:

- `python3`, `git`, `gh` on PATH; Python ≥ 3.10
- Required modules: `yaml`, `openpyxl`
- `gh auth status` + scopes: `admin:org`, `project`, `repo`, `workflow`
- Org access (members visible to your token)
- Target repo accessible
- Org-level Issue Types: Initiative, Epic, Feature, Story, Defect, Task
- `git config user.name` + `user.email` set (auto-commit needs them)
- (If `.edpa/config/people.yaml` exists) declared github logins are org members

Stage 0 runs as part of `project_setup.py` automatically. The script is in the plugin cache:

```bash
# Standalone preflight (no provisioning) — for "is this repo ready?":
python3 "${CLAUDE_PLUGIN_ROOT}/edpa/scripts/project_setup.py" --org <org> --repo <repo> --check-only

# Full setup (runs Stage 0 first, blocks on ERROR, then provisions):
python3 "${CLAUDE_PLUGIN_ROOT}/edpa/scripts/project_setup.py" --org <org> --repo <repo> \
  --project-title "<title>"

# CI / scripted: never prompt, never auto-fix:
python3 "${CLAUDE_PLUGIN_ROOT}/edpa/scripts/project_setup.py" ... --non-interactive

# Auto-apply offered fixes (e.g. create missing Issue Types):
python3 "${CLAUDE_PLUGIN_ROOT}/edpa/scripts/project_setup.py" ... --auto-fix
```

`${CLAUDE_PLUGIN_ROOT}` is set by Claude Code when running plugin skills; it points at `~/.claude/plugins/cache/<plugin-id>/<version>/`. **Always reference plugin scripts via this variable, never via `.claude/edpa/scripts/`** — the target project does NOT vendor those files.

Stage 0 is idempotent and re-runnable. Skip via `--skip-preflight` only for repeat runs in the same session where preflight already passed.

### 1. Verify Python toolchain (covered by Stage 0)

Stage 0 already checked this. The plugin's SessionStart hook (`install_deps.sh`) auto-installs `pyyaml + ruamel.yaml + mcp + openpyxl` on the maintainer's machine the first time Claude Code loads the plugin, so a re-check here is usually a no-op.

If imports still fail: `pip3 install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt" --break-system-packages`

### 2. Create .edpa/ directory structure

```bash
mkdir -p .edpa/config \
         .edpa/backlog/initiatives \
         .edpa/backlog/epics \
         .edpa/backlog/features \
         .edpa/backlog/stories \
         .edpa/iterations \
         .edpa/reports \
         .edpa/snapshots \
         .edpa/data
touch .edpa/changelog.jsonl .edpa/sync_state.json
```

### 3. Install CI workflows into `.github/workflows/`

```bash
mkdir -p .github/workflows
cp "${CLAUDE_PLUGIN_ROOT}"/edpa/workflows/*.yml .github/workflows/
```

The 11 workflows are self-bootstrapping: each one's first job step runs `curl -fsSL https://edpa.technomaton.com/install.sh | sh` on the CI runner, so scripts get installed ephemerally per run and the project repo never has to commit `.claude/edpa/scripts/`. See `${CLAUDE_PLUGIN_ROOT}/edpa/workflows/` for the source.

### 4. Initialize project metadata — `edpa.yaml`

Read `${CLAUDE_PLUGIN_ROOT}/edpa/templates/project.yaml.tmpl` as the starting point. Write to `.edpa/config/edpa.yaml`, populating at minimum `project.name` from `$ARGUMENTS`. Leave optional fields (funding, organizations, addresses) empty for the user to fill in later if relevant.

The template has rich content: project description, funding instrument (program/registration/period), organizations (legal name, tax/VAT IDs, addresses), governance methodology version, naming patterns for PI/iteration/branch, item type prefixes, native GitHub Issue Types, label classifications. Most of these can stay at defaults.

**Do NOT merge project metadata into `people.yaml`** — these are two separate files in the v1.11+ architecture: `edpa.yaml` for project-level config, `people.yaml` for capacity registry only.

### 5. Initialize capacity registry — `people.yaml`

Read `${CLAUDE_PLUGIN_ROOT}/edpa/templates/people.yaml.tmpl` as the starting point. Write to `.edpa/config/people.yaml`, replacing the example `people:` entries with the real team. Keep the `cadence:` and `teams:` blocks (default cadence is AI-native: 1-week iterations, 5-week PI, 4 delivery + 1 IP).

For each team member, ask the user explicitly for: name, role, team, FTE, email, **and GitHub username**. Calculate `capacity_per_iteration = fte × hours_per_week × iteration_weeks` (e.g. `1.0 × 40 × 1 = 40` for 1-week iter).

**Roles** — use one of these exact values: `Arch`, `Dev`, `DevSecOps`, `PM`, `QA`. **Never default to "Dev"** — ask the user explicitly. If the user/memory profile indicates a specific role (e.g. "Lead Architect" → `Arch`), use that; otherwise the canonical phrasing is:

> "What is {name}'s role? (Arch / Dev / DevSecOps / PM / QA)"

**CRITICAL — never invent the `github` field** from email patterns (e.g. `jaroslav@company.com` → `jaroslav`) or from the user's name. GitHub usernames are not derivable. If the user does not know someone's login, leave `github: ""` and tell them they can fill it in later — `sync push --assignee` simply skips people without a login. Inventing a login risks routing issue assignments to a stranger with the same handle.

Canonical phrasing per person:
> "GitHub username for {name}? (leave blank if you don't know it right now — you can fill it in later in `.edpa/config/people.yaml`)"

### 6. Provision GitHub Project + custom fields

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/edpa/scripts/project_setup.py" \
  --org <org> --repo <repo> --project-title "<project-name> Governance" \
  --skip-preflight   # only if Stage 0 already ran this session
```

The script:
- Creates the Project via `gh project create`
- Adds custom fields (WSJF, Estimate, Iteration, etc.) via GraphQL
- Maps Issue Types (Initiative/Epic/Feature/Story/Defect/Task) to the project
- Creates the `Enabler` label and other classifications
- Writes `.edpa/config/issue_map.yaml` mapping local IDs ↔ GitHub Issue numbers
- Offers to call `create_project_views.py` to seed Initiative / Epic / Feature / Story / Status kanban views

### 7. Hierarchy is mandatory — never produce a flat backlog

**CRITICAL** — every backlog item below the Initiative level MUST declare a `parent:` field referencing a higher-level item. The skill must refuse to emit flat lists, and the wizard must use the `backlog.py add` CLI rather than writing YAML files directly or calling `gh issue create` by hand:

```bash
# Correct — backlog.py enforces parent + assigns the next ID
python3 "${CLAUDE_PLUGIN_ROOT}/edpa/scripts/backlog.py" add --type Initiative --title "Platform"
python3 "${CLAUDE_PLUGIN_ROOT}/edpa/scripts/backlog.py" add --type Epic        --parent I-1 --title "Auth"
python3 "${CLAUDE_PLUGIN_ROOT}/edpa/scripts/backlog.py" add --type Feature     --parent E-1 --title "OAuth"
python3 "${CLAUDE_PLUGIN_ROOT}/edpa/scripts/backlog.py" add --type Story       --parent F-1 --title "Login UI" --js 5

# After items exist, sync push wires parent-child to GitHub sub-issues:
python3 "${CLAUDE_PLUGIN_ROOT}/edpa/scripts/sync.py" push
```

**Forbidden** — these bypass hierarchy enforcement:
- `gh issue create ...` directly (skips `backlog.py add` validation)
- Writing `.edpa/backlog/**/*.yaml` files via the editor without a `parent:` field on every non-Initiative entry
- Skipping `sync push` after adding items locally — without it, GitHub Issues never get linked as sub-issues

If the user asks "create issues for the backlog", ALWAYS use `backlog.py add` per item, then a single `sync push` at the end.

### 8. Output confirmation

Print summary: project name, team count, total FTE, capacity/iteration, cadence, GH Project URL.

The `project_setup.py` wizard automatically prompts for optional `create_project_views.py` invocation (Initiative / Epic / Feature / Story / Status views in the GitHub Project UI). Default is yes. Failure to create views is non-fatal — the maintainer can re-run later:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/edpa/scripts/create_project_views.py" --url <project-url>
```

## What NOT to do

- **Don't copy plugin files into `.claude/edpa/`.** The cleanly-installed project has `.claude/settings.json` and nothing else under `.claude/`. Plugin scripts live in `${CLAUDE_PLUGIN_ROOT}` for the maintainer (Claude Code's cache) and are installed ephemerally on CI runners by the workflows themselves. Vendoring them into the project's `.claude/` is legacy v1.0 behaviour that confuses end-users and duplicates content.
- **Don't create `.edpa/config/heuristics.yaml`.** The engine reads canonical CW weights from `${CLAUDE_PLUGIN_ROOT}/edpa/templates/cw_heuristics.yaml.tmpl` (LOCKED, calibrated). The `.edpa/config/heuristics.yaml` file from pre-v1.11 was a copy that the engine ignored — seeding it is dead legacy.
- **Don't merge project metadata into `people.yaml`.** v1.11+ has `edpa.yaml` (project) and `people.yaml` (capacity) as separate files. Mixing them was a pre-v1.11 footgun.
- **Don't default `role: Dev`.** Roles are `Arch / Dev / DevSecOps / PM / QA`; ask the user.

## Error handling

- `gh` not authenticated → print `gh auth login` instructions
- Missing Python packages → install via SessionStart hook, or manually with `pip install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"`
- GitHub API rate limit → wait and retry
- `${CLAUDE_PLUGIN_ROOT}` not set → skill was invoked outside Claude Code's plugin runtime; fall back to manual install via `curl | sh https://edpa.technomaton.com/install.sh` and rerun setup from a Claude Code session
