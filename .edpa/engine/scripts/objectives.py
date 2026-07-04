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

Also runnable as a plain CLI (same library write path, no MCP server needed —
mirrors create_pi.py / pi_close.py)::

    python3 objectives.py set    PI-2026-1 alpha committed "Deliver OMOP parser" --bv 8
    python3 objectives.py remove PI-2026-1 alpha committed "Deliver OMOP parser"
    python3 objectives.py vote   PI-2026-1 alpha 4

The CLI discovers ``.edpa/`` from the current directory upward, or takes an
explicit ``--edpa-root``; pass ``--no-commit`` to skip the git auto-commit.
"""

from __future__ import annotations

import argparse
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


# -- CLI ----------------------------------------------------------------------
# Everything below is CLI-only. The library functions above are imported by
# mcp_server, which must keep stdout pristine for JSON-RPC framing — so the
# ``_console`` UTF-8 reconfigure and ``_auto_commit`` are imported lazily inside
# ``main()``, never at module top. (Mirrors create_pi.py / pi_close.py.)
class C:
    RESET = "\033[0m"
    DIM = "\033[2m"
    OK = "\033[32m"
    WARN = "\033[33m"
    ERR = "\033[31m"


def _isatty() -> bool:
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def _c(text: str, code: str) -> str:
    return f"{code}{text}{C.RESET}" if _isatty() else text


def die(msg, code=1):
    print(f"{_c('✗', C.ERR)} {msg}", file=sys.stderr)
    sys.exit(code)


def info(msg):
    print(f"{_c('·', C.DIM)} {msg}")


def ok(msg):
    print(f"{_c('✓', C.OK)} {msg}")


def warn(msg):
    print(f"{_c('⚠', C.WARN)} {msg}")


def find_edpa_root() -> Path:
    """Locate the ``.edpa/`` directory from cwd upward (mirrors
    create_pi.find_edpa_root). Returns the ``.edpa`` dir or dies."""
    cur = Path.cwd().resolve()
    for parent in [cur, *cur.parents]:
        if (parent / ".edpa").is_dir():
            return parent / ".edpa"
    die("No .edpa/ directory found from current working directory upward.")


def _resolve_edpa_dir(edpa_root) -> Path:
    """The ``.edpa`` directory the library writes under: an explicit
    ``--edpa-root`` (pi_close.py style) when given, else cwd discovery."""
    if edpa_root:
        p = Path(edpa_root)
        if not p.is_dir():
            die(f"--edpa-root {edpa_root!r} is not a directory")
        return p
    return find_edpa_root()


def _do_set(edpa_dir: Path, args) -> tuple[dict, str]:
    r = set_objective(edpa_dir, args.pi, args.team, args.kind, args.title,
                      bv=args.bv, status=args.status)
    ok(f"{r['action']} {r['kind']} objective {r['title']!r} for {r['team']} "
       f"in {r['pi']} (bv={r['bv']}, status={r['status']})")
    return r, (f"chore(pi-objectives): set {r['kind']} objective "
               f"for {r['team']} in {r['pi']}")


def _do_remove(edpa_dir: Path, args) -> tuple[dict, str]:
    r = remove_objective(edpa_dir, args.pi, args.team, args.kind, args.title)
    ok(f"removed {r['kind']} objective {r['title']!r} for {r['team']} "
       f"in {r['pi']}")
    return r, (f"chore(pi-objectives): remove {r['kind']} objective "
               f"for {r['team']} in {r['pi']}")


def _do_vote(edpa_dir: Path, args) -> tuple[dict, str]:
    r = set_confidence(edpa_dir, args.pi, args.team, args.confidence)
    ok(f"confidence vote {r['confidence']} for {r['team']} in {r['pi']}")
    return r, (f"chore(pi-objectives): confidence vote {r['confidence']} "
               f"for {r['team']} in {r['pi']}")


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="objectives",
        description="EDPA PI objectives — set/remove objectives and cast team "
                    "confidence votes in .edpa/pi-objectives/<PI>.yaml, the "
                    "same write path as the edpa_objective_set / "
                    "edpa_objective_remove / edpa_confidence_vote MCP tools.")
    # --edpa-root / --no-commit live on every subcommand (shared parent) so they
    # trail the positionals, like the --no-commit on create_pi.py / pi_close.py.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--edpa-root", dest="edpa_root", default=None,
                        help="path to the .edpa/ directory (default: "
                             "discovered from the current directory upward)")
    common.add_argument("--no-commit", action="store_true",
                        help="write the YAML but skip the git add/commit")
    sub = ap.add_subparsers(dest="command", metavar="{set,remove,vote}")

    p_set = sub.add_parser("set", parents=[common],
                           help="add or update an objective (upsert by title)")
    p_set.add_argument("pi", help="PI id, e.g. PI-2026-1")
    p_set.add_argument("team", help="team name")
    p_set.add_argument("kind", choices=KINDS, help="committed | stretch")
    p_set.add_argument("title", help="objective title")
    p_set.add_argument("--bv", type=int, default=None,
                       help="business value 1-10 (default 5)")
    p_set.add_argument("--status", choices=OBJ_STATUSES, default=None,
                       help="planned | in_progress | done (default planned)")

    p_rm = sub.add_parser("remove", parents=[common],
                          help="remove an objective by (team, kind, title)")
    p_rm.add_argument("pi", help="PI id, e.g. PI-2026-1")
    p_rm.add_argument("team", help="team name")
    p_rm.add_argument("kind", choices=KINDS, help="committed | stretch")
    p_rm.add_argument("title", help="objective title")

    p_vote = sub.add_parser("vote", parents=[common],
                            help="set a team's confidence vote (1-5)")
    p_vote.add_argument("pi", help="PI id, e.g. PI-2026-1")
    p_vote.add_argument("team", help="team name")
    p_vote.add_argument("confidence", type=int, help="confidence 1-5")
    return ap


def main(argv=None) -> int:
    try:  # best-effort UTF-8 stdio on legacy Windows consoles — CLI only
        import _console  # noqa: F401
    except ImportError:
        pass

    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    edpa_dir = _resolve_edpa_dir(args.edpa_root)
    try:
        if args.command == "set":
            result, message = _do_set(edpa_dir, args)
        elif args.command == "remove":
            result, message = _do_remove(edpa_dir, args)
        else:  # vote
            result, message = _do_vote(edpa_dir, args)
    except ValueError as exc:
        die(str(exc))

    path = _path(edpa_dir, result["pi"])
    if args.no_commit:
        info(f"--no-commit: {path} left uncommitted in the working tree")
        return 0

    try:
        from _auto_commit import maybe_commit
        status = maybe_commit([str(path)], message, root=str(edpa_dir.parent))
    except ImportError:
        warn("_auto_commit unavailable — commit manually.")
        return 0
    if status == "committed":
        ok(f"Committed: {message}")
    elif status == "skipped":
        warn("auto-commit skipped (no git, or git user.name/email unset) "
             "— commit manually.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
