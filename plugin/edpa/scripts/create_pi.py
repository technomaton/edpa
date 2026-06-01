#!/usr/bin/env python3
"""
EDPA PI creator — writes the PI-level metadata file
``.edpa/iterations/<PI-YYYY-N>.yaml`` (top-level ``pi:`` block).

This script is the single source of behavior for PI creation. The MCP tool
``edpa_pi_create`` imports :func:`create_pi`, and the ``/edpa:create-pi``
command / ``edpa:create-pi`` skill shell out to this CLI — same engine, like
the rest of EDPA (``capacity_override.py`` <-> ``/edpa:capacity``,
``backlog.py`` <-> ``edpa:add``).

A PI is the parent of per-iteration files (``PI-YYYY-N.1`` ...). This tool does
NOT scaffold those child iterations — create them with the iteration tooling
(``edpa_iteration_create``). The PI list is reconstructed at runtime from
``iterations/*.yaml`` by ``_pi_loader.derive_pis``; that loader globs ``*.yaml``
only, so the file MUST end in ``.yaml`` — a ``.yml`` is silently ignored.

Usage:
    python3 create_pi.py PI-2026-2
    python3 create_pi.py PI-2026-2 --start 2026-06-02 --end 2026-09-06 \\
        --weeks 1 --iterations 5 --status active
    python3 create_pi.py PI-2026-2 --no-commit
"""

# NOTE: ``_console`` (which reconfigures stdout to UTF-8 as an import side
# effect) is imported lazily inside ``main()``, NOT at module top — because
# ``mcp_server`` imports :func:`create_pi` and must keep stdout pristine for
# JSON-RPC framing. Only the CLI opts into the UTF-8 reconfigure.
import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. pip3 install pyyaml --break-system-packages",
          file=sys.stderr)
    sys.exit(2)


# -- console (mirrors capacity_override.py) -----------------------------------
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    OK = "\033[32m"
    WARN = "\033[33m"
    ERR = "\033[31m"
    HEAD = "\033[38;5;147m"


def _isatty():
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def _c(t, code):
    return f"{code}{t}{C.RESET}" if _isatty() else t


def die(msg, code=1):
    print(f"{_c('✗', C.ERR)} {msg}", file=sys.stderr)
    sys.exit(code)


def info(msg):
    print(f"{_c('·', C.DIM)} {msg}")


def ok(msg):
    print(f"{_c('✓', C.OK)} {msg}")


def warn(msg):
    print(f"{_c('⚠', C.WARN)} {msg}")


