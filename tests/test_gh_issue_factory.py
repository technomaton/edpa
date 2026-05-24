"""Tests for plugin/edpa/scripts/_gh_issue_factory.py.

The factory drives the six-step GH issue pipeline shared by
backlog.py / sync.py / project_setup.py. Real subprocess is mocked
out — the unit suite never hits github.com. Coverage focuses on:

* the two creation modes (known-id 1-phase / new-id 2-phase),
* warnings vs. exceptions (soft vs. hard failures),
* conditional pipeline steps (project add / type assign / sub-issue link).

Run: python -m pytest tests/test_gh_issue_factory.py -v
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import _gh_issue_factory as fac  # noqa: E402


# --- _gh stub --------------------------------------------------------------

class _Result:
    """Minimal stand-in for subprocess.CompletedProcess."""
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def make_gh_stub(routes: dict):
    """Build a `_gh` replacement that dispatches by command verb.

    ``routes`` maps a verb key (e.g. ``"create"``, ``"edit"``,
    ``"item-add"``, ``"graphql"``) to a ``_Result`` or to a callable
    that takes the argv and returns one. The default ``_resolve_node_id``
    flow uses two different graphql calls (resolve + assign), so callers
    that need both can pass a list — the stub pops in order.
    """
    counters = {k: 0 for k in routes}

    def stub(args, **_):
        for key in ("create", "edit", "item-add", "graphql"):
            if key in args:
                handler = routes.get(key)
                if handler is None:
                    return _Result(returncode=1,
                                   stderr=f"unexpected gh {key}")
                if isinstance(handler, list):
                    idx = counters[key]
                    counters[key] += 1
                    item = handler[idx] if idx < len(handler) else handler[-1]
                else:
                    item = handler
                if callable(item):
                    return item(args)
                return item
        raise AssertionError(f"unhandled gh argv: {args!r}")

    return stub


# --- edpa_id_for -----------------------------------------------------------

@pytest.mark.parametrize("item_type,num,expected", [
    ("Initiative", 1, "I-1"),
    ("Epic", 12, "E-12"),
    ("Feature", 3, "F-3"),
    ("Story", 42, "S-42"),
    ("Defect", 99, "D-99"),
    ("Event", 7, "EV-7"),
])
def test_edpa_id_for_known_types(item_type, num, expected):
    assert fac.edpa_id_for(item_type, num) == expected


def test_edpa_id_for_unknown_type_falls_back_to_first_letter():
    # Defensive fallback for type names not in TYPE_PREFIX (e.g. legacy
    # "Task"). The factory will still produce *something* so the caller
    # gets a usable id rather than a KeyError mid-flow.
    assert fac.edpa_id_for("Task", 5) == "T-5"


# --- helpers shared by the create tests ------------------------------------

def _graphql_resolve_node(node_id="NODE_ABC"):
    return _Result(
        stdout=json.dumps({"data": {"repository": {"issue": {"id": node_id}}}}),
    )


def _graphql_assign_type_ok():
    return _Result(
        stdout=json.dumps({"data": {"updateIssueIssueType": {"issue": {"id": "X"}}}}),
    )


def _graphql_assign_type_fail():
    # Mimics gh exit 0 but GraphQL-level errors block.
    return _Result(
        stdout=json.dumps({"errors": [{"message": "no permission"}]}),
    )


def _project_add_ok(project_item_id="PVTI_42"):
    return _Result(stdout=json.dumps({"id": project_item_id}))


def _create_ok(url="https://github.com/o/r/issues/42"):
    return _Result(stdout=url)


# --- create_gh_issue: known-id mode (sync.py / project_setup.py path) ------

def test_known_id_uses_single_create_with_full_title(monkeypatch):
    """When edpa_id is given, the factory must produce ONE `gh issue create`
    call carrying the canonical "{ID}: {title}" — no follow-up edit."""
    captured = []

    def create_capture(args):
        captured.append(list(args))
        return _create_ok()

    monkeypatch.setattr(fac, "_gh", make_gh_stub({
        "create": create_capture,
        "graphql": _graphql_resolve_node(),
    }))

    result = fac.create_gh_issue(
        "owner", "repo",
        item_type="Story",
        raw_title="Implement login",
        body="body",
        edpa_id="S-42",
    )

    assert result["issue_number"] == 42
    assert result["edpa_id"] == "S-42"
    # Title argument follows --title in the argv
    title_idx = captured[0].index("--title") + 1
    assert captured[0][title_idx] == "S-42: Implement login"
    # Exactly one `create` and one `graphql` call (resolve). No `edit`.
    assert sum(1 for c in captured if "create" in c) == 1


def test_known_id_skips_title_edit(monkeypatch):
    """Regression guard: known-id MUST NOT trigger `gh issue edit --title`."""
    calls = {"edit": 0}

    def edit_seen(args):
        calls["edit"] += 1
        return _Result()

    monkeypatch.setattr(fac, "_gh", make_gh_stub({
        "create": _create_ok(),
        "edit": edit_seen,
        "graphql": _graphql_resolve_node(),
    }))

    fac.create_gh_issue(
        "o", "r",
        item_type="Story", raw_title="t", body="b",
        edpa_id="S-1",
    )
    assert calls["edit"] == 0


# --- create_gh_issue: new-id mode (backlog.py add path) --------------------

def test_new_id_does_create_then_edit_with_derived_id(monkeypatch):
    """No edpa_id → create with raw title, then edit to "{prefix}-{num}: ..."."""
    captured = {"create": None, "edit": None}

    def create_capture(args):
        captured["create"] = list(args)
        return _create_ok("https://github.com/o/r/issues/7")

    def edit_capture(args):
        captured["edit"] = list(args)
        return _Result()

    monkeypatch.setattr(fac, "_gh", make_gh_stub({
        "create": create_capture,
        "edit": edit_capture,
        "graphql": _graphql_resolve_node(),
    }))

    result = fac.create_gh_issue(
        "o", "r",
        item_type="Event", raw_title="Demo day", body="b",
    )

    # create got the RAW title (no prefix yet)
    ci = captured["create"].index("--title") + 1
    assert captured["create"][ci] == "Demo day"
    # edit rewrote it to EV-7: Demo day (Event prefix is multi-char)
    ei = captured["edit"].index("--title") + 1
    assert captured["edit"][ei] == "EV-7: Demo day"
    assert result["edpa_id"] == "EV-7"


def test_new_id_title_edit_failure_raises(monkeypatch):
    """If the title rewrite fails, the factory must raise — a created
    issue without the ID prefix is exactly the bug we're fixing."""
    monkeypatch.setattr(fac, "_gh", make_gh_stub({
        "create": _create_ok(),
        "edit": _Result(returncode=1, stderr="forbidden"),
        "graphql": _graphql_resolve_node(),
    }))

    with pytest.raises(RuntimeError, match="title rewrite failed"):
        fac.create_gh_issue(
            "o", "r",
            item_type="Story", raw_title="t", body="b",
        )


