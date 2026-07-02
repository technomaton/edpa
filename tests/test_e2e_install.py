#!/usr/bin/env python3
"""
EDPA E2E Install Test

Verifies that a clean project can install EDPA, plant minimal data,
and run the full pipeline (engine + traceability + pi_close + velocity)
without any root-level pollution and without depending on the source
repo's own .edpa/ data.

Mirrors the manual /tmp/edpa-clean-test workflow as an automated check.

Run: python -m pytest tests/test_e2e_install.py -v
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:
    pytest.skip("PyYAML not installed", allow_module_level=True)


ROOT = Path(__file__).resolve().parent.parent
PLUGIN_SRC = ROOT / "plugin"
TEMPLATE_DIR = PLUGIN_SRC / "edpa" / "templates"

ALLOWED_ROOT_ENTRIES = {".claude", ".edpa", ".git", "README.md"}


def _install_plugin(target: Path):
    """Replicate install.sh behaviour using local source — no network.

    v1.18.4+: engine vendors to `.edpa/engine/` (not `.claude/edpa/`).
    `.github/workflows/` install is delegated to /edpa:setup; install.sh
    itself only handles the engine + `.edpa/` data tree.
    """
    engine = target / ".edpa" / "engine"
    engine.mkdir(parents=True)
    for sub in ("scripts", "schemas", "templates"):
        shutil.copytree(PLUGIN_SRC / "edpa" / sub, engine / sub)
    plugin_version = json.loads((PLUGIN_SRC / ".claude-plugin" / "plugin.json").read_text())["version"]
    (engine / "VERSION").write_text(plugin_version + "\n")

    edpa = target / ".edpa"
    for sub in [
        "config", "iterations", "reports", "snapshots", "data",
        "backlog/initiatives", "backlog/epics", "backlog/features", "backlog/stories",
    ]:
        (edpa / sub).mkdir(parents=True, exist_ok=True)

    # Seed templates: people.yaml + edpa.yaml. Engine reads canonical CW
    # heuristics from .edpa/engine/templates/cw_heuristics.yaml.tmpl
    # directly — no .edpa/config/heuristics.yaml is needed.
    shutil.copy(TEMPLATE_DIR / "people.yaml.tmpl", edpa / "config" / "people.yaml")
    shutil.copy(TEMPLATE_DIR / "edpa.yaml.tmpl", edpa / "config" / "edpa.yaml")


def _plant_minimal_backlog(target: Path):
    backlog = target / ".edpa" / "backlog"
    (backlog / "initiatives" / "I-1.md").write_text(
        "---\nid: I-1\ntype: Initiative\ntitle: T\nparent: null\n---\n"
    )
    (backlog / "epics" / "E-1.md").write_text(
        "---\nid: E-1\ntype: Epic\ntitle: T\nparent: I-1\n---\n"
    )
    (backlog / "features" / "F-1.md").write_text(
        "---\nid: F-1\ntype: Feature\ntitle: T\nparent: E-1\njs: 5\n---\n"
    )
    (backlog / "stories" / "S-1.md").write_text(
        "---\nid: S-1\ntype: Story\ntitle: T\nparent: F-1\njs: 5\n"
        "status: Done\niteration: PI-2026-1.1\n"
        "contributors:\n  - person: example-arch\n    as: owner\n    cw: 1\n"
        "---\n"
    )
    (target / ".edpa" / "iterations" / "PI-2026-1.1.yaml").write_text(
        "iteration:\n"
        "  id: PI-2026-1.1\n"
        "  pi: PI-2026-1\n"
        "  status: closed\n"
        "  start_date: 2026-01-05\n"
        "  end_date: 2026-01-16\n"
        "  weeks: 2\n"
        "planning:\n"
        "  capacity: 40\n"
        "  planned_sp: 5\n"
        "delivery:\n"
        "  delivered_sp: 5\n"
        "  velocity: 5\n"
    )


def _run(target: Path, *args):
    return subprocess.run(
        [sys.executable, str(target / ".edpa" / "engine" / "scripts" / args[0]), *args[1:]],
        cwd=target, capture_output=True, text=True, encoding="utf-8",
    )


@pytest.fixture
def project(tmp_path):
    proj = tmp_path / "p"
    proj.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=proj, check=True)
    (proj / "README.md").write_text("# Test\n")
    _install_plugin(proj)
    return proj


def test_install_creates_only_dot_directories(project):
    """install must not create any root-level non-dot entries beyond README."""
    actual = {p.name for p in project.iterdir()}
    extras = actual - ALLOWED_ROOT_ENTRIES
    assert not extras, f"unexpected root entries after install: {extras}"


def test_install_vendors_engine_under_edpa(project):
    """Engine (scripts + schemas + templates) lives in .edpa/engine/."""
    engine = project / ".edpa" / "engine"
    assert engine.is_dir()
    assert (engine / "VERSION").is_file()
    for sub in ("scripts", "schemas", "templates"):
        assert (engine / sub).is_dir(), f"missing .edpa/engine/{sub}/"


def test_install_includes_new_action_scripts(project):
    scripts = project / ".edpa" / "engine" / "scripts"
    for name in ("traceability.py", "pi_close.py", "velocity.py"):
        assert (scripts / name).is_file(), f"missing script: {name}"


def test_traceability_passes_on_valid_backlog(project):
    _plant_minimal_backlog(project)
    r = _run(project, "traceability.py")
    assert r.returncode == 0, r.stderr
    assert "All parent chains valid" in r.stdout


def test_traceability_fails_on_orphan(project):
    _plant_minimal_backlog(project)
    (project / ".edpa" / "backlog" / "stories" / "S-ORPHAN.md").write_text(
        "---\nid: S-ORPHAN\ntype: Story\ntitle: bad\n---\n"
    )
    r = _run(project, "traceability.py")
    assert r.returncode == 1
    assert "S-ORPHAN" in r.stdout


def test_pi_close_aggregates_iteration(project):
    _plant_minimal_backlog(project)
    r = _run(project, "pi_close.py", "--pi", "PI-2026-1")
    assert r.returncode == 0, r.stderr
    results = json.loads(
        (project / ".edpa" / "reports" / "pi-PI-2026-1" / "pi_results.json").read_text()
    )
    assert results["summary"]["total_delivered_sp"] == 5
    assert results["summary"]["avg_predictability_pct"] == 100.0


def test_velocity_writes_report(project):
    _plant_minimal_backlog(project)
    r = _run(project, "velocity.py")
    assert r.returncode == 0, r.stderr
    report = json.loads(
        (project / ".edpa" / "reports" / "velocity" / "velocity.json").read_text()
    )
    assert report["iteration_count"] == 1
    assert report["average_velocity"] == 5


def test_engine_runs_with_template_people(project):
    _plant_minimal_backlog(project)
    r = subprocess.run(
        [sys.executable, str(project / ".edpa" / "engine" / "scripts" / "engine.py"),
         "--edpa-root", str(project / ".edpa"),
         "--iteration", "PI-2026-1.1"],
        cwd=project, capture_output=True, text=True, encoding="utf-8",
    )
    assert r.returncode == 0, r.stderr
    assert "All invariants passed: YES" in r.stdout
    assert (project / ".edpa" / "reports" / "iteration-PI-2026-1.1" / "edpa_results.json").is_file()


def test_no_root_pollution_after_full_pipeline(project):
    _plant_minimal_backlog(project)
    _run(project, "traceability.py")
    _run(project, "pi_close.py", "--pi", "PI-2026-1")
    _run(project, "velocity.py")
    actual = {p.name for p in project.iterdir()}
    extras = actual - ALLOWED_ROOT_ENTRIES
    assert not extras, f"pipeline created root-level entries: {extras}"


def test_plugin_code_does_not_reference_source_repo(project):
    """No script may resolve paths back into the EDPA source repo."""
    forbidden = str(ROOT.resolve())
    scripts = project / ".claude" / "edpa" / "scripts"
    for py in scripts.glob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        assert forbidden not in text, f"{py.name} references source repo path"


# ─── Real install.sh execution — download branches, offline (D-39) ──────────
#
# Everything above replicates install.sh in Python; the tests below run the
# REAL script with a stub `curl` and a PATH that deliberately lacks `gh`, so
# install.sh must take its curl download branches. The release-asset fixture
# is built with the exact tar invocation .github/workflows/release.yml uses,
# which catches layout drift between the workflow and either download branch
# without touching the network. Regression tests for D-39: the curl branch
# used to double-nest the payload (edpa/plugin/plugin/) and abort under
# `set -e`, and --with-server probed a path no payload layout ever had.

INSTALL_SH = ROOT / "install.sh"
_SH = Path("/bin/sh")

requires_posix_sh = pytest.mark.skipif(
    not _SH.exists(), reason="requires POSIX /bin/sh"
)

_COREUTILS = (
    "mktemp", "rm", "tar", "gzip", "grep", "head", "cut", "mkdir", "cp",
    "chmod", "find", "wc", "tr", "touch", "mv", "cat",
)


@pytest.fixture(scope="module")
def release_tarball(tmp_path_factory):
    """edpa-plugin.tar.gz built exactly like release.yml builds it."""
    tarball = tmp_path_factory.mktemp("release-asset") / "edpa-plugin.tar.gz"
    subprocess.run(
        ["tar", "--exclude=__pycache__", "--exclude=*.pyc",
         "--exclude=.DS_Store", "-czf", str(tarball), "plugin/"],
        cwd=ROOT, check=True, env={**os.environ, "COPYFILE_DISABLE": "1"},
    )
    return tarball


def _curl_stub_release(tarball: Path) -> str:
    """curl(1) stand-in: answers the GitHub releases API with one asset URL
    and serves the local tarball for the asset download."""
    return (
        "#!/bin/sh\n"
        'case "$*" in\n'
        "  *api.github.com*)\n"
        "    printf '%s\\n' "
        "'\"browser_download_url\": \"https://release.invalid/edpa-plugin.tar.gz\"'\n"
        "    ;;\n"
        f'  *edpa-plugin.tar.gz*) exec /bin/cat "{tarball}" ;;\n'
        "  *) exit 22 ;;\n"
        "esac\n"
    )


def _curl_stub_main(tarball: Path) -> str:
    """curl(1) stand-in: no release assets published; serves the local
    tarball for the main-branch archive download."""
    return (
        "#!/bin/sh\n"
        'case "$*" in\n'
        "  *api.github.com*) exit 0 ;;\n"
        f'  *archive/refs/heads/main.tar.gz*) exec /bin/cat "{tarball}" ;;\n'
        "  *) exit 22 ;;\n"
        "esac\n"
    )


def _make_offline_bin(bindir: Path, curl_stub: str) -> None:
    """PATH dir with just enough tools for install.sh — and no `gh`, so the
    script deterministically takes the curl branch."""
    bindir.mkdir(parents=True, exist_ok=True)
    for name in _COREUTILS:
        real = shutil.which(name)
        assert real, f"test host lacks required binary: {name}"
        (bindir / name).symlink_to(real)
    py = bindir / "python3"
    py.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
    py.chmod(0o755)
    curl = bindir / "curl"
    curl.write_text(curl_stub, encoding="utf-8")
    curl.chmod(0o755)


def _run_install_sh(workdir: Path, bindir: Path, scratch: Path, *args: str):
    workdir.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": str(bindir),
        "TMPDIR": str(scratch),
        "HOME": str(workdir),
        "LC_ALL": "C",
    }
    return subprocess.run(
        [str(_SH), str(INSTALL_SH), *args],
        cwd=workdir, env=env, capture_output=True, text=True,
        encoding="utf-8", timeout=180,
    )


def _synthetic_payload(root: Path, tools_under: str | None, version: str = "9.9.9") -> None:
    """Minimal plugin payload install.sh can vendor. tools_under: None (no
    server source), "root" (git-clone / main-tarball layout), or "plugin"
    (release-asset layout with the server packed under plugin/)."""
    plugin = root / "plugin"
    for sub in ("scripts", "schemas", "templates"):
        (plugin / "edpa" / sub).mkdir(parents=True)
        (plugin / "edpa" / sub / ".keep").write_text("", encoding="utf-8")
    (plugin / ".claude-plugin").mkdir()
    (plugin / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"version": version}), encoding="utf-8")
    if tools_under is not None:
        base = plugin if tools_under == "plugin" else root
        server = base / "tools" / "pi-planning"
        server.mkdir(parents=True)
        (server / "package.json").write_text(
            '{"name": "pi-planning-stub"}\n', encoding="utf-8")


def _tar_dir(src_parent: Path, member: str, out: Path) -> Path:
    subprocess.run(
        ["tar", "-czf", str(out), member], cwd=src_parent, check=True,
        env={**os.environ, "COPYFILE_DISABLE": "1"},
    )
    return out


@requires_posix_sh
def test_release_tarball_extraction_layout(tmp_path, release_tarball):
    """Both download branches extract the release asset with
    `mkdir -p $TMPDIR/edpa && tar -xz -C $TMPDIR/edpa`; the asset root is
    plugin/, so PLUGIN_SRC=$TMPDIR/edpa/plugin must resolve. Guards the
    layout contract between release.yml and install.sh."""
    dest = tmp_path / "edpa"
    dest.mkdir()
    subprocess.run(["tar", "-xzf", str(release_tarball), "-C", str(dest)], check=True)
    assert (dest / "plugin" / "edpa" / "scripts").is_dir()
    assert (dest / "plugin" / ".claude-plugin" / "plugin.json").is_file()


@requires_posix_sh
def test_install_sh_curl_release_branch_end_to_end(tmp_path, release_tarball):
    """The documented no-gh one-liner (curl | sh) against a release.yml-shaped
    asset must exit 0, vendor the engine (incl. assets/ + rules/), and pin
    the real plugin.json version — not the 'latest-release' placeholder."""
    bindir = tmp_path / "bin"
    _make_offline_bin(bindir, _curl_stub_release(release_tarball))
    work = tmp_path / "proj"
    r = _run_install_sh(work, bindir, tmp_path / "scratch")
    assert r.returncode == 0, f"install.sh failed\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    engine = work / ".edpa" / "engine"
    assert list((engine / "scripts").glob("*.py")), "no engine scripts vendored"
    expected = json.loads(
        (PLUGIN_SRC / ".claude-plugin" / "plugin.json").read_text())["version"]
    assert (engine / "VERSION").read_text().strip() == expected
    # Vendor-set parity with project_setup.py (D-39): assets + rules ship too.
    assert (engine / "assets" / "pi-bundle.html").is_file(), \
        "assets/ missing — pi_planning.py cannot find the vendored bundle"
    assert (engine / "rules").is_dir()
    assert (work / ".edpa" / "config" / "edpa.yaml").is_file()


@requires_posix_sh
def test_with_server_vendors_from_repo_root_layout(tmp_path):
    """--with-server, main-branch tarball layout: tools/pi-planning sits at
    the payload root (like a git clone), not under plugin/."""
    payload = tmp_path / "payload" / "edpa-main"
    _synthetic_payload(payload, tools_under="root")
    tarball = _tar_dir(tmp_path / "payload", "edpa-main", tmp_path / "main.tar.gz")
    bindir = tmp_path / "bin"
    _make_offline_bin(bindir, _curl_stub_main(tarball))
    work = tmp_path / "proj"
    r = _run_install_sh(work, bindir, tmp_path / "scratch", "--with-server")
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert (work / ".claude" / "edpa" / "server" / "package.json").is_file(), r.stdout
    assert "skipping" not in r.stdout


@requires_posix_sh
def test_with_server_vendors_from_release_asset_layout(tmp_path):
    """--with-server, release-asset layout: tools/pi-planning packed under
    plugin/ resolves via the second probe path."""
    payload = tmp_path / "payload"
    _synthetic_payload(payload, tools_under="plugin")
    tarball = _tar_dir(payload, "plugin", tmp_path / "edpa-plugin.tar.gz")
    bindir = tmp_path / "bin"
    _make_offline_bin(bindir, _curl_stub_release(tarball))
    work = tmp_path / "proj"
    r = _run_install_sh(work, bindir, tmp_path / "scratch", "--with-server")
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert (work / ".claude" / "edpa" / "server" / "package.json").is_file(), r.stdout


@requires_posix_sh
def test_with_server_skip_message_names_probed_paths(tmp_path):
    """When neither layout carries the server source, the install still
    succeeds and the skip message names the paths that were probed."""
    payload = tmp_path / "payload"
    _synthetic_payload(payload, tools_under=None)
    tarball = _tar_dir(payload, "plugin", tmp_path / "edpa-plugin.tar.gz")
    bindir = tmp_path / "bin"
    _make_offline_bin(bindir, _curl_stub_release(tarball))
    work = tmp_path / "proj"
    r = _run_install_sh(work, bindir, tmp_path / "scratch", "--with-server")
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert "server source not in payload" in r.stdout
    assert r.stdout.count("tools/pi-planning") >= 2, \
        "skip message must name both probed paths"
    assert not (work / ".claude" / "edpa" / "server").exists()
