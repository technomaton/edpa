"""Tests for pi_metrics.py — PI predictability & confidence trending."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

from pi_metrics import (  # noqa: E402
    _confidence_avg,
    _confidence_votes,
    _is_iteration_file,
    _objective_counts,
    build_report,
    compute_pi_metrics,
    load_pi_iterations,
    load_pi_list,
    load_pi_objectives,
    pi_metrics,
    render_md,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PI_YAML = """\
pi:
  id: {pi_id}
  status: {status}
  start_date: 2026-04-06
  end_date: 2026-05-08
"""

ITER_YAML = """\
iteration:
  id: {it_id}
  pi: {pi_id}
  status: {status}
  start_date: 2026-04-06
  end_date: 2026-04-10
planning:
  planned_sp: {planned_sp}
delivery:
  delivered_sp: {delivered_sp}
"""

OBJ_YAML = """\
pi: PI-2026-1
teams:
  Alpha:
    committed:
      - title: "Feature A"
        bv: 8
        status: done
      - title: "Feature B"
        bv: 5
        status: in_progress
    confidence: 4
  Beta:
    committed:
      - title: "Feature C"
        bv: 7
        status: done
    stretch:
      - title: "Nice to have"
        bv: 3
        status: not_started
    confidence: 3
"""

STORY_MD = """\
---
id: {sid}
type: Story
js: {js}
status: {status}
iteration: {iteration}
parent: F-1
---
"""


def _write_pi(edpa_root, pi_id, status="active"):
    (edpa_root / "iterations").mkdir(parents=True, exist_ok=True)
    f = edpa_root / "iterations" / f"{pi_id}.yaml"
    f.write_text(PI_YAML.format(pi_id=pi_id, status=status), encoding="utf-8")


def _write_iter(edpa_root, it_id, pi_id, status, planned_sp, delivered_sp):
    (edpa_root / "iterations").mkdir(parents=True, exist_ok=True)
    f = edpa_root / "iterations" / f"{it_id}.yaml"
    f.write_text(
        ITER_YAML.format(
            it_id=it_id, pi_id=pi_id, status=status,
            planned_sp=planned_sp, delivered_sp=delivered_sp,
        ),
        encoding="utf-8",
    )


def _write_obj(edpa_root, pi_id, content=OBJ_YAML):
    (edpa_root / "pi-objectives").mkdir(parents=True, exist_ok=True)
    f = edpa_root / "pi-objectives" / f"{pi_id}.yaml"
    f.write_text(content, encoding="utf-8")


def _write_story(edpa_root, sid, js, status, iteration):
    d = edpa_root / "backlog" / "stories"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sid}.md").write_text(
        STORY_MD.format(sid=sid, js=js, status=status, iteration=iteration),
        encoding="utf-8",
    )


@pytest.fixture
def edpa_root(tmp_path):
    root = tmp_path / ".edpa"
    root.mkdir()
    return root


@pytest.fixture
def populated(edpa_root):
    """One closed PI (3 iters) + one active PI (2 iters)."""
    _write_pi(edpa_root, "PI-2026-1", status="closed")
    _write_iter(edpa_root, "PI-2026-1.1", "PI-2026-1", "closed", 20, 20)
    _write_iter(edpa_root, "PI-2026-1.2", "PI-2026-1", "closed", 25, 22)
    _write_iter(edpa_root, "PI-2026-1.3", "PI-2026-1", "closed", 30, 28)
    _write_obj(edpa_root, "PI-2026-1")

    _write_pi(edpa_root, "PI-2026-2", status="active")
    _write_iter(edpa_root, "PI-2026-2.1", "PI-2026-2", "active", 20, 0)
    _write_iter(edpa_root, "PI-2026-2.2", "PI-2026-2", "planned", 20, 0)
    return edpa_root


# ---------------------------------------------------------------------------
# Unit helpers
# ---------------------------------------------------------------------------

def test_is_iteration_file_yes():
    assert _is_iteration_file("PI-2026-1.1")


def test_is_iteration_file_no():
    assert not _is_iteration_file("PI-2026-1")


def test_confidence_avg_basic():
    obj = {"teams": {"A": {"confidence": 4}, "B": {"confidence": 3}}}
    assert _confidence_avg(obj) == pytest.approx(3.5)


def test_confidence_avg_empty():
    assert _confidence_avg({}) is None


def test_confidence_votes():
    obj = {"teams": {"A": {"confidence": 4}, "B": {"confidence": 2}}}
    assert _confidence_votes(obj) == {"A": 4, "B": 2}


def test_objective_counts():
    import yaml
    obj = yaml.safe_load(OBJ_YAML)
    total, done = _objective_counts(obj)
    assert total == 3   # A.committed (2) + B.committed (1); stretch excluded
    assert done == 2    # Feature A (done) + Feature C (done)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def test_load_pi_list(populated):
    pis = load_pi_list(populated)
    assert len(pis) == 2
    assert pis[0]["id"] == "PI-2026-1"
    assert pis[1]["id"] == "PI-2026-2"


def test_load_pi_list_empty(edpa_root):
    assert load_pi_list(edpa_root) == []


def test_load_pi_iterations(populated):
    iters = load_pi_iterations(populated, "PI-2026-1")
    assert len(iters) == 3
    assert iters[0]["id"] == "PI-2026-1.1"
    assert iters[2]["id"] == "PI-2026-1.3"


def test_load_pi_iterations_unknown(populated):
    assert load_pi_iterations(populated, "PI-2099-9") == []


def test_load_pi_objectives_present(populated):
    obj = load_pi_objectives(populated, "PI-2026-1")
    assert "teams" in obj


def test_load_pi_objectives_missing(populated):
    assert load_pi_objectives(populated, "PI-2026-2") == {}


# ---------------------------------------------------------------------------
# compute_pi_metrics
# ---------------------------------------------------------------------------

def test_compute_metrics_basic(populated):
    import yaml
    pi_block = yaml.safe_load((populated / "iterations" / "PI-2026-1.yaml").read_text())["pi"]
    m = compute_pi_metrics(populated, pi_block)

    assert m["pi"] == "PI-2026-1"
    assert m["iterations_total"] == 3
    assert m["iterations_closed"] == 3
    assert m["planned_sp"] == 20 + 25 + 30
    assert m["delivered_sp"] == 20 + 22 + 28
    assert m["predictability_pct"] == pytest.approx(70 / 75 * 100, rel=1e-3)
    assert m["avg_velocity"] == pytest.approx(23.3, abs=0.05)
    assert m["confidence_avg"] == pytest.approx(3.5)
    assert m["confidence_votes"] == {"Alpha": 4, "Beta": 3}
    assert m["objectives_committed"] == 3
    assert m["objectives_done"] == 2


def test_compute_metrics_no_objectives(populated):
    import yaml
    pi_block = yaml.safe_load((populated / "iterations" / "PI-2026-2.yaml").read_text())["pi"]
    m = compute_pi_metrics(populated, pi_block)
    assert m["confidence_avg"] is None
    assert m["confidence_votes"] == {}


def test_compute_metrics_sp_fallback_to_rollup(edpa_root):
    """When iteration YAML has no planned/delivered SP, derive from backlog items."""
    _write_pi(edpa_root, "PI-2026-1", status="active")
    _write_iter(edpa_root, "PI-2026-1.1", "PI-2026-1", "closed", 0, 0)  # no SP in YAML
    _write_story(edpa_root, "S-1", 8, "Done", "PI-2026-1.1")
    _write_story(edpa_root, "S-2", 5, "Implementing", "PI-2026-1.1")

    import yaml
    pi_block = yaml.safe_load((edpa_root / "iterations" / "PI-2026-1.yaml").read_text())["pi"]
    m = compute_pi_metrics(edpa_root, pi_block)
    assert m["planned_sp"] == 13   # S-1 + S-2
    assert m["delivered_sp"] == 8  # only Done


# ---------------------------------------------------------------------------
# build_report / render_md
# ---------------------------------------------------------------------------

def test_build_report_keys(populated):
    r = build_report(populated)
    assert "generated_at" in r
    assert "pis" in r
    assert len(r["pis"]) == 2


def test_build_report_window(populated):
    r = build_report(populated, window=1)
    assert len(r["pis"]) == 1
    assert r["pis"][0]["pi"] == "PI-2026-2"  # last 1 PI


def test_build_report_pi_filter(populated):
    r = build_report(populated, pi_filter="PI-2026-1")
    assert len(r["pis"]) == 1
    assert r["pis"][0]["pi"] == "PI-2026-1"


def test_render_md_contains_table(populated):
    r = build_report(populated)
    md = render_md(r)
    assert "PI-2026-1" in md
    assert "Predictability" in md
    assert "Confidence" in md


def test_render_md_empty():
    assert "No PI data" in render_md({"pis": []})


def test_render_md_confidence_votes_section(populated):
    r = build_report(populated, pi_filter="PI-2026-1")
    md = render_md(r)
    assert "Alpha" in md or "Beta" in md  # team names appear in votes table


# ---------------------------------------------------------------------------
# pi_metrics (integration — writes files)
# ---------------------------------------------------------------------------

def test_pi_metrics_writes_files(populated):
    result = pi_metrics(populated)
    assert (populated / "reports" / "pi-metrics.json").exists()
    assert (populated / "reports" / "pi-metrics.md").exists()
    loaded = json.loads((populated / "reports" / "pi-metrics.json").read_text())
    assert loaded["pis"]


def test_pi_metrics_json_parseable(populated):
    result = pi_metrics(populated)
    # Verify JSON is well-formed by checking round-trip
    json_path = populated / "reports" / "pi-metrics.json"
    data = json.loads(json_path.read_text())
    assert isinstance(data["pis"], list)
    for m in data["pis"]:
        assert "pi" in m
        assert "predictability_pct" in m
