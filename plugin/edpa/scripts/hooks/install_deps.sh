#!/bin/sh
# SessionStart hook — install EDPA Python deps once per plugin install.
#
# Triggered by hooks.json on every Claude Code session start. The fast path
# (cheap import probe + marker file) returns in <100ms when deps are already
# in place, so the cost on warm sessions is negligible.
#
# Marker lives in ${CLAUDE_PLUGIN_DATA} (persistent across plugin updates),
# keyed by the plugin's requirements.txt content hash so a deps bump in
# upstream re-triggers install without manual intervention.
#
# Failure modes:
#   - pip not on PATH         → warn, return 0 (don't block session start)
#   - pip install fails       → warn, return 0 (engine will error later
#                               with a clearer message than a hook abort)
#   - python3 missing         → warn, return 0 (install.sh checked this
#                               at install time; SessionStart can't fix it)
#
# The shape here mirrors the SessionStart pattern from the Vercel docs and
# Anthropic's plugin examples: idempotent shell-out with strong defaults.

set -e

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
PLUGIN_DATA="${CLAUDE_PLUGIN_DATA:-}"

if [ -z "$PLUGIN_ROOT" ] || [ -z "$PLUGIN_DATA" ]; then
  # Hook called outside Claude Code (e.g. shell-tested by hand). Nothing
  # to do — the curl|sh installer path doesn't read this file.
  exit 0
fi

REQUIREMENTS="$PLUGIN_ROOT/requirements.txt"
if [ ! -f "$REQUIREMENTS" ]; then
  exit 0
fi

# Compute a content-addressed marker so a requirements.txt change
# (new dep, version bump) auto-triggers re-install on next session.
if command -v shasum >/dev/null 2>&1; then
  REQ_HASH=$(shasum -a 256 "$REQUIREMENTS" | cut -d' ' -f1)
elif command -v sha256sum >/dev/null 2>&1; then
  REQ_HASH=$(sha256sum "$REQUIREMENTS" | cut -d' ' -f1)
else
  REQ_HASH="nohash"
fi
MARKER="$PLUGIN_DATA/deps_installed.$REQ_HASH"

if [ -f "$MARKER" ]; then
  exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "EDPA: python3 not on PATH — skills/MCP will not work. Install Python 3.10+." >&2
  exit 0
fi

# Cheap probe: if every dep already imports, claim victory without
# bothering pip. This is the common path on machines that already have
# PyYAML / mcp installed system-wide.
if python3 -c 'import yaml, ruamel.yaml, mcp.server, openpyxl' >/dev/null 2>&1; then
  mkdir -p "$PLUGIN_DATA"
  touch "$MARKER"
  exit 0
fi

if ! command -v pip3 >/dev/null 2>&1; then
  echo "EDPA: pip3 not on PATH — install Python deps manually:" >&2
  echo "       pip3 install -r $REQUIREMENTS" >&2
  exit 0
fi

echo "EDPA: installing Python deps (one-time, then cached)..." >&2

# --break-system-packages is the documented escape hatch for PEP 668
# environments (Debian/Ubuntu, recent macOS Homebrew). Plain pip3 install
# is the fallback for older environments where the flag is unknown.
if pip3 install -r "$REQUIREMENTS" --quiet --break-system-packages 2>/dev/null \
   || pip3 install -r "$REQUIREMENTS" --quiet 2>/dev/null; then
  mkdir -p "$PLUGIN_DATA"
  touch "$MARKER"
  echo "EDPA: deps installed." >&2
else
  echo "EDPA: dep install failed — run manually: pip3 install -r $REQUIREMENTS" >&2
fi

exit 0
