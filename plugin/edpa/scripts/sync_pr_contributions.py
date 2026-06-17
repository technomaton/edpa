#!/usr/bin/env python3
"""CI complement — write PR-thread signals into .edpa/backlog/ YAML.

V2 ADR-012 + V2.1 Krok C6 demotion. Triggered by a platform-specific
CI workflow (GH Actions / GitLab CI / Forgejo Actions); reads a PR
event payload, identifies the EDPA items the PR touches, and emits
ONLY the signals that don't exist in local git history:

  - ``pr_reviewer``   (review submitter — PR-thread event)
  - ``issue_comment`` (comment author   — issue-thread event)

The primary attribution source in V2.1+ is ``local_evidence.py``
(post-commit hook), which emits ``commit_author`` for every commit
mentioning an item ID. This script is the optional complement that
adds PR-thread-only signals on top.

Result is merged into the item's ``evidence[]`` block, dedup by ref.

Deterministic: same input event → same YAML diff. No LLM. No heuristics
about who to credit — just maps event → signal type → weight from
``cw_heuristics.yaml`` (when present).

Modes:
    --pr <number> --repo <owner/name>
        Pull PR data via gh CLI (Action context).
    --event <path-to-event.json>
        Read GH-style event payload from file (replay / testing).
    --rebuild --skip-commit
        Used by edpa-close-iteration to refresh open PR state without
        committing (engine reads YAML in-process).
"""
from __future__ import annotations

try:  # best-effort UTF-8 stdio on legacy Windows consoles (cp1250)
    import _console  # noqa: F401
except ImportError:
    pass
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
try:
    from id_counter import TYPE_DIRS  # noqa: E402
    from _md_frontmatter import load_md, save_md_item  # noqa: E402
finally:
    sys.path.pop(0)


# Map item-id prefix → backlog directory.
PREFIX_TO_DIR = {
    "I": "initiatives",
    "E": "epics",
    "F": "features",
    "S": "stories",
    "D": "defects",
    "EV": "events",
    "R": "risks",
}

# Recognized EDPA item refs in PR title/body/branch.
_ITEM_REF_RE = re.compile(r"\b([A-Z]{1,3}-\d{1,9})\b")

