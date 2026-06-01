# EDPA Setup

## Installation

Install the EDPA plugin into your project:

```bash
curl -fsSL https://edpa.technomaton.com/install.sh | sh
```

This copies the EDPA plugin into `.claude/edpa/` and sets up slash commands and skills.

## Setup

Initialize governance for your project:

```
/edpa setup "Project Name"
```

This will:
1. Create `.edpa/config/people.yaml` from template
2. Create `.edpa/config/heuristics.yaml` from template
3. Set up GitHub Project with custom fields (Job Size, WSJF, etc.)
4. Configure branch naming enforcement via GitHub Actions
5. Create initial backlog structure in `.edpa/backlog/`

## Manual Configuration

If you prefer to configure manually instead of using `/edpa setup`:

### Team capacity

Edit `.edpa/config/people.yaml`:

```yaml
people:
  - id: alice
    name: "Alice Smith"
    role: Dev
    fte: 1.0
    capacity_per_iteration: 80
```

### CW heuristics

Edit `.edpa/config/heuristics.yaml` (defaults are calibrated from Monte Carlo simulation):

```yaml
base_weights:
  owner: 1.0
  key_contributor: 0.6
  reviewer: 0.25
  consulted: 0.15
```

### GitHub Project

See [docs/github-setup.md](docs/github-setup.md) for custom field definitions.

## Verify Installation

```bash
# Test the engine
python3 .claude/edpa/scripts/engine.py --demo

# Test branch naming
git checkout -b feature/S-001-test-story
```

## Day-to-Day Usage

| Task | Command |
|------|---------|
| Close iteration | `/edpa close-iteration PI-2026-1.3` |
| Generate reports | `/edpa reports` |
| Sync with GitHub | `/edpa sync` |
| Calibrate heuristics | `/edpa calibrate` |

## Migration from v2.x

If upgrading from the old GitHub template approach:

| Old path | New path |
|----------|----------|
| `scripts/edpa_engine.py` | `.claude/edpa/scripts/engine.py` |
| `config/capacity.yaml` | `.edpa/config/people.yaml` |
| `config/cw_heuristics.yaml` | `.edpa/config/heuristics.yaml` |
| `config/project.yaml` | `.edpa/config/project.yaml` |
| `reports/` | `.edpa/reports/` |
| `snapshots/` | `.edpa/snapshots/` |
| `data/` | `.edpa/data/` |
| `claude-code/skills/` | `.claude/skills/` |
| `claude-code/commands/` | `.claude/commands/` |
