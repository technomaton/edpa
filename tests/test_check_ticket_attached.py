"""Tests for plugin/edpa/scripts/check_ticket_attached.py.

Unit tests on check_message() + a few integration tests with a real
tmp git repo (so we exercise the _staged_paths git call).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import check_ticket_attached as cta  # noqa: E402


# ─── Pure unit tests on check_message ─────────────────────────────────────


def test_message_with_item_id_passes() -> None:
    passes, reason = cta.check_message("S-5: implement login",
                                       ["src/login.py"])
    assert passes is True
    assert "item ID" in reason


def test_item_id_in_body_passes() -> None:
    msg = "feat: stuff\n\nWork on multiple items.\nCloses F-3."
    passes, _ = cta.check_message(msg, ["src/x.py"])
    assert passes is True


def test_no_item_id_with_real_file_fails() -> None:
    passes, reason = cta.check_message("refactor: clean up helpers",
                                       ["src/util.py"])
    assert passes is False
    assert "no EDPA item ID" in reason


def test_empty_diff_passes() -> None:
    """Empty diff (e.g. amend with no file changes) → pass."""
    passes, _ = cta.check_message("some message", [])
    assert passes is True


def test_no_ticket_prefix_passes() -> None:
    for prefix in ("no-ticket:", "[no-ticket]", "WIP:", "wip:"):
        msg = f"{prefix} just iterating"
        passes, _ = cta.check_message(msg, ["src/x.py"])
        assert passes, f"expected pass with prefix {prefix!r}"


def test_auto_prefixes_pass() -> None:
    for prefix in (
        "chore(evidence): S-5 from abc1234",
        "chore(ci-materialization): PR#1 signals",
        "Merge branch 'feat/x' into main",
        "Merge pull request #1",
        'Revert "feat: add login"',
        "Initial commit",
        "fixup! S-5: previous",
        "squash! S-5: previous",
    ):
        passes, _ = cta.check_message(prefix, ["src/x.py"])
        assert passes, f"expected pass with auto-prefix subject {prefix!r}"


def test_only_operational_paths_pass() -> None:
    """README, .gitignore, package.json bumps don't need a ticket."""
    for paths in (
        ["README.md"],
        [".gitignore"],
        ["package.json", "package-lock.json"],
        [".github/workflows/ci.yml"],
        ["LICENSE", "CHANGELOG.md"],
    ):
        passes, _ = cta.check_message("chore: bump", paths)
        assert passes, f"expected pass with operational paths {paths}"


def test_mixed_operational_and_real_fails() -> None:
    """README + src/login.py → real work, ticket required."""
    passes, _ = cta.check_message("chore: cleanup",
                                  ["README.md", "src/login.py"])
    assert passes is False


def test_comment_lines_ignored() -> None:
    """Git adds # comment lines in COMMIT_EDITMSG; they shouldn't count."""
    msg = "# Please enter the commit message\n# S-5 in comment ignored\nplain change"
    passes, _ = cta.check_message(msg, ["src/x.py"])
    assert passes is False


def test_item_id_only_in_comment_does_not_pass() -> None:
    msg = "fix: x\n# S-5 is not a real reference here\n# closes S-1"
    passes, _ = cta.check_message(msg, ["src/x.py"])
    assert passes is False


# ─── Integration tests with real git repo ─────────────────────────────────


def _git(args, cwd, env_extra=None, check=True):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(["git", *args], cwd=str(cwd), env=env,
                          check=check, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(["init", "-q", "-b", "main"], cwd=tmp_path)
    _git(["config", "user.email", "t@x"], cwd=tmp_path)
    _git(["config", "user.name", "T"], cwd=tmp_path)
    _git(["config", "commit.gpgsign", "false"], cwd=tmp_path)
    (tmp_path / "README.md").write_text("hello\n")
    _git(["add", "README.md"], cwd=tmp_path)
    _git(["commit", "-q", "-m", "Initial commit"], cwd=tmp_path)
    return tmp_path


def _stage(repo: Path, paths_contents: list[tuple[str, str]]) -> None:
    for rel, content in paths_contents:
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    _git(["add", *(p for p, _ in paths_contents)], cwd=repo)


def _run_check_with_msg(repo: Path, msg: str) -> int:
    msg_file = repo / ".git" / "COMMIT_EDITMSG"
    msg_file.write_text(msg)
    old = Path.cwd()
    old_argv = sys.argv
    try:
        os.chdir(repo)
        # main() reads sys.argv[1] for the msg path; pytest's argv leaks
        # through otherwise.
        sys.argv = ["check_ticket_attached.py", str(msg_file)]
        return cta.main()
    finally:
        os.chdir(old)
        sys.argv = old_argv


def test_integration_real_diff_no_ticket_fails(repo: Path, capsys) -> None:
    _stage(repo, [("src/feature.py", "# new feature\n")])
    rc = _run_check_with_msg(repo, "refactor: tidy up")
    assert rc == 1
    err = capsys.readouterr().err
    assert "no item reference" in err.lower()
    assert "src/feature.py" in err


def test_integration_real_diff_with_ticket_passes(repo: Path) -> None:
    _stage(repo, [("src/feature.py", "# new feature\n")])
    rc = _run_check_with_msg(repo, "S-5: add feature endpoint")
    assert rc == 0


def test_integration_real_diff_with_no_ticket_escape_passes(
    repo: Path,
) -> None:
    _stage(repo, [("src/feature.py", "# new feature\n")])
    rc = _run_check_with_msg(repo, "no-ticket: emergency rollback fix")
    assert rc == 0


def test_integration_disabled_via_env(repo: Path, monkeypatch) -> None:
    monkeypatch.setenv(cta.ENV_DISABLE, "1")
    _stage(repo, [("src/feature.py", "# new feature\n")])
    rc = _run_check_with_msg(repo, "no item ref at all")
    assert rc == 0


def test_integration_operational_only_passes(repo: Path) -> None:
    _stage(repo, [("README.md", "updated\n"),
                  (".gitignore", "*.log\n")])
    rc = _run_check_with_msg(repo, "docs: tweak readme")
    assert rc == 0


def test_integration_uses_default_msg_file_when_no_arg(
    repo: Path, monkeypatch,
) -> None:
    """Hook invocation always passes $1, but the script should also
    work when sys.argv has no path arg (defensive fallback)."""
    _stage(repo, [("src/x.py", "x\n")])
    (repo / ".git/COMMIT_EDITMSG").write_text("S-1: work")
    monkeypatch.setattr(sys, "argv", ["check_ticket_attached.py"])
    old = Path.cwd()
    try:
        os.chdir(repo)
        rc = cta.main()
    finally:
        os.chdir(old)
    assert rc == 0
