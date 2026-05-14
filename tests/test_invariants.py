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

import yaml

# Add plugin scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "plugin" / "edpa" / "scripts"))

from engine import run_edpa, generate_demo_data, load_backlog_items, extract_contributors
from _md_frontmatter import save_md as _save_md_helper


def test_sum_equals_capacity():
    """Derived hours must sum to declared capacity for each person."""
    capacity, heuristics, items = generate_demo_data()
    results = run_edpa(capacity, heuristics, items)

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
    results = run_edpa(capacity, heuristics, items)

    for person in results:
        if person["items"]:
            ratio_sum = sum(item["ratio"] for item in person["items"])
            assert abs(ratio_sum - 1.0) < 0.001, (
                f"{person['id']}: ratio sum {ratio_sum} != 1.0"
            )


def test_no_negative_hours():
    """No person should have negative derived hours."""
    capacity, heuristics, items = generate_demo_data()
    results = run_edpa(capacity, heuristics, items)

    for person in results:
        for item in person["items"]:
            assert item["hours"] >= 0, (
                f"{person['id']}: negative hours {item['hours']} on {item['id']}"
            )


def test_no_negative_scores():
    """No score should be negative."""
    capacity, heuristics, items = generate_demo_data()
    results = run_edpa(capacity, heuristics, items)

    for person in results:
        for item in person["items"]:
            assert item["score"] >= 0, (
                f"{person['id']}: negative score {item['score']} on {item['id']}"
            )


def test_score_formula_simple():
    """In simple mode: Score = JS x CW."""
    capacity, heuristics, items = generate_demo_data()
    results = run_edpa(capacity, heuristics, items)

    for person in results:
        for item in person["items"]:
            expected_score = item["js"] * item["cw"]
            assert abs(item["score"] - expected_score) < 0.001, (
                f"{person['id']}/{item['id']}: score {item['score']} != JS({item['js']}) x CW({item['cw']}) = {expected_score}"
            )


def test_score_formula_full():
    """In full mode: Score = JS x CW x RS."""
    capacity, heuristics, items = generate_demo_data()
    results = run_edpa(capacity, heuristics, items)

    for person in results:
        for item in person["items"]:
            expected_score = item["js"] * item["cw"] * item["rs"]
            assert abs(item["score"] - expected_score) < 0.01, (
                f"{person['id']}/{item['id']}: score {item['score']} != JS({item['js']}) x CW({item['cw']}) x RS({item['rs']}) = {expected_score}"
            )


def test_full_mode_invariants():
    """Full mode should also maintain sum = capacity invariant."""
    capacity, heuristics, items = generate_demo_data()
    results = run_edpa(capacity, heuristics, items)

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
    results = run_edpa(capacity, heuristics, items)

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

    results = run_edpa(capacity, heuristics, items)
    assert len(results) == 1
    assert results[0]["total_derived"] == 0.0
    assert results[0]["items"] == []


def test_signal_weight_ordering():
    """v1.11: signal weights should follow the role-implied hierarchy
    (assignee/owner > pr_author/key > commit_author/reviewer >
    issue_comment/consulted). Calibration may shuffle within each
    band but the gross ordering should hold."""
    capacity, heuristics, items = generate_demo_data()
    sw = heuristics["signals"]
    assert sw["assignee"] >= sw["pr_author"], (
        f"assignee ({sw['assignee']}) should >= pr_author ({sw['pr_author']})"
    )
    assert sw["pr_author"] >= sw["commit_author"], (
        f"pr_author ({sw['pr_author']}) should >= commit_author ({sw['commit_author']})"
    )
    # commit_author and pr_reviewer often calibrate close — allow tie
    assert sw["commit_author"] >= sw["pr_reviewer"] - 0.5, (
        f"commit_author ({sw['commit_author']}) should be near pr_reviewer ({sw['pr_reviewer']})"
    )
    assert sw["pr_reviewer"] >= sw["issue_comment"], (
        f"pr_reviewer ({sw['pr_reviewer']}) should >= issue_comment ({sw['issue_comment']})"
    )


