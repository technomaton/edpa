"""Tests for plugin/edpa/scripts/local_evidence.py.

End-to-end tests against a real tmp git repo. Each test makes a commit,
invokes ``local_evidence.main()`` as if from a post-commit hook, and
asserts that the touched items' ``evidence[]`` was updated and a
follow-up commit was created.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import local_evidence as le  # noqa: E402
from _md_frontmatter import load_md, save_md_item  # noqa: E402


# ─── Fixtures ─────────────────────────────────────────────────────────────


def _git(args, cwd, env_extra=None, check=True):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(["git", *args], cwd=str(cwd), env=env,
                          check=check, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(["init", "-q", "-b", "main"], cwd=tmp_path)
    _git(["config", "user.email", "alice@example.dev"], cwd=tmp_path)
    _git(["config", "user.name", "Alice Senior"], cwd=tmp_path)
    _git(["config", "commit.gpgsign", "false"], cwd=tmp_path)

    edpa = tmp_path / ".edpa"
    (edpa / "config").mkdir(parents=True)
    for d in ("initiatives", "epics", "features", "stories", "defects",
              "events", "risks"):
        (edpa / "backlog" / d).mkdir(parents=True)
    (edpa / "config" / "people.yaml").write_text(yaml.safe_dump({
        "people": [
            {"id": "alice", "name": "Alice Senior",
             "role": "Dev", "email": "alice@example.dev"},
            {"id": "bob", "name": "Bob Architect",
             "role": "Arch", "email": "bob@example.dev",
             "github": "bob-bot"},
        ],
    }))
    save_md_item(edpa / "backlog" / "stories" / "S-1.md", {
        "id": "S-1", "type": "Story", "title": "Login",
        "status": "Implementing",
    })
    save_md_item(edpa / "backlog" / "stories" / "S-2.md", {
        "id": "S-2", "type": "Story", "title": "Signup",
        "status": "Implementing",
    })
    _git(["add", "."], cwd=tmp_path)
    _git(["commit", "-q", "-m", "init"], cwd=tmp_path,
         env_extra={"GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
                    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00"})
    return tmp_path


def _make_commit(repo: Path, msg: str, files_changed: list[tuple[str, str]],
                 author_email: str = "alice@example.dev",
                 author_name: str = "Alice Senior") -> str:
    """Create + return the new HEAD sha. files_changed: [(path, content), …]."""
    for rel, content in files_changed:
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    _git(["add", *(p for p, _ in files_changed)], cwd=repo)
    _git(["commit", "-q", "-m", msg], cwd=repo, env_extra={
        "GIT_AUTHOR_EMAIL": author_email, "GIT_AUTHOR_NAME": author_name,
        "GIT_COMMITTER_EMAIL": author_email, "GIT_COMMITTER_NAME": author_name,
        "GIT_AUTHOR_DATE": "2026-05-26T10:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-05-26T10:00:00+00:00",
    })
    return _git(["rev-parse", "HEAD"], cwd=repo).stdout.strip()


def _run_emitter(repo: Path) -> int:
    """Invoke local_evidence.main() as if from post-commit hook."""
    old = Path.cwd()
    try:
        os.chdir(repo)
        return le.main()
    finally:
        os.chdir(old)


# ─── Item detection ───────────────────────────────────────────────────────


def test_detect_items_from_subject(repo: Path) -> None:
    sha = _make_commit(repo, "S-1: implement login",
                       [("src/login.py", "# code\n")])
    commit = le._head_commit(repo)
    assert le.detect_items(commit) == ["S-1"]


def test_detect_items_from_body(repo: Path) -> None:
    sha = _make_commit(repo,
                       "wip\n\ncloses S-2 and refines F-3",
                       [("src/x.py", "x\n")])
    commit = le._head_commit(repo)
    ids = le.detect_items(commit)
    assert "S-2" in ids
    assert "F-3" in ids


def test_detect_items_from_changed_backlog_paths(repo: Path) -> None:
    """Commit modifying .edpa/backlog/stories/S-1.md → S-1 inferred."""
    save_md_item(repo / ".edpa/backlog/stories/S-1.md", {
        "id": "S-1", "type": "Story", "title": "Login Renamed",
        "status": "Done",
    })
    _git(["add", ".edpa/backlog/stories/S-1.md"], cwd=repo)
    _git(["commit", "-q", "-m", "tweak"], cwd=repo)
    commit = le._head_commit(repo)
    assert le.detect_items(commit) == ["S-1"]


def test_detect_items_dedupes_across_sources(repo: Path) -> None:
    save_md_item(repo / ".edpa/backlog/stories/S-1.md", {
        "id": "S-1", "type": "Story", "title": "Updated",
    })
    _git(["add", "."], cwd=repo)
    _git(["commit", "-q", "-m", "S-1: tweak"], cwd=repo)
    commit = le._head_commit(repo)
    assert le.detect_items(commit) == ["S-1"]


# ─── Person resolution ────────────────────────────────────────────────────


def test_resolve_person_by_email(repo: Path) -> None:
    people = le._load_people(repo / ".edpa")
    assert le._resolve_person("alice@example.dev", "Alice", people) == "alice"


def test_resolve_person_unknown_returns_none(repo: Path) -> None:
    people = le._load_people(repo / ".edpa")
    assert le._resolve_person("ghost@nowhere.dev", "Ghost", people) is None


def test_resolve_person_by_github_login_prefix(repo: Path) -> None:
    people = le._load_people(repo / ".edpa")
    # bob's people.yaml has github: bob-bot — match local-part 'bob'
    assert le._resolve_person("bob@notlisted.io", "B", people) == "bob"


# ─── End-to-end emit + commit ─────────────────────────────────────────────


def test_emit_creates_evidence_and_followup_commit(repo: Path) -> None:
    _make_commit(repo, "S-1: implement login endpoint",
                 [("src/login.py", "# code\n")])
    rc = _run_emitter(repo)
    assert rc == 0

    # Evidence written
    s1 = load_md(repo / ".edpa/backlog/stories/S-1.md")
    sigs = s1["evidence"]
    types = sorted(s.get("type") for s in sigs)
    assert types == ["commit_author"]
    assert sigs[0]["person"] == "alice"
    assert sigs[0]["ref"].startswith("commit/")

    # Follow-up commit exists with chore(evidence): prefix
    log = _git(["log", "-1", "--format=%s"], cwd=repo).stdout.strip()
    assert log.startswith("chore(evidence):")


def test_emit_parses_contribute_directive(repo: Path) -> None:
    body_msg = ("S-1: implement\n\nLong rationale.\n"
                "/contribute @bob weight:1.5")
    _make_commit(repo, body_msg, [("src/login.py", "x\n")])
    _run_emitter(repo)

    s1 = load_md(repo / ".edpa/backlog/stories/S-1.md")
    types = {s["type"] for s in s1["evidence"]}
    persons = {s["person"] for s in s1["evidence"]}
    assert "commit_author" in types
    assert "manual:commit_message" in types
    assert "bob" in persons


def test_emit_dedupes_across_runs(repo: Path) -> None:
    """Running the emitter twice on the same HEAD → no duplicates."""
    _make_commit(repo, "S-1: tweak", [("a.txt", "a\n")])
    _run_emitter(repo)
    n_after_first = len(load_md(repo / ".edpa/backlog/stories/S-1.md")["evidence"])
    # Reset HEAD to the source commit (drop the follow-up) and re-run
    _git(["reset", "--hard", "HEAD~1"], cwd=repo)
    _run_emitter(repo)
    n_after_second = len(load_md(repo / ".edpa/backlog/stories/S-1.md")["evidence"])
    assert n_after_first == n_after_second


def test_emit_self_commit_skipped(repo: Path) -> None:
    """Self-generated chore(evidence): commits don't recurse."""
    # Simulate the script's own commit
    p = repo / ".edpa/backlog/stories/S-1.md"
    data = load_md(p)
    data["evidence"] = [{"type": "commit_author", "person": "alice",
                         "weight": 2.78, "ref": "commit/abcdef0",
                         "at": "2026-05-26T10:00:00Z"}]
    save_md_item(p, data)
    _git(["add", "."], cwd=repo)
    _git(["commit", "-q", "-m",
          "chore(evidence): S-1 from abcdef0"], cwd=repo)

    rc = _run_emitter(repo)
    assert rc == 0
    # No new commit should have been created — log -1 still shows the
    # chore(evidence) one we made, not a recursive third one.
    log = _git(["log", "--format=%s", "-2"], cwd=repo).stdout
    assert log.count("chore(evidence)") == 1


