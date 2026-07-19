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


# ─── Pre-sentinel (legacy) hooks — D-78 ────────────────────────────────────────
#
# Hooks installed before EDPA_HOOK_SENTINEL existed carry the same executable
# body under an older comment header. Classified on the sentinel alone they read
# as "foreign" forever: refresh never re-stamps them, so plugin hook fixes stop
# propagating, and --check-hooks reports a correctly-wired repo as 4/4 unwired.


def _legacy_variant(src_text: str) -> str:
    """A pre-sentinel EDPA hook: identical runnable lines, older header."""
    kept = [ln for ln in src_text.splitlines()
            if ps.EDPA_HOOK_SENTINEL not in ln]
    return "\n".join(kept + ["# Install: symlink into .git/hooks/ (old docs)"]) + "\n"


def _seed_legacy(tmp_path: Path, hook: str, src_name: str) -> tuple[Path, Path]:
    hooks = _git_hooks(tmp_path)
    src = ps._hook_src_dir(tmp_path) / src_name
    dst = hooks / hook
    dst.write_text(_legacy_variant(src.read_text()))
    return dst, src


def test_legacy_hook_restamped_without_refresh(tmp_path: Path) -> None:
    dst, src = _seed_legacy(tmp_path, "post-commit", "post-commit-evidence")
    ps.install_hooks(tmp_path, refresh=False)
    assert ps.EDPA_HOOK_SENTINEL in dst.read_text(), "legacy hook not re-stamped"
    assert dst.read_text() == src.read_text(), "re-stamp did not match source"


def test_legacy_hook_not_reported_foreign(tmp_path: Path, capsys) -> None:
    _seed_legacy(tmp_path, "post-commit", "post-commit-evidence")
    ps.install_hooks(tmp_path, check_only=True)
    out = capsys.readouterr().out
    assert "NOT EDPA-managed" not in out, "legacy hook misreported as foreign"
    assert "pre-sentinel" in out


def test_legacy_check_only_writes_nothing(tmp_path: Path) -> None:
    dst, _ = _seed_legacy(tmp_path, "post-commit", "post-commit-evidence")
    before = dst.read_text()
    ps.install_hooks(tmp_path, check_only=True)
    assert dst.read_text() == before, "check_only re-stamped a hook"


def test_body_match_ignores_comments_not_code(tmp_path: Path) -> None:
    """The adoption rule keys on runnable lines — a changed command is foreign."""
    dst, src = _seed_legacy(tmp_path, "post-commit", "post-commit-evidence")
    assert ps._hook_ownership(dst, src) == ps._OWN_LEGACY
    dst.write_text(dst.read_text().replace("python3", "python2"))
    assert ps._hook_ownership(dst, src) == ps._OWN_FOREIGN


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


# ─── extends: auto-wiring — S-255 ──────────────────────────────────────────────
#
# extends: is the default registration path and EDPA writes it itself. The hard
# boundary these tests pin: that one entry is the ONLY thing EDPA may change in
# a config the user owns.

import yaml  # noqa: E402

FRAG = ps.LEFTHOOK_FRAGMENT_REL


def _wire(tmp_path: Path, body: str, name: str = "lefthook.yml"):
    cfg = tmp_path / name
    cfg.write_text(body)
    return cfg, ps.ensure_lefthook_extends(cfg)


def test_wire_adds_block_when_no_extends_key(tmp_path: Path) -> None:
    cfg, result = _wire(tmp_path, "pre-commit:\n  commands:\n    lint:\n      run: x\n")
    assert result == "added"
    assert yaml.safe_load(cfg.read_text())["extends"] == [FRAG]


def test_wire_appends_to_existing_block_list(tmp_path: Path) -> None:
    cfg, result = _wire(tmp_path, "extends:\n  - shared/base.yml\n\npre-commit:\n  parallel: true\n")
    assert result == "added"
    loaded = yaml.safe_load(cfg.read_text())
    assert loaded["extends"] == ["shared/base.yml", FRAG], "order or contents wrong"
    assert loaded["pre-commit"] == {"parallel": True}, "unrelated key disturbed"


