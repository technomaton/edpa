# Auto-Calibration — Karpathy Autoresearch Loop (v1.11)

## Principle

One file, one metric, one loop. Inspired by Karpathy's autoresearch
pattern.

```
Target:     .edpa/config/cw_heuristics.yaml (signals: section, 5 weights)
Metric:     mean_absolute_deviation (computed cw vs ground-truth cw)
Direction:  lower
Budget:     50–100 experiments (configurable)
Memory:     git log on calibration branch
Evaluator:  .claude/edpa/scripts/evaluate_cw.py (LOCKED — agent must NOT edit)
```

## Prerequisites

- ≥ 20 manually confirmed CW records in `.edpa/data/ground_truth.yaml`
- Typically available after 1st Planning Interval (~10 weeks, 4–5
  iterations)
- Records come from team retrospectives where computed `cw` (per-item
  share) is compared to team consensus

## v1.11 calibration target

The calibration tunes the **5 signal weights** in
`cw_heuristics.yaml.signals`:

```yaml
signals:
  assignee: 4.0          # ← calibrate
  pr_author: 2.0         # ← calibrate
  commit_author: 1.0     # ← calibrate
  pr_reviewer: 1.0       # ← calibrate
  issue_comment: 0.5     # ← calibrate
```

Manual `/contribute` weights are not calibrated — they're operator-
supplied per directive.

**No role overrides** (v1.10's `role_overrides` matrix was dropped in
v1.11). Strategic-role bias correction (PM/BO/Arch under-weighting in
Git) is now addressed purely through signal weight tuning: if BO
contributions are routinely under-credited, calibrator naturally
bumps `issue_comment` weight (BO's primary signal) to match ground
truth. If a small-pilot calibration shows persistent bias, per-role
signal multipliers may return in v1.12 as a calibration extension.

## Search strategy

```
Phase 1 — Monte Carlo random sampling (5–10 experiments)
  - Sample 5 weight combinations from [0.5, 8.0]^5
  - Evaluate MAD for each
  - Pick top 3 candidates by MAD

Phase 2 — Nelder-Mead refinement (per top candidate)
  - Local downhill simplex around each candidate
  - Converges in ~10–20 evaluations per starting point
  - Yields local optimum near the candidate

Phase 3 — Pick global best across refined candidates
  - Commit winning weights to cw_heuristics.yaml
  - Append calibration metadata (timestamp, MAD, sample count)
```

Total experiment budget: ~50 evaluations for 5D search. Each
evaluation is ~1 second of compute on a typical project (re-run
detect_contributors aggregation against ground truth). Wall-clock
~minute, fits comfortably in a single CI job.

## Loop

```
1. git checkout -b calibration/{timestamp}
2. for experiment in 1..budget:
     a. Read current heuristics + experiment history
     b. Propose ONE parameter change (one signal weight)
     c. git commit -m "exp {n}: signals.{name} {old} -> {new}"
     d. Run: python .claude/edpa/scripts/evaluate_cw.py \
              --ground-truth .edpa/data/ground_truth.yaml \
              --heuristics .edpa/config/cw_heuristics.yaml
     e. Parse MAD from output
     f. If MAD < previous_best: KEEP (advance branch)
        Else: git reset --hard HEAD~1 (revert)
     g. Log to .edpa/data/calibration_log.tsv
3. Print summary: initial MAD, final MAD, % improvement, optimized weights
4. Ask user: merge calibration branch into main?
```

## Safety constraints

- **Agent MUST NOT edit `evaluate_cw.py`** — separation of optimizer
  from objective. The evaluator is the ground truth function; modifying
  it during calibration is gradient hacking, not legitimate tuning.
- **One change per experiment** — if you change 5 things, you don't
  know what worked. Single-coordinate descent yields interpretable
  history.
- **Ordering soft constraint** — calibrator should prefer weights
  where `assignee ≥ pr_author ≥ commit_author ≈ pr_reviewer ≥
  issue_comment`. Reversed orderings (e.g., `issue_comment >
  assignee`) typically indicate ground truth pollution or bot/spam
  comments not filtered out.
- **Bounds** — all signal weights in [0.1, 10.0]. Below 0.1 the
  signal effectively never fires; above 10.0 it dominates regardless
  of other evidence.
- **Σ cw = 1.0 invariant** — the per-item normalization is
  structural; calibrator doesn't need to enforce it.

## Expected results (v1.11)

- Typical improvement: 10–20% MAD reduction vs starting defaults
  (depends on team composition; Dev-heavy teams converge faster
  because Git signals already accurate)
- Strategic-heavy teams (BO/PM/Arch) typically see `issue_comment`
  weight rise from 0.5 → 0.8–1.5 in calibration
- After 50 experiments: heuristics closely match team's actual
  allocation patterns
- Diminishing returns after ~30 experiments for most teams

## Pre-v1.11 calibration data

Pre-v1.11 calibrations operated on a different parameter space (role
weights + role overrides + signal weights = 11+ parameters). Those
results are **not directly comparable** to v1.11 (5 parameters,
additive signal aggregation). Re-run calibration after first PI close
on v1.11 to establish the new baseline.

## Simulation & Reproduction

Full simulation with 2 PIs, 10 iterations, 7 team members, 510 commits:

- Repository: [technomaton/edpa-simulation](https://github.com/technomaton/edpa-simulation)
- Run: `python scripts/simulate.py --pi all --seed 42`
- Calibration: `python scripts/calibrate_signals.py` (5D Monte Carlo
  + Nelder-Mead, single-objective)
