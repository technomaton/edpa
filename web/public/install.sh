#!/bin/sh
# EDPA Installer — installs the EDPA plugin into .claude/edpa/
# Usage: curl -fsSL https://edpa.technomaton.com/install.sh | sh
set -e

REPO="technomaton/edpa"
BRANCH="main"
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
  gh repo clone "$REPO" "$TMPDIR/edpa" -- --depth 1 --branch "$BRANCH" -q
else
  curl -fsSL "https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz" \
    | tar -xz -C "$TMPDIR"
  mv "$TMPDIR"/edpa-* "$TMPDIR/edpa"
fi

# Copy plugin contents into .claude/
cp -R "$TMPDIR/edpa/plugin/"* "$TARGET/"

# Create .edpa structure if it doesn't exist
for dir in config backlog reports snapshots data; do
  mkdir -p ".edpa/$dir"
done

echo ""
echo "EDPA installed successfully into $TARGET/edpa/"
echo ""
echo "Next steps:"
echo "  1. Open Claude Code in this directory"
echo "  2. Run:  /edpa setup \"Project Name\""
echo ""
