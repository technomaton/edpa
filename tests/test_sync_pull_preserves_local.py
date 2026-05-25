"""Regression tests for compute_diff non-destructive pull behavior.

Background: `gh project item-list --format json` does not expose user
picker fields (assignee, owner) — they come back empty even when the
issue has assignees set on GitHub. Without a guard, `sync pull` saw
remote.assignee == "" and proposed wiping the local `assignee:` value
on every run. The same applies to `iteration` when the option hasn't
been created yet on the Project.

These tests pin compute_diff to the safe behavior: when remote is
empty AND local has a value, for these fields, no change is proposed
(local wins). The push direction still writes these fields correctly
via gh issue edit --add-assignee / gh_set_field_value.

If these tests fail, sync pull will start destroying local
assignee/owner/iteration data on every run.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "plugin" / "edpa" / "scripts"))

from sync import compute_diff  # noqa: E402


def _local(item_id, **fields):
    base = {"level": "Story", "title": "x", "status": "Backlog"}
    base.update(fields)
    return {item_id: base}


def _remote(item_id, **fields):
    base = {"level": "Story", "title": "x", "status": "Backlog"}
    base.update(fields)
    return {item_id: base}


def _field_changes(changes, item_id=None, field=None):
    out = [c for c in changes if c["action"] == "field_changed"]
    if item_id is not None:
        out = [c for c in out if c["id"] == item_id]
    if field is not None:
        out = [c for c in out if c["field"] == field]
    return out


def test_pull_does_not_wipe_local_assignee_when_remote_empty():
    local = _local("S-4", assignee="jurby")
    remote = _remote("S-4")  # no assignee on remote
    changes = compute_diff(local, remote)
    assert _field_changes(changes, "S-4", "assignee") == [], (
        "pull would wipe local assignee — Bug 2 regression"
    )


def test_pull_does_not_wipe_local_owner_when_remote_empty():
    local = _local("S-4", owner="martin")
    remote = _remote("S-4")
    changes = compute_diff(local, remote)
    assert _field_changes(changes, "S-4", "owner") == []


def test_pull_does_not_wipe_local_iteration_when_remote_empty():
    local = _local("S-4", iteration="PI-2026-1.1")
    remote = _remote("S-4")
    changes = compute_diff(local, remote)
    assert _field_changes(changes, "S-4", "iteration") == []


def test_pull_still_applies_remote_assignee_when_remote_has_value():
    """Guard is one-way: empty-remote is non-destructive, but a real
    remote value still wins. (This case is rare today because
    gh project item-list doesn't expose assignees, but the contract
    must hold for a future GraphQL-based fetch.)"""
    local = _local("S-4", assignee="jurby")
    remote = _remote("S-4", assignee="martin")
    changes = compute_diff(local, remote)
    field_changes = _field_changes(changes, "S-4", "assignee")
    assert len(field_changes) == 1, "remote→local assignee update must still flow"
    assert field_changes[0]["local_val"] == "jurby"
    assert field_changes[0]["remote_val"] == "martin"


def test_pull_still_wipes_other_fields_on_empty_remote():
    """The guard is intentionally narrow — other fields (e.g. status, js)
    must still propagate empty values, otherwise we'd never honor a
    genuine clear on GH side."""
    local = _local("S-4", js=5)
    remote = _remote("S-4")  # js missing
    changes = compute_diff(local, remote)
    js_changes = _field_changes(changes, "S-4", "js")
    assert len(js_changes) == 1
    assert js_changes[0]["local_val"] == 5
    assert js_changes[0]["remote_val"] == ""


def test_status_diff_still_works():
    local = _local("S-4", status="Done")
    remote = _remote("S-4", status="Implementing")
    changes = compute_diff(local, remote)
    status_changes = _field_changes(changes, "S-4", "status")
    assert len(status_changes) == 1
