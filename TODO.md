# EDPA — TODO

Forward-looking improvement backlog. Current shipped state: v1.3.0-beta.
Each entry has a target version, motivation, and rough effort estimate.

Items are roughly ordered by priority within each version. Move an entry
to CHANGELOG.md (`## Unreleased`) when picked up; delete it from here when
shipped.

---

## v1.4 — MCP & developer experience polish

### MCP integration tests in pytest (~ 50 lines)

Today the JSON-RPC stdio roundtrip is verified ad-hoc by spawning a
subprocess and feeding it `initialize` / `tools/list` / `tools/call`
manually. Make that a real pytest case so CI catches a regression where
e.g. the `Server(name, version=…)` constructor signature changes upstream
or the launcher entry point breaks.

**Acceptance:** `tests/test_mcp_integration.py` runs by default
(no e2e marker), spawns `python3 plugin/edpa/scripts/mcp_server.py`,
sends initialize → tools/list → tools/call edpa_status → tools/call
edpa_item("../etc/passwd"), asserts on stderr log lines. Skip on
Windows or when the `mcp` package is missing.

### Resource caching with mtime invalidation (~ 30 lines)

`read_resource` and the `_handle_*` family re-read YAML and JSON files on
every call. For a large backlog (1000+ items) this gets noticeable. Cache
`load_yaml` results keyed by `(path, st_mtime_ns)`; invalidate on stat
change. Bound the cache (e.g. last 64 entries) so a one-shot scan can't
balloon memory.

**Acceptance:** repeated `edpa_backlog` against unchanged data uses cache
(measured); editing a YAML invalidates the entry on next call.

### Live "first 5 minutes" tutorial in README

Today's README references the install command and `/edpa:setup` but a new
contributor lands on it without a "what does this look like?" walkthrough.
Add a short section: install → setup → first iteration close → first
report, with copy-pastable commands and screenshots of `engine --status`
output.

**Acceptance:** someone can read just the tutorial section and produce a
working toy iteration on a fresh repo.

### `sync add-iteration <ID>` subcommand (~ 80 lines)

Right now adding a new iteration YAML locally doesn't propagate the
`Iteration` field option to the GitHub Project. The user has to either
re-run `project_setup.py` (heavy) or manually create the option in the
GH UI. Add a small subcommand that uses `updateProjectV2Field` with the
merged option list.

**Acceptance:** create `.edpa/iterations/PI-2026-1.5.yaml`, run
`sync add-iteration PI-2026-1.5`, then `sync push` of an item with
`iteration: PI-2026-1.5` succeeds without manual GH edits.

---

## v1.5 — Operational tooling

### Live integration smoke as a CI workflow (~ 1 file)

Add `.github/workflows/integration.yml` that runs the e2e suite against
`technomaton/edpa-e2e-test` on a schedule (nightly) and on release tags.
Today these tests are local-only via `EDPA_E2E_REPO`; the sandbox would
benefit from a known-good signal independent of the developer's machine.

**Acceptance:** workflow runs nightly, posts a status check on the latest
release tag.

### Rate limiting / DoS guard for MCP (~ 40 lines)

Less relevant for stdio (single client), but if we ever expose MCP over
HTTP/SSE the server needs a request budget. Track requests per minute
per client; refuse with `ERROR: rate limit exceeded` past threshold.
Pure read-only tool list means low risk today, but plan now while the
surface is small.

**Acceptance:** loop of 1000 calls in 1s gets throttled; normal usage
unaffected.

### Engine `--explain <person>` (~ 60 lines)

`engine.py` produces JSON results, but extracting "why does Alice have
40h on S-200?" requires reading the audit trail by hand. Add a
human-readable explanation mode that walks one person's allocation step
by step (item → role → CW source → ratio → hours), citing the
heuristic source for each CW value.

**Acceptance:** `engine --iteration PI-… --explain alice` prints a
narrative reproduction of the math, suitable for sharing with a
non-technical PM.

---

## v2.0 — MCP write tools

### `--mode write` permission model

Currently the MCP server is read-only by design. Some assistants would
benefit from `edpa_create_item`, `edpa_update_status`, `edpa_close_iteration`
tools — but exposing writes through MCP needs a real permission model:

- per-tool allowlist (explicit opt-in)
- audit log of all writes (who, what, when)
- dry-run mode default
- session token / signed claims for the writing client

This is a v2 feature because it changes the trust boundary materially.
Don't ship without a security review.

**Acceptance:** spec doc + threat model exist before any tool lands.

### MCP HTTP transport

Stdio is single-client. Multi-tenant scenarios (e.g. team-wide MCP
deployment) need HTTP/SSE. Wait until there's a real use case; don't
build for hypothetical demand.

---

## Cross-cutting / undated

### `tests/test_mcp_server.py` — add resource-listing tests

`list_resources` enumerates `edpa://config`, `edpa://people`, and one
entry per closed iteration's `edpa_results.json`. Currently only
`read_resource` is tested. Add tests that verify `list_resources`
returns the right URIs on a fresh fixture and updates when a new
iteration's results land.

### Document `EDPA_ROOT` env var in install.sh output

After install, the printed "Next steps" doesn't mention `EDPA_ROOT`.
Useful when a user clones the EDPA repo itself for hacking and wants
their MCP client to read the demo `.edpa/` data; or when a project
keeps `.edpa/` in a non-standard location.

### Audit `engine.py` for the same hardening pass MCP got

`mcp_server.py` got: stderr logging, version-aware identity, regex
input validation, crash-safe dispatch, `try`/`except` specificity.
`engine.py` is older and predates that pass — likely has bare except,
no structured logging, possibly unsafe path joins in custom backlog
locations. Run the same audit; backport what fits.

### Surface Vercel install.sh CDN cache TTL

`install.sh` is served via Vercel from `main`. After a fix-and-push,
how fast does `curl install.sh` see the new bytes? Document the
expected TTL (or set explicit `cache-control` on the deployment) so
hot-fix turnaround time is predictable.
