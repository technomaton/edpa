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

# Add plugin scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "plugin" / "edpa" / "scripts"))

from engine import run_edpa, generate_demo_data, detect_evidence, compute_cw


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


def test_multi_contract_isolation():
    """Two contracts of same person must have independent invariants."""
    capacity = {
        "people": [
            {"id": "alice-arch", "name": "Alice (Arch)", "role": "Arch",
             "fte": 0.5, "capacity_per_iteration": 40,
             "evidence_scope": ["S-*"], "evidence_default": True},
            {"id": "alice-pm", "name": "Alice (PM)", "role": "PM",
             "fte": 0.25, "capacity_per_iteration": 20,
             "evidence_scope": ["E-*", "F-*"]},
            {"id": "bob", "name": "Bob (Dev)", "role": "Dev",
             "fte": 1.0, "capacity_per_iteration": 80},
            {"id": "carol", "name": "Carol (Dev)", "role": "Dev",
             "fte": 0.75, "capacity_per_iteration": 60},
        ]
    }
    heuristics = {
        "evidence_threshold": 1.0,
        "role_weights": {"owner": 1.0, "key": 0.6, "reviewer": 0.25, "consulted": 0.15},
        "role_overrides": {
            "Arch": {"owner": 1.00, "key": 0.60, "reviewer": 0.30, "consulted": 0.15},
            "PM":   {"owner": 1.00, "key": 0.60, "reviewer": 0.25, "consulted": 0.20},
            "Dev":  {"owner": 1.00, "key": 0.60, "reviewer": 0.25, "consulted": 0.15},
        },
    }
    items = [
        {"id": "S-101", "level": "Story", "job_size": 5,
         "assignees": [{"login": "bob"}], "body": "",
         "pr_author": "bob", "commit_authors": ["bob"],
         "pr_reviewers": ["alice-arch"], "commenters": []},
        {"id": "S-102", "level": "Story", "job_size": 8,
         "assignees": [{"login": "carol"}], "body": "",
         "pr_author": "carol", "commit_authors": ["carol"],
         "pr_reviewers": ["alice-arch"], "commenters": []},
        {"id": "F-10", "level": "Feature", "job_size": 13,
         "assignees": [{"login": "alice-pm"}], "body": "",
         "pr_author": None, "commit_authors": [],
         "pr_reviewers": [], "commenters": ["bob"]},
        {"id": "E-10", "level": "Epic", "job_size": 21,
         "assignees": [{"login": "alice-pm"}], "body": "",
         "pr_author": None, "commit_authors": [],
         "pr_reviewers": [], "commenters": ["carol"]},
    ]

    results = run_edpa(capacity, heuristics, items, mode="simple")

    result_map = {r["id"]: r for r in results}

    # alice-arch must derive exactly 40h across her items
    arch = result_map["alice-arch"]
    assert arch["items"], "alice-arch should have items"
    assert abs(arch["total_derived"] - 40) < 0.01, (
        f"alice-arch: derived {arch['total_derived']}h != 40h"
    )

    # alice-pm must derive exactly 20h across her items
    pm = result_map["alice-pm"]
    assert pm["items"], "alice-pm should have items"
    assert abs(pm["total_derived"] - 20) < 0.01, (
        f"alice-pm: derived {pm['total_derived']}h != 20h"
    )

    # Both must pass invariants independently
    assert arch["invariant_ok"], "alice-arch invariant failed"
    assert pm["invariant_ok"], "alice-pm invariant failed"


def test_role_overrides_applied():
    """role_overrides should change CW based on person.role."""
    heuristics = {
        "evidence_threshold": 1.0,
        "role_weights": {"owner": 1.0, "key": 0.6, "reviewer": 0.25, "consulted": 0.15},
        "role_overrides": {
            "Arch": {"owner": 1.00, "key": 0.60, "reviewer": 0.30, "consulted": 0.15},
        },
    }
    # Simulate an evidence entry where the person is a reviewer
    evidence_entry = {
        "signals": ["pr_reviewer"],
        "evidence_score": 1.0,
        "manual_cw": None,
    }

    # With person_role="Arch", should use override: reviewer = 0.30
    cw_arch = compute_cw(evidence_entry, heuristics, person_role="Arch")
    assert abs(cw_arch - 0.30) < 0.001, (
        f"Arch reviewer CW should be 0.30, got {cw_arch}"
    )

    # With person_role="Dev" (no override defined), should use generic: reviewer = 0.25
    cw_dev = compute_cw(evidence_entry, heuristics, person_role="Dev")
    assert abs(cw_dev - 0.25) < 0.001, (
        f"Dev reviewer CW should be 0.25, got {cw_dev}"
    )

    # With no role, should use generic: reviewer = 0.25
    cw_none = compute_cw(evidence_entry, heuristics, person_role=None)
    assert abs(cw_none - 0.25) < 0.001, (
        f"No-role reviewer CW should be 0.25, got {cw_none}"
    )


def test_evidence_scope_routing():
    """evidence_scope must filter items for each contract."""
    people = [
        {"id": "alice-arch", "name": "Alice (Arch)", "role": "Arch",
         "evidence_scope": ["S-*"]},
        {"id": "alice-pm", "name": "Alice (PM)", "role": "PM",
         "evidence_scope": ["E-*"]},
    ]
    items = [
        {"id": "S-101", "level": "Story", "job_size": 5,
         "assignees": [{"login": "alice-arch"}], "body": "",
         "pr_author": None, "commit_authors": [],
         "pr_reviewers": [], "commenters": []},
        {"id": "E-10", "level": "Epic", "job_size": 21,
         "assignees": [{"login": "alice-pm"}], "body": "",
         "pr_author": None, "commit_authors": [],
         "pr_reviewers": [], "commenters": []},
    ]

    evidence = detect_evidence(people, items, "test-iter")

    # S-101 should produce evidence for alice-arch only
    assert ("alice-arch", "S-101") in evidence, (
        "S-101 should be routed to alice-arch"
    )
    assert ("alice-pm", "S-101") not in evidence, (
        "S-101 should NOT be routed to alice-pm"
    )

    # E-10 should produce evidence for alice-pm only
    assert ("alice-pm", "E-10") in evidence, (
        "E-10 should be routed to alice-pm"
    )
    assert ("alice-arch", "E-10") not in evidence, (
        "E-10 should NOT be routed to alice-arch"
    )


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
        test_multi_contract_isolation,
        test_role_overrides_applied,
        test_evidence_scope_routing,
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
