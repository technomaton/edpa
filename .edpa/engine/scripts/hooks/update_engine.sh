#!/bin/sh
# SessionStart hook — auto-vendor engine into .edpa/engine/ when the
# bundled plugin version diverges from the on-disk one.
#
# Mirrors the install.sh / project_setup.py vendor set (scripts/schemas/
# templates/assets + plugin rules + VERSION pin) so users don't have to
# manually re-run /edpa:setup after a `/plugin update`. Fast path is a
# single file compare returning in <50ms.
#
# Skip conditions (in order):
#   1. CLAUDE_PLUGIN_ROOT unset — hook invoked outside Claude Code
#   2. cwd has no .edpa/engine/ — not an EDPA project, or pre-setup
#   3. VERSION matches — already up to date
#   4. installed plugin OLDER than the on-disk engine — never downgrade (D-49)
#   5. .edpa/config/edpa.yaml has auto_update_engine: false — opt-out
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

  # Every-session partial-paste guard (D-77). The rich python audit further down
  # only runs on a version change (cold path), but a partial lefthook paste
  # happens at setup and must surface promptly — every session, not just after a
  # `/plugin update`. Cheap shell tripwire: count EDPA hook basenames wired into
  # the lefthook config (following the extends fragment, if referenced) and spawn
  # python ONLY on a partial wiring (1..3 of 4) for the full UNGUARDED message.
  # 0/4 (not opted in) and 4/4 (correct) stay silent and python-free. Basenames
  # mirror _HOOK_SPECS in project_setup.py.
  for _lf in lefthook.yml lefthook.yaml .lefthook.yml .lefthook.yaml lefthook.toml lefthook.json; do
    [ -f "$PROJECT/$_lf" ] || continue
    _corpus=$(cat "$PROJECT/$_lf" 2>/dev/null)
    case "$_corpus" in
      *lefthook-edpa.yml*)
        _corpus="$_corpus
$(cat "$PROJECT/.edpa/engine/lefthook-edpa.yml" 2>/dev/null)" ;;
    esac
    _wired=0
    for _b in pre-commit-id-safety commit-msg-ticket-attached post-commit-evidence pre-push-id-safety; do
      case "$_corpus" in *"$_b"*) _wired=$((_wired + 1)) ;; esac
    done
    if [ "$_wired" -gt 0 ] && [ "$_wired" -lt 4 ]; then
      python3 "$TARGET/scripts/project_setup.py" --lefthook-audit --root "$PROJECT" 1>&2 || true
    fi
    break
  done
  exit 0
fi

# 3b. Direction guard (D-49) — vendor only FORWARD. The plugin is canonical
# only when it is NEWER; an installed plugin that is *older* than the project's
# committed engine (a developer who hasn't run /plugin update) must never
# rsync-clobber it back to a stale version. Compare as semver; only a *proven*
# downgrade is blocked — an upgrade or a non-semver dev build ("main") falls
# through to the normal vendor path below.
VERSION_ORDER=$(python3 - "$PLUGIN_VERSION" "$LOCAL_VERSION" 2>/dev/null <<'PY' || echo ""
import re, sys
def parse(v):
    m = re.match(r'\s*(\d+)\.(\d+)\.(\d+)', v or "")
    return tuple(int(g) for g in m.groups()) if m else None
plug, loc = parse(sys.argv[1]), parse(sys.argv[2])
if plug is not None and loc is not None and plug < loc:
    print("DOWNGRADE")
PY
)
if [ "$VERSION_ORDER" = "DOWNGRADE" ]; then
  echo "EDPA: installed plugin ($PLUGIN_VERSION) is older than this project's engine ($LOCAL_VERSION) — not downgrading." >&2
  echo "       Run /plugin update to catch up, then restart the session." >&2
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
  # $1 = engine subdir, $2 = optional source parent (default $PLUGIN_SRC).
  # Missing sources are skipped so older plugin payloads stay valid.
  _SRC="${2:-$PLUGIN_SRC}/$1"
  if [ ! -d "$_SRC" ]; then
    return 0
  fi
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete "$_SRC/" "$TARGET/$1/"
  else
    rm -rf "$TARGET/$1"
    cp -R "$_SRC" "$TARGET/"
  fi
}

