"""Tests for GitHub issue timestamp extraction, diff detection, and read-only guard.

Covers:
  - map_gh_items_to_edpa extracts created_at / closed_at / updated_at from content
  - Missing timestamps are gracefully skipped
  - compute_diff detects timestamp field changes
  - READONLY_FIELDS prevents pushing timestamps back to GitHub
  - validate_syntax accepts timestamp fields in all item types
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "plugin" / "edpa" / "scripts"))

import json  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from sync import (  # noqa: E402
    DEFAULT_SYNC_CONFIG,
    READONLY_FIELDS,
    compute_diff,
    gh_fetch_project_items,
    gh_set_field_value,
    map_gh_items_to_edpa,
)
import sync  # noqa: E402
from validate_syntax import ITEM_SCHEMA  # noqa: E402

FIELDS = DEFAULT_SYNC_CONFIG["fields_mapping"]


def _gh_item(issue_num: int, title: str, level: str = "Story",
             created_at: str | None = "2025-01-10T08:00:00Z",
             updated_at: str | None = "2025-06-15T12:00:00Z",
             closed_at: str | None = None):
    """Build a GH project item fixture with optional timestamps in content."""
    content: dict = {
        "number": issue_num,
        "title": title,
        "type": "Issue",
        "url": f"https://github.com/x/y/issues/{issue_num}",
    }
    if created_at is not None:
        content["createdAt"] = created_at
    if updated_at is not None:
        content["updatedAt"] = updated_at
    if closed_at is not None:
        content["closedAt"] = closed_at
    return {
        "id": f"PVTI_test_{issue_num}",
        "title": title,
        "status": "Implementing",
        "content": content,
        "issueType": {"name": level},
    }


# -- Extraction tests ----------------------------------------------------------

def test_timestamps_extracted():
    """map_gh_items_to_edpa should populate created_at, updated_at, closed_at."""
    data = {"items": [_gh_item(1, "S-1: foo", closed_at="2025-07-01T00:00:00Z")]}
    mapped = map_gh_items_to_edpa(data, FIELDS)
    item = mapped["S-1"]
    assert item["created_at"] == "2025-01-10T08:00:00Z"
    assert item["updated_at"] == "2025-06-15T12:00:00Z"
    assert item["closed_at"] == "2025-07-01T00:00:00Z"


def test_missing_timestamps_skipped():
    """When content has no timestamp keys, the entry should not contain them."""
    data = {"items": [_gh_item(2, "S-2: bar",
                               created_at=None, updated_at=None, closed_at=None)]}
    mapped = map_gh_items_to_edpa(data, FIELDS)
    item = mapped["S-2"]
    assert "created_at" not in item
    assert "updated_at" not in item
    assert "closed_at" not in item


def test_partial_timestamps():
    """Only present timestamps should appear on the entry."""
    data = {"items": [_gh_item(3, "F-3: baz", level="Feature",
                               created_at="2025-02-01T00:00:00Z",
                               updated_at=None, closed_at=None)]}
    mapped = map_gh_items_to_edpa(data, FIELDS)
    item = mapped["F-3"]
    assert item["created_at"] == "2025-02-01T00:00:00Z"
    assert "updated_at" not in item
    assert "closed_at" not in item


# -- Diff detection tests ------------------------------------------------------

def test_compute_diff_detects_timestamp_change():
    """compute_diff should report a field_changed for timestamp fields."""
    local = {"S-1": {"status": "Implementing", "created_at": "2025-01-01T00:00:00Z"}}
    remote = {"S-1": {"status": "Implementing", "created_at": "2025-01-10T08:00:00Z"}}
    changes = compute_diff(local, remote)
    ts_changes = [c for c in changes if c.get("field") == "created_at"]
    assert len(ts_changes) == 1
    assert ts_changes[0]["local_val"] == "2025-01-01T00:00:00Z"
    assert ts_changes[0]["remote_val"] == "2025-01-10T08:00:00Z"


def test_compute_diff_no_false_positive_when_equal():
    """Equal timestamps should produce no diff."""
    ts = "2025-06-15T12:00:00Z"
    local = {"S-1": {"status": "Implementing", "updated_at": ts}}
    remote = {"S-1": {"status": "Implementing", "updated_at": ts}}
    changes = compute_diff(local, remote)
    assert changes == []


# -- Read-only guard tests -----------------------------------------------------

def test_readonly_fields_constant():
    """READONLY_FIELDS must include all three timestamp fields."""
    assert READONLY_FIELDS == {"created_at", "closed_at", "updated_at"}


def test_gh_set_field_value_skips_readonly():
    """gh_set_field_value should silently return None for read-only fields."""
    dummy_state = {"project_id": "PID", "field_ids": {}, "option_ids": {}}
    for field in READONLY_FIELDS:
        result = gh_set_field_value(dummy_state, "ITEM_1", field, "2025-01-01", "Story")
        assert result is None, f"gh_set_field_value should return None for {field}"


# -- Validator acceptance tests ------------------------------------------------

def test_validator_accepts_timestamps_all_types():
    """All 6 item types should list the timestamp fields as optional."""
    for item_type, schema in ITEM_SCHEMA.items():
        for ts_field in ("created_at", "closed_at", "updated_at"):
            assert ts_field in schema["optional"], (
                f"{item_type} schema missing {ts_field!r} in optional set"
            )


# -- Integration: gh_fetch_project_items enrichment ----------------------------
# Regression for v1.23.0 bug: gh project item-list --format json does NOT
# include createdAt/closedAt/updatedAt in content. Enrichment must fetch them
# from `gh issue list` and merge into content before returning.

def _fake_subprocess_run_factory(item_list_payload, issue_list_payload):
    """Build a subprocess.run replacement that returns either payload based on argv.

    - `gh project item-list ...`  → item_list_payload (no timestamps)
    - `gh issue list   ...`        → issue_list_payload (with timestamps)
    """
    calls = []

    def fake_run(cmd, capture_output=False, text=False, timeout=None, **_kwargs):
        calls.append(cmd)
        if cmd[:3] == ["gh", "project", "item-list"]:
            payload = item_list_payload
        elif cmd[:3] == ["gh", "issue", "list"]:
            payload = issue_list_payload
        else:
            return SimpleNamespace(returncode=1, stdout="", stderr=f"unexpected: {cmd}")
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    return fake_run, calls


def test_gh_fetch_project_items_enriches_missing_timestamps(monkeypatch):
    """gh project item-list lacks timestamps → enrichment fills content from gh issue list."""
    item_list_payload = {
        "items": [
            {
                "id": "PVTI_x",
                "title": "S-1: foo",
                "status": "Implementing",
                "content": {
                    "body": "...",
                    "number": 1,
                    "repository": "acme/repo",
                    "title": "S-1: foo",
                    "type": "Issue",
                    "url": "https://github.com/acme/repo/issues/1",
                },
            },
            {
                "id": "PVTI_y",
                "title": "S-2: bar",
                "status": "Done",
                "content": {
                    "body": "...",
                    "number": 2,
                    "repository": "acme/repo",
                    "title": "S-2: bar",
                    "type": "Issue",
                    "url": "https://github.com/acme/repo/issues/2",
                },
            },
        ],
        "totalCount": 2,
    }
    issue_list_payload = [
        {
            "number": 1,
            "createdAt": "2025-01-10T08:00:00Z",
            "updatedAt": "2025-06-15T12:00:00Z",
            "closedAt": None,
        },
        {
            "number": 2,
            "createdAt": "2025-02-01T00:00:00Z",
            "updatedAt": "2025-07-01T00:00:00Z",
            "closedAt": "2025-07-01T00:00:00Z",
        },
    ]

    fake_run, calls = _fake_subprocess_run_factory(item_list_payload, issue_list_payload)
    monkeypatch.setattr(sync.subprocess, "run", fake_run)

    data = gh_fetch_project_items({"github_org": "acme", "github_project_number": 1})

    item1, item2 = data["items"]
    assert item1["content"]["createdAt"] == "2025-01-10T08:00:00Z"
    assert item1["content"]["updatedAt"] == "2025-06-15T12:00:00Z"
    assert "closedAt" not in item1["content"]  # None must not overwrite

    assert item2["content"]["createdAt"] == "2025-02-01T00:00:00Z"
    assert item2["content"]["closedAt"] == "2025-07-01T00:00:00Z"

    # One project call + one issue-list call per unique repo (here: 1 repo).
    issue_list_calls = [c for c in calls if c[:3] == ["gh", "issue", "list"]]
    assert len(issue_list_calls) == 1
    assert "--repo" in issue_list_calls[0]
    assert "acme/repo" in issue_list_calls[0]


def test_gh_fetch_project_items_batches_per_repo(monkeypatch):
    """Items spanning multiple repos → one gh issue list call per unique repo."""
    item_list_payload = {
        "items": [
            {"id": "A", "content": {"number": 1, "repository": "acme/repo-a"}},
            {"id": "B", "content": {"number": 7, "repository": "acme/repo-b"}},
            {"id": "C", "content": {"number": 2, "repository": "acme/repo-a"}},
        ],
        "totalCount": 3,
    }
    fake_run, calls = _fake_subprocess_run_factory(item_list_payload, [])
    monkeypatch.setattr(sync.subprocess, "run", fake_run)

    gh_fetch_project_items({"github_org": "acme", "github_project_number": 1})

    issue_list_repos = sorted(
        c[c.index("--repo") + 1] for c in calls if c[:3] == ["gh", "issue", "list"]
    )
    assert issue_list_repos == ["acme/repo-a", "acme/repo-b"]


def test_gh_fetch_project_items_enrichment_failure_is_silent(monkeypatch):
    """If gh issue list fails, items still return without timestamps."""
    item_list_payload = {
        "items": [{"id": "A", "content": {"number": 1, "repository": "acme/repo"}}],
        "totalCount": 1,
    }

    def fake_run(cmd, **_kwargs):
        if cmd[:3] == ["gh", "project", "item-list"]:
            return SimpleNamespace(returncode=0, stdout=json.dumps(item_list_payload), stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(sync.subprocess, "run", fake_run)
    data = gh_fetch_project_items({"github_org": "acme", "github_project_number": 1})

    assert data["items"][0]["content"]["number"] == 1
    assert "createdAt" not in data["items"][0]["content"]
