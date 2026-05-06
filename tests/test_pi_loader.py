"""Tests for plugin/edpa/scripts/_pi_loader.py.

Covers happy-path reconstruction plus every diagnostic code:
weeks mismatch, date gaps/overlaps, inverted/missing dates,
missing PI yaml, PI bounds mismatch, weekend bridging.

Run: python -m pytest tests/test_pi_loader.py -v
"""

import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

from _pi_loader import (  # noqa: E402
    _derived_weeks,
    _is_weekend_bridge,
    _pi_status_from_iterations,
    derive_pis,
    find_active_pi,
    split_diagnostics,
)


def write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def make_iter(it_id: str, start: str, end: str, *, status: str = "closed",
              weeks: int | None = None, pi: str | None = None,
              type_: str | None = None) -> dict:
    iteration: dict = {
        "id": it_id,
        "pi": pi or it_id.rsplit(".", 1)[0],
        "start_date": start,
        "end_date": end,
        "status": status,
    }
    if weeks is not None:
        iteration["weeks"] = weeks
    if type_:
        iteration["type"] = type_
    return {"iteration": iteration}


def make_pi(pi_id: str, *, status: str = "active", iteration_weeks: int = 1,
            pi_iterations: int = 5, start: str | None = None,
            end: str | None = None) -> dict:
    pi: dict = {
        "id": pi_id,
        "status": status,
        "iteration_weeks": iteration_weeks,
        "pi_iterations": pi_iterations,
    }
    if start: pi["start_date"] = start
    if end: pi["end_date"] = end
    return {"pi": pi}


# --- pure helpers ----------------------------------------------------------

def test_derived_weeks_full_calendar_week():
    assert _derived_weeks(date(2026, 4, 6), date(2026, 4, 12)) == 1   # Mon-Sun = 7d


def test_derived_weeks_business_week():
    assert _derived_weeks(date(2026, 4, 6), date(2026, 4, 10)) == 1   # Mon-Fri = 5d


def test_derived_weeks_two_weeks_business():
    assert _derived_weeks(date(2026, 4, 6), date(2026, 4, 17)) == 2   # 12d → round(12/7)=2


def test_derived_weeks_floors_at_one():
    assert _derived_weeks(date(2026, 4, 6), date(2026, 4, 6)) == 1   # 1d → max(1, 0)


def test_pi_status_from_iterations_picks_active():
    assert _pi_status_from_iterations([{"status": "closed"}, {"status": "active"}]) == "active"


def test_pi_status_from_iterations_all_closed():
    assert _pi_status_from_iterations([{"status": "closed"}, {"status": "closed"}]) == "closed"


def test_pi_status_from_iterations_planning():
    assert _pi_status_from_iterations([{"status": "planned"}]) == "planning"


def test_pi_status_from_iterations_empty():
    assert _pi_status_from_iterations([]) == "planning"


def test_is_weekend_bridge_friday_to_monday():
    # Friday 2026-04-17 → Monday 2026-04-20: gap days = Sat 18, Sun 19 (2 days)
    assert _is_weekend_bridge(date(2026, 4, 20), 2)


def test_is_weekend_bridge_rejects_weekday():
    # Tuesday → Monday: includes weekday Wednesday, Thursday, Friday
    assert not _is_weekend_bridge(date(2026, 4, 13), 5)


# --- happy path ------------------------------------------------------------

def test_happy_path_single_pi(tmp_path):
    iter_dir = tmp_path / "iterations"
    write_yaml(iter_dir / "PI-2026-1.yaml",
               make_pi("PI-2026-1", status="active", iteration_weeks=2,
                       pi_iterations=3, start="2026-04-06", end="2026-05-15"))
    write_yaml(iter_dir / "PI-2026-1.1.yaml",
               make_iter("PI-2026-1.1", "2026-04-06", "2026-04-17",
                         status="closed", weeks=2))
    write_yaml(iter_dir / "PI-2026-1.2.yaml",
               make_iter("PI-2026-1.2", "2026-04-20", "2026-05-01",
                         status="closed", weeks=2))
    write_yaml(iter_dir / "PI-2026-1.3.yaml",
               make_iter("PI-2026-1.3", "2026-05-04", "2026-05-15",
                         status="active", weeks=2))

    pis, diags = derive_pis(tmp_path)

    assert diags == [], f"expected no diagnostics, got {diags}"
    assert len(pis) == 1
    pi = pis[0]
    assert pi["id"] == "PI-2026-1"
    assert pi["status"] == "active"
    assert pi["iteration_weeks"] == 2
    assert pi["pi_iterations"] == 3
    assert pi["start_date"] == "2026-04-06"
    assert pi["end_date"] == "2026-05-15"
    assert len(pi["iterations"]) == 3
    assert pi["iterations"][0]["id"] == "PI-2026-1.1"
    assert pi["iterations"][0]["weeks"] == 2
    assert pi["iterations"][2]["status"] == "active"


