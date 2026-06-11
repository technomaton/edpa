# Release checklist

When releasing a new EDPA version, complete ALL steps — do not consider the release done until every item is checked:

1. **Version bump** — run `python3 scripts/bump_version.py {version} --apply` (stamps plugin.json + web/package.json + README badge + methodology/playbook/mcp/RUNBOOK stamps + edpa.yaml.tmpl + SKILL examples). Then `pytest tests/test_consistency.py::test_version_consistent` must pass — it guards the same stamps. Re-vendor the repo's own engine: `python3 plugin/edpa/scripts/project_setup.py`
2. **CHANGELOG.md** — add a new version entry describing all changes
3. **Tests** — run `pytest tests/` and fix any failures before proceeding
4. **Push** — push all changes to `main`
5. **Documentation** — update all affected docs:
   - Core docs: `docs/mcp.md`, `docs/RUNBOOK.md`, `docs/quick-start.md`, `README.md`
   - Plugin docs: `plugin/README.md`, relevant `plugin/skills/*/SKILL.md` files
   - Metadata: `.claude-plugin/marketplace.json`
   - Website: Astro pages in `web/src/pages/` (both CZ and EN versions)
6. **Web build + deploy** — run `vercel build --prod --cwd <path-to-web>` (NOT `astro build` — that skips `.vercel/output/`), then `vercel deploy --prebuilt --prod --cwd <path-to-web>`
7. **Verify web version** — run `curl -s https://edpa.technomaton.com/ | grep -o 'v[0-9]\+\.[0-9]\+\.[0-9]\+'` to confirm the correct version is live (do not trust WebFetch — it caches for 15 min)
8. **GitHub release** — create via `gh release create v{version}` with release notes from CHANGELOG
