"""Tests for F2 insights.py — mid-iteration anomaly detection.

Covers:
  - detect_capacity_overload: normal, warning (110-120%), critical (>120%)
  - detect_job_size_creep: below/above threshold
  - detect_stalled_stories: idle < threshold, idle > threshold
  - detect_critical_path_blockers: dep done, dep in_progress
  - compute_insights: integration with a minimal edpa_results.json
  - render_md: headers, severity badges, empty report
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

from insights import (  # noqa: E402
    DEFAULT_JS_THRESHOLD,
    DEFAULT_OVERLOAD_THRESHOLD,
    DEFAULT_STALE_DAYS,
    compute_insights,
    detect_capacity_overload,
    detect_critical_path_blockers,
    detect_job_size_creep,
    detect_stalled_stories,
    render_md,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_results(tmp_path: Path, iteration: str, reports: list[dict]) -> Path:
    out = tmp_path / "reports" / f"iteration-{iteration}"
    out.mkdir(parents=True)
    payload = {
        "iteration": iteration,
        "derived_reports": reports,
        "items": [],
    }
    (out / "edpa_results.json").write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path


def _make_item(tmp_path: Path, item_id: str, **kwargs) -> Path:
    backlog = tmp_path / "backlog" / "stories"
    backlog.mkdir(parents=True, exist_ok=True)
    fm_lines = ["---"]
    fm = {"id": item_id, "type": "Story", **kwargs}
    for k, v in fm.items():
        if isinstance(v, list):
            fm_lines.append(f"{k}:")
            for item in v:
                fm_lines.append(f"  - {item}")
        else:
            fm_lines.append(f"{k}: {v}")
    fm_lines += ["---", ""]
    f = backlog / f"{item_id}.md"
    f.write_text("\n".join(fm_lines), encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# detect_capacity_overload
# ---------------------------------------------------------------------------

def test_no_overload_below_threshold():
    reports = [{"person": "alice", "name": "Alice", "capacity": 40.0, "total_derived": 40.0}]
    assert detect_capacity_overload(reports, threshold=1.10) == []


def test_overload_warning_between_110_120():
    reports = [{"person": "alice", "name": "Alice", "capacity": 40.0, "total_derived": 44.5}]
    result = detect_capacity_overload(reports, threshold=1.10)
    assert len(result) == 1
    assert result[0]["severity"] == "warning"
    assert result[0]["person"] == "alice"
    assert result[0]["overload_pct"] == pytest.approx(11.25, abs=0.1)


def test_overload_critical_above_120():
    reports = [{"person": "bob", "name": "Bob", "capacity": 40.0, "total_derived": 50.0}]
    result = detect_capacity_overload(reports, threshold=1.10)
    assert len(result) == 1
    assert result[0]["severity"] == "critical"


def test_overload_zero_capacity_skipped():
    reports = [{"person": "alice", "capacity": 0, "total_derived": 10.0}]
    assert detect_capacity_overload(reports) == []


def test_overload_multiple_people():
    reports = [
        {"person": "a", "name": "A", "capacity": 40.0, "total_derived": 50.0},
        {"person": "b", "name": "B", "capacity": 40.0, "total_derived": 38.0},
        {"person": "c", "name": "C", "capacity": 40.0, "total_derived": 48.0},
    ]
    result = detect_capacity_overload(reports, threshold=1.10)
    persons = {r["person"] for r in result}
    assert "a" in persons
    assert "c" in persons
    assert "b" not in persons


# ---------------------------------------------------------------------------
# detect_job_size_creep
# ---------------------------------------------------------------------------

def test_job_size_at_threshold_no_flag(tmp_path):
    f = _make_item(tmp_path, "S-1", js=8, iteration="PI-2026-1.1", status="todo")
    result = detect_job_size_creep([({"id": "S-1", "type": "Story", "js": 8}, f)])
    assert result == []


def test_job_size_above_threshold_flagged(tmp_path):
    f = _make_item(tmp_path, "S-2", js=13, iteration="PI-2026-1.1", status="todo")
    result = detect_job_size_creep(
        [({"id": "S-2", "type": "Story", "js": 13, "title": "Big story"}, f)],
        js_threshold=8,
    )
    assert len(result) == 1
    assert result[0]["item"] == "S-2"
    assert result[0]["severity"] == "warning"


def test_job_size_non_story_skipped(tmp_path):
    backlog = tmp_path / "backlog" / "features"
    backlog.mkdir(parents=True)
    f = backlog / "F-5.md"
    f.write_text("---\nid: F-5\ntype: Feature\njs: 20\niteration: PI-2026-1.1\n---\n")
    result = detect_job_size_creep(
        [({"id": "F-5", "type": "Feature", "js": 20}, f)],
    )
    assert result == []


# ---------------------------------------------------------------------------
# detect_stalled_stories
# ---------------------------------------------------------------------------

def test_stalled_story_flagged(tmp_path):
    f = _make_item(tmp_path, "S-10", status="in_progress", title="Stalled")
    now = 1_000_000_000.0
    stale_epoch = int(now - 7 * 86400)  # 7 days ago
    with patch("insights._git_last_commit_epoch", return_value=stale_epoch):
        result = detect_stalled_stories(
            [({"id": "S-10", "type": "Story", "status": "in_progress", "title": "Stalled"}, f)],
            stale_days=5,
            now_epoch=now,
        )
    assert len(result) == 1
    assert result[0]["item"] == "S-10"
    assert result[0]["days_idle"] == pytest.approx(7.0, abs=0.1)


def test_active_story_not_flagged(tmp_path):
    f = _make_item(tmp_path, "S-11", status="in_progress", title="Active")
    now = 1_000_000_000.0
    recent_epoch = int(now - 2 * 86400)  # 2 days ago
    with patch("insights._git_last_commit_epoch", return_value=recent_epoch):
        result = detect_stalled_stories(
            [({"id": "S-11", "type": "Story", "status": "in_progress", "title": "Active"}, f)],
            stale_days=5,
            now_epoch=now,
        )
    assert result == []


def test_done_story_not_stalled(tmp_path):
    f = _make_item(tmp_path, "S-12", status="Done", title="Done story")
    now = 1_000_000_000.0
    old_epoch = int(now - 30 * 86400)
    with patch("insights._git_last_commit_epoch", return_value=old_epoch):
        result = detect_stalled_stories(
            [({"id": "S-12", "type": "Story", "status": "Done"}, f)],
            stale_days=5,
            now_epoch=now,
        )
    assert result == []


def test_no_git_history_skipped(tmp_path):
    f = _make_item(tmp_path, "S-13", status="in_progress")
    with patch("insights._git_last_commit_epoch", return_value=None):
        result = detect_stalled_stories(
            [({"id": "S-13", "type": "Story", "status": "in_progress"}, f)],
            now_epoch=1_000_000_000.0,
        )
    assert result == []


# ---------------------------------------------------------------------------
# detect_critical_path_blockers
# ---------------------------------------------------------------------------

def test_blocker_dep_not_done(tmp_path):
    f = _make_item(tmp_path, "S-20", status="in_progress", title="Blocked", depends_on="S-19")
    _make_item(tmp_path, "S-19", status="in_progress", title="Blocking")
    result = detect_critical_path_blockers(
        [({"id": "S-20", "type": "Story", "status": "in_progress",
           "title": "Blocked", "depends_on": ["S-19"]}, f)],
        edpa_root=tmp_path,
    )
    assert len(result) == 1
    assert result[0]["item"] == "S-20"
    assert result[0]["blocked_by"] == "S-19"
    assert result[0]["severity"] == "critical"


def test_blocker_dep_done_no_flag(tmp_path):
    f = _make_item(tmp_path, "S-21", status="in_progress", title="OK", depends_on="S-19")
    _make_item(tmp_path, "S-19", status="Done", title="Done dep")
    result = detect_critical_path_blockers(
        [({"id": "S-21", "type": "Story", "status": "in_progress",
           "title": "OK", "depends_on": ["S-19"]}, f)],
        edpa_root=tmp_path,
    )
    assert result == []


def test_blocker_no_deps(tmp_path):
    f = _make_item(tmp_path, "S-22", status="in_progress", title="Free")
    result = detect_critical_path_blockers(
        [({"id": "S-22", "type": "Story", "status": "in_progress", "title": "Free"}, f)],
        edpa_root=tmp_path,
    )
    assert result == []


def test_done_story_not_checked_for_blocker(tmp_path):
    f = _make_item(tmp_path, "S-23", status="Done", title="Closed", depends_on="S-19")
    _make_item(tmp_path, "S-19", status="in_progress")
    result = detect_critical_path_blockers(
        [({"id": "S-23", "type": "Story", "status": "Done",
           "title": "Closed", "depends_on": ["S-19"]}, f)],
        edpa_root=tmp_path,
    )
    assert result == []


# ---------------------------------------------------------------------------
# compute_insights (integration)
# ---------------------------------------------------------------------------

def test_compute_insights_no_anomalies(tmp_path):
    _make_results(tmp_path, "PI-2026-1.1", [
        {"person": "alice", "name": "Alice", "capacity": 40.0, "total_derived": 38.0},
    ])
    _make_item(tmp_path, "S-30", iteration="PI-2026-1.1", status="in_progress",
               title="Normal", js=5)
    with patch("insights._git_last_commit_epoch", return_value=9_999_999_999):
        report = compute_insights(tmp_path, "PI-2026-1.1", now_epoch=10_000_000_000.0)
    assert report["anomaly_count"] == 0
    assert report["critical"] == 0
    assert report["warnings"] == 0


def test_compute_insights_overload_and_creep(tmp_path):
    _make_results(tmp_path, "PI-2026-1.2", [
        {"person": "bob", "name": "Bob", "capacity": 40.0, "total_derived": 50.0},
    ])
    _make_item(tmp_path, "S-40", iteration="PI-2026-1.2", status="todo",
               title="Huge", js=13)
    with patch("insights._git_last_commit_epoch", return_value=9_999_999_999):
        report = compute_insights(tmp_path, "PI-2026-1.2", now_epoch=10_000_000_000.0)
    assert report["anomaly_count"] >= 2
    types = {a["type"] for a in report["anomalies"]}
    assert "capacity_overload" in types
    assert "job_size_creep" in types


def test_compute_insights_thresholds_in_report(tmp_path):
    _make_results(tmp_path, "PI-2026-1.3", [])
    report = compute_insights(
        tmp_path, "PI-2026-1.3",
        overload_threshold=1.15,
        js_threshold=5,
        stale_days=3,
        now_epoch=10_000_000_000.0,
    )
    assert report["thresholds"]["overload_pct"] == 15
    assert report["thresholds"]["js_max"] == 5
    assert report["thresholds"]["stale_days"] == 3


# ---------------------------------------------------------------------------
# render_md
# ---------------------------------------------------------------------------

def test_render_md_no_anomalies():
    report = {
        "iteration": "PI-2026-1.1",
        "anomaly_count": 0,
        "critical": 0,
        "warnings": 0,
        "anomalies": [],
        "thresholds": {"overload_pct": 10, "js_max": 8, "stale_days": 5},
    }
    md = render_md(report)
    assert "No anomalies" in md
    assert "PI-2026-1.1" in md


def test_render_md_with_anomalies():
    report = {
        "iteration": "PI-2026-1.2",
        "anomaly_count": 2,
        "critical": 1,
        "warnings": 1,
        "anomalies": [
            {"type": "capacity_overload", "severity": "critical",
             "person": "alice", "message": "Alice overloaded"},
            {"type": "job_size_creep", "severity": "warning",
             "item": "S-5", "message": "S-5 has JS=13"},
        ],
        "thresholds": {"overload_pct": 10, "js_max": 8, "stale_days": 5},
    }
    md = render_md(report)
    assert "Capacity Overload" in md
    assert "Job Size Creep" in md
    assert "Alice overloaded" in md
    assert "S-5 has JS=13" in md
    assert "🔴" in md
    assert "🟡" in md


def test_render_md_all_sections_present():
    types = [
        ("capacity_overload", "critical"),
        ("job_size_creep", "warning"),
        ("stalled_story", "warning"),
        ("critical_path_blocker", "critical"),
    ]
    anomalies = [
        {"type": t, "severity": s, "message": f"msg for {t}"}
        for t, s in types
    ]
    report = {
        "iteration": "PI-X",
        "anomaly_count": len(anomalies),
        "critical": 2,
        "warnings": 2,
        "anomalies": anomalies,
        "thresholds": {"overload_pct": 10, "js_max": 8, "stale_days": 5},
    }
    md = render_md(report)
    for title in ("Capacity Overload", "Job Size Creep", "Stalled Stories", "Critical Path"):
        assert title in md
