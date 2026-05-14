---
name: edpa:autocalib
user-invocable: true
description: >
  Auto-calibrate EDPA CW signal weights using the Monte Carlo + coordinate-descent
  optimizer (v1.11+). One target file (cw_heuristics.yaml.tmpl), one metric (MAD
  on a synthetic corpus), two phases (random sample → coordinate descent). Use
  when: user says "calibrate CW", "auto-calibrate", "optimize heuristics",
  "recalibrate signals". Synthetic corpus — runnable any time, no ground-truth
  file required. Re-run after a real PI close once team-confirmed CW corrections
  are available (see "Re-run with real data" below).
license: MIT
compatibility: Python 3.10+, git, plugin/edpa/scripts/calibrate_signals.py
allowed-tools: Read Write Bash(python3 *) Bash(git *) Grep
disable-model-invocation: false
metadata:
  author: Jaroslav Urbánek
  version: 2.0.0
  domain: governance
  phase: auto-calibration
  pattern: Monte Carlo + coordinate descent
  standard: AgentSkills v1.0
---

# EDPA Auto-Calibration — Monte Carlo signal-weight optimizer

## What this does

Optimizes the five **signal weights** (`assignee`, `pr_author`, `commit_author`,
`pr_reviewer`, `issue_comment`) in `plugin/edpa/templates/cw_heuristics.yaml.tmpl`
against a synthetic corpus generated procedurally. The engine consumes those
weights directly — there is no `role_weights` or `role_overrides` block any
more (both were dropped in v1.11; see `plugin/edpa/scripts/engine.py:864`).

The optimizer is self-contained: it generates its own ground truth via Monte
Carlo, evaluates candidate weight vectors against it, and writes the best
candidate back into the template when `--apply` is passed.

## Arguments

`$ARGUMENTS` = optional flags forwarded to `calibrate_signals.py`. Common forms:

- empty / `help` → show current calibration metadata, propose a default run
- `quick` → adds `--quick` (200 MC samples; ~1 s; smoke test only)
- a positive integer → `--scenarios <N>` (e.g. `2000`); default `1000`
- `apply` → after calibration, write best weights back to the template
- raw flags (`--scenarios 2000 --seed 7 --apply --report report.json`) →
  passed verbatim

## Argument resolution (when `$ARGUMENTS` is empty)

1. Read the current `calibration:` block from
   `plugin/edpa/templates/cw_heuristics.yaml.tmpl` and print:
   ```
   Last calibration:
     method:        MC random-sample + coordinate descent
     scenarios:     1000   records: 31041
     baseline MAD:  0.0861
     calibrated:    0.0805 (+6.5%)
     version:       1.11.0
     timestamp:     2026-05-08T18:37:24Z
   ```
2. Suggest defaults:
   ```
   Suggested run:
     python3 plugin/edpa/scripts/calibrate_signals.py \
       --scenarios 1000 --seed 42

   Apply best weights to the template? [N]
   ```
3. Wait for user confirmation (run / apply / change scenarios / cancel).

## Prerequisites

**None for the synthetic path.** The MC corpus is generated in-process; no
`.edpa/data/ground_truth.yaml` is needed. The legacy `role_weights` /
`role_overrides` schema and the `evaluate_cw.py` autoresearch evaluator
were removed in v1.18.2.

If the user explicitly asks to calibrate against *real* PI data, fall through
to "Re-run with real data" below.

## Configuration

```
Target file:    plugin/edpa/templates/cw_heuristics.yaml.tmpl
Script:         plugin/edpa/scripts/calibrate_signals.py (LOCKED)
Metric:         mean_absolute_deviation(predicted_cw, true_cw)
                where predicted_cw = Σ weight × signal_count, per-item normalized
Direction:      lower
Phases:         (1) MC random sampling   default 2000 samples (200 if --quick)
                (2) coordinate descent   refines top-5 candidates
Search space:   5D, each weight ∈ [0.1, 8.0]
Defaults:       assignee 4.0, pr_author 3.4, commit_author 2.78,
                pr_reviewer 2.25, issue_comment 1.14
```

