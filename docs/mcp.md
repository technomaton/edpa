# EDPA MCP Server

A Model Context Protocol server bundled with the EDPA plugin. It exposes
read-only access to `.edpa/` project data — config, iterations, people,
backlog — over the standard MCP `stdio` transport. Any MCP-aware client
(Claude Code, Cursor, Codex CLI, custom Python/TS clients) can read it.

**Production-ready since v1.3.0-beta; current as of v2.9.0** (read + write
tools — see the tool tables below). Validated handlers, schema-checked
inputs, item-ID path-traversal guard, stderr logging, version-aware identity.

---

## What it does

Instead of the assistant grepping `.edpa/backlog/*.yaml` itself, it calls one
of five tools and gets a structured JSON response. That keeps the assistant's
context tight and makes the data shape predictable.

| Tool             | Purpose                                                | Input                              |
|------------------|--------------------------------------------------------|------------------------------------|
| `edpa_status`    | Project name, current PI, active iteration, capacity    | none                               |
| `edpa_iterations`| List iterations of the active PI                        | optional `status` filter           |
| `edpa_people`    | Team registry from `people.yaml`                        | optional `team` filter             |
| `edpa_backlog`   | Backlog items from `.edpa/backlog/`                    | optional `iteration`, `type`, `status` |
| `edpa_item`      | Detail for one item                                     | required `item_id` (e.g. `S-200`)  |
| `edpa_flow_metrics` | Cycle time, throughput, open item age                | optional `iteration`, `level`      |
| `edpa_validate`  | Iterations continuity + schema check                    | none                               |
| `edpa_pi_board`  | Generate the self-contained PI planning HTML            | optional `pi`                      |

Analytics read tools (2.6.0+):

| Tool | Purpose |
|---|---|
| `edpa_forecast_pi` | Monte-Carlo PI completion forecast (p20/p50/p80) |
| `edpa_pi_metrics` | Multi-PI velocity, confidence + predictability trend |
| `edpa_insights` | Mid-iteration anomaly detection (overload, creep, stalled, blockers) |
| `edpa_ai_attribution` | Human vs AI delivery ratio from `Co-Authored-By` trailers |
| `edpa_payroll_export` | Billable-hours CSV from derived hours + `hourly_rate` |
| `edpa_reconcile` | Git evidence vs backlog status drift — suggests transitions (2.7.0) |

It also publishes resources for whole-file reads:

| Resource URI               | Content                                                |
|----------------------------|--------------------------------------------------------|
| `edpa://config`            | `.edpa/config/edpa.yaml`                                |
| `edpa://people`            | `.edpa/config/people.yaml`                              |
| `edpa://results/<iter-id>` | `edpa_results.json` for closed iteration `<iter-id>`    |

---

## How it gets started

The plugin's `plugin/.mcp.json` registers two MCP servers — `edpa` (this one)
and `github` (the upstream `@modelcontextprotocol/server-github` for issue
operations during sync). When Claude Code (or another MCP client) loads the
EDPA plugin, both servers come up automatically.

Manifest excerpt:

```json
{
  "mcpServers": {
    "edpa": {
      "command": "python3",
      "args": ["${CLAUDE_PLUGIN_ROOT}/edpa/scripts/mcp_server.py"]
    }
  }
}
```

`${CLAUDE_PLUGIN_ROOT}` resolves to the installed plugin directory regardless
of the client's working directory — important because Claude Code can be
launched from anywhere in the repo (e.g. `web/`, `tools/pi-planning/`, …).

For ad-hoc CLI use:

```bash
python3 .edpa/engine/scripts/mcp_server.py
```

Started by hand, the server reads JSON-RPC on stdin and writes responses on
stdout. Logs go to stderr (see below).

---

## Environment variables

| Variable          | Default       | Purpose                                                                |
|-------------------|---------------|------------------------------------------------------------------------|
| `EDPA_ROOT`       | walk up cwd   | Force a specific `.edpa/` directory (handy for tests, CI, multi-repo)   |
| `EDPA_LOG_LEVEL`  | `INFO`        | `DEBUG`, `INFO`, `WARNING`, `ERROR`                                      |
| `EDPA_LOG_FILE`   | unset         | Mirror logs to this file in addition to stderr                          |

`EDPA_ROOT` precedence: env var → walk up from `cwd` looking for the nearest
`.edpa/` directory. Returning `None` only when neither resolves.

