---
name: setup
user-invocable: false
description: >
  Initialize EDPA governance for a project. Vendors the engine (scripts + schemas +
  templates) into `.edpa/engine/`, creates `.edpa/config/{edpa.yaml,people.yaml}`,
  copies CI workflows to `.github/workflows/`, provisions GitHub Project + custom
  fields. Use when starting a new project or onboarding EDPA.
license: MIT
compatibility: GitHub CLI (gh), Python 3.10+
allowed-tools: Read Write Bash(gh *) Bash(git *) Bash(mkdir *) Bash(python3 *) Bash(cp *) Bash(touch *) Bash(rm *)
metadata:
  author: Jaroslav Urbánek
  version: 1.0.0
  domain: governance
  phase: setup
  standard: AgentSkills v1.0
---

# EDPA Setup — Project Initialization

## What this does

Initializes EDPA governance for a GitHub-based project with a **clean** layout that puts everything EDPA-related under `.edpa/`. The engine (scripts + schemas + templates) is vendored from `${CLAUDE_PLUGIN_ROOT}/edpa/` into `.edpa/engine/`, so:

- CI workflows reference `python3 .edpa/engine/scripts/X.py` — no curl|sh install step per CI run, zero overhead
- Non-Claude-Code tools (Cursor, Codex) can run engine scripts directly from `.edpa/engine/`
- `.claude/` in the project stays clean (typically empty or just `settings.json`)
- Plugin payload is duplicated 1.6 MB into the project (committed), but pinned to a specific plugin version for reproducibility

Resulting layout:

```
<project>/
├── .edpa/
│   ├── engine/                       ← vendored from ${CLAUDE_PLUGIN_ROOT}/edpa/
│   │   ├── scripts/   (30 .py)
│   │   ├── schemas/   (1 .json)
│   │   ├── templates/ (3 .tmpl)
│   │   └── VERSION    ← plugin version pinned in this project
│   ├── config/
│   │   ├── edpa.yaml                 ← project metadata (from edpa.yaml.tmpl)
│   │   └── people.yaml               ← capacity registry (from people.yaml.tmpl)
│   ├── backlog/{initiatives,epics,features,stories}/
│   ├── iterations/, reports/, snapshots/, data/
│   ├── changelog.jsonl
│   └── sync_state.json
└── .github/workflows/edpa-*.yml      ← 11 CI workflows (call .edpa/engine/scripts/X.py)
```

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

