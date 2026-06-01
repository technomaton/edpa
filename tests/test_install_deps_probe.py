"""Static guard: install_deps.sh's import probe covers every runtime dep.

The SessionStart hook skips ``pip install`` when a cheap
``python3 -c 'import ...'`` probe succeeds. If a dependency in requirements.txt
is missing from that probe, the hook can mark deps "installed" while the
package is actually absent — exactly how ``filelock`` silently failed to
install on fresh Windows boxes that already had PyYAML/mcp system-wide, after
which ``id_counter`` crashed the bootstrap with ``ModuleNotFoundError``.

Keep the probe and requirements.txt in sync so the drift can't recur.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = (ROOT / "plugin" / "edpa" / "scripts" / "hooks" / "install_deps.sh").read_text(
    encoding="utf-8"
)
REQS = (ROOT / "plugin" / "requirements.txt").read_text(encoding="utf-8")

# pip distribution name -> import token the probe must reference.
IMPORT_TOKEN = {
    "pyyaml": "yaml",
    "ruamel.yaml": "ruamel",
    "mcp": "mcp",
    "openpyxl": "openpyxl",
    "filelock": "filelock",
}


def _requirement_names() -> list[str]:
    names = []
    for line in REQS.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        names.append(re.split(r"[<>=!~; ]", line)[0].lower())
    return names


def _probe_line() -> str:
    for line in HOOK.splitlines():
        if "python3 -c" in line and "import" in line:
            return line
    raise AssertionError("import probe line not found in install_deps.sh")


def test_every_requirement_is_in_the_probe() -> None:
    probe = _probe_line()
    for name in _requirement_names():
        token = IMPORT_TOKEN.get(name, name)
        assert token in probe, (
            f"requirements.txt dep {name!r} (import {token!r}) is missing from "
            f"the install_deps.sh probe — pip install can be skipped, leaving "
            f"it uninstalled. Probe: {probe.strip()}"
        )


def test_filelock_specifically_covered() -> None:
    # Regression: filelock was the dep that drifted out of the probe.
    assert "filelock" in _probe_line()