# Defaults if cw_heuristics.yaml is missing. This script emits the
# GH-side signals (pr_reviewer, issue_comment); commit_author is
# emitted locally by local_evidence.py.
DEFAULT_WEIGHTS = {
    "pr_reviewer": 2.25,
    "issue_comment": 1.14,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gh_json(args: list[str]) -> dict | list | None:
    try:
        r = subprocess.run(
            ["gh", *args], capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        print("ERROR: gh CLI not found in PATH", file=sys.stderr)
        return None
    if r.returncode != 0:
        # Surface stderr so workflow logs show *why* gh failed (auth,
        # bad json field, rate limit, missing repo, …) instead of just
        # "cannot fetch PR".
        if r.stderr:
            print(f"gh error (exit {r.returncode}): {r.stderr.rstrip()}",
                  file=sys.stderr)
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        print(f"ERROR: gh returned non-JSON output: {r.stdout[:200]!r}",
              file=sys.stderr)
        return None


def _find_edpa_root(start: Path) -> Path | None:
    p = start.resolve()
    while p != p.parent:
        if (p / ".edpa").is_dir():
            return p / ".edpa"
        p = p.parent
    return None


def _load_weights(edpa_root: Path) -> dict[str, float]:
    h = edpa_root / "config" / "cw_heuristics.yaml"
    if not h.exists():
        return dict(DEFAULT_WEIGHTS)
    try:
        data = yaml.safe_load(h.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return dict(DEFAULT_WEIGHTS)
    sig = data.get("signal_weights") or {}
    return {**DEFAULT_WEIGHTS, **{k: float(v) for k, v in sig.items()}}


def extract_item_ids(text: str) -> list[str]:
    return list(dict.fromkeys(_ITEM_REF_RE.findall(text or "")))


def find_item_path(edpa_root: Path, item_id: str) -> Path | None:
    prefix = item_id.split("-", 1)[0]
    type_dir = PREFIX_TO_DIR.get(prefix)
    if not type_dir:
        return None
    candidate = edpa_root / "backlog" / type_dir / f"{item_id}.md"
    return candidate if candidate.exists() else None


def fetch_pr(pr_number: int, repo: str | None) -> dict | None:
    """Pull a PR's title/body/author/reviews/comments via gh CLI.

    Note: ``merged`` is not a valid ``gh pr view --json`` field. Use
    ``state`` (returns ``OPEN``/``CLOSED``/``MERGED``) instead. The
    workflow already gates on ``pull_request.merged == true`` before
    invoking this script, so state checking here is informational only.
    """
    args = [
        "pr", "view", str(pr_number),
        "--json",
        "number,title,body,author,reviews,comments,headRefName,state",
    ]
    if repo:
        args.extend(["--repo", repo])
    data = _gh_json(args)
    return data if isinstance(data, dict) else None


def event_to_signals(pr: dict, weights: dict[str, float]) -> list[dict]:
    """Turn a PR payload into a flat list of (item_id, signal) tuples.

    V2.1 demotion: this script is the OPTIONAL CI complement to
    ``local_evidence.py`` (the primary local hook). It emits only
    PR-thread events that can't be detected from git alone:

      - ``pr_reviewer``   (review submitter — lives in GH PR thread)
      - ``issue_comment`` (comment author   — lives in GH issue thread)

    What it deliberately does NOT emit:

      - ``pr_author`` — the PR author wrote at least one commit, and
        ``local_evidence.py`` already credits them as ``commit_author``
        (weight 2.78, ref ``commit/{sha}``). Emitting pr_author here
        would double-count the same human action.

    Projects without local hooks installed and that want pr_author
    attribution should either (a) install hooks via
    ``project_setup.py --with-hooks``, or (b) fork this script with a
    custom emitter.

    Returns ``[{item_id, signal: {type, person, weight, ref, at}}]``.
    """
    item_ids = set()
    for chunk in (pr.get("title", ""), pr.get("body", ""), pr.get("headRefName", "")):
        item_ids.update(extract_item_ids(chunk))
    if not item_ids:
        return []

    pr_num = pr.get("number")
    pr_url_base = f"PR#{pr_num}"
    now = _utc_now()
    signals: list[dict] = []

    for rv in pr.get("reviews") or []:
        login = (rv.get("author") or {}).get("login")
        if not login:
            continue
        sub_at = rv.get("submittedAt") or now
        for iid in item_ids:
            signals.append({
                "item_id": iid,
                "signal": {
                    "type": "pr_reviewer",
                    "person": login,
                    "weight": weights.get("pr_reviewer", 0),
                    "ref": f"{pr_url_base}:review:{rv.get('id') or sub_at}",
                    "at": sub_at,
                },
            })

    for cm in pr.get("comments") or []:
        login = (cm.get("author") or {}).get("login")
        if not login:
            continue
        cre = cm.get("createdAt") or now
        for iid in item_ids:
            signals.append({
                "item_id": iid,
                "signal": {
                    "type": "issue_comment",
                    "person": login,
                    "weight": weights.get("issue_comment", 0),
                    "ref": f"{pr_url_base}:comment:{cm.get('id') or cre}",
                    "at": cre,
                },
            })

    return signals


def _dedupe_signals(existing: list[dict], new: list[dict]) -> list[dict]:
    """Merge ``new`` into ``existing`` keyed by ``ref``; new wins on conflict."""
    by_ref = {s.get("ref"): s for s in existing if isinstance(s, dict)}
    for s in new:
        by_ref[s.get("ref")] = s
    return [by_ref[k] for k in sorted(by_ref) if k is not None]


def apply_signals(edpa_root: Path, signals: list[dict]) -> dict[str, int]:
    """Group signals by item_id; merge into each item's contributors block.

    Returns ``{item_id: signal_count_after_merge}``.
    """
    by_item: dict[str, list[dict]] = {}
    for s in signals:
        by_item.setdefault(s["item_id"], []).append(s["signal"])

    summary: dict[str, int] = {}
    for item_id, new_signals in by_item.items():
        path = find_item_path(edpa_root, item_id)
        if not path:
            continue
        item = load_md(path) or {}
        # V2.1 rename: ci_signals[] → evidence[]. Read from either
        # (backward-compat for items written by V2.0); always write
        # to evidence[] and drop any legacy ci_signals[] entry so the
        # YAML converges on the new shape.
        existing = item.get("evidence")
        if existing is None:
            existing = item.get("ci_signals") or []
        if not isinstance(existing, list):
            existing = []
        merged = _dedupe_signals(existing, new_signals)
        item["evidence"] = merged
        if "ci_signals" in item:
            del item["ci_signals"]
        save_md_item(path, item)
        summary[item_id] = len(merged)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="sync_pr_contributions",
        description="CI materialization layer for EDPA PR signals.",
    )
    parser.add_argument("--pr", type=int, help="PR number (fetched via gh).")
    parser.add_argument("--repo", help="owner/name (e.g. octocat/demo).")
    parser.add_argument("--event", type=Path,
                        help="Path to event payload JSON (replay / testing).")
    parser.add_argument("--rebuild", action="store_true",
                        help="Force re-materialization even if up-to-date.")
    parser.add_argument("--skip-commit", action="store_true",
                        help="Write YAML but don't git-add/commit.")
    parser.add_argument("--edpa-root", type=Path, default=None,
                        help="Override .edpa/ lookup (default: walk up from CWD).")
    args = parser.parse_args()

    edpa_root = (args.edpa_root.resolve() if args.edpa_root
                 else _find_edpa_root(Path.cwd()))
    if not edpa_root:
        print("ERROR: .edpa/ not found", file=sys.stderr)
        return 2

    weights = _load_weights(edpa_root)

    if args.event:
        try:
            pr = json.loads(args.event.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"ERROR: cannot read event {args.event}: {e}", file=sys.stderr)
            return 2
        # GH event payload nests PR under "pull_request"
        if "pull_request" in pr:
            pr = pr["pull_request"]
    elif args.pr is not None:
        pr = fetch_pr(args.pr, args.repo)
        if not pr:
            print(f"ERROR: cannot fetch PR #{args.pr}", file=sys.stderr)
            return 2
    else:
        print("ERROR: --pr or --event required", file=sys.stderr)
        return 2

    signals = event_to_signals(pr, weights)
    if not signals:
        print(f"No EDPA item refs found in PR #{pr.get('number','?')}")
        return 0

    summary = apply_signals(edpa_root, signals)
    print(f"Materialized {len(signals)} signal(s) into {len(summary)} item(s):")
    for iid, n in sorted(summary.items()):
        print(f"  {iid}: {n} total evidence after merge")

    if args.skip_commit:
        return 0

    repo_root = edpa_root.parent
    paths = [edpa_root / "backlog" / PREFIX_TO_DIR[iid.split("-")[0]] / f"{iid}.md"
             for iid in summary]
    paths_str = [str(p.relative_to(repo_root)) for p in paths]
    subprocess.run(["git", "add", *paths_str],
                   cwd=str(repo_root), capture_output=True)
    msg = f"chore(ci-materialization): PR#{pr.get('number','?')} signals"
    # 3× retry with rebase ours strategy per ADR-013 race handling
    for attempt in range(3):
        commit = subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=str(repo_root), capture_output=True, text=True,
        )
        if commit.returncode == 0:
            break
        # If commit failed because nothing to commit, that's fine.
        if "nothing to commit" in (commit.stdout + commit.stderr).lower():
            break
        # Otherwise treat as race; pull --rebase --strategy-option=ours
        subprocess.run(["git", "pull", "--rebase", "--strategy-option=ours"],
                       cwd=str(repo_root), capture_output=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
