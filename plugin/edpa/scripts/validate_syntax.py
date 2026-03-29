#!/usr/bin/env python3
"""
EDPA Syntax Validator — validates YAML and Python files before commit.

Usage:
    python validate_syntax.py <file1> [file2 ...]

Exit codes:
    0 — all files valid
    1 — one or more files have syntax errors
"""

import ast
import sys

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def validate_yaml(path):
    """Validate YAML syntax. Returns (ok, error_message)."""
    try:
        with open(path) as f:
            yaml.safe_load(f)
        return True, None
    except yaml.YAMLError as e:
        return False, str(e)
    except OSError as e:
        return False, str(e)


def validate_python(path):
    """Validate Python syntax. Returns (ok, error_message)."""
    try:
        with open(path) as f:
            source = f.read()
        ast.parse(source, filename=path)
        return True, None
    except SyntaxError as e:
        return False, f"{e.msg} (line {e.lineno})"
    except OSError as e:
        return False, str(e)


def validate_file(path):
    """Validate a single file based on extension. Returns (ok, error_message)."""
    if path.endswith((".yaml", ".yml")):
        return validate_yaml(path)
    elif path.endswith(".py"):
        return validate_python(path)
    else:
        return True, None  # Skip unknown file types


def main():
    if len(sys.argv) < 2:
        print("Usage: validate_syntax.py <file1> [file2 ...]", file=sys.stderr)
        sys.exit(1)

    files = sys.argv[1:]
    errors = []

    for path in files:
        ok, msg = validate_file(path)
        if not ok:
            errors.append((path, msg))
            print(f"FAIL: {path}: {msg}", file=sys.stderr)

    if errors:
        print(f"\n{len(errors)} file(s) failed validation.", file=sys.stderr)
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