# -- core (importable; raises ValueError, never sys.exit) ---------------------
# PI-level id only — NO ``.iteration`` suffix. Mirrors the year/num shape of
# mcp_server.ITERATION_ID_RE but rejects the ``.N`` tail.
PI_ID_RE = re.compile(r"^PI-\d{4}-\d{1,2}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VALID_STATUSES = ("planning", "active", "closed")


def _write_yaml_atomic(path: Path, data: dict) -> None:
    """tmp + rename; ``safe_dump(sort_keys=False, allow_unicode=True)``.

    Same shape as ``mcp_server._write_yaml_atomic`` — kept here so this script
    has no dependency on the MCP layer and runs as a plain CLI.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".yaml", prefix=f".{path.stem}_",
                               dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False,
                           default_flow_style=False, allow_unicode=True)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def create_pi(edpa_root, pi_id, *, start_date=None, end_date=None,
              iteration_weeks=1, pi_iterations=None, status="planning") -> dict:
    """Write the PI-level metadata file; return ``{"id", "path"}``.

    ``edpa_root`` is the ``.edpa/`` directory. ``pi_id`` must be PI-level
    (``PI-YYYY-N``) — an iteration id with a ``.N`` suffix is rejected. Raises
    ``ValueError`` on a bad/duplicate id or invalid field; callers map that to
    their own channel (MCP -> ``_err``, CLI -> :func:`die`). Does not commit.
    """
    edpa_root = Path(edpa_root)
    if not isinstance(pi_id, str) or not PI_ID_RE.match(pi_id):
        raise ValueError(
            f"invalid PI id {pi_id!r}; expected PI-YYYY-N (e.g. PI-2026-1) "
            f"with no .iteration suffix")
    if status not in VALID_STATUSES:
        raise ValueError(
            f"invalid status {status!r}; expected one of {VALID_STATUSES}")
    for label, val in (("start_date", start_date), ("end_date", end_date)):
        if val is not None and not _DATE_RE.match(str(val)):
            raise ValueError(f"{label} {val!r} must be YYYY-MM-DD")
    if iteration_weeks is not None and (not isinstance(iteration_weeks, int)
                                        or isinstance(iteration_weeks, bool)
                                        or iteration_weeks < 1):
        raise ValueError(
            f"iteration_weeks must be an integer >= 1 (got {iteration_weeks!r})")
    if pi_iterations is not None and (not isinstance(pi_iterations, int)
                                      or isinstance(pi_iterations, bool)
                                      or pi_iterations < 1):
        raise ValueError(
            f"pi_iterations must be an integer >= 1 (got {pi_iterations!r})")

    iter_path = edpa_root / "iterations" / f"{pi_id}.yaml"
    if iter_path.exists():
        raise ValueError(f"PI {pi_id} already exists at {iter_path}")

    # Field order mirrors the playbook canonical shape.
    pi_block: dict = {"id": pi_id, "status": status}
    if iteration_weeks is not None:
        pi_block["iteration_weeks"] = iteration_weeks
    if pi_iterations is not None:
        pi_block["pi_iterations"] = pi_iterations
    if start_date is not None:
        pi_block["start_date"] = start_date
    if end_date is not None:
        pi_block["end_date"] = end_date

    _write_yaml_atomic(iter_path, {"pi": pi_block})
    return {"id": pi_id, "path": str(iter_path)}


# -- CLI ----------------------------------------------------------------------
def find_edpa_root() -> Path:
    """Locate .edpa/ from cwd upward. Returns absolute path or dies."""
    cur = Path.cwd().resolve()
    for parent in [cur, *cur.parents]:
        if (parent / ".edpa").is_dir():
            return parent / ".edpa"
    die("No .edpa/ directory found from current working directory upward.")


def run_validator(edpa_root: Path) -> bool:
    """Run validate_iterations.py for continuity feedback (non-gating).

    Returns False if it reports errors. A lone PI with no child iterations is
    valid (no ``missing_pi_yaml``), so this is informational, not a gate.
    """
    script = Path(__file__).resolve().parent / "validate_iterations.py"
    if not script.is_file():
        return True
    rc = subprocess.run([sys.executable, str(script), str(edpa_root)],
                        capture_output=True, text=True)
    if rc.stdout.strip():
        print(rc.stdout.strip())
    if rc.stderr.strip():
        print(rc.stderr.strip(), file=sys.stderr)
    return rc.returncode == 0


def main(argv=None) -> int:
    try:  # best-effort UTF-8 stdio on legacy Windows consoles (cp1250) — CLI only
        import _console  # noqa: F401
    except ImportError:
        pass
    ap = argparse.ArgumentParser(
        description="EDPA PI creator — write the PI-level metadata file "
                    "(.edpa/iterations/<PI-YYYY-N>.yaml)")
    ap.add_argument("id", help="PI id, e.g. PI-2026-2 (no .iteration suffix)")
    ap.add_argument("--start", dest="start_date", help="PI start date YYYY-MM-DD")
    ap.add_argument("--end", dest="end_date", help="PI end date YYYY-MM-DD")
    ap.add_argument("--weeks", dest="iteration_weeks", type=int, default=1,
                    help="iteration cadence in weeks (default 1)")
    ap.add_argument("--iterations", dest="pi_iterations", type=int,
                    help="planned number of iterations in the PI")
    ap.add_argument("--status", default="planning", choices=VALID_STATUSES,
                    help="PI status (default planning)")
    ap.add_argument("--no-commit", action="store_true",
                    help="skip git add/commit (file mutation only)")
    args = ap.parse_args(argv)

    edpa_root = find_edpa_root()
    try:
        result = create_pi(
            edpa_root, args.id,
            start_date=args.start_date, end_date=args.end_date,
            iteration_weeks=args.iteration_weeks,
            pi_iterations=args.pi_iterations, status=args.status)
    except ValueError as e:
        die(str(e))

    rel = Path(result["path"]).relative_to(edpa_root.parent)
    ok(f"Created PI {args.id} -> {rel}")

    run_validator(edpa_root)  # informational continuity feedback (non-gating)

    if args.no_commit:
        info(f"--no-commit: {rel} left uncommitted in the working tree")
    else:
        try:
            from _auto_commit import maybe_commit
            commit_status = maybe_commit(
                [result["path"]], f"chore(pi): create {args.id}",
                root=str(edpa_root.parent))
            if commit_status == "committed":
                ok(f"Committed: chore(pi): create {args.id}")
            elif commit_status == "skipped":
                warn("auto-commit skipped (no git, or git user.name/email "
                     "unset) — commit manually.")
        except ImportError:
            warn("_auto_commit unavailable — commit manually.")

    info("Next: add child iterations (per-iteration files):")
    print(f"    {args.id}.1 ... via the iteration tooling (edpa_iteration_create);")
    print("    the last iteration of a PI is usually type: IP.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
