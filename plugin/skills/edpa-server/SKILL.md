---
name: edpa:server
user-invocable: true
description: >
  Start/stop/status of the optional PI planning HTTP server (V2 experimental).
  Server is a React+Vite frontend backed by an Express+TS API that proxies
  reads/writes through the EDPA MCP server (single source of truth). Off by
  default — opt-in via install.sh --with-server. Listens on localhost:3001.
license: MIT
compatibility: Node.js 20+, MCP edpa server, Python 3.10+
allowed-tools: Read Bash(node *) Bash(npm *) Bash(kill *)
---

# EDPA Server — Local PI Planning UI

> **Experimental in V2.0.** The PI planning server is a *complement* to
> the canonical CLI/skill workflow, not a replacement. Per ADR-009 the
> default install does not vendor the server (~50 MB Node payload). Opt
> in with `./install.sh --with-server`.

## What this does

Starts a long-lived Node process at `localhost:3001`. The process:

- Serves the React SPA from `.claude/edpa/server/dist/` (frontend build).
- Exposes HTTP endpoints under `/api/*` that translate to MCP
  `tools/call` against the bundled `mcp_server.py`. Every read/write
  goes through MCP — the UI never touches YAML directly.
- Keeps one long-lived MCP subprocess across requests (per ADR open
  question in concept.md: long-lived > spawn-per-request).
- Writes its PID to `.edpa/.server.pid` (gitignored).

Each developer runs their own local instance — there is no shared
server in V2.0. Multi-user planning happens via `git pull` between
sessions.

## Arguments

`$ARGUMENTS` — one of:

- `start` — spawn the Node process, write PID file. No-op if already running.
- `stop` — kill the running PID, remove PID file. No-op if not running.
- `status` — print PID, port, uptime. Exit 1 if not running.
- `restart` — `stop` then `start`.

## Steps

### 1. Verify the server is installed

The server bundle lives at `.claude/edpa/server/`. If missing:

```
ERROR: PI planning server not installed.
       Re-run: ./install.sh --with-server
```

### 2. Run the subcommand

```bash
# start
node .claude/edpa/server/index.js --port 3001 &
echo $! > .edpa/.server.pid

# stop
kill "$(cat .edpa/.server.pid)" 2>/dev/null
rm -f .edpa/.server.pid

# status
if [ -f .edpa/.server.pid ]; then
  PID=$(cat .edpa/.server.pid)
  if kill -0 "$PID" 2>/dev/null; then
    echo "running pid=$PID port=3001 url=http://localhost:3001"
  else
    echo "stale PID file; server not running"
  fi
else
  echo "not running"
fi
```

### 3. Print the URL

On `start`, print:
```
EDPA PI planning UI is running at: http://localhost:3001
Stop with: /edpa:server stop
```

## What NOT to do

- **Never expose the server beyond localhost.** Listening on 0.0.0.0
  bypasses MCP's local-only assumptions and creates an authenticated
  surface that EDPA does not provide.
- **Never share a single instance across team.** V2.0 is single-user
  per checkout; sync is `git pull`. V2.x will revisit the canonical
  shared-server architecture.
- **Never edit YAML directly from custom UI code** — always route
  through MCP. The UI exists to provide ergonomics, not to bypass the
  validation/idempotency layers.

## Future work (out of scope for V2.0)

- Builds + vendoring: `tools/pi-planning/` ships as source today.
  Pre-built `dist/` shipped via the install.sh `--with-server` path
  is a follow-up (see plan.md Krok 7).
- Server↔MCP transport: long-lived subprocess vs. socket → TBD.
- HTTPS / auth: not in V2.0 scope (localhost-only).
