"""Tests for C3 CW governance features.

Covers:
  - diff_weights: human-readable weight diff
  - apply_to_heuristics dry_run=True: no file write
  - commit_heuristics: subprocess invocation (mocked)
  - validate_cw_heuristics: bounds [0.1, 8.0], missing signals, type errors
  - _is_heuristics_path: name matching
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

from calibrate_signals import (  # noqa: E402
    SIGNAL_TYPES,
    _read_current_weights,
    apply_to_heuristics,
    commit_heuristics,
    diff_weights,
)
from validate_syntax import (  # noqa: E402
    _is_heuristics_path,
    validate_cw_heuristics,
    validate_file,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_HEURISTICS = """\
signals:
  assignee: 4.00             # GitHub issue assignee
  pr_author: 3.40            # PR author referencing item
  commit_author: 2.78        # Commit with item ID in branch/title/msg
  pr_reviewer: 2.25          # PR review submitted (excluding self)
  issue_comment: 1.14        # Comment on issue/PR (excluding bots)

gates:
  min_signals: 1

calibration:
  method: "MC random-sample + coordinate descent"
  monte_carlo:
    scenarios: 1000
    records: 31041
  ground_truth_records: 0
  mad_baseline: 0.0861
  mad_calibrated: 0.0805
  improvement_pct: 6.5
  calibrated_at: "2026-05-08T18:37:24Z"
  calibrated_by_version: "2.5.1"
  notes: |
    Synthetic baseline.
