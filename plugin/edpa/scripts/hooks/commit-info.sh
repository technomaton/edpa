#!/usr/bin/env bash
# EDPA post-commit hook: generate commit info
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$SCRIPT_DIR/edpa_commit_info.py"
