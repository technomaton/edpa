"""Regression guard for project_setup.install_hooks() — robust git-hook
registration + lefthook coexistence (EDPA 2.3.0).

Before 2.3.0, install_hooks used a blunt ``not dst.exists()`` guard: if any
file already occupied a hook slot (typically a lefthook dispatcher shim, since
lefthook owns .git/hooks/), EDPA silently skipped installing its hook — which
stopped the post-commit ``local_evidence.py`` contribution emitter from ever
firing. It also never refreshed a stale snapshot after a plugin update.

These tests pin the new decision tree:
  * lefthook detected  → print snippet, leave .git/hooks/ untouched
  * dst missing        → install
  * dst EDPA-owned     → refresh on demand, else report active
  * dst foreign        → never clobber; warn loudly
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import project_setup as ps  # noqa: E402

HOOK_NAMES = ("pre-commit", "pre-push", "commit-msg", "post-commit")


def _git_hooks(project: Path) -> Path:
    """install_hooks only needs .git/hooks to exist — no real repo required."""
    hooks = project / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    return hooks


# ─── Fresh install ───────────────────────────────────────────────────────────


def test_fresh_install_writes_all_four_hooks(tmp_path: Path) -> None:
    hooks = _git_hooks(tmp_path)
    assert ps.install_hooks(tmp_path, refresh=True) is True
    for name in HOOK_NAMES:
        dst = hooks / name
        assert dst.exists(), f"{name} not installed"
        assert dst.stat().st_mode & 0o111, f"{name} not executable"
        assert ps.EDPA_HOOK_SENTINEL in dst.read_text(), f"{name} missing sentinel"


def test_no_git_hooks_dir_returns_false(tmp_path: Path) -> None:
    # No .git/ at all → cannot install, returns False (does not crash).
    assert ps.install_hooks(tmp_path) is False


# ─── check_only doctor ─────────────────────────────────────────────────────────


def test_check_only_writes_nothing(tmp_path: Path) -> None:
    hooks = _git_hooks(tmp_path)
    assert ps.install_hooks(tmp_path, check_only=True) is True
    # Doctor mode must not create any hook files on an empty repo.
    for name in HOOK_NAMES:
        assert not (hooks / name).exists(), f"check-only created {name}"


def test_check_only_reports_active_after_install(tmp_path: Path, capsys) -> None:
    _git_hooks(tmp_path)
    ps.install_hooks(tmp_path, refresh=True)
    capsys.readouterr()  # drop install output
    ps.install_hooks(tmp_path, check_only=True)
    out = capsys.readouterr().out
    assert "Active EDPA hooks" in out
    for name in HOOK_NAMES:
        assert name in out


# ─── Refresh semantics ─────────────────────────────────────────────────────────


def test_refresh_overwrites_edpa_owned(tmp_path: Path) -> None:
    hooks = _git_hooks(tmp_path)
    ps.install_hooks(tmp_path, refresh=True)
    pc = hooks / "post-commit"
    pc.write_text(pc.read_text() + "\n# STALE-MARKER\n")  # tamper, keep sentinel
    ps.install_hooks(tmp_path, refresh=True)
    assert "STALE-MARKER" not in pc.read_text(), "refresh did not overwrite"
    assert ps.EDPA_HOOK_SENTINEL in pc.read_text()


def test_no_refresh_leaves_edpa_owned_untouched(tmp_path: Path) -> None:
    hooks = _git_hooks(tmp_path)
    ps.install_hooks(tmp_path, refresh=True)
    pc = hooks / "post-commit"
    pc.write_text(pc.read_text() + "\n# KEEP-ME\n")
    ps.install_hooks(tmp_path, refresh=False)  # plain re-run, no refresh
    assert "KEEP-ME" in pc.read_text(), "non-refresh run clobbered an EDPA hook"


# ─── Foreign hook protection ───────────────────────────────────────────────────


def test_foreign_hook_never_clobbered(tmp_path: Path, capsys) -> None:
    hooks = _git_hooks(tmp_path)
    foreign = hooks / "post-commit"
    foreign.write_text("#!/bin/sh\necho 'my own hook'\n")
    ps.install_hooks(tmp_path, refresh=True)
    # Foreign file is byte-for-byte preserved; EDPA sentinel never leaked in.
    assert foreign.read_text() == "#!/bin/sh\necho 'my own hook'\n"
    assert ps.EDPA_HOOK_SENTINEL not in foreign.read_text()
    # The other three slots were free → installed.
    for name in ("pre-commit", "pre-push", "commit-msg"):
        assert ps.EDPA_HOOK_SENTINEL in (hooks / name).read_text()
    # Loud warning + actionable chain-in instructions printed.
    out = capsys.readouterr().out
    assert "NOT EDPA-managed" in out
    assert "post-commit-evidence" in out  # the manual chain-in source path


# ─── Lefthook coexistence ──────────────────────────────────────────────────────


def test_lefthook_detected_prints_snippet_and_skips_git_hooks(
    tmp_path: Path, capsys
) -> None:
    hooks = _git_hooks(tmp_path)
    (tmp_path / "lefthook.yml").write_text("# user config\n")
    assert ps.install_hooks(tmp_path, refresh=True) is True
    # Nothing written into .git/hooks/ — lefthook owns it.
    for name in HOOK_NAMES:
        assert not (hooks / name).exists(), f"{name} leaked into .git/hooks"
    out = capsys.readouterr().out
    assert "lefthook detected" in out
    assert "use_stdin: true" in out  # the critical pre-push correctness flag


@pytest.mark.parametrize(
    "cfg",
    ["lefthook.yml", "lefthook.yaml", ".lefthook.yml",
     ".lefthook.yaml", "lefthook.toml", "lefthook.json"],
)
def test_detect_lefthook_recognizes_all_config_names(tmp_path: Path, cfg: str) -> None:
    assert ps.detect_lefthook(tmp_path) is None
    (tmp_path / cfg).write_text("\n")
    assert ps.detect_lefthook(tmp_path) == tmp_path / cfg


def test_lefthook_snippet_is_valid_yaml() -> None:
    yaml = pytest.importorskip("yaml")
    cfg = yaml.safe_load(ps.LEFTHOOK_SNIPPET)
    # All four git hooks present, each with at least one command.
    for hook in HOOK_NAMES:
        assert hook in cfg, f"snippet missing {hook}"
        assert cfg[hook]["commands"], f"{hook} has no commands"
    # pre-push reads refs on stdin → command MUST set use_stdin, or lefthook
    # hangs the push. This is the correctness flag the verification turned up.
    pre_push_cmd = next(iter(cfg["pre-push"]["commands"].values()))
    assert pre_push_cmd.get("use_stdin") is True
    # commit-msg passes the message file as the first positional arg.
    commit_msg_cmd = next(iter(cfg["commit-msg"]["commands"].values()))
    assert "{1}" in commit_msg_cmd["run"]
