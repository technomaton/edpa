#!/usr/bin/env python3
"""Schema-tolerant access to edpa_results.json person reports (D-56).

Two producers write per-person results in different shapes:

  - The engine CLI (``engine.py --edpa-root``) writes ``edpa_results.json``
    with key ``people`` — entries keyed ``id`` and carrying ``capacity`` /
    ``total_derived`` / ``items`` / ``invariant_ok``.
  - Frozen snapshots (``engine._snapshot_payload``) and pre-v1.14 results
    files carry ``derived_reports`` — entries keyed ``person`` with
    ``items_count`` instead of ``items`` — plus a top-level
    ``capacity_registry``.

Readers (payroll_export.py, insights.py) historically consumed only the
``derived_reports`` shape, so a stock engine run yielded zero payroll rows
and no capacity-overload insights (D-56). This module maps both shapes onto
the snapshot-style entry — ``person`` / ``name`` / ``role`` / ``capacity`` /
``total_derived`` — which stays the readers' internal contract.

Producer output is intentionally untouched: snapshots and downstream tests
pin both shapes; the tolerance lives in the readers.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from _people_loader import load_people as _load_people  # noqa: E402
finally:
    sys.path.pop(0)


def person_reports(results: dict, capacity_by_id: dict | None = None) -> list[dict]:
    """Return per-person report dicts normalized to the legacy
    ``derived_reports`` entry shape (person id under key ``person``).

    Accepts results dicts carrying either ``derived_reports`` (frozen
    snapshot / pre-v1.14) or ``people`` (engine CLI output). When both are
    present and non-empty, ``derived_reports`` wins — it is derived from
    ``people`` at freeze time, so preferring it keeps snapshot consumers
    byte-stable. Entries pass through copied with all their keys;
    ``person`` is guaranteed present. Malformed entries (non-dicts,
    missing id) are skipped.

    ``capacity_by_id`` — optional ``{person_id: hours}`` fallback (from the
    people.yaml registry, see :func:`registry_capacity_by_id`) applied only
    when an entry carries no ``capacity`` of its own. An explicit
    ``capacity: 0`` (e.g. vacation) is a real value and is kept.
    """
    raw = results.get("derived_reports") or results.get("people") or []
    reports: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        pid = entry.get("person") or entry.get("id")
        if pid in (None, ""):
            continue
        norm = dict(entry)
        norm["person"] = str(pid)
        if norm.get("capacity") is None and capacity_by_id:
            fallback = capacity_by_id.get(norm["person"])
            if fallback is not None:
                norm["capacity"] = fallback
        reports.append(norm)
    return reports


def registry_capacity_by_id(edpa_root: Path) -> dict:
    """Return ``{person_id: capacity_hours}`` from ``config/people.yaml``.

    Mirrors the engine's baseline resolution (``engine._resolve_capacity``):
    ``capacity_per_iteration`` first, legacy ``capacity`` second. People
    without either field are omitted. Empty dict when the registry is
    missing or unreadable.
    """
    _, by_id = _load_people(Path(edpa_root))
    out: dict = {}
    for pid, person in by_id.items():
        cap = person.get("capacity_per_iteration")
        if cap is None:
            cap = person.get("capacity")
        if cap is not None:
            out[str(pid)] = cap
    return out
