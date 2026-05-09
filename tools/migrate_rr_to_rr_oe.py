#!/usr/bin/env python3
"""Migrate `rr:` → `rr_oe:` in EDPA backlog YAMLs (v1.14 → v1.15 breaking change).

EDPA v1.15 renames the WSJF Risk Reduction & Opportunity Enablement field
to its full SAFe name. The internal YAML field key changed from `rr` to
`rr_oe`; the GitHub Projects custom field changed from `Risk Reduction`
to `Risk Reduction & Opportunity Enablement`.

This script handles the YAML side. Run from the project root with .edpa/
present. The GitHub field is migrated lazily by sync.py — it accepts the
old `Risk Reduction` field name as a fallback and warns when found, so
you can rename the custom field in the GitHub Projects UI on your own
schedule.

Usage:
  python3 tools/migrate_rr_to_rr_oe.py            # apply changes
  python3 tools/migrate_rr_to_rr_oe.py --dry-run  # show what would change
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Match `rr:` only when it's a YAML key (start of line + optional indent).
# Won't accidentally match `wsjf:`, `rrr:`, or anything inside a string.
PATTERN = re.compile(r"^(\s*)rr:(\s)", re.MULTILINE)


def migrate_file(path: Path, dry_run: bool) -> int:
    text = path.read_text(encoding="utf-8")
    new_text, n = PATTERN.subn(r"\1rr_oe:\2", text)
    if n == 0:
        return 0
    if dry_run:
        print(f"  would migrate {n} line(s) in {path}")
    else:
        path.write_text(new_text, encoding="utf-8")
        print(f"  migrated {n} line(s) in {path}")
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would change without writing.",
    )
    parser.add_argument(
        "--root", default=".",
        help="Project root containing .edpa/ (default: current directory).",
    )
    args = parser.parse_args()

    root = Path(args.root)
    backlog = root / ".edpa" / "backlog"
    if not backlog.is_dir():
        print(f"ERROR: {backlog} not found. Run from a project root with .edpa/ initialized.",
              file=sys.stderr)
        return 1

    yamls = sorted(backlog.rglob("*.yaml"))
    if not yamls:
        print(f"No YAML files under {backlog}.")
        return 0

    total_files = 0
    total_lines = 0
    for p in yamls:
        n = migrate_file(p, args.dry_run)
        if n > 0:
            total_files += 1
            total_lines += n

    verb = "Would migrate" if args.dry_run else "Migrated"
    print(f"\n{verb} {total_lines} `rr:` → `rr_oe:` line(s) across {total_files} file(s).")
    if not args.dry_run and total_lines > 0:
        print("\nNext steps:")
        print("  1. Run `python3 plugin/edpa/scripts/validate_syntax.py` to confirm clean.")
        print("  2. If you sync to GitHub Projects, the existing 'Risk Reduction' custom")
        print("     field keeps working as a fallback. Rename it to 'Risk Reduction &")
        print("     Opportunity Enablement' in the Project settings when convenient.")
        print("  3. Commit the change so future contributors see the new field name.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
