---
description: Auto-calibrate EDPA CW heuristics
allowed-tools: Read, Write, Bash, Grep
model: sonnet
---

# EDPA Calibrate

Invoke the `edpa-autocalib` skill to optimize CW **signal weights** in
`plugin/edpa/templates/cw_heuristics.yaml.tmpl` via Monte Carlo random sampling
+ coordinate descent (v1.11+). The optimizer drives
`plugin/edpa/scripts/calibrate_signals.py`, which generates its own synthetic
ground-truth corpus — no `.edpa/data/ground_truth.yaml` is needed.

Pass arguments to forward to the script: `quick`, `apply`, an integer for
`--scenarios`, or raw flags. Empty argument shows the last calibration
metadata and proposes a default run.

Legacy note: the v1.10 `role_weights`/`role_overrides` schema and
`evaluate_cw.py` autoresearch loop are deprecated — the engine ignores them.
