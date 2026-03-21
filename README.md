# EDPA — Evidence-Driven Proportional Allocation

**Derive hours from Git evidence. No timesheets.**

[![EDPA](https://img.shields.io/badge/EDPA-v1.0.0-34d399)](docs/methodology.md)
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
$ python scripts/edpa_engine.py --demo

EDPA v1.0.0 — Iteration DEMO-1.1 (simple mode)
======================================================================
Person                    Role     Capacity  Derived  Items    OK
----------------------------------------------------------------------
Alice (Arch)              Arch         40h      40h      4    OK
Bob (Dev)                 Dev          80h      80h      5    OK
Carol (Dev)               Dev          60h      60h      5    OK
----------------------------------------------------------------------
TEAM TOTAL                            180h     180h
All invariants passed: YES
```

## Key Features

- **Zero manual input** — hours derived from GitHub delivery evidence (commits, PRs, reviews, comments)
- **Mathematical guarantee** — derived hours always sum to declared capacity
- **Dual-view** — per-person timesheets AND per-item cost allocation from the same data
- **Audit-grade** — frozen snapshots, immutable records, BankID signing support
- **Self-tuning** — auto-calibrates heuristics using Karpathy's autoresearch loop
- **GitHub-native** — works with GitHub Issues, Projects, PRs, and Actions

## Quick Start

### 1. Use this template

```bash
gh repo create my-project --template technomaton/edpa --private
cd my-project
```

### 2. Configure your team

Edit `config/capacity.yaml`:
```yaml
cadence:
  iteration_weeks: 2    # 1 (AI-native) or 2 (classic)

people:
  - id: alice
    name: "Alice Smith"
    role: Dev
    fte: 1.0
    capacity_per_iteration: 80
```

### 3. Work normally

Follow one rule: **branch names must reference a work item**.
```bash
git checkout -b feature/S-200-omop-parser
git checkout -b bugfix/B-215-upload-validation
```

CI enforces this automatically. Everything else generates evidence.

### 4. Close iterations

With Claude Code:
```
Close iteration PI-2026-1.3
```

Or with the Python CLI:
```bash
python scripts/edpa_engine.py --iteration PI-2026-1.3 \
  --capacity config/capacity.yaml \
  --heuristics config/cw_heuristics.yaml
```

### 5. Try the demo

```bash
git clone https://github.com/technomaton/edpa.git
cd edpa
pip install pyyaml
python scripts/edpa_engine.py --demo
```

## How It Works

1. **Person declares capacity** (e.g., 80h per 2-week iteration)
2. **System detects evidence** from GitHub (assignee, PR author, reviewer, committer, commenter)
3. **Evidence maps to Contribution Weight** (owner=1.0, key=0.6, reviewer=0.25, consulted=0.15)
4. **Score = JobSize x CW** for each (person, item) pair
5. **Hours = (Score / TotalScores) x Capacity** — proportional allocation
6. **Invariant: Sum always equals declared capacity**

Two complementary views from the same data:

| View | Question | Output | Guarantee |
|------|----------|--------|-----------|
| **Per-person** | How did P's time distribute? | Timesheet | Sum = capacity |
| **Per-item** | What did item X cost? | Cost allocation | Sum = 100% |

## Repo Structure

```
.
├── config/                    # Team and project configuration
│   ├── capacity.yaml.tmpl     # Team members, FTE, capacity
│   ├── cw_heuristics.yaml.tmpl # Evidence scoring weights
│   └── project.yaml.tmpl      # Project metadata
├── scripts/
│   ├── edpa_engine.py         # Standalone Python EDPA engine
│   └── evaluate_cw.py         # CW evaluator for auto-calibration (LOCKED)
├── docs/                      # Full methodology documentation
├── examples/                  # Worked examples and sample data
├── claude-code/               # Claude Code skills and commands
├── .github/                   # Actions, issue templates, PR template
├── .mcp.json                  # GitHub MCP server configuration
├── snapshots/                 # Frozen iteration snapshots (auto-generated)
└── reports/                   # Generated timesheets & exports (auto-generated)
```

## Claude Code Integration

EDPA includes 4 composable skills for [Claude Code](https://docs.anthropic.com/en/docs/claude-code):

| Command | What it does |
|---------|-------------|
| `/edpa setup` | Initialize governance (GitHub Projects, config, CI) |
| `/edpa close-iteration` | Compute hours + generate reports |
| `/edpa reports` | Generate timesheets, snapshots, Excel exports |
| `/edpa calibrate` | Auto-calibrate CW heuristics (after 1st PI) |

Skills work on 26+ platforms (Codex CLI, Cursor, Gemini CLI, etc.)

## Cross-Platform

```bash
# Claude Code — skills auto-detected from claude-code/
# Codex CLI
cp -r claude-code/skills/* ~/.codex/skills/
# Cursor — auto-detected
# Gemini CLI
cp -r claude-code/skills/* ~/.gemini/skills/
```

## Who Is This For?

- **EU-funded project teams** (OP TAK, Horizon Europe) — audit-grade timesheets without manual work
- **Software consultancies** (5-30 people) — billable hours from delivery evidence
- **Engineering managers** — evidence-based capacity planning with dual-view analytics
- **Government contractors** — per-deliverable cost allocation for compliance

## Documentation

| Document | Description |
|----------|-------------|
| [Methodology](docs/methodology.md) | Full EDPA v1.0.0 specification |
| [Quick Start](docs/quick-start.md) | 10-minute setup guide |
| [Evidence Detection](docs/evidence-detection.md) | How GitHub signals map to CW |
| [Dual-View](docs/dual-view.md) | Per-person vs per-item perspectives |
| [Audit Trail](docs/audit-trail.md) | Freeze rules and snapshot format |
| [Auto-Calibration](docs/auto-calibration.md) | Karpathy autoresearch loop |
| [Cadence](docs/cadence.md) | Classic (2/10) vs AI-Native (1/5) |
| [GitHub Setup](docs/github-setup.md) | Projects, custom fields, views |
| [FAQ](docs/faq.md) | Common questions |

## Simulation & Calibration

| Resource | Description |
|----------|-------------|
| [edpa-simulation](https://github.com/technomaton/edpa-simulation) | Full EDPA simulation — 2 PIs, 10 iterations, 510 commits, 7 team members |
| [calibrate_roles.py](https://github.com/technomaton/edpa-simulation/blob/main/scripts/calibrate_roles.py) | Multi-scenario CW calibration (8 scenarios, 569 pairs, MAD reduction 6.7%) |
| [edpa.technomaton.com](https://edpa.technomaton.com) | Public website with interactive dashboard, presentation, methodology, evaluation |

The default CW weights in `config/cw_heuristics.yaml.tmpl` are calibrated from 8 team scenarios
(Startup, Enterprise, DevOps-heavy, Research, Consultancy, AI-Native, Regulated, kashealth).
Key correction: BO/PM/Arch are systematically undervalued by Git auto-detection; QA slightly overvalued.

## Part of TECHNOMATON Hub

EDPA is one of 15 capability packs in [TECHNOMATON Hub](https://github.com/technomaton/technomaton-hub) — a curated collection of AI-powered skills for development, operations, security, marketing, finance, and governance.

Complementary packs:
- **[tm-dx](https://github.com/technomaton/technomaton-hub/tree/main/packs/tm-dx)** — PR workflows and release automation
- **[tm-docs](https://github.com/technomaton/technomaton-hub/tree/main/packs/tm-docs)** — ADR, changelog, and documentation generation
- **[tm-secure](https://github.com/technomaton/technomaton-hub/tree/main/packs/tm-secure)** — Security scanning and compliance

## License

MIT — see [LICENSE](LICENSE)

---

*Built by [TECHNOMATON](https://technomaton.com). Methodology by Jaroslav Urbánek.*
