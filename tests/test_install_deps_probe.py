"""Guards for install_deps.sh, the SessionStart dep auto-installer.

Static guard: the hook skips ``pip install`` when a cheap
``python3 -c 'import ...'`` probe succeeds. If a dependency in requirements.txt
is missing from that probe, the hook can mark deps "installed" while the
package is actually absent — exactly how ``filelock`` silently failed to
install on fresh Windows boxes that already had PyYAML/mcp system-wide, after
which ``id_counter`` crashed the bootstrap with ``ModuleNotFoundError``.
Keep the probe and requirements.txt in sync so the drift can't recur.

Behavioral guards (D-43): the hook pip-installs into the user's shared
environment (trying --break-system-packages first), so it must (a) honor the
EDPA_NO_AUTO_DEPS opt-out before ever reaching pip, (b) say exactly which
packages it installs, and (c) every requirement must carry an upper bound so
a breaking new major is never auto-pulled onto fresh installs.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = ROOT / "plugin" / "edpa" / "scripts" / "hooks" / "install_deps.sh"
HOOK = HOOK_PATH.read_text(encoding="utf-8")
REQS = (ROOT / "plugin" / "requirements.txt").read_text(encoding="utf-8")
PLUGIN_ROOT = ROOT / "plugin"

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


# ---------------------------------------------------------------------------
# Version caps + install-message transparency (D-43, static)
# ---------------------------------------------------------------------------


def test_every_requirement_has_upper_bound() -> None:
    """Floor-only constraints let a breaking (or compromised) new major
    auto-install into the user's shared environment on fresh installs."""
    for line in REQS.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        assert "<" in line, (
            f"requirements.txt line {line!r} has no upper bound — a breaking "
            f"new major would be auto-pulled by the SessionStart hook"
        )


def test_install_message_names_every_requirement() -> None:
    """The visible install line must say exactly what lands in the user's
    environment (and stay in sync when requirements.txt changes)."""
    msg_lines = [l for l in HOOK.splitlines() if "EDPA: installing" in l]
    assert msg_lines, "install message not found in install_deps.sh"
    msg = msg_lines[0].lower()
    for name in _requirement_names():
        assert name in msg, (
            f"dep {name!r} missing from the install message: {msg_lines[0].strip()}"
        )
    assert "edpa_no_auto_deps" in msg, "install message must mention the opt-out"


# ---------------------------------------------------------------------------
# EDPA_NO_AUTO_DEPS opt-out (D-43, behavioral)
#
# python3/pip3 PATH shims force the probe outcome and record whether pip
# was ever invoked; CLAUDE_PLUGIN_DATA points at a tmp dir so no real
# marker is touched.
# ---------------------------------------------------------------------------


def _make_shims(tmp_path: Path, *, probe_ok: bool) -> tuple[Path, Path]:
    bindir = tmp_path / "shimbin"
    bindir.mkdir()
    pip_marker = tmp_path / "pip_invoked"
    py = bindir / "python3"
    py.write_text(f"#!/bin/sh\nexit {'0' if probe_ok else '1'}\n", encoding="utf-8")
    py.chmod(0o755)
    pip = bindir / "pip3"
    pip.write_text(f"#!/bin/sh\ntouch '{pip_marker}'\nexit 0\n", encoding="utf-8")
    pip.chmod(0o755)
    return bindir, pip_marker


def _run_hook(tmp_path: Path, bindir: Path, *, opt_out: bool) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    env["CLAUDE_PLUGIN_DATA"] = str(tmp_path / "data")
    env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"
    env.pop("EDPA_NO_AUTO_DEPS", None)
    if opt_out:
        env["EDPA_NO_AUTO_DEPS"] = "1"
    return subprocess.run(
        ["sh", str(HOOK_PATH)],
        input="", cwd=str(tmp_path), env=env,
        capture_output=True, text=True, timeout=30, encoding="utf-8",
    )


def test_opt_out_skips_pip_when_probe_fails(tmp_path) -> None:
    bindir, pip_marker = _make_shims(tmp_path, probe_ok=False)
    r = _run_hook(tmp_path, bindir, opt_out=True)
    assert r.returncode == 0
    assert not pip_marker.exists(), "pip ran despite EDPA_NO_AUTO_DEPS=1"
    assert "EDPA_NO_AUTO_DEPS" in r.stderr
    assert "pip3 install -r" in r.stderr  # manual command still shown


def test_pip_runs_when_probe_fails_without_opt_out(tmp_path) -> None:
    bindir, pip_marker = _make_shims(tmp_path, probe_ok=False)
    r = _run_hook(tmp_path, bindir, opt_out=False)
    assert r.returncode == 0
    assert pip_marker.exists(), "pip was never invoked on a failed probe"
    # The explicit message names the packages and the opt-out.
    assert "PyYAML" in r.stderr
    assert "EDPA_NO_AUTO_DEPS" in r.stderr


def test_probe_success_writes_marker_and_skips_pip(tmp_path) -> None:
    bindir, pip_marker = _make_shims(tmp_path, probe_ok=True)
    r = _run_hook(tmp_path, bindir, opt_out=False)
    assert r.returncode == 0
    assert r.stderr == ""
    assert not pip_marker.exists()
    markers = list((tmp_path / "data").glob("deps_installed.*"))
    assert markers, "probe success must cache a marker in CLAUDE_PLUGIN_DATA"
