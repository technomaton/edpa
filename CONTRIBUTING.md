# Contributing to EDPA

Thank you for your interest in contributing to EDPA!

## How to Contribute

### Reporting Issues

- Use [GitHub Issues](https://github.com/technomaton/edpa/issues) for bugs and feature requests
- Use the provided issue templates (Story, Feature, Epic)
- Include your EDPA version, Python version, and OS

### Pull Requests

1. Fork the repository
2. Create a branch — any short name works; attribution comes from the commit scope, not the branch
3. Make your changes
4. Run tests: `python3 -m pytest tests/`
5. Submit a PR using the PR template

### Branch Naming

A **soft** convention — not CI-enforced. Attribution comes from the
Conventional-Commit scope (see below), not the branch name, so worktree/bot
branches are fine as-is. A readable shape if you want one:
```
defect/D-15-fix-invariant-check
feature/S-200-new-signal-type
```

### Commit Conventions

EDPA uses [Conventional Commits](https://www.conventionalcommits.org/)
with the EDPA ticket ID as scope:

```
feat(S-200): add new signal type for design reviews
fix(B-15): correct invariant check after gate events
docs(E-10): clarify CW normalization formula
refactor(F-100)!: drop legacy auth shim
chore(release): 2.1.2
```

Accepted types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`,
`test`, `build`, `ci`, `chore`. Use `!` after the scope for breaking
changes. The ticket ID in the scope is what `check_ticket_attached.py`
(commit-msg hook) and `local_evidence.py` (post-commit hook) parse to
attribute work. See [`plugin/rules/edpa-work-rules.md`](plugin/rules/edpa-work-rules.md)
for the full work-attribution rules including escape hatches
(`no-ticket:`, `WIP:`) and auto-prefixes (`chore(evidence):`,
`Merge`, `Revert`).

### Code Style

- Python: Follow PEP 8
- YAML: 2-space indentation
- Markdown: One sentence per line in docs

### Areas Where Help Is Welcome

- English translations of Czech documentation
- Additional GitHub Actions (WSJF calculator, velocity tracker)
- Integration with other project management tools (Jira, Linear)
- Test coverage improvements
- Example configurations for different team sizes

## Development Setup

```bash
git clone https://github.com/technomaton/edpa.git
cd edpa
pip install pyyaml openpyxl pytest
python3 -m pytest tests/
python3 plugin/edpa/scripts/engine.py --demo
```

### Claude Code dogfooding (optional but recommended)

The repo dogfoods its own EDPA plugin so any changes to `plugin/` are
testable in this same Claude Code session. After cloning, run **once
per clone** in Claude Code:

```
/plugin marketplace add .
```

This registers the local marketplace from `.claude-plugin/marketplace.json`.
Then:

```
/plugin install edpa@technomaton-edpa
```

`.claude/settings.json` has `"enabledPlugins": {"edpa@technomaton-edpa": "enabled"}`
so the plugin stays active across `/reload-plugins` and session restarts —
you only need the install command once.

**Iteration loop** for plugin development:

1. Edit `plugin/skills/<X>/SKILL.md` (or any other plugin file)
2. `/plugin marketplace update technomaton-edpa` — re-copies working tree into cache
3. `/reload-plugins` — re-loads skills/commands/hooks/MCP from cache

`${CLAUDE_PLUGIN_ROOT}` resolves to `~/.claude/plugins/cache/edpa/`, so
the engine and MCP server run from the cache copy — not directly from
the working tree. This matches what end-users experience.

## Project Structure

- `plugin/` — EDPA plugin source (skills, commands, scripts, templates)
- `docs/` — Methodology documentation
- `web/` — Public website (edpa.technomaton.com)
- `tests/` — Test suite
- `.edpa/` — Governance data for this repo

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
