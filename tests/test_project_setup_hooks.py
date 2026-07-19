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


# ─── Lefthook content-aware detection (partial-paste blind spot) ───────────────

_FULL_LEFTHOOK = """\
# my project hooks
pre-commit:
  commands:
    lint:
      run: npm run lint
    edpa-id-safety:
      run: sh .edpa/engine/scripts/hooks/pre-commit-id-safety
commit-msg:
  commands:
    edpa-ticket-attached:
      run: sh .edpa/engine/scripts/hooks/commit-msg-ticket-attached {1}
post-commit:
  commands:
    edpa-evidence:
      run: sh .edpa/engine/scripts/hooks/post-commit-evidence
pre-push:
  commands:
    edpa-id-safety:
      run: sh .edpa/engine/scripts/hooks/pre-push-id-safety {1} {2}
      use_stdin: true
"""

# Only the reporting hook pasted — the exact real-world bug: guards dropped.
_PARTIAL_LEFTHOOK = """\
# my hooks
post-commit:
  commands:
    edpa-evidence:
      run: sh .edpa/engine/scripts/hooks/post-commit-evidence
"""


def test_lefthook_hook_status_all_registered(tmp_path: Path) -> None:
    cfg = tmp_path / "lefthook.yml"
    cfg.write_text(_FULL_LEFTHOOK)
    registered, missing = ps.lefthook_hook_status(cfg)
    assert set(registered) == set(HOOK_NAMES)
    assert missing == []


def test_lefthook_hook_status_partial(tmp_path: Path) -> None:
    cfg = tmp_path / "lefthook.yml"
    cfg.write_text(_PARTIAL_LEFTHOOK)
    registered, missing = ps.lefthook_hook_status(cfg)
    assert registered == ["post-commit"]
    assert set(missing) == {"pre-commit", "pre-push", "commit-msg"}


def test_lefthook_hook_status_survives_reorder_and_noise(tmp_path: Path) -> None:
    # Hooks out of snippet order, interleaved with unrelated commands + comments.
    cfg = tmp_path / "lefthook.yml"
    cfg.write_text(
        "pre-push:\n  commands:\n    x:\n"
        "      run: sh .edpa/engine/scripts/hooks/pre-push-id-safety {1} {2}\n"
        "      use_stdin: true\n"
        "commit-msg:\n  commands:\n    y:\n"
        "      run: sh .edpa/engine/scripts/hooks/commit-msg-ticket-attached {1}\n"
        "# a comment line\n"
        "pre-commit:\n  commands:\n    z:\n"
        "      run: sh .edpa/engine/scripts/hooks/pre-commit-id-safety\n"
        "post-commit:\n  commands:\n    w:\n"
        "      run: sh .edpa/engine/scripts/hooks/post-commit-evidence\n"
        "test:\n  commands:\n    unit:\n      run: pytest\n"
    )
    registered, missing = ps.lefthook_hook_status(cfg)
    assert set(registered) == set(HOOK_NAMES)
    assert missing == []


def test_install_hooks_lefthook_partial_warns_unguarded(
    tmp_path: Path, capsys
) -> None:
    hooks = _git_hooks(tmp_path)
    (tmp_path / "lefthook.yml").write_text(_PARTIAL_LEFTHOOK)
    assert ps.install_hooks(tmp_path, refresh=True) is True
    out = capsys.readouterr().out
    assert "UNGUARDED" in out
    for hook in ("pre-commit", "pre-push", "commit-msg"):
        assert hook in out, f"missing hook {hook} not named in warning"
    assert "registered: post-commit" in out
    # Still nothing written into .git/hooks/ — lefthook owns it.
    for name in HOOK_NAMES:
        assert not (hooks / name).exists()


def test_install_hooks_lefthook_all_registered_is_quiet(
    tmp_path: Path, capsys
) -> None:
    hooks = _git_hooks(tmp_path)
    (tmp_path / "lefthook.yml").write_text(_FULL_LEFTHOOK)
    assert ps.install_hooks(tmp_path, refresh=True) is True
    out = capsys.readouterr().out
    assert "All 4 EDPA hooks registered" in out
    assert "UNGUARDED" not in out
    # 4/4 wired → no reason to dump the paste snippet.
    assert "use_stdin" not in out
    for name in HOOK_NAMES:
        assert not (hooks / name).exists()


# ─── --lefthook-audit (SessionStart doctor: stderr-only, non-blocking) ─────────


def test_lefthook_audit_partial_is_loud(tmp_path: Path, capsys) -> None:
    (tmp_path / "lefthook.yml").write_text(_PARTIAL_LEFTHOOK)
    assert ps.lefthook_audit(tmp_path) == 0
    err = capsys.readouterr().err
    assert "UNGUARDED" in err
    for hook in ("pre-commit", "pre-push", "commit-msg"):
        assert hook in err


def test_lefthook_audit_all_registered_is_silent(tmp_path: Path, capsys) -> None:
    (tmp_path / "lefthook.yml").write_text(_FULL_LEFTHOOK)
    assert ps.lefthook_audit(tmp_path) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""


def test_lefthook_audit_zero_registered_is_silent(tmp_path: Path, capsys) -> None:
    (tmp_path / "lefthook.yml").write_text("# user config only\n")
    assert ps.lefthook_audit(tmp_path) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""


def test_lefthook_audit_no_lefthook_is_silent(tmp_path: Path, capsys) -> None:
    assert ps.lefthook_audit(tmp_path) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""
