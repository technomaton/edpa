"""Tests for calibrate_signals.py — Monte Carlo signal-weight calibrator.

D2 roadmap item: 580-line statistical optimizer had zero tests.
C2 roadmap item: real-data calibration feedback loop.

Critical failure modes to guard (per roadmap §5.D2):
  - NaN / Inf weights appearing in output
  - Weight constraint violations (floor < 0.05)
  - MAD > 1.0 (mathematically impossible for cw deviations in [0,1])
  - Calibrated MAD worse than baseline after optimization
  - Per-item CW shares not summing to ~1.0 in synthetic data
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

from calibrate_signals import (  # noqa: E402
    SIGNAL_TYPES,
    SyntheticContribution,
    SyntheticScenario,
    _count_signals,
    blend_corpora,
    build_real_contribution,
    coordinate_descent,
    evaluate_mad,
    generate_corpus,
    generate_scenario,
    generate_signals,
    load_corrections,
    load_real_corpus,
    random_sample_phase,
    run_calibration,
    run_calibration_real_data,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uniform_weights(value: float = 1.0) -> dict:
    return {s: value for s in SIGNAL_TYPES}


def _minimal_corpus(n: int = 5, seed: int = 0) -> list:
    """Small deterministic corpus for fast tests."""
    return generate_corpus(n, seed)


# ---------------------------------------------------------------------------
# generate_signals
# ---------------------------------------------------------------------------

class TestGenerateSignals:
    def _rng(self, seed=0):
        return random.Random(seed)

    def test_returns_all_signal_keys(self):
        sigs = generate_signals(0.6, "Dev", self._rng())
        assert set(sigs.keys()) == set(SIGNAL_TYPES)

    def test_no_negative_signal_counts(self):
        rng = self._rng(7)
        for true_cw in (0.05, 0.15, 0.30, 0.50, 0.85):
            for role in ("Dev", "Arch", "PM", "QA", "DevSecOps"):
                sigs = generate_signals(true_cw, role, rng)
                assert all(v >= 0 for v in sigs.values()), (
                    f"negative signal for cw={true_cw} role={role}: {sigs}"
                )

    def test_high_cw_owner_gets_assignee(self):
        # Owner band (>= 0.5): assignee should always be set
        rng = self._rng(42)
        hits = sum(
            generate_signals(0.75, "Dev", rng)["assignee"] > 0
            for _ in range(20)
        )
        assert hits == 20

    def test_edge_case_pm_driven_owner(self):
        rng = self._rng(0)
        sigs = generate_signals(0.5, "PM", rng, edge_case="pm_driven_owner")
        assert sigs["assignee"] == 1
        assert sigs["issue_comment"] >= 2

    def test_edge_case_silent_reviewer_no_commits(self):
        rng = self._rng(0)
        sigs = generate_signals(0.2, "Arch", rng, edge_case="silent_reviewer")
        assert sigs["commit_author"] == 0
        assert sigs["pr_reviewer"] >= 1

    def test_edge_case_arch_consultant_no_commits(self):
        rng = self._rng(0)
        sigs = generate_signals(0.25, "Arch", rng, edge_case="arch_consultant")
        assert sigs["commit_author"] == 0
        assert sigs["issue_comment"] >= 2

    def test_edge_case_pair_partner_has_commits(self):
        rng = self._rng(0)
        sigs = generate_signals(0.45, "Dev", rng, edge_case="pair_partner")
        assert sigs["commit_author"] >= 2


# ---------------------------------------------------------------------------
# generate_scenario / generate_corpus
# ---------------------------------------------------------------------------

class TestGenerateScenario:
    def test_per_item_cw_sums_to_one(self):
        """True CW shares for each item must sum to ~1.0 across contributors."""
        rng = random.Random(99)
        scenario = generate_scenario(0, rng)
        by_item: dict[str, float] = {}
        for c in scenario.contributions:
            by_item[c.item_id] = by_item.get(c.item_id, 0.0) + c.true_cw
        for item_id, total in by_item.items():
            assert abs(total - 1.0) < 0.02, (
                f"item {item_id}: CW sum = {total:.4f} (expected ~1.0)"
            )

    def test_all_persons_in_team(self):
        """Every contribution must reference a person declared in the team."""
        rng = random.Random(0)
        scenario = generate_scenario(1, rng)
        team_ids = {p["id"] for p in scenario.team}
        for c in scenario.contributions:
            assert c.person in team_ids, (
                f"contribution from unknown person {c.person!r}"
            )

    def test_item_count_in_range(self):
        rng = random.Random(0)
        for i in range(20):
            s = generate_scenario(i, rng)
            assert 5 <= len(s.items) <= 15

    def test_corpus_count(self):
        corpus = generate_corpus(10, seed=5)
        assert len(corpus) == 10

    def test_corpus_deterministic(self):
        a = generate_corpus(5, seed=42)
        b = generate_corpus(5, seed=42)
        # Compare first contributions list by true_cw
        for ca, cb in zip(a[0].contributions, b[0].contributions):
            assert ca.true_cw == cb.true_cw
            assert ca.signal_counts == cb.signal_counts

    def test_no_nan_in_signals(self):
        corpus = generate_corpus(20, seed=7)
        for scenario in corpus:
            for c in scenario.contributions:
                for sig, val in c.signal_counts.items():
                    assert not math.isnan(val), f"NaN in signal {sig}"
                    assert not math.isinf(val), f"Inf in signal {sig}"
                assert not math.isnan(c.true_cw), "NaN in true_cw"


# ---------------------------------------------------------------------------
# evaluate_mad
# ---------------------------------------------------------------------------

class TestEvaluateMad:
    def test_returns_float_between_zero_and_one(self):
        corpus = _minimal_corpus(10, seed=0)
        mad, n = evaluate_mad(corpus, _uniform_weights(1.0))
        assert isinstance(mad, float)
        assert 0.0 <= mad <= 1.0

    def test_n_matches_nonempty_records(self):
        corpus = _minimal_corpus(5, seed=1)
        _, n = evaluate_mad(corpus, _uniform_weights())
        total_contribs = sum(len(s.contributions) for s in corpus)
        assert n <= total_contribs  # zero-signal items excluded

    def test_empty_corpus_returns_inf(self):
        mad, n = evaluate_mad([], _uniform_weights())
        assert mad == float("inf")
        assert n == 0

    def test_zero_signal_item_skipped(self):
        """An item where all contributors have zero signals is skipped (no /0)."""
        zero_contrib = SyntheticContribution(
            person="p1", role="Dev", item_id="S-ZZ",
            true_cw=0.5, signal_counts={s: 0 for s in SIGNAL_TYPES},
        )
        nonzero = SyntheticContribution(
            person="p2", role="Dev", item_id="S-AA",
            true_cw=1.0, signal_counts={"commit_author": 3,
                                         **{s: 0 for s in SIGNAL_TYPES if s != "commit_author"}},
        )
        corpus = [SyntheticScenario(team=[], items=["S-ZZ", "S-AA"],
                                    contributions=[zero_contrib, nonzero])]
        mad, n = evaluate_mad(corpus, _uniform_weights())
        assert n == 1  # only S-AA counted

    def test_mad_finite_with_default_weights(self):
        defaults = {
            "assignee": 4.0, "pr_author": 3.4, "commit_author": 2.78,
            "pr_reviewer": 2.25, "issue_comment": 1.14,
        }
        corpus = _minimal_corpus(30, seed=3)
        mad, _ = evaluate_mad(corpus, defaults)
        assert math.isfinite(mad)
        assert 0.0 <= mad <= 1.0

    def test_no_nan_in_mad(self):
        """Mad must never be NaN regardless of weight values."""
        corpus = _minimal_corpus(10, seed=9)
        for w_val in (0.0, 0.01, 8.0, 0.05):
            mad, _ = evaluate_mad(corpus, _uniform_weights(w_val))
            assert not math.isnan(mad), f"NaN MAD with uniform weights={w_val}"


# ---------------------------------------------------------------------------
# random_sample_phase
# ---------------------------------------------------------------------------

class TestRandomSamplePhase:
    def test_returns_n_results(self):
        corpus = _minimal_corpus(5, seed=0)
        results = random_sample_phase(corpus, n_samples=10, seed=1)
        assert len(results) == 10

    def test_sorted_by_mad(self):
        corpus = _minimal_corpus(10, seed=0)
        results = random_sample_phase(corpus, n_samples=20, seed=2)
        mads = [r[0] for r in results]
        assert mads == sorted(mads)

    def test_weights_in_range(self):
        corpus = _minimal_corpus(5, seed=0)
        results = random_sample_phase(corpus, n_samples=15, seed=3,
                                      weight_range=(0.1, 8.0))
        for _, w in results:
            for s in SIGNAL_TYPES:
                assert 0.1 <= w[s] <= 8.0, (
                    f"weight for {s} = {w[s]:.3f} out of [0.1, 8.0]"
                )

    def test_deterministic_with_same_seed(self):
        corpus = _minimal_corpus(5, seed=0)
        a = random_sample_phase(corpus, n_samples=10, seed=7)
        b = random_sample_phase(corpus, n_samples=10, seed=7)
        assert [r[0] for r in a] == [r[0] for r in b]

    def test_no_nan_weights(self):
        corpus = _minimal_corpus(5, seed=0)
        results = random_sample_phase(corpus, n_samples=20, seed=5)
        for _, w in results:
            for s in SIGNAL_TYPES:
                assert not math.isnan(w[s]), f"NaN weight for signal {s}"


# ---------------------------------------------------------------------------
# coordinate_descent
# ---------------------------------------------------------------------------

class TestCoordinateDescent:
    def test_mad_does_not_increase(self):
        corpus = _minimal_corpus(10, seed=0)
        start = _uniform_weights(2.0)
        start_mad, _ = evaluate_mad(corpus, start)
        final_mad, final_weights = coordinate_descent(corpus, start)
        assert final_mad <= start_mad + 1e-9

    def test_floor_constraint_respected(self):
        """No weight should fall below the 0.05 floor in coordinate_descent."""
        corpus = _minimal_corpus(10, seed=0)
        # Start with tiny weights to stress the floor
        start = _uniform_weights(0.06)
        _, final_weights = coordinate_descent(corpus, start)
        for s, v in final_weights.items():
            assert v >= 0.05, f"weight {s}={v:.4f} below 0.05 floor"

    def test_no_nan_in_output_weights(self):
        corpus = _minimal_corpus(10, seed=1)
        _, final_weights = coordinate_descent(corpus, _uniform_weights(1.5))
        for s, v in final_weights.items():
            assert not math.isnan(v), f"NaN in final weight {s}"
            assert not math.isinf(v), f"Inf in final weight {s}"

    def test_returns_all_signal_types(self):
        corpus = _minimal_corpus(5, seed=0)
        _, final_weights = coordinate_descent(corpus, _uniform_weights())
        assert set(final_weights.keys()) == set(SIGNAL_TYPES)


# ---------------------------------------------------------------------------
# run_calibration (integration, quick mode only)
# ---------------------------------------------------------------------------

class TestRunCalibration:
    def test_result_has_expected_keys(self, capsys):
        report = run_calibration(n_scenarios=10, seed=42, quick=True)
        for key in ("n_scenarios", "n_records", "seed", "baseline_weights",
                    "baseline_mad", "calibrated_weights", "calibrated_mad",
                    "improvement_pct", "method"):
            assert key in report, f"missing key: {key}"

    def test_calibrated_mad_leq_baseline(self, capsys):
        report = run_calibration(n_scenarios=10, seed=42, quick=True)
        assert report["calibrated_mad"] <= report["baseline_mad"] + 1e-6, (
            f"calibrated MAD {report['calibrated_mad']:.4f} > "
            f"baseline {report['baseline_mad']:.4f}"
        )

    def test_improvement_pct_consistent(self, capsys):
        report = run_calibration(n_scenarios=10, seed=1, quick=True)
        expected = (report["baseline_mad"] - report["calibrated_mad"]) / report["baseline_mad"] * 100
        assert abs(report["improvement_pct"] - expected) < 0.01

    def test_no_nan_in_calibrated_weights(self, capsys):
        report = run_calibration(n_scenarios=10, seed=7, quick=True)
        for s, v in report["calibrated_weights"].items():
            assert not math.isnan(v), f"NaN in calibrated weight {s}"
            assert not math.isinf(v), f"Inf in calibrated weight {s}"

    def test_calibrated_weights_above_floor(self, capsys):
        report = run_calibration(n_scenarios=10, seed=3, quick=True)
        for s, v in report["calibrated_weights"].items():
            assert v >= 0.05, f"calibrated weight {s}={v:.4f} below 0.05"

    def test_mads_in_valid_range(self, capsys):
        report = run_calibration(n_scenarios=15, seed=0, quick=True)
        assert 0.0 <= report["baseline_mad"] <= 1.0
        assert 0.0 <= report["calibrated_mad"] <= 1.0

    def test_n_records_positive(self, capsys):
        report = run_calibration(n_scenarios=5, seed=2, quick=True)
        assert report["n_records"] > 0
        assert report["n_scenarios"] == 5


# ---------------------------------------------------------------------------
# C2: real-data calibration helpers
# ---------------------------------------------------------------------------

CORRECTIONS_YAML = """\
corrections:
  - iteration: PI-2026-1
    item: S-1
    person: alice
    actual_cw: 0.70
    note: "pair session"
  - iteration: PI-2026-1
    item: S-1
    person: bob
    actual_cw: 0.30
  - iteration: PI-2026-1
    item: S-2
    person: alice
    actual_cw: 1.0
