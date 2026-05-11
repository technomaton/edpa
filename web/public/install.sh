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

# ruamel.yaml — comment-preserving YAML round-trip for the
# collaborator-sync workflow. Without it sync_collaborators.py rejects
# at startup and any people.yaml edit by the bot would lose comments.
if python3 -c 'from ruamel.yaml import YAML' 2>/dev/null; then
  echo "  ruamel.yaml ✓"
else
  echo "  ruamel.yaml not found — installing..."
  pip3 install ruamel.yaml --quiet --break-system-packages 2>/dev/null || pip3 install ruamel.yaml --quiet
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
# skill produces only Markdown timesheets, no edpa-results.xlsx.
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
#
# Read prompts in a `curl … | sh` flow: stdin is the pipe, not the
# terminal, so plain `read` returns EOF immediately and the script
# aborts before the user can type anything. The canonical fix
# (rustup, nvm, oh-my-zsh all do this) is to redirect from /dev/tty,
# which still points at the real terminal even when stdin is piped.
#
# Non-interactive environments (CI, docker build, sub-shells with no
# tty): /dev/tty is unavailable. Skip the prompt and require the
# `EDPA_FORCE_INSTALL=1` env var to overwrite — never silently
# destroy an existing install just because nobody could answer.
if [ -d "$TARGET/edpa" ]; then
  if [ "$EDPA_FORCE_INSTALL" = "1" ]; then
    echo "EDPA_FORCE_INSTALL=1 — overwriting existing $TARGET/edpa/ without prompt."
  elif [ -r /dev/tty ]; then
    printf "Warning: %s/edpa/ already exists. Overwrite? [y/N] " "$TARGET"
    read -r answer < /dev/tty
    case "$answer" in
      [yY]*) echo "Overwriting..." ;;
      *) echo "Aborted."; exit 1 ;;
    esac
  else
    echo "ERROR: $TARGET/edpa/ already exists and no TTY available for prompt."
    echo "Re-run with EDPA_FORCE_INSTALL=1 to overwrite, or remove the directory first."
    exit 1
  fi
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

# Install GitHub Actions workflows. The plugin ships 11 workflows under
# edpa/workflows/ (all prefixed `edpa-*.yml` since v1.18.0-beta), but
# GitHub only runs files in .github/workflows/. Without this copy step,
# workflows sit unused inside the plugin directory and the customer
# never gets branch-check, contributor-detect, sync-*, etc.
#
# Safe defaults: only copy files that don't already exist in the target.
# A user who has hand-edited their workflow keeps the hand-edited version;
# new workflows are installed without surprise overwrites. Use
# `EDPA_FORCE_WORKFLOWS=1` to force overwrites on a deliberate update.
#
# Legacy migration (pre-v1.18.0-beta): the legacy filenames were
# unprefixed (`branch-check.yml`, `sync-*.yml`, etc.). When detected,
# install.sh either:
#   - default: warns and prints `git mv` commands (review before
#     applying — keeps your hand-edits visible in the rename diff)
#   - EDPA_AUTO_MIGRATE=1: renames legacy files automatically (then
#     the normal install path overwrites them only if
#     EDPA_FORCE_WORKFLOWS=1; otherwise your renamed version stays)
LEGACY_WORKFLOWS="branch-check collaborators-sync contributor-detect iteration-close pi-close sync-git-to-projects sync-projects-to-git traceability-check validate-item velocity-track wsjf-calculate"
if [ -d "$TARGET/edpa/workflows" ]; then
  mkdir -p ".github/workflows"

  # Detect legacy unprefixed installations.
  legacy_found=""
  for f in $LEGACY_WORKFLOWS; do
    [ -e ".github/workflows/$f.yml" ] && legacy_found="$legacy_found $f"
  done

  if [ -n "$legacy_found" ]; then
    if [ "$EDPA_AUTO_MIGRATE" = "1" ]; then
      echo "EDPA legacy migration: renaming unprefixed workflows..."
      for f in $legacy_found; do
        if [ -e ".github/workflows/edpa-$f.yml" ]; then
          echo "  skip $f.yml (edpa-$f.yml already exists — delete one manually)"
        else
          mv ".github/workflows/$f.yml" ".github/workflows/edpa-$f.yml"
          echo "  renamed $f.yml -> edpa-$f.yml"
        fi
      done
    else
      echo ""
      echo "EDPA legacy workflow names detected (v1.18.0-beta renamed everything to edpa-* prefix)."
      echo "Run these commands to migrate, OR re-run install with EDPA_AUTO_MIGRATE=1:"
      for f in $legacy_found; do
        echo "  git mv .github/workflows/$f.yml .github/workflows/edpa-$f.yml"
      done
      echo ""
      echo "Continuing install — new edpa-* files will be installed alongside legacy ones."
      echo "After migration, you may see duplicate workflows running until the rename commits."
      echo ""
    fi
  fi

  installed=0
  skipped=0
  for src in "$TARGET"/edpa/workflows/*.yml; do
    [ -e "$src" ] || continue
    name=$(basename "$src")
    dest=".github/workflows/$name"
    if [ -e "$dest" ] && [ "$EDPA_FORCE_WORKFLOWS" != "1" ]; then
      skipped=$((skipped + 1))
    else
      cp "$src" "$dest"
      installed=$((installed + 1))
    fi
  done
  if [ $installed -gt 0 ] || [ $skipped -gt 0 ]; then
    echo "GitHub Actions: $installed workflow(s) installed in .github/workflows/, $skipped already present (skipped)"
    if [ $skipped -gt 0 ] && [ "$EDPA_FORCE_WORKFLOWS" != "1" ]; then
      echo "  (set EDPA_FORCE_WORKFLOWS=1 and re-run to overwrite skipped files)"
    fi
  fi
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
echo "  3. Configure EDPA_TOKEN secret for automated GH Projects sync:"
echo "     https://edpa.technomaton.com/docs/edpa-token-setup"
echo "     (~5 min, optional — without it, run sync.py pull/push manually)"
echo ""
