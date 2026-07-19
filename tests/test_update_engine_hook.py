"""End-to-end tests for plugin/edpa/scripts/hooks/update_engine.sh.

The hook is a sh script invoked by Claude Code at SessionStart. It
auto-vendors plugin/edpa/{scripts,schemas,templates}/ into the project's
.edpa/engine/ when the bundled plugin VERSION diverges from the on-disk
one. Skip conditions tested: no plugin root, no .edpa/engine/ dir,
matching versions, opt-out config.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / "plugin/edpa/scripts/hooks/update_engine.sh"
PLUGIN_ROOT = REPO / "plugin"


def _run(cwd: Path, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if env_extra is not None:
        env.update(env_extra)
    else:
        env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    return subprocess.run(
        ["sh", str(HOOK)],
        cwd=str(cwd), env=env,
        capture_output=True, text=True, timeout=30, encoding="utf-8",
    )


def _seed_engine(project: Path, version: str = "1.0.0") -> None:
    """Minimal .edpa/engine/ tree the hook will recognize."""
    eng = project / ".edpa" / "engine"
    for sub in ("scripts", "schemas", "templates"):
        (eng / sub).mkdir(parents=True, exist_ok=True)
    (eng / "VERSION").write_text(version, encoding="utf-8")
    (eng / "scripts" / "sync.py").write_text("# old\n", encoding="utf-8")


def _current_plugin_version() -> str:
    import json
    return json.loads(
        (PLUGIN_ROOT / ".claude-plugin/plugin.json").read_text()
    )["version"]


# ─── Skip paths ─────────────────────────────────────────────────────────────


def test_skips_when_plugin_root_unset(tmp_path):
    # No CLAUDE_PLUGIN_ROOT in env → exit 0 silently.
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_ROOT"}
    result = _run(tmp_path, env_extra=env)
    assert result.returncode == 0
    assert result.stderr == ""


def test_skips_when_not_an_edpa_project(tmp_path):
    # cwd has no .edpa/engine/ → exit 0 silently.
    result = _run(tmp_path)
    assert result.returncode == 0
    assert result.stderr == ""


# ─── Update path ────────────────────────────────────────────────────────────


def test_updates_when_version_diverges(tmp_path):
    _seed_engine(tmp_path, version="1.0.0")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "updating engine" in result.stderr
    target_version = (tmp_path / ".edpa/engine/VERSION").read_text().strip()
    assert target_version == _current_plugin_version()
    # Scripts directory got re-vendored with the real plugin tree.
    assert (tmp_path / ".edpa/engine/scripts/backlog.py").read_text() != "# old\n"
    # Migration script is reachable from the vendored tree.
    assert (tmp_path / ".edpa/engine/scripts/migrate_backlog_yaml_to_md.py").exists()


def test_warm_path_no_update_when_versions_match(tmp_path):
    _seed_engine(tmp_path, version=_current_plugin_version())
    (tmp_path / ".edpa/engine/scripts/backlog.py").write_text("# pinned\n", encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 0
    assert "updating engine" not in result.stderr
    # Local file untouched.
    assert (tmp_path / ".edpa/engine/scripts/backlog.py").read_text() == "# pinned\n"


# ─── Downgrade guard (D-49) ─────────────────────────────────────────────────


def test_refuses_to_downgrade_when_plugin_older_than_project(tmp_path):
    """A developer whose installed plugin is BEHIND the project's committed
    engine must not have their working tree silently downgraded at
    SessionStart. The hook vendors only forward (plugin strictly newer); an
    older plugin is a no-op with a 'run /plugin update' nudge. Regression for
    D-49 — an out-of-date plugin was rsync-clobbering a newer committed engine
    on every session start, reproduced independently across developers."""
    # Project engine is far AHEAD of the installed plugin version.
    _seed_engine(tmp_path, version="99.0.0")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    # Must NOT vendor / downgrade.
    assert "updating engine" not in result.stderr
    # VERSION left untouched — no downgrade to the older plugin version.
    assert (tmp_path / ".edpa/engine/VERSION").read_text().strip() == "99.0.0"
    # rsync --delete did not run: the seeded local script survives verbatim.
    assert (tmp_path / ".edpa/engine/scripts/sync.py").read_text() == "# old\n"
    # User is told why nothing happened and how to catch up.
    assert "not downgrading" in result.stderr
    assert "/plugin update" in result.stderr


# ─── Legacy .yaml backlog warning ───────────────────────────────────────────


def test_warns_about_legacy_yaml_after_update(tmp_path):
    _seed_engine(tmp_path, version="1.0.0")
    (tmp_path / ".edpa/backlog/stories").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".edpa/backlog/stories/S-1.yaml").write_text("id: S-1\n", encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 0
    assert "legacy .yaml backlog" in result.stderr
    assert "migrate_backlog_yaml_to_md.py" in result.stderr


def test_warns_about_legacy_yaml_on_warm_path(tmp_path):
    _seed_engine(tmp_path, version=_current_plugin_version())
    (tmp_path / ".edpa/backlog/stories").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".edpa/backlog/stories/S-1.yaml").write_text("id: S-1\n", encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 0
    assert "updating engine" not in result.stderr
    assert "legacy .yaml backlog" in result.stderr


def test_no_warning_when_backlog_is_clean(tmp_path):
    _seed_engine(tmp_path, version=_current_plugin_version())
    (tmp_path / ".edpa/backlog/stories").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".edpa/backlog/stories/S-1.md").write_text(
        "---\nid: S-1\n---\n", encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 0
    assert "legacy .yaml" not in result.stderr


# ─── Opt-out ────────────────────────────────────────────────────────────────


def test_opt_out_via_edpa_yaml(tmp_path):
    _seed_engine(tmp_path, version="1.0.0")
    (tmp_path / ".edpa/config").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".edpa/config/edpa.yaml").write_text(
        "auto_update_engine: false\n", encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 0
    assert "engine update skipped" in result.stderr
    # VERSION must be untouched.
    assert (tmp_path / ".edpa/engine/VERSION").read_text().strip() == "1.0.0"


def test_opt_out_respects_quoted_value(tmp_path):
    """`auto_update_engine: "false"` should also opt out."""
    _seed_engine(tmp_path, version="1.0.0")
    (tmp_path / ".edpa/config").mkdir(parents=True, exist_ok=True)
    # NOTE: hook does a regex match on bare `false`; we document the
    # current behavior here. If we ever support quoted/true variants,
    # update both the hook and this test.
    (tmp_path / ".edpa/config/edpa.yaml").write_text(
        'auto_update_engine: "false"\n', encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 0
    # Quoted form is NOT recognized — update proceeds. Make this
    # explicit so future maintainers know.
    assert "updating engine" in result.stderr


# ─── Walks up to find .edpa/engine/ ─────────────────────────────────────────


def test_finds_edpa_root_from_subdirectory(tmp_path):
    _seed_engine(tmp_path, version="1.0.0")
    nested = tmp_path / "src" / "deep" / "path"
    nested.mkdir(parents=True)
    result = _run(nested)
    assert result.returncode == 0, result.stderr
    assert "updating engine" in result.stderr
    assert (tmp_path / ".edpa/engine/VERSION").read_text().strip() == _current_plugin_version()


# ─── Git-hook self-heal after update (2.3.0) ────────────────────────────────

SENTINEL = "EDPA-MANAGED-HOOK"


def _git_hooks(project: Path) -> Path:
    hooks = project / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    return hooks


def test_self_heal_reregisters_when_edpa_hooks_present(tmp_path):
    """A prior EDPA install (sentinel in .git/hooks/) signals opt-in; after an
    engine update the hook re-registers — reinstalling a clobbered hook and
    refreshing the rest. This is the user's "hooks gone after update" fix."""
    _seed_engine(tmp_path, version="1.0.0")
    hooks = _git_hooks(tmp_path)
    # Simulate: post-commit survived (EDPA-owned), pre-commit got clobbered/removed.
    (hooks / "post-commit").write_text(f"#!/bin/sh\n# {SENTINEL}\nexit 0\n")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "re-registering git hooks" in result.stderr
    # The missing pre-commit hook is now installed with the sentinel.
    assert (hooks / "pre-commit").exists()
    assert SENTINEL in (hooks / "pre-commit").read_text()


