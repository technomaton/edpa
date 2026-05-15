# EDPA — Evidence-Driven Proportional Allocation

**Derive hours from Git evidence. No timesheets.**

[![EDPA](https://img.shields.io/badge/EDPA-1.21.0-34d399)](docs/methodology.md)
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
$ python3 .claude/edpa/scripts/engine.py --edpa-root .edpa --iteration PI-2026-1.3

EDPA 1.21.0 — Iteration PI-2026-1.3
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

- **Zero manual input** — hours derived from GitHub delivery evidence (commits, PRs, reviews, comments)
- **Mathematical guarantee** — derived hours always sum to declared capacity
- **Gates mode (default)** — credits each Initiative/Epic/Feature status transition as a mini-deliverable, so prep work (LBC, decomposition, design) gets credited as it happens, not only at final Done. Validated to ±0.35 pp stability under ±20 % CW perturbation across 100 Monte Carlo runs.
- **Bidirectional GitHub Projects sync** — `sync push` creates issues with custom fields, `sync pull` mirrors GH UI changes back into local YAML; conflict auto-resolution with `last-write-wins` / `local-wins` / `remote-wins` strategies.
- **Dual-view** — per-person timesheets AND per-item cost allocation from the same data
- **Audit-grade** — frozen snapshots, immutable records, BankID signing support
- **Self-tuning** — auto-calibrates heuristics using Karpathy's autoresearch loop
- **GitHub-native** — works with GitHub Issues, Projects, PRs, and Actions (real E2E tested against `technomaton/edpa-e2e-test` sandbox)

## First 5 minutes — guided walkthrough

This walkthrough takes a fresh empty repo to a closed iteration with
derived hours and per-person reports. **No GitHub Project required** —
the walkthrough stays local so onboarding is zero-friction. For the
real GitHub Projects flow (push backlog, sync issue states, gate-based
prep-work attribution) see [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

### 1. Install (~30 s)

```bash
mkdir my-edpa-toy && cd my-edpa-toy
git init -q
curl -fsSL https://edpa.technomaton.com/install.sh | sh
```

You should see:

```
EDPA Installer
  Python 3.X ✓
  PyYAML ✓
  mcp (MCP SDK) ✓
  openpyxl ✓
  ...
EDPA 1.21.0 installed successfully!
```

Three config files were seeded from templates:

```bash
ls .edpa/config/
# edpa.yaml  heuristics.yaml  people.yaml
```

### 2. Edit `people.yaml` to your team (~1 min)

The template ships with placeholder names. Replace them with your team
— even one person works. Minimum example for the AI-native default
(1-week iterations, 5-week PI = 4 delivery + 1 IP):

```yaml
cadence:
  iteration_weeks: 1        # AI-native default; use 2 for classic SAFe
  pi_weeks: 5               # 4 delivery iterations + 1 IP

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
python3 .claude/edpa/scripts/engine.py --status
```

```
EDPA 1.21.0 — Status
========================================
✓ .edpa/ found at .edpa
✓ people.yaml — 2 members, 1.5 FTE, 60h/iteration
    Alice Architect           Arch     0.5 FTE  20h
    Bob Developer             Dev      1.0 FTE  40h
✓ heuristics loaded
✓ backlog — 0 features, 0 stories
```

### 3. Add a toy iteration + backlog (~2 min)

One iteration plus two stories, one per person:

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

cat > .edpa/backlog/stories/S-1.yaml <<'YAML'
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
YAML

cat > .edpa/backlog/stories/S-2.yaml <<'YAML'
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
YAML

git add .
git -c user.email="you@example.com" -c user.name="You" commit -q -m "seed"
```

### 4. Close the iteration (~30 s)

```bash
mkdir -p .edpa/reports/iteration-PI-2026-1.1
python3 .claude/edpa/scripts/engine.py \
  --edpa-root .edpa --iteration PI-2026-1.1 --mode gates \
  --output .edpa/reports/iteration-PI-2026-1.1/edpa_results.json
```

```
======================================================================
EDPA 1.21.0 — Iteration PI-2026-1.1
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
- An `edpa-results.xlsx` (Team Summary + Item Costs tabs) was emitted alongside the JSON results.

### 5. Generate timesheets — `/edpa:reports PI-2026-1.1` (Claude Code)

If you have Claude Code running in this directory, the reports skill
picks up the engine output and writes per-person Markdown timesheets
plus the cost-allocation Excel. After it runs:

```
.edpa/reports/iteration-PI-2026-1.1/
├── edpa_results.json      ← engine output
├── edpa-results.xlsx      ← Team Summary + Item Costs tabs
├── timesheet-alice.md     ← human-readable, ready to attach to invoice
└── timesheet-bob.md
```

Each Markdown timesheet is a paste-able audit artefact: which items,
which roles, which scores, how many hours.

### Try the demo without your own data

If you just want to see the math against a synthetic team:

```bash
python3 .claude/edpa/scripts/engine.py --demo
```

A pre-seeded 3-person team with 4 stories runs through the full
calculation in under a second.

### What's next

- **Real GitHub Projects integration** (push backlog → issues, sync
  status changes, gate-based prep-work credit): [`docs/RUNBOOK.md`](docs/RUNBOOK.md)
- **Claude Code MCP layer** (5 read-only tools so the assistant
  reads `.edpa/` structurally instead of grep): [`docs/mcp.md`](docs/mcp.md)
- **Methodology** (CW heuristics, gate model, audit trail, Monte
  Carlo calibration): [`docs/methodology.md`](docs/methodology.md)
- **Repeatable E2E test**: [`docs/E2E-TEST-PLAN.md`](docs/E2E-TEST-PLAN.md)
  (script-level) and [`docs/E2E-SKILLS-TEST-PLAN.md`](docs/E2E-SKILLS-TEST-PLAN.md)
  (skill-level).

## How It Works

1. **Person declares capacity** (e.g., 40h per 1-week iteration on the AI-native default; 80h per 2-week on classic SAFe)
2. **System detects evidence** from GitHub (assignee, PR author, reviewer, committer, commenter)
3. **Evidence maps to Contribution Weight** (owner=1.0, key=0.6, reviewer=0.25, consulted=0.15)
4. **Score = JobSize x CW** for each (person, item) pair
5. **Gates (default)**: each Initiative/Epic/Feature status transition becomes a mini-deliverable
   with `effective_js = parent.js × gate_weight`. Stories still credited at Done. Run
   `--mode simple` if your project does not record mid-life status transitions in git.
6. **Hours = (Score / TotalScores) x Capacity** — proportional allocation
7. **Invariant: Sum always equals declared capacity**

Two complementary views from the same data:

| View | Question | Output | Guarantee |
|------|----------|--------|-----------|
| **Per-person** | How did P's time distribute? | Timesheet | Sum = capacity |
| **Per-item** | What did item X cost? | Cost allocation | Sum = 100% |

## Backlog Item Schema

Every YAML under `.edpa/backlog/<level>/` follows this shape (the
pre-commit hook + `validate_syntax.py` enforce it):

```yaml
id: S-200                 # required, must match file name + level prefix
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
```

`contributors[].as` is **not** the human job role (Dev/Arch/QA/PM —
that lives in `people[].role`). It's the **evidence role** the engine
uses to map the contributor to a GitHub signal: `owner` ≈ assignee,
`key` ≈ PR author, `reviewer` ≈ PR reviewer, `consulted` ≈
issue commenter. Anything outside that enum produces zero evidence
and triggers a clear `WARN: 0 evidence pairs derived from N
contributor entries` at engine startup.

> Migrating from <1.7? Run
> `python3 .claude/edpa/scripts/migrate_contributors.py` once.
> The old keys (`role:` and `weight:`) are hard-rejected — there is
> no aliasing, by design — so the validator will tell you exactly
> which file still needs the rewrite.

## Directory Structure

After installation, your project will have:

```
.
├── .claude/
│   └── edpa/                      # EDPA plugin (installed by npx/curl)
│       ├── scripts/
│       │   ├── engine.py          # Core EDPA engine
│       │   ├── evaluate_cw.py     # CW evaluator for auto-calibration
│       │   ├── backlog.py         # Git-native backlog CLI
│       │   ├── sync.py            # GitHub Projects <-> Git sync
│       │   ├── issue_types.py     # GitHub Issue Types management
│       │   ├── project_setup.py   # GitHub Project initialization
│       │   ├── project_views.py   # GitHub Project view setup
│       │   └── create_project_views.py
│       ├── templates/             # Config templates (.tmpl)
│       └── workflows/             # GitHub Actions workflows
├── .edpa/                         # Project governance data
│   ├── config/
│   │   ├── people.yaml             # Team members, FTE, capacity
│   │   └── heuristics.yaml        # Evidence scoring weights (CW)
│   ├── backlog/                   # Work items (file-per-item)
│   ├── iterations/                # Iteration definitions
│   ├── reports/                   # Generated timesheets & exports
│   ├── snapshots/                 # Frozen iteration snapshots
│   └── data/                      # Raw evidence data
├── .mcp.json                      # GitHub MCP server configuration
└── ...your project files
```

Source repository structure:

```
.
├── plugin/                        # Plugin source (what gets installed)
│   ├── edpa/scripts/              # Python engine + utilities
│   ├── edpa/templates/            # Config templates
│   ├── edpa/workflows/            # GitHub Actions
│   ├── commands/edpa/             # Claude Code slash commands
│   ├── skills/                    # Claude Code skills (5 skills)
│   └── .mcp.json                  # MCP server config
├── docs/                          # Full methodology + examples
├── web/                           # Public website (edpa.technomaton.com)
├── install.sh                     # Shell installer
└── .edpa/                         # Governance data for this repo
```

## Claude Code Integration

EDPA includes 5 composable skills for [Claude Code](https://docs.anthropic.com/en/docs/claude-code):

| Command | What it does |
|---------|-------------|
| `/edpa setup` | Initialize governance (GitHub Projects, config, CI) |
| `/edpa close-iteration` | Compute hours + generate reports |
| `/edpa reports` | Generate timesheets, snapshots, Excel exports |
| `/edpa calibrate` | Auto-calibrate CW heuristics (after 1st PI) |
| `/edpa sync` | Sync GitHub Projects <-> Git backlog |

Skills work on 26+ platforms (Codex CLI, Cursor, Gemini CLI, etc.)

## Cross-Platform

```bash
# Claude Code — skills auto-detected from .claude/
# Codex CLI
cp -r .claude/skills/* ~/.codex/skills/
# Cursor — auto-detected
# Gemini CLI
cp -r .claude/skills/* ~/.gemini/skills/
```

## Who Is This For?

- **EU-funded project teams** (OP TAK, Horizon Europe) — audit-grade timesheets without manual work
- **Software consultancies** (5-30 people) — billable hours from delivery evidence
- **Engineering managers** — evidence-based capacity planning with dual-view analytics
- **Government contractors** — per-deliverable cost allocation for compliance

## Documentation

| Document | Description |
|----------|-------------|
| [Methodology](docs/methodology.md) | Full EDPA v1.21.0 specification |
| [Quick Start](docs/quick-start.md) | 10-minute setup guide |
| [Evidence Detection](docs/evidence-detection.md) | How GitHub signals map to CW |
| [Dual-View](docs/dual-view.md) | Per-person vs per-item perspectives |
| [Audit Trail](docs/audit-trail.md) | Freeze rules and snapshot format |
| [Auto-Calibration](docs/auto-calibration.md) | Karpathy autoresearch loop |
| [Cadence](docs/cadence.md) | Classic (2/10) vs AI-Native (1/5) |
| [GitHub Setup](docs/github-setup.md) | Projects, custom fields, views |
| [EDPA_TOKEN Setup](docs/edpa-token-setup.md) | PAT generation, repo/org secret, rotation — required for the automated GitHub Projects ↔ git sync |
| [FAQ](docs/faq.md) | Common questions |

## Simulation & Calibration

| Resource | Description |
|----------|-------------|
| [edpa-simulation](https://github.com/technomaton/edpa-simulation) | Original `--mode simple` simulation — 2 PIs, 10 iterations, 510 commits, 7 team members |
| [edpa-simulation-gates](https://github.com/technomaton/edpa-simulation-gates) | `--mode gates` validation — 4 PI × 2 iter, 156 git transitions, 6-person virtual team. **Avg MAD 7.8 % vs ground truth, 0.35 pp spread under ±20 % CW perturbation across 100 Monte Carlo runs.** |
| [calibrate_roles.py](https://github.com/technomaton/edpa-simulation/blob/main/scripts/calibrate_roles.py) | Multi-scenario CW calibration (8 scenarios, 569 pairs, MAD reduction 6.7%) |
| [edpa.technomaton.com](https://edpa.technomaton.com) | Public website with interactive dashboard, presentation, methodology, evaluation |

The default CW weights in `.edpa/config/heuristics.yaml` are calibrated from 8 team scenarios
(Startup, Enterprise, DevOps-heavy, Research, Consultancy, AI-Native, Regulated, kashealth).
Key correction: BO/PM/Arch are systematically undervalued by Git auto-detection; QA slightly overvalued.

## GitHub Projects Sync

EDPA is bidirectionally synchronized with a GitHub Project:

```bash
python3 .claude/edpa/scripts/sync.py status            # health overview
python3 .claude/edpa/scripts/sync.py diff               # what would change
python3 .claude/edpa/scripts/sync.py pull --commit      # GH → local YAML, auto-commit
python3 .claude/edpa/scripts/sync.py push               # local → GH (creates issues if missing)
python3 .claude/edpa/scripts/sync.py setup-refresh      # rebuild field IDs after manual GH edits
python3 .claude/edpa/scripts/sync.py conflicts \
    --strategy last-write-wins --apply                  # auto-resolve conflicts
```

`project_setup.py` creates a Project with all custom fields (Job Size, BV, TC, RR, WSJF, Team,
per-level Status workflows, Iteration), persists field IDs to `.edpa/config/edpa.yaml`, and
maps every backlog item to a GH issue in `.edpa/config/issue_map.yaml`. See
[`docs/RUNBOOK.md`](docs/RUNBOOK.md) for the full operational guide and
[`tests/test_e2e_sync.py`](tests/test_e2e_sync.py) for end-to-end tests against a real GitHub
sandbox.

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
