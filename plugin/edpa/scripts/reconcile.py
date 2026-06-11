#!/usr/bin/env python3
"""Reconcile git delivery evidence against backlog item status.

Closes the attribution loop: commits reference tickets (Conventional-Commit
scope, enforced by the commit-msg hook), but nothing maps merge evidence back
to ``status:`` in ``.edpa/backlog/``. Items routinely ship and stay in Funnel
— velocity under-reports and Done-only rollups miss them (defect D-17 found
26 such items).

What counts as delivery evidence (deliberately conservative):

* commits reachable from the main branch whose **subject** references the
  item ID — the CC scope ``feat(S-42): …`` or a bare ``S-42`` in the subject.
  Body mentions do NOT count: bulk/maintenance commits routinely enumerate
  many IDs they talk *about* but don't deliver.
* auto-prefixed commits (``chore(evidence):``, ``chore(ci-materialization):``,
  ``Merge``, ``Revert``, ``fixup!``, ``squash!``) never count.

Suggestion rules per delivery-tracked item (Story / Defect; Feature / Epic /
Initiative only get "Implementing" hints — their Done is a human/rollup call):

* evidence commit contained in a release tag        → suggest **Done**
* latest evidence older than ``--stale-days`` (3)   → suggest **Done**
* evidence exists, status before Implementing       → suggest **Implementing**
* status Done, zero evidence                        → **phantom** (report only;
  may be legitimate — bundle commits, docs-only delivery — but worth a look)

Read-only by default. ``--apply`` writes the suggested status (stamping
``closed_at`` from the latest evidence commit on first Done) but does NOT
git-commit — the caller commits, exactly like the other write paths.
``--check`` exits 1 when drift exists (CI-friendly). ``--json`` for machines;
the ``edpa_reconcile`` MCP tool returns the same payload (always read-only —
apply via ``edpa_item_transition`` or this CLI).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _md_frontmatter import load_md, update_frontmatter_field  # noqa: E402

ITEM_REF_RE = re.compile(r"\b[A-Z]{1,3}-\d{1,9}\b")
CC_SCOPE_RE = re.compile(r"^\w+!?\(([A-Z]{1,3}-\d{1,9})\)")
AUTO_PREFIXES = ("chore(evidence):", "chore(ci-materialization):",
                 "Merge ", "Revert ", "fixup!", "squash!")

DELIVERY_SUGGEST_TYPES = {"Story", "Defect"}
HINT_ONLY_TYPES = {"Feature", "Epic", "Initiative"}
TRACKED_TYPES = DELIVERY_SUGGEST_TYPES | HINT_ONLY_TYPES
PRE_IMPLEMENTING = {"Funnel", "Reviewing", "Analyzing", "Ready", "Backlog",
                    "Portfolio Backlog"}
BACKLOG_DIRS = ("initiatives", "epics", "features", "stories", "defects",
                "tasks", "events", "risks")


def find_repo_root(start: Path | None = None) -> Path:
    cur = (start or Path.cwd()).resolve()
    for cand in (cur, *cur.parents):
        if (cand / ".git").exists():
            return cand
    raise SystemExit("ERROR: not inside a git repository")


def _git(repo: Path, *args: str) -> str:
    res = subprocess.run(["git", "-C", str(repo), *args],
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {res.stderr.strip()}")
    return res.stdout


def detect_main_branch(repo: Path) -> str:
    for cand in ("main", "master"):
        if subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify",
                           "--quiet", cand], capture_output=True).returncode == 0:
            return cand
    raise SystemExit("ERROR: neither 'main' nor 'master' exists — pass --branch")


def load_items(edpa_root: Path) -> list[dict]:
    items = []
    for sub in BACKLOG_DIRS:
        d = edpa_root / "backlog" / sub
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.md")):
            item = load_md(f)
            if item and item.get("id"):
                item["_path"] = f
                items.append(item)
    return items


def collect_evidence(repo: Path, branch: str) -> dict[str, list[dict]]:
    """Map item ID -> evidence commits (newest first), subject-scope only."""
    out: dict[str, list[dict]] = {}
    log = _git(repo, "log", branch, "--format=%H%x1f%cI%x1f%s%x1e")
    for record in log.split("\x1e"):
        record = record.strip("\n\x00 ")
        if not record:
            continue
        sha, iso, subject = record.split("\x1f", 2)
        if subject.startswith(AUTO_PREFIXES):
            continue
        ids = set(ITEM_REF_RE.findall(subject))
        scope = CC_SCOPE_RE.match(subject)
        if scope:
            ids.add(scope.group(1))
        for iid in ids:
            out.setdefault(iid, []).append(
                {"sha": sha, "date": iso, "subject": subject})
    return out


def _to_utc_z(iso: str) -> str:
    return (datetime.fromisoformat(iso).astimezone(timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"))


def _in_release_tag(repo: Path, sha: str) -> bool:
    try:
        return bool(_git(repo, "tag", "--contains", sha).strip())
    except RuntimeError:
        return False


def build_report(repo: Path, edpa_root: Path, branch: str | None = None,
                 stale_days: int = 3) -> dict:
    branch = branch or detect_main_branch(repo)
    evidence = collect_evidence(repo, branch)
    now = datetime.now(timezone.utc)
    stuck: list[dict] = []
    phantoms: list[dict] = []
    clean = 0

    for item in load_items(edpa_root):
        itype, iid = item.get("type"), item["id"]
        if itype not in TRACKED_TYPES:
            continue
        status = item.get("status") or "Funnel"
        ev = evidence.get(iid, [])

        if status == "Done":
            if ev:
                clean += 1
            else:
                phantoms.append({"id": iid, "type": itype,
                                 "title": item.get("title", ""),
                                 "note": "Done without subject-scope commit "
                                         "evidence (bundle/docs-only delivery?)"})
            continue

        if not ev:
            continue  # no evidence, not Done — backlog item not started, fine

        latest = ev[0]
        latest_dt = datetime.fromisoformat(latest["date"])
        released = _in_release_tag(repo, latest["sha"])
        is_stale = (now - latest_dt.astimezone(timezone.utc)
                    ) >= timedelta(days=stale_days)

        if itype in DELIVERY_SUGGEST_TYPES and (released or is_stale):
            suggested, reason = "Done", (
                "evidence in release tag" if released
                else f"merged & quiet ≥{stale_days}d")
        elif status in PRE_IMPLEMENTING:
            suggested, reason = "Implementing", "delivery evidence exists"
        else:
            clean += 1
            continue

        stuck.append({
            "id": iid, "type": itype, "title": item.get("title", ""),
            "status": status, "suggested": suggested, "reason": reason,
            "evidence_commits": len(ev), "latest_sha": latest["sha"][:9],
            "latest_subject": latest["subject"][:80],
            "closed_at": _to_utc_z(latest["date"]) if suggested == "Done" else None,
            "_path": str(item["_path"]),
        })

    return {"branch": branch, "stale_days": stale_days, "stuck": stuck,
            "phantoms": phantoms, "clean": clean,
            "drift": bool(stuck)}


def apply_suggestions(report: dict) -> int:
    n = 0
    for s in report["stuck"]:
        path = Path(s["_path"])
        update_frontmatter_field(path, "status", s["suggested"])
        if s["suggested"] == "Done" and s["closed_at"]:
            item = load_md(path)
            if item is not None and not item.get("closed_at"):
                update_frontmatter_field(path, "closed_at", s["closed_at"])
        n += 1
    return n


def render_text(report: dict) -> str:
    lines = [f"Reconcile — branch {report['branch']}, "
             f"stale-days {report['stale_days']}", ""]
    if report["stuck"]:
        lines.append(f"  Drift ({len(report['stuck'])} item(s)):")
        for s in report["stuck"]:
            lines.append(
                f"    {s['id']:<6} {s['status']:<13} → {s['suggested']:<13}"
                f" [{s['reason']}; {s['evidence_commits']} commit(s),"
                f" last {s['latest_sha']}]")
    else:
        lines.append("  No drift — every evidenced item is at/past the right status.")
    if report["phantoms"]:
        lines.append("")
        lines.append(f"  Done without evidence ({len(report['phantoms'])}, review only):")
        for p in report["phantoms"]:
            lines.append(f"    {p['id']:<6} {p['title'][:60]}")
    lines.append("")
    lines.append(f"  Clean: {report['clean']} item(s)")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--edpa-root", default=None,
                    help="Path to .edpa/ (default: <repo>/.edpa)")
    ap.add_argument("--branch", default=None,
                    help="Branch to read evidence from (default: main/master)")
    ap.add_argument("--stale-days", type=int, default=3,
                    help="Quiet days after last evidence before suggesting Done (default 3)")
    ap.add_argument("--json", action="store_true", help="Machine-readable output")
    ap.add_argument("--apply", action="store_true",
                    help="Write suggested statuses (+closed_at) to the backlog files")
    ap.add_argument("--check", action="store_true",
                    help="Exit 1 when drift exists (CI gate)")
    args = ap.parse_args()

    repo = find_repo_root()
    edpa_root = Path(args.edpa_root) if args.edpa_root else repo / ".edpa"
    if not edpa_root.is_dir():
        print(f"ERROR: {edpa_root} not found", file=sys.stderr)
        return 2

    report = build_report(repo, edpa_root, args.branch, args.stale_days)

    applied = 0
    if args.apply and report["stuck"]:
        applied = apply_suggestions(report)

    if args.json:
        payload = {k: v for k, v in report.items()}
        payload["stuck"] = [{k: v for k, v in s.items() if k != "_path"}
                            for s in report["stuck"]]
        payload["applied"] = applied
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_text(report))
        if applied:
            print(f"\n  Applied {applied} status change(s) — review with "
                  f"`git diff .edpa/backlog/` and commit.")
        elif report["stuck"]:
            print("\n  Re-run with --apply to write these statuses "
                  "(or transition via /edpa:change-state).")

    if args.check and report["drift"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