---

## Known limitation: single-project scope per session

The MCP server is a **persistent process** launched once when the MCP client
(Claude Code, Cursor, etc.) starts. Its working directory is fixed at startup.
Subsequent `cd` calls from tool invocations cannot change it — they happen in
subprocess shells, not in the server process.

Practical consequences:

- `find_edpa_root()` calls `Path.cwd()` per request, but `cwd` reflects the
  server's launch directory, not whatever the assistant just changed to.
- All MCP tools (`edpa_status`, `edpa_backlog`, `edpa_item`, …) resolve
  `.edpa/` from that single, fixed location.
- If an automation needs to drive EDPA against a different project (sandbox,
  temp directory, sibling repo), MCP tools will read the **host project**,
  not the target.

**Workarounds:**

- **Set `EDPA_ROOT` before launching the MCP client.** This pins the server
  to an explicit project regardless of cwd. Useful for CI jobs and test
  harnesses.
- **Restart the MCP client when switching projects.** Closing and reopening
  Claude Code re-launches the server with the new cwd.
- **Fall back to direct script invocation** for multi-project automation.
  `python3 .edpa/engine/scripts/backlog.py …` resolves `.edpa/` from the
  subprocess's cwd, so `cd target-project && python3 …` works as expected.
  EDPA's full-flow E2E test (`tests/e2e_v2_full/`) takes this approach
  because it drives a `/tmp/edpa-e2e-*` sandbox in addition to the host
  project — see `docs/e2e-v2-full.md` for the pattern.

Multi-project MCP routing (per-call `EDPA_ROOT` argument, separate server
instance per workspace) is not implemented. The single-project assumption
matches the typical Claude Code workflow — one repo per session — and
keeps the server simple. Raise an issue if your workflow requires multi-
project support.

---

## Tool reference

### `edpa_status`

```json
{ }
```

Returns:

```json
{
  "project": "Medical Platform & Datovy e-shop",
  "current_pi": "PI-2026-1",
  "iterations_total": 5,
  "iterations_closed": 3,
  "active_iteration": "PI-2026-1.4",
  "active_iteration_dates": "18.3.-31.3.2026",
  "team_size": 9,
  "total_capacity_per_iteration": 720,
  "cadence": "2-week iterations, 10-week PI (5 iterations)"
}
```

### `edpa_iterations`

```json
{ "status": "closed" }
```

Returns array of `{id, status, dates, type, has_results}`.

### `edpa_people`

```json
{ "team": "CVUT" }
```

Returns array of `{id, name, role, fte, capacity, team}`.

### `edpa_backlog`

```json
{ "iteration": "PI-2026-1.3", "type": "Story", "status": "Done" }
```

Filters compose with AND. Returns array of items with their full YAML body.

### `edpa_item`

```json
{ "item_id": "S-200" }
```

Validates against the regex `^[A-Z]-\d{1,9}$`. Anything else is rejected
with `ERROR: invalid item_id ...` — the path lookup never sees raw input,
which prevents `../` traversal and similar tricks. The handler resolves the
type directory from the prefix (`S → stories`, `F → features`, `E → epics`,
`I → initiatives`, `D → defects`, `T → tasks`).

**Timestamp fields (v1.23.0+):** `edpa_backlog` and `edpa_item` include
`created_at`, `closed_at`, and `updated_at` in their responses when the
fields are present in the item's frontmatter (populated by `sync pull`).

### `edpa_flow_metrics`

```json
{ "iteration": "PI-2026-1.3", "level": "Story" }
```

Both inputs are optional. When omitted, metrics cover the entire backlog.

Returns:

```json
{
  "cycle_time": { "mean": 4.2, "median": 3.0, "p85": 7.0, "unit": "days" },
  "open_items_age": { "mean": 6.1, "median": 5.0, "p85": 12.0, "unit": "days" },
  "throughput": { "count": 14, "period_days": 7 },
  "items_detail": [
    { "id": "S-200", "status": "Done", "cycle_days": 3, "created_at": "...", "closed_at": "..." }
  ]
}
```

`cycle_time` is computed from `created_at` to `closed_at` for items at
`status: Done`. `open_items_age` is the elapsed time since `created_at`
for items not yet closed. Both require timestamp fields synced from GitHub
(see `sync pull` timestamp extraction).

