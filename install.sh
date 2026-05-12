#!/bin/sh
# EDPA Installer — installs the EDPA plugin into .claude/
# Usage: curl -fsSL https://edpa.technomaton.com/install.sh | sh
#
# Two install paths exist for EDPA:
#
#   1. Claude Code marketplace  → `/plugin install tm-edpa@technomaton-hub`
#      Pulls plugin payload from technomaton/edpa@plugin directly.
#      Python deps install automatically via the plugin's SessionStart hook.
#      .github/workflows/ get copied by /edpa:setup on first invocation.
#
#   2. This script (curl|sh)    → for Cursor, Codex CLI, or any environment
#      that doesn't speak the Claude Code plugin protocol. Downloads the
#      same plugin payload from a GitHub Release tarball, places it under
#      .claude/, and bootstraps .edpa/. After install, the user must:
#        - install Python deps:   pip3 install -r .claude/requirements.txt
#        - copy CI workflows:     run /edpa:setup or python3 .claude/edpa/scripts/preflight.py
#
# This script is intentionally minimal: it does NOT install pip packages
# or copy CI workflows. Both belong to /edpa:setup, which is the single
# source of truth across both install paths.
set -e

REPO="technomaton/edpa"
TARGET=".claude"

echo "EDPA Installer"
echo "=============="

# --- Prereq existence checks (no pip installs — see header) ---
echo ""
echo "Checking prerequisites..."

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

if command -v git >/dev/null 2>&1; then
  echo "  git ✓"
else
  echo "WARNING: git not found. EDPA requires git for evidence detection."
fi

if command -v gh >/dev/null 2>&1; then
  echo "  GitHub CLI ✓"
else
  echo "  GitHub CLI not found (optional — needed for /edpa setup and sync)"
fi

if command -v pip3 >/dev/null 2>&1; then
  echo "  pip3 ✓"
else
  echo "  pip3 not found — install Python deps manually after this script:"
  echo "       pip3 install -r .claude/requirements.txt"
fi

echo ""

# --- Idempotency guard ---
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

mkdir -p "$TARGET"

# --- Download plugin payload ---
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

# --- Bootstrap .edpa/ data directory + seed templates ---
for dir in config backlog/initiatives backlog/epics backlog/features backlog/stories iterations reports snapshots data; do
  mkdir -p ".edpa/$dir"
done

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
echo ""
echo "  Claude Code users:"
echo "    1. Restart Claude Code (SessionStart hook will auto-install Python deps)"
echo "    2. Run  /edpa:setup \"Project Name\"  to provision GitHub Projects + workflows"
echo ""
echo "  Other tools (Cursor, Codex CLI, raw):"
echo "    1. Install Python deps:"
echo "         pip3 install -r .claude/requirements.txt"
echo "    2. Run preflight + setup wizard:"
echo "         python3 .claude/edpa/scripts/preflight.py --org <your-org>"
echo "         python3 .claude/edpa/scripts/project_setup.py --org <org> --repo <repo>"
echo ""
echo "  CI sync (optional, ~5 min):"
echo "    Configure the EDPA_TOKEN secret so GH Actions workflows can run."
echo "    https://edpa.technomaton.com/docs/edpa-token-setup"
echo ""
