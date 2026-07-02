"""D-50: Python 3.10 compatibility for Z-suffixed ISO timestamps.

datetime.fromisoformat() accepts a trailing 'Z' only from Python 3.11.
The engine's declared floor is 3.10 (install.sh gate, collision workflow),
and transition logs / evidence entries carry Z-suffixed timestamps, so every
parse site must normalise 'Z' -> '+00:00' first.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugin" / "edpa" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import transitions  # noqa: E402


def test_parse_since_accepts_z_suffix():
    dt = transitions.parse_since("2026-04-10T10:00:00Z")
    assert (dt.year, dt.month, dt.day, dt.hour) == (2026, 4, 10, 10)


def test_parse_until_accepts_z_suffix():
    dt = transitions.parse_until("2026-04-10T10:00:00Z")
    assert (dt.year, dt.hour, dt.minute) == (2026, 23, 59)


# Lines where a bare fromisoformat() is provably safe (no 'Z' can reach it).
_ALLOWED = (
    ("_pi_loader.py", "date.fromisoformat"),            # date-only strings
    ("yaml_edit_signals.py", "T00:00:00+00:00"),        # constructed literal
    ("yaml_edit_signals.py", "T23:59:59+00:00"),        # constructed literal
    ("mcp_server.py", "dt = datetime.fromisoformat(s)"),  # s normalised above
)


def _is_allowed(fname: str, line: str) -> bool:
    return any(fname == f and marker in line for f, marker in _ALLOWED)


def test_every_fromisoformat_call_normalises_z():
    """Guard against reintroducing 3.11-only fromisoformat('...Z') parses."""
    offenders = []
    for py in sorted(SCRIPTS.glob("*.py")):
        for no, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if "fromisoformat" not in line or line.lstrip().startswith("#"):
                continue
            if 'replace("Z", "+00:00")' in line or _is_allowed(py.name, line):
                continue
            offenders.append(f"{py.name}:{no}: {line.strip()}")
    assert not offenders, (
        "fromisoformat() without Z-normalisation (breaks Python 3.10):\n"
        + "\n".join(offenders)
    )
