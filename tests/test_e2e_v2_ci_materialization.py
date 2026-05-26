"""End-to-end test of the V2 CI materialization layer.

Exercises the full happy-path of ADR-012 + ADR-013 *without* hitting
GitHub:

  PR event payload (JSON)
        │
        ▼
  sync_pr_contributions.py --event …  (real subprocess, not import)
        │
        ▼
  evidence[] block written into .edpa/backlog/{type}/{ID}.md
        │
        ▼
  detect_contributors.read_evidence() returns the same data
        │
        ▼
  Engine aggregation can mix CI signals with git-native signals

The synthetic flow covers everything except the GH Action ↔ git push
race. A separate ``@pytest.mark.e2e`` test (opt-in, requires
``EDPA_E2E_REPO`` + ``gh auth``) drives a real PR end-to-end.

Run synthetic only:        pytest tests/test_e2e_v2_ci_materialization.py -v
Run real-GitHub variants:  pytest -m e2e tests/test_e2e_v2_ci_materialization.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_SRC = ROOT / "plugin"
SYNC_SCRIPT = PLUGIN_SRC / "edpa" / "scripts" / "sync_pr_contributions.py"

sys.path.insert(0, str(PLUGIN_SRC / "edpa" / "scripts"))

from _md_frontmatter import load_md, save_md_item  # noqa: E402
import detect_contributors as dc  # noqa: E402


# ─── Sandbox fixture ────────────────────────────────────────────────────────


def _seed_project(tmp_path: Path) -> Path:
    """Build a tmp project with vendored engine + seeded backlog items.

    Returns the project root (parent of .edpa/).
    """
    project = tmp_path / "sandbox"
    edpa = project / ".edpa"
    (edpa / "config").mkdir(parents=True)
    for d in ("initiatives", "epics", "features", "stories", "defects",
              "events", "risks"):
        (edpa / "backlog" / d).mkdir(parents=True)

    # Minimal vendored engine — sync_pr_contributions.py needs id_counter
    # and _md_frontmatter at import time.
    eng_scripts = edpa / "engine" / "scripts"
    eng_scripts.mkdir(parents=True)
    for f in ("sync_pr_contributions.py", "id_counter.py",
              "_md_frontmatter.py", "detect_contributors.py"):
        shutil.copy(PLUGIN_SRC / "edpa" / "scripts" / f, eng_scripts / f)

    # Config (people, edpa.yaml, cw_heuristics override)
    (edpa / "config" / "people.yaml").write_text(yaml.safe_dump({
        "people": [
            {"id": "alice", "name": "Alice", "role": "Dev", "fte": 1.0, "capacity": 80, "github": "alice-gh"},
            {"id": "bob", "name": "Bob", "role": "Arch", "fte": 0.5, "capacity": 40, "github": "bob-gh"},
            {"id": "carol", "name": "Carol", "role": "Dev", "fte": 1.0, "capacity": 80, "github": "carol-gh"},
        ],
    }))
    (edpa / "config" / "edpa.yaml").write_text(yaml.safe_dump({
        "project": {"name": "V2 E2E Sandbox"},
    }))

    # Seed backlog items
    save_md_item(edpa / "backlog" / "stories" / "S-1.md",
                 {"id": "S-1", "type": "Story", "title": "Login flow",
                  "status": "Implementing"})
    save_md_item(edpa / "backlog" / "stories" / "S-2.md",
                 {"id": "S-2", "type": "Story", "title": "Signup",
                  "status": "Funnel"})

    # git init so sync_pr_contributions.py's auto-commit (when called
    # without --skip-commit) has somewhere to land.
    subprocess.run(["git", "init", "-q", "-b", "main"],
                   cwd=str(project), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@x"],
                   cwd=str(project), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"],
                   cwd=str(project), check=True, capture_output=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"],
                   cwd=str(project), check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=str(project), check=True,
                   capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(project),
                   check=True, capture_output=True,
                   env={**os.environ,
                        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
                        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00"})
    return project


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return _seed_project(tmp_path)


def _write_event(path: Path, **kwargs) -> Path:
    """Write a synthetic PR event payload as JSON."""
    pr = {
        "number": kwargs.get("number", 42),
        "title": kwargs.get("title", "S-1: implement login"),
        "body": kwargs.get("body", "Closes S-1"),
        "author": {"login": kwargs.get("author", "alice-gh")},
        "reviews": kwargs.get("reviews", []),
        "comments": kwargs.get("comments", []),
        "headRefName": kwargs.get("branch", "feat/login"),
        "state": "closed",
        "merged": True,
    }
    path.write_text(json.dumps({"pull_request": pr}, indent=2))
    return path


def _run_sync(project: Path, event_path: Path, *,
              extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    """Invoke sync_pr_contributions.py as a subprocess (true E2E)."""
    script = project / ".edpa" / "engine" / "scripts" / "sync_pr_contributions.py"
    cmd = [
        "python3", str(script),
        "--event", str(event_path),
        "--skip-commit",
        "--edpa-root", str(project / ".edpa"),
        *(extra_args or []),
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


# ─── Synthetic-flow tests (always run) ──────────────────────────────────────


def test_synthetic_pr_event_writes_evidence(project: Path, tmp_path: Path) -> None:
    """V2.1: PR with reviews + comments → pr_reviewer + issue_comment
    materialized (NO pr_author — local_evidence handles commit_author)."""
    event = _write_event(
        tmp_path / "evt.json",
        number=100,
        title="S-1: implement login flow",
        body="closes S-1",
        author="alice-gh",
        reviews=[
            {"id": "RV1", "author": {"login": "bob-gh"},
             "submittedAt": "2026-05-25T12:00:00Z"},
            {"id": "RV2", "author": {"login": "carol-gh"},
             "submittedAt": "2026-05-25T13:00:00Z"},
        ],
        comments=[
            {"id": "C1", "author": {"login": "bob-gh"},
             "createdAt": "2026-05-25T14:00:00Z"},
        ],
    )

    result = _run_sync(project, event)
    assert result.returncode == 0, result.stderr

    s1 = load_md(project / ".edpa/backlog/stories/S-1.md")
    sigs = s1.get("evidence", [])
    assert len(sigs) == 3, (
        f"expected 3 signals (2 reviews + 1 comment, NO pr_author), "
        f"got {len(sigs)}: {sigs}"
    )

    types = sorted(s.get("type") for s in sigs)
    assert types == ["issue_comment", "pr_reviewer", "pr_reviewer"]

    refs = {s["ref"] for s in sigs}
    assert refs == {
        "PR#100:review:RV1",
        "PR#100:review:RV2",
        "PR#100:comment:C1",
    }


def test_synthetic_idempotent_rerun(project: Path, tmp_path: Path) -> None:
    """V2.1: same review event run twice → dedupe by ref; no duplicates."""
    event = _write_event(
        tmp_path / "evt.json", number=200, author="alice-gh",
        reviews=[{"id": "RV1", "author": {"login": "bob-gh"},
                  "submittedAt": "2026-05-25T12:00:00Z"}],
    )
    _run_sync(project, event)
    first = load_md(project / ".edpa/backlog/stories/S-1.md")
    _run_sync(project, event)
    second = load_md(project / ".edpa/backlog/stories/S-1.md")

    assert len(second["evidence"]) == len(first["evidence"]) == 1


def test_synthetic_multi_pr_accumulates(project: Path, tmp_path: Path) -> None:
    """V2.1: three PRs each with one reviewer → 3 pr_reviewer signals."""
    for n, reviewer in [(301, "alice-gh"), (302, "bob-gh"), (303, "carol-gh")]:
        evt = _write_event(
            tmp_path / f"evt-{n}.json", number=n, author="other-gh",
            reviews=[{"id": "RV1", "author": {"login": reviewer},
                      "submittedAt": "2026-05-25T12:00:00Z"}],
        )
        result = _run_sync(project, evt)
        assert result.returncode == 0, result.stderr

    s1 = load_md(project / ".edpa/backlog/stories/S-1.md")
    sigs = s1["evidence"]
    assert len(sigs) == 3
    refs = {s["ref"] for s in sigs}
    assert refs == {"PR#301:review:RV1", "PR#302:review:RV1", "PR#303:review:RV1"}
    reviewers = sorted(s["person"] for s in sigs)
    assert reviewers == ["alice-gh", "bob-gh", "carol-gh"]


def test_synthetic_pr_referencing_multiple_items_explodes(
    project: Path, tmp_path: Path,
) -> None:
    """V2.1: PR mentioning S-1 AND S-2, with a reviewer → both items
    get a pr_reviewer signal each."""
    event = _write_event(
        tmp_path / "evt.json",
        number=400,
        title="S-1 + S-2: unified auth refactor",
        author="alice-gh",
        reviews=[{"id": "RV1", "author": {"login": "bob-gh"},
                  "submittedAt": "2026-05-25T12:00:00Z"}],
    )
    result = _run_sync(project, event)
    assert result.returncode == 0, result.stderr

    s1 = load_md(project / ".edpa/backlog/stories/S-1.md")
    s2 = load_md(project / ".edpa/backlog/stories/S-2.md")
    assert len(s1["evidence"]) == 1
    assert len(s2["evidence"]) == 1
    assert s1["evidence"][0]["ref"] == s2["evidence"][0]["ref"] == "PR#400:review:RV1"


def test_synthetic_pr_with_no_item_refs_is_noop(
    project: Path, tmp_path: Path,
) -> None:
    """PR without EDPA item IDs in title/body/branch → no writes anywhere."""
    event = _write_event(
        tmp_path / "evt.json",
        number=500,
        title="refactor: drop dead code",
        body="just cleanup, no item ref",
        branch="chore/dead-code",
    )
    result = _run_sync(project, event)
    assert result.returncode == 0
    assert "No EDPA item refs" in result.stdout

    s1 = load_md(project / ".edpa/backlog/stories/S-1.md")
    s2 = load_md(project / ".edpa/backlog/stories/S-2.md")
    assert "evidence" not in s1
    assert "evidence" not in s2


def test_synthetic_unknown_item_skipped_silently(
    project: Path, tmp_path: Path,
) -> None:
    """PR mentions S-999 (doesn't exist) → command succeeds, nothing written."""
    event = _write_event(
        tmp_path / "evt.json",
        number=600,
        title="S-999: nonexistent story",
        author="alice-gh",
    )
    result = _run_sync(project, event)
    assert result.returncode == 0
    # No file at backlog/stories/S-999.md, so apply_signals skips it
    assert not (project / ".edpa/backlog/stories/S-999.md").exists()


# ─── Engine integration ────────────────────────────────────────────────────


def test_read_evidence_returns_engine_shape(
    project: Path, tmp_path: Path,
) -> None:
    """V2.1: PR with reviewer + commenter → 2 signals (no pr_author)."""
    event = _write_event(
        tmp_path / "evt.json",
        number=700,
        author="alice-gh",
        reviews=[{"id": "RV1", "author": {"login": "bob-gh"},
                  "submittedAt": "2026-05-25T12:00:00Z"}],
        comments=[{"id": "C1", "author": {"login": "carol-gh"},
                   "createdAt": "2026-05-25T13:00:00Z"}],
    )
    _run_sync(project, event)

    s1_path = project / ".edpa/backlog/stories/S-1.md"
    signals = dc.read_evidence(s1_path)

    assert len(signals) == 2
    # Each entry must have the keys expected by aggregate_signals().
    for s in signals:
        assert set(s.keys()) >= {"type", "ref", "login", "weight", "detected_at"}
        assert isinstance(s["weight"], float)
    types = sorted(s["type"] for s in signals)
    assert types == ["issue_comment", "pr_reviewer"]


def test_read_evidence_empty_when_no_block(project: Path) -> None:
    """An untouched item returns [] — not None, not crash."""
    s2_path = project / ".edpa/backlog/stories/S-2.md"
    assert dc.read_evidence(s2_path) == []


def test_read_evidence_handles_missing_file(project: Path) -> None:
    """Missing item file returns [] — no exception."""
    assert dc.read_evidence(project / ".edpa/backlog/stories/S-404.md") == []


# ─── Mid-flight close-iteration sync (ADR-013) ─────────────────────────────


def test_skip_commit_writes_yaml_without_git_commit(
    project: Path, tmp_path: Path,
) -> None:
    """--skip-commit (used by close-iteration mid-flight) writes YAML
    but leaves git history alone — engine reads current state from disk."""
    head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(project),
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    event = _write_event(
        tmp_path / "evt.json", number=800, author="alice-gh",
        reviews=[{"id": "RV1", "author": {"login": "bob-gh"},
                  "submittedAt": "2026-05-25T12:00:00Z"}],
    )
    result = _run_sync(project, event)  # --skip-commit baked into helper
    assert result.returncode == 0

    head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(project),
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    assert head_before == head_after, "subprocess must not create commits"

    # YAML on disk has the new signal even though it isn't committed
    s1 = load_md(project / ".edpa/backlog/stories/S-1.md")
    assert len(s1["evidence"]) == 1


# ─── Real-GitHub variant (opt-in, requires gh + EDPA_E2E_REPO) ─────────────


@pytest.mark.e2e
def test_real_github_pr_roundtrip(tmp_path: Path) -> None:
    """End-to-end against a real repo with the contribution-sync workflow.

    Requires:
      EDPA_E2E_REPO=owner/repo    target sandbox repo with workflow installed
      gh auth login --scopes repo,workflow,delete_repo

    This test:
      1. Clones the target repo into tmp.
      2. Creates branch + S-1 item + commit + push.
      3. Opens a PR via ``gh pr create`` whose title references S-1.
      4. Merges the PR via ``gh pr merge --squash``.
      5. Polls for the contribution-sync workflow run to complete.
      6. Pulls and asserts ``.edpa/backlog/stories/S-1.md`` now has
         a ``evidence[]`` entry with type ``pr_author``.

    Slow (~3 min); skipped by default. Opt-in via ``pytest -m e2e``.
    """
    repo = os.environ.get("EDPA_E2E_REPO")
    if not repo:
        pytest.skip("EDPA_E2E_REPO env var not set")
    if not shutil.which("gh"):
        pytest.skip("gh CLI not installed")

    # Clone
    subprocess.run(["gh", "repo", "clone", repo, str(tmp_path / "repo")],
                   check=True, capture_output=True)
    work = tmp_path / "repo"

    # Sanity: workflow must be present
    workflow = work / ".github/workflows/edpa-contribution-sync.yml"
    if not workflow.exists():
        pytest.skip(f"{repo} has no edpa-contribution-sync.yml — run "
                    f"project_setup.py --with-ci on it first")

    branch = f"e2e/ci-mat-{int(time.time())}"
    subprocess.run(["git", "checkout", "-q", "-b", branch],
                   cwd=str(work), check=True, capture_output=True)

    # Seed S-1 item
    stories = work / ".edpa/backlog/stories"
    stories.mkdir(parents=True, exist_ok=True)
    save_md_item(stories / "S-1.md",
                 {"id": "S-1", "type": "Story",
                  "title": "E2E CI materialization probe",
                  "status": "Implementing"})

    subprocess.run(["git", "add", "."], cwd=str(work),
                   check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "S-1: e2e probe"],
                   cwd=str(work), check=True, capture_output=True)
    subprocess.run(["git", "push", "-q", "-u", "origin", branch],
                   cwd=str(work), check=True, capture_output=True)

    # Open + merge PR
    pr = subprocess.run(
        ["gh", "pr", "create", "--title", "S-1: e2e probe",
         "--body", "closes S-1", "--head", branch, "--base", "main"],
        cwd=str(work), check=True, capture_output=True, text=True,
    )
    pr_url = pr.stdout.strip()
    pr_num = int(pr_url.rsplit("/", 1)[-1])

    subprocess.run(["gh", "pr", "merge", str(pr_num), "--squash",
                    "--delete-branch", "--admin"],
                   cwd=str(work), check=True, capture_output=True)

    # Poll up to 5 min for the contribution-sync workflow run to finish
    deadline = time.time() + 300
    found_commit = False
    while time.time() < deadline:
        time.sleep(10)
        subprocess.run(["git", "fetch", "-q", "origin", "main"],
                       cwd=str(work), check=True, capture_output=True)
        log = subprocess.run(
            ["git", "log", "-1", "--format=%s", "origin/main"],
            cwd=str(work), capture_output=True, text=True,
        ).stdout
        if f"PR#{pr_num}" in log and "ci-materialization" in log.lower():
            found_commit = True
            break

    assert found_commit, (
        f"contribution-sync workflow did not commit evidence for PR#{pr_num} "
        f"within 5 min — check GH Actions logs for {repo}"
    )

    subprocess.run(["git", "checkout", "-q", "main"],
                   cwd=str(work), check=True, capture_output=True)
    subprocess.run(["git", "pull", "-q"], cwd=str(work),
                   check=True, capture_output=True)

    s1 = load_md(work / ".edpa/backlog/stories/S-1.md")
    sigs = s1.get("evidence", [])
    refs = {s.get("ref") for s in sigs}
    assert f"PR#{pr_num}:author" in refs, f"missing pr_author signal: {sigs}"
