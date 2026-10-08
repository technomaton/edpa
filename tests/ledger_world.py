"""Shared fixtures for the ID-ledger tests: a bare ``origin`` and clones.

Imported by ``test_id_ledger.py`` (the protocol) and
``test_id_authority.py`` (the allocator on top of it). Building a world
costs a couple of dozen git processes, so two templates are built once
per module and every test gets a file copy of one.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugin" / "edpa" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import _id_ledger as ledger  # noqa: E402
from _id_ledger import DEFAULT_REF  # noqa: E402
from id_counter import TYPE_DIRS  # noqa: E402

COUNTER = Path(".edpa/config/id_counters.yaml")


def git(cwd: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                       text=True, encoding="utf-8", check=False)
    if check and r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {r.stderr}")
    return r.stdout.strip()


def project(root: Path, *, authority: str | None = None,
            counters: dict | None = None, extra_ids: dict | None = None) -> Path:
    """Lay an (untracked) ``.edpa/`` skeleton into a checkout."""
    (root / ".edpa" / "config").mkdir(parents=True, exist_ok=True)
    for d in TYPE_DIRS.values():
        (root / ".edpa" / "backlog" / d).mkdir(parents=True, exist_ok=True)
    if authority or extra_ids:
        ids = {**({"authority": authority} if authority else {}),
               **(extra_ids or {})}
        (root / ".edpa" / "config" / "edpa.yaml").write_text(
            yaml.safe_dump({"ids": ids}), encoding="utf-8")
    if counters is not None:
        (root / COUNTER).write_text(
            yaml.safe_dump({"counters": counters}), encoding="utf-8")
    return root


def item(root: Path, item_id: str, dirname: str = "stories", *,
         title: str | None = None, created_at: str | None = None) -> Path:
    """Write a minimal backlog item file by hand (i.e. NOT via the
    allocator — that is the point in several tests)."""
    front: dict = {"id": item_id}
    if title:
        front["title"] = title
    if created_at:
        front["created_at"] = created_at
    path = root / ".edpa" / "backlog" / dirname / f"{item_id}.md"
    path.write_text("---\n" + yaml.safe_dump(front, sort_keys=False) + "---\n",
                    encoding="utf-8")
    return path


class World:
    """A bare ``origin`` plus independent clones under one base directory."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.origin = base / "origin.git"

    @classmethod
    def build(cls, base: Path) -> "World":
        w = cls(base)
        git(base, "init", "-q", "--bare", "-b", "main", str(w.origin))
        seed = w.clone("seed")
        (seed / "README").write_text("init\n", encoding="utf-8")
        git(seed, "add", "README")
        git(seed, "commit", "-q", "-m", "init")
        git(seed, "push", "-q", "origin", "HEAD:main")
        return w

    def clone(self, name: str) -> Path:
        path = self.base / name
        git(self.base, "clone", "-q", str(self.origin), str(path))
        git(path, "config", "user.name", name)
        git(path, "config", "user.email", f"{name}@edpa-test.local")
        git(path, "config", "commit.gpgsign", "false")
        return path

    def worktree(self, clone: Path, name: str) -> Path:
        path = self.base / name
        git(clone, "worktree", "add", "-q", str(path), "-b", name)
        return path

    def tip(self, ref: str = DEFAULT_REF) -> str | None:
        out = git(self.origin, "rev-parse", "--verify", "--quiet", ref,
                  check=False)
        return out or None

    def counters(self, ref: str = DEFAULT_REF) -> dict:
        import yaml
        return yaml.safe_load(
            git(self.origin, "cat-file", "-p", f"{ref}:counters.yaml"))


def _copy_world(src: Path, dst: Path) -> None:
    """Clone a prepared world by file copy (dozens of git spawns cheaper
    than rebuilding it) and repoint each clone's origin at the copy."""
    shutil.copytree(src, dst, dirs_exist_ok=True)
    for cfg in dst.glob("*/.git/config"):
        cfg.write_text(cfg.read_text(encoding="utf-8").replace(
            str(src), str(dst)), encoding="utf-8")


@pytest.fixture(scope="module", autouse=True)
def _isolated_git_config(tmp_path_factory):
    # Keep the developer's own git config (hooks path, signing, templates)
    # out of the picture.
    empty = tmp_path_factory.mktemp("gitcfg") / "gitconfig"
    empty.write_text("", encoding="utf-8")
    mp = pytest.MonkeyPatch()
    mp.setenv("GIT_CONFIG_GLOBAL", str(empty))
    mp.setenv("GIT_CONFIG_NOSYSTEM", "1")
    yield
    mp.undo()


@pytest.fixture(scope="module")
def _templates(tmp_path_factory, _isolated_git_config) -> tuple[Path, Path]:
    plain = tmp_path_factory.mktemp("world-plain")
    w = World.build(plain)
    w.clone("alice")
    w.clone("bob")
    seeded = tmp_path_factory.mktemp("world-seeded")
    _copy_world(plain, seeded)
    ledger.raise_floors(seeded / "alice", {"Story": 10}, create=True,
                        subject="init: seed")
    return plain, seeded


@pytest.fixture
def world(request, tmp_path: Path, _templates) -> World:
    """Fresh world per test; with ``ledger_ready`` requested, one whose
    ledger Alice already bootstrapped at Story=10."""
    plain, seeded = _templates
    _copy_world(seeded if "ledger_ready" in request.fixturenames else plain,
                tmp_path)
    return World(tmp_path)


@pytest.fixture
def ledger_ready(world: World) -> World:
    return world


@pytest.fixture
def alice(world: World) -> Path:
    return world.base / "alice"


@pytest.fixture
def bob(world: World) -> Path:
    return world.base / "bob"
