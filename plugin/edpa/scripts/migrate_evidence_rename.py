#!/usr/bin/env python3
"""Rename ``ci_signals[]`` → ``evidence[]`` in every backlog YAML.

V2.0 named the raw signal log ``ci_signals[]`` (the CI workflow was the
only emitter). V2.1 broadens the source set — local git hooks emit too
— so the name became misleading. The new name ``evidence[]`` matches
EDPA's methodology vocabulary ("Evidence-Driven Proportional
Allocation") and stays accurate regardless of source.

This script walks ``.edpa/backlog/{type}/*.md`` and, for any item that:

- has a non-empty ``ci_signals[]`` but no ``evidence[]`` → moves it
  over (the entries are byte-identical; only the key changes)
- has BOTH (rare; manual edit?) → merges deduplicated by ``ref``,
  evidence[] wins on conflict, ci_signals[] dropped
- has only ``evidence[]`` already → skip

Idempotent. ``--dry-run`` for preview.

Usage:
    python3 .edpa/engine/scripts/migrate_evidence_rename.py
    python3 .edpa/engine/scripts/migrate_evidence_rename.py --dry-run
"""

from __future__ import annotations

try:  # best-effort UTF-8 stdio on legacy Windows consoles (cp1250)
    import _console  # noqa: F401
except ImportError:
    pass
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    from _md_frontmatter import load_md, save_md_item  # noqa: E402
    from id_counter import TYPE_DIRS  # noqa: E402
finally:
    sys.path.pop(0)


def _normalize_item(item: dict) -> tuple[dict, bool]:
    """Returns (item, changed). Migrates ci_signals[] → evidence[]."""
    legacy = item.get("ci_signals")
    if legacy is None:
        return item, False  # no legacy block; nothing to do

    if not isinstance(legacy, list):
        legacy = []

    new = item.get("evidence")
    if new is None:
        item["evidence"] = list(legacy)
        del item["ci_signals"]
        return item, True

    # Both blocks present (unusual): dedupe by ref, new wins.
    if not isinstance(new, list):
        new = []
    by_ref = {s.get("ref"): s for s in legacy if isinstance(s, dict)}
    for s in new:
        if isinstance(s, dict):
            by_ref[s.get("ref")] = s
    item["evidence"] = [by_ref[k] for k in sorted(by_ref) if k is not None]
    del item["ci_signals"]
    return item, True


def migrate(edpa_root: Path, dry_run: bool = False) -> dict:
    backlog = edpa_root / "backlog"
    touched: list[str] = []
    skipped: list[str] = []
    for type_dir in TYPE_DIRS.values():
        dir_path = backlog / type_dir
        if not dir_path.exists():
            continue
        for f in sorted(dir_path.glob("*.md")):
            data = load_md(f) or {}
            body = data.pop("body", "") if isinstance(data, dict) else ""
            _, changed = _normalize_item(data)
            rel = str(f.relative_to(edpa_root.parent))
            if not changed:
                skipped.append(rel)
                continue
            touched.append(rel)
            if not dry_run:
                save_md_item(f, {**data, "body": body})
    return {"touched": touched, "skipped": skipped}


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="migrate_evidence_rename",
        description="Rename ci_signals[] → evidence[] in backlog YAMLs.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--edpa-root", type=Path, default=None)
    args = parser.parse_args()

    if args.edpa_root:
        edpa_root = args.edpa_root.resolve()
    else:
        p = Path.cwd().resolve()
        edpa_root = None
        while p != p.parent:
            if (p / ".edpa").is_dir():
                edpa_root = p / ".edpa"
                break
            p = p.parent
    if not edpa_root or not edpa_root.exists():
        print("ERROR: .edpa/ not found", file=sys.stderr)
        return 2

    result = migrate(edpa_root, dry_run=args.dry_run)
    verb = "would migrate" if args.dry_run else "migrated"
    print(f"{verb}: {len(result['touched'])} file(s) "
          f"(no legacy block: {len(result['skipped'])})")
    for p in result["touched"]:
        print(f"  ~ {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
