#!/usr/bin/env python3
"""Migrate `.edpa/backlog/**/*.yaml` to `.md` with YAML frontmatter + body.

Idempotent: if the destination `.md` already exists, the source `.yaml` is
left alone (the operator must resolve the conflict). Otherwise:

1. Parse the YAML file.
2. Pop the prose fields (description, acceptance_criteria, refinement_notes,
   notes) — they become the Markdown body via ``format_body_sections``.
3. Write the remaining metadata + body to ``<stem>.md``.
4. Delete the original ``<stem>.yaml``.

Run with ``--dry-run`` to preview the rewrite. Pass paths to limit the
search; default is ``.edpa/backlog/``.
"""

from __future__ import annotations

try:  # best-effort UTF-8 stdio on legacy Windows consoles (cp1250)
    import _console  # noqa: F401
except ImportError:
    pass
import argparse
import sys
from pathlib import Path

# The script lives alongside the engine — both as the source-of-truth
# under plugin/edpa/scripts/ (this repo) and as the vendored copy under
# <project>/.edpa/engine/scripts/ (downstream installs). Either way,
# `_md_frontmatter` sits in the same directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from _md_frontmatter import BODY_SECTIONS, format_body_sections, save_md  # noqa: E402


def migrate_file(path: Path, dry_run: bool = False) -> tuple[bool, str]:
    """Migrate one .yaml → .md file. Returns (changed, message)."""
    if path.suffix != ".yaml":
        return False, f"skip (not .yaml): {path}"
    dest = path.with_suffix(".md")
    if dest.exists():
        return False, f"skip (.md already exists): {dest}"

    try:
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
    except (yaml.YAMLError, OSError) as exc:
        return False, f"ERROR loading {path}: {exc}"

    if not isinstance(data, dict):
        return False, f"skip (not a YAML mapping): {path}"

    prose = {k: data[k] for k in BODY_SECTIONS if k in data and data[k]}
    frontmatter = {k: v for k, v in data.items() if k not in BODY_SECTIONS}
    body = format_body_sections(prose)

    msg = (
        f"{path.name} → {dest.name} "
        f"({len(frontmatter)} fm fields, {len(prose)} prose fields, "
        f"body={len(body)} chars)"
    )
    if dry_run:
        return True, "DRY-RUN " + msg

    save_md(dest, frontmatter, body)
    path.unlink()
    return True, msg


def collect_targets(roots: list[Path]) -> list[Path]:
    seen: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix == ".yaml":
            seen.append(root)
        elif root.is_dir():
            seen.extend(sorted(root.rglob("*.yaml")))
    return seen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Files or directories to migrate (default: .edpa/backlog)",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without writing.")
    args = parser.parse_args()

    roots = args.paths or [Path(".edpa/backlog")]
    targets = collect_targets(roots)
    if not targets:
        print("No .yaml files found.", file=sys.stderr)
        return 0

    changed = 0
    errors = 0
    for path in targets:
        ok, msg = migrate_file(path, dry_run=args.dry_run)
        print(msg)
        if msg.startswith("ERROR"):
            errors += 1
        elif ok:
            changed += 1

    summary = (
        f"\n{'Would migrate' if args.dry_run else 'Migrated'} "
        f"{changed} file(s); {errors} error(s); "
        f"{len(targets) - changed - errors} skipped."
    )
    print(summary)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