def test_wire_appends_to_flow_list(tmp_path: Path) -> None:
    cfg, result = _wire(tmp_path, "extends: [shared/base.yml]\ncolors: false\n")
    assert result == "added"
    assert yaml.safe_load(cfg.read_text())["extends"] == ["shared/base.yml", FRAG]


def test_wire_is_idempotent(tmp_path: Path) -> None:
    cfg, first = _wire(tmp_path, "pre-commit:\n  commands:\n    lint:\n      run: x\n")
    assert first == "added"
    after_first = cfg.read_text()
    assert ps.ensure_lefthook_extends(cfg) == "present"
    assert cfg.read_text() == after_first, "second run rewrote the file"


def test_wire_refuses_non_yaml_configs(tmp_path: Path) -> None:
    for name in ("lefthook.toml", "lefthook.json"):
        cfg, result = _wire(tmp_path, "[pre-commit]\n", name=name)
        assert result == "unsupported", f"{name} must not be line-edited"
        assert cfg.read_text() == "[pre-commit]\n", f"{name} was modified"


def test_wire_refuses_scalar_extends(tmp_path: Path) -> None:
    body = "extends: shared/base.yml\n"
    cfg, result = _wire(tmp_path, body)
    assert result == "unsupported", "a shape we cannot edit safely must be refused"
    assert cfg.read_text() == body


def test_wire_changes_nothing_but_the_extends_entry(tmp_path: Path) -> None:
    """The scope boundary: a stale hand-pasted EDPA block stays untouched.

    Removing it would be a cosmetic edit to someone else's file — and it is
    harmless, since the fragment wins the name collision with identical run:
    lines. Every original line must survive, in order, with only the extends
    entry added.
    """
    body = (
        "# my project hooks\n"
        "pre-commit:\n"
        "  commands:\n"
        "    my-lint:\n"
        "      run: make lint\n"
        "post-commit:\n"
        "  commands:\n"
        "    edpa-evidence:\n"          # the stale hand-pasted EDPA command
        "      run: sh .edpa/engine/scripts/hooks/post-commit-evidence\n"
    )
    cfg, result = _wire(tmp_path, body)
    assert result == "added"
    after = cfg.read_text().splitlines()
    original = body.splitlines()
    # Blank lines are ignored: the inserted block carries its own separator,
    # which is formatting on EDPA's own addition, not a change to user content.
    added = [ln for ln in after if ln.strip() and ln not in original]
    assert added == ["extends:", f"  - {FRAG}"], f"EDPA changed more than extends: {added}"
    # Every original line survives, in its original relative order.
    kept = [ln for ln in after if ln.strip() and ln in original]
    assert kept == [ln for ln in original if ln.strip()], "original lines reordered or dropped"


def test_wire_preserves_comments(tmp_path: Path) -> None:
    body = "# keep me\nextends:\n  - base.yml\n# trailing note\n"
    cfg, _ = _wire(tmp_path, body)
    after = cfg.read_text()
    assert "# keep me" in after and "# trailing note" in after
    # The entry lands inside the block, not after the trailing comment.
    assert yaml.safe_load(after)["extends"] == ["base.yml", FRAG]


def test_check_hooks_never_writes_to_lefthook_config(tmp_path: Path) -> None:
    """--check-hooks is a read-only doctor; it must not wire anything."""
    _git_hooks(tmp_path)
    body = "pre-commit:\n  commands:\n    lint:\n      run: x\n"
    cfg = tmp_path / "lefthook.yml"
    cfg.write_text(body)
    ps.install_hooks(tmp_path, check_only=True)
    assert cfg.read_text() == body, "read-only doctor edited the user's config"


def test_with_hooks_wires_extends(tmp_path: Path) -> None:
    _git_hooks(tmp_path)
    cfg = tmp_path / "lefthook.yml"
    cfg.write_text("pre-commit:\n  commands:\n    lint:\n      run: x\n")
    ps.install_hooks(tmp_path, refresh=True)
    assert yaml.safe_load(cfg.read_text())["extends"] == [FRAG]