def test_iteration_weeks_derived_when_omitted(tmp_path):
    iter_dir = tmp_path / "iterations"
    write_yaml(iter_dir / "PI-2026-1.yaml", make_pi("PI-2026-1"))
    write_yaml(iter_dir / "PI-2026-1.1.yaml",
               make_iter("PI-2026-1.1", "2026-04-06", "2026-04-10"))   # no weeks field

    pis, diags = derive_pis(tmp_path)
    assert pis[0]["iterations"][0]["weeks"] == 1
    assert all(d["severity"] != "error" for d in diags)


def test_type_field_preserved(tmp_path):
    iter_dir = tmp_path / "iterations"
    write_yaml(iter_dir / "PI-2026-1.yaml", make_pi("PI-2026-1"))
    write_yaml(iter_dir / "PI-2026-1.5.yaml",
               make_iter("PI-2026-1.5", "2026-06-01", "2026-06-12",
                         status="planned", type_="IP"))
    pis, _ = derive_pis(tmp_path)
    assert pis[0]["iterations"][0]["type"] == "IP"


def test_multi_pi_sorted(tmp_path):
    iter_dir = tmp_path / "iterations"
    write_yaml(iter_dir / "PI-2026-2.yaml",
               make_pi("PI-2026-2", status="planning"))
    write_yaml(iter_dir / "PI-2026-1.yaml",
               make_pi("PI-2026-1", status="closed"))
    pis, _ = derive_pis(tmp_path)
    assert [p["id"] for p in pis] == ["PI-2026-1", "PI-2026-2"]


# --- diagnostics: errors ---------------------------------------------------

def test_weeks_mismatch_emits_error(tmp_path):
    iter_dir = tmp_path / "iterations"
    write_yaml(iter_dir / "PI-2026-1.yaml", make_pi("PI-2026-1"))
    write_yaml(iter_dir / "PI-2026-1.1.yaml",
               make_iter("PI-2026-1.1", "2026-04-06", "2026-04-10", weeks=2))   # 5d but says 2w

    _, diags = derive_pis(tmp_path)
    errors, _ = split_diagnostics(diags)
    assert any(d["code"] == "weeks_mismatch" for d in errors)


def test_date_overlap_emits_error(tmp_path):
    iter_dir = tmp_path / "iterations"
    write_yaml(iter_dir / "PI-2026-1.yaml", make_pi("PI-2026-1"))
    write_yaml(iter_dir / "PI-2026-1.1.yaml",
               make_iter("PI-2026-1.1", "2026-04-06", "2026-04-17"))
    write_yaml(iter_dir / "PI-2026-1.2.yaml",
               make_iter("PI-2026-1.2", "2026-04-15", "2026-05-01"))   # overlaps prev

    _, diags = derive_pis(tmp_path)
    errors, _ = split_diagnostics(diags)
    assert any(d["code"] == "date_overlap" for d in errors)


def test_inverted_dates_emits_error(tmp_path):
    iter_dir = tmp_path / "iterations"
    write_yaml(iter_dir / "PI-2026-1.1.yaml",
               make_iter("PI-2026-1.1", "2026-04-17", "2026-04-06"))   # end before start
    _, diags = derive_pis(tmp_path)
    errors, _ = split_diagnostics(diags)
    assert any(d["code"] == "inverted_dates" for d in errors)


def test_missing_dates_emits_error(tmp_path):
    iter_dir = tmp_path / "iterations"
    write_yaml(iter_dir / "PI-2026-1.1.yaml",
               {"iteration": {"id": "PI-2026-1.1", "status": "planned"}})
    _, diags = derive_pis(tmp_path)
    errors, _ = split_diagnostics(diags)
    assert any(d["code"] == "missing_dates" for d in errors)


def test_missing_id_emits_error(tmp_path):
    iter_dir = tmp_path / "iterations"
    write_yaml(iter_dir / "PI-2026-1.1.yaml",
               {"iteration": {"start_date": "2026-04-06", "end_date": "2026-04-10"}})
    _, diags = derive_pis(tmp_path)
    errors, _ = split_diagnostics(diags)
    assert any(d["code"] == "missing_id" for d in errors)


# --- diagnostics: warnings -------------------------------------------------

