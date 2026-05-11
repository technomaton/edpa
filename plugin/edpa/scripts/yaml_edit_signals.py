#!/usr/bin/env python3
"""
EDPA YAML-edit signal collector — v1.17 structural detection.

Walks `git log -p -- .edpa/backlog/` for an iteration window and emits
one or more signals per (commit, item) pair. Unlike detect_contributors.py
(which extracts signals from PR/issue API surfaces), this collector reads
git diffs directly and scores them by *what changed structurally* — not
*what semantically the change represents*. The semantic distinction
between e.g. "business case" and "benefit hypothesis" is unreliable
(operator naming drift, content quality varies), so we explicitly avoid
it and credit raw structural deltas instead. Auditor reviewing per-signal
ref opens the commit and sees the actual diff.

Signal taxonomy (8 types, all `yaml_edit:*`):

  create                  — new file with +id + +type + +title (item born)
  block_add               — new top-level nested object added
  list_grow               — net `- ` bullets added (capped at 10/commit/item)
  scalar_change           — top-level scalar field set or changed
  lines_volume            — total +lines effort proxy (capped at min(3.0, n/30))
  contributors_rebalance  — new person added to contributors[] (cw shift only = 0)
  revert                  — net-removal commit (negative weight)
  status_transition_skip  — sentinel; status changes owned by transitions.py

Mitigations baked in:
  - bulk migration commits (e.g. `EDPA migrate`, `chore: rename`) → weight × 0.1
  - tool-generated commits (bot authors, EDPA sync/setup prefixes) → weight = 0
  - whitespace/format-only edits → 0 weight (no list/block/scalar deltas)
  - file moves / renames → 0 weight (metadata only)
  - backdated commits use **author date** for iteration window check

Usage:
    python3 yaml_edit_signals.py <iteration_id>
    python3 yaml_edit_signals.py PI-2026-1.5 --json

API:
    from yaml_edit_signals import collect_yaml_edit_signals
    signals = collect_yaml_edit_signals(edpa_root, iteration_id)
    # → dict: item_id → list of signal dicts
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required", file=sys.stderr)
    sys.exit(1)


# ─── Constants ──────────────────────────────────────────────────────────────

TRACKED_DIRS = ("initiatives", "epics", "features", "stories", "defects", "tasks")

# Default signal weights. Calibration tunes these via /edpa:calibrate
# against ground truth. Initial values are conservative round numbers
# anchored to the existing detect_contributors weights (assignee=4.0,
# pr_author=3.4, commit_author=2.78) — yaml_edit:create is comparable
# in effort to commit_author for a meaningful PR.
DEFAULT_WEIGHTS = {
    "yaml_edit:create": 5.0,
    "yaml_edit:block_add": 2.0,
    "yaml_edit:list_grow": 1.0,           # per net + bullet, capped 10
    "yaml_edit:scalar_change": 0.5,
    "yaml_edit:lines_volume_cap": 3.0,    # max contribution from line count
    "yaml_edit:lines_volume_divisor": 30, # +30 lines = +1.0
    "yaml_edit:contributors_rebalance": 0.3,
    "yaml_edit:revert": -0.5,             # per net-removed block
    "bulk_migration_discount": 0.1,
    "list_grow_cap_per_commit": 10,
}

# Commit messages matching these patterns are tool-generated and produce
# 0 yaml_edit weight (the actual work happened elsewhere; sync/setup
# auto-commits are bookkeeping).
TOOL_COMMIT_PATTERNS = [
    re.compile(r"^EDPA sync (push|pull)", re.IGNORECASE),
    re.compile(r"^EDPA setup state committed", re.IGNORECASE),
    re.compile(r"^EDPA: capacity override", re.IGNORECASE),
    re.compile(r"^EDPA sync setup-refresh", re.IGNORECASE),
    re.compile(r"^Auto-commit\b", re.IGNORECASE),
]

# Bulk migration commits get weight × 0.1. Pattern matches the leading
# slug of the message.
BULK_MIGRATION_PATTERNS = [
    re.compile(r"^chore[:(].*\b(rename|migrate|bulk)\b", re.IGNORECASE),
    re.compile(r"^EDPA migrate\b", re.IGNORECASE),
    re.compile(r"^migrate:", re.IGNORECASE),
    re.compile(r"^refactor[:(].*\bbulk\b", re.IGNORECASE),
]

# Bot author emails. Commits authored by these never produce yaml_edit
# weight — they are tool-generated state synchronization, not human work.
#
# `*@noreply.technomaton.com` covers the EDPA sync bot identity used by
# the `sync-projects-to-git.yml` / `sync-git-to-projects.yml` workflows
# (default `edpa-bot@noreply.technomaton.com`). The whole subdomain is
# matched so future bot accounts (e.g. `release-bot@noreply.…`,
# `iteration-close-bot@noreply.…`) inherit the exclusion automatically.
BOT_EMAIL_PATTERNS = [
    re.compile(r".*\[bot\]@.*"),
    re.compile(r".*github-actions@.*"),
    re.compile(r".*noreply@github\.com$"),
    re.compile(r".*@noreply\.technomaton\.com$"),
]


# ─── Helpers ────────────────────────────────────────────────────────────────


def _run_git(args: list[str], cwd: Path) -> str:
    """Run git with cwd, return stdout. Raises on nonzero exit."""
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {result.stderr.strip()}"
        )
    return result.stdout


def _parse_iter_window(edpa_root: Path, iter_id: str) -> tuple[datetime, datetime]:
    """Read .edpa/iterations/<id>.yaml and return (start, end) UTC datetimes."""
    iter_file = edpa_root / "iterations" / f"{iter_id}.yaml"
    if not iter_file.is_file():
        raise FileNotFoundError(f"iteration file not found: {iter_file}")
    d = yaml.safe_load(iter_file.read_text())["iteration"]
    start = datetime.fromisoformat(f"{d['start_date']}T00:00:00+00:00")
    end = datetime.fromisoformat(f"{d['end_date']}T23:59:59+00:00")
    return start, end


def _load_people(edpa_root: Path) -> list[dict]:
    p = edpa_root / "config" / "people.yaml"
    if not p.is_file():
        return []
    d = yaml.safe_load(p.read_text()) or {}
    return d.get("people", []) or []


def _email_to_login(email: str, people: list[dict]) -> str:
    """Resolve commit author email → github login (if mapped). Falls back
    to email if no mapping found, so signals are never dropped on the
    floor — auditor can still trace back to the commit."""
    e = (email or "").lower()
    for p in people:
        if (p.get("email") or "").lower() == e:
            return p.get("github") or p["id"]
    return email or "unknown"


def _is_tool_commit(subject: str) -> bool:
    return any(p.search(subject or "") for p in TOOL_COMMIT_PATTERNS)


def _is_bulk_migration(subject: str) -> bool:
    return any(p.search(subject or "") for p in BULK_MIGRATION_PATTERNS)


def _is_bot_author(email: str) -> bool:
    return any(p.search(email or "") for p in BOT_EMAIL_PATTERNS)


# Public alias — consumed by transitions.py and other modules that need
# to identify bot commits and skip them from CW credit. Keeping the
# regex list in this single module ensures all evidence collectors
# agree on which authors are "tools".
def is_bot_author(email: str) -> bool:
    """True if the email matches a known bot/tool-author pattern.

    Used by every signal collector (yaml_edit_signals, transitions,
    detect_contributors) to keep EDPA's own sync/setup/release bots
    out of the CW calculation. Without this, the bot would self-credit
    every YAML mutation it makes during scheduled syncs.
    """
    return _is_bot_author(email)


# ─── Diff scoring ───────────────────────────────────────────────────────────


# Pre-compiled regexes for diff line classification.
_RE_STATUS_LINE = re.compile(r"^[+-]status:\s*(.+)$")
_RE_TOP_LEVEL_KEY = re.compile(r"^[+-]([a-z_][a-z0-9_]*)\s*:\s*(.*)$", re.IGNORECASE)
_RE_LIST_BULLET = re.compile(r"^[+-]- ")
_RE_PERSON_ENTRY = re.compile(r"^[+-]- person:\s*(.+?)\s*$")
_RE_ID_FIELD = re.compile(r"^\+id:\s*(\S+)\s*$")
_RE_TYPE_FIELD = re.compile(r"^\+type:\s*(\S+)\s*$")
_RE_TITLE_FIELD = re.compile(r"^\+title:\s*")


def score_diff(diff_lines: list[str], weights: dict) -> tuple[float, list[str]]:
    """Score a per-(commit, file) diff. Returns (total_weight, audit_tags).

    Edge cases handled:
      - status-only changes → 0 weight (transitions.py owns those)
      - whitespace-only diffs → 0 weight
      - file rewrite (yaml.dump reorder) → only counts net deltas, not gross
      - new file (full file as +) → create signal
      - net-removal (significantly more - than +) → revert signal (negative)
      - cap on list_grow per commit → prevents AC spam
    """
    added = [l[1:] for l in diff_lines if l.startswith("+") and not l.startswith("+++")]
    removed = [l[1:] for l in diff_lines if l.startswith("-") and not l.startswith("---")]

    # Strip trailing whitespace and skip purely empty/whitespace lines.
    def _meaningful(s: str) -> bool:
        return s.strip() != ""

    added_real = [a for a in added if _meaningful(a)]
    removed_real = [r for r in removed if _meaningful(r)]

    tags: list[str] = []
    weight = 0.0

    # Skip pure whitespace diffs.
    if not added_real and not removed_real:
        return 0.0, ["whitespace_only"]

    # Net direction: revert if removal dominates (>2× added by line count and
    # no new id added).
    net_lines = len(added_real) - len(removed_real)
    is_revert = (net_lines < 0 and len(removed_real) > 2 * max(len(added_real), 1)
                 and not any(_RE_ID_FIELD.match("+" + a) for a in added_real))
    if is_revert:
        # Per-removed-block negative weight, capped to keep magnitude sane.
        n_blocks_removed = len(removed_real) // 5  # rough block heuristic
        weight += weights["yaml_edit:revert"] * max(1, n_blocks_removed)
        tags.append(f"revert(-{n_blocks_removed})")
        return weight, tags  # short-circuit on revert

    # ─── 1. File creation: +id + +type + +title in adds ──────────────────
    has_id = any(_RE_ID_FIELD.match("+" + a) for a in added_real)
    has_type = any(_RE_TYPE_FIELD.match("+" + a) for a in added_real)
    has_title = any(_RE_TITLE_FIELD.match("+" + a) for a in added_real)
    is_create = has_id and has_type and has_title and not removed_real
    if is_create:
        weight += weights["yaml_edit:create"]
        tags.append("create")
        # On create the rest of the file is also "new content" — count
        # block/list/lines but skip the create-specific signals to avoid
        # double-credit for id/type/title.

    # ─── 2. Status-only change (status:X → status:Y) ─────────────────────
    # Skip these — transitions.py owns gate_event credit.
    status_added = [a for a in added_real if _RE_STATUS_LINE.match("+" + a)]
    status_removed = [r for r in removed_real if _RE_STATUS_LINE.match("-" + r)]
    other_added = [a for a in added_real if a not in status_added]
    other_removed = [r for r in removed_real if r not in status_removed]
    if status_added and not other_added and not other_removed:
        return 0.0, ["status_transition_owned_by_transitions_py"]

    # ─── 3. Block addition: top-level key with empty value (followed by
    # nested content). Detected via top-level key with `:` end-of-line.
    block_keys_added = set()
    for a in other_added:
        m = _RE_TOP_LEVEL_KEY.match("+" + a)
        if m and not m.group(2).strip():  # `key:` with no inline value
            block_keys_added.add(m.group(1))
    # Filter out blocks that already existed (appeared in - too).
    block_keys_removed = set()
    for r in other_removed:
        m = _RE_TOP_LEVEL_KEY.match("-" + r)
        if m and not m.group(2).strip():
            block_keys_removed.add(m.group(1))
    new_blocks = block_keys_added - block_keys_removed
    if new_blocks:
        weight += len(new_blocks) * weights["yaml_edit:block_add"]
        tags.append(f"block_add×{len(new_blocks)}")

    # ─── 4. List growth: net `- ` bullets added (cap 10) ─────────────────
    bullets_added = sum(1 for a in other_added if _RE_LIST_BULLET.match("+" + a))
    bullets_removed = sum(1 for r in other_removed if _RE_LIST_BULLET.match("-" + r))
    net_bullets = max(0, bullets_added - bullets_removed)
    if net_bullets > 0:
        capped = min(net_bullets, weights["list_grow_cap_per_commit"])
        weight += capped * weights["yaml_edit:list_grow"]
        if capped < net_bullets:
            tags.append(f"list_grow×{capped}(capped_from_{net_bullets})")
        else:
            tags.append(f"list_grow×{capped}")

    # ─── 5. Scalar change: top-level key with inline value ───────────────
    scalar_changes = 0
    for a in other_added:
        m = _RE_TOP_LEVEL_KEY.match("+" + a)
        if m and m.group(2).strip():  # has inline value
            # Skip if this is part of a create (id/type/title already credited)
            if is_create and m.group(1) in ("id", "type", "title"):
                continue
            scalar_changes += 1
    if scalar_changes > 0:
        weight += scalar_changes * weights["yaml_edit:scalar_change"]
        tags.append(f"scalar×{scalar_changes}")

    # ─── 6. Contributors rebalance: new person added (NOT cw shift) ───────
    persons_added = set()
    for a in other_added:
        m = _RE_PERSON_ENTRY.match("+" + a)
        if m:
            persons_added.add(m.group(1).strip())
    persons_removed = set()
    for r in other_removed:
        m = _RE_PERSON_ENTRY.match("-" + r)
        if m:
            persons_removed.add(m.group(1).strip())
    new_persons = persons_added - persons_removed
    if new_persons and not is_create:  # don't double-count on create
        weight += len(new_persons) * weights["yaml_edit:contributors_rebalance"]
        tags.append(f"contributors+{len(new_persons)}")

    # ─── 7. Lines volume bonus (capped) ──────────────────────────────────
    lines_bonus = min(
        weights["yaml_edit:lines_volume_cap"],
        max(0, net_lines) / weights["yaml_edit:lines_volume_divisor"],
    )
    if lines_bonus > 0.1:
        weight += lines_bonus
        tags.append(f"vol+{lines_bonus:.1f}")

    return round(weight, 2), tags


# ─── Main collection ────────────────────────────────────────────────────────


def collect_yaml_edit_signals(edpa_root: Path, iter_id: str,
                               weights: dict | None = None) -> dict[str, list[dict]]:
    """Walk git log over backlog YAMLs in iter window and emit signals.

    Returns: {item_id: [signal_dict, ...]}
    Each signal_dict has: type, ref, login, weight, detected_at, tags.
    """
    edpa_root = Path(edpa_root)
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}

    start, end = _parse_iter_window(edpa_root, iter_id)
    people = _load_people(edpa_root)
    repo_root = edpa_root.parent

    paths = [
        str((edpa_root / "backlog" / d).relative_to(repo_root))
        for d in TRACKED_DIRS
        if (edpa_root / "backlog" / d).is_dir()
    ]
    if not paths:
        return {}

    log = _run_git(
        ["log", "--pretty=format:__COMMIT__|%H|%aI|%ae|%s",
         "-p", "--unified=0", "--", *paths],
        cwd=repo_root,
    )

    signals_by_item: dict[str, list[dict]] = defaultdict(list)
    cur_sha = cur_ts = cur_email = cur_subject = None
    cur_file = None
    cur_diff: list[str] = []

    def _flush():
        nonlocal cur_diff
        if not (cur_file and cur_sha and cur_diff):
            cur_diff = []
            return
        if not any(f"backlog/{d}/" in cur_file for d in TRACKED_DIRS):
            cur_diff = []
            return
        if cur_ts < start or cur_ts > end:
            cur_diff = []
            return
        if _is_bot_author(cur_email):
            cur_diff = []
            return
        if _is_tool_commit(cur_subject):
            cur_diff = []
            return

        weight, tags = score_diff(cur_diff, weights)
        if abs(weight) < 0.01:  # zero-weight = nothing to record
            cur_diff = []
            return

        # Apply bulk migration discount if applicable.
        if _is_bulk_migration(cur_subject):
            weight = round(weight * weights["bulk_migration_discount"], 2)
            tags.append("bulk_discount")

        item_id = Path(cur_file).stem
        login = _email_to_login(cur_email, people)
        signals_by_item[item_id].append({
            "type": "yaml_edit",
            "ref": f"commit/{cur_sha[:7]}/{Path(cur_file).name}",
            "login": login,
            "weight": weight,
            "detected_at": cur_ts.isoformat(),
            "tags": tags,
        })
        cur_diff = []

    for line in log.splitlines():
        if line.startswith("__COMMIT__|"):
            _flush()
            try:
                _, sha, ts_iso, email, subject = line.split("|", 4)
            except ValueError:
                continue
            cur_sha = sha
            cur_ts = datetime.fromisoformat(ts_iso).astimezone(timezone.utc)
            cur_email = email
            cur_subject = subject
            cur_file = None
            continue
        if line.startswith("diff --git "):
            _flush()
            parts = line.split(" b/", 1)
            cur_file = parts[1] if len(parts) == 2 else None
            continue
        if line.startswith("@@") or line.startswith("index ") \
                or line.startswith("similarity index") \
                or line.startswith("rename "):
            continue
        if line.startswith("---") or line.startswith("+++"):
            continue
        cur_diff.append(line)
    _flush()

    return dict(signals_by_item)


# ─── CLI ────────────────────────────────────────────────────────────────────


def _print_human(signals_by_item: dict[str, list[dict]]) -> None:
    n_signals = sum(len(v) for v in signals_by_item.values())
    print(f"\n=== {n_signals} yaml_edit signals across "
          f"{len(signals_by_item)} items ===\n")
    print(f"{'item':6s} {'commit':10s} {'login':22s} {'wt':>6s}  tags")
    print("-" * 100)
    for item_id, sigs in sorted(signals_by_item.items()):
        for s in sigs:
            print(f"{item_id:6s} {s['ref'].split('/')[1]:10s} "
                  f"{s['login']:22s} {s['weight']:>6.2f}  "
                  f"{','.join(s['tags'])}")
    # Per-login totals
    totals = defaultdict(float)
    for sigs in signals_by_item.values():
        for s in sigs:
            totals[s['login']] += s['weight']
    print("\n--- per-login totals ---")
    for login, total in sorted(totals.items(), key=lambda x: -x[1]):
        print(f"  {login:25s}  {total:>6.2f}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("iteration", help="Iteration ID (e.g. PI-2026-1.5)")
    p.add_argument("--edpa-root", default=".edpa", help="Path to .edpa/")
    p.add_argument("--json", action="store_true",
                   help="Emit JSON instead of human-readable table")
    args = p.parse_args()

    signals = collect_yaml_edit_signals(Path(args.edpa_root), args.iteration)
    if args.json:
        print(json.dumps(signals, indent=2, ensure_ascii=False))
    else:
        _print_human(signals)


if __name__ == "__main__":
    main()