"""

SAMPLE_REPORT = {
    "n_scenarios": 10,
    "n_records": 300,
    "seed": 42,
    "baseline_weights": {s: 1.0 for s in SIGNAL_TYPES},
    "baseline_mad": 0.0861,
    "calibrated_weights": {
        "assignee": 4.23,
        "pr_author": 3.38,
        "commit_author": 2.80,
        "pr_reviewer": 2.20,
        "issue_comment": 1.10,
    },
    "calibrated_mad": 0.0805,
    "improvement_pct": 6.5,
    "method": "MC + coord-descent",
    "real_records": 0,
}


@pytest.fixture
def heuristics_file(tmp_path):
    f = tmp_path / "cw_heuristics.yaml.tmpl"
    f.write_text(MINIMAL_HEURISTICS, encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# _read_current_weights
# ---------------------------------------------------------------------------

def test_read_current_weights(heuristics_file):
    w = _read_current_weights(heuristics_file)
    assert w["assignee"] == pytest.approx(4.00)
    assert w["commit_author"] == pytest.approx(2.78)


def test_read_current_weights_missing_file(tmp_path):
    assert _read_current_weights(tmp_path / "nonexistent.yaml") == {}


# ---------------------------------------------------------------------------
# diff_weights
# ---------------------------------------------------------------------------

def test_diff_weights_shows_changes():
    old = {"assignee": 4.0, "pr_author": 3.4, "commit_author": 2.78,
           "pr_reviewer": 2.25, "issue_comment": 1.14}
    new = {"assignee": 4.23, "pr_author": 3.38, "commit_author": 2.80,
           "pr_reviewer": 2.20, "issue_comment": 1.10}
    lines = diff_weights(old, new)
    assert len(lines) == 5
    assert any("assignee" in l for l in lines)
    assert any("↑" in l for l in lines)  # at least one increase
    assert any("↓" in l for l in lines)  # at least one decrease


def test_diff_weights_no_change():
    same = {"assignee": 4.0, "pr_author": 3.4, "commit_author": 2.78,
            "pr_reviewer": 2.25, "issue_comment": 1.14}
    lines = diff_weights(same, same)
    assert all("  " in l for l in lines)  # all "no-change" marker


def test_diff_weights_empty_old():
    new = {s: 1.0 for s in SIGNAL_TYPES}
    lines = diff_weights({}, new)
    assert lines == []  # missing old → no diff lines


# ---------------------------------------------------------------------------
# apply_to_heuristics dry_run
# ---------------------------------------------------------------------------

def test_dry_run_does_not_write(heuristics_file, capsys):
    original = heuristics_file.read_text()
    apply_to_heuristics(SAMPLE_REPORT, heuristics_file, dry_run=True)
    assert heuristics_file.read_text() == original  # unchanged


def test_dry_run_prints_diff(heuristics_file, capsys):
    apply_to_heuristics(SAMPLE_REPORT, heuristics_file, dry_run=True)
    out = capsys.readouterr().out
    assert "dry-run" in out.lower()
    assert "assignee" in out


def test_apply_writes_new_weights(heuristics_file, capsys):
    apply_to_heuristics(SAMPLE_REPORT, heuristics_file, dry_run=False)
    w = _read_current_weights(heuristics_file)
    assert w["assignee"] == pytest.approx(4.23)
    assert w["commit_author"] == pytest.approx(2.80)


def test_apply_missing_target(tmp_path, capsys):
    with pytest.raises(SystemExit):
        apply_to_heuristics(SAMPLE_REPORT, tmp_path / "nonexistent.yaml")


# ---------------------------------------------------------------------------
# commit_heuristics (subprocess mocked)
# ---------------------------------------------------------------------------

def test_commit_heuristics_calls_git(heuristics_file):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = commit_heuristics(heuristics_file, SAMPLE_REPORT)
    assert result is True
    assert mock_run.call_count == 2  # git add + git commit
    # First call: git add
    first_args = mock_run.call_args_list[0][0][0]
    assert first_args[0] == "git"
    assert first_args[1] == "add"
    # Second call: git commit with MAD info
    second_args = mock_run.call_args_list[1][0][0]
    assert second_args[0] == "git"
    assert second_args[1] == "commit"
    commit_msg = second_args[3]
    assert "0.0861" in commit_msg
    assert "0.0805" in commit_msg


def test_commit_heuristics_returns_false_on_failure(heuristics_file):
    import subprocess
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")):
        result = commit_heuristics(heuristics_file, SAMPLE_REPORT)
    assert result is False


def test_commit_heuristics_returns_false_when_git_missing(heuristics_file):
    with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
        result = commit_heuristics(heuristics_file, SAMPLE_REPORT)
    assert result is False


# ---------------------------------------------------------------------------
# _is_heuristics_path
# ---------------------------------------------------------------------------

def test_is_heuristics_path_yaml():
    assert _is_heuristics_path(Path(".edpa/config/cw_heuristics.yaml"))


def test_is_heuristics_path_tmpl():
    assert _is_heuristics_path(Path("plugin/edpa/templates/cw_heuristics.yaml.tmpl"))


def test_is_heuristics_path_other():
    assert not _is_heuristics_path(Path(".edpa/config/people.yaml"))
    assert not _is_heuristics_path(Path("some/other.yaml"))


# ---------------------------------------------------------------------------
# validate_cw_heuristics
# ---------------------------------------------------------------------------

def test_valid_weights_no_errors(tmp_path):
    errors, warnings = validate_cw_heuristics(
        tmp_path / "cw_heuristics.yaml",
        {"signals": {"assignee": 4.0, "pr_author": 3.4, "commit_author": 2.78,
                     "pr_reviewer": 2.25, "issue_comment": 1.14}},
    )
    assert errors == []
    assert warnings == []


def test_weight_below_minimum(tmp_path):
    errors, _ = validate_cw_heuristics(
        tmp_path / "cw_heuristics.yaml",
        {"signals": {"assignee": 0.05, "pr_author": 3.4, "commit_author": 2.78,
                     "pr_reviewer": 2.25, "issue_comment": 1.14}},
    )
    assert any("assignee" in e for e in errors)
    assert any("0.1" in e for e in errors)


def test_weight_above_maximum(tmp_path):
    errors, _ = validate_cw_heuristics(
        tmp_path / "cw_heuristics.yaml",
        {"signals": {"assignee": 9.0, "pr_author": 3.4, "commit_author": 2.78,
                     "pr_reviewer": 2.25, "issue_comment": 1.14}},
    )
    assert any("assignee" in e for e in errors)
    assert any("8.0" in e for e in errors)


def test_missing_signal_key_is_warning(tmp_path):
    _, warnings = validate_cw_heuristics(
        tmp_path / "cw_heuristics.yaml",
        {"signals": {"assignee": 4.0}},
    )
    assert any("pr_author" in w for w in warnings)


def test_non_numeric_weight_is_error(tmp_path):
    errors, _ = validate_cw_heuristics(
        tmp_path / "cw_heuristics.yaml",
        {"signals": {"assignee": "high", "pr_author": 3.4, "commit_author": 2.78,
                     "pr_reviewer": 2.25, "issue_comment": 1.14}},
    )
    assert any("assignee" in e for e in errors)


def test_signals_not_mapping_is_error(tmp_path):
    errors, _ = validate_cw_heuristics(
        tmp_path / "cw_heuristics.yaml",
        {"signals": [1, 2, 3]},
    )
    assert errors


def test_validate_file_heuristics(tmp_path):
    f = tmp_path / "cw_heuristics.yaml"
    f.write_text(
        "signals:\n  assignee: 99.0\n  pr_author: 3.4\n"
        "  commit_author: 2.78\n  pr_reviewer: 2.25\n  issue_comment: 1.14\n",
        encoding="utf-8",
    )
    errors, _ = validate_file(f)
    assert any("assignee" in e for e in errors)
