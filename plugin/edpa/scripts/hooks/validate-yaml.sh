#!/usr/bin/env bash
# EDPA pre-commit hook: validate YAML syntax
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$SCRIPT_DIR/validate_syntax.py" .edpa/