**CRITICAL: never edit `calibrate_signals.py`.** The synthetic corpus generator
and the MAD cost function are inside the same script *intentionally* — the
locked-vs-tunable separation is preserved by structure: the cost function takes
only a candidate weight vector and pure-reads `signal_count × weight` with
per-item normalization (no parameters live inside the cost function itself).
If you are tempted to modify the generator to match a particular weight
vector, STOP — that gamifies the metric. Add new scenario flavors only when
they reflect a real-world contribution pattern the corpus does not yet model,
and even then file a separate PR — not inside a calibration run.

## Run

### Step 1 — Execute

```bash
python3 plugin/edpa/scripts/calibrate_signals.py \
  --scenarios "${SCENARIOS:-1000}" \
  --seed "${SEED:-42}" \
  ${QUICK:+--quick} \
  ${APPLY:+--apply} \
  ${REPORT:+--report "$REPORT"}
```

Expected stdout (abridged):
```
Generating 1000 synthetic scenarios (seed=42)...
  → 31041 (person, item) records across 1000 scenarios
Baseline (v1.11 shipped defaults): MAD = 0.0861
Phase 1 — Monte Carlo random sampling (2000 samples)...
  Top 5 candidates by MAD: ...
Phase 2 — Coordinate descent refinement...
  Cand 1: 0.0820 → 0.0805 after refinement
  ...
Best calibrated weights (MAD = 0.0805):
  assignee: 4.00
  pr_author: 3.40
  ...
MAD improvement: 0.0861 → 0.0805 (+6.5%)
```

### Step 2 — Report

Summarize the run to the user:
- baseline MAD, calibrated MAD, % improvement
- which weights moved most (delta from defaults)
- whether `--apply` was used (template updated or not)

### Step 3 — Apply (only if requested)

When the user passed `apply`, `calibrate_signals.py --apply` has already
rewritten the template `signals:` block and refreshed the `calibration:`
metadata. Confirm by re-reading the target file's `calibration:` block and
echoing `mad_calibrated` and `calibrated_at`.

If not applied, leave the template untouched and tell the user how to apply
later:
```
Re-run with: python3 plugin/edpa/scripts/calibrate_signals.py --apply
```

## Re-run with real data (post-first-PI)

The MC corpus is a *prior*: it encodes plausible signal/cw mappings under
v1.11's procedural model. To improve on it, replace synthetic
`SyntheticContribution` records with team-confirmed corrections from a closed
PI retrospective.

Today this requires a small adapter (not yet implemented as a skill):

1. Export per-item engine output from a closed PI (`edpa_results.json`).
2. Run the retrospective; capture team-corrected CW shares.
3. Build a list of
   `SyntheticContribution(person, role, item_id, true_cw=<confirmed_cw>,
   signal_counts=<observed_counts_from_engine>)`.
4. Replace `generate_corpus(...)` with the loaded real corpus and rerun the
   optimizer.

If the user asks for this flow now, refuse with: "Real-data calibration adapter
not yet implemented. Run the synthetic MC pipeline first; track real
corrections in retros until the adapter ships."

## Strategy guidance

- Smoke test / CI gate: `--scenarios 200 --quick` (~1 s; may not improve over
  baseline, that's fine).
- Honest calibration: `--scenarios 1000 --seed 42` (~10 s; 31 k records).
- Thorough run: `--scenarios 2000 --seed 42 --apply` (~30 s).
- Stability check: rerun with 3 different `--seed` values. If best weights
  agree within ~±0.3, the result is stable. If they diverge, raise
  `--scenarios`.

## Error handling

- `calibrate_signals.py` missing → check `plugin/edpa/scripts/`; do not
  recreate from template. Tell the user the plugin install is incomplete.
- Template file missing → same; do not synthesize. Point to plugin install
  state.
- `MAD improvement: +0.0%` after a full run → expected; the shipped defaults
  are already near a local optimum on the v1.11 generator. Higher
  `--scenarios` rarely changes this.
- Negative improvement → corpus generator was edited; revert that change.
