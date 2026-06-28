"""Tests for F4 — AI attribution (ai_attribution.py + local_evidence.py changes).

Covers:
  - _normalize_agent_name: converts 'Claude Sonnet 4.6 ' → 'claude-sonnet-4-6'
  - _AGENT_COAUTHOR_RE regex: matches Co-Authored-By / Co-authored-by trailers
  - build_signals: emits agent_contribution signal when AI co-author present
  - compute_ai_attribution: per-item and per-person breakdown, ai_delivery_ratio
  - render_md: correct Markdown output structure
  - ai_attribution: writes json + md files to reports dir
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

from ai_attribution import (  # noqa: E402
    compute_ai_attribution,
    render_md,
)
from local_evidence import (  # noqa: E402
    _normalize_agent_name,
    _AGENT_COAUTHOR_RE,
    build_signals,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item_md(tmp_path: Path, item_id: str, **kwargs) -> Path:
    """Write a minimal .md backlog item with YAML frontmatter."""
    backlog = tmp_path / "backlog" / "stories"
    backlog.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"id: {item_id}", "type: Story"]
    for k, v in kwargs.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            for entry in v:
                if isinstance(entry, dict):
                    first = True
                    for ek, ev in entry.items():
                        prefix = "  - " if first else "    "
                        first = False
                        lines.append(f"{prefix}{ek}: {ev!r}")
                else:
                    lines.append(f"  - {entry!r}")
        else:
            lines.append(f"{k}: {v!r}")
    lines.append("---")
    p = backlog / f"{item_id}.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# _normalize_agent_name
# ---------------------------------------------------------------------------

def test_normalize_agent_name_basic():
    assert _normalize_agent_name("Claude Sonnet 4.6 ") == "claude-sonnet-4-6"


def test_normalize_agent_name_opus():
    assert _normalize_agent_name("Claude Opus 4.8") == "claude-opus-4-8"


def test_normalize_agent_name_already_normalized():
    assert _normalize_agent_name("claude-haiku-4-5") == "claude-haiku-4-5"


# ---------------------------------------------------------------------------
# _AGENT_COAUTHOR_RE
# ---------------------------------------------------------------------------

def test_coauthor_re_standard_case():
    body = "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
    matches = _AGENT_COAUTHOR_RE.findall(body)
    assert len(matches) == 1
    assert "Claude Sonnet 4.6" in matches[0]


def test_coauthor_re_lowercase_variant():
    body = "Co-authored-by: Claude Opus 4.8 <noreply@anthropic.com>"
    matches = _AGENT_COAUTHOR_RE.findall(body)
    assert len(matches) == 1


def test_coauthor_re_multiline():
    body = (
        "Some commit message body\n"
        "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>\n"
        "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>\n"
    )
    matches = _AGENT_COAUTHOR_RE.findall(body)
    assert len(matches) == 2


def test_coauthor_re_no_match_non_anthropic():
    body = "Co-Authored-By: Bob Dev <bob@example.com>"
    assert not _AGENT_COAUTHOR_RE.findall(body)


def test_coauthor_re_no_match_empty():
    assert not _AGENT_COAUTHOR_RE.findall("")


# ---------------------------------------------------------------------------
# build_signals — agent_contribution emission
# ---------------------------------------------------------------------------

def _fake_commit(body: str, items: list[str] | None = None) -> dict:
    items = items or ["S-1"]
    return {
        "sha": "abc1234" + "0" * 33,
        "parents": ["parent0"],
        "author_email": "user@example.com",
        "author_name": "Test User",
        # D-38: build_signals only credits leading-scope (or .md-changed) items,
        # so scope the commit on exactly the items under test.
        "subject": f"feat({','.join(items)}): test commit",
        "body": body,
        "changed_files": [],
    }


def test_build_signals_no_agent():
    commit = _fake_commit("Just a regular commit body.")
    sigs = build_signals(commit, ["S-1"], "alice", {"commit_author": 2.78})
    types = [s["signal"]["type"] for s in sigs]
    assert "commit_author" in types
    assert "agent_contribution" not in types


def test_build_signals_with_claude_coauthor():
    body = "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
    commit = _fake_commit(body)
    sigs = build_signals(commit, ["S-1"], "alice", {"commit_author": 2.78})
    agent_sigs = [s for s in sigs if s["signal"]["type"] == "agent_contribution"]
    assert len(agent_sigs) == 1
    assert agent_sigs[0]["signal"]["agent"] == "claude-sonnet-4-6"
    assert agent_sigs[0]["signal"]["person"] == "_claude"
    assert agent_sigs[0]["item_id"] == "S-1"


def test_build_signals_deduplicates_same_agent():
    body = (
        "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>\n"
        "Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>\n"
    )
    commit = _fake_commit(body)
    sigs = build_signals(commit, ["S-1"], "alice", {})
    agent_sigs = [s for s in sigs if s["signal"]["type"] == "agent_contribution"]
    # Two matches in regex → two signals (not deduplicated at this level because
    # they get deduplicated by ref in _apply_to_item; both have same ref)
    assert all(s["signal"]["agent"] == "claude-sonnet-4-6" for s in agent_sigs)


def test_build_signals_ref_contains_agent():
    body = "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
    commit = _fake_commit(body, ["S-99"])
    sigs = build_signals(commit, ["S-99"], "bob", {})
    agent_sigs = [s for s in sigs if s["signal"]["type"] == "agent_contribution"]
    assert "claude-opus-4-8" in agent_sigs[0]["signal"]["ref"]


def test_build_signals_multiple_items_each_get_agent_sig():
    body = "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
    # Both items are in the leading scope → both are worked-on, so each earns an
    # agent_contribution (D-38: credit follows scope/changed-files, not a bare
    # mention).
    commit = _fake_commit(body, ["S-1", "S-2"])
    sigs = build_signals(commit, ["S-1", "S-2"], "alice", {})
    item_ids_with_agent = {s["item_id"] for s in sigs
                           if s["signal"]["type"] == "agent_contribution"}
    assert item_ids_with_agent == {"S-1", "S-2"}


# ---------------------------------------------------------------------------
# compute_ai_attribution
# ---------------------------------------------------------------------------

def _write_item(tmp_path: Path, item_id: str, iteration: str,
                evidence: list[dict], contributors: list[dict]) -> None:
    """Write a done Story with given evidence and contributors."""
    backlog = tmp_path / "backlog" / "stories"
    backlog.mkdir(parents=True, exist_ok=True)
    import yaml  # noqa: PLC0415
    data = {
        "id": item_id,
        "type": "Story",
        "status": "done",
        "iteration": iteration,
        "title": f"Test story {item_id}",
        "js": 3,
        "evidence": evidence,
        "contributors": contributors,
    }
    p = backlog / f"{item_id}.md"
    fm = yaml.dump(data, default_flow_style=False, allow_unicode=True)
    p.write_text(f"---\n{fm}---\n", encoding="utf-8")


def test_compute_ai_attribution_no_items(tmp_path: Path):
    edpa_root = tmp_path / ".edpa"
    (edpa_root / "backlog" / "stories").mkdir(parents=True)
    report = compute_ai_attribution(edpa_root, "PI-2026-1.1")
    assert report["summary"]["total_items"] == 0
    assert report["summary"]["ai_delivery_ratio"] == 0.0


def test_compute_ai_attribution_all_human(tmp_path: Path):
    edpa = tmp_path / ".edpa"
    _write_item(
        edpa, "S-1", "PI-2026-1.1",
        evidence=[{"type": "commit_author", "person": "alice", "ref": "commit/abc"}],
        contributors=[{"person": "alice", "cw": 1.0}],
    )
    report = compute_ai_attribution(edpa, "PI-2026-1.1")
    assert report["summary"]["total_items"] == 1
    assert report["summary"]["ai_assisted_items"] == 0
    assert report["summary"]["ai_delivery_ratio"] == 0.0
    assert report["summary"]["unique_agents"] == []


def test_compute_ai_attribution_one_ai_item(tmp_path: Path):
    edpa = tmp_path / ".edpa"
    _write_item(
        edpa, "S-1", "PI-2026-1.1",
        evidence=[
            {"type": "commit_author", "person": "alice", "ref": "commit/abc"},
            {"type": "agent_contribution", "agent": "claude-sonnet-4-6",
             "person": "_claude", "ref": "commit/abc/agent/claude-sonnet-4-6"},
        ],
        contributors=[{"person": "alice", "cw": 1.0}],
    )
    report = compute_ai_attribution(edpa, "PI-2026-1.1")
    assert report["summary"]["ai_assisted_items"] == 1
    assert report["summary"]["ai_delivery_ratio"] == 1.0
    assert "claude-sonnet-4-6" in report["summary"]["unique_agents"]


def test_compute_ai_attribution_mixed(tmp_path: Path):
    edpa = tmp_path / ".edpa"
    _write_item(
        edpa, "S-1", "PI-2026-1.1",
        evidence=[
            {"type": "agent_contribution", "agent": "claude-sonnet-4-6",
             "person": "_claude", "ref": "commit/aaa/agent/claude-sonnet-4-6"},
        ],
        contributors=[{"person": "alice", "cw": 1.0}],
    )
    _write_item(
        edpa, "S-2", "PI-2026-1.1",
        evidence=[{"type": "commit_author", "person": "alice", "ref": "commit/bbb"}],
        contributors=[{"person": "alice", "cw": 1.0}],
    )
    report = compute_ai_attribution(edpa, "PI-2026-1.1")
    assert report["summary"]["total_items"] == 2
    assert report["summary"]["ai_assisted_items"] == 1
    assert abs(report["summary"]["ai_delivery_ratio"] - 0.5) < 0.001


def test_compute_ai_attribution_by_person(tmp_path: Path):
    edpa = tmp_path / ".edpa"
    _write_item(
        edpa, "S-1", "PI-2026-1.1",
        evidence=[{"type": "agent_contribution", "agent": "claude-sonnet-4-6",
                   "person": "_claude", "ref": "commit/aaa/agent/claude-sonnet-4-6"}],
        contributors=[{"person": "alice", "cw": 1.0}],
    )
    _write_item(
        edpa, "S-2", "PI-2026-1.1",
        evidence=[{"type": "commit_author", "person": "alice", "ref": "commit/bbb"}],
        contributors=[{"person": "alice", "cw": 1.0}],
    )
    report = compute_ai_attribution(edpa, "PI-2026-1.1")
    alice = next(p for p in report["by_person"] if p["person_id"] == "alice")
    assert alice["total_items"] == 2
    assert alice["ai_assisted_items"] == 1
    assert abs(alice["ai_ratio"] - 0.5) < 0.001


def test_compute_ai_attribution_excludes_internal_person(tmp_path: Path):
    """_claude synthetic person must not appear in by_person."""
    edpa = tmp_path / ".edpa"
    _write_item(
        edpa, "S-1", "PI-2026-1.1",
        evidence=[{"type": "agent_contribution", "agent": "claude-sonnet-4-6",
                   "person": "_claude", "ref": "commit/aaa/agent/claude-sonnet-4-6"}],
        contributors=[{"person": "_claude", "cw": 0.5}, {"person": "bob", "cw": 0.5}],
    )
    report = compute_ai_attribution(edpa, "PI-2026-1.1")
    person_ids = {p["person_id"] for p in report["by_person"]}
    assert "_claude" not in person_ids
    assert "bob" in person_ids


# ---------------------------------------------------------------------------
# render_md
# ---------------------------------------------------------------------------

def test_render_md_contains_header():
    report = {
        "iteration": "PI-2026-1.3",
        "summary": {
            "total_items": 5, "ai_assisted_items": 2,
            "ai_delivery_ratio": 0.4, "unique_agents": ["claude-sonnet-4-6"],
        },
        "by_person": [
            {"person_id": "alice", "total_items": 5, "ai_assisted_items": 2,
             "ai_ratio": 0.4},
        ],
        "items": [
            {"id": "S-1", "title": "Feature X", "ai_signals": 1,
             "human_signals": 2, "ai_assisted": True, "agents": ["claude-sonnet-4-6"]},
        ],
    }
    md = render_md(report)
    assert "# AI Attribution — PI-2026-1.3" in md
    assert "40.0%" in md
    assert "claude-sonnet-4-6" in md
    assert "alice" in md
    assert "S-1" in md


def test_render_md_no_agents():
    report = {
        "iteration": "PI-2026-1.1",
        "summary": {
            "total_items": 3, "ai_assisted_items": 0,
            "ai_delivery_ratio": 0.0, "unique_agents": [],
        },
        "by_person": [],
        "items": [],
    }
    md = render_md(report)
    assert "0.0%" in md
    assert "—" in md


# ---------------------------------------------------------------------------
# ai_attribution (writes files)
# ---------------------------------------------------------------------------

def test_ai_attribution_writes_files(tmp_path: Path):
    from ai_attribution import ai_attribution  # noqa: PLC0415
    edpa = tmp_path / ".edpa"
    _write_item(
        edpa, "S-1", "PI-2026-1.1",
        evidence=[{"type": "agent_contribution", "agent": "claude-sonnet-4-6",
                   "person": "_claude", "ref": "commit/x/agent/claude-sonnet-4-6"}],
        contributors=[{"person": "alice", "cw": 1.0}],
    )
    result = ai_attribution(edpa, "PI-2026-1.1")
    json_file = edpa / "reports" / "iteration-PI-2026-1.1" / "ai_attribution.json"
    md_file = edpa / "reports" / "iteration-PI-2026-1.1" / "ai-attribution-PI-2026-1.1.md"
    assert json_file.exists()
    assert md_file.exists()
    loaded = json.loads(json_file.read_text(encoding="utf-8"))
    assert loaded["summary"]["ai_assisted_items"] == result["summary"]["ai_assisted_items"]
