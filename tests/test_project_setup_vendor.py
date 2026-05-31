"""Regression guard for project_setup.vendor_engine().

The ``/edpa:setup`` (→ project_setup.py) path lost its engine-vendoring when
the engine moved from ``.claude/edpa/`` to ``.edpa/engine/``: commit 7223b40
dropped vendoring from the skill, and 12 minutes later c8978f4 flipped the
architecture back to "engine vendored at .edpa/engine/ is required" but wired
that only into install.sh — never restoring it to the CC-native setup path.
Result: a fresh repo onboarded purely via /edpa:setup referenced a
``.edpa/engine/scripts/`` that never existed (CI + documented CLI broke
silently; MCP masked it by running from the plugin cache).

These tests assert project_setup.py now produces a usable ``.edpa/engine/``.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import project_setup as ps  # noqa: E402

PLUGIN_VERSION = json.loads(
    (ROOT / "plugin" / ".claude-plugin" / "plugin.json").read_text()
)["version"]


def test_vendor_engine_populates_edpa_engine(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    assert ps.vendor_engine(project) is True
    eng = project / ".edpa" / "engine"
    assert any((eng / "scripts").glob("*.py")), "no Python modules vendored"
    assert (eng / "schemas").is_dir()
    assert (eng / "templates").is_dir()
    # The skill's documented Step 3 target must now resolve.
    assert (eng / "scripts" / "backlog.py").exists()
    # VERSION pinned to the plugin version (install.sh parity).
    assert (eng / "VERSION").read_text().strip() == PLUGIN_VERSION


def test_main_bootstrap_vendors_engine(tmp_path: Path, monkeypatch) -> None:
    """The vendor step must be wired into main(), not just defined — guards
    against someone dropping the vendor_engine(root) call again."""
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setattr(sys, "argv", ["project_setup", "--root", str(project)])
    assert ps.main() == 0
    assert (project / ".edpa" / "engine" / "scripts" / "backlog.py").exists()


def test_main_bootstrap_stamps_methodology(tmp_path: Path, monkeypatch) -> None:
    """Seeded edpa.yaml carries the live plugin version, not the template's
    frozen string (fresh-install finding #3)."""
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setattr(sys, "argv", ["project_setup", "--root", str(project)])
    assert ps.main() == 0
    text = (project / ".edpa" / "config" / "edpa.yaml").read_text()
    assert f'methodology: "EDPA {PLUGIN_VERSION}"' in text
    assert '"EDPA 1.22.1"' not in text


def test_vendor_engine_includes_rules(tmp_path: Path) -> None:
    """Rules live at plugin/rules (one level above edpa/) — vendor must pull
    them in, else --with-rules later fails (install_rules reads them back
    from .edpa/engine/rules)."""
    project = tmp_path / "proj"
    project.mkdir()
    ps.vendor_engine(project)
    rules = project / ".edpa" / "engine" / "rules"
    assert rules.is_dir(), ".edpa/engine/rules not vendored"
    assert any(rules.glob("*.md")), "no rule .md files vendored"


def test_main_with_rules_installs_claude_rules(tmp_path: Path, monkeypatch) -> None:
    """End-to-end: /edpa:setup --with-rules populates .claude/rules/ — the
    vendor→install_rules chain that silently broke when rules weren't vendored
    to .edpa/engine/rules."""
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setattr(
        sys, "argv", ["project_setup", "--root", str(project), "--with-rules"]
    )
    assert ps.main() == 0
    assert any((project / ".claude" / "rules").glob("*.md"))


def test_vendor_engine_idempotent(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    ps.vendor_engine(project)
    assert ps.vendor_engine(project) is True  # second run must not raise
    eng = project / ".edpa" / "engine"
    assert (eng / "VERSION").read_text().strip() == PLUGIN_VERSION


def test_vendor_engine_hooks_executable(tmp_path: Path) -> None:
    """Vendored hook scripts stay executable (install.sh parity)."""
    project = tmp_path / "proj"
    project.mkdir()
    ps.vendor_engine(project)
    hooks = project / ".edpa" / "engine" / "scripts" / "hooks"
    if hooks.is_dir():
        for f in hooks.iterdir():
            if f.is_file():
                assert os.access(f, os.X_OK), f"{f.name} not executable"