def test_emit_no_item_refs_is_noop(repo: Path) -> None:
    _make_commit(repo, "chore: bump version", [("VERSION", "1.0\n")])
    rc = _run_emitter(repo)
    assert rc == 0
    # No follow-up commit
    log = _git(["log", "-1", "--format=%s"], cwd=repo).stdout.strip()
    assert log == "chore: bump version"


def test_emit_unknown_author_skipped_with_warning(repo: Path, capsys) -> None:
    _make_commit(repo, "S-1: work", [("a.txt", "x\n")],
                 author_email="ghost@nowhere.dev", author_name="Ghost")
    rc = _run_emitter(repo)
    assert rc == 0
    err = capsys.readouterr().err
    assert "not in" in err and "people.yaml" in err


def test_emit_disabled_via_env(repo: Path, monkeypatch) -> None:
    monkeypatch.setenv(le.ENV_DISABLE, "1")
    _make_commit(repo, "S-1: work", [("a.txt", "x\n")])
    _run_emitter(repo)
    s1 = load_md(repo / ".edpa/backlog/stories/S-1.md")
    assert "evidence" not in s1  # no emission


def test_emit_unknown_item_warning_does_not_fail(repo: Path, capsys) -> None:
    _make_commit(repo, "S-999: phantom story", [("a.txt", "x\n")])
    rc = _run_emitter(repo)
    assert rc == 0
    err = capsys.readouterr().err
    assert "S-999" in err


def test_emit_merge_commit_skipped(repo: Path) -> None:
    """Merge commits shouldn't be credited (they aggregate, not author)."""
    _git(["checkout", "-b", "feat/x"], cwd=repo)
    _make_commit(repo, "S-1: work", [("a.txt", "x\n")])
    _run_emitter(repo)  # this should work and add evidence
    n_before = len(load_md(repo / ".edpa/backlog/stories/S-1.md")["evidence"])

    _git(["checkout", "main"], cwd=repo)
    _git(["merge", "--no-ff", "-m", "Merge feat/x", "feat/x"], cwd=repo)
    _run_emitter(repo)
    n_after = len(load_md(repo / ".edpa/backlog/stories/S-1.md")["evidence"])
    assert n_after == n_before  # merge commit didn't add new signals
