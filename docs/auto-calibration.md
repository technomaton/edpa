# Auto-Calibration — Karpathy Autoresearch Loop

## Principle

One file, one metric, one loop. Inspired by Karpathy's autoresearch pattern.

```
Target:     config/cw_heuristics.yaml
Metric:     mean_absolute_deviation (auto CW vs ground truth)
Direction:  lower
Budget:     50-100 experiments (configurable)
Memory:     git log on calibration branch
Evaluator:  scripts/evaluate_cw.py (LOCKED — agent must NOT edit)
```

## Prerequisites

- ≥ 20 manually confirmed CW records in `data/ground_truth.yaml`
- Typically available after 1st Planning Interval (~10 weeks, 4-5 iterations)
- Records come from team retrospectives where auto-CW is compared to reality

## Loop

```
1. git checkout -b calibration/{timestamp}
2. for experiment in 1..budget:
     a. Read current heuristics + experiment history
     b. Propose ONE parameter change (threshold, weight, signal score)
     c. git commit -m "exp {n}: {param} {old} -> {new}"
     d. Run: python scripts/evaluate_cw.py --ground-truth data/ground_truth.yaml --heuristics config/cw_heuristics.yaml
     e. Parse MAD from output
     f. If MAD < previous_best: KEEP (advance branch)
        Else: git reset --hard HEAD~1 (revert)
     g. Log to data/calibration_log.tsv
3. Print summary: initial MAD, final MAD, % improvement, optimized params
4. Ask user: merge calibration branch into main?
```

## Safety constraints

- **Agent MUST NOT edit scripts/evaluate_cw.py** — separation of optimizer from objective
- **One change per experiment** — if you change 5 things, you don't know what worked
- **Ordering preserved** — owner ≥ key ≥ reviewer ≥ consulted
- **Bounds** — all weights in [0.05, 1.0], threshold in [0.5, 3.0]

## Strategy escalation

- Experiments 1-10: role_weights (biggest impact, 4 parameters)
- Experiments 11-25: signal weights (6 parameters)
- Experiments 26-50: threshold + combined fine-tuning
- Every 10 experiments: review patterns in calibration_log.tsv

## Expected results

- Typical improvement: 15-30% MAD reduction
- After 50 experiments: heuristic closely matches team's actual allocation patterns
- Diminishing returns after ~30 experiments for most teams