Run the preflight script directly from the plugin cache (engine isn't vendored yet at this point):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/edpa/scripts/project_setup.py" \
  --org <org> --repo <repo> --check-only
```

This verifies: Python ≥ 3.10, `pyyaml + openpyxl`, `gh auth status`, scopes (`admin:org`, `project`, `repo`, `workflow`), org access, target repo, org-level Issue Types, `git config user.name + user.email`, and (if `.edpa/config/people.yaml` exists) that declared github logins are org members. Blocks on error.

### 1. Create .edpa/ directory tree

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

### 2. Vendor engine into `.edpa/engine/`

```bash
mkdir -p .edpa/engine
cp -R "${CLAUDE_PLUGIN_ROOT}/edpa/scripts"   .edpa/engine/
cp -R "${CLAUDE_PLUGIN_ROOT}/edpa/schemas"   .edpa/engine/
cp -R "${CLAUDE_PLUGIN_ROOT}/edpa/templates" .edpa/engine/

# Pin the vendored plugin version so /edpa:setup --update-engine knows what to
# diff against and CI workflows can sanity-check their script tree.
python3 -c "import json; print(json.load(open('${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json'))['version'])" > .edpa/engine/VERSION
```

**Why .edpa/engine/ (not .claude/edpa/):**

- `.edpa/` is the EDPA namespace owned by the project — engine code belongs inside it.
- `.claude/` is reserved for Claude Code's per-project config (e.g., `settings.json`); putting plugin payload there conflates two ownership boundaries.
- CI runners and non-Claude-Code tools have no `${CLAUDE_PLUGIN_ROOT}` and no plugin cache, so the engine must live in the project repo somewhere — `.edpa/engine/` is that somewhere.

**What gets vendored:** `scripts/` (30 .py), `schemas/` (1 .json), `templates/` (3 .tmpl). Skills/commands/hooks/.mcp.json from `${CLAUDE_PLUGIN_ROOT}` are NOT vendored — those are for Claude Code's plugin runtime exclusively, which loads them from its cache, not from the project.

### 3. Install CI workflows into `.github/workflows/`

```bash
mkdir -p .github/workflows
cp "${CLAUDE_PLUGIN_ROOT}"/edpa/workflows/*.yml .github/workflows/
```

The 11 workflows call `python3 .edpa/engine/scripts/X.py` directly — no install step needed per run because the engine is already vendored in the project repo from step 2.

### 4. Initialize project metadata — `.edpa/config/edpa.yaml`

```bash
cp "${CLAUDE_PLUGIN_ROOT}/edpa/templates/edpa.yaml.tmpl" .edpa/config/edpa.yaml
```

Then update `project.name` in the new file to `$ARGUMENTS`. Leave optional fields (funding instrument, organizations, addresses) empty for the user to fill in later if relevant.

The template carries:
- `project.{name, description, domain}` (basic identity)
- `project.funding.{program, registration, period_*}` (grants / contracts; remove block if N/A)
- `project.organizations[]` (legal name, tax/VAT IDs, addresses; for audit + invoicing)
- `governance.methodology` (engine version pin)
- `naming.{pi_pattern, iteration_pattern, branch_pattern, item_prefixes}`
- `issue_types.{Initiative, Epic, Feature, Story, Defect, Task}`
- `labels.Enabler`

Most of these can stay at defaults.

**Don't merge project metadata into `people.yaml`** — these are two separate files in the v1.11+ architecture: `edpa.yaml` for project-level config, `people.yaml` for capacity registry only.

### 5. Initialize capacity registry — `.edpa/config/people.yaml`

```bash
cp "${CLAUDE_PLUGIN_ROOT}/edpa/templates/people.yaml.tmpl" .edpa/config/people.yaml
```

Then replace the `people[]` example entries with the real team. Keep the `cadence:` and `teams:` blocks (default cadence is AI-native: 1-week iterations, 5-week PI, 4 delivery + 1 IP).

For each team member, ask the user explicitly for: **name, role, team, FTE, email, and GitHub username**. Calculate `capacity_per_iteration = fte × hours_per_week × iteration_weeks` (e.g. `1.0 × 40 × 1 = 40` for 1-week iter).

**Roles** — use one of these exact values: `Arch`, `Dev`, `DevSecOps`, `PM`, `QA`. **Never default to "Dev"** — ask the user explicitly. If a memory profile indicates a specific role (e.g. "Lead Architect" → `Arch`), use that; otherwise:

> "What is {name}'s role? (Arch / Dev / DevSecOps / PM / QA)"

**CRITICAL — never invent the `github` field** from email patterns or names. GitHub usernames are not derivable. If the user doesn't know someone's login, leave `github: ""` and tell them they can fill it in later — `sync push --assignee` skips people without a login. Inventing risks routing issue assignments to a stranger with the same handle.

> "GitHub username for {name}? (leave blank if you don't know — fill in later via PR to people.yaml)"

### 6. Provision GitHub Project + custom fields

```bash
python3 .edpa/engine/scripts/project_setup.py \
  --org <org> --repo <repo> --project-title "<project-name> Governance" \
  --skip-preflight   # already ran in step 0
```

The script:
- Creates the Project via `gh project create`
- Adds custom fields (WSJF, Estimate, Iteration, etc.) via GraphQL
- Maps Issue Types (Initiative/Epic/Feature/Story/Defect/Task) to the project
- Creates the `Enabler` label and other classifications
- Writes `.edpa/config/issue_map.yaml` mapping local IDs ↔ GitHub Issue numbers
- Offers to call `create_project_views.py` to seed kanban views

### 7. Hierarchy is mandatory — never produce a flat backlog

**CRITICAL** — every backlog item below the Initiative level MUST declare a `parent:` field referencing a higher-level item. The skill must refuse to emit flat lists, and the wizard must use the `backlog.py add` CLI rather than writing YAML files directly or calling `gh issue create` by hand:

```bash
# Correct — backlog.py enforces parent + assigns the next ID
python3 .edpa/engine/scripts/backlog.py add --type Initiative --title "Platform"
python3 .edpa/engine/scripts/backlog.py add --type Epic        --parent I-1 --title "Auth"
python3 .edpa/engine/scripts/backlog.py add --type Feature     --parent E-1 --title "OAuth"
python3 .edpa/engine/scripts/backlog.py add --type Story       --parent F-1 --title "Login UI" --js 5

# After items exist, sync push wires parent-child to GitHub sub-issues:
python3 .edpa/engine/scripts/sync.py push
```

**Forbidden** — these bypass hierarchy enforcement:
- `gh issue create ...` directly (skips `backlog.py add` validation)
- Writing `.edpa/backlog/**/*.yaml` files via the editor without a `parent:` field on every non-Initiative entry
- Skipping `sync push` after adding items locally — without it, GitHub Issues never get linked as sub-issues

### 8. Commit + output confirmation

Commit `.edpa/`, `.edpa/engine/`, `.github/workflows/edpa-*.yml`. Print summary: project name, team count, total FTE, capacity/iteration, cadence, GH Project URL.

The `project_setup.py` wizard automatically prompts for optional `create_project_views.py` invocation. Default is yes. Failure is non-fatal — the maintainer can re-run later:

```bash
python3 .edpa/engine/scripts/create_project_views.py --url <project-url>
```

## What NOT to do

- **Don't copy plugin files into `.claude/edpa/`.** Engine vendors to `.edpa/engine/`. The project's `.claude/` stays clean (typically just `settings.json`). Vendoring to `.claude/edpa/` was the v1.0-era pattern; v1.19.6+ uses `.edpa/engine/`.
- **Don't create `.edpa/config/heuristics.yaml`.** The engine reads canonical CW weights from `.edpa/engine/templates/cw_heuristics.yaml.tmpl` (LOCKED, calibrated). The user-editable `.edpa/config/heuristics.yaml` from pre-v1.11 was a copy the engine ignored.
- **Don't merge project metadata into `people.yaml`.** v1.11+ has `edpa.yaml` (project) and `people.yaml` (capacity) as separate files. Mixing them was a pre-v1.11 footgun.
- **Don't default `role: Dev`.** Roles are `Arch / Dev / DevSecOps / PM / QA`; ask the user.

## Error handling

- `gh` not authenticated → print `gh auth login` instructions
- Missing Python packages → SessionStart hook installs them; manual fallback: `pip3 install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt" --break-system-packages`
- GitHub API rate limit → wait and retry
- `${CLAUDE_PLUGIN_ROOT}` not set → skill was invoked outside Claude Code's plugin runtime; fall back to `curl -fsSL https://edpa.technomaton.com/install.sh | sh` (which vendors to `.edpa/engine/` directly) and rerun setup
- `.edpa/engine/VERSION` mismatches `${CLAUDE_PLUGIN_ROOT}` plugin version → engine drift; offer `/edpa:setup --update-engine` to refresh
