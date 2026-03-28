# Auto-Calibration — Karpathy Autoresearch Loop

## Principle

One file, one metric, one loop. Inspired by Karpathy's autoresearch pattern.

```
Target:     .edpa/config/heuristics.yaml
Metric:     mean_absolute_deviation (auto CW vs ground truth)
Direction:  lower
Budget:     50-100 experiments (configurable)
Memory:     git log on calibration branch
Evaluator:  .claude/edpa/scripts/evaluate_cw.py (LOCKED — agent must NOT edit)
```

## Prerequisites

- ≥ 20 manually confirmed CW records in `.edpa/data/ground_truth.yaml`
- Typically available after 1st Planning Interval (~10 weeks, 4-5 iterations)
- Records come from team retrospectives where auto-CW is compared to reality

## Calibration Results (Simulation-Validated)

Multi-scenario calibration across 8 team compositions (569 person-item pairs)
and full 2-PI simulation (172 ground truth records) produced these findings:

### Systematic Biases in Auto-Detection

| Role | Evidence | Original CW | Confirmed CW | Bias | Correction Rate |
|------|----------|-------------|--------------|------|-----------------|
| **BO** | consulted | 0.15 | 0.32 | **+0.17** | 80% |
| **PM** | consulted | 0.15 | 0.29 | **+0.14** | 61% |
| **Arch** | reviewer | 0.25 | 0.36 | **+0.11** | 58% |
| Dev | owner | 1.00 | 1.00 | 0.00 | 0% |
| Dev | key | 0.60 | 0.60 | 0.00 | 0% |
| DevSecOps | owner | 1.00 | 1.00 | 0.00 | 0% |
| **QA** | owner | 1.00 | 0.90 | **−0.10** | 25% |

**Key insight:** Git signals measure *activity*, not *value*. Roles that contribute
strategically (BO decisions, PM requirements, Arch reviews) are systematically
undervalued. QA is slightly overvalued (many test commits ≠ ownership).

### Recommended Defaults (role_overrides)

Applied in `.claude/edpa/templates/heuristics.yaml.tmpl`:

```yaml
role_overrides:
  BO:
    consulted: 0.30    # was 0.15, ★ 52.9% MAD improvement
    reviewer: 0.35
  PM:
    consulted: 0.25    # was 0.15, ● 16.0% MAD improvement
  Arch:
    reviewer: 0.30     # was 0.25, ● 7.4% MAD improvement
  QA:
    key: 0.55          # was 0.60
    owner: 0.95        # was 1.00 (cautious — small sample)
```


### Monte Carlo Validation (1000 scenarios, 68,156 records)

The calibration results were validated by Monte Carlo simulation with 1000
randomly generated team compositions (4-15 members, random role distributions).
All biases are statistically significant (p < 0.001).

| Role | Evidence | N | Auto CW | Median Confirmed | Bias | Corr% | Confidence |
|------|----------|---|---------|------------------|------|-------|------------|
| BO | consulted | 1,597 | 0.15 | **0.30** | +0.16 | 74.4% | HIGH |
| BO | reviewer | 341 | 0.25 | **0.35** | +0.10 | 61.0% | MEDIUM |
| PM | consulted | 6,304 | 0.15 | **0.20** | +0.11 | 59.7% | HIGH |
| PM | reviewer | 1,213 | 0.25 | 0.25 | +0.04 | 45.6% | HIGH |
| Arch | reviewer | 3,120 | 0.25 | **0.30** | +0.10 | 55.4% | HIGH |
| Dev | owner | 18,472 | 1.00 | 1.00 | -0.01 | 5.1% | HIGH |
| Dev | key | 15,078 | 0.60 | 0.60 | +0.02 | 15.0% | HIGH |
| DevSecOps | reviewer | 1,275 | 0.25 | 0.25 | +0.05 | 40.2% | HIGH |
| QA | key | 2,966 | 0.60 | 0.60 | -0.04 | 25.9% | HIGH |

Percentile distribution of confirmed CW for key corrections:
- **BO consulted:** p5=0.15, p25=0.15, **p50=0.30**, p75=0.40, p95=0.50
- **PM consulted:** p5=0.15, p25=0.15, **p50=0.20**, p75=0.30, p95=0.50
- **Arch reviewer:** p5=0.25, p25=0.25, **p50=0.30**, p75=0.40, p95=0.60

Monte Carlo script: `python scripts/monte_carlo_calibration.py --scenarios 1000 --seed 42`

### MAD Impact

```
Original defaults:             MAD = 0.0375  [██████████████████████] baseline
Calibrated (8 scenarios):      MAD = 0.0314  [██████████████████] ↓16.3%
Recommended (calib+simulation): MAD = 0.0326  [██████████████████] ↓13.2%

PI-1 → PI-2 trend:             MAD = 0.0412 → 0.0333  ↓19.2%
Correction rate trend:          18.7% → 14.8% (fewer corrections = better heuristic)
```

### Per-Role MAD Improvement

| Role | MAD (original) | MAD (calibrated) | Improvement |
|------|---------------|-----------------|-------------|
| BO | 0.1700 | 0.0800 | **52.9%** ★ |
| PM | 0.1190 | 0.1000 | **16.0%** ● |
| Arch | 0.0482 | 0.0446 | **7.4%** ● |
| Dev | 0.0000 | 0.0000 | 0.0% (already perfect) |
| DevSecOps | 0.0000 | 0.0000 | 0.0% (already perfect) |

## Loop

```
1. git checkout -b calibration/{timestamp}
2. for experiment in 1..budget:
     a. Read current heuristics + experiment history
     b. Propose ONE parameter change (threshold, weight, signal score)
     c. git commit -m "exp {n}: {param} {old} -> {new}"
     d. Run: python .claude/edpa/scripts/evaluate_cw.py --ground-truth .edpa/data/ground_truth.yaml --heuristics .edpa/config/heuristics.yaml
     e. Parse MAD from output
     f. If MAD < previous_best: KEEP (advance branch)
        Else: git reset --hard HEAD~1 (revert)
     g. Log to .edpa/data/calibration_log.tsv
3. Print summary: initial MAD, final MAD, % improvement, optimized params
4. Ask user: merge calibration branch into main?
```

## Safety constraints

- **Agent MUST NOT edit .claude/edpa/scripts/evaluate_cw.py** — separation of optimizer from objective
- **One change per experiment** — if you change 5 things, you don't know what worked
- **Ordering preserved** — owner ≥ key ≥ reviewer ≥ consulted
- **Bounds** — all weights in [0.05, 1.0], threshold in [0.5, 3.0]

## Strategy escalation

- Experiments 1-10: role_weights (biggest impact, 4 parameters)
- Experiments 11-25: signal weights (6 parameters)
- Experiments 26-50: threshold + combined fine-tuning
- Every 10 experiments: review patterns in calibration_log.tsv

## Expected results

- Typical improvement: 13-20% MAD reduction (validated by simulation)
- BO/PM/Arch: largest improvement (strategic roles undervalued by Git signals)
- Dev/DevSecOps: minimal change needed (Git signals already accurate)
- After 50 experiments: heuristic closely matches team's actual allocation patterns
- Diminishing returns after ~30 experiments for most teams

## Simulation & Reproduction

Full simulation with 2 PIs, 10 iterations, 7 team members, 510 commits:
- Repository: [technomaton/edpa-simulation](https://github.com/technomaton/edpa-simulation)
- Run: `python scripts/simulate.py --pi all --seed 42`
- Calibration: `python scripts/calibrate_roles.py` (8 scenarios, 569 pairs)
