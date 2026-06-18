#!/usr/bin/env python3
"""
EDPA Contributor Auto-Detection — v1.11 single-source CW pipeline.

Collects ALL evidence signals for an item (issue + linked PRs) and computes
the final `contributors[]` block with per-item-normalized CW shares.

Signal types collected:
  - commit_author         ← commit author (PR commit or local commit)
  - pr_reviewer           ← PR review submitted
  - issue_comment         ← comment on issue
  - manual:pr_body        ← /contribute @X weight:Y in PR description
  - manual:commit_message ← /contribute in commit message body
  - manual:issue_body     ← /contribute in issue description
  - manual:issue_comment  ← /contribute in issue comment
  - manual:pr_comment     ← /contribute in PR comment (issue-style)

Each signal has: type, ref (auditor-resolvable), weight (from heuristics),
optional excerpt (for manual:*), detected_at timestamp.

Aggregation:
  contribution_score[P, item] = Σ signal_weights for person P on item
  cw[P, item]                 = score[P, item] / Σ_persons score[*, item]
  → Σ_persons cw[*, item] = 1.0    (per-item invariant)

Modes:
  1. CI mode (env-driven, used by edpa-contributor-detect.yml):
       PR_NUMBER, PR_AUTHOR, PR_TITLE, PR_BRANCH set by workflow
  2. CLI audit:
       detect_contributors.py --pr 42
       detect_contributors.py --item S-200 [--since 7days]

Edge case: 0 signals detected for an item → warn-and-skip; existing
contributors[] is left untouched (caller decides whether to fail).
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
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required", file=sys.stderr)
    sys.exit(1)


# ─── Constants ──────────────────────────────────────────────────────────────

# Default signal weights (overridden by .edpa/config/cw_heuristics.yaml).
# Synthetic Monte Carlo baseline over the 3 signal types that fire in the
# local-first flow. The GitHub-issue ``assignee`` and ``pr_author`` signals
# were dropped — they were sourced from GH issues/PRs and never fired in the
# local-first default; commit_author covers PR/commit authorship.
DEFAULT_SIGNAL_WEIGHTS = {
    "commit_author": 4.00,
    "pr_reviewer": 2.17,
    "issue_comment": 1.46,
}

# Map item-id prefix → backlog directory under .edpa/backlog/
PREFIX_TO_DIR = {
    "S": "stories",
    "F": "features",
    "E": "epics",
    "I": "initiatives",
    "T": "tasks",
    "D": "defects",
    "EV": "events",
    "R":  "risks",
}

# /contribute manual directive — additive signal, no role clause.
# Multiple matches for same login on same surface stack additively.
_CONTRIBUTE_PATTERN = re.compile(
    r'/contribute\s+@([A-Za-z0-9_-]+)\s+weight:([0-9]+(?:\.[0-9]+)?)',
    re.IGNORECASE,
)


# ─── Helpers ────────────────────────────────────────────────────────────────


def run_gh(args, *, repo: str | None = None):
    """Run `gh` CLI command, return parsed JSON or None on failure.

    V2 default: returns None — engine is 100% local, reads PR signals
    from the ``ci_signals[]`` field that ``sync_pr_contributions.py``
    materializes via CI workflow (ADR-012 in docs/v2/decisions.md).

    Escape hatch: set ``EDPA_USE_GH=1`` to re-enable direct gh calls
    for the engine — useful only for local debugging against a single
    repo with ``gh auth`` configured. Not recommended for normal use;
    the CI layer is deterministic and avoids the per-developer auth
    requirement.
    """
    if os.environ.get("EDPA_USE_GH") != "1":
        return None
    cmd = ["gh"] + list(args)
    if repo and "--repo" not in cmd:
        cmd.extend(["--repo", repo])
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        # Don't spam stderr for expected "not found" — caller decides.
        return None
    out = result.stdout.strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def extract_item_ids(text: str) -> list[str]:
    """Extract EDPA item IDs (S-200, F-100, E-10, I-1, T-3, D-2) from any text."""
    return re.findall(r'\b([SFEITD]-\d+)\b', text or "")


def parse_contribute_directives(text: str) -> dict[str, float]:
    """Find `/contribute @person weight:X` directives in text.

    Returns a dict {login: total_weight} where multiple directives for
    the same login on the same surface stack additively. Negative or
    non-numeric weights are silently dropped (typo safety).

    No `as:role` parsing — the v1.11 design treats `/contribute` as a
    pure additive signal without role classification (role is derived
    from signal type by the display layer at render time).
    """
    result: dict[str, float] = defaultdict(float)
    for m in _CONTRIBUTE_PATTERN.finditer(text or ""):
        login, weight_str = m.group(1), m.group(2)
        try:
            w = float(weight_str)
        except ValueError:
            continue
        if w < 0:
            continue
        result[login] += w
    return dict(result)


def find_backlog_file(edpa_root: Path, item_id: str) -> Path | None:
    """Locate .edpa/backlog/<dir>/<item_id>.md; None if missing."""
    prefix = item_id.split("-")[0]
    type_dir = PREFIX_TO_DIR.get(prefix, "stories")
    candidate = edpa_root / "backlog" / type_dir / f"{item_id}.md"
    if candidate.exists():
        return candidate
    for d in PREFIX_TO_DIR.values():
        p = edpa_root / "backlog" / d / f"{item_id}.md"
        if p.exists():
            return p
    return None


def load_people_map(edpa_root: Path) -> dict[str, str]:
    """Build github_login → person_id map from .edpa/config/people.yaml."""
    people_path = edpa_root / "config" / "people.yaml"
    if not people_path.exists():
        return {}
    try:
        data = yaml.safe_load(people_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    mapping: dict[str, str] = {}
    for p in data.get("people", []) or []:
        pid = p.get("id", "")
        github = p.get("github", "")
        if github:
            mapping[github.lower()] = pid
        # Fallback: bare email/name lookup for legacy data
        if p.get("email"):
            mapping[p["email"].lower()] = pid
        if p.get("name"):
            mapping[p["name"].lower()] = pid
    # Canonical id always resolves to itself and takes precedence over any
    # github/email/name collision. Lets `/contribute @<id>` target a specific
    # contract for multi-contract people who share a github handle (R-2:
    # bob-arch + bob-pm share one login, so the shared handle is ambiguous —
    # address them by id). ids are unique, so this pass is collision-free.
    for p in data.get("people", []) or []:
        pid = p.get("id", "")
        if pid:
            mapping[pid.lower()] = pid
    return mapping


def load_signal_weights(edpa_root: Path) -> dict[str, float]:
    """Load signal weights from .edpa/config/cw_heuristics.yaml.

    Falls back to DEFAULT_SIGNAL_WEIGHTS when missing or unparseable.
    The `signals:` block at the top level holds the 3 base weights.
    Manual directives (`manual:*` types) carry the user-supplied
    `weight:X` value verbatim — they're not weighted by heuristics.
    """
    h_path = edpa_root / "config" / "cw_heuristics.yaml"
    if not h_path.exists():
        return dict(DEFAULT_SIGNAL_WEIGHTS)
    try:
        data = yaml.safe_load(h_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return dict(DEFAULT_SIGNAL_WEIGHTS)
    weights = dict(DEFAULT_SIGNAL_WEIGHTS)
    for key in DEFAULT_SIGNAL_WEIGHTS:
        if key in (data.get("signals") or {}):
            try:
                weights[key] = float(data["signals"][key])
            except (TypeError, ValueError):
                pass
    return weights


def detect_repo_from_config(edpa_root: Path) -> str | None:
    cfg = edpa_root / "config" / "edpa.yaml"
    if not cfg.exists():
        return None
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return None
    sync = data.get("sync") or {}
    org, repo = sync.get("github_org"), sync.get("github_repo")
    return f"{org}/{repo}" if org and repo else None


def load_issue_map(edpa_root: Path) -> dict[str, int]:
    """Map item_id → GH issue_number from .edpa/config/issue_map.yaml."""
    path = edpa_root / "config" / "issue_map.yaml"
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, dict):
        return {}
    out: dict[str, int] = {}
    for k, v in items.items():
        if isinstance(v, dict) and "issue_number" in v:
            out[k] = int(v["issue_number"])
    return out


# ─── Signal collection ──────────────────────────────────────────────────────


def read_evidence(item_path: Path) -> list[dict]:
    """Read materialized PR/local signals from an item's YAML ``evidence[]``.

    V2.1 ADR-012 rename (was ``ci_signals[]`` in V2.0): the block holds
    deterministic event-derived signals (pr_reviewer, issue_comment
    from CI; commit_author, yaml_edit:* from local hooks in V2.1+).
    Returns the entries shaped like ``_signal()`` output so
    the aggregator can mix them with any remaining live collectors.

    Backward compatible: if the YAML still has the legacy
    ``ci_signals[]`` block (V2.0 items not yet migrated), it is read
    transparently. The next write through ``sync_pr_contributions.py``
    or ``migrate_evidence_rename.py`` converges the file on
    ``evidence[]``.

    Returns ``[]`` if the file is missing or has neither block.
    """
    if not item_path.exists():
        return []
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from _md_frontmatter import load_md  # noqa: E402
    finally:
        sys.path.pop(0)
    data = load_md(item_path) or {}
    raw = data.get("evidence")
    if raw is None:
        raw = data.get("ci_signals") or []
    if not isinstance(raw, list):
        return []
    out = []
    for s in raw:
        if not isinstance(s, dict):
            continue
        out.append({
            "type": s.get("type", ""),
            "ref": s.get("ref", ""),
            "login": s.get("person", ""),
            "weight": float(s.get("weight", 0)),
            "detected_at": s.get("at", utc_now_iso()),
        })
    return out


# Backward-compat alias for V2.0 callers; will be removed in V3.0.
read_ci_signals = read_evidence


def _signal(stype: str, ref: str, login: str, weight: float,
            excerpt: str | None = None) -> dict:
    """Build a normalized signal record with detected_at timestamp."""
    sig: dict = {
        "type": stype,
        "ref": ref,
        "login": login,
        "weight": float(weight),
        "detected_at": utc_now_iso(),
    }
    if excerpt:
        sig["excerpt"] = excerpt.strip()
    return sig


def _excerpt_for(text: str, login: str) -> str:
    """Return the first /contribute line mentioning @login, or empty string."""
    for line in (text or "").splitlines():
        if f"@{login}" in line and "/contribute" in line.lower():
            return line.strip()
    return ""


def collect_pr_signals(repo: str, pr_num: int,
                       weights: dict[str, float]) -> list[dict]:
    """PR author + commit authors + reviewers + manual directives in body
    and commit messages."""
    pr = run_gh(["pr", "view", str(pr_num), "--json",
                 "author,body,commits,reviews"], repo=repo)
    if not pr:
        return []

    out: list[dict] = []
    pr_author = (pr.get("author") or {}).get("login", "")
    pr_body = pr.get("body", "") or ""

    # 1. Commit authors (PR author included — credited via their commits)
    seen_commit_authors: set[str] = set()
    for c in pr.get("commits", []) or []:
        sha = (c.get("oid") or "")[:7]  # short sha for ref readability
        for a in c.get("authors", []) or []:
            login = a.get("login", "")
            if login:
                key = (login, sha)
                if key in seen_commit_authors:
                    continue
                seen_commit_authors.add(key)
                out.append(_signal(
                    stype="commit_author",
                    ref=f"pr#{pr_num}/commit/{sha}",
                    login=login,
                    weight=weights["commit_author"],
                ))

        # 2. Manual /contribute in commit message
        msg = (c.get("messageHeadline") or "") + "\n" + (c.get("messageBody") or "")
        for login, w in parse_contribute_directives(msg).items():
            out.append(_signal(
                stype="manual:commit_message",
                ref=f"commit/{sha}/message",
                login=login,
                weight=w,
                excerpt=_excerpt_for(msg, login),
            ))

    # 3. PR reviewers
    seen_reviews: set[tuple[str, str]] = set()
    for r in pr.get("reviews", []) or []:
        rid = str(r.get("id", ""))
        login = (r.get("author") or {}).get("login", "")
        if login and login != pr_author and (login, rid) not in seen_reviews:
            seen_reviews.add((login, rid))
            ref = f"pr#{pr_num}/review/{rid}" if rid else f"pr#{pr_num}/review"
            out.append(_signal(
                stype="pr_reviewer",
                ref=ref,
                login=login,
                weight=weights["pr_reviewer"],
            ))

    # 4. Manual /contribute in PR body
    for login, w in parse_contribute_directives(pr_body).items():
        out.append(_signal(
            stype="manual:pr_body",
            ref=f"pr#{pr_num}/body",
            login=login,
            weight=w,
            excerpt=_excerpt_for(pr_body, login),
        ))

    return out


def collect_issue_signals(repo: str, issue_num: int,
                          weights: dict[str, float]) -> list[dict]:
    """Issue body + comments → issue_comment + manual:issue_body +
    manual:issue_comment signals."""
    issue = run_gh(["issue", "view", str(issue_num), "--json",
                    "body,comments"], repo=repo)
    if not issue:
        return []

    out: list[dict] = []
    body = issue.get("body", "") or ""

    # 1. /contribute in issue body
    for login, w in parse_contribute_directives(body).items():
        out.append(_signal(
            stype="manual:issue_body",
            ref=f"issue#{issue_num}/body",
            login=login,
            weight=w,
            excerpt=_excerpt_for(body, login),
        ))

    # 2. Comments — both as issue_comment evidence + manual directives
    for c in issue.get("comments", []) or []:
        cid = str(c.get("id", ""))
        login = (c.get("author") or {}).get("login", "")
        comment_body = c.get("body", "") or ""

        # Skip bot comments (edpa-bot, github-actions, etc.)
        if login.endswith("[bot]") or login in {"edpa-bot", "github-actions"}:
            continue

        if login:
            ref = (f"issue#{issue_num}/comment/{cid}" if cid
                   else f"issue#{issue_num}/comment")
            out.append(_signal(
                stype="issue_comment",
                ref=ref,
                login=login,
                weight=weights["issue_comment"],
            ))

        # /contribute inside the comment
        for ovr_login, w in parse_contribute_directives(comment_body).items():
            ref = (f"issue#{issue_num}/comment/{cid}" if cid
                   else f"issue#{issue_num}/comment")
            out.append(_signal(
                stype="manual:issue_comment",
                ref=ref,
                login=ovr_login,
                weight=w,
                excerpt=_excerpt_for(comment_body, ovr_login),
            ))

    return out


def collect_pr_comment_signals(repo: str, pr_num: int) -> list[dict]:
    """/contribute directives in PR-level (issue-style) comments — separate
    surface from PR review threads. Uses gh api directly since `gh pr view
    --json comments` is not always populated."""
    raw = run_gh(["api", f"repos/{repo}/issues/{pr_num}/comments"], repo=None)
    if not isinstance(raw, list):
        return []

    out: list[dict] = []
    for c in raw:
        cid = str(c.get("id", ""))
        login = (c.get("user") or {}).get("login", "")
        body = c.get("body", "") or ""
        if login.endswith("[bot]"):
            continue
        for ovr_login, w in parse_contribute_directives(body).items():
            ref = f"pr#{pr_num}/comment/{cid}" if cid else f"pr#{pr_num}/comment"
            out.append(_signal(
                stype="manual:pr_comment",
                ref=ref,
                login=ovr_login,
                weight=w,
                excerpt=_excerpt_for(body, ovr_login),
            ))
    return out


# ─── Aggregation ─────────────────────────────────────────────────────────────


def aggregate_signals(signals: list[dict],
                      people_map: dict[str, str]) -> list[dict] | None:
    """Group signals by resolved person_id, compute contribution_score and
    per-item-normalized cw share. Returns the contributors[] list ready
    to write into the YAML — or None when no signals fired (caller's
    edge-case handling, see Q1 in v1.11 RFC)."""
    if not signals:
        return None

    # Resolve every signal's login → person_id, normalising case.
    by_person: dict[str, list[dict]] = defaultdict(list)
    total_score = 0.0
    unknown: set[str] = set()
    for sig in signals:
        login = sig["login"]
        person_id = people_map.get(login.lower(), login)
        if login.lower() not in people_map:
            unknown.add(login)
        # Preserve a clean signal record for YAML — drop the working
        # `login` field, add resolved person id later in contributor entry.
        clean = {k: v for k, v in sig.items() if k != "login"}
        by_person[person_id].append(clean)
        total_score += sig["weight"]
    # Surface tokens that resolved to neither a known github handle nor a
    # person id — these are credited as-is and the engine awards 0h, so a
    # silent typo would otherwise vanish without a trace.
    for tok in sorted(unknown):
        print(f"WARNING: contribution token '{tok}' matches no github handle "
              f"or person id in people.yaml — credited as-is (engine awards 0h "
              f"unless it is a real person id; typo or external contributor?).",
              file=sys.stderr)

    if total_score <= 0:
        return None

    # Sort persons by contribution_score desc for deterministic YAML order.
    contributors: list[dict] = []
    person_scores = [
        (pid, sum(s["weight"] for s in sigs), sigs)
        for pid, sigs in by_person.items()
    ]
    person_scores.sort(key=lambda x: (-x[1], x[0]))

    for pid, score, sigs in person_scores:
        cw = score / total_score
        # Sort signals deterministic by (type, ref) so two detect runs on
        # identical GH state produce byte-identical YAML.
        sigs_sorted = sorted(sigs, key=lambda s: (s["type"], s["ref"]))
        contributors.append({
            "person": pid,
            "cw": round(cw, 4),
            "contribution_score": round(score, 2),
            "signals": sigs_sorted,
        })
    return contributors


def write_contributors(item_path: Path,
                       new_contributors: list[dict],
                       *, dry_run: bool = False) -> bool:
    """Replace `contributors[]` block in a backlog `.md` file.

    v1.11 semantics: full rewrite, no merge-with-existing. Re-running
    detect_contributors is idempotent — same signals → same output.
    Returns True when the file changed.
    """
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from _md_frontmatter import load_md, update_frontmatter_field
    finally:
        _sys.path.pop(0)

    data = load_md(item_path) or {}
    old = data.get("contributors", []) or []
    if old == new_contributors:
        return False
    if not dry_run:
        update_frontmatter_field(item_path, "contributors", new_contributors)
    return True


# ─── Per-item processing ────────────────────────────────────────────────────


def find_prs_touching_item(repo: str, item_id: str,
                           since: datetime | None) -> list[int]:
    """Search merged PRs whose title/branch/body references item_id."""
    since_iso = since.strftime("%Y-%m-%d") if since else "2020-01-01"
    query = f"is:pr is:merged merged:>={since_iso} {item_id}"
    res = run_gh(["search", "prs", "--repo", repo,
                  "--json", "number,title", "--limit", "100", query])
    if not isinstance(res, list):
        return []
    return [int(p["number"]) for p in res if "number" in p]


def process_item(edpa_root: Path, repo: str, item_id: str,
                 *, weights: dict[str, float],
                 people_map: dict[str, str],
                 issue_map: dict[str, int],
                 pr_scope: list[int] | None = None,
                 since: datetime | None = None,
                 dry_run: bool = False) -> tuple[bool, int]:
    """Recompute contributors[] for a single item from all known sources.

    pr_scope: optional explicit list of PR numbers to consider (CI mode
    typically passes [PR_NUMBER]). When None, all merged PRs touching
    the item since `since` are searched.

    Returns (changed: bool, n_signals: int).
    """
    item_path = find_backlog_file(edpa_root, item_id)
    if not item_path:
        print(f"  {item_id}: no backlog file — skipping", file=sys.stderr)
        return False, 0

    issue_num = issue_map.get(item_id)
    if pr_scope is None:
        pr_nums = find_prs_touching_item(repo, item_id, since)
    else:
        pr_nums = list(pr_scope)

    signals: list[dict] = []
    # V2 ADR-012: signals arrive via the item's evidence[] block —
    # written by sync_pr_contributions.py (CI) or local hooks. The
    # runtime gh path below is a no-op unless EDPA_USE_GH=1 (escape
    # hatch for local debug).
    signals.extend(read_evidence(item_path))
    if issue_num:
        signals.extend(collect_issue_signals(repo, issue_num, weights))
    for pr_num in sorted(set(pr_nums)):
        signals.extend(collect_pr_signals(repo, pr_num, weights))
        signals.extend(collect_pr_comment_signals(repo, pr_num))

    n = len(signals)
    if n == 0:
        # Q1 edge case: warn-and-skip. Existing contributors[] left intact.
        print(f"  {item_id}: 0 signals detected — leaving contributors[] untouched")
        return False, 0

    contributors = aggregate_signals(signals, people_map)
    if not contributors:
        print(f"  {item_id}: aggregation produced 0 contributors — skipping")
        return False, n

    changed = write_contributors(item_path, contributors, dry_run=dry_run)
    verb = "would update" if dry_run else ("updated" if changed else "unchanged")
    print(f"  {item_id}: {len(contributors)} contributors, {n} signals → {verb}")
    return changed, n


# ─── Entry-point flows ──────────────────────────────────────────────────────


def cmd_pr(edpa_root: Path, repo: str, pr_number: int,
           dry_run: bool = False) -> int:
    """Recompute contributors[] for every item referenced by a single PR."""
    weights = load_signal_weights(edpa_root)
    people_map = load_people_map(edpa_root)
    issue_map = load_issue_map(edpa_root)

    pr = run_gh(["pr", "view", str(pr_number),
                 "--json", "title,headRefName,body,commits"], repo=repo)
    if not pr:
        print(f"PR #{pr_number}: not found", file=sys.stderr)
        return 1

    item_ids: set[str] = set()
    item_ids.update(extract_item_ids(pr.get("title", "")))
    item_ids.update(extract_item_ids(pr.get("headRefName", "")))
    item_ids.update(extract_item_ids(pr.get("body", "")))
    for c in pr.get("commits", []) or []:
        msg = (c.get("messageHeadline") or "") + " " + (c.get("messageBody") or "")
        item_ids.update(extract_item_ids(msg))

    if not item_ids:
        print(f"PR #{pr_number}: no item IDs referenced", file=sys.stderr)
        return 0

    print(f"PR #{pr_number} touches: {sorted(item_ids)}")
    updated = 0
    for item_id in sorted(item_ids):
        changed, _ = process_item(
            edpa_root, repo, item_id,
            weights=weights, people_map=people_map, issue_map=issue_map,
            pr_scope=[pr_number],
            dry_run=dry_run,
        )
        if changed:
            updated += 1
    print(f"\n✓ {updated}/{len(item_ids)} item(s) updated")
    return 0


def cmd_item(edpa_root: Path, repo: str, item_id: str,
             since: datetime | None, dry_run: bool = False) -> int:
    """Walk all merged PRs touching item_id since `since` and recompute."""
    weights = load_signal_weights(edpa_root)
    people_map = load_people_map(edpa_root)
    issue_map = load_issue_map(edpa_root)

    changed, n = process_item(
        edpa_root, repo, item_id,
        weights=weights, people_map=people_map, issue_map=issue_map,
        since=since, dry_run=dry_run,
    )
    return 0 if (changed or n == 0) else 0


def cmd_ci(edpa_root: Path, repo: str, dry_run: bool = False) -> int:
    """Driven by edpa-contributor-detect.yml workflow — env vars give PR context."""
    pr_number = os.environ.get("PR_NUMBER", "").strip()
    if not pr_number:
        print("CI mode requires PR_NUMBER env var", file=sys.stderr)
        return 1
    return cmd_pr(edpa_root, repo, int(pr_number), dry_run=dry_run)


def cmd_all_items(edpa_root: Path, dry_run: bool = False) -> int:
    """V2.1 C7.6 — refresh contributors[] for EVERY item with evidence.

    Run before engine at close-iteration so gate events (Feature/Epic/
    Initiative) and Story Done credits see fresh contributors[]
    reflecting the latest evidence[] aggregation — not the stale
    snapshot from whenever someone last edited the item.

    Idempotent: items without evidence[] are no-ops. Cost is O(items)
    file reads + O(signals) aggregations; trivial for backlogs <1000
    items.
    """
    weights = load_signal_weights(edpa_root)
    people_map = load_people_map(edpa_root)
    issue_map: dict = {}  # V2 doesn't use GH issue map

    type_dirs = ("initiatives", "epics", "features", "stories",
                 "defects", "events", "risks")
    n_touched = 0
    n_total = 0
    for type_dir in type_dirs:
        dir_path = edpa_root / "backlog" / type_dir
        if not dir_path.exists():
            continue
        for f in sorted(dir_path.glob("*.md")):
            item_id = f.stem
            n_total += 1
            try:
                changed, n_signals = process_item(
                    edpa_root, repo="", item_id=item_id,
                    weights=weights, people_map=people_map,
                    issue_map=issue_map, pr_scope=[], dry_run=dry_run,
                )
                if n_signals > 0:
                    n_touched += 1
            except Exception as e:
                print(f"WARN: process_item({item_id}) failed: {e}",
                      file=sys.stderr)
    verb = "would refresh" if dry_run else "refreshed"
    print(f"{verb}: {n_touched} item(s) with evidence "
          f"(scanned {n_total} total)")
    return 0


# ─── _parse_relative_since (preserved API) ─────────────────────────────────


def _parse_relative_since(since: str) -> datetime | None:
    if not since:
        return None
    s = since.strip().lower()
    m = re.fullmatch(r"(\d+)\s*(day|days|d|week|weeks|w|month|months|m)", s)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if unit.startswith("d"):
            delta = timedelta(days=n)
        elif unit.startswith("w"):
            delta = timedelta(weeks=n)
        else:
            delta = timedelta(days=30 * n)
        return datetime.now(timezone.utc) - delta
    try:
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ─── Main ──────────────────────────────────────────────────────────────────


def find_edpa_root() -> Path:
    """Locate .edpa/ from cwd upward."""
    cur = Path.cwd().resolve()
    for parent in [cur, *cur.parents]:
        if (parent / ".edpa").is_dir():
            return parent / ".edpa"
    print("ERROR: no .edpa/ directory found", file=sys.stderr)
    sys.exit(2)


def main():
    ap = argparse.ArgumentParser(
        description="EDPA contributor auto-detection (v1.11 single-source CW)"
    )
    ap.add_argument("--pr", type=int, help="Recompute contributors for items in this PR")
    ap.add_argument("--item", help="Recompute contributors for a single item ID (e.g. S-200)")
    ap.add_argument("--all-items", action="store_true",
                    help="V2.1: refresh contributors[] for every item with "
                         "evidence (run before /edpa:engine at close-iteration)")
    ap.add_argument("--since", default="30days",
                    help="With --item: how far back to scan PRs (default: 30days)")
    ap.add_argument("--repo",
                    help="GH repo (owner/name); defaults to .edpa/config/edpa.yaml")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would change without writing YAML")
    args = ap.parse_args()

    edpa_root = find_edpa_root()

    # --all-items doesn't need a repo (V2 evidence-only path).
    if args.all_items:
        return cmd_all_items(edpa_root, dry_run=args.dry_run)

    repo = args.repo or detect_repo_from_config(edpa_root)
    if not repo:
        print("ERROR: --repo required (or set sync.github_org/_repo in edpa.yaml)",
              file=sys.stderr)
        sys.exit(2)

    if args.pr:
        return cmd_pr(edpa_root, repo, args.pr, dry_run=args.dry_run)
    if args.item:
        since = _parse_relative_since(args.since)
        return cmd_item(edpa_root, repo, args.item, since, dry_run=args.dry_run)

    # CI mode (env-driven)
    if os.environ.get("PR_NUMBER"):
        return cmd_ci(edpa_root, repo, dry_run=args.dry_run)

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
