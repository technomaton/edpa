"""Static guard: install.sh "Next steps" stays V2 local-first.

Fresh-install finding #2 — install.sh printed stale V1 guidance ("provision
GitHub Project … push to GitHub Projects") and invoked project_setup.py with
V1 args (--org / --project-title) that no longer exist and would error.
"""
from __future__ import annotations

from pathlib import Path

INSTALL_SH = (Path(__file__).resolve().parent.parent / "install.sh").read_text()


def test_no_v1_github_project_language() -> None:
    for stale in ("push to GitHub Projects", "provision GitHub Project"):
        assert stale not in INSTALL_SH, f"stale V1 phrase in install.sh: {stale!r}"


def test_no_v1_project_setup_args() -> None:
    # NB: --repo is legitimate (gh release commands), so only assert the
    # args unique to the removed V1 project_setup invocation.
    for stale in ("--project-title", "--org "):
        assert stale not in INSTALL_SH, f"V1 project_setup arg in install.sh: {stale!r}"


def test_uses_v2_project_setup_invocation() -> None:
    assert "--with-ci --with-hooks --with-rules" in INSTALL_SH


def test_lists_filelock_dependency() -> None:
    # id_counter imports filelock; the curl|sh dep hint must include it.
    assert "filelock" in INSTALL_SH
