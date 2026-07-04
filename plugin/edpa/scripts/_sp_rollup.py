#!/usr/bin/env python3
"""Derive Story-Point (Job Size) rollups per iteration from backlog items.

EDPA stores effort as ``js`` (Job Size) on individual Story/Defect items, not on
the iteration files. This helper derives per-iteration SP from the items:

  planned_sp[iter]   = Σ js over Story/Defect items with iteration == iter
  delivered_sp[iter] = same, restricted to status == "Done"

Consumers use it in two distinct roles — keep them apart (D-60):

- ``delivered_sp`` is a safe report-time fallback (velocity.py, pi_close.py,
  pi_metrics.py) and the close-time stamp source (mcp_server, D-57): Done
  items are facts regardless of when they were assigned.
- ``planned_sp`` reflects the CURRENT assignment, including unplanned
  mid-iteration additions — at close it equals delivered by construction.
  It is therefore ONLY valid as the planning-time stamp source
  (mcp_server._refresh_planned_sp, while the iteration has not started).
  Reports must never fall back to it for "planned"; a missing
  ``planning.planned_sp`` stamp means predictability n/a, not 100%.
"""
from pathlib import Path

try:
    from _md_frontmatter import load_md
except ImportError:  # pragma: no cover - ensure sibling import when run standalone
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _md_frontmatter import load_md

_DELIVERY_DIRS = ("stories", "defects")


def predictability_pct(planned, delivered):
    """Predictability % — how close delivery landed to the planning-time plan.

    Symmetric deviation measure, ``100 × min/max``: overdelivery (unplanned
    scope landing mid-iteration) is a plan miss exactly like underdelivery —
    delivering 29 against a plan of 26 is ~89.7%, not 100 and not 111.5
    (D-60: the E2E close backfilled planned=delivered, so the old
    ``delivered/planned`` ratio was always a vacuous 100%).

    ``planned`` must be a real planning-time stamp; when it is missing (None
    or 0 — no committed scope to measure against) the result is None and
    reports render "n/a" instead of pretending perfect predictability.
    """
    if not planned or planned < 0 or delivered is None or delivered < 0:
        return None
    return round(100 * min(planned, delivered) / max(planned, delivered), 1)


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
