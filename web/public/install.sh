#!/bin/sh
# EDPA Installer — installs the EDPA plugin into .claude/edpa/
# Usage: curl -fsSL https://edpa.technomaton.com/install.sh | sh
set -e

REPO="technomaton/edpa"
TARGET=".claude"

echo "EDPA Installer"
echo "=============="

# --- Dependency checks ---
echo ""
echo "Checking prerequisites..."

# Python 3.10+
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: Python 3 not found. Install Python 3.10+ first."
  exit 1
fi
PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_OK=$(python3 -c 'import sys; print("yes" if sys.version_info >= (3, 10) else "no")')
if [ "$PY_OK" = "no" ]; then
  echo "ERROR: Python 3.10+ required (found $PY_VERSION)."
  exit 1
fi
echo "  Python $PY_VERSION ✓"

# PyYAML — required for every EDPA script
if python3 -c 'import yaml' 2>/dev/null; then
  echo "  PyYAML ✓"
else
  echo "  PyYAML not found — installing..."
  pip3 install pyyaml --quiet --break-system-packages 2>/dev/null || pip3 install pyyaml --quiet
fi

# mcp — required for MCP server (.claude/edpa/scripts/mcp_server.py)
# Without this the MCP tools (edpa_status, edpa_backlog, ...) silently fail
# to start and Claude Code falls back to Bash + grep for everything.
if python3 -c 'from mcp.server import Server' 2>/dev/null; then
  echo "  mcp (MCP SDK) ✓"
else
  echo "  mcp not found — installing..."
  pip3 install mcp --quiet --break-system-packages 2>/dev/null || pip3 install mcp --quiet
fi

# openpyxl — required for Excel exports in /edpa:reports
# Without this the engine prints "Excel export skipped" and the reports
# skill produces only Markdown timesheets, no item-costs.xlsx.
if python3 -c 'import openpyxl' 2>/dev/null; then
  echo "  openpyxl ✓"
else
  echo "  openpyxl not found — installing..."
  pip3 install openpyxl --quiet --break-system-packages 2>/dev/null || pip3 install openpyxl --quiet
fi

# git
if command -v git >/dev/null 2>&1; then
  echo "  git ✓"
else
  echo "WARNING: git not found. EDPA requires git for evidence detection."
fi

# gh (optional but recommended)
if command -v gh >/dev/null 2>&1; then
  echo "  GitHub CLI ✓"
else
  echo "  GitHub CLI not found (optional — needed for /edpa setup and sync)"
fi

echo ""

# --- Warn if already installed ---
if [ -d "$TARGET/edpa" ]; then
  printf "Warning: %s/edpa/ already exists. Overwrite? [y/N] " "$TARGET"
  read -r answer
  case "$answer" in
    [yY]*) echo "Overwriting..." ;;
    *) echo "Aborted."; exit 1 ;;
  esac
fi

# Create target directory
mkdir -p "$TARGET"

# Download plugin contents
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

echo "Downloading EDPA plugin..."
# Pick the most recent release tag (including prereleases — GitHub's
# "/releases/latest" API and `gh release download` without a tag both
# skip prereleases, which would silently fall back to a main-branch
# clone whenever every published release is marked `-beta`).
if command -v gh >/dev/null 2>&1; then
  LATEST_TAG=$(gh release list --repo "$REPO" --limit 1 --json tagName --jq '.[0].tagName' 2>/dev/null || true)
  if [ -n "$LATEST_TAG" ] && gh release download "$LATEST_TAG" --repo "$REPO" --pattern "edpa-plugin.tar.gz" --dir "$TMPDIR" 2>/dev/null; then
    echo "Downloaded from release $LATEST_TAG."
    mkdir -p "$TMPDIR/edpa"
    tar -xzf "$TMPDIR/edpa-plugin.tar.gz" -C "$TMPDIR/edpa"
  else
    echo "No release asset found, cloning main branch..."
    gh repo clone "$REPO" "$TMPDIR/edpa" -- --depth 1 -q
  fi
else
  # /releases (plural) returns ALL releases including prereleases,
  # most recent first. Take the first matching asset URL.
  RELEASE_URL=$(curl -fsSL "https://api.github.com/repos/$REPO/releases" 2>/dev/null \
    | grep '"browser_download_url".*edpa-plugin.tar.gz' \
    | head -1 | cut -d'"' -f4) || true

  if [ -n "$RELEASE_URL" ]; then
    echo "Downloaded from latest release."
    curl -fsSL "$RELEASE_URL" | tar -xz -C "$TMPDIR"
    mkdir -p "$TMPDIR/edpa/plugin"
    mv "$TMPDIR"/* "$TMPDIR/edpa/plugin/" 2>/dev/null || true
  else
    echo "No release found, downloading main branch..."
    curl -fsSL "https://github.com/$REPO/archive/refs/heads/main.tar.gz" \
      | tar -xz -C "$TMPDIR"
    mv "$TMPDIR"/edpa-* "$TMPDIR/edpa"
  fi
fi

# Copy plugin contents into .claude/ (including hidden files like .mcp.json, .claude-plugin/)
PLUGIN_SRC="$TMPDIR/edpa/plugin"
if [ ! -d "$PLUGIN_SRC" ]; then
  PLUGIN_SRC="$TMPDIR/edpa"
fi
# Copy visible files
cp -R "$PLUGIN_SRC/"* "$TARGET/" 2>/dev/null || true
# Copy hidden files (but not . and ..)
for f in "$PLUGIN_SRC"/.[!.]* "$PLUGIN_SRC"/..?*; do
  [ -e "$f" ] && cp -R "$f" "$TARGET/" 2>/dev/null || true
done

# Make hook scripts executable
chmod +x "$TARGET/edpa/scripts/hooks/"* 2>/dev/null || true

# Create .edpa structure if it doesn't exist
for dir in config backlog/initiatives backlog/epics backlog/features backlog/stories iterations reports snapshots data; do
  mkdir -p ".edpa/$dir"
done

# Copy default config templates (if not already present)
if [ ! -f ".edpa/config/heuristics.yaml" ] && [ -f "$TARGET/edpa/templates/cw_heuristics.yaml.tmpl" ]; then
  cp "$TARGET/edpa/templates/cw_heuristics.yaml.tmpl" ".edpa/config/heuristics.yaml"
  echo "Created .edpa/config/heuristics.yaml from template"
fi
if [ ! -f ".edpa/config/people.yaml" ] && [ -f "$TARGET/edpa/templates/people.yaml.tmpl" ]; then
  cp "$TARGET/edpa/templates/people.yaml.tmpl" ".edpa/config/people.yaml"
  echo "Created .edpa/config/people.yaml from template (edit with your team)"
fi
if [ ! -f ".edpa/config/edpa.yaml" ] && [ -f "$TARGET/edpa/templates/project.yaml.tmpl" ]; then
  cp "$TARGET/edpa/templates/project.yaml.tmpl" ".edpa/config/edpa.yaml"
  echo "Created .edpa/config/edpa.yaml from template (run /edpa:setup to configure)"
fi

# Show installed version
if [ -f "$TARGET/.claude-plugin/plugin.json" ]; then
  VERSION=$(python3 -c "import json; print(json.load(open('$TARGET/.claude-plugin/plugin.json'))['version'])" 2>/dev/null || echo "unknown")
  echo ""
  echo "EDPA $VERSION installed successfully!"
else
  echo ""
  echo "EDPA installed successfully!"
fi

echo ""
echo "Next steps:"
echo "  1. Edit .edpa/config/people.yaml with your team"
echo "  2. Open Claude Code and run:  /edpa setup \"Project Name\""
echo ""
