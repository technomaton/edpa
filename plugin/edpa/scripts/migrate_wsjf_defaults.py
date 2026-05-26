#!/usr/bin/env python3
"""Backfill WSJF fields on legacy backlog items to V2.1 strict defaults.

V2.0 omitted js/bv/tc/rr_oe/wsjf from YAML when the user didn't pass
them on create — the engine implicitly coerced None → 0 at read time.
V2.1 makes the WSJF block explicit: every item has all five fields
even when zero.

This script scans every ``.edpa/backlog/{type}/*.md`` and, for any item
missing any of {js, bv, tc, rr_oe, wsjf}, writes 0 / 0.0 in place. Items
that already have all five fields are skipped. wsjf is recomputed from
(bv + tc + rr_oe) / js when js > 0; otherwise set to 0.0.

Idempotent: re-runs are no-ops once every item is normalized.

Usage:
    python3 .edpa/engine/scripts/migrate_wsjf_defaults.py            # apply
    python3 .edpa/engine/scripts/migrate_wsjf_defaults.py --dry-run  # preview
"""

from __future__ import annotations

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


_WSJF_FIELDS = ("js", "bv", "tc", "rr_oe")


def _normalize_item(item: dict) -> tuple[dict, bool]:
    """Return (item, changed). Adds 0 defaults + recomputes wsjf."""
    changed = False
    for f in _WSJF_FIELDS:
        if item.get(f) is None:
            item[f] = 0
            changed = True
    js = item.get("js") or 0
    bv = item.get("bv") or 0
    tc = item.get("tc") or 0
    rr = item.get("rr_oe") or 0
    new_wsjf = round((bv + tc + rr) / js, 2) if js > 0 else 0.0
    if item.get("wsjf") != new_wsjf:
        item["wsjf"] = new_wsjf
        changed = True
    return item, changed


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
        prog="migrate_wsjf_defaults",
        description="Backfill js/bv/tc/rr_oe/wsjf to V2.1 strict defaults.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--edpa-root", type=Path, default=None,
                        help="Override .edpa/ lookup (default: walk up from cwd)")
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
    n_t = len(result["touched"])
    n_s = len(result["skipped"])
    verb = "would update" if args.dry_run else "updated"
    print(f"{verb}: {n_t} file(s) (already-normalized: {n_s})")
    for path in result["touched"]:
        print(f"  ~ {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
