"""Tests for plugin/edpa/scripts/_people_loader.py.

Covers:
  - load_people / by_id index
  - display_handle (@login fallback to id)
  - avatar_url (None when no github)
  - validate_people diagnostic codes:
      person_missing      (error)
      person_no_github    (warning)
      person_unused       (warning)

Run: python -m pytest tests/test_people_loader.py -v
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

from _people_loader import (  # noqa: E402
    avatar_url,
    display_handle,
    load_people,
    split_diagnostics,
    validate_people,
)


def write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def make_people_yaml(*entries) -> dict:
    return {"people": list(entries)}


def make_iteration(stories_detail=None) -> dict:
    return {
        "iteration": {"id": "PI-2026-1.1", "pi": "PI-2026-1",
                      "start_date": "2026-04-06", "end_date": "2026-04-10",
                      "weeks": 1, "status": "closed"},
        "stories_detail": stories_detail or [],
    }


# --- pure helpers ----------------------------------------------------------

def test_display_handle_prefers_github():
    assert display_handle({"id": "alice", "github": "alice-on-gh"}) == "@alice-on-gh"


def test_display_handle_falls_back_to_id():
    assert display_handle({"id": "alice"}) == "alice"


def test_display_handle_blank_github_falls_back():
    assert display_handle({"id": "alice", "github": ""}) == "alice"


def test_avatar_url_with_github():
    url = avatar_url({"id": "alice", "github": "alice-on-gh"})
    assert url == "https://github.com/alice-on-gh.png?size=40"


def test_avatar_url_without_github_returns_none():
    assert avatar_url({"id": "alice"}) is None


def test_avatar_url_custom_size():
    assert avatar_url({"id": "alice", "github": "a"}, size=120).endswith("size=120")


# --- load_people -----------------------------------------------------------

def test_load_people_missing_returns_empty(tmp_path):
    people, by_id = load_people(tmp_path)
    assert people == []
    assert by_id == {}


def test_load_people_indexes_by_id(tmp_path):
    write_yaml(tmp_path / "config" / "people.yaml",
               make_people_yaml({"id": "alice", "name": "Alice"},
                                {"id": "bob", "name": "Bob"}))
    people, by_id = load_people(tmp_path)
    assert len(people) == 2
    assert by_id["alice"]["name"] == "Alice"


def test_load_people_skips_entries_without_id(tmp_path):
    write_yaml(tmp_path / "config" / "people.yaml",
               make_people_yaml({"name": "Anonymous"},
                                {"id": "alice"}))
    _, by_id = load_people(tmp_path)
    assert list(by_id) == ["alice"]


# --- validate_people -------------------------------------------------------

def test_validate_clean_registry_no_diags(tmp_path):
    write_yaml(tmp_path / "config" / "people.yaml",
               make_people_yaml({"id": "alice", "github": "a"}))
    write_yaml(tmp_path / "iterations" / "PI-2026-1.1.yaml",
               make_iteration([{"id": "S-1", "assignee": "alice"}]))
    diags = validate_people(tmp_path)
    assert diags == []


def test_validate_unknown_assignee_emits_error(tmp_path):
    write_yaml(tmp_path / "config" / "people.yaml",
               make_people_yaml({"id": "alice", "github": "a"}))
    write_yaml(tmp_path / "iterations" / "PI-2026-1.1.yaml",
               make_iteration([{"id": "S-1", "assignee": "ghost"}]))
    diags = validate_people(tmp_path)
    errors, _ = split_diagnostics(diags)
    assert any(d["code"] == "person_missing" and d["person"] == "ghost"
               for d in errors)


def test_validate_assignee_without_github_emits_warning(tmp_path):
    write_yaml(tmp_path / "config" / "people.yaml",
               make_people_yaml({"id": "alice"}))   # no github
    write_yaml(tmp_path / "iterations" / "PI-2026-1.1.yaml",
               make_iteration([{"id": "S-1", "assignee": "alice"}]))
    diags = validate_people(tmp_path)
    _, warnings = split_diagnostics(diags)
    assert any(d["code"] == "person_no_github" and d["person"] == "alice"
               for d in warnings)


def test_validate_unused_person_emits_warning(tmp_path):
    write_yaml(tmp_path / "config" / "people.yaml",
               make_people_yaml({"id": "alice", "github": "a"},
                                {"id": "bob", "github": "b"}))
    write_yaml(tmp_path / "iterations" / "PI-2026-1.1.yaml",
               make_iteration([{"id": "S-1", "assignee": "alice"}]))
    diags = validate_people(tmp_path)
    _, warnings = split_diagnostics(diags)
    assert any(d["code"] == "person_unused" and d["person"] == "bob"
               for d in warnings)


def test_validate_assignee_in_backlog_counts(tmp_path):
    """Assignees that appear only in backlog/ (not iteration) still count."""
    write_yaml(tmp_path / "config" / "people.yaml",
               make_people_yaml({"id": "alice"}))   # no github
    write_yaml(tmp_path / "backlog" / "stories" / "S-1.yaml",
               {"id": "S-1", "type": "Story", "assignee": "alice"})
    diags = validate_people(tmp_path)
    _, warnings = split_diagnostics(diags)
    assert any(d["code"] == "person_no_github" for d in warnings)


def test_validate_handles_no_iterations_no_backlog(tmp_path):
    """Empty workspace — only person_unused warnings, no errors."""
    write_yaml(tmp_path / "config" / "people.yaml",
               make_people_yaml({"id": "alice"}))
    diags = validate_people(tmp_path)
    errors, warnings = split_diagnostics(diags)
    assert errors == []
    assert any(d["code"] == "person_unused" for d in warnings)