"""

BACKLOG_ITEM_WITH_SIGNALS = """\
---
id: S-1
type: Story
title: Auth endpoint
js: 5
status: Done
iteration: PI-2026-1
assignee: alice
contributors:
  - person: alice
    cw: 0.80
    as: owner
    signals:
      - type: commit_author
        ref: abc1
        weight: 2.78
      - type: commit_author
        ref: abc2
        weight: 2.78
      - type: assignee
        ref: S-1
        weight: 4.0
  - person: bob
    cw: 0.20
    as: reviewer
    signals:
      - type: pr_reviewer
        ref: pr-55
        weight: 2.25
---
"""

BACKLOG_ITEM_NO_SIGNALS = """\
---
id: S-2
type: Story
title: Login UI
js: 3
status: Done
iteration: PI-2026-1
assignee: alice
contributors:
  - person: alice
    cw: 1.0
    as: owner
---
"""


@pytest.fixture
def corrections_workspace(tmp_path):
    edpa = tmp_path / ".edpa"
    (edpa / "data").mkdir(parents=True)
    (edpa / "backlog" / "stories").mkdir(parents=True)

    (edpa / "data" / "calibration_corrections.yaml").write_text(
        CORRECTIONS_YAML, encoding="utf-8"
    )
    (edpa / "backlog" / "stories" / "S-1.md").write_text(
        BACKLOG_ITEM_WITH_SIGNALS, encoding="utf-8"
    )
    (edpa / "backlog" / "stories" / "S-2.md").write_text(
        BACKLOG_ITEM_NO_SIGNALS, encoding="utf-8"
    )
    return edpa


class TestCountSignals:
    def test_counts_by_type(self):
        raw = [
            {"type": "commit_author", "ref": "a"},
            {"type": "commit_author", "ref": "b"},
            {"type": "assignee", "ref": "S-1"},
        ]
        counts = _count_signals(raw)
        assert counts["commit_author"] == 2
        assert counts["assignee"] == 1
        assert counts["pr_reviewer"] == 0

    def test_ignores_unknown_types(self):
        raw = [{"type": "unknown_signal"}, {"type": "commit_author", "ref": "x"}]
        counts = _count_signals(raw)
        assert counts["commit_author"] == 1
        assert all(counts[s] >= 0 for s in SIGNAL_TYPES)

    def test_empty_returns_all_zeros(self):
        counts = _count_signals([])
        assert all(counts[s] == 0 for s in SIGNAL_TYPES)


class TestLoadCorrections:
    def test_loads_records(self, corrections_workspace):
        recs = load_corrections(corrections_workspace / "data" / "calibration_corrections.yaml")
        assert len(recs) == 3

    def test_missing_file_returns_empty(self, tmp_path):
        assert load_corrections(tmp_path / "nonexistent.yaml") == []

    def test_empty_corrections_returns_empty(self, tmp_path):
        f = tmp_path / "c.yaml"
        f.write_text("corrections: []\n", encoding="utf-8")
        assert load_corrections(f) == []


class TestBuildRealContribution:
    def test_uses_signals_from_backlog(self, corrections_workspace):
        rec = {"iteration": "PI-2026-1", "item": "S-1",
               "person": "alice", "actual_cw": 0.70}
        c = build_real_contribution(rec, corrections_workspace)
        assert c is not None
        assert c.true_cw == pytest.approx(0.70)
        assert c.signal_counts["commit_author"] == 2
        assert c.signal_counts["assignee"] == 1

    def test_infers_signals_when_none(self, corrections_workspace):
        rec = {"iteration": "PI-2026-1", "item": "S-2",
               "person": "alice", "actual_cw": 1.0}
        c = build_real_contribution(rec, corrections_workspace)
        assert c is not None
        # Inferred from as: owner + assignee
        assert c.signal_counts["assignee"] >= 1

    def test_missing_item_returns_none(self, corrections_workspace):
        rec = {"item": "S-999", "person": "alice", "actual_cw": 0.5}
        assert build_real_contribution(rec, corrections_workspace) is None

    def test_invalid_cw_returns_none(self, corrections_workspace):
        rec = {"item": "S-1", "person": "alice", "actual_cw": -0.1}
        assert build_real_contribution(rec, corrections_workspace) is None

    def test_zero_cw_returns_none(self, corrections_workspace):
        rec = {"item": "S-1", "person": "alice", "actual_cw": 0.0}
        assert build_real_contribution(rec, corrections_workspace) is None


class TestLoadRealCorpus:
    def test_groups_by_iteration(self, corrections_workspace):
        corpus = load_real_corpus(
            corrections_workspace,
            corrections_workspace / "data" / "calibration_corrections.yaml",
        )
        assert len(corpus) == 1  # all corrections in PI-2026-1
        assert corpus[0].items  # at least one item

    def test_contributions_count(self, corrections_workspace):
        corpus = load_real_corpus(
            corrections_workspace,
            corrections_workspace / "data" / "calibration_corrections.yaml",
        )
        # 3 corrections → 3 SyntheticContribution records
        total = sum(len(s.contributions) for s in corpus)
        assert total == 3

    def test_empty_corrections_returns_empty(self, tmp_path):
        edpa = tmp_path / ".edpa"
        (edpa / "data").mkdir(parents=True)
        f = edpa / "data" / "calibration_corrections.yaml"
        f.write_text("corrections: []\n", encoding="utf-8")
        assert load_real_corpus(edpa, f) == []


class TestBlendCorpora:
    def test_blend_length(self):
        real = _minimal_corpus(2, seed=0)
        synthetic = _minimal_corpus(5, seed=1)
        blended = blend_corpora(real, synthetic, real_weight=3)
        assert len(blended) == 3 * 2 + 5  # real×3 + synthetic

    def test_zero_weight_keeps_only_synthetic(self):
        real = _minimal_corpus(2, seed=0)
        synthetic = _minimal_corpus(5, seed=1)
        blended = blend_corpora(real, synthetic, real_weight=0)
        assert len(blended) == 5

    def test_blend_preserves_contributions(self, corrections_workspace):
        real = load_real_corpus(
            corrections_workspace,
            corrections_workspace / "data" / "calibration_corrections.yaml",
        )
        synthetic = _minimal_corpus(3, seed=7)
        blended = blend_corpora(real, synthetic, real_weight=2)
        assert len(blended) > 0


class TestRunCalibrationRealData:
    def test_falls_back_to_synthetic_on_empty_corrections(self, tmp_path, capsys):
        edpa = tmp_path / ".edpa"
        (edpa / "data").mkdir(parents=True)
        f = edpa / "data" / "calibration_corrections.yaml"
        f.write_text("corrections: []\n", encoding="utf-8")
        report = run_calibration_real_data(
            edpa_root=edpa,
            corrections_file=f,
            n_scenarios=5,
            seed=0,
            quick=True,
        )
        assert report["real_records"] == 0
        assert report["mode"] == "synthetic-only (no corrections found)"

    def test_real_data_report_keys(self, corrections_workspace, capsys):
        report = run_calibration_real_data(
            edpa_root=corrections_workspace,
            corrections_file=corrections_workspace / "data" / "calibration_corrections.yaml",
            n_scenarios=5,
            seed=42,
            quick=True,
        )
        for key in ("real_records", "calibrated_weights", "calibrated_mad",
                    "baseline_mad", "improvement_pct", "mode"):
            assert key in report, f"missing key: {key}"

    def test_real_data_mode_string(self, corrections_workspace, capsys):
        report = run_calibration_real_data(
            edpa_root=corrections_workspace,
            corrections_file=corrections_workspace / "data" / "calibration_corrections.yaml",
            n_scenarios=5,
            seed=0,
            quick=True,
        )
        assert report["mode"] == "real-data blended"
        assert report["real_records"] == 3

    def test_real_data_weights_valid(self, corrections_workspace, capsys):
        report = run_calibration_real_data(
            edpa_root=corrections_workspace,
            corrections_file=corrections_workspace / "data" / "calibration_corrections.yaml",
            n_scenarios=5,
            seed=1,
            quick=True,
        )
        for s, v in report["calibrated_weights"].items():
            assert v >= 0.05, f"{s} weight below floor"
            assert not math.isnan(v), f"NaN weight for {s}"