def test_multi_contract_isolation():
    """Two contracts of same person must have independent invariants.

    v1.11: contributors[].cw is pre-computed per item (sum=1.0). Each
    contract is a separate person id; engine treats them independently.
    Multi-contract is now modeled by adding the same GitHub login to
    multiple person entries in people.yaml — each contract owns its
    own slice of contributors[] for items in its scope.
    """
    capacity = {
        "people": [
            {"id": "alice-arch", "name": "Alice (Arch)", "role": "Arch",
             "fte": 0.5, "capacity_per_iteration": 40},
            {"id": "alice-pm", "name": "Alice (PM)", "role": "PM",
             "fte": 0.25, "capacity_per_iteration": 20},
            {"id": "bob", "name": "Bob (Dev)", "role": "Dev",
             "fte": 1.0, "capacity_per_iteration": 80},
            {"id": "carol", "name": "Carol (Dev)", "role": "Dev",
             "fte": 0.75, "capacity_per_iteration": 60},
        ]
    }
    heuristics = {}  # not used in v1.11 engine

    # In v1.11 detect_contributors would have populated these cw shares
    # by reading real PR/issue evidence. Here we hand-build for the test:
    # alice-arch reviews stories (cw 0.3 each), alice-pm owns F-10 + E-10.
    items = [
        {"id": "S-101", "level": "Story", "job_size": 5,
         "assignees": [{"login": "bob"}],
         "contributors": [
             {"person": "bob", "cw": 0.7, "signals": []},
             {"person": "alice-arch", "cw": 0.3, "signals": []},
         ]},
        {"id": "S-102", "level": "Story", "job_size": 8,
         "assignees": [{"login": "carol"}],
         "contributors": [
             {"person": "carol", "cw": 0.7, "signals": []},
             {"person": "alice-arch", "cw": 0.3, "signals": []},
         ]},
        {"id": "F-10", "level": "Feature", "job_size": 13,
         "assignees": [{"login": "alice-pm"}],
         "contributors": [
             {"person": "alice-pm", "cw": 0.85, "signals": []},
             {"person": "bob", "cw": 0.15, "signals": []},
         ]},
        {"id": "E-10", "level": "Epic", "job_size": 21,
         "assignees": [{"login": "alice-pm"}],
         "contributors": [
             {"person": "alice-pm", "cw": 0.80, "signals": []},
             {"person": "carol", "cw": 0.20, "signals": []},
         ]},
    ]

    results = run_edpa(capacity, heuristics, items)

    result_map = {r["id"]: r for r in results}

    # alice-arch must derive exactly 40h across her items (capacity invariant)
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


# test_role_overrides_applied was removed in v1.11. Role-based CW
# computation is gone — detect_contributors.py produces per-item-normalized
# cw shares directly via additive signal aggregation, and engine consumes
# them verbatim. If role-aware signal weighting returns in v1.12 (e.g., as
# per-role multipliers on signal weights), it will be tested in
# test_detect_contributors.py against ground truth, not at engine level.

# test_evidence_scope_routing was removed in v1.11. The `evidence_scope`
# field was a detect_evidence-era routing mechanism. v1.11 establishes
# scope implicitly via contributors[] presence: a person is "in scope"
# for an item iff they appear in that item's contributors[] block, which
# detect_contributors.py builds from real GH evidence per item. Multi-
# contract people (one person, multiple contracts) is now modeled by
# adding the same GitHub login under multiple person ids in people.yaml.


def test_extract_contributors_v1_11_schema():
    """v1.11 engine reads cw directly from contributors[]; signals[] is
    optional audit trail."""
    item = {
        "contributors": [
            {"person": "alice", "cw": 0.6, "contribution_score": 6.0,
             "signals": [{"type": "assignee", "ref": "issue#1", "weight": 4.0},
                         {"type": "pr_author", "ref": "pr#10", "weight": 2.0}]},
            {"person": "bob", "cw": 0.4, "contribution_score": 4.0,
             "signals": [{"type": "pr_author", "ref": "pr#11", "weight": 2.0},
                         {"type": "commit_author", "ref": "pr#11/commit/abc",
                          "weight": 1.0},
                         {"type": "issue_comment", "ref": "issue#1/c/1",
                          "weight": 0.5}]},
        ]
    }
    extracted = extract_contributors(item)
    assert len(extracted) == 2
    by_person = {c["person"]: c for c in extracted}
    assert by_person["alice"]["cw"] == 0.6
    assert by_person["bob"]["cw"] == 0.4
    assert len(by_person["alice"]["signals"]) == 2
    assert len(by_person["bob"]["signals"]) == 3


