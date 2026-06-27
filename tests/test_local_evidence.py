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
                          check=check, capture_output=True, text=True, encoding="utf-8")


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


# ─── Calibrated-weight load (D-35) ────────────────────────────────────────


def _write_cw_heuristics(repo: Path, commit_author: float = 4.00) -> None:
    """Write a cw_heuristics.yaml whose calibrated anchor lives under the
    canonical ``signals:`` block (the same key detect_contributors.py and
    calibrate_signals.py use)."""
    (repo / ".edpa" / "config" / "cw_heuristics.yaml").write_text(
        yaml.safe_dump({
            "schema_version": "1.0",
            "signals": {
                "commit_author": commit_author,
                "pr_reviewer": 2.17,
                "issue_comment": 1.46,
            },
        }), encoding="utf-8")


def test_load_weights_reads_signals_block(repo: Path) -> None:
    """D-35: _load_weights must read the calibrated anchor from the
    ``signals:`` block (cw_heuristics single source), NOT a non-existent
    ``signal_weights:`` key — otherwise commit_author silently falls back
    to the stale 2.78 default instead of the calibrated 4.00."""
    _write_cw_heuristics(repo, commit_author=4.00)
    weights = le._load_weights(repo / ".edpa")
    assert weights["commit_author"] == 4.00


def test_build_signals_emits_calibrated_commit_author_weight(repo: Path) -> None:
    """D-35 end-to-end: with a signals: block present, the emitted
    commit_author signal must carry weight 4.00 (and raw_weight 4.00)."""
    _write_cw_heuristics(repo, commit_author=4.00)
    sha = _make_commit(repo, "S-1: implement login",
                       [("src/login.py", "# code\n")])
    commit = le._head_commit(repo)
    weights = le._load_weights(repo / ".edpa")
    sigs = le.build_signals(commit, ["S-1"], "alice", weights)
    ca = [s["signal"] for s in sigs if s["signal"]["type"] == "commit_author"]
    assert ca, "no commit_author signal emitted"
    assert ca[0]["weight"] == 4.00
    assert ca[0]["raw_weight"] == 4.00


def test_load_weights_no_config_uses_calibrated_default(repo: Path) -> None:
    """D-35: even config-less, the DEFAULT_WEIGHTS fallback for
    commit_author must match the calibrated anchor (4.00), so a project
    without a cw_heuristics.yaml is not silently under-weighting commits."""
    (repo / ".edpa" / "config" / "cw_heuristics.yaml").unlink(missing_ok=True)
    weights = le._load_weights(repo / ".edpa")
    assert weights["commit_author"] == 4.00


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


def test_emit_keeps_contribute_weight_above_ten(repo: Path) -> None:
    """D-34: a /contribute weight >10 must still land as a manual:commit_message
    signal. build_signals previously clamped to [0,10] and silently dropped
    larger weights — diverging from detect_contributors (no upper bound) and
    losing legitimate strong manual attributions (e.g. weight:13 for off-repo
    coordination work)."""
    _make_commit(repo, "S-1: coordinate\n\n/contribute @bob weight:13",
                 [("src/coord.py", "x\n")])
    _run_emitter(repo)

    s1 = load_md(repo / ".edpa/backlog/stories/S-1.md")
    manual = [s for s in s1["evidence"]
              if s["type"] == "manual:commit_message" and s["person"] == "bob"]
    assert manual, "weight:13 /contribute directive was silently dropped"
    assert manual[0]["weight"] == 13.0


