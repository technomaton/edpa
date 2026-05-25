"""Tests for timestamp-based conflict detection."""
from __future__ import annotations
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "plugin" / "edpa" / "scripts"))

from sync import _detect_remote_modifications  # noqa: E402


def test_detects_modified_items():
    remote = {
        "S-1": {"updated_at": "2026-05-20T10:00:00Z"},
        "S-2": {"updated_at": "2026-05-18T10:00:00Z"},
    }
    result = _detect_remote_modifications(remote, "2026-05-19T00:00:00Z")
    assert result == {"S-1"}


def test_no_modifications_when_all_older():
    remote = {
        "S-1": {"updated_at": "2026-05-10T10:00:00Z"},
    }
    result = _detect_remote_modifications(remote, "2026-05-19T00:00:00Z")
    assert result == set()


def test_handles_missing_updated_at():
    remote = {
        "S-1": {"title": "no timestamp"},
        "S-2": {"updated_at": ""},
    }
    result = _detect_remote_modifications(remote, "2026-05-19T00:00:00Z")
    assert result == set()


def test_empty_last_pull_returns_empty():
    remote = {"S-1": {"updated_at": "2026-05-20T10:00:00Z"}}
    assert _detect_remote_modifications(remote, "") == set()
    assert _detect_remote_modifications(remote, None) == set()
