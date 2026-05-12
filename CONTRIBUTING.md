# Contributing to EDPA

Thank you for your interest in contributing to EDPA!

## How to Contribute

### Reporting Issues

- Use [GitHub Issues](https://github.com/technomaton/edpa/issues) for bugs and feature requests
- Use the provided issue templates (Story, Feature, Epic)
- Include your EDPA version, Python version, and OS

### Pull Requests

1. Fork the repository
2. Create a feature branch following EDPA naming: `feature/S-XXX-description`
3. Make your changes
4. Run tests: `python3 -m pytest tests/`
5. Submit a PR using the PR template

### Branch Naming

Follow EDPA conventions:
```
feature/S-200-new-signal-type
bugfix/B-15-fix-invariant-check
```

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
