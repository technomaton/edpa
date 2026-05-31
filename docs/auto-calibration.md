# Auto-Calibration — Monte Carlo Signal-Weight Optimizer (2.1.8)

*Updated 2026-05-31*

## Principle

One file, one metric, two phases. The CW signal weights are tuned by a
self-contained Monte Carlo + coordinate-descent optimizer that synthesizes
its own corpus — no hand-recorded ground truth required.

```
Target:     .edpa/config/cw_heuristics.yaml (signals: section, 5 weights)
Metric:     mean_absolute_deviation (predicted cw vs synthetic true cw)
Direction:  lower
Optimizer:  .edpa/engine/scripts/calibrate_signals.py (LOCKED — agent must NOT edit)
Corpus:     1000 synthetic team×iteration scenarios, generated in-process
Phases:     (1) MC random sampling → (2) coordinate-descent refinement
```

## Prerequisites

**None for the synthetic path.** The Monte Carlo corpus is generated
in-process every run. There is no `.edpa/data/ground_truth.yaml` file to
populate and no minimum record count to wait for — the optimizer is
runnable at any time, including before the first Planning Interval closes.

If you want to re-tune against *real* delivery data instead of the synthetic
prior, see "Re-run with real data" below — but that path is optional.

## v2 calibration target

The optimizer tunes the **5 signal weights** in
`cw_heuristics.yaml.signals`:

```yaml
signals:
  assignee: 4.0          # ← calibrate
  pr_author: 3.4         # ← calibrate
  commit_author: 2.78    # ← calibrate
  pr_reviewer: 2.25      # ← calibrate
  issue_comment: 1.14    # ← calibrate
```

Manual `/contribute` weights are not calibrated — they're operator-
supplied per directive and carried verbatim as additive signals.

**No role overrides** (the `role_weights` / `role_overrides` matrix was
dropped in v1.11). Strategic-role bias correction (PM/BO/Arch under-weighting
in Git) is addressed purely through signal weight tuning: if BO contributions
are routinely under-credited in the corpus, the optimizer naturally bumps the
`issue_comment` weight (BO's primary signal).

## Optimizer mechanism

`calibrate_signals.py` is self-contained. It generates its own ground truth,
scores candidate weight vectors against it, and (with `--apply`) writes the
winning vector back to the template.

```
Target file:    .edpa/engine/templates/cw_heuristics.yaml.tmpl
Script:         .edpa/engine/scripts/calibrate_signals.py (LOCKED)
                source: plugin/edpa/scripts/calibrate_signals.py
Metric:         mean_absolute_deviation(predicted_cw, true_cw)
                where predicted_cw = Σ weight × signal_count, per-item normalized
Direction:      lower
Search space:   5D, each weight ∈ [0.1, 8.0]
Defaults:       assignee 4.0, pr_author 3.4, commit_author 2.78,
                pr_reviewer 2.25, issue_comment 1.14
```

## Search strategy

```
Phase 1 — Monte Carlo random sampling
  - Sample weight vectors from [0.1, 8.0]^5 (default 2000 samples; 200 if --quick)
  - Score MAD for each against the synthetic corpus
  - Keep the top 5 candidates by MAD

Phase 2 — Coordinate-descent refinement (per top candidate)
  - Refine one weight at a time, holding the others fixed
  - Converges to a local optimum near each candidate

Pick global best across refined candidates
  - When --apply is passed: write winning weights to cw_heuristics.yaml.tmpl
  - Refresh the calibration: metadata block (timestamp, MAD, scenarios, records)
```

A full run (`--scenarios 1000`) materializes ~31 k (person, item) records and
completes in ~10 s. `--quick` runs ~200 MC samples in ~1 s as a smoke test.

## Run

```bash
python3 .edpa/engine/scripts/calibrate_signals.py \
  --scenarios 1000 \
  --seed 42 \
  --apply \
  --report calibration-report.json
```

Flags:

| Flag | Effect |
|------|--------|
| `--scenarios N` | Number of synthetic team×iteration scenarios (default 1000) |
| `--seed` | RNG seed for reproducible corpus + sampling (default 42) |
| `--quick` | Smaller MC sample (~200) — fast smoke test, may not beat baseline |
| `--apply` | Write best weights back to `cw_heuristics.yaml.tmpl` |
| `--report PATH` | Emit a JSON report of the run |

Invoke through the `/edpa:calibrate` skill (edpa-autocalib), which prints the
last calibration metadata, proposes a default run, and applies on confirmation.

## Safety constraints

- **Agent MUST NOT edit `calibrate_signals.py`** — the synthetic corpus
  generator and the MAD cost function live inside the same locked script
  intentionally. Modifying the generator to favor a particular weight vector
  gamifies the metric. The cost function takes only a candidate weight vector
  and pure-reads `signal_count × weight` with per-item normalization.
- **Bounds** — all signal weights in [0.1, 8.0]. Below 0.1 the signal
  effectively never fires; at the top of the range it dominates regardless of
  other evidence.
- **Σ cw = 1.0 invariant** — per-item normalization is structural; the
  optimizer doesn't need to enforce it.
- **Add scenario flavors only for real patterns** — extend the corpus
  generator only to model a real-world contribution pattern it doesn't yet
  cover, and do so in a separate PR, never inside a calibration run.

## Expected results

- The shipped defaults are already near a local optimum on the synthetic
  generator, so a full run typically reports a modest improvement
  (single-digit % MAD reduction) or `+0.0%`. That is expected, not a failure.
- A negative improvement means the corpus generator was edited — revert it.
- Stability check: rerun with 3 different `--seed` values. If the best weights
  agree within ~±0.3, the result is stable. If they diverge, raise
  `--scenarios`.

## Re-run with real data (optional, post-PI)

The synthetic corpus is a *prior*. To improve on it, replace the synthetic
records with team-confirmed CW corrections from a closed PI retrospective:

1. Export per-item engine output from a closed PI (`edpa_results.json`).
2. Run the retrospective; capture team-corrected CW shares.
3. Build records pairing each person's observed signal counts with the
   confirmed CW for that item.
4. Feed those records to the optimizer in place of the synthetic corpus and
   rerun.

This requires a small real-data adapter that is **not yet implemented as a
skill**. Until it ships, run the synthetic MC pipeline and track real
corrections in retros.

## Simulation & Reproduction

Full simulation with 2 PIs, 10 iterations, 7 team members, 510 commits:

- Repository: [technomaton/edpa-simulation](https://github.com/technomaton/edpa-simulation)
- Run: `python scripts/simulate.py --pi all --seed 42`
- Calibration: `python3 .edpa/engine/scripts/calibrate_signals.py --scenarios 1000 --seed 42`
  (5D Monte Carlo + coordinate descent, single-objective, synthetic corpus)
