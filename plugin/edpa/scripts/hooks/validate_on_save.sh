#!/bin/sh
# EDPA validate_on_save hook — validates YAML, JSON, and Python files when Claude Code writes them.
# Reads Claude Code tool_input JSON from stdin.
# Exit 0 always (non-blocking), but prints validation errors to stderr.
#
# This hook fires on EVERY Edit/Write tool call in EVERY project once
# the plugin is enabled, so the common path must stay pure shell: a cwd
# walk-up gate (same pattern as update_engine.sh) plus a raw-string
# extension pre-filter run before any python3 spawn, and only files
# that themselves live inside an EDPA project get validated.
set -e

# Gate: only act inside EDPA projects. Walk up from cwd looking for a
# .edpa/ directory; non-EDPA repos exit here, quietly, at zero cost.
DIR=$(pwd)
EDPA_CWD_ROOT=""
while [ "$DIR" != "/" ]; do
  if [ -d "$DIR/.edpa" ]; then
    EDPA_CWD_ROOT="$DIR"
    break
  fi
  DIR=$(dirname "$DIR")
done
if [ -z "$EDPA_CWD_ROOT" ]; then
  exit 0
fi

# Read stdin (Claude Code passes JSON with tool_input)
INPUT=$(cat)

# Cheap pre-filter on the raw JSON: a matching file_path must contain
# one of the supported extensions as a literal substring, so anything
# else (e.g. .ts/.go edits) skips without spawning an interpreter. The
# real extension check on the parsed file_path below stays authoritative.
case "$INPUT" in
    *.yaml*|*.yml*|*.md*|*.json*|*.py*) ;;
    *) exit 0 ;;
esac

# Extract file_path from JSON
FILE_PATH=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    path = data.get('tool_input', {}).get('file_path', '')
    print(path)
except Exception:
    print('')
" 2>/dev/null)

# Skip if no file path or not a supported file type
case "$FILE_PATH" in
    *.yaml|*.yml|*.md|*.json|*.py) ;;
    *) exit 0 ;;
esac

# Skip if file doesn't exist
[ -f "$FILE_PATH" ] || exit 0

# Restrict validation to files that live inside an EDPA project.
# file_path may lie outside cwd, so walk up from the file's own
# directory looking for .edpa/ — unrelated projects' files must not
# get EDPA-validated just because the session cwd is an EDPA project.
FILE_DIR=$(cd "$(dirname "$FILE_PATH")" 2>/dev/null && pwd) || FILE_DIR=""
if [ -z "$FILE_DIR" ]; then
  exit 0
fi
DIR="$FILE_DIR"
FILE_EDPA_ROOT=""
while [ "$DIR" != "/" ]; do
  if [ -d "$DIR/.edpa" ]; then
    FILE_EDPA_ROOT="$DIR"
    break
  fi
  DIR=$(dirname "$DIR")
done
if [ -z "$FILE_EDPA_ROOT" ]; then
  exit 0
fi

# Validate syntax (pass path via env to avoid shell injection)
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT_DIR="$SCRIPT_DIR" EDPA_VALIDATE_PATH="$FILE_PATH" python3 -c "
import os, sys
path = os.environ['EDPA_VALIDATE_PATH']
script_dir = os.environ.get('SCRIPT_DIR', '')
sys.path.insert(0, script_dir)
try:
    from validate_syntax import validate_file
    # validate_file returns an (errors, warnings) tuple — unpack it.
    # Iterating the tuple itself printed 'EDPA: validation error: []'
    # twice for perfectly valid files.
    errors, _warnings = validate_file(path)
    for e in errors:
        print(f'EDPA: validation error: {e}', file=sys.stderr)
except Exception as exc:
    # Non-blocking hook: failure to validate must not block the user's edit.
    # Surface the cause on stderr so debugging is still possible without
    # polluting stdout (which Claude Code may parse for hook output).
    print(f'EDPA: validate hook internal error: {exc}', file=sys.stderr)
"
# stderr stays on stderr — earlier '2>&1' redirected validation errors
# into stdout, which made Claude Code render them as if they were tool
# output rather than diagnostics.

# Iteration-schema validation: when the edited file is .edpa/iterations/*.yaml,
# also run the structural validator so date gaps, weeks mismatches, etc.
# surface immediately. Non-blocking — exit 0 even if errors are found.
case "$FILE_PATH" in
    */.edpa/iterations/*.yaml)
        VALIDATOR="$SCRIPT_DIR/validate_iterations.py"
        if [ -f "$VALIDATOR" ]; then
            python3 "$VALIDATOR" 2>&1 | grep -E "^(✗|⚠)" | sed 's/^/EDPA: /' >&2 || true
        fi
        ;;
esac

exit 0
