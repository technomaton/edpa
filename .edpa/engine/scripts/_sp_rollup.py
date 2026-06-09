#!/usr/bin/env python3
"""Derive Story-Point (Job Size) rollups per iteration from backlog items.

EDPA stores effort as ``js`` (Job Size) on individual Story/Defect items, not on
the iteration files. ``velocity.py`` and ``pi_close.py`` read
``planning.planned_sp`` / ``delivery.delivered_sp`` from the iteration YAML,
which are absent for item-driven backlogs (→ velocity 0, predictability None).
This helper derives the rollup from the items so those reports work without
hand-maintained iteration SP fields.

  planned_sp[iter]   = Σ js over Story/Defect items with iteration == iter
  delivered_sp[iter] = same, restricted to status == "Done"
"""
from pathlib import Path

try:
    from _md_frontmatter import load_md
except ImportError:  # pragma: no cover - ensure sibling import when run standalone
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _md_frontmatter import load_md

_DELIVERY_DIRS = ("stories", "defects")


def iteration_sp(edpa_root) -> dict:
    """Return ``{iteration_id: {"planned_sp": int, "delivered_sp": int}}``.

    Effort is taken from each item's ``js`` field; only Story/Defect items that
    carry an ``iteration`` are counted. ``delivered_sp`` counts the ``Done`` ones.
    """
    out: dict = {}
    backlog = Path(edpa_root) / "backlog"
    for sub in _DELIVERY_DIRS:
        d = backlog / sub
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.md")):
            fm = load_md(f) or {}
            it = fm.get("iteration")
            if not it:
                continue
            try:
                js = int(fm.get("js") or 0)
            except (TypeError, ValueError):
                js = 0
            rec = out.setdefault(str(it), {"planned_sp": 0, "delivered_sp": 0})
            rec["planned_sp"] += js
            if str(fm.get("status", "")).strip().lower() == "done":
                rec["delivered_sp"] += js
    return out
