"""D3 — property-based tests for engine core invariants.

Uses Hypothesis to generate random but valid inputs and verify that the
engine's mathematical guarantees hold for all of them:

  1. Σ derived hours == capacity  (for persons with items, within 0.1 h)
  2. All hours ≥ 0
  3. Σ ratios == 1.0              (for persons with items, within 0.001)
  4. _resolve_capacity always returns non-negative capacity
  5. Engine is deterministic (same input → same output)
  6. Capacity override is respected
  7. Zero-item persons get derived == 0
  8. Single-item person gets all capacity
  9. Two-item person: hours sum to capacity regardless of JS split

run_edpa result shape (per person):
  { "id", "name", "role", "capacity", "total_derived", "items": [...],
    "invariant_ok", ... }
Each item: { "id", "js", "cw", "score", "ratio", "hours", ... }

_resolve_capacity(person, override) → (effective, baseline, override_meta)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

hypothesis = pytest.importorskip("hypothesis", reason="hypothesis not installed")

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from engine import run_edpa, _resolve_capacity  # noqa: E402


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

@st.composite
def item_with_contributors(draw, person_ids: list[str]):
    """One backlog item with JS ≥ 1 and CW contributors that sum to 1.0."""
    iid = f"S-{draw(st.integers(1, 9999))}"
    js = draw(st.integers(1, 100))
    n = draw(st.integers(1, min(3, len(person_ids))))
    persons = draw(st.lists(
        st.sampled_from(person_ids), min_size=n, max_size=n, unique=True,
    ))
    raw = draw(st.lists(
        st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
        min_size=n, max_size=n,
    ))
    total = sum(raw)
    contributors = [
        {"person": p, "cw": round(w / total, 6), "signals": []}
        for p, w in zip(persons, raw)
    ]
    return {"id": iid, "job_size": js, "contributors": contributors, "status": "Done"}


@st.composite
def capacity_and_items(draw):
    """Generate (capacity_config, items) with consistent person IDs."""
    n_people = draw(st.integers(1, 5))
    capacities = draw(st.lists(
        st.floats(min_value=1.0, max_value=200.0, allow_nan=False, allow_infinity=False),
        min_size=n_people, max_size=n_people,
    ))
    people = [
        {"id": f"p{i}", "name": f"Person {i}", "capacity_per_iteration": c}
        for i, c in enumerate(capacities)
    ]
    person_ids = [p["id"] for p in people]
    capacity_config = {"people": people}

    raw_items = draw(st.lists(
        item_with_contributors(person_ids),
        min_size=1, max_size=10,
    ))
    # Deduplicate item IDs
    seen: set[str] = set()
    items = []
    for item in raw_items:
        if item["id"] not in seen:
            seen.add(item["id"])
            items.append(item)
    assume(len(items) >= 1)

    return capacity_config, items


# ---------------------------------------------------------------------------
# Core invariants
# ---------------------------------------------------------------------------

@given(capacity_and_items())
@settings(max_examples=200, deadline=5000)
def test_derived_equals_capacity(args):
    """Σ derived hours == capacity for every person with items."""
    capacity_config, items = args
    results = run_edpa(capacity_config, {}, items)
    for r in results:
        if r["items"]:
            assert abs(r["total_derived"] - r["capacity"]) <= 0.11, (
                f"{r['id']}: derived={r['total_derived']} != capacity={r['capacity']}"
            )


@given(capacity_and_items())
@settings(max_examples=200, deadline=5000)
def test_no_negative_hours(args):
    """No person item has negative hours."""
    capacity_config, items = args
    results = run_edpa(capacity_config, {}, items)
    for r in results:
        for item in r["items"]:
            assert item["hours"] >= -0.01, (
                f"{r['id']}/{item['id']}: hours={item['hours']} < 0"
            )


@given(capacity_and_items())
@settings(max_examples=200, deadline=5000)
def test_ratio_sum_is_one(args):
    """Σ ratios == 1.0 for every person with items."""
    capacity_config, items = args
    results = run_edpa(capacity_config, {}, items)
    for r in results:
        if r["items"]:
            ratio_sum = sum(i["ratio"] for i in r["items"])
            assert abs(ratio_sum - 1.0) <= 0.002, (
                f"{r['id']}: Σ ratios = {ratio_sum}"
            )


@given(capacity_and_items())
@settings(max_examples=100, deadline=5000)
def test_engine_is_deterministic(args):
    """Same inputs produce identical outputs on two consecutive runs."""
    capacity_config, items = args
    r1 = run_edpa(capacity_config, {}, items)
    r2 = run_edpa(capacity_config, {}, items)
    for a, b in zip(r1, r2):
        assert a["total_derived"] == b["total_derived"]
        assert a["capacity"] == b["capacity"]


@given(capacity_and_items())
@settings(max_examples=100, deadline=5000)
def test_invariant_ok_agrees_with_derived(args):
    """invariant_ok flag is True iff derived == capacity and hours ≥ 0."""
    capacity_config, items = args
    results = run_edpa(capacity_config, {}, items)
    for r in results:
        if r["items"]:
            expected_ok = (
                abs(r["total_derived"] - r["capacity"]) <= 0.1
                and all(i["hours"] >= 0 for i in r["items"])
                and abs(sum(i["ratio"] for i in r["items"]) - 1.0) <= 0.001
            )
            assert r["invariant_ok"] == expected_ok, (
                f"{r['id']}: invariant_ok={r['invariant_ok']} but computed={expected_ok}"
            )


# ---------------------------------------------------------------------------
# _resolve_capacity invariants
# ---------------------------------------------------------------------------

@given(
    cpi=st.one_of(
        st.none(),
        st.floats(min_value=0.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    ),
    cap=st.one_of(
        st.none(),
        st.floats(min_value=0.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    ),
)
@settings(max_examples=200, deadline=1000)
def test_resolve_capacity_non_negative(cpi, cap):
    """_resolve_capacity returns non-negative effective capacity for valid inputs."""
    person: dict = {}
    if cpi is not None:
        person["capacity_per_iteration"] = cpi
    elif cap is not None:
        person["capacity"] = cap
    effective, _baseline, _meta = _resolve_capacity(person, None)
    assert effective >= 0, f"effective={effective} for person={person}"


@given(
    base=st.floats(min_value=1.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    override_val=st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=200, deadline=1000)
def test_resolve_capacity_override_respected(base, override_val):
    """When override sets capacity_per_iteration, it overrides the baseline."""
    person = {"capacity_per_iteration": base}
    effective, baseline, meta = _resolve_capacity(
        person, {"capacity_per_iteration": override_val},
    )
    assert abs(effective - override_val) < 0.001
    assert abs(baseline - base) < 0.001


# ---------------------------------------------------------------------------
# Edge-case properties
# ---------------------------------------------------------------------------

@given(
    capacity=st.floats(min_value=1.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    js=st.integers(min_value=1, max_value=100),
)
@settings(max_examples=100, deadline=2000)
def test_single_person_single_item_gets_all_capacity(capacity, js):
    """One person with one item gets exactly all their capacity."""
    capacity_config = {"people": [
        {"id": "alice", "capacity_per_iteration": capacity},
    ]}
    items = [{"id": "S-1", "job_size": js, "status": "Done",
              "contributors": [{"person": "alice", "cw": 1.0, "signals": []}]}]
    results = run_edpa(capacity_config, {}, items)
    alice = next(r for r in results if r["id"] == "alice")
    assert abs(alice["total_derived"] - capacity) <= 0.11


@given(
    capacity=st.floats(min_value=1.0, max_value=200.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50, deadline=1000)
def test_zero_items_gives_zero_derived(capacity):
    """Person with no contributions gets 0 derived hours."""
    capacity_config = {"people": [
        {"id": "alice", "capacity_per_iteration": capacity},
    ]}
    results = run_edpa(capacity_config, {}, [])
    alice = next(r for r in results if r["id"] == "alice")
    assert alice["total_derived"] == 0.0


@given(
    capacity=st.floats(min_value=1.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    js1=st.integers(min_value=1, max_value=50),
    js2=st.integers(min_value=1, max_value=50),
)
@settings(max_examples=150, deadline=2000)
def test_two_items_hours_sum_to_capacity(capacity, js1, js2):
    """Two items where alice owns both: hours sum to capacity."""
    capacity_config = {"people": [
        {"id": "alice", "capacity_per_iteration": capacity},
    ]}
    items = [
        {"id": "S-1", "job_size": js1, "status": "Done",
         "contributors": [{"person": "alice", "cw": 1.0, "signals": []}]},
        {"id": "S-2", "job_size": js2, "status": "Done",
         "contributors": [{"person": "alice", "cw": 1.0, "signals": []}]},
    ]
    results = run_edpa(capacity_config, {}, items)
    alice = next(r for r in results if r["id"] == "alice")
    assert abs(alice["total_derived"] - capacity) <= 0.11
