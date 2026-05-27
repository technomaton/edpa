#!/bin/sh
# EDPA Installer — installs the EDPA plugin into the current project.
# Usage: curl -fsSL https://edpa.technomaton.com/install.sh | sh
#
# Two install paths exist for EDPA:
#
#   1. Claude Code marketplace  → `/plugin install tm-edpa@technomaton-hub`
#      or `/plugin install edpa@technomaton-edpa`. Pulls plugin payload from
#      technomaton/edpa@plugin into Claude Code's plugin cache. Then the
#      user runs `/edpa:setup` which vendors the engine to `.edpa/engine/`
#      and provisions the project.
#
#   2. This script (curl|sh)    → for Cursor, Codex CLI, or any environment
#      that doesn't speak the Claude Code plugin protocol. Downloads the
#      same plugin payload from a GitHub Release tarball, vendors the
#      engine to `.edpa/engine/`, bootstraps `.edpa/`, and prints
#      next-step instructions for project provisioning.
#
# This script is intentionally minimal: it vendors `plugin/edpa/{scripts,
# schemas,templates}/` into `.edpa/engine/` so CI workflows and non-CC tools
# can find the engine. It does NOT install pip packages, does NOT copy CI
# workflows (that's project_setup.py / /edpa:setup), and does NOT touch
# `.claude/`. The result is a project root that has `.edpa/` and nothing
# else added.
set -e

REPO="technomaton/edpa"
TARGET=".edpa/engine"
WITH_SERVER=0

# Parse args (only --with-server supported today; everything else stays
# legacy for backwards compatibility).
for arg in "$@"; do
  case "$arg" in
    --with-server) WITH_SERVER=1 ;;
    *) ;;
  esac
done

echo "EDPA Installer"
echo "=============="

# --- Prereq existence checks ---
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
  echo "  pip3 not found — install Python deps manually after this script."
fi

echo ""

# --- Idempotency guard ---
#
# Read prompts in a `curl … | sh` flow: stdin is the pipe, not the
# terminal, so plain `read` returns EOF immediately. The canonical fix
# (rustup, nvm, oh-my-zsh all do this) is to redirect from /dev/tty,
# which still points at the real terminal even when stdin is piped.
#
# Non-interactive environments (CI, docker build, sub-shells with no
# tty): /dev/tty is unavailable. Skip the prompt and require the
# `EDPA_FORCE_INSTALL=1` env var to overwrite.
if [ -d "$TARGET" ]; then
  if [ "$EDPA_FORCE_INSTALL" = "1" ]; then
    echo "EDPA_FORCE_INSTALL=1 — overwriting existing $TARGET/ without prompt."
  elif [ -r /dev/tty ]; then
    printf "Warning: %s already exists. Overwrite? [y/N] " "$TARGET"
    read -r answer < /dev/tty
    case "$answer" in
      [yY]*) echo "Overwriting..." ;;
      *) echo "Aborted."; exit 1 ;;
    esac
  else
    echo "ERROR: $TARGET/ already exists and no TTY available for prompt."
    echo "Re-run with EDPA_FORCE_INSTALL=1 to overwrite, or remove the directory first."
    exit 1
  fi
fi

# --- Download plugin payload ---
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

echo "Downloading EDPA plugin..."
# Prefer the most recent release tag (including prereleases — GitHub's
# /releases/latest API skips prereleases, which would silently fall back
# to a main-branch clone whenever every published release is marked beta).
if command -v gh >/dev/null 2>&1; then
  LATEST_TAG=$(gh release list --repo "$REPO" --limit 1 --json tagName --jq '.[0].tagName' 2>/dev/null || true)
  if [ -n "$LATEST_TAG" ] && gh release download "$LATEST_TAG" --repo "$REPO" --pattern "edpa-plugin.tar.gz" --dir "$TMPDIR" 2>/dev/null; then
    echo "Downloaded from release $LATEST_TAG."
    mkdir -p "$TMPDIR/edpa"
    tar -xzf "$TMPDIR/edpa-plugin.tar.gz" -C "$TMPDIR/edpa"
    PLUGIN_VERSION="$LATEST_TAG"
  else
    echo "No release asset found, cloning main branch..."
    gh repo clone "$REPO" "$TMPDIR/edpa" -- --depth 1 -q
    PLUGIN_VERSION="main"
  fi
