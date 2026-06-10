#!/usr/bin/env python3
"""
EDPA Allocation Explainer — narrative markdown for one person's derived hours.

Reads edpa_results.json (already computed by the engine) + backlog items
(for signal details) and formats: signal → cw → JS×cw → ratio → hours.

Usage:
    python3 explain.py --person urbanek --iteration PI-2026-1.1
    python3 explain.py --person urbanek --iteration PI-2026-1.1 --item S-206
"""
try:
    import _console  # noqa: F401
except ImportError:
    pass

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. pip install pyyaml", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------

def load_results(edpa_root: Path, iteration_id: str) -> dict:
    path = edpa_root / "reports" / f"iteration-{iteration_id}" / "edpa_results.json"
    if not path.exists():
        raise FileNotFoundError(
            f"edpa_results.json not found at {path}\n"
            f"Run the engine for {iteration_id} first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_item_meta(edpa_root: Path, item_id: str) -> dict:
    """Return frontmatter dict for a backlog item (title, contributors with signals)."""
    backlog = edpa_root / "backlog"
    if not backlog.is_dir():
        return {}
    for type_dir in backlog.iterdir():
        if not type_dir.is_dir():
            continue
        f = type_dir / f"{item_id}.md"
        if f.exists():
            try:
                content = f.read_text(encoding="utf-8")
                if not content.startswith("---"):
                    return {}
                end = content.find("---", 3)
                if end == -1:
                    return {}
                return yaml.safe_load(content[3:end]) or {}
            except Exception:
                return {}
    return {}


# ---------------------------------------------------------------------------
# Explain rendering
# ---------------------------------------------------------------------------

def _signal_line(sig: dict) -> str:
    stype = sig.get("type", "?")
    ref = sig.get("ref", "")
    weight = sig.get("weight")
    parts = [f"  • {stype}"]
    if ref:
        parts.append(f"ref: {ref}")
    if weight is not None:
        parts.append(f"weight: {weight:.2f}")
    return "  ".join(parts)


def explain_person(
    results: dict,
    person_id: str,
    edpa_root: Path,
    item_filter: str | None = None,
) -> str:
    """Generate a narrative markdown explaining one person's allocation."""
    iteration_id = results.get("iteration", "?")

    # Find person in people[] (engine output is keyed by `id`, not `person`)
    dr = next(
        (r for r in (results.get("people") or []) if r.get("id") == person_id),
        None,
    )
    if dr is None:
        return f"ERROR: person {person_id!r} not found in {iteration_id} results.\n"

    name = dr.get("name", person_id)
    role = dr.get("role", "")
    capacity = dr.get("capacity", 0)
    total_derived = dr.get("total_derived", 0)

    # This person's items are nested under their entry in people[].
    all_items = list(dr.get("items") or [])
    if item_filter:
        all_items = [i for i in all_items if i["id"] == item_filter]
        if not all_items:
            return f"ERROR: item {item_filter!r} not attributed to {person_id} in {iteration_id}.\n"

    # Compute sum_scores for context (already in ratio, but useful for display)
    sum_scores = sum(i["score"] for i in all_items) if all_items else 0

    lines = [
        f"# Allocation Explanation: {person_id} / {iteration_id}",
        "",
        f"**{name}** ({role})",
        f"Capacity: **{capacity}h** | Derived: **{total_derived}h**",
        "",
    ]

    # ── Summary table ──────────────────────────────────────────────────────
    if all_items:
        lines += [
            "## Summary",
            "",
            "| Item | JS | CW | Score | Ratio | Hours |",
            "|------|---:|---:|------:|------:|------:|",
        ]
        for it in all_items:
            lines.append(
                f"| {it['id']} | {it['js']} "
                f"| {it['cw']:.4f} | {it['score']:.4f} "
                f"| {it['ratio']:.4f} | **{it['hours']}h** |"
            )
        if not item_filter:
            lines += [
                f"| **Σ** | | | {sum_scores:.4f} | 1.0000 | **{total_derived}h** |",
            ]
        lines.append("")
    else:
        lines += ["_No items attributed to this person in this iteration._", ""]

    # ── Per-item detail ────────────────────────────────────────────────────
    for it in all_items:
        item_id = it["id"]
        meta = load_item_meta(edpa_root, item_id)
        title = meta.get("title", "")
        js = it["js"]
        cw = it["cw"]
        score = it["score"]
        ratio = it["ratio"]
        hours = it["hours"]

        lines += [
            f"## {item_id}{(' — ' + title) if title else ''}",
            "",
            f"**Job Size:** {js} SP | **Contribution Weight:** {cw:.4f} | "
            f"**Score:** JS × CW = {js} × {cw:.4f} = {score:.4f}",
            "",
        ]

        # Signals from backlog contributors[] block
        contributors = meta.get("contributors") or []
        person_contrib = next(
            (c for c in contributors
             if isinstance(c, dict) and str(c.get("person", "")) == person_id),
            None,
        )

        if person_contrib:
            signals = person_contrib.get("signals") or []
            contrib_score = person_contrib.get("contribution_score")
            total_contrib = sum(
                (c.get("contribution_score") or 0)
                for c in contributors if isinstance(c, dict)
            )

            if signals:
                lines.append("**Evidence signals:**")
                for sig in signals:
                    lines.append(_signal_line(sig))
                lines.append("")
                if contrib_score is not None:
                    lines.append(
                        f"contribution_score = {contrib_score:.2f} "
                        f"(sum of signal weights above)"
                    )
                    if total_contrib > 0:
                        lines.append(
                            f"CW = {contrib_score:.2f} / {total_contrib:.2f} = {cw:.4f} "
                            f"(this person's share of all contributors)"
                        )
                    lines.append("")
            else:
                # Manual CW (no signal trail) or legacy `as:` field
                as_role = person_contrib.get("as", "")
                manual_note = f"manual CW ({as_role})" if as_role else "manually assigned CW"
                lines += [
                    f"**Evidence:** {manual_note} — no signal trail recorded.",
                    f"CW = {cw:.4f} (set directly in contributors[] block)",
                    "",
                ]
        else:
            lines += [
                "_No contributors[] block found for this item. CW derived from engine heuristics._",
                "",
            ]

        lines += [
            f"**Allocation:** score ({score:.4f}) / Σ scores ({sum_scores:.4f}) "
            f"× capacity ({capacity}h) = ratio {ratio:.4f} × {capacity}h = **{hours}h**",
            "",
            "---",
            "",
        ]

    # ── Invariant footer ────────────────────────────────────────────────────
    if not item_filter:
        # Prefer the engine's own per-person verdict; fall back to the local check.
        inv_ok = dr.get(
            "invariant_ok", abs(total_derived - capacity) <= 0.1 if capacity else True
        )
        inv_sym = "✓" if inv_ok else "✗"
        lines += [
            "## Invariant",
            "",
            f"Σ derived hours = {total_derived}h {'=' if inv_ok else '!='} "
            f"capacity {capacity}h  {inv_sym}",
            "",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="EDPA Allocation Explainer")
    parser.add_argument("--person", required=True, help="Person ID (e.g. urbanek)")
    parser.add_argument("--iteration", required=True, help="Iteration ID (e.g. PI-2026-1.1)")
    parser.add_argument("--item", default=None, help="Focus on a single item ID")
    parser.add_argument("--edpa-root", default=".edpa", type=Path)
    parser.add_argument("--output", type=Path, default=None,
                        help="Write markdown to file (default: stdout)")
    args = parser.parse_args()

    if not args.edpa_root.is_dir():
        print(f"ERROR: {args.edpa_root} not found", file=sys.stderr)
        return 2

    try:
        results = load_results(args.edpa_root, args.iteration)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    md = explain_person(results, args.person, args.edpa_root, args.item)

    if md.startswith("ERROR:"):
        print(md, file=sys.stderr)
        return 1

    if args.output:
        args.output.write_text(md, encoding="utf-8")
        print(f"Explanation written to {args.output}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
