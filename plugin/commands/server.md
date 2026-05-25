---
description: Start/stop/status of the optional PI planning HTTP server (V2 experimental)
allowed-tools: Read, Bash
model: sonnet
---

# EDPA Server

Manage the optional PI planning HTTP server. See `edpa:server` skill for
the full workflow.

## Argument forms

- `start` — spawn server on `localhost:3001`, write PID file
- `stop` — kill the running PID, remove PID file
- `status` — print running state, PID, port
- `restart` — `stop` then `start`

Example: `/edpa:server start`

If the `--with-server` install path was not used, the bundle at
`.claude/edpa/server/` does not exist and the command fails fast with a
hint to re-run `install.sh --with-server`.