# ─── Lefthook coexistence ──────────────────────────────────────────────────────


def test_lefthook_detected_wires_extends_and_skips_git_hooks(
    tmp_path: Path, capsys
) -> None:
    """Under lefthook EDPA wires extends: itself (S-255) rather than printing a
    snippet and hoping — and still never writes into .git/hooks/."""
    hooks = _git_hooks(tmp_path)
    cfg = tmp_path / "lefthook.yml"
    cfg.write_text("# user config\n")
    assert ps.install_hooks(tmp_path, refresh=True) is True
    for name in HOOK_NAMES:
        assert not (hooks / name).exists(), f"{name} leaked into .git/hooks"
    out = capsys.readouterr().out
    assert "lefthook detected" in out
    assert yaml.safe_load(cfg.read_text())["extends"] == [FRAG]
    assert "# user config" in cfg.read_text(), "user's own content dropped"
    # The paste-in fallback is for configs EDPA cannot edit — not this one.
    assert ps.LEFTHOOK_SNIPPET not in out


def test_unsupported_config_falls_back_to_printed_snippet(
    tmp_path: Path, capsys
) -> None:
    """A .toml config cannot be line-edited, so the manual path is still shown —
    including use_stdin: true, the pre-push correctness flag."""
    _git_hooks(tmp_path)
    (tmp_path / "lefthook.toml").write_text("[pre-commit]\n")
    ps.install_hooks(tmp_path, refresh=True)
    out = capsys.readouterr().out
    assert "could not add the extends: line" in out
    assert "use_stdin: true" in out


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


# ─── Extends-aware detection (the vendored fragment lives outside lefthook.yml) ─


def _write_fragment(root: Path) -> Path:
    frag = root / ".edpa" / "engine" / "lefthook-edpa.yml"
    frag.parent.mkdir(parents=True, exist_ok=True)
    frag.write_text(_FULL_LEFTHOOK)  # carries the four run: basenames
    return frag


def test_extends_paths_parses_block_and_inline() -> None:
    block = "extends:\n  - .edpa/engine/lefthook-edpa.yml\n  - other.yml\n"
    assert ps._lefthook_extends_paths(block) == [
        ".edpa/engine/lefthook-edpa.yml", "other.yml"]
    inline = "extends: [.edpa/engine/lefthook-edpa.yml, other.yml]\n"
    assert ps._lefthook_extends_paths(inline) == [
        ".edpa/engine/lefthook-edpa.yml", "other.yml"]
    assert ps._lefthook_extends_paths("pre-commit:\n  commands: {}\n") == []


def test_lefthook_hook_status_follows_extends(tmp_path: Path) -> None:
    # Main config holds ZERO run: lines — all four live in the extended fragment.
    _write_fragment(tmp_path)
    cfg = tmp_path / "lefthook.yml"
    cfg.write_text("extends:\n  - .edpa/engine/lefthook-edpa.yml\n")
    registered, missing = ps.lefthook_hook_status(cfg)
    assert set(registered) == set(HOOK_NAMES), "extends fragment misread as missing"
    assert missing == []


def test_lefthook_audit_extends_is_silent(tmp_path: Path, capsys) -> None:
    # extends → 4/4 → SessionStart audit must stay quiet, not false-alarm.
    _write_fragment(tmp_path)
    (tmp_path / "lefthook.yml").write_text(
        "extends: [.edpa/engine/lefthook-edpa.yml]\n")
    assert ps.lefthook_audit(tmp_path) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""


def test_lefthook_extends_missing_fragment_does_not_crash(tmp_path: Path) -> None:
    # A dangling extends (fragment not vendored yet) is best-effort: no run:
    # lines found anywhere → treated as not-opted-in, never raises.
    cfg = tmp_path / "lefthook.yml"
    cfg.write_text("extends:\n  - .edpa/engine/lefthook-edpa.yml\n")
    registered, missing = ps.lefthook_hook_status(cfg)
    assert registered == []
    assert set(missing) == set(HOOK_NAMES)