def test_referenced_only_id_is_audit_only(repo: Path) -> None:
    """D-38: an item that only *appears* in the message (not in the leading
    scope, and its backlog .md not changed) is recorded audit-only —
    commit_author weight 0, tagged ``referenced`` — so a 'see also / supersedes
    / renumbered from X' mention never inflates X's credit. The scoped item
    keeps full weight, and the agent / ``/contribute`` extras never leak onto
    the mention."""
    msg = ("fix(S-1): real work\n\n"
           "renumbered from S-2; see S-2 for context\n"
           "/contribute @bob weight:2\n"
           "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>")
    _make_commit(repo, msg, [("src/login.py", "# code\n")])
    assert _run_emitter(repo) == 0

    # S-1 (leading scope): full-weight commit_author + agent + manual, untagged.
    s1 = load_md(repo / ".edpa/backlog/stories/S-1.md")["evidence"]
    ca1 = [s for s in s1 if s["type"] == "commit_author"]
    assert ca1 and all(s["weight"] > 0 for s in ca1)
    assert all("referenced" not in s.get("tags", []) for s in ca1)
    assert any(s["type"] == "agent_contribution" for s in s1)
    assert any(s["type"] == "manual:commit_message" for s in s1)

    # S-2 (mentioned only): commit_author recorded but weight 0 + referenced tag,
    # raw_weight kept; NO agent/manual credit leaks onto a mere reference.
    s2 = load_md(repo / ".edpa/backlog/stories/S-2.md")["evidence"]
    ca2 = [s for s in s2 if s["type"] == "commit_author"]
    assert ca2, "the reference must still be recorded for audit"
    assert all(s["weight"] == 0 for s in ca2)
    assert all("referenced" in s.get("tags", []) for s in ca2)
    assert all(s.get("raw_weight") for s in ca2)
    assert not [s for s in s2
                if s["type"] in ("agent_contribution", "manual:commit_message")]


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


# ─── Phase 1: state_transition materialization ────────────────────────────


def _set_status(repo: Path, item_rel: str, status: str) -> None:
    p = repo / item_rel
    data = load_md(p)
    data["status"] = status
    save_md_item(p, data)


def _commit_status_flip(repo: Path, item_rel: str, status: str,
                        msg: str) -> str:
    _set_status(repo, item_rel, status)
    _git(["add", "."], cwd=repo)
    _git(["commit", "-q", "-m", msg], cwd=repo, env_extra={
        "GIT_AUTHOR_DATE": "2026-05-26T10:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-05-26T10:00:00+00:00",
    })
    return _git(["rev-parse", "HEAD"], cwd=repo).stdout.strip()


def test_emit_writes_state_transition_signal(repo: Path) -> None:
    """A commit that flips S-1 status emits a weight-0 state_transition."""
    _commit_status_flip(repo, ".edpa/backlog/stories/S-1.md", "Done",
                        "S-1: mark done")
    rc = _run_emitter(repo)
    assert rc == 0
    sigs = load_md(repo / ".edpa/backlog/stories/S-1.md")["evidence"]
    trans = [s for s in sigs if s["type"] == "state_transition"]
    assert len(trans) == 1
    t = trans[0]
    assert t["from_status"] == "Implementing"
    assert t["to_status"] == "Done"
    assert t["weight"] == 0
    assert t["person"] == "alice"
    assert "S-1/Implementing->Done" in t["ref"]
    # commit_author still emitted alongside it
    assert any(s["type"] == "commit_author" for s in sigs)


def test_state_transition_excluded_from_cw() -> None:
    """Zero-weight state_transition must not alter contributors[] cw."""
    from detect_contributors import aggregate_signals
    sigs = [
        {"type": "state_transition", "login": "alice", "weight": 0.0,
         "ref": "commit/x/S-1/Implementing->Done", "detected_at": "x"},
        {"type": "commit_author", "login": "bob", "weight": 2.78,
         "ref": "commit/y", "detected_at": "x"},
    ]
    out = aggregate_signals(sigs, {})
    assert {c["person"] for c in out} == {"bob"}
    assert out[0]["cw"] == 1.0


