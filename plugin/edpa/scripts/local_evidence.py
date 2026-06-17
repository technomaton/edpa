#!/usr/bin/env python3
"""Emit local evidence signals from a git commit (post-commit hook).

V2.1 closure of the local-first gap: V2.0 wrote ``evidence[]`` only via
the GH Action ``sync_pr_contributions.py``, so projects without GH CI
got no PR-style attribution at all. This script runs as a post-commit
hook on every commit and emits the signals that don't need GH:

  - ``commit_author``        — author of the commit, credited to the
                               item(s) the commit touches
  - ``manual:commit_message`` — ``/contribute @login weight:N`` in the
                               commit body (additive override)

What it does NOT emit (those still come from the optional CI workflow):

  - ``pr_reviewer``   — review is a GH-side action
  - ``issue_comment`` — comment thread lives in GH issues

Item attribution sources (in order of precedence):

  1. EDPA item IDs in the commit subject/body (regex ``[A-Z]{1,3}-\\d+``)
  2. Item IDs derived from changed file paths
     (``.edpa/backlog/{type}/S-N.md`` → S-N)

If neither produces a match, the script exits 0 silently. The
companion pre-commit hook (``pre-commit-ticket-attached``, Krok C4)
warns about commits without item refs at commit-time, before the
attribution problem reaches this hook.

Self-recursion guard: the follow-up commit this script creates has
subject prefix ``chore(evidence):`` — the next post-commit invocation
sees that, skips, and exits 0. No loops.

Usage (typically called by .git/hooks/post-commit, not by humans):
    python3 .edpa/engine/scripts/local_evidence.py
"""

from __future__ import annotations

try:  # best-effort UTF-8 stdio on legacy Windows consoles (cp1250)
    import _console  # noqa: F401
except ImportError:
    pass
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    from _md_frontmatter import load_md, save_md_item  # noqa: E402
    from id_counter import TYPE_DIRS  # noqa: E402
finally:
    sys.path.pop(0)


_SELF_COMMIT_PREFIX = "chore(evidence):"

