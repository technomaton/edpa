#!/usr/bin/env python3
"""
EDPA gate_weights sensitivity analysis.

Engine math (per plugin/edpa/scripts/engine.py:716–820):
  For each detected status transition, the engine emits a synthetic event
  with effective_js = parent.js * gate_weights[item_type][transition], then
  credits parent.contributors[] (cw shares) proportionally to effective_js.

Per-person credit on a PI is:
  credit[person] = Σ_events  effective_js[event] * cw[person, event.parent]

Sensitivity question: when one gate_weight perturbs ±20%, how much does the
per-person credit distribution shift? High-impact weights deserve team
discussion; low-impact weights can be left at defaults.

Two perturbation modes:
  - rebalanced (default): Δw on one gate, -Δw spread across other gates of
    the same item_type so the per-type sum stays 1.0. Models the practical
    case where a team retunes weights together.
  - naked (--naked): perturb one weight, leave others unchanged. Sum drifts
    away from 1.0. Models the typo case ("what if I mistype one weight").

Run:
  python3 tools/sensitivity_check.py
  python3 tools/sensitivity_check.py --naked
  python3 tools/sensitivity_check.py --seed 7 --pi-size 40
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required", file=sys.stderr)
    sys.exit(1)


TEMPLATE_PATH = Path("plugin/edpa/templates/cw_heuristics.yaml.tmpl")


# Gate paths per item type. Order matters — gates fire in sequence as items
# progress. Must match plugin/edpa/templates/cw_heuristics.yaml.tmpl.
GATE_PATHS = {
    "Feature": [
        "Funnel→Analyzing",
        "Analyzing→Backlog",
        "Backlog→Implementing",
        "Implementing→Validating",
        "Validating→Deploying",
        "Deploying→Releasing",
        "Releasing→Done",
    ],
    "Epic": [
        "Funnel→Reviewing",
        "Reviewing→Analyzing",
        "Analyzing→Ready",
        "Ready→Implementing",
        "Implementing→Done",
    ],
    "Initiative": [
        "Funnel→Reviewing",
        "Reviewing→Analyzing",
        "Analyzing→Ready",
        "Ready→Implementing",
        "Implementing→Done",
    ],
}

ROLES = ["Dev", "Arch", "PM", "QA", "DevSecOps"]


def load_gate_weights(template_path):
    data = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    gw = data.get("gate_weights", {}) or {}
    # Deep copy + cast to float
    out = {}
    for item_type, weights in gw.items():
        out[item_type] = {k: float(v) for k, v in weights.items()}
    return out


# ── Synthetic PI scenario ─────────────────────────────────────────────────


def build_team(n_people, rng):
    return [
        {"id": f"p{i}", "role": rng.choices(ROLES, weights=[5, 1, 2, 1, 1])[0]}
        for i in range(n_people)
    ]


def random_contributor_split(team, rng):
    """Pick 2–4 contributors with cw shares summing to 1.0."""
    n = rng.randint(2, min(4, len(team)))
    picks = rng.sample(team, n)
    raw = sorted([rng.random() ** 0.5 for _ in range(n)], reverse=True)
    s = sum(raw)
    cws = [r / s for r in raw]
    return [{"person": p["id"], "cw": cw} for p, cw in zip(picks, cws)]


def build_pi_items(team, n_features, n_epics, n_init, rng):
    """Generate items + which gates fired for each, within the PI window."""
    items = []

    for i in range(n_features):
        # How far through the gate path did this Feature progress in the PI?
        path = GATE_PATHS["Feature"]
        # Most Features advance 1–4 gates per PI; some go all the way; some stall
        n_gates = rng.choices(
            [0, 1, 2, 3, 4, 5, 6, 7],
            weights=[5, 25, 25, 20, 12, 6, 4, 3],
        )[0]
        # Where in the path did it start?
        start = rng.randint(0, max(0, len(path) - n_gates))
        gates_fired = path[start:start + n_gates]
        items.append({
            "type": "Feature",
            "id": f"F-{i:03d}",
            "js": rng.uniform(8, 40),
            "contributors": random_contributor_split(team, rng),
            "gates_fired": gates_fired,
        })

    for i in range(n_epics):
        path = GATE_PATHS["Epic"]
        n_gates = rng.choices([0, 1, 2, 3, 4, 5], weights=[10, 30, 25, 20, 10, 5])[0]
        start = rng.randint(0, max(0, len(path) - n_gates))
        items.append({
            "type": "Epic",
            "id": f"E-{i:03d}",
            "js": rng.uniform(40, 120),
            "contributors": random_contributor_split(team, rng),
            "gates_fired": path[start:start + n_gates],
        })

    for i in range(n_init):
        path = GATE_PATHS["Initiative"]
        n_gates = rng.choices([0, 1, 2, 3], weights=[20, 40, 30, 10])[0]
        start = rng.randint(0, max(0, len(path) - n_gates))
        items.append({
            "type": "Initiative",
            "id": f"I-{i:03d}",
            "js": rng.uniform(100, 300),
            "contributors": random_contributor_split(team, rng),
            "gates_fired": path[start:start + n_gates],
        })

    return items


# ── Engine math (subset — only gate events) ───────────────────────────────


def credit_per_person(items, weights):
    """Σ_events effective_js × cw[person]. Matches engine load_gate_events
    math: each fired gate emits an event with effective_js = parent.js × weight,
    contributors inherit parent.contributors[] verbatim."""
    credit = {}
    for item in items:
        item_w = weights.get(item["type"], {})
        for gate_key in item["gates_fired"]:
            w = item_w.get(gate_key, 0.0)
            if w <= 0:
                continue
            effective_js = item["js"] * w
            for c in item["contributors"]:
                credit[c["person"]] = credit.get(c["person"], 0.0) + effective_js * c["cw"]
    return credit


def normalize(credit):
    total = sum(credit.values()) or 1.0
    return {p: c / total for p, c in credit.items()}


# ── Perturbation ──────────────────────────────────────────────────────────


def perturb_rebalanced(weights, item_type, gate_key, factor):
    """Multiply one weight by `factor`, redistribute the delta across the
    other gates of the same item_type proportionally to their current value.
    Per-type sum stays 1.0."""
    out = {t: dict(g) for t, g in weights.items()}
    g = out[item_type]
    old = g[gate_key]
    new = old * factor
    delta = new - old  # how much we added (or removed) to this weight

    other_keys = [k for k in g if k != gate_key]
    other_sum = sum(g[k] for k in other_keys) or 1e-9
    for k in other_keys:
        share = g[k] / other_sum
        g[k] = max(0.0, g[k] - delta * share)
    g[gate_key] = new
    return out


def perturb_naked(weights, item_type, gate_key, factor):
    """Multiply one weight by `factor`. Other weights untouched. Sum drifts."""
    out = {t: dict(g) for t, g in weights.items()}
    out[item_type][gate_key] *= factor
    return out


# ── Analysis ──────────────────────────────────────────────────────────────


def evaluate_perturbation(items, weights, perturb_fn, item_type, gate_key, factor):
    base = normalize(credit_per_person(items, weights))
    perturbed = normalize(credit_per_person(
        items, perturb_fn(weights, item_type, gate_key, factor)
    ))
    all_people = set(base) | set(perturbed)
    deltas = {p: perturbed.get(p, 0) - base.get(p, 0) for p in all_people}
    return deltas


def classify(max_abs_delta):
    if max_abs_delta >= 0.02:
        return "HIGH"
    if max_abs_delta >= 0.005:
        return "MED"
    return "LOW"


def main():
    ap = argparse.ArgumentParser(description="EDPA gate_weights sensitivity check")
    ap.add_argument("--template", type=Path, default=TEMPLATE_PATH,
                    help="Path to cw_heuristics template")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--pi-size", type=int, default=20,
                    help="Total items in synthetic PI (Features + Epics + Initiatives, ratio 8:4:1)")
    ap.add_argument("--team-size", type=int, default=5)
    ap.add_argument("--factor", type=float, default=1.20,
                    help="Perturbation factor (1.20 = +20%%)")
    ap.add_argument("--naked", action="store_true",
                    help="Perturb without rebalancing other gates")
    args = ap.parse_args()

    if not args.template.is_file():
        print(f"ERROR: template not found at {args.template}", file=sys.stderr)
        sys.exit(2)

    weights = load_gate_weights(args.template)

    # Split pi-size into Feature/Epic/Initiative roughly 8:4:1
    total = args.pi_size
    n_init = max(1, total // 13)
    n_epics = max(2, (total * 4) // 13)
    n_features = total - n_init - n_epics

    rng = random.Random(args.seed)
    team = build_team(args.team_size, rng)
    items = build_pi_items(team, n_features, n_epics, n_init, rng)

    n_events = sum(len(i["gates_fired"]) for i in items)
    print(f"PI scenario: {n_features}F + {n_epics}E + {n_init}I items, "
          f"{args.team_size} people, {n_events} gate events fired")
    print(f"Perturbation: ×{args.factor:.2f} "
          f"({'rebalanced' if not args.naked else 'naked'})")
    print()

    # Baseline distribution
    base = normalize(credit_per_person(items, weights))
    if not base:
        print("WARNING: no gate events fired in scenario. Increase --pi-size "
              "or --seed and retry.")
        sys.exit(1)

    print("Baseline cw distribution:")
    for p in sorted(base, key=lambda x: -base[x]):
        bar = "█" * int(round(base[p] * 40))
        print(f"  {p:<6} {base[p]*100:5.1f}%  {bar}")
    print()

    perturb_fn = perturb_naked if args.naked else perturb_rebalanced

    rows = []
    for item_type, gates in weights.items():
        for gate_key, w in gates.items():
            up = evaluate_perturbation(items, weights, perturb_fn,
                                       item_type, gate_key, args.factor)
            down = evaluate_perturbation(items, weights, perturb_fn,
                                         item_type, gate_key, 2 - args.factor)
            # Sum of absolute changes across both directions, max single-person impact
            sum_abs = (sum(abs(v) for v in up.values()) +
                       sum(abs(v) for v in down.values())) / 2
            max_abs = max(
                max((abs(v) for v in up.values()), default=0.0),
                max((abs(v) for v in down.values()), default=0.0),
            )
            rows.append({
                "item_type": item_type,
                "gate": gate_key,
                "weight": w,
                "sum_abs": sum_abs,
                "max_abs": max_abs,
                "class": classify(max_abs),
            })

    rows.sort(key=lambda r: -r["max_abs"])

    print(f"{'Type':<11} {'Gate':<32} {'W':>5}  {'ΔΣ':>6}  {'max|Δ|':>7}  Class")
    print("─" * 78)
    for r in rows:
        print(f"{r['item_type']:<11} {r['gate']:<32} "
              f"{r['weight']:>5.2f}  {r['sum_abs']*100:>5.1f}%  "
              f"{r['max_abs']*100:>6.1f}%  {r['class']}")

    high = [r for r in rows if r["class"] == "HIGH"]
    med = [r for r in rows if r["class"] == "MED"]
    low = [r for r in rows if r["class"] == "LOW"]

    print()
    print("Verdict:")
    print(f"  HIGH ({len(high)}): cw shifts ≥2% on a single person — discuss with team before adjusting.")
    for r in high:
        print(f"    - {r['item_type']:<11} {r['gate']:<32} (w={r['weight']:.2f})")
    print(f"  MED  ({len(med)}): cw shifts 0.5–2% — tune cautiously, doc reason.")
    print(f"  LOW  ({len(low)}): cw shifts <0.5% — robust, leave at defaults.")


if __name__ == "__main__":
    main()
