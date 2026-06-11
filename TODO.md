# EDPA — TODO

Current shipped state: **v2.6.0** (2026-06-10).

**The canonical forward backlog lives in `.edpa/backlog/`** — this repo
dogfoods EDPA on itself (see Initiative `I-2 EDPA Platform Development`).
Browse it with `/edpa:backlog status` or
`python3 .edpa/engine/scripts/backlog.py tree`.

This file keeps only loose ideas that have no ticket yet. Move an entry to
`.edpa/backlog/` (via `/edpa:add`) when picked up; delete it here once shipped.

> History note: the pre-2026-06 revision of this file tracked the v1.x
> roadmap. Everything still relevant was shipped (see CHANGELOG 2.0.0–2.6.0)
> or migrated to the backlog. V1-era entries (GitHub-Projects two-way sync,
> `issue_map.yaml`, sub-issue provisioning, `sync add-iteration`) were
> dropped — that architecture was removed in 2.0.0.

---

## Ideas without tickets

### Multi-repo / org portfolio aggregation (V3)

`portfolio.yaml` at org level: capacity aggregation across repos, cross-repo
dependencies, org-wide WSJF ranking. Explicitly deferred to V3
(`docs/v2/verification.md` OQ-5) — the only unshipped item from the 2026-06
improvement roadmap.

### MCP HTTP transport (V3)

Stdio is single-client. Multi-tenant scenarios (team-wide MCP deployment)
need HTTP/SSE. Wait until there's a real use case; don't build for
hypothetical demand.

### MCP rate limiting (only with HTTP transport)

Irrelevant for stdio (single client). If MCP is ever exposed over HTTP/SSE,
add a per-client request budget before exposure, not after.

### `tests/test_mcp_server.py` — resource-listing tests

`list_resources` enumerates `edpa://config`, `edpa://people`, and one entry
per closed iteration's `edpa_results.json`. Only `read_resource` is tested
today; add tests that `list_resources` returns the right URIs on a fresh
fixture and picks up a newly closed iteration.

### Document `EDPA_ROOT` env var in install.sh output

The printed "Next steps" after install doesn't mention `EDPA_ROOT`. Useful
when hacking on the EDPA repo itself (MCP client should read the demo
`.edpa/`) or when a project keeps `.edpa/` in a non-standard location.

### install.sh root ↔ web/public sync automation

`tests/test_install_sh_hygiene.py` guards byte-equality between
`./install.sh` and `web/public/install.sh`, so drift fails CI — but the sync
itself is manual. Candidate: a build step in `web/` that copies the root file
into `public/` on every deploy (symlinks need Vercel verification).