_ITEM_REF_RE = re.compile(r"\b([A-Z]{1,3}-\d{1,9})\b")
_BACKLOG_PATH_RE = re.compile(
    r"\.edpa/backlog/([^/]+)/([A-Z]{1,3}-\d{1,9})\.md$"
)
_CONTRIBUTE_RE = re.compile(
    r"/contribute\s+@([A-Za-z0-9_-]+)\s+weight:([0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
_AGENT_COAUTHOR_RE = re.compile(
    r"^Co-[Aa]uthored-[Bb]y:\s+(Claude[^<\r\n]*)<[^>]*@anthropic\.com>",
    re.MULTILINE,
)

PREFIX_TO_DIR = {
    "I": "initiatives", "E": "epics", "F": "features", "S": "stories",
    "D": "defects", "EV": "events", "R": "risks",
}

# Default weights — overridable via .edpa/config/cw_heuristics.yaml.
DEFAULT_WEIGHTS = {
    "commit_author": 2.78,
}

ENV_DISABLE = "EDPA_NO_LOCAL_EVIDENCE"


# ─── git helpers ────────────────────────────────────────────────────────────


def _git(args: list[str], cwd: Path | None = None) -> str | None:
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        return None
    if r.returncode != 0:
        return None
    return r.stdout


def _repo_root() -> Path | None:
    out = _git(["rev-parse", "--show-toplevel"])
    return Path(out.strip()) if out else None


def _head_commit(repo_root: Path) -> dict | None:
    """Return {sha, subject, body, author_email, author_name, parents,
    changed_files} for HEAD, or None on failure."""
    info = _git(
        ["log", "-1", "--format=%H%x1f%P%x1f%ae%x1f%an%x1f%s%x1f%B%x1e"],
        cwd=repo_root,
    )
    if not info:
        return None
    rec = info.split("\x1e", 1)[0]
    parts = rec.split("\x1f")
    if len(parts) < 6:
        return None
    sha, parents, email, name, subject, body = parts[:6]
    body = body.strip()
    changed = _git(
        ["log", "-1", "--name-only", "--format=", "HEAD"], cwd=repo_root,
    )
    files = [p for p in (changed or "").splitlines() if p]
    return {
        "sha": sha,
        "parents": parents.split() if parents else [],
        "author_email": email,
        "author_name": name,
        "subject": subject,
        "body": body,
        "changed_files": files,
    }


# ─── people resolution ─────────────────────────────────────────────────────


def _load_people(edpa_root: Path) -> list[dict]:
    p = edpa_root / "config" / "people.yaml"
    if not p.exists():
        return []
    import yaml
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return []
    return data.get("people") or []


def _resolve_person(email: str, name: str, people: list[dict]) -> str | None:
    """Map a git author email/name to a person id from people.yaml.

    Order: email exact match → name exact match → github login prefix
    (alice@x.dev → 'alice' if github: alice exists). Returns None on
    no match (caller skips emission to avoid bogus attributions)."""
    if not email and not name:
        return None
    e = (email or "").lower()
    n = (name or "").lower()
    local = e.split("@", 1)[0] if "@" in e else ""
    for p in people:
        if not isinstance(p, dict):
            continue
        if p.get("email", "").lower() == e and e:
            return p.get("id")
    for p in people:
        if isinstance(p, dict) and p.get("name", "").lower() == n and n:
            return p.get("id")
    if local:
        for p in people:
            if not isinstance(p, dict):
                continue
            if p.get("id", "").lower() == local:
                return p.get("id")
            if p.get("github", "").lower() == local:
                return p.get("id")
    return None


def _load_weights(edpa_root: Path) -> dict[str, float]:
    h = edpa_root / "config" / "cw_heuristics.yaml"
    if not h.exists():
        return dict(DEFAULT_WEIGHTS)
    import yaml
    try:
        data = yaml.safe_load(h.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return dict(DEFAULT_WEIGHTS)
    sig = data.get("signal_weights") or {}
    return {**DEFAULT_WEIGHTS, **{k: float(v) for k, v in sig.items()}}


# ─── item detection ─────────────────────────────────────────────────────────


def detect_items(commit: dict) -> list[str]:
    """Return unique list of item IDs referenced by the commit."""
    ids: list[str] = []
    seen: set[str] = set()
    for chunk in (commit["subject"], commit["body"]):
        for m in _ITEM_REF_RE.findall(chunk or ""):
            if m not in seen:
                seen.add(m)
                ids.append(m)
    for path in commit["changed_files"]:
        m = _BACKLOG_PATH_RE.search(path)
        if m:
            iid = m.group(2)
            if iid not in seen:
                seen.add(iid)
                ids.append(iid)
    return ids


def find_item_path(edpa_root: Path, item_id: str) -> Path | None:
    prefix = item_id.split("-", 1)[0]
    dir_name = PREFIX_TO_DIR.get(prefix)
    if not dir_name:
        return None
    p = edpa_root / "backlog" / dir_name / f"{item_id}.md"
    return p if p.exists() else None


# ─── signal emission ───────────────────────────────────────────────────────


def _normalize_agent_name(raw: str) -> str:
    """'Claude Sonnet 4.6 ' → 'claude-sonnet-4-6'."""
    normalized = re.sub(r"[\s.]+", "-", raw.strip()).lower()
    return re.sub(r"-+", "-", normalized)


def build_signals(commit: dict, items: list[str], person_id: str,
                  weights: dict[str, float]) -> list[dict]:
    """Build the list of (item_id, signal_dict) tuples for one commit."""
    sha = commit["sha"]
    short = sha[:7]
    iso = _git(["log", "-1", "--format=%aI", sha]) or ""
    iso = iso.strip() or _git(["log", "-1", "--format=%aI"]) or ""

    # Detect AI co-authors from Co-Authored-By: Claude ... <...@anthropic.com>
    body = commit["body"] or ""
    agent_names = [
        _normalize_agent_name(m)
        for m in _AGENT_COAUTHOR_RE.findall(body)
    ]

    out: list[dict] = []
    for iid in items:
        # 1. commit_author (always, once per commit per item)
        out.append({
            "item_id": iid,
            "signal": {
                "type": "commit_author",
                "person": person_id,
                "weight": weights.get("commit_author", 2.78),
                "ref": f"commit/{short}",
                "at": iso,
            },
        })
        # 2. agent_contribution — one signal per distinct AI co-author
        for agent in dict.fromkeys(agent_names):  # deduplicate, preserve order
            out.append({
                "item_id": iid,
                "signal": {
                    "type": "agent_contribution",
                    "agent": agent,
                    "person": "_claude",
                    "weight": weights.get("agent_contribution", 1.0),
                    "ref": f"commit/{short}/agent/{agent}",
                    "at": iso,
                },
            })
        # 3. /contribute directives in commit body (additive override)
        for login, w_str in _CONTRIBUTE_RE.findall(body):
            try:
                w = float(w_str)
            except ValueError:
                continue
            if not (0 <= w <= 10):
                continue
            out.append({
                "item_id": iid,
                "signal": {
                    "type": "manual:commit_message",
                    "person": login,
                    "weight": w,
                    "ref": f"commit/{short}/contrib/{login}",
                    "at": iso,
                },
            })
    return out


def _apply_to_item(item_path: Path, new_sigs: list[dict]) -> bool:
    """Merge new signals into item.evidence[] (dedup by ref). Return True
    if anything changed on disk."""
    data = load_md(item_path) or {}
    body = data.pop("body", "") if isinstance(data, dict) else ""
    existing = data.get("evidence")
    if existing is None:
        existing = data.get("ci_signals") or []  # backward-compat read
    if not isinstance(existing, list):
        existing = []

    by_ref = {s.get("ref"): s for s in existing if isinstance(s, dict)}
    changed = False
    for s in new_sigs:
        ref = s.get("ref")
        if ref in by_ref:
            continue
        by_ref[ref] = s
        changed = True
    if not changed:
        return False

    merged = [by_ref[k] for k in sorted(by_ref) if k is not None]
    data["evidence"] = merged
    if "ci_signals" in data:
        del data["ci_signals"]  # converge on V2.1 shape
    save_md_item(item_path, {**data, "body": body})
    return True


def _commit_evidence(repo_root: Path, paths: list[Path],
                     commit: dict, items: list[str]) -> bool:
    """Stage + commit the evidence changes. --no-verify is safe because
    we're modifying frontmatter only (no new IDs, counter unchanged)."""
    rels = [str(p.relative_to(repo_root)) for p in paths]
    add = subprocess.run(
        ["git", "add", *rels],
        cwd=str(repo_root), capture_output=True, text=True,
    )
    if add.returncode != 0:
        return False
    items_str = ",".join(items)
    msg = (f"{_SELF_COMMIT_PREFIX} {items_str} from {commit['sha'][:7]}\n\n"
           f"Auto-generated by local_evidence.py post-commit hook.\n"
           f"Source commit: {commit['sha']}")
    commit_res = subprocess.run(
        ["git", "commit", "--no-verify", "-m", msg],
        cwd=str(repo_root), capture_output=True, text=True,
    )
    return commit_res.returncode == 0


# ─── main ───────────────────────────────────────────────────────────────────


def main() -> int:
    if os.environ.get(ENV_DISABLE) == "1":
        return 0  # explicit opt-out (e.g. during bulk imports, rebases)

    repo_root = _repo_root()
    if not repo_root:
        return 0  # not in a git repo

    edpa_root = repo_root / ".edpa"
    if not edpa_root.exists():
        return 0  # not an EDPA project

    commit = _head_commit(repo_root)
    if not commit:
        return 0

    # Self-recursion guard
    if commit["subject"].startswith(_SELF_COMMIT_PREFIX):
        return 0

    # Skip merge commits — they aggregate, not author
    if len(commit["parents"]) > 1:
        return 0

    # Skip bot commits (CI workflows etc.)
    if "edpa-bot" in commit["author_email"].lower():
        return 0

    items = detect_items(commit)
    if not items:
        return 0  # no item refs → nothing to attribute

    people = _load_people(edpa_root)
    person_id = _resolve_person(commit["author_email"],
                                commit["author_name"], people)
    if not person_id:
        # Don't crash — just emit a stderr note. The commit succeeded;
        # losing one signal is better than blocking work.
        print(
            f"local_evidence: skipped — {commit['author_email']!r} not "
            f"in .edpa/config/people.yaml (add github/email to attribute "
            f"future commits).",
            file=sys.stderr,
        )
        return 0

    weights = _load_weights(edpa_root)
    new_sigs = build_signals(commit, items, person_id, weights)
    if not new_sigs:
        return 0

    grouped: dict[str, list[dict]] = {}
    for s in new_sigs:
        grouped.setdefault(s["item_id"], []).append(s["signal"])

    touched_paths: list[Path] = []
    for iid, sigs in grouped.items():
        p = find_item_path(edpa_root, iid)
        if not p:
            print(
                f"local_evidence: item {iid!r} referenced but not found in "
                f"backlog — skipping its signal.",
                file=sys.stderr,
            )
            continue
        if _apply_to_item(p, sigs):
            touched_paths.append(p)

    if not touched_paths:
        return 0

    if _commit_evidence(repo_root, touched_paths, commit, list(grouped)):
        print(f"local_evidence: appended to {len(touched_paths)} "
              f"item(s) from {commit['sha'][:7]}")
    else:
        print(f"local_evidence: warning — failed to commit evidence update",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
