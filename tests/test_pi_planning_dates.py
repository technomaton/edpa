"""Regression tests for PI-calendar multi-year date handling (S-244).

The PI calendar collapsed every PI onto the current year because
`pi_planning.load_pis` emitted only the pretty `D.M.` date string (year
dropped), and the calendar's parser fell back to the current year. The fix
adds authoritative ISO `start_date`/`end_date` fields the calendar uses for
year-safe date math, while the pretty `dates` string stays for display.

These tests pin both halves: the ISO fields carry the year, and `dates`
still drops it (so the 4 display consumers are unaffected).
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import pi_planning as pp  # noqa: E402


def test_iso_date_carries_year_from_date_obj():
    assert pp._iso_date(datetime.date(2027, 1, 5)) == "2027-01-05"
    assert pp._iso_date(datetime.datetime(2026, 12, 31, 0, 0)) == "2026-12-31"


def test_iso_date_carries_year_from_iso_string():
    assert pp._iso_date("2027-03-15") == "2027-03-15"
    assert pp._iso_date("2027-03-15T00:00:00") == "2027-03-15"


def test_iso_date_empty_on_missing_or_bad():
    assert pp._iso_date(None) == ""
    assert pp._iso_date("") == ""
    assert pp._iso_date("5.1.") == ""  # the year-less pretty form is not ISO


def test_pretty_dates_still_drop_year():
    # The 4 display consumers expect `D.M.–D.M.`; do not regress them to ISO.
    assert pp.format_iteration_dates("2027-01-04", "2027-01-08") == "4.1.–8.1."


def _write_iter(itdir: Path, iid: str, pid: str, start: str, end: str, status: str):
    (itdir / f"{iid}.yaml").write_text(
        f"iteration:\n  id: {iid}\n  pi: {pid}\n"
        f"  start_date: {start}\n  end_date: {end}\n  status: {status}\n",
        encoding="utf-8",
    )


def test_load_pis_emits_year_safe_iso_across_years(tmp_path: Path):
    """A 2026 + 2027 PI set must keep each iteration on its own year."""
    itdir = tmp_path / ".edpa" / "iterations"
    itdir.mkdir(parents=True)
    (itdir / "PI-2026-1.yaml").write_text(
        "pi:\n  id: PI-2026-1\n  status: closed\n  pi_iterations: 1\n", encoding="utf-8")
    _write_iter(itdir, "PI-2026-1.1", "PI-2026-1", "2026-01-05", "2026-01-09", "closed")
    (itdir / "PI-2027-1.yaml").write_text(
        "pi:\n  id: PI-2027-1\n  status: planning\n  pi_iterations: 1\n", encoding="utf-8")
    _write_iter(itdir, "PI-2027-1.1", "PI-2027-1", "2027-01-04", "2027-01-08", "planned")

    pis = {pi["id"]: pi for pi in pp.load_pis(tmp_path)}
    it26 = pis["PI-2026-1"]["iterations"][0]
    it27 = pis["PI-2027-1"]["iterations"][0]

    assert it26["start_date"] == "2026-01-05" and it26["end_date"] == "2026-01-09"
    assert it27["start_date"] == "2027-01-04" and it27["end_date"] == "2027-01-08"
    # Pretty form is identical across years (the bug's root) — proves the ISO
    # fields, not `dates`, are what disambiguate the year.
    assert it26["dates"] == "5.1.–9.1." and it27["dates"] == "4.1.–8.1."
