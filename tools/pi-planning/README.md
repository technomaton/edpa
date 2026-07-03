# tools/pi-planning — PI planning UI (build source)

This directory is **shipped product source, not a scratch PoC**. Two
deliverables build from here:

| Deliverable | Consumed by | Notes |
|---|---|---|
| `plugin/edpa/assets/pi-bundle.html` — prebuilt single-file React bundle (committed) | `plugin/edpa/scripts/pi_planning.py`, i.e. `/edpa:pi-planning` and the `edpa_pi_board` MCP tool | The Python script injects the `window.__EDPA__` snapshot JSON into the bundle and writes a portable, read-only `pi-<PI>.html`. No Node needed on the target machine. |
| `server/` — optional live HTTP server (TypeScript/Express) | `/edpa:server` (experimental); vendored to `.claude/edpa/server/` by `install.sh --with-server` | Serves the same React SPA from `dist/` plus `/api/*` endpoints that proxy MCP `tools/call` against the bundled `mcp_server.py`. |

The whole directory is packed into the release asset by
`.github/workflows/release.yml` (the `install.sh --with-server` probe
expects it in the payload).

## Rebuilding the committed bundle

Any change under `src/` or to `index.html` must be followed by a rebuild
**and** re-copying the committed bundle — otherwise `/edpa:pi-planning`
keeps shipping the stale UI (no CI check catches the drift yet):

```bash
cd tools/pi-planning
npm ci                  # once per clone
npm run build           # vite + vite-plugin-singlefile → dist/index.html
cp dist/index.html ../../plugin/edpa/assets/pi-bundle.html
```

`pi_planning.py` resolves the bundle in this order:

1. `--bundle <path>` (explicit override)
2. `plugin/edpa/assets/pi-bundle.html` (vendored — what end users get)
3. `tools/pi-planning/dist/index.html` (dev fallback, gitignored)

## Snapshot contract

The Python generator and the TypeScript app share the `window.__EDPA__`
snapshot shape:

- **Single source of truth:** `src/types/snapshot.ts`
  (`EDPA_SNAPSHOT_SCHEMA = 1`), mirrored by `pi_planning.py`
  (`SCHEMA_VERSION = 1`). Bump **both** together on any
  backward-incompatible shape change.
- The injection point `pi_planning.py` replaces is defined in
  `index.html` (the `__edpa_data__` script element).
- `pi_planning.py` deliberately re-implements the `.edpa → contract`
  transform from `server/yaml-store.ts` in Python so generated boards
  need no Node at use time — behavioural changes to the transform must
  land on both sides.

## Dev loop

```bash
npm run dev     # concurrently: tsx watch server/ + vite client
npm run build   # production single-file bundle → dist/index.html
npm start       # serve the built SPA + API (what /edpa:server runs)
```

## Neighbours

`tools/migrate_rr_to_rr_oe.py` and `tools/sensitivity_check.py` are
unrelated one-off analysis/migration scripts (see the project-structure
section in CONTRIBUTING.md). Only `tools/pi-planning/` is shipped
product source.