def test_materialize_reconcile_is_idempotent(repo: Path) -> None:
    """cmd_materialize writes state_transition for the window; re-running
    is a no-op (dedup by ref, and its own chore(evidence): commit changes
    no status: field so it produces no new transition)."""
    (repo / ".edpa" / "iterations").mkdir(parents=True, exist_ok=True)
    (repo / ".edpa" / "iterations" / "PI-2026-2.1.yaml").write_text(
        yaml.safe_dump({"iteration": {
            "id": "PI-2026-2.1",
            "start_date": "2026-05-01", "end_date": "2026-05-31"}}))
    # Flip S-2 status without the hook (commit only).
    _commit_status_flip(repo, ".edpa/backlog/stories/S-2.md", "Done",
                        "S-2: done")

    edpa = repo / ".edpa"
    old = Path.cwd()
    try:
        os.chdir(repo)
        assert le.cmd_materialize(edpa, "PI-2026-2.1") == 0
        sigs = load_md(repo / ".edpa/backlog/stories/S-2.md")["evidence"]
        trans = [s for s in sigs if s["type"] == "state_transition"]
        assert any(s["to_status"] == "Done" for s in trans)
        n1 = len(sigs)
        # Re-run → idempotent.
        assert le.cmd_materialize(edpa, "PI-2026-2.1") == 0
        n2 = len(load_md(repo / ".edpa/backlog/stories/S-2.md")["evidence"])
    finally:
        os.chdir(old)
    assert n1 == n2


# ─── Phase 2: yaml_edit materialization ───────────────────────────────────


def test_emit_writes_yaml_edit_signal_with_delta(repo: Path) -> None:
    """A commit that edits a story's YAML emits a yaml_edit signal carrying
    a structural delta, attributed to the commit author."""
    p = repo / ".edpa/backlog/stories/S-1.md"
    data = load_md(p)
    data["js"] = 5
    data["bv"] = 3
    save_md_item(p, data)
    _git(["add", "."], cwd=repo)
    _git(["commit", "-q", "-m", "S-1: estimate"], cwd=repo, env_extra={
        "GIT_AUTHOR_DATE": "2026-05-26T10:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-05-26T10:00:00+00:00"})
    _run_emitter(repo)
    sigs = load_md(p)["evidence"]
    ye = [s for s in sigs if s["type"] == "yaml_edit"]
    assert len(ye) == 1
    assert ye[0]["person"] == "alice"
    assert ye[0]["weight"] > 0
    assert isinstance(ye[0]["delta"], dict)
    assert ye[0]["delta"]["scalars_changed"] >= 1
    assert ye[0]["ref"].startswith("commit/")


def test_materialize_all_iterations(repo: Path) -> None:
    """--all-iterations back-fills every iteration window in one shot."""
    iters = repo / ".edpa" / "iterations"
    iters.mkdir(parents=True, exist_ok=True)
    (iters / "PI-2026-2.1.yaml").write_text(yaml.safe_dump({"iteration": {
        "id": "PI-2026-2.1",
        "start_date": "2026-05-01", "end_date": "2026-05-31"}}))
    _commit_status_flip(repo, ".edpa/backlog/stories/S-1.md", "Done",
                        "S-1: done")
    old = Path.cwd()
    try:
        os.chdir(repo)
        rc = le.main(["--materialize", "--all-iterations"])
    finally:
        os.chdir(old)
    assert rc == 0
    sigs = load_md(repo / ".edpa/backlog/stories/S-1.md")["evidence"]
    assert any(s["type"] == "state_transition" and s["to_status"] == "Done"
               for s in sigs)


# ─── D-28: cross-iteration yaml_edit is recorded but zero-weighted ─────────


def _write_iter(repo: Path, iter_id: str, start: str, end: str) -> None:
    iters = repo / ".edpa" / "iterations"
    iters.mkdir(parents=True, exist_ok=True)
    (iters / f"{iter_id}.yaml").write_text(yaml.safe_dump({"iteration": {
        "id": iter_id, "start_date": start, "end_date": end}}))


