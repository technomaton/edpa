"""Tests for plugin/edpa/scripts/sync_collaborators.py.

Pure-function coverage: diff, make_stub, _propose_id, apply_removes,
apply_adds (with mocked gh fetch). The CLI / gh-network paths are
deliberately not covered here — they're exercised by the workflow
integration test in CI.

Run: python -m pytest tests/test_sync_collaborators.py -v
"""
import json
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import sync_collaborators as sc  # noqa: E402


# --- _propose_id -----------------------------------------------------------

def test_propose_id_lowercases():
    assert sc._propose_id("Alice-GH", set()) == "alice-gh"


def test_propose_id_handles_underscore():
    assert sc._propose_id("octo_cat", set()) == "octo-cat"


def test_propose_id_collision_appends_suffix():
    assert sc._propose_id("alice", {"alice"}) == "alice-2"
    assert sc._propose_id("alice", {"alice", "alice-2"}) == "alice-3"


# --- diff ------------------------------------------------------------------

def test_diff_classifies_three_buckets():
    people = [
        {"id": "alice", "github": "alice-gh", "availability": "confirmed"},
        {"id": "bob", "github": "bob-gh", "availability": "confirmed"},
    ]
    collabs = [
        {"login": "alice-gh"},
        {"login": "eve-gh"},
    ]
    d = sc.diff(people, collabs)
    assert [a["login"] for a in d["adds"]] == ["eve-gh"]
    assert [r["login"] for r in d["removes"]] == ["bob-gh"]
    assert [u["login"] for u in d["unchanged"]] == ["alice-gh"]


def test_diff_skips_people_without_github():
    people = [{"id": "cara", "availability": "confirmed"}]
    collabs = [{"login": "eve-gh"}]
    d = sc.diff(people, collabs)
    # cara stays in people.yaml but is invisible to the diff (nothing to
    # compare against). eve-gh shows up as an add.
    assert [a["login"] for a in d["adds"]] == ["eve-gh"]
    assert d["removes"] == []


def test_diff_already_unavailable_not_re_flagged():
    people = [
        {"id": "bob", "github": "bob-gh", "availability": "unavailable"},
    ]
    collabs = []   # bob-gh removed
    d = sc.diff(people, collabs)
    assert d["removes"] == []   # already flagged — don't double-process


def test_diff_case_insensitive_login_match():
    people = [{"id": "alice", "github": "Alice-GH"}]
    collabs = [{"login": "alice-gh"}]
    d = sc.diff(people, collabs)
    assert [u["login"] for u in d["unchanged"]] == ["Alice-GH"]


# --- make_stub -------------------------------------------------------------

def test_make_stub_uses_profile_name():
    stub = sc.make_stub("alice-gh",
                        {"name": "Alice Architect", "email": "a@x.com"},
                        set())
    assert stub["id"] == "alice-gh"
    assert stub["name"] == "Alice Architect"
    assert stub["email"] == "a@x.com"
    assert stub["github"] == "alice-gh"
    # Maintainer-fillable fields stay blank
    assert stub["role"] == ""
    assert stub["team"] == ""
    assert stub["fte"] == 0.0
    assert stub["capacity_per_iteration"] == 0


def test_make_stub_falls_back_to_login_when_profile_blank():
    stub = sc.make_stub("alice-gh", {}, set())
    assert stub["name"] == "alice-gh"
    assert stub["email"] == ""


def test_make_stub_avoids_id_collision():
    stub = sc.make_stub("alice-gh", {"name": "Alice"}, {"alice-gh"})
    assert stub["id"] == "alice-gh-2"


# --- apply_removes ---------------------------------------------------------

def test_apply_removes_flips_availability():
    person = {"id": "bob", "github": "bob-gh", "availability": "confirmed"}
    n = sc.apply_removes([person], [{"login": "bob-gh", "person": person}])
    assert n == 1
    assert person["availability"] == "unavailable"
    assert person["availability_changed"] == date.today().isoformat()


def test_apply_removes_no_diffs_no_mutations():
    person = {"id": "alice", "github": "alice-gh", "availability": "confirmed"}
    n = sc.apply_removes([person], [])
    assert n == 0
    assert person["availability"] == "confirmed"


# --- apply_adds (with mocked profile fetch) --------------------------------

def test_apply_adds_uses_fetched_profile(monkeypatch):
    profiles = {
        "eve-gh": {"name": "Eve Example", "email": "eve@example.com"},
    }
    monkeypatch.setattr(sc, "fetch_user_profile",
                        lambda login: profiles.get(login, {}))

    people: list[dict] = []
    n = sc.apply_adds(people, [{"login": "eve-gh", "collaborator": {"login": "eve-gh"}}])
    assert n == 1
    assert people[0]["name"] == "Eve Example"
    assert people[0]["email"] == "eve@example.com"
    assert people[0]["github"] == "eve-gh"


def test_apply_adds_handles_blank_profile(monkeypatch):
    """gh api can return empty when the user has no public profile."""
    monkeypatch.setattr(sc, "fetch_user_profile", lambda login: {})

    people: list[dict] = []
    sc.apply_adds(people, [{"login": "eve-gh", "collaborator": {"login": "eve-gh"}}])
    assert people[0]["name"] == "eve-gh"
    assert people[0]["email"] == ""


# --- write_people_yaml round-trip ------------------------------------------

def test_write_people_yaml_preserves_keys(tmp_path):
    p = tmp_path / "people.yaml"
    doc = {
        "cadence": {"iteration_weeks": 1},
        "teams": [{"id": "Core"}],
        "people": [{"id": "alice", "name": "A"}],
    }
    sc.write_people_yaml(p, doc)
    reloaded = yaml.safe_load(p.read_text())
    assert reloaded == doc


# --- find_edpa_root --------------------------------------------------------

def test_find_edpa_root_handles_dot_edpa_directly(tmp_path):
    edpa = tmp_path / ".edpa"
    edpa.mkdir()
    assert sc.find_edpa_root(edpa) == edpa


def test_find_edpa_root_walks_up(tmp_path):
    edpa = tmp_path / ".edpa"
    edpa.mkdir()
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    assert sc.find_edpa_root(deep) == edpa


def test_find_edpa_root_returns_none_when_missing(tmp_path):
    # Ensure no .edpa anywhere up the hierarchy from tmp_path
    assert sc.find_edpa_root(tmp_path) is None


# --- resolve_repo_from_config ----------------------------------------------

def test_resolve_repo_reads_sync_section(tmp_path):
    edpa = tmp_path / ".edpa"
    (edpa / "config").mkdir(parents=True)
    (edpa / "config" / "edpa.yaml").write_text(
        "sync:\n"
        "  github_org: my-org\n"
        "  github_repo: my-repo\n"
    )
    assert sc.resolve_repo_from_config(edpa) == "my-org/my-repo"


def test_resolve_repo_returns_none_when_missing(tmp_path):
    edpa = tmp_path / ".edpa"
    (edpa / "config").mkdir(parents=True)
    (edpa / "config" / "edpa.yaml").write_text("sync: {}\n")
    assert sc.resolve_repo_from_config(edpa) is None
