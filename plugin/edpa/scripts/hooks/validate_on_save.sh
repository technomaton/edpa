#!/bin/sh
# EDPA validate_on_save hook — validates YAML files when Claude Code writes them.
# Reads Claude Code tool_input JSON from stdin.
# Exit 0 always (non-blocking), but prints validation errors to stderr.
set -e

# Read stdin (Claude Code passes JSON with tool_input)
INPUT=$(cat)

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

# Skip if no file path or not a YAML file
case "$FILE_PATH" in
    *.yaml|*.yml) ;;
    *) exit 0 ;;
esac

# Skip if file doesn't exist
[ -f "$FILE_PATH" ] || exit 0

# Validate YAML syntax (pass path via env to avoid shell injection)
EDPA_VALIDATE_PATH="$FILE_PATH" python3 -c "
import os, sys, yaml
path = os.environ['EDPA_VALIDATE_PATH']
try:
    with open(path) as f:
        yaml.safe_load(f)
except yaml.YAMLError as e:
    print(f'EDPA: YAML validation error in {path}:', file=sys.stderr)
    print(str(e), file=sys.stderr)
except Exception:
    pass
" 2>&1

exit 0
