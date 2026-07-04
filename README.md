# EDPA — Evidence-Driven Proportional Allocation

**Derive hours from Git evidence. No timesheets.**

[![EDPA](https://img.shields.io/badge/EDPA-2.14.0-34d399)](docs/methodology.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub](https://img.shields.io/badge/Made_for-GitHub-181717?logo=github)](https://github.com)

```
Score = JobSize x ContributionWeight x RelevanceSignal
DerivedHours = (Score / SumScores) x Capacity
Guarantee: Sum(DerivedHours) = Capacity (always)
```

## The Problem

Your team spends hours filling timesheets. The data is inaccurate, the process is hated, and for audit-grade projects (EU grants, government contracts) it's a compliance nightmare.

## The Solution

EDPA eliminates manual timesheets entirely. Your team works normally — commits, PRs, reviews, comments — and EDPA derives hours automatically from this delivery evidence.

**Before EDPA:**
```
Monday morning: "What did I work on last week? Let me guess... 4h on S-200, maybe 6h on F-102..."
```

**After EDPA:**
```
$ python3 .edpa/engine/scripts/engine.py --edpa-root .edpa --iteration PI-2026-1.3

EDPA 2.14.0 — Iteration PI-2026-1.3
======================================================================
Person                    Role     Capacity  Derived  Items   OK
----------------------------------------------------------------------
J. Urbanek                Arch          40h    40.0h     15   OK   ← Arch credited 15×
                                                                     for Feature/Epic gate
                                                                     transitions (LBC, design,
                                                                     refinement) — invisible
                                                                     in old simple mode.
O. Tuma                   DevSecOps      80h    80.0h      9   OK
Turyna                    Dev           60h    60.0h      7   OK
Matousek                  Dev           60h    60.0h      5   OK
----------------------------------------------------------------------
TEAM TOTAL                             240h   240.0h
PLANNING CAPACITY                    192.0h  (factor: 0.8)

All invariants passed: YES
```

## Key Features

- **Zero manual input** — hours derived from **local git evidence**: post-commit hook emits `commit_author` + `/contribute` signals; engine reads `yaml_edit`, gate-event, and in-flight Story activity directly from `git log`. Hooks register into `.git/hooks/` (or, under lefthook, via a printed snippet) and can be verified with `project_setup.py --check-hooks`.
- **Mathematical guarantee** — derived hours always sum to declared capacity
- **Gates mode (default)** — credits each Initiative/Epic/Feature status transition as a mini-deliverable, so prep work (LBC, decomposition, design) gets credited as it happens, not only at final Done. Validated to ±0.35 pp stability under ±20 % CW perturbation across 100 Monte Carlo runs.
- **C7.5 in-flight Story credit** — Stories with `yaml_edit` activity in the iteration window receive partial credit (`js × credit_factor`, default 0.40) even before they reach Done; the `story_activity_events[]` audit log in `edpa_results.json` records what was credited and why.
- **Optional PR-signal CI** — one GitHub Actions workflow (`edpa-contribution-sync.yml`) materializes PR-thread signals (`pr_reviewer`, `issue_comment`) into an item's `evidence[]` after the PR merges; useful for review/comment credit, but **not required** — V2.1 produces a complete derived timesheet from local git alone.
- **Flow metrics** — `edpa_flow_metrics` MCP tool computes cycle time, throughput, and open item age from git-derived item timestamps, filterable by iteration and level.
- **PI planning / overview** — `/edpa:pi-planning` (and the `edpa_pi_board` MCP tool) render the whole SAFe program picture — program board with dependency arrows, PI objectives, ROAM, portfolio rollup, WSJF, capacity — as a single self-contained, read-only HTML. No server, no Node, no network: it runs with only the Python engine and regenerates deterministically from `.edpa/`. Dependencies are first-class via `edpa_item_link_dep` (with cycle detection).
- **Dual-view** — per-person timesheets AND per-item cost allocation from the same data
- **Audit-grade** — frozen snapshots, immutable records, BankID signing support
- **Self-tuning** — auto-calibrates heuristics using Karpathy's autoresearch loop
- **Git-native, GitHub-friendly** — works with any git workflow; the only GitHub touchpoint is the optional PR-signal Action (E2E tested against `technomaton/edpa-e2e-test` sandbox)

## First 5 minutes — guided walkthrough

This walkthrough takes a fresh empty repo to a closed iteration with
derived hours and per-person reports. **No GitHub required** — the
walkthrough stays local so onboarding is zero-friction. For the full
operational flow (materialized git evidence, hooks, gate-based
prep-work attribution, optional PR-signal CI) see
[`docs/RUNBOOK.md`](docs/RUNBOOK.md).

### 1. Install (~30 s)

```bash
mkdir my-edpa-toy && cd my-edpa-toy
git init -q
curl -fsSL https://edpa.technomaton.com/install.sh | sh
```

You should see:

```
EDPA Installer

Checking prerequisites...
  Python 3.12 ✓
  git ✓
  ...

Vendoring engine into .edpa/engine/...
Bootstrapping .edpa/ data tree...
  Created .edpa/config/people.yaml (edit with your team)
  Created .edpa/config/edpa.yaml (edit project.name + governance metadata)

EDPA 2.14.0 installed.
```

The installer vendors the engine to `.edpa/engine/` (it installs no pip
packages and never touches `.claude/`) and seeds two config files from
templates:

```bash
ls .edpa/config/
# edpa.yaml  people.yaml
```

(The CW heuristics config, `cw_heuristics.yaml`, is seeded later by
`/edpa:setup` or `project_setup.py` — until then the engine falls back
to the vendored template defaults.)

### 2. Edit `people.yaml` to your team (~1 min)

The template ships with placeholder names. Replace them with your team
— even one person works. Minimum example for the AI-native default
(1-week iterations, 5-week PI = 4 delivery + 1 IP):

```yaml
people:
  - id: alice
    name: "Alice Architect"
    role: Arch
    fte: 0.5
    capacity_per_iteration: 20    # FTE × 40 for 1-week iter
  - id: bob
    name: "Bob Developer"
    role: Dev
    fte: 1.0
    capacity_per_iteration: 40
```

Verify the engine sees them:

```bash
python3 .edpa/engine/scripts/engine.py --status
```

```
EDPA 2.14.0 — Status
========================================
✓ .edpa/ found at .edpa
✓ people.yaml — 2 members, 1.5 FTE, 60h/iteration
    Alice Architect           Arch     0.5 FTE  20h
    Bob Developer             Dev      1.0 FTE  40h
✓ heuristics loaded
✓ backlog — 0 features, 0 stories
  reports/ empty (no iterations closed yet)
```

### 3. Add a toy iteration + backlog (~2 min)

One iteration plus two stories, one per person. Iterations are plain
YAML; backlog items are **Markdown files with YAML frontmatter** — one
file per item. (In a real project you'd create items with `/edpa:add`
or `python3 .edpa/engine/scripts/backlog.py add`, which also allocates
IDs; for the toy we write the files directly.)

```bash
cat > .edpa/iterations/PI-2026-1.1.yaml <<'YAML'
iteration:
  id: PI-2026-1.1
  pi: PI-2026-1
  status: active
  start_date: 2026-01-05
  end_date: 2026-01-09
  weeks: 1
YAML

cat > .edpa/backlog/stories/S-1.md <<'MD'
---
id: S-1
type: Story
title: "First user-facing feature"
parent: null
status: Done
js: 3
iteration: PI-2026-1.1
contributors:
  - person: alice
    as: owner
    cw: 1.0
---
MD

cat > .edpa/backlog/stories/S-2.md <<'MD'
---
id: S-2
type: Story
title: "Backend integration"
parent: null
status: Done
js: 5
iteration: PI-2026-1.1
contributors:
  - person: bob
    as: owner
    cw: 1.0
---
MD

git add .
git -c user.email="you@example.com" -c user.name="You" commit -q -m "seed"
```

### 4. Close the iteration (~30 s)

```bash
mkdir -p .edpa/reports/iteration-PI-2026-1.1
python3 .edpa/engine/scripts/engine.py \
  --edpa-root .edpa --iteration PI-2026-1.1 \
  --output .edpa/reports/iteration-PI-2026-1.1/edpa_results.json
```

```
Loaded 2 items (2 Done Stories/Defects + 0 gate events + 0 story activity events)
Filtered to iteration: PI-2026-1.1

Results written to: .edpa/reports/iteration-PI-2026-1.1/edpa_results.json
Snapshot frozen: .edpa/snapshots/PI-2026-1.1.json
Excel: .edpa/reports/iteration-PI-2026-1.1/edpa-results.xlsx

======================================================================
EDPA 2.14.0 — Iteration PI-2026-1.1
======================================================================
Person                    Role     Capacity  Derived  Items   OK
----------------------------------------------------------------------
Alice Architect           Arch          20h    20.0h      1   OK
Bob Developer             Dev           40h    40.0h      1   OK
----------------------------------------------------------------------
TEAM TOTAL                              60h    60.0h
PLANNING CAPACITY                     48.0h  (factor: 0.8)

All invariants passed: YES

--- Alice Architect (20h) ---
  Item       Level      JS     CW   Score   Ratio   Hours
  S-1        Story       3   1.00    3.00 100.0%   20.0h

--- Bob Developer (40h) ---
  Item       Level      JS     CW   Score   Ratio   Hours
  S-2        Story       5   1.00    5.00 100.0%   40.0h
```

What just happened:

- **Capacity 20h, Derived 20h**: Alice declared 20h for the 1-week
  iteration. Story S-1 (JS=3, owner role, CW=1.0) was the only thing
  she touched, so all 20 derived hours land on S-1.
- **All invariants passed**: each person's derived hours sum to their
  declared capacity, ratios sum to 1.0, no negative scores. The math
  holds — the snapshot is auditable.
- An `edpa-results.xlsx` (Team Summary + Item Costs tabs) was emitted
  alongside the JSON results, and a frozen snapshot landed in
  `.edpa/snapshots/` for the audit trail.

### 5. Generate timesheets — `/edpa:reports PI-2026-1.1` (Claude Code)

If you have Claude Code running in this directory, the reports skill
picks up the engine output and writes per-person Markdown timesheets
plus the cost-allocation Excel. After it runs:

```
.edpa/reports/iteration-PI-2026-1.1/
├── edpa_results.json      ← engine output
├── edpa-results.xlsx      ← Team Summary + Item Costs tabs
├── timesheet-alice.md     ← human-readable, ready to attach to invoice
├── timesheet-bob.md
└── timesheet-team.md      ← aggregated team rollup
```

Each Markdown timesheet is a paste-able audit artefact: which items,
which roles, which scores, how many hours.

### Try the demo without your own data

If you just want to see the math against a synthetic team:

```bash
python3 .edpa/engine/scripts/engine.py --demo
```

A pre-seeded 3-person team with 4 stories runs through the full
calculation in under a second.

### What's next

- **Full operational flow** (materialize git evidence, close
  iterations and PIs, capacity overrides, gate-based prep-work
  credit): [`docs/RUNBOOK.md`](docs/RUNBOOK.md)
- **Optional GitHub integration** (PR-thread signals materialized
  into `evidence[]` after merges): [`docs/github-setup.md`](docs/github-setup.md)
- **Claude Code MCP layer** (29 tools — 14 read + 15 write — so the
  assistant reads and updates `.edpa/` structurally instead of
  grep): [`docs/mcp.md`](docs/mcp.md)
- **Methodology** (CW heuristics, gate model, audit trail, Monte
  Carlo calibration): [`docs/methodology.md`](docs/methodology.md)
- **Repeatable E2E test**: [`docs/E2E-TEST-PLAN.md`](docs/E2E-TEST-PLAN.md)
  (script-level) and [`docs/E2E-SKILLS-TEST-PLAN.md`](docs/E2E-SKILLS-TEST-PLAN.md)
  (skill-level).

## How It Works

1. **Person declares capacity** (e.g., 40h per 1-week iteration on the AI-native default; 80h per 2-week on classic SAFe)
2. **System detects evidence** from local git (commit author, `/contribute` directives, `yaml_edit` + gate transitions) plus optional PR-thread signals (reviewer, commenter)
3. **Evidence maps to Contribution Weight** (owner=1.0, key=0.6, reviewer=0.25, consulted=0.15)
4. **Score = JobSize x CW** for each (person, item) pair
5. **Scoring**: each Initiative/Epic/Feature status transition becomes a mini-deliverable
   with `effective_js = parent.js × gate_weight`. Stories still credited at Done.
6. **Hours = (Score / TotalScores) x Capacity** — proportional allocation
7. **Invariant: Sum always equals declared capacity**

Two complementary views from the same data:

| View | Question | Output | Guarantee |
|------|----------|--------|-----------|
| **Per-person** | How did P's time distribute? | Timesheet | Sum = capacity |
| **Per-item** | What did item X cost? | Cost allocation | Sum = 100% |

## Backlog Item Schema

Every backlog item is a Markdown file with YAML frontmatter under
`.edpa/backlog/<level>/` and follows this shape (the pre-commit hook +
`validate_syntax.py` enforce it):

```yaml
---
id: S-200                 # required, must match file name (S-200.md) + level prefix
type: Story               # Initiative | Epic | Feature | Story | Defect | Task
title: "Add OMOP parser"  # required
parent: F-100             # required for non-Initiative levels
status: Done              # required. Portfolio enum (Initiative/Epic):
                          #   Funnel | Reviewing | Analyzing | Ready | Implementing | Done
                          # Delivery enum (Feature/Story/Defect):
                          #   Funnel | Analyzing | Backlog | Implementing | Validating |
                          #   Deploying | Releasing | Done
js: 5                     # required for Story/Feature, > 0
iteration: PI-2026-1.3    # required for Story; optional for Feature
contributors:             # who actually delivered the work
  - person: bob-dev       # MUST match a people[].id in people.yaml
    as: owner             # owner | key | reviewer | consulted (evidence role)
    cw: 0.8               # 0..1 manual contribution weight
  - person: carol-qa
    as: reviewer
    cw: 0.2
---
```

`contributors[].as` is **not** the human job role (Dev/Arch/QA/PM —
that lives in `people[].role`). It's the **evidence role** the engine
uses to map the contributor to an evidence signal: `owner` ≈ commit
author, `key` ≈ manual `/contribute`, `reviewer` ≈ PR reviewer,
`consulted` ≈ issue commenter. Anything outside that enum produces zero evidence
and triggers a clear `WARN: 0 evidence pairs derived from N
contributor entries` at engine startup.

> Migrating from <1.7? Run
> `python3 .edpa/engine/scripts/migrate_contributors.py` once.
> The old keys (`role:` and `weight:`) are hard-rejected — there is
> no aliasing, by design — so the validator will tell you exactly
> which file still needs the rewrite.

## Directory Structure

After installation (curl installer or `/edpa:setup`), your project will have:

```
.
├── .edpa/                         # All EDPA state lives here
│   ├── engine/                    # Vendored engine (never touches .claude/)
│   │   ├── scripts/               # engine.py, backlog.py, local_evidence.py,
│   │   │                          #   project_setup.py, mcp_server.py,
│   │   │                          #   sync_pr_contributions.py, ...
│   │   ├── schemas/               # JSON schemas
│   │   ├── templates/             # Config + CI workflow templates (.tmpl)
│   │   └── VERSION                # Pinned plugin version
│   ├── config/
│   │   ├── people.yaml            # Team members, FTE, capacity
│   │   ├── edpa.yaml              # Project name + governance metadata
│   │   └── cw_heuristics.yaml     # Evidence scoring weights (seeded by
│   │                              #   project_setup.py / /edpa:setup)
│   ├── backlog/                   # Work items (file-per-item, .md + YAML frontmatter)
│   ├── iterations/                # Iteration definitions (.yaml)
│   ├── reports/                   # Generated timesheets & exports
│   ├── snapshots/                 # Frozen iteration snapshots
│   └── data/                      # Raw evidence data
└── ...your project files
```

Source repository structure:

```
.
├── plugin/                        # Plugin source (what gets installed)
│   ├── edpa/scripts/              # Python engine + utilities (50+ modules)
│   ├── edpa/schemas/              # JSON schemas
│   ├── edpa/templates/            # Config + CI workflow templates
│   ├── commands/                  # Claude Code slash commands (20)
│   ├── skills/                    # Claude Code skills (5)
│   └── .mcp.json                  # MCP server config
├── docs/                          # Full methodology + examples
├── tests/                         # Unit / integration / e2e suites
├── web/                           # Public website (edpa.technomaton.com)
├── install.sh                     # Shell installer
└── .edpa/                         # Governance data for this repo (self-hosted)
```

## Claude Code Integration

EDPA ships 5 composable skills, 20 slash commands, and a 29-tool MCP
server for [Claude Code](https://docs.anthropic.com/en/docs/claude-code):

| Skill | What it does |
|---------|-------------|
| `/edpa:setup` | Provision `.edpa/` governance (engine, config, id_counters, hooks, CI) |
| `/edpa:add` | Create a backlog item (local-first; ID from id_counters) |
| `/edpa:engine` | Compute hours from local git evidence + validate invariants |
| `/edpa:reports` | Per-person timesheets, per-item cost, snapshots, Excel |
| `/edpa:autocalib` | Auto-calibrate CW heuristics (after 1st PI) |

The 20 commands (`/edpa:close-iteration`, `/edpa:board`,
`/edpa:pi-planning`, `/edpa:forecast`, `/edpa:export`,
`/edpa:materialize`, ...) and the 29 MCP tools (14 read + 15 write)
are listed in [`plugin/README.md`](plugin/README.md) and
[`docs/mcp.md`](docs/mcp.md).

## Cross-Platform

The engine is plain Python — Claude Code is optional:

```bash
# Claude Code — plugin marketplace, then /edpa:setup
/plugin install edpa@technomaton-edpa

# Cursor, Codex CLI, any editor or CI — shell installer, then drive the CLIs
curl -fsSL https://edpa.technomaton.com/install.sh | sh
python3 .edpa/engine/scripts/engine.py --demo
python3 .edpa/engine/scripts/backlog.py add --type Story --title "..."
```

## Who Is This For?

- **EU-funded project teams** (OP TAK, Horizon Europe) — audit-grade timesheets without manual work
- **Software consultancies** (5-30 people) — billable hours from delivery evidence
- **Engineering managers** — evidence-based capacity planning with dual-view analytics
- **Government contractors** — per-deliverable cost allocation for compliance

## Documentation

| Document | Description |
|----------|-------------|
| [Methodology](docs/methodology.md) | Full EDPA v2.14.0 specification |
| [Quick Start](docs/quick-start.md) | 10-minute setup guide |
| [Operational Runbook](docs/RUNBOOK.md) | Every `/edpa:*` command end to end — setup, close-iteration, capacity, autocalib, board |
| [Playbook](docs/playbook.md) | From empty repo to first closed PI — full operations guide (Czech) |
| [Evidence Detection](docs/evidence-detection.md) | How delivery signals map to CW |
| [Dual-View](docs/dual-view.md) | Per-person vs per-item perspectives |
| [Audit Trail](docs/audit-trail.md) | Freeze rules and snapshot format |
| [Auto-Calibration](docs/auto-calibration.md) | Karpathy autoresearch loop |
| [Cadence](docs/cadence.md) | Classic (2/10) vs AI-Native (1/5) |
| [GitHub Setup](docs/github-setup.md) | Optional GitHub integration — local-first positioning, PR-signal workflow |
| [EDPA_TOKEN Setup](docs/edpa-token-setup.md) | PAT generation, repo/org secret, rotation — needed only for the optional PR-signal CI workflow |
| [FAQ](docs/faq.md) | Common questions |

## Simulation & Calibration

| Resource | Description |
|----------|-------------|
| [edpa-simulation](https://github.com/technomaton/edpa-simulation) | Original `--mode simple` simulation — 2 PIs, 10 iterations, 510 commits, 7 team members |
| [edpa-simulation-gates](https://github.com/technomaton/edpa-simulation-gates) | `--mode gates` validation — 4 PI × 2 iter, 156 git transitions, 6-person virtual team. **Avg MAD 7.8 % vs ground truth, 0.35 pp spread under ±20 % CW perturbation across 100 Monte Carlo runs.** |
| [calibrate_roles.py](https://github.com/technomaton/edpa-simulation/blob/main/scripts/calibrate_roles.py) | Multi-scenario CW calibration (8 scenarios, 569 pairs, MAD reduction 6.7%) |
| [edpa.technomaton.com](https://edpa.technomaton.com) | Public website with interactive dashboard, presentation, methodology, evaluation |

The default CW weights ship in the engine's `cw_heuristics.yaml` template (seeded to
`.edpa/config/cw_heuristics.yaml` by `project_setup.py` / `/edpa:setup`) and are calibrated
from 8 team scenarios
(Startup, Enterprise, DevOps-heavy, Research, Consultancy, AI-Native, Regulated, kashealth).
Key correction: BO/PM/Arch are systematically undervalued by Git auto-detection; QA slightly overvalued.

## Optional GitHub Integration

EDPA V2 is **local-first**: evidence collection runs against `git log` alone,
so derived timesheets, reports, and snapshots need no GitHub at all. (The V1
bidirectional GitHub Projects sync — `sync.py`, `issue_map.yaml`, custom
fields — was removed in 2.0.0.)

There is exactly **one** optional GitHub touchpoint: a CI workflow
(`edpa-contribution-sync.yml`, installed by `/edpa:setup --with-ci` or
`project_setup.py --with-ci`) that runs after a PR referencing an item
(e.g. `feat(S-1): ...`) merges, and materializes PR-thread signals
(`pr_reviewer`, `issue_comment`) into that item's `evidence[]`. It needs one
repository secret — see [`docs/edpa-token-setup.md`](docs/edpa-token-setup.md).

Want a board? `/edpa:board` renders a self-contained HTML Kanban and
`/edpa:pi-planning` the full PI picture, both straight from `.edpa/backlog/`
— no GitHub Project needed. See [`docs/github-setup.md`](docs/github-setup.md)
for the positioning, and
[`tests/test_sync_pr_contributions.py`](tests/test_sync_pr_contributions.py) +
[`tests/test_e2e_v2_ci_materialization.py`](tests/test_e2e_v2_ci_materialization.py)
for the workflow's tests.

## Part of TECHNOMATON Hub

EDPA is one of 15 capability packs in [TECHNOMATON Hub](https://github.com/technomaton/technomaton-hub) — a curated collection of AI-powered skills for development, operations, security, marketing, finance, and governance.

Complementary packs:
- **[tm-dx](https://github.com/technomaton/technomaton-hub/tree/main/packs/tm-dx)** — PR workflows and release automation
- **[tm-docs](https://github.com/technomaton/technomaton-hub/tree/main/packs/tm-docs)** — ADR, changelog, and documentation generation
- **[tm-secure](https://github.com/technomaton/technomaton-hub/tree/main/packs/tm-secure)** — Security scanning and compliance

## License

MIT — see [LICENSE](LICENSE)

---

*Built by [TECHNOMATON](https://technomaton.com). Methodology by Jaroslav Urbanek.*
