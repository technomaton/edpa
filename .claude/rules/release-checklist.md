# Release checklist

When releasing a new EDPA version, complete ALL steps — do not consider the release done until every item is checked:

1. **Version bump** — update `plugin/.claude-plugin/plugin.json` (single source of truth) AND `web/package.json` (must match, used by Vercel metadata)
2. **CHANGELOG.md** — add a new version entry describing all changes
3. **Tests** — run `pytest tests/` and fix any failures before proceeding
4. **Push** — push all changes to `main`
5. **Documentation** — update all affected docs:
   - Core docs: `docs/mcp.md`, `docs/RUNBOOK.md`, `docs/quick-start.md`, `README.md`
   - Plugin docs: `plugin/README.md`, relevant `plugin/skills/*/SKILL.md` files
   - Metadata: `.claude-plugin/marketplace.json`
   - Website: Astro pages in `web/src/pages/` (both CZ and EN versions)
6. **Web build + deploy** — run `npm run build` in `web/`, then `vercel deploy --prebuilt --prod --cwd <path-to-web>`
7. **Verify web version** — confirm the deployed site shows the correct version (header + footer read from `plugin/.claude-plugin/plugin.json` via `web/src/lib/version.ts`)
8. **GitHub release** — create via `gh release create v{version}` with release notes from CHANGELOG
