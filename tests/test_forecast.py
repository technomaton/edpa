"""Tests for forecast.py — Monte-Carlo PI completion forecast."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

from forecast import (  # noqa: E402
    forecast_pi,
    load_pi_state,
    load_velocity_history,
    percentile,
    run_monte_carlo,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ITER_YAML = """\
iteration:
  id: {id}
  pi: {pi}
  start_date: 2026-04-06
  end_date: 2026-04-13
  status: {status}
delivery:
  delivered_sp: {sp}
  velocity: {sp}
"""

PI_YAML = """\
pi:
  id: {pi}
  status: active
"""

STORY_MD = """\
---
id: {id}
type: Story
parent: F-100
js: {js}
status: {status}
iteration: {iteration}
---
"""


def _write_iteration(edpa_root, it_id, pi, status, sp):
    (edpa_root / "iterations").mkdir(parents=True, exist_ok=True)
    f = edpa_root / "iterations" / f"{it_id}.yaml"
    f.write_text(ITER_YAML.format(id=it_id, pi=pi, status=status, sp=sp), encoding="utf-8")


def _write_pi(edpa_root, pi_id):
    (edpa_root / "iterations").mkdir(parents=True, exist_ok=True)
    f = edpa_root / "iterations" / f"{pi_id}.yaml"
    f.write_text(PI_YAML.format(pi=pi_id), encoding="utf-8")


def _write_story(edpa_root, sid, js, status, iteration):
    d = edpa_root / "backlog" / "stories"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sid}.md").write_text(
        STORY_MD.format(id=sid, js=js, status=status, iteration=iteration),
        encoding="utf-8",
    )


@pytest.fixture
def edpa_root(tmp_path):
    root = tmp_path / ".edpa"
    root.mkdir()
    return root


# ---------------------------------------------------------------------------
# percentile()
# ---------------------------------------------------------------------------

def test_percentile_median():
    vals = list(range(1, 101))  # 1..100
    assert percentile(vals, 50) == pytest.approx(50.5)


def test_percentile_empty():
    assert percentile([], 50) == 0.0


def test_percentile_single():
    assert percentile([42.0], 80) == 42.0


# ---------------------------------------------------------------------------
# run_monte_carlo()
# ---------------------------------------------------------------------------

def test_mc_returns_sorted(edpa_root):
    totals = run_monte_carlo(30.0, 5.0, 3, simulations=200, seed=42)
    assert totals == sorted(totals)
    assert len(totals) == 200


def test_mc_zero_remaining_iterations():
    totals = run_monte_carlo(30.0, 5.0, 0, simulations=100, seed=1)
    assert all(t == 0.0 for t in totals)


def test_mc_no_negative_totals():
    # With very high std dev, individual samples could be negative — totals must not be.
    totals = run_monte_carlo(5.0, 100.0, 2, simulations=500, seed=7)
    assert all(t >= 0.0 for t in totals)


def test_mc_deterministic_with_seed():
    a = run_monte_carlo(25.0, 4.0, 2, simulations=50, seed=99)
    b = run_monte_carlo(25.0, 4.0, 2, simulations=50, seed=99)
    assert a == b


# ---------------------------------------------------------------------------
# load_velocity_history()
# ---------------------------------------------------------------------------

def test_load_velocity_history_returns_last_window(edpa_root):
    _write_iteration(edpa_root, "PI-2026-1.1", "PI-2026-1", "closed", 20)
    _write_iteration(edpa_root, "PI-2026-1.2", "PI-2026-1", "closed", 30)
    _write_iteration(edpa_root, "PI-2026-1.3", "PI-2026-1", "closed", 40)
    _write_iteration(edpa_root, "PI-2026-1.4", "PI-2026-1", "closed", 50)
    vels = load_velocity_history(edpa_root, window=3)
    assert vels == [30.0, 40.0, 50.0]


def test_load_velocity_history_skips_open(edpa_root):
    _write_iteration(edpa_root, "PI-2026-1.1", "PI-2026-1", "closed", 25)
    _write_iteration(edpa_root, "PI-2026-1.2", "PI-2026-1", "active", 0)
    vels = load_velocity_history(edpa_root, window=5)
    assert vels == [25.0]


def test_load_velocity_history_skips_pi_level_file(edpa_root):
    _write_pi(edpa_root, "PI-2026-1")
    _write_iteration(edpa_root, "PI-2026-1.1", "PI-2026-1", "closed", 20)
    vels = load_velocity_history(edpa_root, window=5)
    assert len(vels) == 1


def test_load_velocity_history_empty(edpa_root):
    assert load_velocity_history(edpa_root, window=3) == []


# ---------------------------------------------------------------------------
# load_pi_state()
# ---------------------------------------------------------------------------

def test_load_pi_state_basic(edpa_root):
    _write_iteration(edpa_root, "PI-2026-2.1", "PI-2026-2", "closed", 30)
    _write_iteration(edpa_root, "PI-2026-2.2", "PI-2026-2", "active", 0)
    _write_iteration(edpa_root, "PI-2026-2.3", "PI-2026-2", "planned", 0)
    _write_story(edpa_root, "S-300", 5, "Implementing", "PI-2026-2.2")
    _write_story(edpa_root, "S-301", 8, "Backlog", "PI-2026-2.3")
    _write_story(edpa_root, "S-302", 3, "Done", "PI-2026-2.2")

    state = load_pi_state(edpa_root, "PI-2026-2")
    assert state["pi_exists"]
    assert state["total_iterations"] == 3
    assert state["closed_iterations"] == 1
    assert state["remaining_iterations"] == 2
    assert state["remaining_sp"] == 5 + 8  # S-302 is Done, excluded


def test_load_pi_state_unknown_pi(edpa_root):
    _write_iteration(edpa_root, "PI-2026-1.1", "PI-2026-1", "closed", 20)
    state = load_pi_state(edpa_root, "PI-2099-9")
    assert not state["pi_exists"]
    assert state["remaining_sp"] == 0


# ---------------------------------------------------------------------------
# forecast_pi() — integration
# ---------------------------------------------------------------------------

@pytest.fixture
def rich_edpa(edpa_root):
    """3 closed iterations (PI-1) + 1 active + 1 planned in PI-2."""
    for i, sp in enumerate([20, 25, 22], start=1):
        _write_iteration(edpa_root, f"PI-2026-1.{i}", "PI-2026-1", "closed", sp)
    _write_iteration(edpa_root, "PI-2026-2.1", "PI-2026-2", "active", 0)
    _write_iteration(edpa_root, "PI-2026-2.2", "PI-2026-2", "planned", 0)
    _write_story(edpa_root, "S-10", 8, "Implementing", "PI-2026-2.1")
    _write_story(edpa_root, "S-11", 5, "Backlog", "PI-2026-2.2")
    return edpa_root


def test_forecast_result_keys(rich_edpa):
    result = forecast_pi(rich_edpa, "PI-2026-2", window=3, simulations=200, seed=0)
    for key in ("pi", "p20", "p50", "p80", "completion_probability", "recommendation",
                "velocity_mean", "velocity_std", "remaining_sp", "remaining_iterations"):
        assert key in result, f"missing key: {key}"


def test_forecast_bands_ordering(rich_edpa):
    result = forecast_pi(rich_edpa, "PI-2026-2", window=3, simulations=500, seed=1)
    assert result["p20"] <= result["p50"] <= result["p80"]


def test_forecast_completion_probability_range(rich_edpa):
    result = forecast_pi(rich_edpa, "PI-2026-2", window=3, simulations=500, seed=2)
    assert 0.0 <= result["completion_probability"] <= 100.0


def test_forecast_too_few_iterations_raises(edpa_root):
    _write_iteration(edpa_root, "PI-2026-1.1", "PI-2026-1", "closed", 20)
    _write_iteration(edpa_root, "PI-2026-2.1", "PI-2026-2", "planned", 0)
    with pytest.raises(ValueError, match="at least 2"):
        forecast_pi(edpa_root, "PI-2026-2", window=3)


def test_forecast_unknown_pi_raises(edpa_root):
    _write_iteration(edpa_root, "PI-2026-1.1", "PI-2026-1", "closed", 20)
    _write_iteration(edpa_root, "PI-2026-1.2", "PI-2026-1", "closed", 25)
    with pytest.raises(ValueError, match="no iterations"):
        forecast_pi(edpa_root, "PI-2099-9", window=2)


def test_forecast_no_remaining_work(edpa_root):
    for i, sp in enumerate([20, 25], start=1):
        _write_iteration(edpa_root, f"PI-2026-1.{i}", "PI-2026-1", "closed", sp)
    _write_iteration(edpa_root, "PI-2026-2.1", "PI-2026-2", "planned", 0)
    # All items Done → remaining_sp == 0
    _write_story(edpa_root, "S-1", 5, "Done", "PI-2026-2.1")
    result = forecast_pi(edpa_root, "PI-2026-2", window=2, simulations=100, seed=3)
    assert result["remaining_sp"] == 0
