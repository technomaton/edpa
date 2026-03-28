# Quick Start Guide

Get EDPA running in 10 minutes.

## Prerequisites

- Python 3.10+ with `pyyaml` (`pip install pyyaml`)
- GitHub CLI (`gh`) authenticated (`gh auth login`)
- A GitHub repository for your project

## Step 1: Create your project from template

```bash
gh repo create my-org/my-project --template technomaton/edpa-template --private
cd my-project
```

Or clone directly:
```bash
git clone https://github.com/technomaton/edpa.git my-project
cd my-project
```

## Step 2: Configure your team

Copy and edit the capacity registry:
```bash
cp .claude/edpa/templates/capacity.yaml.tmpl .edpa/config/capacity.yaml
```

Edit `.edpa/config/capacity.yaml` with your team:
```yaml
cadence:
  iteration_weeks: 2        # 2-week iterations
  pi_weeks: 10              # 10-week planning intervals

people:
  - id: alice
    name: "Alice Smith"
    role: Arch
    team: "My Org"
    fte: 0.5
    capacity_per_iteration: 40
    email: "alice@example.com"
    availability: confirmed

  - id: bob
    name: "Bob Jones"
    role: Dev
    team: "My Org"
    fte: 1.0
    capacity_per_iteration: 80
    email: "bob@example.com"
    availability: confirmed
```

Copy the heuristics (defaults work fine for most teams):
```bash
cp .claude/edpa/templates/heuristics.yaml.tmpl .edpa/config/heuristics.yaml
cp .claude/edpa/templates/project.yaml.tmpl .edpa/config/project.yaml
```

Edit `.edpa/config/project.yaml` with your project name.

## Step 3: Try the demo

Before using real data, run the built-in demo:
```bash
python .claude/edpa/scripts/engine.py --demo
```

You'll see a complete EDPA calculation with sample data, including per-person breakdown and invariant validation.

## Step 4: Set up GitHub Projects

Follow [docs/github-setup.md](github-setup.md) to create custom fields (Job Size, Issue Type, etc.) on your GitHub Project.

Or with Claude Code:
```
Set up EDPA governance for My Project
```

## Step 5: Start working

Create issues with the provided templates (Epic, Feature, Story). Set Job Size on each.

Follow the branch naming convention:
```bash
git checkout -b feature/S-001-first-story
```

## Step 6: Close your first iteration

After completing work items, close the iteration:

With Claude Code:
```
Close iteration PI-2026-1.1
```

Or manually:
```bash
python .claude/edpa/scripts/engine.py --iteration PI-2026-1.1 \
  --capacity .edpa/config/capacity.yaml \
  --heuristics .edpa/config/heuristics.yaml
```

## Step 7: Review outputs

Check the generated reports in `.edpa/reports/iteration-PI-2026-1.1/`:
- `edpa_results.json` — raw calculation data
- `vykaz-{person}.md` — per-person timesheet
- `item-costs.xlsx` — per-item cost allocation

Check the frozen snapshot in `.edpa/snapshots/PI-2026-1.1.json`.

## What's Next?

- After 4-5 iterations: [auto-calibrate](auto-calibration.md) your CW heuristics
- Explore [dual-view](dual-view.md) for per-item cost analysis
- Set up the full [TECHNOMATON Hub](https://github.com/technomaton/technomaton-hub) for additional capabilities
