#!/usr/bin/env python3
"""EDPA PI Objectives — read/write ``.edpa/pi-objectives/<PI>.yaml``.

Single source of behavior for the PI-objectives write tools (committed /
stretch objectives + team confidence vote). The on-disk shape mirrors the PI
planning ``ObjectivesData`` contract consumed by the board:

    pi: PI-2026-1
    teams:
      CVUT:
        committed:
          - {title: "OMOP parser production-ready", bv: 8, status: done}
        stretch:
          - {title: "FHIR bridge MVP", bv: 5, status: in_progress}
        confidence: 4        # team confidence vote, 1..5

Consumed by the ``edpa_objective_set`` / ``edpa_objective_remove`` /
``edpa_confidence_vote`` MCP tools. ``edpa_dir`` is the ``.edpa/`` directory
(the convention used by create_pi.py and the MCP handlers).
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is a hard dep
    print("ERROR: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    raise

OBJ_STATUSES = ("planned", "in_progress", "done")
KINDS = ("committed", "stretch")
_PI_RE = re.compile(r"^PI-\d{4}-\d+$")


def _safe_pi(pi) -> str | None:
    return pi if isinstance(pi, str) and _PI_RE.match(pi) else None


def _path(edpa_dir, pi: str) -> Path:
    return Path(edpa_dir) / "pi-objectives" / f"{pi}.yaml"


def load(edpa_dir, pi: str) -> dict:
    """Load ObjectivesData for ``pi`` (default ``{pi, teams: {}}`` if absent)."""
    p = _path(edpa_dir, pi)
    if not p.exists():
        return {"pi": pi, "teams": {}}
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"pi": pi, "teams": {}}
    data.setdefault("pi", pi)
    if not isinstance(data.get("teams"), dict):
        data["teams"] = {}
    return data


def _atomic_write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def save(edpa_dir, pi: str, data: dict) -> Path:
    p = _path(edpa_dir, pi)
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120)
    _atomic_write(p, text)
    return p


def _ensure_team(data: dict, team: str) -> dict:
    teams = data["teams"]
    t = teams.setdefault(team, {"committed": [], "stretch": [], "confidence": 3})
    t.setdefault("committed", [])
    t.setdefault("stretch", [])
    t.setdefault("confidence", 3)
    return t


def set_objective(edpa_dir, pi, team, kind, title, *, bv=None, status=None) -> dict:
    """Upsert an objective by (team, kind, title). Creates the file/team as
    needed. Returns a result dict. Raises ValueError on invalid input."""
    pi = _safe_pi(pi)
    if not pi:
        raise ValueError("pi must be PI-level, e.g. PI-2026-1")
    if not team or not str(team).strip():
        raise ValueError("team is required")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {list(KINDS)} (got {kind!r})")
    if not title or not str(title).strip():
        raise ValueError("title is required")
    if bv is None:
        bv = 5
    if not isinstance(bv, int) or isinstance(bv, bool) or not (1 <= bv <= 10):
        raise ValueError(f"bv must be an integer 1..10 (got {bv!r})")
    if status is None:
        status = "planned"
    if status not in OBJ_STATUSES:
        raise ValueError(f"status must be one of {list(OBJ_STATUSES)} (got {status!r})")

    data = load(edpa_dir, pi)
    t = _ensure_team(data, team)
    existing = next(
        (o for o in t[kind] if isinstance(o, dict) and o.get("title") == title), None
    )
    if existing is not None:
        existing["bv"] = bv
        existing["status"] = status
        action = "updated"
    else:
        t[kind].append({"title": title, "bv": bv, "status": status})
        action = "added"
    save(edpa_dir, pi, data)
    return {"pi": pi, "team": team, "kind": kind, "title": title,
            "bv": bv, "status": status, "action": action}


def remove_objective(edpa_dir, pi, team, kind, title) -> dict:
    """Remove an objective by (team, kind, title). Raises if not found."""
    pi = _safe_pi(pi)
    if not pi:
        raise ValueError("pi must be PI-level, e.g. PI-2026-1")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {list(KINDS)} (got {kind!r})")
    data = load(edpa_dir, pi)
    team_data = data["teams"].get(team)
    if not isinstance(team_data, dict):
        raise ValueError(f"team {team!r} not found in {pi} objectives")
    lst = team_data.get(kind, []) or []
    kept = [o for o in lst if not (isinstance(o, dict) and o.get("title") == title)]
    if len(kept) == len(lst):
        raise ValueError(f"no {kind} objective titled {title!r} for team {team}")
    team_data[kind] = kept
    save(edpa_dir, pi, data)
    return {"pi": pi, "team": team, "kind": kind, "title": title, "action": "removed"}


def set_confidence(edpa_dir, pi, team, confidence) -> dict:
    """Set a team's confidence vote (1..5). Creates the team if needed."""
    pi = _safe_pi(pi)
    if not pi:
        raise ValueError("pi must be PI-level, e.g. PI-2026-1")
    if not team or not str(team).strip():
        raise ValueError("team is required")
    if not isinstance(confidence, int) or isinstance(confidence, bool) or not (1 <= confidence <= 5):
        raise ValueError(f"confidence must be an integer 1..5 (got {confidence!r})")
    data = load(edpa_dir, pi)
    t = _ensure_team(data, team)
    t["confidence"] = confidence
    save(edpa_dir, pi, data)
    return {"pi": pi, "team": team, "confidence": confidence}