def test_self_heal_skipped_when_no_edpa_hooks(tmp_path):
    """A repo that never opted into hooks must not get them forced on update."""
    _seed_engine(tmp_path, version="1.0.0")
    hooks = _git_hooks(tmp_path)  # empty .git/hooks, no EDPA sentinel anywhere
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "updating engine" in result.stderr
    assert "re-registering git hooks" not in result.stderr
    for name in ("pre-commit", "pre-push", "commit-msg", "post-commit"):
        assert not (hooks / name).exists(), f"{name} forced onto opt-out repo"


def test_self_heal_lefthook_silent_when_not_opted_in(tmp_path):
    """Under lefthook with no EDPA hooks pasted (0/4), the audit stays silent —
    the repo never opted in, so don't nag. .git/hooks/ is never touched."""
    _seed_engine(tmp_path, version="1.0.0")
    hooks = _git_hooks(tmp_path)
    (tmp_path / "lefthook.yml").write_text("# user config\n")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "UNGUARDED" not in result.stderr
    for name in ("pre-commit", "pre-push", "commit-msg", "post-commit"):
        assert not (hooks / name).exists(), f"{name} written under lefthook"


def test_self_heal_lefthook_warns_on_partial_paste(tmp_path):
    """A partial lefthook paste (only the evidence hook wired, guards missing)
    is the silent blind spot — SessionStart must now flag it loudly on stderr,
    while still never editing .git/hooks/ (lefthook owns it)."""
    _seed_engine(tmp_path, version="1.0.0")
    hooks = _git_hooks(tmp_path)
    (tmp_path / "lefthook.yml").write_text(
        "post-commit:\n  commands:\n    edpa-evidence:\n"
        "      run: sh .edpa/engine/scripts/hooks/post-commit-evidence\n"
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "UNGUARDED" in result.stderr
    assert "commit-msg" in result.stderr  # a named missing guard
    for name in ("pre-commit", "pre-push", "commit-msg", "post-commit"):
        assert not (hooks / name).exists(), f"{name} written under lefthook"


# ─── Every-session partial-paste guard on the WARM path (D-77) ───────────────
#
# The cold-path audit only fires on a version change, but a partial lefthook
# paste happens at setup and must surface every session. update_engine.sh runs a
# cheap shell tripwire on the warm path that spawns the python audit ONLY when
# the wiring is partial (1..3 of 4). The warm path does not vendor, so the audit
# script the tripwire calls must be seeded (in reality it's the copy a prior
# cold path vendored).


def _seed_project_setup(project: Path) -> None:
    # project_setup.py imports sibling modules (id_counter, …) at load, so vendor
    # the whole real scripts/ tree — exactly what a prior cold path leaves behind
    # on the warm path.
    dst = project / ".edpa" / "engine" / "scripts"
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(REPO / "plugin/edpa/scripts", dst)


def test_warm_path_warns_on_partial_lefthook_paste(tmp_path):
    """Warm start (versions match) + partial paste → still warns loudly. This is
    the every-session guarantee the cold-path-only audit could not give."""
    _seed_engine(tmp_path, version=_current_plugin_version())
    _seed_project_setup(tmp_path)
    (tmp_path / "lefthook.yml").write_text(
        "post-commit:\n  commands:\n    edpa-evidence:\n"
        "      run: sh .edpa/engine/scripts/hooks/post-commit-evidence\n"
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "updating engine" not in result.stderr  # proves this is the warm path
    assert "UNGUARDED" in result.stderr
    assert "commit-msg" in result.stderr


def test_warm_path_silent_when_lefthook_fully_wired(tmp_path):
    """Warm start + all four hooks wired → no nag (and the tripwire never spawns
    python)."""
    _seed_engine(tmp_path, version=_current_plugin_version())
    _seed_project_setup(tmp_path)
    (tmp_path / "lefthook.yml").write_text(
        "pre-commit:\n  commands:\n    edpa-id-safety:\n"
        "      run: sh .edpa/engine/scripts/hooks/pre-commit-id-safety\n"
        "commit-msg:\n  commands:\n    edpa-ticket-attached:\n"
        "      run: sh .edpa/engine/scripts/hooks/commit-msg-ticket-attached {1}\n"
        "post-commit:\n  commands:\n    edpa-evidence:\n"
        "      run: sh .edpa/engine/scripts/hooks/post-commit-evidence\n"
        "pre-push:\n  commands:\n    edpa-id-safety:\n"
        "      run: sh .edpa/engine/scripts/hooks/pre-push-id-safety {1} {2}\n"
        "      use_stdin: true\n"
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "updating engine" not in result.stderr
    assert "UNGUARDED" not in result.stderr


def test_warm_path_silent_when_lefthook_not_opted_in(tmp_path):
    """Warm start + a lefthook repo with no EDPA hooks (0/4) → silent, python-free."""
    _seed_engine(tmp_path, version=_current_plugin_version())
    _seed_project_setup(tmp_path)
    (tmp_path / "lefthook.yml").write_text("# user config\n")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "UNGUARDED" not in result.stderr


def test_warm_path_silent_with_extends_fragment(tmp_path):
    """Warm start + extends-based wiring → 4/4 via the fragment, silent. The
    tripwire must follow the referenced fragment, not false-alarm on the thin
    main config."""
    _seed_engine(tmp_path, version=_current_plugin_version())
    _seed_project_setup(tmp_path)
    shutil.copy(REPO / "plugin/edpa/lefthook-edpa.yml",
                tmp_path / ".edpa/engine/lefthook-edpa.yml")
    (tmp_path / "lefthook.yml").write_text(
        "extends:\n  - .edpa/engine/lefthook-edpa.yml\n"
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "UNGUARDED" not in result.stderr