### Write tools

The server also exposes local-first **write** tools (V2). They mutate `.edpa/`
files directly (atomic tmp+rename) and do **not** commit or call the network —
the calling skill/command owns the commit. Full set: `edpa_item_create`,
`edpa_item_update`, `edpa_item_transition`, `edpa_item_link_parent`,
`edpa_item_link_dep`, `edpa_item_roam`, `edpa_objective_set`,
`edpa_objective_remove`, `edpa_confidence_vote`, `edpa_iteration_create`,
`edpa_iteration_close`, `edpa_pi_create`, `edpa_pi_close`, `edpa_people_upsert`.

#### `edpa_pi_create`

```json
{ "id": "PI-2026-2", "start_date": "2026-06-02", "iteration_weeks": 1,
  "pi_iterations": 5, "status": "active" }
```

Creates the PI-level metadata file `.edpa/iterations/<id>.yaml` (top-level
`pi:` block). Only `id` is required, and it must be **PI-level** (`PI-YYYY-N`) —
an iteration id with a `.N` suffix is rejected, as is overwriting an existing
PI. The filename is always `.yaml` (the loader globs `*.yaml`; a `.yml` is
silently ignored). Delegates to `create_pi.py`, the single source of behavior
also used by the `/edpa:create-pi` command. Does not
scaffold child iterations — add those with `edpa_iteration_create`.

#### `edpa_pi_close`

```json
{ "id": "PI-2026-1" }
```

Closes a Program Increment: verifies **every child iteration is `closed`**, flips
the PI-level `pi.status` to `closed` in `.edpa/iterations/<id>.yaml`, and
(re)writes the PI rollup report (`.edpa/reports/pi-<id>/pi_results.json` +
`summary.md` — aggregated SP, predictability, per-person derived hours, completed
Features). `id` must be **PI-level** (`PI-YYYY-N`); an iteration id is rejected.
Pass `force: true` to roll up even when some iterations are still open (the
rollup then under-reports — it only sums closed iterations). Re-runnable:
regenerates the rollup and is a no-op on an already-closed status. Delegates to
`pi_close.py`, the single source of behavior also used by the `/edpa:close-pi`
command. The PI-level counterpart to `edpa_pi_create`; distinct from
`edpa_iteration_close`, which closes a single iteration.

#### `edpa_item_link_dep`

```json
{ "item_id": "F-101", "depends_on_id": "F-100", "action": "add" }
```

Adds or removes a dependency on a backlog item's `depends_on` list —
`depends_on: [F-100]` on `F-101` means "F-101 depends on F-100" (F-100 must land
first). Validates both items exist, refuses a self-loop, and (on `add`) refuses
an edge that would create a cycle. `action` is `add` (default) or `remove`. The
PI planning program board renders these as dependency arrows.

#### `edpa_item_roam`

```json
{ "item_id": "R-1", "roam_status": "mitigated" }
```

Sets the ROAM classification (`resolved` / `owned` / `accepted` / `mitigated`)
on a Risk item — the ROAM board groups risks into those four columns. Applies
only to items of type `Risk`.

### PI objectives

`edpa_objective_set` upserts a committed/stretch objective (keyed by title) for
a team; `edpa_objective_remove` deletes one; `edpa_confidence_vote` sets a team's
confidence (1-5). All persist to `.edpa/pi-objectives/<pi>.yaml` and render on
the PI planning Objectives board.

```json
{ "pi": "PI-2026-1", "team": "CVUT", "kind": "committed",
  "title": "OMOP parser production-ready", "bv": 8, "status": "done" }
```

### PI planning / overview

#### `edpa_pi_board`

```json
{ "pi": "PI-2026-1" }
```

Generates the self-contained **PI planning / overview** HTML for a PI (program
board, PI objectives, ROAM, portfolio rollup, WSJF, capacity) at
`.edpa/reports/pi-<id>/pi-<id>.html` and returns its path. `pi` is optional
(default: planning > active > first). It is a **read-only projection** of
`.edpa/` — a single portable file with no server, no Node, no network, safe to
re-run after edits. Delegates to `pi_planning.py`, the single source also driven
by the `/edpa:pi-planning` command. To change the plan, edit `.edpa/` (via the
write tools) and re-run.

---

## Production hardening (history: v1.3-beta)

