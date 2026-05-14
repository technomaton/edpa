#!/bin/sh
# SessionStart hook — auto-vendor engine into .edpa/engine/ when the
# bundled plugin version diverges from the on-disk one.
#
# Mirrors the install.sh vendor path (scripts/schemas/templates +
# VERSION pin) so users don't have to manually re-run /edpa:setup
# after a `/plugin update`. Fast path is a single file compare
# returning in <50ms.
#
# Skip conditions (in order):
#   1. CLAUDE_PLUGIN_ROOT unset — hook invoked outside Claude Code
#   2. cwd has no .edpa/engine/ — not an EDPA project, or pre-setup
#   3. VERSION matches — already up to date
#   4. .edpa/config/edpa.yaml has auto_update_engine: false — opt-out
#
# On version mismatch:
#   - rsync (or cp -R fallback) plugin engine -> .edpa/engine/
#   - Write new VERSION
#   - Chmod hook scripts executable
#   - Log the update on stderr
#
# Legacy .yaml backlog check (always runs, regardless of update):
#   - If .edpa/backlog/**/*.yaml exists, print one-line warning
#     pointing at the migration script. v1.20.0+ requires .md.

set -e

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"

# 1. Hook called outside Claude Code (CI, manual test) — exit quietly.
if [ -z "$PLUGIN_ROOT" ]; then
  exit 0
fi

# 2. Walk up from cwd looking for .edpa/engine/. Bail when we hit /.
TARGET=""
DIR=$(pwd)
while [ "$DIR" != "/" ]; do
  if [ -d "$DIR/.edpa/engine" ]; then
    TARGET="$DIR/.edpa/engine"
    PROJECT="$DIR"
    break
  fi
  DIR=$(dirname "$DIR")
done

if [ -z "$TARGET" ]; then
  exit 0
fi

# 3. Compare versions. Plugin source is canonical.
PLUGIN_SRC="$PLUGIN_ROOT/edpa"
PLUGIN_VERSION_FILE="$PLUGIN_ROOT/.claude-plugin/plugin.json"
LOCAL_VERSION_FILE="$TARGET/VERSION"

if [ ! -f "$PLUGIN_VERSION_FILE" ]; then
  # Plugin root layout we don't recognize — bail.
  exit 0
fi

PLUGIN_VERSION=$(python3 -c "import json; print(json.load(open('$PLUGIN_VERSION_FILE'))['version'])" 2>/dev/null || echo "")
LOCAL_VERSION=$(cat "$LOCAL_VERSION_FILE" 2>/dev/null || echo "")

if [ -z "$PLUGIN_VERSION" ]; then
  # Can't determine plugin version — refuse to touch the engine tree.
  exit 0
fi

if [ "$PLUGIN_VERSION" = "$LOCAL_VERSION" ]; then
  # Warm path. Still run the legacy-yaml warning.
  _warn_legacy_yaml() {
    LEGACY_COUNT=$(find "$PROJECT/.edpa/backlog" -name "*.yaml" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$LEGACY_COUNT" != "0" ] && [ -n "$LEGACY_COUNT" ]; then
      echo "EDPA: $LEGACY_COUNT legacy .yaml backlog file(s) found." >&2
      echo "       v1.20.0+ uses .md + YAML frontmatter." >&2
      echo "       Migrate with: python3 $TARGET/scripts/migrate_backlog_yaml_to_md.py" >&2
    fi
  }
  _warn_legacy_yaml
  exit 0
fi

# 4. Opt-out check. Cheap grep so we don't pull in PyYAML at hook time.
EDPA_CONFIG="$PROJECT/.edpa/config/edpa.yaml"
if [ -f "$EDPA_CONFIG" ]; then
  if grep -qE '^[[:space:]]*auto_update_engine:[[:space:]]*false' "$EDPA_CONFIG" 2>/dev/null; then
    echo "EDPA: engine update skipped (auto_update_engine: false in edpa.yaml)" >&2
    echo "       plugin=$PLUGIN_VERSION  local=$LOCAL_VERSION" >&2
    exit 0
  fi
fi

# 5. Vendor — rsync when available (preserves timestamps), fall back to cp -R.
echo "EDPA: updating engine $LOCAL_VERSION → $PLUGIN_VERSION..." >&2

VENDOR() {
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete "$PLUGIN_SRC/$1/" "$TARGET/$1/"
  else
    rm -rf "$TARGET/$1"
    cp -R "$PLUGIN_SRC/$1" "$TARGET/"
  fi
}

VENDOR scripts
VENDOR schemas
VENDOR templates

echo "$PLUGIN_VERSION" > "$TARGET/VERSION"
chmod +x "$TARGET/scripts/hooks/"* 2>/dev/null || true

echo "EDPA: engine updated. $(find "$TARGET/scripts" -maxdepth 1 -name '*.py' | wc -l | tr -d ' ') Python modules, $(find "$TARGET/templates" -maxdepth 1 -name '*.tmpl' | wc -l | tr -d ' ') templates." >&2

# Legacy backlog format check after update — the .md migration arrived
# in 1.20.0; surface it whenever stale .yaml files linger.
LEGACY_COUNT=$(find "$PROJECT/.edpa/backlog" -name "*.yaml" 2>/dev/null | wc -l | tr -d ' ')
if [ "$LEGACY_COUNT" != "0" ] && [ -n "$LEGACY_COUNT" ]; then
  echo "EDPA: $LEGACY_COUNT legacy .yaml backlog file(s) found." >&2
  echo "       v1.20.0+ uses .md + YAML frontmatter. Sync/engine will ignore .yaml items." >&2
  echo "       Migrate with: python3 $TARGET/scripts/migrate_backlog_yaml_to_md.py" >&2
fi

exit 0
