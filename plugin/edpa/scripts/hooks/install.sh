#!/bin/sh
# Thin delegator — the real EDPA git-hook registration lives in
# project_setup.py (script-first: one implementation, thin callers). Kept for
# the documented `sh .edpa/engine/scripts/hooks/install.sh` path.
#
# It installs into .git/hooks/ (ownership-tracked, foreign hooks left alone)
# or prints a paste-ready snippet when lefthook is detected. The old
# `git config core.hooksPath` mechanism is gone: it pointed at a stale path
# and silently fought lefthook / the .git/hooks/ copy path.
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
[ -z "$ROOT" ] && { echo "ERROR: not a git repository." >&2; exit 1; }

SETUP="$ROOT/.edpa/engine/scripts/project_setup.py"
if [ ! -f "$SETUP" ]; then
    echo "ERROR: EDPA engine not found at $SETUP" >&2
    echo "Run /edpa:setup (or the curl|sh installer) to vendor the engine first." >&2
    exit 1
fi

exec python3 "$SETUP" --refresh-hooks --root "$ROOT"
