#!/bin/sh
# EDPA Installer — installs the EDPA plugin into .claude/edpa/
# Usage: curl -fsSL https://edpa.technomaton.com/install.sh | sh
set -e

REPO="technomaton/edpa"
TARGET=".claude"

echo "EDPA Installer"
echo "=============="

# Warn if .claude/edpa already exists
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
if command -v gh >/dev/null 2>&1; then
  # Try latest release first, fall back to main branch
  if gh release download --repo "$REPO" --pattern "edpa-plugin.tar.gz" --dir "$TMPDIR" 2>/dev/null; then
    echo "Downloaded from latest release."
    mkdir -p "$TMPDIR/edpa"
    tar -xzf "$TMPDIR/edpa-plugin.tar.gz" -C "$TMPDIR/edpa"
  else
    echo "No release found, cloning main branch..."
    gh repo clone "$REPO" "$TMPDIR/edpa" -- --depth 1 -q
  fi
else
  # Try release tarball first, fall back to main branch archive
  RELEASE_URL=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null \
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
if [ -d "$TMPDIR/edpa/plugin" ]; then
  cp -R "$TMPDIR/edpa/plugin/"* "$TARGET/"
  cp -R "$TMPDIR/edpa/plugin/".* "$TARGET/" 2>/dev/null || true
else
  cp -R "$TMPDIR/edpa/"* "$TARGET/"
  cp -R "$TMPDIR/edpa/".* "$TARGET/" 2>/dev/null || true
fi

# Make hook scripts executable
chmod +x "$TARGET/edpa/scripts/hooks/"* 2>/dev/null || true

# Create .edpa structure if it doesn't exist
for dir in config backlog/initiatives backlog/epics backlog/features backlog/stories iterations reports snapshots data; do
  mkdir -p ".edpa/$dir"
done

# Show installed version
if [ -f "$TARGET/.claude-plugin/plugin.json" ]; then
  VERSION=$(python3 -c "import json; print(json.load(open('$TARGET/.claude-plugin/plugin.json'))['version'])" 2>/dev/null || echo "unknown")
  echo ""
  echo "EDPA $VERSION installed successfully into $TARGET/edpa/"
else
  echo ""
  echo "EDPA installed successfully into $TARGET/edpa/"
fi

echo ""
echo "Next steps:"
echo "  1. Open Claude Code in this directory"
echo "  2. Run:  /edpa setup \"Project Name\""
echo ""