VENDOR scripts
VENDOR schemas
VENDOR templates
VENDOR assets
# Plugin rules live at $PLUGIN_ROOT/rules (one level above edpa/), NOT
# $PLUGIN_SRC/rules — the same trap project_setup.py's vendor step
# documents. Getting this wrong silently ships an engine with stale rules
# under a freshly stamped VERSION.
VENDOR rules "$PLUGIN_ROOT"

echo "$PLUGIN_VERSION" > "$TARGET/VERSION"
chmod +x "$TARGET/scripts/hooks/"* 2>/dev/null || true

# Single-file lefthook fragment for `extends:` — vendored to the engine root so
# a one-line extends in the user's lefthook.yml wires in all four hooks and
# tracks plugin updates (no re-paste). VENDOR only handles subdirs, so copy it
# explicitly.
if [ -f "$PLUGIN_SRC/lefthook-edpa.yml" ]; then
  cp "$PLUGIN_SRC/lefthook-edpa.yml" "$TARGET/lefthook-edpa.yml"
fi

# Self-heal git hooks after an engine update. A version bump can leave
# .git/hooks/ holding a stale snapshot, or another tool (e.g. lefthook) may
# have clobbered EDPA's hooks — which silently stops contribution evidence
# from firing. Re-register ONLY when the project already opted into hooks
# (an EDPA-owned hook is present, or lefthook is in use), so a version bump
# never forces hooks on a repo that deliberately skipped them.
#
# The opt-in probe matches on the hook BODY, not just the sentinel (D-78).
# Gating on EDPA-MANAGED-HOOK alone deadlocked exactly the repos that needed
# healing: a pre-sentinel hook carries no sentinel, so self-heal never fired, so
# the hook never got re-stamped, so it never gained a sentinel. Every EDPA hook
# of every generation invokes a script under .edpa/engine/scripts/, so that path
# is the durable opt-in signal. It also matches a hook the user chained EDPA
# into by hand — opt-in too, and --refresh-hooks leaves foreign files untouched,
# so the broader probe costs nothing.
_has_lefthook() {
  for _lf in lefthook.yml lefthook.yaml .lefthook.yml .lefthook.yaml lefthook.toml lefthook.json; do
    [ -f "$PROJECT/$_lf" ] && return 0
  done
  return 1
}
if _has_lefthook; then
  # If the repo wires EDPA via `extends:` to the vendored fragment, lefthook's
  # sync only watches the MAIN config's mtime — the fragment just changed under
  # it, so drop lefthook's checksum (a git-internal file, never the user's
  # config) to force a re-sync on the next git op. Only when the fragment is
  # actually referenced, so inline-paste users aren't nudged into a needless
  # reinstall.
  for _lf in lefthook.yml lefthook.yaml .lefthook.yml .lefthook.yaml lefthook.toml lefthook.json; do
    if [ -f "$PROJECT/$_lf" ] && grep -q "lefthook-edpa.yml" "$PROJECT/$_lf" 2>/dev/null; then
      rm -f "$PROJECT/.git/info/lefthook.checksum"
      break
    fi
  done
  # Content-aware audit: silent when 0/4 (repo never opted in) or 4/4 (all
  # wired), loud + specific only on a partial paste (guards silently missing).
  # Non-blocking (|| true) — advisory only, must never break a session start.
  python3 "$TARGET/scripts/project_setup.py" --lefthook-audit --root "$PROJECT" 1>&2 || true
elif grep -qE "EDPA-MANAGED-HOOK|\.edpa/engine/scripts/" "$PROJECT"/.git/hooks/* 2>/dev/null; then
  echo "EDPA: re-registering git hooks after update..." >&2
  python3 "$TARGET/scripts/project_setup.py" --refresh-hooks --root "$PROJECT" 1>&2 || true
fi

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