def test_date_gap_emits_warning(tmp_path):
    iter_dir = tmp_path / "iterations"
    write_yaml(iter_dir / "PI-2026-1.yaml", make_pi("PI-2026-1"))
    write_yaml(iter_dir / "PI-2026-1.1.yaml",
               make_iter("PI-2026-1.1", "2026-04-06", "2026-04-10"))   # ends Friday
    write_yaml(iter_dir / "PI-2026-1.2.yaml",
               make_iter("PI-2026-1.2", "2026-04-20", "2026-04-24"))   # starts NEXT Monday (full week gap)

    _, diags = derive_pis(tmp_path)
    _, warnings = split_diagnostics(diags)
    assert any(d["code"] == "date_gap" for d in warnings)


def test_friday_to_monday_no_gap(tmp_path):
    iter_dir = tmp_path / "iterations"
    write_yaml(iter_dir / "PI-2026-1.yaml", make_pi("PI-2026-1"))
    write_yaml(iter_dir / "PI-2026-1.1.yaml",
               make_iter("PI-2026-1.1", "2026-04-06", "2026-04-17"))   # ends Friday
    write_yaml(iter_dir / "PI-2026-1.2.yaml",
               make_iter("PI-2026-1.2", "2026-04-20", "2026-05-01"))   # starts Monday

    _, diags = derive_pis(tmp_path)
    assert not any(d["code"] == "date_gap" for d in diags), \
        f"weekend bridge should not warn, got {diags}"


def test_missing_pi_yaml_emits_warning(tmp_path):
    iter_dir = tmp_path / "iterations"
    write_yaml(iter_dir / "PI-2026-1.1.yaml",
               make_iter("PI-2026-1.1", "2026-04-06", "2026-04-10"))
    pis, diags = derive_pis(tmp_path)
    _, warnings = split_diagnostics(diags)
    assert any(d["code"] == "missing_pi_yaml" for d in warnings)
    assert pis[0]["id"] == "PI-2026-1"   # still reconstructed


def test_pi_bounds_mismatch_warning(tmp_path):
    iter_dir = tmp_path / "iterations"
    write_yaml(iter_dir / "PI-2026-1.yaml",
               make_pi("PI-2026-1", start="2026-04-01", end="2026-05-15"))   # PI claims earlier start
    write_yaml(iter_dir / "PI-2026-1.1.yaml",
               make_iter("PI-2026-1.1", "2026-04-06", "2026-04-17"))
    write_yaml(iter_dir / "PI-2026-1.2.yaml",
               make_iter("PI-2026-1.2", "2026-04-20", "2026-05-15"))

    _, diags = derive_pis(tmp_path)
    _, warnings = split_diagnostics(diags)
    assert any(d["code"] == "pi_start_mismatch" for d in warnings)


# --- edge cases ------------------------------------------------------------

def test_no_iterations_dir(tmp_path):
    pis, diags = derive_pis(tmp_path)
    assert pis == []
    assert diags == []


def test_empty_iterations_dir(tmp_path):
    (tmp_path / "iterations").mkdir()
    pis, diags = derive_pis(tmp_path)
    assert pis == []
    assert diags == []


def test_unrecognized_filenames_skipped(tmp_path):
    iter_dir = tmp_path / "iterations"
    iter_dir.mkdir()
    (iter_dir / "CHANGELOG.yaml").write_text("notes: hello\n")
    write_yaml(iter_dir / "PI-2026-1.1.yaml",
               make_iter("PI-2026-1.1", "2026-04-06", "2026-04-10"))
    pis, diags = derive_pis(tmp_path)
    assert len(pis) == 1
    assert all(d["code"] != "missing_id" for d in diags)


def test_find_active_pi_picks_active():
    pis = [{"id": "A", "status": "closed"}, {"id": "B", "status": "active"}]
    assert find_active_pi(pis)["id"] == "B"


def test_find_active_pi_falls_back_to_first():
    pis = [{"id": "A", "status": "closed"}, {"id": "B", "status": "planning"}]
    assert find_active_pi(pis)["id"] == "A"


def test_find_active_pi_handles_empty():
    assert find_active_pi([]) == {}


def test_loader_injection(tmp_path):
    """Custom loader can replace yaml.safe_load — useful for sandboxing."""
    (tmp_path / "iterations").mkdir()
    (tmp_path / "iterations" / "PI-2026-1.1.yaml").touch()

    def fake_loader(_path):
        return {"iteration": {"id": "PI-2026-1.1", "start_date": "2026-04-06",
                              "end_date": "2026-04-10", "status": "closed"}}

    pis, _ = derive_pis(tmp_path, loader=fake_loader)
    assert pis[0]["iterations"][0]["id"] == "PI-2026-1.1"