What changed from the v1.0–v1.2 prototype (kept as design rationale):

1. **Portable plugin path.** `${CLAUDE_PLUGIN_ROOT}/...` instead of relative
   `.claude/edpa/...`. Working directory of the client no longer matters.
2. **Graceful import errors.** Missing `mcp` or `pyyaml` packages exit with
   a one-line install hint on stderr, not a stack trace.
3. **Stderr logging.** A real `logging.Logger` named `edpa.mcp` writes to
   stderr (and optionally `EDPA_LOG_FILE`) without polluting stdout. Every
   `call_tool` invocation is logged with its arguments.
4. **Server identity carries version.** `Server("edpa", version=…)` reads
   the plugin manifest at startup and reports the same string MCP clients
   show in their connection panel. Falls back to `"unknown"` only if the
   manifest is unreadable.
5. **`item_id` regex guard.** Path-shaped or empty IDs are rejected before
   they hit the filesystem.
6. **Specific exception handling in `load_yaml`.** Bare `except` removed —
   only `yaml.YAMLError` and `OSError` are caught and logged; everything
   else (`KeyboardInterrupt`, `SystemExit`) propagates.
7. **Crash-safe dispatch.** `call_tool` wraps every handler in a `try` so
   a handler bug returns a `TextContent` `ERROR: internal error ...`
   instead of dropping the JSON-RPC session.
8. **GitHub MCP token via env.** `plugin/.mcp.json` no longer ships a
   blank `GITHUB_PERSONAL_ACCESS_TOKEN`; it reads `${GITHUB_PERSONAL_ACCESS_TOKEN}`
   from the environment, so the user supplies it once and `gh auth` flows
   normally.

---

## Troubleshooting

| Symptom                                                | First check                                                                 |
|--------------------------------------------------------|-----------------------------------------------------------------------------|
| `ModuleNotFoundError: mcp`                             | `pip install -r requirements-dev.txt` (or `requirements.txt`).              |
| `ModuleNotFoundError: yaml`                            | Same.                                                                       |
| `ERROR: .edpa/ directory not found`                    | Run `/edpa setup` or `cd` into a project that has `.edpa/`.                 |
| Client shows `version: unknown`                        | Plugin manifest missing — reinstall from latest release.                     |
| Tool returns `ERROR: internal error ...`              | Set `EDPA_LOG_LEVEL=DEBUG` and `EDPA_LOG_FILE=/tmp/edpa-mcp.log`, retry.    |
| Need stdout-clean logs                                 | All logs already go to stderr; stdout carries only JSON-RPC.                 |

---

## Security model

- **Local-first writes.** Read tools never mutate state. The V2 write tools
  (`edpa_item_*`, `edpa_iteration_*`, `edpa_pi_create`, `edpa_pi_close`, `edpa_people_upsert`)
  write `.edpa/` files via atomic tmp+rename and do not commit or call the
  network; the calling skill/command owns the commit.
- **Path traversal blocked.** `item_id` parameter is the only user input that
  reaches the filesystem; the regex guard plus prefix→directory whitelist
  means a request like `{"item_id": "../etc/passwd"}` is rejected at the
  validator and never resolves to a path.
- **No outbound network.** The server does not call GitHub or any external
  service. The neighbouring `github` MCP server in `.mcp.json` does, but
  it's a separate process under user control.
- **Crash containment.** A handler exception is caught, logged, and surfaced
  as a tool error. The session stays open; the client can retry.

---

## Tests

Coverage in `tests/test_mcp_server.py`:

- 36 handler tests (status, iterations, people, backlog, item, resources)
- `TestItemIdValidation` (6 cases) — accepts canonical IDs, rejects
  traversal/lowercase/empty/non-digit/non-string and verifies `call_tool`
  surfaces the error
- `TestCallToolErrorHandling` (3 cases) — handler exceptions, unknown
  tools, missing `.edpa/` root all return TextContent errors
- `TestServerIdentity` (2 cases) — version comes from the manifest and is
  attached to the `Server` instance
- `TestLoggingSetup` (1 case) — logger has a stderr handler

Run them with:

```bash
pip install -r requirements-dev.txt
pytest tests/test_mcp_server.py -v
```

The full repo suite (`pytest tests/ -m "not e2e"`) is currently **127 passed,
0 skipped, 0 errors** with the dev dependency tree complete.