# --- hard failures ---------------------------------------------------------

def test_create_failure_raises(monkeypatch):
    monkeypatch.setattr(fac, "_gh", make_gh_stub({
        "create": _Result(returncode=1, stderr="repo not found"),
    }))
    with pytest.raises(RuntimeError, match="repo not found"):
        fac.create_gh_issue(
            "o", "r",
            item_type="Story", raw_title="t", body="b", edpa_id="S-1",
        )


def test_create_subprocess_oserror_raises(monkeypatch):
    def boom(args, **_):
        raise FileNotFoundError("gh missing")
    monkeypatch.setattr(fac, "_gh", boom)
    with pytest.raises(RuntimeError, match="gh missing"):
        fac.create_gh_issue(
            "o", "r",
            item_type="Story", raw_title="t", body="b", edpa_id="S-1",
        )


def test_unparseable_url_raises(monkeypatch):
    """gh exit 0 but stdout is junk — defensive parse guard."""
    monkeypatch.setattr(fac, "_gh", make_gh_stub({
        "create": _Result(stdout="not-a-url"),
    }))
    with pytest.raises(RuntimeError, match="parse issue number"):
        fac.create_gh_issue(
            "o", "r",
            item_type="Story", raw_title="t", body="b", edpa_id="S-1",
        )


# --- soft failures populate warnings, never raise --------------------------

def test_node_id_lookup_failure_warns_but_returns(monkeypatch):
    """node_id resolution is best-effort; without it sub-issue link and
    Issue Type assign get skipped but the issue still exists in GH."""
    monkeypatch.setattr(fac, "_gh", make_gh_stub({
        "create": _create_ok(),
        "graphql": _Result(returncode=1, stderr="rate limited"),
    }))
    result = fac.create_gh_issue(
        "o", "r",
        item_type="Story", raw_title="t", body="b", edpa_id="S-1",
    )
    assert result["node_id"] == ""
    assert any("node_id" in w for w in result["warnings"])


def test_issue_type_assign_failure_warns(monkeypatch):
    """When type_ids has the level but GraphQL refuses, we warn but
    don't fail — caller has already created a usable issue."""
    monkeypatch.setattr(fac, "_gh", make_gh_stub({
        "create": _create_ok(),
        # First graphql = node resolve (ok); second = assign type (fail).
        "graphql": [_graphql_resolve_node(), _graphql_assign_type_fail()],
    }))
    result = fac.create_gh_issue(
        "o", "r",
        item_type="Story", raw_title="t", body="b", edpa_id="S-1",
        type_ids={"Story": "TYPE_ABC"},
    )
    assert any("Issue Type" in w for w in result["warnings"])


