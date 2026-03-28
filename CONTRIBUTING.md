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

## Project Structure

- `plugin/` — EDPA plugin source (skills, commands, scripts, templates)
- `docs/` — Methodology documentation
- `web/` — Public website (edpa.technomaton.com)
- `tests/` — Test suite
- `.edpa/` — Governance data for this repo

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
