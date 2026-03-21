#!/usr/bin/env python3
"""
EDPA Invariant Tests

Validates the core mathematical guarantees of the EDPA engine:
1. Sum of derived hours equals declared capacity (per person)
2. Sum of ratios equals 1.0 (per person)
3. No negative hours
4. Score calculation correctness
"""

import json
import sys
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from edpa_engine import run_edpa, generate_demo_data


def test_sum_equals_capacity():
    """Derived hours must sum to declared capacity for each person."""
    capacity, heuristics, items = generate_demo_data()
    results = run_edpa(capacity, heuristics, items, mode="simple")

    for person in results:
        if person["items"]:
            expected = person["capacity"]
            actual = person["total_derived"]
            assert abs(actual - expected) < 0.01, (
                f"{person['id']}: derived {actual}h != capacity {expected}h"
            )


def test_ratio_sum_equals_one():
    """Ratios must sum to 1.0 for each person with items."""
    capacity, heuristics, items = generate_demo_data()
    results = run_edpa(capacity, heuristics, items, mode="simple")

    for person in results:
        if person["items"]:
            ratio_sum = sum(item["ratio"] for item in person["items"])
            assert abs(ratio_sum - 1.0) < 0.001, (
                f"{person['id']}: ratio sum {ratio_sum} != 1.0"
            )


def test_no_negative_hours():
    """No person should have negative derived hours."""
    capacity, heuristics, items = generate_demo_data()
    results = run_edpa(capacity, heuristics, items, mode="simple")

    for person in results:
        for item in person["items"]:
            assert item["hours"] >= 0, (
                f"{person['id']}: negative hours {item['hours']} on {item['id']}"
            )


def test_no_negative_scores():
    """No score should be negative."""
    capacity, heuristics, items = generate_demo_data()
    results = run_edpa(capacity, heuristics, items, mode="simple")

    for person in results:
        for item in person["items"]:
            assert item["score"] >= 0, (
                f"{person['id']}: negative score {item['score']} on {item['id']}"
            )


def test_score_formula_simple():
    """In simple mode: Score = JS x CW."""
    capacity, heuristics, items = generate_demo_data()
    results = run_edpa(capacity, heuristics, items, mode="simple")

    for person in results:
        for item in person["items"]:
            expected_score = item["js"] * item["cw"]
            assert abs(item["score"] - expected_score) < 0.001, (
                f"{person['id']}/{item['id']}: score {item['score']} != JS({item['js']}) x CW({item['cw']}) = {expected_score}"
            )


def test_score_formula_full():
    """In full mode: Score = JS x CW x RS."""
    capacity, heuristics, items = generate_demo_data()
    results = run_edpa(capacity, heuristics, items, mode="full")

    for person in results:
        for item in person["items"]:
            expected_score = item["js"] * item["cw"] * item["rs"]
            assert abs(item["score"] - expected_score) < 0.01, (
                f"{person['id']}/{item['id']}: score {item['score']} != JS({item['js']}) x CW({item['cw']}) x RS({item['rs']}) = {expected_score}"
            )


def test_full_mode_invariants():
    """Full mode should also maintain sum = capacity invariant."""
    capacity, heuristics, items = generate_demo_data()
    results = run_edpa(capacity, heuristics, items, mode="full")

    for person in results:
        if person["items"]:
            expected = person["capacity"]
            actual = person["total_derived"]
            assert abs(actual - expected) < 0.01, (
                f"Full mode: {person['id']}: derived {actual}h != capacity {expected}h"
            )


def test_all_invariants_flag():
    """The all_invariants_passed flag should reflect actual invariant checks."""
    capacity, heuristics, items = generate_demo_data()
    results = run_edpa(capacity, heuristics, items, mode="simple")

    for person in results:
        if person["items"]:
            assert person["invariant_ok"] is True, (
                f"{person['id']}: invariant_ok is False but should be True"
            )


def test_empty_items_no_crash():
    """Person with no relevant items should produce 0 derived hours, not crash."""
    capacity = {
        "people": [
            {"id": "lonely", "name": "Lonely Dev", "role": "Dev",
             "fte": 1.0, "capacity_per_iteration": 80, "email": "lonely@example.com"}
        ]
    }
    heuristics = {
        "evidence_threshold": 1.0,
        "role_weights": {"owner": 1.0, "key": 0.6, "reviewer": 0.25, "consulted": 0.15},
        "signals": {"assignee": 4.0, "pr_author": 2.0, "commit_author": 1.0,
                     "pr_reviewer": 1.0, "issue_comment": 0.5, "contribute_command": 3.0},
    }
    items = [
        {"id": "S-100", "level": "Story", "job_size": 5,
         "assignees": [{"login": "someone_else"}], "body": "",
         "pr_author": "someone_else", "commit_authors": [],
         "pr_reviewers": [], "commenters": []}
    ]

    results = run_edpa(capacity, heuristics, items, mode="simple")
    assert len(results) == 1
    assert results[0]["total_derived"] == 0.0
    assert results[0]["items"] == []


def test_cw_ordering():
    """CW should be: owner >= key >= reviewer >= consulted."""
    capacity, heuristics, items = generate_demo_data()
    rw = heuristics["role_weights"]
    assert rw["owner"] >= rw["key"] >= rw["reviewer"] >= rw["consulted"]


if __name__ == "__main__":
    tests = [
        test_sum_equals_capacity,
        test_ratio_sum_equals_one,
        test_no_negative_hours,
        test_no_negative_scores,
        test_score_formula_simple,
        test_score_formula_full,
        test_full_mode_invariants,
        test_all_invariants_flag,
        test_empty_items_no_crash,
        test_cw_ordering,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {test.__name__}: {e}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed out of {len(tests)} tests")
    sys.exit(1 if failed else 0)
