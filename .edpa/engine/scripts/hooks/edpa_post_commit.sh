#!/bin/sh
# EDPA post-commit hook — generates commit info JSON after git commit.
# Reads Claude Code tool_input JSON from stdin.
# Exit 0 always (non-blocking). Outputs JSON to stdout only for git commit commands.
#
# This hook fires on EVERY Bash tool call in EVERY project once the
# plugin is enabled, so the common path must stay pure shell: a cwd
# walk-up gate (same pattern as update_engine.sh) plus a raw-string
# pre-filter run before any python3 spawn.
set -e

# Gate: only act inside EDPA projects. Walk up from cwd looking for a
# .edpa/ directory; non-EDPA repos exit here, quietly, at zero cost.
DIR=$(pwd)
EDPA_ROOT=""
while [ "$DIR" != "/" ]; do
  if [ -d "$DIR/.edpa" ]; then
    EDPA_ROOT="$DIR"
    break
  fi
  DIR=$(dirname "$DIR")
done
if [ -z "$EDPA_ROOT" ]; then
  exit 0
fi

# Read stdin (Claude Code passes JSON with tool_input)
INPUT=$(cat)

# Cheap pre-filter on the raw JSON: any command matching the
# authoritative `git commit *` case below contains the literal
# substring "git commit" (JSON does not escape spaces), so everything
# else skips without spawning an interpreter.
case "$INPUT" in
    *git\ commit*) ;;
    *) exit 0 ;;
esac

# Extract command from JSON (authoritative check after the pre-filter)
COMMAND=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    cmd = data.get('tool_input', {}).get('command', '')
    print(cmd)
except Exception:
    print('')
" 2>/dev/null)

# Only trigger on git commit (not amend, not other git commands)
case "$COMMAND" in
    git\ commit\ *)
        # Skip amend commits
        case "$COMMAND" in
            *--amend*) exit 0 ;;
        esac
        ;;
    *) exit 0 ;;
esac

# Find the script directory (resolve symlinks)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Run edpa_commit_info.py
python3 "$SCRIPT_DIR/../edpa_commit_info.py" 2>/dev/null || true

exit 0