def _commit_edit(repo: Path, rel: str, mutate: dict, msg: str, date: str,
                 email: str = "alice@example.dev",
                 name: str = "Alice Senior") -> str:
    """Apply a frontmatter mutation to an item and commit it at a fixed date."""
    p = repo / rel
    data = load_md(p)
    data.update(mutate)
    save_md_item(p, data)
    _git(["add", "."], cwd=repo)
    _git(["commit", "-q", "-m", msg], cwd=repo, env_extra={
        "GIT_AUTHOR_EMAIL": email, "GIT_AUTHOR_NAME": name,
        "GIT_COMMITTER_EMAIL": email, "GIT_COMMITTER_NAME": name,
        "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date})
    return _git(["rev-parse", "HEAD"], cwd=repo).stdout.strip()


def test_item_in_iteration_membership_rules() -> None:
    """D-28: the shared SAFe-hierarchy membership predicate (answers the
    per-type question: which items a materialize for iteration N may credit)."""
    from transitions import item_in_iteration as f
    for t in ("Story", "Defect", "Task"):          # exact match
        assert f(t, "PI-2026-3.1", "PI-2026-3.1") is True
        assert f(t, "PI-2026-1.1", "PI-2026-3.1") is False
    assert f("Feature", "PI-2026-3", "PI-2026-3.1") is True     # PI-prefix
    assert f("Feature", "PI-2026-3.1", "PI-2026-3.1") is True
    assert f("Feature", "PI-2026-1", "PI-2026-3.1") is False
    assert f("Epic", "PI-2026-1", "PI-2026-3.1") is True        # cross-PI
    assert f("Initiative", "whatever", "PI-2026-3.1") is True
    assert f("Story", "PI-2026-1.1", "") is True               # no filter


def test_materialize_zero_weights_cross_iteration_yaml_edit(repo: Path) -> None:
    """D-28: a commit inside iteration N's window that edits a story belonging
    to a DIFFERENT iteration records the yaml_edit signal but neutralises it to
    weight 0 (+ ``out_of_iteration`` tag), so it never scores in the foreign
    story's iteration. A genuine in-iteration story keeps full weight."""
    _write_iter(repo, "PI-2026-1.1", "2026-04-01", "2026-04-30")  # spring/closed
    _write_iter(repo, "PI-2026-3.1", "2026-06-15", "2026-06-30")  # current

    # S-1: a CLOSED spring story (belongs to 1.1). Set up in the spring window
    # so its setup commit is OUTSIDE the 3.1 window being materialized.
    _commit_edit(repo, ".edpa/backlog/stories/S-1.md",
                 {"iteration": "PI-2026-1.1", "status": "Done", "js": 5},
                 "S-1: spring work", "2026-04-10T10:00:00+00:00")
    # S-2: a genuine 3.1 story (belongs to 3.1).
    _commit_edit(repo, ".edpa/backlog/stories/S-2.md",
                 {"iteration": "PI-2026-3.1", "status": "Done", "js": 5},
                 "S-2: setup", "2026-06-16T09:00:00+00:00",
                 email="bob@example.dev", name="Bob Architect")

    # JUNE bulk-authoring commit (inside 3.1 window) edits BOTH stories.
    for rel in (".edpa/backlog/stories/S-1.md", ".edpa/backlog/stories/S-2.md"):
        d = load_md(repo / rel)
        d["bv"] = 8
        d["tc"] = 5
        save_md_item(repo / rel, d)
    _git(["add", "."], cwd=repo)
    _git(["commit", "-q", "-m", "add features and stories for E-1/E-2"],
         cwd=repo, env_extra={
             "GIT_AUTHOR_EMAIL": "bob@example.dev", "GIT_AUTHOR_NAME": "Bob Architect",
             "GIT_COMMITTER_EMAIL": "bob@example.dev", "GIT_COMMITTER_NAME": "Bob Architect",
             "GIT_AUTHOR_DATE": "2026-06-18T10:00:00+00:00",
             "GIT_COMMITTER_DATE": "2026-06-18T10:00:00+00:00"})

    edpa = repo / ".edpa"
    old = Path.cwd()
    try:
        os.chdir(repo)
        assert le.cmd_materialize(edpa, "PI-2026-3.1") == 0
    finally:
        os.chdir(old)

    # S-1 (foreign / spring): the June yaml_edit is recorded but neutralised.
    s1 = [s for s in load_md(repo / ".edpa/backlog/stories/S-1.md")["evidence"]
          if s["type"] == "yaml_edit"]
    assert s1, "the cross-iteration edit must still be recorded for audit"
    assert all(s["weight"] == 0 for s in s1)
    assert all("out_of_iteration" in s.get("tags", []) for s in s1)
    assert any(s.get("raw_weight") for s in s1)  # raw_weight retained → reversible

    # S-2 (genuine 3.1): full weight, never tagged out_of_iteration.
    s2 = [s for s in load_md(repo / ".edpa/backlog/stories/S-2.md")["evidence"]
          if s["type"] == "yaml_edit"]
    assert s2 and any(s["weight"] > 0 for s in s2)
    assert all("out_of_iteration" not in s.get("tags", []) for s in s2)


def test_materialize_keeps_yaml_edit_on_unassigned_item(repo: Path) -> None:
    """D-28 guard must NOT zero a yaml_edit on an item with no ``iteration:``
    — ~half of real stories/defects are unassigned; their in-window work is
    legitimate and must keep full weight. The guard neutralises only items that
    PROVABLY belong to a different iteration, not blank/unknown ones."""
    _write_iter(repo, "PI-2026-3.1", "2026-06-15", "2026-06-30")
    # S-1 keeps NO iteration field; a real edit lands inside the 3.1 window.
    _commit_edit(repo, ".edpa/backlog/stories/S-1.md",
                 {"status": "Done", "js": 5, "bv": 7},
                 "S-1: work", "2026-06-18T10:00:00+00:00",
                 email="bob@example.dev", name="Bob Architect")
    assert "iteration" not in load_md(repo / ".edpa/backlog/stories/S-1.md")

    edpa = repo / ".edpa"
    old = Path.cwd()
    try:
        os.chdir(repo)
        assert le.cmd_materialize(edpa, "PI-2026-3.1") == 0
    finally:
        os.chdir(old)

    ye = [s for s in load_md(repo / ".edpa/backlog/stories/S-1.md")["evidence"]
          if s["type"] == "yaml_edit"]
    assert ye and any(s["weight"] > 0 for s in ye), "unassigned work must not vanish"
    assert all("out_of_iteration" not in s.get("tags", []) for s in ye)


def test_post_commit_hook_zero_weights_cross_iteration_yaml_edit(repo: Path) -> None:
    """D-28: the LIVE post-commit hook (not just materialize) neutralises a
    yaml_edit on an item belonging to a different iteration than the commit's
    own (resolved by author date). A same-iteration item keeps full weight."""
    _write_iter(repo, "PI-2026-1.1", "2026-04-01", "2026-04-30")  # spring/closed
    _write_iter(repo, "PI-2026-3.1", "2026-06-15", "2026-06-30")  # current
    # S-1 ∈ spring 1.1; S-2 ∈ current 3.1.
    _commit_edit(repo, ".edpa/backlog/stories/S-1.md",
                 {"iteration": "PI-2026-1.1", "status": "Done", "js": 5},
                 "S-1: spring", "2026-04-10T10:00:00+00:00")
    _commit_edit(repo, ".edpa/backlog/stories/S-2.md",
                 {"iteration": "PI-2026-3.1", "status": "Done", "js": 5},
                 "S-2: setup", "2026-06-16T09:00:00+00:00")

    # ONE June commit (iteration 3.1 window) edits BOTH stories; run the HOOK.
    for rel in (".edpa/backlog/stories/S-1.md", ".edpa/backlog/stories/S-2.md"):
        d = load_md(repo / rel)
        d["bv"] = 8
        d["tc"] = 5
        save_md_item(repo / rel, d)
    _git(["add", "."], cwd=repo)
    _git(["commit", "-q", "-m", "groom S-1/S-2"], cwd=repo, env_extra={
        "GIT_AUTHOR_EMAIL": "bob@example.dev", "GIT_AUTHOR_NAME": "Bob Architect",
        "GIT_COMMITTER_EMAIL": "bob@example.dev", "GIT_COMMITTER_NAME": "Bob Architect",
        "GIT_AUTHOR_DATE": "2026-06-18T10:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-06-18T10:00:00+00:00"})
    assert _run_emitter(repo) == 0

    # S-1 (spring, foreign to the June commit): yaml_edit recorded but neutralised.
    s1 = [s for s in load_md(repo / ".edpa/backlog/stories/S-1.md")["evidence"]
          if s["type"] == "yaml_edit"]
    assert s1 and all(s["weight"] == 0 for s in s1)
    assert all("out_of_iteration" in s.get("tags", []) for s in s1)
    # S-2 (genuine 3.1): full weight, never tagged.
    s2 = [s for s in load_md(repo / ".edpa/backlog/stories/S-2.md")["evidence"]
          if s["type"] == "yaml_edit"]
    assert s2 and any(s["weight"] > 0 for s in s2)
    assert all("out_of_iteration" not in s.get("tags", []) for s in s2)


def test_post_commit_hook_zero_weights_cross_iteration_commit_author(repo: Path) -> None:
    """D-29: the live hook neutralises the full-weight ``commit_author`` signal
    (not just ``yaml_edit``) on an item belonging to a different iteration than
    the commit's own — overflow is gated to weight 0 (audit-only), while a
    same-iteration item keeps full weight. raw_weight is carried for audit."""
    _write_iter(repo, "PI-2026-1.1", "2026-04-01", "2026-04-30")  # spring/closed
    _write_iter(repo, "PI-2026-3.1", "2026-06-15", "2026-06-30")  # current
    _commit_edit(repo, ".edpa/backlog/stories/S-1.md",
                 {"iteration": "PI-2026-1.1", "status": "Done", "js": 5},
                 "S-1: spring", "2026-04-10T10:00:00+00:00")
    _commit_edit(repo, ".edpa/backlog/stories/S-2.md",
                 {"iteration": "PI-2026-3.1", "status": "Done", "js": 5},
                 "S-2: setup", "2026-06-16T09:00:00+00:00")

    # ONE June commit (iteration 3.1 window) touches BOTH stories; run the HOOK.
    for rel in (".edpa/backlog/stories/S-1.md", ".edpa/backlog/stories/S-2.md"):
        d = load_md(repo / rel)
        d["bv"] = 8
        save_md_item(repo / rel, d)
    _git(["add", "."], cwd=repo)
    _git(["commit", "-q", "-m", "groom S-1/S-2"], cwd=repo, env_extra={
        "GIT_AUTHOR_EMAIL": "bob@example.dev", "GIT_AUTHOR_NAME": "Bob Architect",
        "GIT_COMMITTER_EMAIL": "bob@example.dev", "GIT_COMMITTER_NAME": "Bob Architect",
        "GIT_AUTHOR_DATE": "2026-06-18T10:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-06-18T10:00:00+00:00"})
    assert _run_emitter(repo) == 0

    # S-1 (spring, foreign to the June commit): commit_author recorded, neutralised.
    s1 = [s for s in load_md(repo / ".edpa/backlog/stories/S-1.md")["evidence"]
          if s["type"] == "commit_author"]
    assert s1, "the cross-iteration commit_author must still be recorded for audit"
    assert all(s["weight"] == 0 for s in s1)
    assert all("out_of_iteration" in s.get("tags", []) for s in s1)
    assert all(s.get("raw_weight") for s in s1)  # original retained → reversible
    # S-2 (genuine 3.1): full weight, never tagged, raw_weight present.
    s2 = [s for s in load_md(repo / ".edpa/backlog/stories/S-2.md")["evidence"]
          if s["type"] == "commit_author"]
    assert s2 and all(s["weight"] > 0 for s in s2)
    assert all("out_of_iteration" not in s.get("tags", []) for s in s2)
    assert all(s.get("raw_weight") for s in s2)


def test_post_commit_hook_keeps_commit_author_on_unassigned_item(repo: Path) -> None:
    """D-29: the gate must NOT zero a ``commit_author`` on an item with no
    ``iteration:`` — overflow can't be proven without a window, so unassigned
    work keeps full weight (mirrors the D-28 yaml_edit rule for blank items)."""
    _write_iter(repo, "PI-2026-3.1", "2026-06-15", "2026-06-30")
    _commit_edit(repo, ".edpa/backlog/stories/S-1.md",
                 {"status": "Done", "js": 5}, "S-1: setup",
                 "2026-06-16T09:00:00+00:00")
    assert "iteration" not in load_md(repo / ".edpa/backlog/stories/S-1.md")

    d = load_md(repo / ".edpa/backlog/stories/S-1.md")
    d["bv"] = 7
    save_md_item(repo / ".edpa/backlog/stories/S-1.md", d)
    _git(["add", "."], cwd=repo)
    _git(["commit", "-q", "-m", "work on S-1"], cwd=repo, env_extra={
        "GIT_AUTHOR_EMAIL": "bob@example.dev", "GIT_AUTHOR_NAME": "Bob Architect",
        "GIT_COMMITTER_EMAIL": "bob@example.dev", "GIT_COMMITTER_NAME": "Bob Architect",
        "GIT_AUTHOR_DATE": "2026-06-18T10:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-06-18T10:00:00+00:00"})
    assert _run_emitter(repo) == 0

    ca = [s for s in load_md(repo / ".edpa/backlog/stories/S-1.md")["evidence"]
          if s["type"] == "commit_author"]
    assert ca and all(s["weight"] > 0 for s in ca), "unassigned work must not vanish"
    assert all("out_of_iteration" not in s.get("tags", []) for s in ca)


def test_neutralize_foreign_signals_gates_all_weighted_types() -> None:
    """D-29: the guard zeroes EVERY weighted GATED_TYPES signal on a
    foreign-iteration item (commit_author, manual:commit_message,
    agent_contribution, yaml_edit) — preserving raw_weight — while a
    zero-weight state_transition is left untouched."""
    item = {"type": "Story", "iteration": "PI-2026-1.1"}
    sigs = [
        {"type": "commit_author", "weight": 2.78},
        {"type": "manual:commit_message", "weight": 5.0},
        {"type": "agent_contribution", "weight": 1.0},
        {"type": "yaml_edit", "weight": 7.0, "raw_weight": 7.0},
        {"type": "state_transition", "weight": 0},
    ]
    # commit's iteration (3.1) differs from the item's (1.1) → out of window.
    le._neutralize_foreign_signals(item, sigs, Path("x/stories/S-1.md"),
                                   "PI-2026-3.1")
    by_type = {s["type"]: s for s in sigs}
    for t in ("commit_author", "manual:commit_message",
              "agent_contribution", "yaml_edit"):
        assert by_type[t]["weight"] == 0, t
        assert "out_of_iteration" in by_type[t]["tags"], t
        assert by_type[t]["raw_weight"] > 0, t  # original retained for audit
    assert by_type["state_transition"]["weight"] == 0
    assert "out_of_iteration" not in by_type["state_transition"].get("tags", [])


def test_post_commit_hook_keeps_commit_author_outside_all_windows(repo: Path) -> None:
    """D-29 / decision #2: a commit whose author date falls in NO iteration
    window (under a contiguous calendar the only real gap is the edge of the
    project timeline) resolves commit_iter=None, so the gate no-ops and the
    commit_author keeps full weight — a lenient fallback, never a router."""
    _write_iter(repo, "PI-2026-3.1", "2026-06-15", "2026-06-30")
    _commit_edit(repo, ".edpa/backlog/stories/S-1.md",
                 {"iteration": "PI-2026-3.1", "status": "Done", "js": 5},
                 "S-1: setup", "2026-06-16T09:00:00+00:00")
    # A late edit committed in DECEMBER — after every defined iteration → no window.
    d = load_md(repo / ".edpa/backlog/stories/S-1.md")
    d["bv"] = 9
    save_md_item(repo / ".edpa/backlog/stories/S-1.md", d)
    _git(["add", "."], cwd=repo)
    _git(["commit", "-q", "-m", "late tweak on S-1"], cwd=repo, env_extra={
        "GIT_AUTHOR_DATE": "2026-12-01T10:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-12-01T10:00:00+00:00"})
    assert _run_emitter(repo) == 0
    ca = [s for s in load_md(repo / ".edpa/backlog/stories/S-1.md")["evidence"]
          if s["type"] == "commit_author"]
    assert ca and all(s["weight"] > 0 for s in ca), "no-window commit keeps full weight"
    assert all("out_of_iteration" not in s.get("tags", []) for s in ca)