else
  RELEASE_URL=$(curl -fsSL "https://api.github.com/repos/$REPO/releases" 2>/dev/null \
    | grep '"browser_download_url".*edpa-plugin.tar.gz' \
    | head -1 | cut -d'"' -f4) || true

  if [ -n "$RELEASE_URL" ]; then
    echo "Downloaded from latest release."
    curl -fsSL "$RELEASE_URL" | tar -xz -C "$TMPDIR"
    mkdir -p "$TMPDIR/edpa/plugin"
    mv "$TMPDIR"/* "$TMPDIR/edpa/plugin/" 2>/dev/null || true
    PLUGIN_VERSION="latest-release"
  else
    echo "No release found, downloading main branch..."
    curl -fsSL "https://github.com/$REPO/archive/refs/heads/main.tar.gz" \
      | tar -xz -C "$TMPDIR"
    mv "$TMPDIR"/edpa-* "$TMPDIR/edpa"
    PLUGIN_VERSION="main"
  fi
fi

PLUGIN_SRC="$TMPDIR/edpa/plugin"
if [ ! -d "$PLUGIN_SRC" ]; then
  PLUGIN_SRC="$TMPDIR/edpa"
fi

# --- Vendor engine into .edpa/engine/ ---
echo ""
echo "Vendoring engine into $TARGET/..."
mkdir -p "$TARGET"
cp -R "$PLUGIN_SRC/edpa/scripts"   "$TARGET/"
cp -R "$PLUGIN_SRC/edpa/schemas"   "$TARGET/"
cp -R "$PLUGIN_SRC/edpa/templates" "$TARGET/"
if [ -d "$PLUGIN_SRC/rules" ]; then
  cp -R "$PLUGIN_SRC/rules" "$TARGET/"
fi

# Pin the vendored plugin version so /edpa:setup --update-engine and CI
# workflows can sanity-check the engine tree.
if [ -f "$PLUGIN_SRC/.claude-plugin/plugin.json" ]; then
  PINNED=$(python3 -c "import json; print(json.load(open('$PLUGIN_SRC/.claude-plugin/plugin.json'))['version'])" 2>/dev/null || echo "$PLUGIN_VERSION")
else
  PINNED="$PLUGIN_VERSION"
fi
echo "$PINNED" > "$TARGET/VERSION"

# Make hook shell scripts executable (used by EDPA plugin hooks if user
# also runs this in a Claude Code project — harmless otherwise).
chmod +x "$TARGET/scripts/hooks/"* 2>/dev/null || true

echo "  scripts:   $(find $TARGET/scripts -maxdepth 1 -name '*.py' | wc -l | tr -d ' ') Python modules"
echo "  schemas:   $(find $TARGET/schemas -maxdepth 1 -name '*.json' | wc -l | tr -d ' ') JSON schemas"
echo "  templates: $(find $TARGET/templates -maxdepth 1 -name '*.tmpl' | wc -l | tr -d ' ') YAML templates"
echo "  pinned:    $PINNED"

# --- Bootstrap .edpa/ data tree + seed configs from templates ---
echo ""
echo "Bootstrapping .edpa/ data tree..."
for dir in config backlog/initiatives backlog/epics backlog/features backlog/stories iterations reports snapshots data; do
  mkdir -p ".edpa/$dir"
done

# Seed people.yaml + edpa.yaml from canonical templates. Engine reads
# canonical CW heuristics from .edpa/engine/templates/cw_heuristics.yaml.tmpl
# directly — no .edpa/config/heuristics.yaml is needed and would be ignored.
if [ ! -f ".edpa/config/people.yaml" ] && [ -f "$TARGET/templates/people.yaml.tmpl" ]; then
  cp "$TARGET/templates/people.yaml.tmpl" ".edpa/config/people.yaml"
  echo "  Created .edpa/config/people.yaml (edit with your team)"
fi
if [ ! -f ".edpa/config/edpa.yaml" ] && [ -f "$TARGET/templates/edpa.yaml.tmpl" ]; then
  cp "$TARGET/templates/edpa.yaml.tmpl" ".edpa/config/edpa.yaml"
  echo "  Created .edpa/config/edpa.yaml (edit project.name + governance metadata)"
elif [ -f ".edpa/config/edpa.yaml" ]; then
  python3 - "$PINNED" ".edpa/config/edpa.yaml" <<'PYEOF'
import sys, re
version, path = sys.argv[1], sys.argv[2]
text = open(path).read()
new_text = re.sub(r'(methodology:\s*"?EDPA )[^"\n]+("?)', rf'\g<1>{version}\2', text)
if new_text != text:
    open(path, "w").write(new_text)
    print(f"  Updated edpa.yaml governance.methodology → EDPA {version}")
PYEOF
fi

touch ".edpa/sync_state.json"

# --- Optional: PI planning server vendoring (--with-server flag) ---
if [ "$WITH_SERVER" = "1" ]; then
  SERVER_SRC="$TMPDIR/edpa/plugin/tools/pi-planning"
  SERVER_DST=".claude/edpa/server"
  if [ -d "$SERVER_SRC" ]; then
    echo ""
    echo "Vendoring PI planning server (--with-server)..."
    mkdir -p "$SERVER_DST"
    cp -R "$SERVER_SRC/." "$SERVER_DST/"
    echo "  Vendored to $SERVER_DST/"
    echo "  Build deps + dist: cd $SERVER_DST && npm install && npm run build"
    echo "  Start later: /edpa:server start"
  else
    echo ""
    echo "  --with-server requested but server source not in payload — skipping."
  fi
else
  echo ""
  echo "  (Optional: re-run with --with-server to vendor the PI planning UI.)"
fi

echo ""
echo "EDPA $PINNED installed."
echo ""
echo "Next steps:"
echo ""
echo "  Claude Code users:"
echo "    Re-run setup via /edpa:setup to provision GitHub Project + CI workflows."
echo "    /edpa:setup will overlay the same .edpa/engine/ tree and prompt for"
echo "    team details, then push to GitHub Projects."
echo ""
echo "  Other tools (Cursor, Codex CLI, raw):"
echo "    1. Install Python deps:"
echo "         pip3 install pyyaml ruamel.yaml openpyxl"
echo "         (mcp package only needed if you want the MCP server)"
echo "    2. Edit team and project metadata:"
echo "         .edpa/config/people.yaml"
echo "         .edpa/config/edpa.yaml"
echo "    3. Run project provisioning manually:"
echo "         python3 .edpa/engine/scripts/project_setup.py --org <org> --repo <repo> \\"
echo "           --project-title \"<your-project-name> Governance\""
echo "    4. Copy CI workflows:"
echo "         mkdir -p .github/workflows"
echo "         cp .edpa/engine/templates/../workflows/*.yml .github/workflows/  # if present"
echo "         # (release tarball doesn't ship workflows separately; pull them"
echo "         # from the plugin source tree at github.com/$REPO/tree/main/plugin/edpa/workflows)"
echo ""
echo "  CI sync (optional, ~5 min):"
echo "    Configure the EDPA_TOKEN secret so GH Actions workflows can run."
echo "    https://edpa.technomaton.com/docs/edpa-token-setup"
echo ""