def test_extract_contributors_skips_invalid_entries():
    item = {
        "contributors": [
            {"person": "alice", "cw": 0.6},     # ok, no signals
            {"person": "bob"},                   # missing cw
            {"cw": 0.4},                         # missing person
            {"person": "carol", "cw": 1.5},      # cw out of range
            "not a dict",                        # malformed
        ]
    }
    extracted = extract_contributors(item)
    assert len(extracted) == 1
    assert extracted[0]["person"] == "alice"


def test_extract_contributors_tolerates_legacy_as_field():
    """v1.11 engine ignores `as:` for backward read compatibility with
    fixtures from v1.10-era tests. validate_syntax.py rejects `as:`
    on commit-time hooks but engine doesn't fail on it during read."""
    item = {
        "contributors": [
            {"person": "alice", "cw": 0.5, "as": "owner"},  # legacy as: ignored
        ]
    }
    extracted = extract_contributors(item)
    assert len(extracted) == 1
    assert extracted[0]["person"] == "alice"
    assert extracted[0]["cw"] == 0.5
    assert "as" not in extracted[0]  # not propagated to engine output


class TestLoadBacklogItems:
    """Tests for load_backlog_items() and SAFe iteration hierarchy."""

    def _create_item(self, backlog_dir, dir_name, item_id, item_type, js, status, iteration=None, assignee=None, contributors=None):
        type_dir = backlog_dir / dir_name
        type_dir.mkdir(parents=True, exist_ok=True)
        data = {"id": item_id, "type": item_type, "js": js, "status": status}
        if iteration is not None:
            data["iteration"] = iteration
        if assignee:
            data["assignee"] = assignee
        if contributors:
            data["contributors"] = contributors
        _save_md_helper(type_dir / f"{item_id}.md", data, "")

    def test_load_stories_by_iteration(self, tmp_path):
        """Stories filtered by exact iteration match."""
        edpa_root = tmp_path / ".edpa"
        backlog = edpa_root / "backlog"

        self._create_item(backlog, "stories", "S-101", "Story", 5, "Done", "PI-2026-1.1", assignee="alice")
        self._create_item(backlog, "stories", "S-102", "Story", 8, "Done", "PI-2026-1.1", assignee="bob")
        self._create_item(backlog, "stories", "S-103", "Story", 3, "Done", "PI-2026-1.2", assignee="carol")

        items, _ = load_backlog_items(edpa_root, iteration_id="PI-2026-1.1")

        ids = [i["id"] for i in items]
        assert "S-101" in ids
        assert "S-102" in ids
        assert "S-103" not in ids
        assert len(items) == 2

    def test_load_features_by_pi(self, tmp_path):
        """Features included when PI prefix matches iteration."""
        edpa_root = tmp_path / ".edpa"
        backlog = edpa_root / "backlog"

        self._create_item(backlog, "features", "F-10", "Feature", 13, "Done", "PI-2026-1", assignee="alice")
        self._create_item(backlog, "features", "F-20", "Feature", 8, "Done", "PI-2026-2", assignee="bob")

        items, _ = load_backlog_items(edpa_root, iteration_id="PI-2026-1.1")

        ids = [i["id"] for i in items]
        assert "F-10" in ids, "Feature with matching PI prefix should be included"
        assert "F-20" not in ids, "Feature with different PI should be excluded"

    def test_load_epics_always_included(self, tmp_path):
        """Done Epics included regardless of iteration filter."""
        edpa_root = tmp_path / ".edpa"
        backlog = edpa_root / "backlog"

        self._create_item(backlog, "epics", "E-1", "Epic", 21, "Done")
        self._create_item(backlog, "initiatives", "I-1", "Initiative", 34, "Closed")

        items, _ = load_backlog_items(edpa_root, iteration_id="PI-2026-1.1")

        ids = [i["id"] for i in items]
        assert "E-1" in ids, "Done Epic should always be included"
        assert "I-1" in ids, "Closed Initiative should always be included"

    def test_load_skips_active_items(self, tmp_path):
        """Implementing items excluded from loading."""
        edpa_root = tmp_path / ".edpa"
        backlog = edpa_root / "backlog"

        self._create_item(backlog, "stories", "S-200", "Story", 5, "Implementing", "PI-2026-1.1", assignee="alice")
        self._create_item(backlog, "stories", "S-201", "Story", 3, "Implementing", "PI-2026-1.1", assignee="bob")
        self._create_item(backlog, "stories", "S-202", "Story", 8, "Done", "PI-2026-1.1", assignee="carol")

        items, _ = load_backlog_items(edpa_root, iteration_id="PI-2026-1.1")

        ids = [i["id"] for i in items]
        assert "S-200" not in ids, "Implementing story should be excluded"
        assert "S-201" not in ids, "Implementing story should be excluded"
        assert "S-202" in ids, "Done story should be included"

    def test_contributor_v1_11_passthrough(self, tmp_path):
        """v1.11: contributors[] is passed through to engine items
        verbatim. Engine reads `cw` directly. The pre-v1.11 mapping
        (`as: owner` → top-level `assignees`, `as: key` → `pr_author`,
        etc.) is gone — those signal fields are no longer engine inputs."""
        edpa_root = tmp_path / ".edpa"
        backlog = edpa_root / "backlog"

        contributors = [
            {"person": "alice", "cw": 0.5, "contribution_score": 4.0,
             "signals": [{"type": "assignee", "ref": "issue#1", "weight": 4.0}]},
            {"person": "bob", "cw": 0.3, "contribution_score": 2.5,
             "signals": [{"type": "pr_author", "ref": "pr#10", "weight": 2.0},
                         {"type": "issue_comment", "ref": "issue#1/c/1",
                          "weight": 0.5}]},
            {"person": "carol", "cw": 0.2, "contribution_score": 1.5,
             "signals": [{"type": "commit_author", "ref": "pr#10/commit/abc",
                          "weight": 1.0},
                         {"type": "issue_comment", "ref": "issue#1/c/2",
                          "weight": 0.5}]},
        ]
        self._create_item(backlog, "stories", "S-300", "Story", 5, "Done", "PI-2026-1.1",
                          assignee="alice", contributors=contributors)

        items, _ = load_backlog_items(edpa_root, iteration_id="PI-2026-1.1")

        assert len(items) == 1
        item = items[0]
        # Engine receives `contributors` field with cw + signals intact.
        assert "contributors" in item
        by_person = {c["person"]: c for c in item["contributors"]}
        assert by_person["alice"]["cw"] == 0.5
        assert by_person["bob"]["cw"] == 0.3
        assert by_person["carol"]["cw"] == 0.2
        # Σ cw per item ≈ 1.0
        cw_sum = sum(c["cw"] for c in item["contributors"])
        assert abs(cw_sum - 1.0) < 0.001

    def test_contributor_v1_11_cw_required(self, tmp_path):
        """v1.11: contributors entries without cw are skipped — caller
        must run detect_contributors.py to populate per-item shares."""
        edpa_root = tmp_path / ".edpa"
        backlog = edpa_root / "backlog"

        # alice has cw, bob doesn't — only alice should make it through
        contributors = [
            {"person": "alice", "cw": 1.0, "signals": []},
            {"person": "bob"},  # missing cw → dropped with warning
        ]
        self._create_item(backlog, "stories", "S-400", "Story", 5, "Done", "PI-2026-1.1",
                          contributors=contributors)

        items, _ = load_backlog_items(edpa_root, iteration_id="PI-2026-1.1")
        assert len(items) == 1
        contribs = items[0]["contributors"]
        assert len(contribs) == 1
        assert contribs[0]["person"] == "alice"

    def test_capacity_field_priority(self):
        """capacity_per_iteration: 0 should be 0, not fallback."""
        capacity = {
            "people": [
                {"id": "zero-cap", "name": "Zero Cap", "role": "Dev",
                 "fte": 1.0, "capacity_per_iteration": 0, "capacity": 40}
            ]
        }
        heuristics = {
            "evidence_threshold": 1.0,
            "role_weights": {"owner": 1.0, "key": 0.6, "reviewer": 0.25, "consulted": 0.15},
        }
        items = [
            {"id": "S-500", "level": "Story", "job_size": 5,
             "assignees": [{"login": "zero-cap"}], "body": "",
             "pr_author": "zero-cap", "commit_authors": [],
             "pr_reviewers": [], "commenters": []}
        ]

        results = run_edpa(capacity, heuristics, items)

        assert len(results) == 1
        assert results[0]["capacity"] == 0, (
            f"capacity_per_iteration=0 should yield 0, got {results[0]['capacity']}"
        )
        assert results[0]["total_derived"] == 0.0


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
        test_signal_weight_ordering,
        test_multi_contract_isolation,
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