def test_no_type_id_for_level_skips_assign_silently(monkeypatch):
    """If org doesn't expose this type, the factory must NOT warn — the
    feature is optional and falsely warning would spam every add call."""
    calls = {"graphql": 0}

    def gql(args):
        calls["graphql"] += 1
        return _graphql_resolve_node()

    monkeypatch.setattr(fac, "_gh", make_gh_stub({
        "create": _create_ok(),
        "graphql": gql,
    }))
    result = fac.create_gh_issue(
        "o", "r",
        item_type="Story", raw_title="t", body="b", edpa_id="S-1",
        type_ids={"Initiative": "T_INIT"},  # no "Story" key
    )
    assert result["warnings"] == []
    # Only the node-resolve graphql call was made
    assert calls["graphql"] == 1


def test_project_add_failure_warns(monkeypatch):
    monkeypatch.setattr(fac, "_gh", make_gh_stub({
        "create": _create_ok(),
        "graphql": _graphql_resolve_node(),
        "item-add": _Result(returncode=1, stderr="project not found"),
    }))
    result = fac.create_gh_issue(
        "o", "r",
        item_type="Story", raw_title="t", body="b", edpa_id="S-1",
        project_num=5,
    )
    assert result["project_item_id"] == ""
    assert any("project" in w for w in result["warnings"])


def test_sub_issue_link_failure_warns(monkeypatch):
    monkeypatch.setattr(fac, "_gh", make_gh_stub({
        "create": _create_ok(),
        "graphql": _graphql_resolve_node(),
    }))
    monkeypatch.setattr(fac, "_link_sub_issue",
                        lambda p, c: (False, "permission denied"))
    result = fac.create_gh_issue(
        "o", "r",
        item_type="Story", raw_title="t", body="b", edpa_id="S-1",
        parent_node_id="NODE_PARENT",
    )
    assert any("sub-issue" in w for w in result["warnings"])


# --- conditional pipeline ---------------------------------------------------

def test_no_parent_node_id_skips_link(monkeypatch):
    """When the caller doesn't supply a parent_node_id (e.g. orphan
    Initiative, or sync.py push deferring linking to a second pass),
    `_link_sub_issue` must not be invoked at all."""
    called = []
    monkeypatch.setattr(fac, "_link_sub_issue",
                        lambda p, c: called.append((p, c)) or (True, "x"))
    monkeypatch.setattr(fac, "_gh", make_gh_stub({
        "create": _create_ok(),
        "graphql": _graphql_resolve_node(),
    }))
    fac.create_gh_issue(
        "o", "r",
        item_type="Initiative", raw_title="root", body="b", edpa_id="I-1",
    )
    assert called == []


def test_no_project_num_skips_project_add(monkeypatch):
    """When project_num is None (caller intentionally skipping project
    membership) the factory must not call `gh project item-add`."""
    monkeypatch.setattr(fac, "_gh", make_gh_stub({
        "create": _create_ok(),
        "graphql": _graphql_resolve_node(),
    }))
    result = fac.create_gh_issue(
        "o", "r",
        item_type="Story", raw_title="t", body="b", edpa_id="S-1",
    )
    assert result["project_item_id"] == ""


def test_assignee_and_labels_passed_to_create(monkeypatch):
    captured = {}

    def create_capture(args):
        captured["args"] = list(args)
        return _create_ok()

    monkeypatch.setattr(fac, "_gh", make_gh_stub({
        "create": create_capture,
        "graphql": _graphql_resolve_node(),
    }))

    fac.create_gh_issue(
        "o", "r",
        item_type="Story", raw_title="t", body="b", edpa_id="S-1",
        assignee_login="octocat",
        extra_labels=["Enabler", "blocked"],
    )
    args = captured["args"]
    assert "--assignee" in args and args[args.index("--assignee") + 1] == "octocat"
    # Each label adds its own --label argument
    label_args = [args[i + 1] for i, a in enumerate(args) if a == "--label"]
    assert label_args == ["Enabler", "blocked"]


def test_happy_path_returns_full_dict(monkeypatch):
    """End-to-end success: returned dict has every documented field
    populated to non-empty values and no warnings."""
    monkeypatch.setattr(fac, "_gh", make_gh_stub({
        "create": _create_ok("https://github.com/o/r/issues/100"),
        "graphql": [_graphql_resolve_node("NODE_100"),
                    _graphql_assign_type_ok()],
        "item-add": _project_add_ok("PVTI_100"),
    }))
    monkeypatch.setattr(fac, "_link_sub_issue", lambda p, c: (True, "linked"))

    result = fac.create_gh_issue(
        "o", "r",
        item_type="Story", raw_title="hello", body="b", edpa_id="S-100",
        project_num=3,
        type_ids={"Story": "TYPE_STORY"},
        parent_node_id="NODE_PARENT",
    )
    assert result == {
        "issue_number": 100,
        "node_id": "NODE_100",
        "project_item_id": "PVTI_100",
        "url": "https://github.com/o/r/issues/100",
        "edpa_id": "S-100",
        "warnings": [],
    }
