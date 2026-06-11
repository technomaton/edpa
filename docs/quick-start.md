# Quick Start Guide

Get EDPA running in 10 minutes.

## Prerequisites

- Python 3.10+ with `pyyaml` (`pip install pyyaml`)
- A git repository for your project (local is fine; GitHub is only needed for the optional PR-signal CI workflow)
- GitHub CLI (`gh`) authenticated (`gh auth login`) — only if you enable that optional workflow

## Step 1: Install EDPA plugin

```bash
cd my-project
curl -fsSL https://edpa.technomaton.com/install.sh | sh
```

## Step 2: Initialize and configure

**Option A: Interactive (recommended)**
```
/edpa:setup "My Project"
```

**Option B: Manual** (assumes `/edpa:setup` already vendored the engine into
`.edpa/engine/` — or copy the templates from your plugin checkout)

Copy and edit the capacity registry:
```bash
cp .edpa/engine/templates/people.yaml.tmpl .edpa/config/people.yaml
```

Edit `.edpa/config/people.yaml` with your team:
```yaml
people:
  - id: alice
    name: "Alice Smith"
    role: Arch
    team: "My Org"
    fte: 0.5
    capacity_per_iteration: 20
    email: "alice@example.com"
    availability: confirmed

  - id: bob
    name: "Bob Jones"
    role: Dev
    team: "My Org"
    fte: 1.0
    capacity_per_iteration: 40
    email: "bob@example.com"
    availability: confirmed
```

Copy the heuristics (defaults work fine for most teams):
```bash
cp .edpa/engine/templates/cw_heuristics.yaml.tmpl .edpa/config/cw_heuristics.yaml
cp .edpa/engine/templates/edpa.yaml.tmpl .edpa/config/edpa.yaml
```

Edit `.edpa/config/edpa.yaml` with your project name.

## Step 3: Try the demo

Before using real data, run the built-in demo:
```bash
python3 .edpa/engine/scripts/engine.py --demo
```

You'll see a complete EDPA calculation with sample data, including per-person breakdown and invariant validation.

## Step 4: (Optional) Enable PR-signal CI

V2 evidence comes from local git — you can skip this step entirely and the
engine still produces a complete derived timesheet. Enable the optional
`edpa-contribution-sync.yml` workflow only if you want PR-thread signals
(`pr_reviewer`, `issue_comment`) materialized into `evidence[]` after merges:

```bash
python3 .edpa/engine/scripts/project_setup.py --with-ci
```

Token setup (one secret, ~5 minutes): see [edpa-token-setup.md](edpa-token-setup.md).

## Step 5: Start working

Create backlog items with `/edpa:add` (Initiative / Epic / Feature / Story / Defect), each with a Job Size:
```
/edpa:add Story "First story" --parent F-100 --js 5
```

Follow the branch naming convention:
```bash
git checkout -b feature/S-001-first-story
```

## Step 6: Close your first iteration

After completing work items, close the iteration:

With Claude Code:
```
/edpa:close-iteration PI-2026-1.1
```

Or manually:
```bash
python3 .edpa/engine/scripts/engine.py \
  --edpa-root .edpa \
  --iteration PI-2026-1.1
```

## Step 7: Review outputs

Check the generated reports in `.edpa/reports/iteration-PI-2026-1.1/`:
- `edpa_results.json` — raw calculation data
- `vykaz-{person}.md` — per-person timesheet
- `edpa-results.xlsx` — Team Summary + Item Costs tabs (per-person aggregate + per-item allocation)

Check the frozen snapshot in `.edpa/snapshots/PI-2026-1.1.json`.

## What's Next?

- After 4-5 iterations: [auto-calibrate](auto-calibration.md) your CW heuristics
- Explore [dual-view](dual-view.md) for per-item cost analysis
- Use the `edpa_flow_metrics` MCP tool for cycle time, throughput, and item age analytics (requires synced timestamp fields -- see [MCP docs](mcp.md))
- Set up the full [TECHNOMATON Hub](https://github.com/technomaton/technomaton-hub) for additional capabilities

## Multi-developer setup — ID collision handling

If your team has more than one person creating backlog items in parallel, you'll occasionally hit ID collisions (two devs both allocate `S-5` before either's PR merges). EDPA ships four defense layers and a semi-automatic recovery tool — see [`docs/dev-collisions.md`](dev-collisions.md) for the full guide.

**Setup** (one-time per project):

```bash
# 1. Install git hooks (pre-commit, pre-push, commit-msg, post-commit).
#    Under lefthook this prints a snippet to paste into lefthook.yml + run
#    `lefthook install` instead of writing .git/hooks/. Foreign hooks are
#    never overwritten; re-run any time to refresh.
python3 .edpa/engine/scripts/project_setup.py --with-hooks
python3 .edpa/engine/scripts/project_setup.py --check-hooks   # verify (read-only)

# 2. Copy CI workflow template
cp .edpa/engine/templates/github-workflows/edpa-collision-check.yml \
   .github/workflows/edpa-collision-check.yml
git add .github/workflows/edpa-collision-check.yml
git commit -m "ci: add EDPA collision check"
```

**Recovery** (when a PR shows a conflict in `.edpa/backlog/`):

```bash
git fetch origin
python3 .edpa/engine/scripts/renumber_collisions.py --apply
git add . && git commit -m "renumber: collision with main"
git merge origin/main   # take MAX for id_counters.yaml conflict
git push
```
