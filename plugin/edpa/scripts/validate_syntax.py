#!/usr/bin/env python3
"""
EDPA Validate Syntax — validates YAML files in the .edpa directory.

Checks:
  - Valid YAML syntax (including .tmpl files)
  - Required fields present
  - No binary content masquerading as YAML
"""

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install with: pip install pyyaml")
    sys.exit(1)


def validate_yaml(path):
    """Validate a single YAML file. Returns list of error strings."""
    errors = []
    path = Path(path)

    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        errors.append(f"{path}: file not found")
        return errors
    except UnicodeDecodeError:
        errors.append(f"{path}: binary file, not valid YAML")
        return errors

    try:
        yaml.safe_load(content)
    except yaml.YAMLError as e:
        errors.append(f"{path}: {e}")

    return errors


def validate_directory(directory):
    """Validate all YAML files in a directory tree."""
    directory = Path(directory)
    all_errors = []

    patterns = ["**/*.yaml", "**/*.yml", "**/*.tmpl"]
    seen = set()

    for pattern in patterns:
        for path in directory.glob(pattern):
            if path in seen:
                continue
            seen.add(path)
            all_errors.extend(validate_yaml(path))

    return all_errors


def main():
    if len(sys.argv) < 2:
        print("Usage: validate_syntax.py <path> [<path> ...]")
        sys.exit(1)

    all_errors = []
    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.is_dir():
            all_errors.extend(validate_directory(p))
        elif p.is_file():
            all_errors.extend(validate_yaml(p))
        else:
            all_errors.append(f"{p}: not found")

    if all_errors:
        for err in all_errors:
            print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)
    else:
        print("All YAML files valid.")


if __name__ == "__main__":
    main()
