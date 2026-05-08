#!/usr/bin/env python3
"""
EDPA v1.11 Monte Carlo signal-weight calibrator.

Search space: 5D (assignee, pr_author, commit_author, pr_reviewer,
issue_comment) signal weights from cw_heuristics.yaml.signals.

Procedure:
  1. Generate N synthetic team×iteration scenarios with known "true"
     cw shares per (person, item) and plausible Git-signal patterns
     reflecting those shares (owner has assignee+commits, reviewer
     has pr_reviewer, consulted has issue_comment, etc., with noise).
  2. For each candidate weight vector:
       For each (person, item) record in synthetic data:
         contribution_score = Σ signal_weight × signal_count_for_person
       cw_predicted = score / Σ_persons score (per-item normalization)
       deviation = |cw_predicted - cw_true|
       MAD = mean of deviations across all records
  3. Monte Carlo phase: sample N1 random weight vectors → top-K by MAD
  4. Refinement phase: coordinate descent around each top-K → local
     optimum
  5. Pick global best, write to cw_heuristics.yaml + report.

The synthetic ground truth is built from:
  - Random team of 3-7 people with mixed roles (Dev/Arch/PM/QA/...)
  - Random 5-15 items per scenario
  - Per item: pick 2-5 contributors, distribute true_cw shares
    summing to 1.0 with role-based bias (owner > key > reviewer >
    consulted)
  - Per (person, item, true_cw): emit plausible signal mix:
      true_cw >= 0.5:   assignee + 1-3 commits + pr_author (high prob)
      0.3 <= cw < 0.5:  pr_author + 1-2 commits, sometimes assignee
      0.15 <= cw < 0.3: pr_reviewer + maybe commit, sometimes comment
      cw < 0.15:        issue_comment only
  - Adds noise: swap signals between persons with low probability,
    extra noise commits, etc.

Usage:
    python3 calibrate_signals.py --scenarios 1000 --seed 42
    python3 calibrate_signals.py --scenarios 200 --seed 1 --quick
    python3 calibrate_signals.py --apply  # write to cw_heuristics.yaml

This is the v1.11 replacement for the v1.10 evaluate_cw.py + role-
based calibrator. The locked-vs-tunable separation (evaluator must
not be edited by optimizer) is preserved by structure: this script
contains BOTH the synthetic-truth generator AND the optimizer, but
the cost function inside `evaluate_mad` is a pure read of
contribution_score and per-item normalization — no parameters
inside the cost function itself, only inputs from the candidate
weight vector.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required", file=sys.stderr)
    sys.exit(1)


# ── Synthetic ground-truth generator ───────────────────────────────────────


SIGNAL_TYPES = ["assignee", "pr_author", "commit_author", "pr_reviewer",
                "issue_comment"]
ROLES = ["Dev", "Arch", "PM", "QA", "DevSecOps"]


@dataclass
class SyntheticContribution:
    """One (person, item) record with true cw + observed signal counts."""
    person: str
    role: str
    item_id: str
    true_cw: float
    signal_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class SyntheticScenario:
    team: list[dict]   # [{id, role}]
    items: list[str]
    contributions: list[SyntheticContribution]


def generate_signals(true_cw: float, role: str, rng: random.Random,
                     edge_case: str | None = None) -> dict[str, int]:
    """Emit a plausible signal mix for a person whose true_cw on this
    item is `true_cw`. Roles bias which signals fire (Dev commits,
    PM comments, Arch reviews). `edge_case` injects atypical patterns:

      - 'pm_driven_owner': PM is assignee but has no commits; their
        work shows up as issue_comments + maybe pr_reviewer (specs,
        AC reviews). Models items where PM owns scope, devs implement.
      - 'silent_reviewer': contributor has only pr_reviewer (no
        commits, no comments). Models a tech-review-only role.
      - 'pair_partner': contributor has commits comparable to owner's
        commit count (true_cw similar to ~0.45 each). Models pair
        programming where authorship is split.
      - 'arch_consultant': contributor has many issue_comments + pr
        reviews but no commits, despite cw band being non-trivial.
        Models Arch contribution that's invisible in commit history.

    None means: use the base role-driven signal pattern.
    """
    signals: dict[str, int] = {s: 0 for s in SIGNAL_TYPES}

    if edge_case == "pm_driven_owner":
        # PM as assignee/owner without commits — their work is in
        # specifications, AC, and issue discussions.
        signals["assignee"] += 1
        signals["issue_comment"] += rng.randint(2, 5)
        signals["pr_reviewer"] += rng.choices([0, 1], weights=[0.5, 0.5])[0]
        return signals

    if edge_case == "silent_reviewer":
        # Tech reviewer who reviews PRs without committing or
        # commenting on the issue. Common pattern for Architects.
        signals["pr_reviewer"] += rng.randint(1, 3)
        return signals

    if edge_case == "pair_partner":
        # Pair-programmed with the owner — full commit participation,
        # often co-authored PR, but not the assignee.
        signals["pr_author"] += rng.choices([0, 1], weights=[0.4, 0.6])[0]
        signals["commit_author"] += rng.randint(2, 4)
        signals["issue_comment"] += rng.randint(0, 1)
        return signals

    if edge_case == "arch_consultant":
        # Arch consulted across multiple items: lots of design comments
        # and reviews, no direct commits. true_cw is non-trivial
        # because their input shaped the implementation.
        signals["issue_comment"] += rng.randint(2, 4)
        signals["pr_reviewer"] += rng.randint(1, 2)
        return signals

    # ── Base role-driven pattern (no edge case) ──────────────────

    # Owner band (cw >= 0.5)
    if true_cw >= 0.5:
        signals["assignee"] += 1
        signals["pr_author"] += rng.choices([0, 1], weights=[0.2, 0.8])[0]
        signals["commit_author"] += rng.randint(2, 5)
        signals["issue_comment"] += rng.randint(0, 2)

    # Key band (0.3 <= cw < 0.5)
    elif true_cw >= 0.3:
        signals["pr_author"] += rng.choices([0, 1], weights=[0.3, 0.7])[0]
        signals["commit_author"] += rng.randint(1, 3)
        signals["assignee"] += rng.choices([0, 1], weights=[0.7, 0.3])[0]
        signals["issue_comment"] += rng.randint(0, 2)

    # Reviewer band (0.15 <= cw < 0.3)
    elif true_cw >= 0.15:
        signals["pr_reviewer"] += rng.choices([0, 1, 2], weights=[0.2, 0.6, 0.2])[0]
        signals["commit_author"] += rng.choices([0, 1], weights=[0.6, 0.4])[0]
        signals["issue_comment"] += rng.randint(0, 3)

    # Consulted band (cw < 0.15)
    else:
        signals["issue_comment"] += rng.randint(1, 4)
        signals["pr_reviewer"] += rng.choices([0, 1], weights=[0.85, 0.15])[0]

    # Role bias overlay
    if role == "PM":
        signals["issue_comment"] += rng.randint(0, 2)
    elif role == "Arch":
        signals["pr_reviewer"] += rng.choices([0, 1], weights=[0.5, 0.5])[0]
    elif role == "Dev":
        if true_cw > 0.2:
            signals["commit_author"] += rng.choices([0, 1], weights=[0.6, 0.4])[0]
    elif role == "QA":
        signals["pr_reviewer"] += rng.choices([0, 1], weights=[0.6, 0.4])[0]
    elif role == "DevSecOps":
        signals["pr_reviewer"] += rng.choices([0, 1], weights=[0.7, 0.3])[0]

    return signals


def generate_scenario(scenario_id: int, rng: random.Random) -> SyntheticScenario:
    """Single team×iteration with realistic-ish team and items.

    Each item gets one of these flavors (probability in parentheses):
      - 'normal' (60%): base role-driven signal pattern
      - 'pm_driven' (15%): PM is owner, devs are key/reviewer with commits
      - 'pair_programmed' (10%): two near-equal contributors, both commit
      - 'design_heavy' (10%): Arch consultant + dev implementer pattern
      - 'minimal' (5%): single owner, very small team participation

    Models real-world item heterogeneity better than uniform Dirichlet
    sampling — calibrator sees patterns where signal-to-truth mapping
    varies across item types, forcing weights to generalize rather
    than overfit one mode.
    """
    team_size = rng.randint(3, 7)
    team = []
    for i in range(team_size):
        role = rng.choices(ROLES, weights=[5, 1, 1, 2, 1])[0]
        team.append({"id": f"p{scenario_id}_{i}", "role": role})

    n_items = rng.randint(5, 15)
    items = [f"S-{scenario_id:04d}-{i}" for i in range(n_items)]

    contributions = []
    for item_id in items:
        flavor = rng.choices(
            ["normal", "pm_driven", "pair", "design_heavy", "minimal"],
            weights=[60, 15, 10, 10, 5],
        )[0]

        if flavor == "pair" and team_size >= 3:
            # 2 near-equal contributors (~0.45 each) + 1 reviewer (~0.10)
            picks = rng.sample(team, 3)
            true_cws = [0.45 + rng.uniform(-0.05, 0.05),
                        0.45 + rng.uniform(-0.05, 0.05),
                        0.10]
            # normalize
            s = sum(true_cws); true_cws = [c/s for c in true_cws]
            for idx, (person, true_cw) in enumerate(zip(picks, true_cws)):
                edge = "pair_partner" if idx < 2 else None
                contributions.append(SyntheticContribution(
                    person=person["id"], role=person["role"],
                    item_id=item_id, true_cw=true_cw,
                    signal_counts=generate_signals(true_cw, person["role"], rng, edge_case=edge),
                ))
            continue

        if flavor == "pm_driven":
            # Find PM if any; if no PM, fall back to normal
            pms = [p for p in team if p["role"] == "PM"]
            devs = [p for p in team if p["role"] in ("Dev", "DevSecOps", "QA")]
            if not pms or not devs:
                flavor = "normal"  # graceful fallback
            else:
                pm = rng.choice(pms)
                n_devs = min(rng.randint(1, 3), len(devs))
                dev_picks = rng.sample(devs, n_devs)
                # PM owner ~0.55, devs split ~0.45 among themselves
                pm_cw = 0.50 + rng.uniform(-0.10, 0.05)
                dev_share = 1.0 - pm_cw
                # Distribute dev_share across devs
                dev_raw = sorted([rng.random() for _ in dev_picks], reverse=True)
                dev_total = sum(dev_raw)
                dev_cws = [r / dev_total * dev_share for r in dev_raw]
                contributions.append(SyntheticContribution(
                    person=pm["id"], role="PM", item_id=item_id, true_cw=pm_cw,
                    signal_counts=generate_signals(pm_cw, "PM", rng, edge_case="pm_driven_owner"),
                ))
                for d, cw in zip(dev_picks, dev_cws):
                    contributions.append(SyntheticContribution(
                        person=d["id"], role=d["role"], item_id=item_id,
                        true_cw=cw,
                        signal_counts=generate_signals(cw, d["role"], rng),
                    ))
                continue

        if flavor == "design_heavy":
            # Arch consultant + dev implementer
            archs = [p for p in team if p["role"] == "Arch"]
            devs = [p for p in team if p["role"] in ("Dev", "DevSecOps")]
            if not archs or not devs:
                flavor = "normal"  # fallback
            else:
                arch = rng.choice(archs)
                dev = rng.choice(devs)
                # Dev does ~0.65 of the work, Arch consults ~0.25, maybe one more reviewer ~0.10
                contributions.append(SyntheticContribution(
                    person=dev["id"], role=dev["role"], item_id=item_id, true_cw=0.65,
                    signal_counts=generate_signals(0.65, dev["role"], rng),
                ))
                contributions.append(SyntheticContribution(
                    person=arch["id"], role="Arch", item_id=item_id, true_cw=0.25,
                    signal_counts=generate_signals(0.25, "Arch", rng, edge_case="arch_consultant"),
                ))
                # Optional silent reviewer
                if team_size >= 4:
                    rest = [p for p in team if p not in (arch, dev)]
                    rev = rng.choice(rest)
                    contributions.append(SyntheticContribution(
                        person=rev["id"], role=rev["role"], item_id=item_id, true_cw=0.10,
                        signal_counts=generate_signals(0.10, rev["role"], rng, edge_case="silent_reviewer"),
                    ))
                continue

        if flavor == "minimal":
            # Single owner + maybe 1 small reviewer
            owner = rng.choice(team)
            contributions.append(SyntheticContribution(
                person=owner["id"], role=owner["role"], item_id=item_id, true_cw=0.85,
                signal_counts=generate_signals(0.85, owner["role"], rng),
            ))
            if team_size >= 2 and rng.random() < 0.5:
                rest = [p for p in team if p != owner]
                rev = rng.choice(rest)
                contributions.append(SyntheticContribution(
                    person=rev["id"], role=rev["role"], item_id=item_id, true_cw=0.15,
                    signal_counts=generate_signals(0.15, rev["role"], rng),
                ))
            continue

        # Default: normal Dirichlet-ish flavor
        n_contribs = rng.randint(2, min(5, team_size))
        contribs = rng.sample(team, n_contribs)
        raw = sorted([rng.random() ** 0.5 for _ in range(n_contribs)],
                     reverse=True)
        s = sum(raw)
        true_cws = [r / s for r in raw]
        for person, true_cw in zip(contribs, true_cws):
            contributions.append(SyntheticContribution(
                person=person["id"], role=person["role"], item_id=item_id, true_cw=true_cw,
                signal_counts=generate_signals(true_cw, person["role"], rng),
            ))

    return SyntheticScenario(team=team, items=items, contributions=contributions)


def generate_corpus(n_scenarios: int, seed: int) -> list[SyntheticScenario]:
    rng = random.Random(seed)
    return [generate_scenario(i, rng) for i in range(n_scenarios)]


# ── Cost function (locked — no parameters inside) ─────────────────────────


def evaluate_mad(corpus: list[SyntheticScenario],
                 weights: dict[str, float]) -> tuple[float, int]:
    """For each scenario, compute predicted_cw from signal counts × weights
    using v1.11 sum-and-normalize. Compare to true_cw. Return
    (mean_absolute_deviation, n_records)."""
    total_dev = 0.0
    n = 0
    for scenario in corpus:
        # Group contributions by item to enable per-item normalization
        by_item: dict[str, list[SyntheticContribution]] = {}
        for c in scenario.contributions:
            by_item.setdefault(c.item_id, []).append(c)

        for item_id, contribs in by_item.items():
            scores = []
            for c in contribs:
                score = sum(weights[s] * c.signal_counts.get(s, 0)
                            for s in SIGNAL_TYPES)
                scores.append(score)
            total_score = sum(scores)
            if total_score <= 0:
                continue  # no signals — skip per Q1 edge case
            for c, score in zip(contribs, scores):
                predicted_cw = score / total_score
                total_dev += abs(predicted_cw - c.true_cw)
                n += 1
    if n == 0:
        return float("inf"), 0
    return total_dev / n, n


# ── Optimizers ─────────────────────────────────────────────────────────────


def random_sample_phase(corpus, n_samples: int, seed: int,
                        weight_range: tuple[float, float] = (0.1, 8.0),
                        ) -> list[tuple[float, dict]]:
    """Random-sample phase. Returns list of (mad, weights) sorted by mad."""
    rng = random.Random(seed)
    results = []
    for _ in range(n_samples):
        weights = {s: rng.uniform(*weight_range) for s in SIGNAL_TYPES}
        mad, _ = evaluate_mad(corpus, weights)
        results.append((mad, weights))
    results.sort(key=lambda x: x[0])
    return results


def coordinate_descent(corpus, start_weights: dict[str, float],
                       step: float = 0.5,
                       min_step: float = 0.05,
                       max_iter: int = 50,
                       ) -> tuple[float, dict]:
    """Simple coordinate descent — for each signal, try ±step, pick best.
    Halve step on no-improvement round. Stops at min_step."""
    current = dict(start_weights)
    current_mad, _ = evaluate_mad(corpus, current)

    iteration = 0
    while step >= min_step and iteration < max_iter:
        improved = False
        for s in SIGNAL_TYPES:
            base = current[s]
            for delta in (step, -step):
                trial = dict(current)
                trial[s] = max(0.05, base + delta)
                trial_mad, _ = evaluate_mad(corpus, trial)
                if trial_mad < current_mad - 1e-6:
                    current = trial
                    current_mad = trial_mad
                    improved = True
                    break
        if not improved:
            step *= 0.5
        iteration += 1

    return current_mad, current


# ── Driver ─────────────────────────────────────────────────────────────────


def run_calibration(n_scenarios: int, seed: int, quick: bool = False) -> dict:
    """End-to-end: generate corpus, baseline, MC sample, refine, return report."""
    print(f"Generating {n_scenarios} synthetic scenarios (seed={seed})...")
    corpus = generate_corpus(n_scenarios, seed)
    n_records = sum(len(s.contributions) for s in corpus)
    print(f"  → {n_records} (person, item) records across {n_scenarios} scenarios")

    # Baseline = current cw_heuristics defaults (v1.11 edge-case-trained).
    # Calibration runs measure improvement over the current shipped values.
    defaults = {
        "assignee": 4.0,
        "pr_author": 3.4,
        "commit_author": 2.78,
        "pr_reviewer": 2.25,
        "issue_comment": 1.14,
    }
    baseline_mad, _ = evaluate_mad(corpus, defaults)
    print(f"\nBaseline (v1.11 shipped defaults): MAD = {baseline_mad:.4f}")

    # Phase 1 — Monte Carlo random sampling
    n_samples = 200 if quick else 2000
    print(f"\nPhase 1 — Monte Carlo random sampling ({n_samples} samples)...")
    mc_results = random_sample_phase(corpus, n_samples, seed)
    top_k = 5
    print(f"  Top {top_k} candidates by MAD:")
    for i, (mad, w) in enumerate(mc_results[:top_k], 1):
        ws = " ".join(f"{s}={v:.2f}" for s, v in w.items())
        print(f"    {i}. MAD={mad:.4f}  ({ws})")

    # Phase 2 — Coordinate-descent refinement on top candidates
    print(f"\nPhase 2 — Coordinate descent refinement...")
    refined = []
    for i, (start_mad, start_weights) in enumerate(mc_results[:top_k], 1):
        mad, weights = coordinate_descent(corpus, start_weights)
        print(f"  Cand {i}: {start_mad:.4f} → {mad:.4f} after refinement")
        refined.append((mad, weights))
    refined.sort(key=lambda x: x[0])

    best_mad, best_weights = refined[0]
    improvement = (baseline_mad - best_mad) / baseline_mad * 100

    print(f"\n{'═' * 60}")
    print(f"Best calibrated weights (MAD = {best_mad:.4f}):")
    for s, v in best_weights.items():
        print(f"  {s}: {v:.3f}")
    print(f"\nMAD improvement: {baseline_mad:.4f} → {best_mad:.4f} "
          f"({improvement:+.1f}%)")
    print(f"{'═' * 60}")

    return {
        "n_scenarios": n_scenarios,
        "n_records": n_records,
        "seed": seed,
        "baseline_weights": defaults,
        "baseline_mad": baseline_mad,
        "calibrated_weights": best_weights,
        "calibrated_mad": best_mad,
        "improvement_pct": improvement,
        "method": "MC random-sample + coordinate descent",
    }


def apply_to_heuristics(report: dict, target: Path):
    """Write calibrated weights into cw_heuristics.yaml.tmpl, preserving
    the rest of the file and updating calibration metadata."""
    if not target.exists():
        print(f"ERROR: target {target} not found", file=sys.stderr)
        sys.exit(2)

    text = target.read_text(encoding="utf-8")
    weights = report["calibrated_weights"]

    # Re-emit the signals: block (5 keys, fixed order)
    new_signals_block = (
        "signals:\n"
        f"  assignee: {weights['assignee']:.2f}             # GitHub issue assignee\n"
        f"  pr_author: {weights['pr_author']:.2f}            # PR author referencing item\n"
        f"  commit_author: {weights['commit_author']:.2f}        # Commit with item ID in branch/title/msg\n"
        f"  pr_reviewer: {weights['pr_reviewer']:.2f}          # PR review submitted (excluding self)\n"
        f"  issue_comment: {weights['issue_comment']:.2f}        # Comment on issue/PR (excluding bots)\n"
    )

    import re
    text2 = re.sub(
        r'signals:\s*\n(?:  \w+:.*\n)+',
        new_signals_block,
        text,
        count=1,
    )

    # Update calibration metadata
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    calib_block = (
        f'calibration:\n'
        f'  method: "{report["method"]}"\n'
        f'  monte_carlo:\n'
        f'    scenarios: {report["n_scenarios"]}\n'
        f'    records: {report["n_records"]}\n'
        f'  ground_truth_records: 0   # synthetic baseline; re-run with real data after first PI\n'
        f'  mad_baseline: {report["baseline_mad"]:.4f}\n'
        f'  mad_calibrated: {report["calibrated_mad"]:.4f}\n'
        f'  improvement_pct: {report["improvement_pct"]:.1f}\n'
        f'  calibrated_at: "{now}"\n'
        f'  calibrated_by_version: "1.11.0"\n'
        f'  notes: |\n'
        f'    Synthetic Monte Carlo baseline ({report["n_scenarios"]} scenarios,\n'
        f'    {report["n_records"]} records). Ground truth was generated\n'
        f'    procedurally from a model where signal counts probabilistically\n'
        f'    reflect each person\'s true cw share with role-based bias.\n'
        f'    Re-run /edpa:calibrate after first real PI close with team-confirmed\n'
        f'    cw records to derive a real-data baseline.\n'
    )
    text2 = re.sub(
        r'calibration:\s*\n(?:  .+\n)+(?:    .+\n)*',
        calib_block,
        text2,
        count=1,
    )

    target.write_text(text2, encoding="utf-8")
    print(f"\n✓ Calibrated weights written to {target}")


def main():
    ap = argparse.ArgumentParser(
        description="EDPA v1.11 Monte Carlo signal-weight calibrator"
    )
    ap.add_argument("--scenarios", type=int, default=1000,
                    help="Number of synthetic team×iteration scenarios (default 1000)")
    ap.add_argument("--seed", type=int, default=42,
                    help="RNG seed for reproducibility")
    ap.add_argument("--quick", action="store_true",
                    help="Smaller MC sample (200 instead of 2000) — faster, less accurate")
    ap.add_argument("--apply", action="store_true",
                    help="Write calibrated weights to plugin/edpa/templates/cw_heuristics.yaml.tmpl")
    ap.add_argument("--report", type=Path, default=None,
                    help="Optional path to write JSON calibration report")
    args = ap.parse_args()

    report = run_calibration(args.scenarios, args.seed, quick=args.quick)

    if args.report:
        args.report.write_text(json.dumps(report, indent=2, default=str),
                               encoding="utf-8")
        print(f"\n✓ Report written to {args.report}")

    if args.apply:
        target = Path(__file__).parent.parent / "templates" / "cw_heuristics.yaml.tmpl"
        apply_to_heuristics(report, target)


if __name__ == "__main__":
    main()
