"""Single GitHub issue creation pipeline shared by backlog.py / sync.py /
project_setup.py.

Before this module the three callers had drifted copies of the same flow
(create → rewrite title → set Issue Type → add to project → link parent),
which produced the pilot-user bugs fixed in PR1: cmd_add skipped the
sub-issue link, the title rewrite, and ID synchronization. Centralising
the pipeline guarantees those three behaviours stay aligned.

The factory exposes one function, ``create_gh_issue``. Idempotency (reuse
of an existing issue when a title already matches) stays with the caller
because the three sites have incompatible idempotency models:
project_setup.py does bulk lookup by title before the loop, sync.py push
relies on issue_map.yaml, and cmd_add is single-shot.

Two creation modes:
* ``edpa_id`` is given (sync.py push, project_setup.py) — single
  ``gh issue create`` with the final title ``"{edpa_id}: {raw_title}"``.
* ``edpa_id`` is omitted (backlog.py add) — ``gh issue create`` with the
  raw title, then ``gh issue edit --title`` once the server-assigned
  number is known.

Hard failures (create / title rewrite) raise ``RuntimeError``; soft
failures (Issue Type assign, project add, sub-issue link) populate
``warnings`` in the return dict so the caller decides how loudly to surface
them. This matches what backlog.py already does inline — sub-issue link
failure should not abort the local file write.
"""
from __future__ import annotations

import json
import logging
import subprocess
from typing import Iterable

logger = logging.getLogger(__name__)


TYPE_PREFIX = {
    "Initiative": "I",
    "Epic":       "E",
    "Feature":    "F",
    "Story":      "S",
    "Defect":     "D",
    "Event":      "EV",
}


def _gh(args: list[str], *, timeout: int = 30) -> "subprocess.CompletedProcess[str]":
    """Run ``gh`` with the given args, capturing output. Centralised so
    tests can monkey-patch one entry point."""
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def _gh_graphql(query: str) -> "dict | None":
    """Execute a GraphQL query via ``gh api graphql -f query=...``.
    Returns parsed JSON or None on subprocess failure (the caller treats
    None as 'soft failure' — log + warn, don't abort)."""
    try:
        result = _gh(["gh", "api", "graphql", "-f", f"query={query}"], timeout=20)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("gh graphql failed: %s", exc)
        return None
    if result.returncode != 0:
        # gh exits non-zero on GraphQL errors but still returns JSON in stdout
        try:
            return json.loads(result.stdout)
        except (ValueError, json.JSONDecodeError):
            logger.warning("gh graphql exit %d: %s",
                           result.returncode, result.stderr.strip())
            return None
    try:
        return json.loads(result.stdout)
    except (ValueError, json.JSONDecodeError):
        return None


def _resolve_node_id(org: str, repo: str, issue_number: int) -> str:
    """Look up an issue's GraphQL node id (needed for Issue Type assign,
    project field updates, and addSubIssue). Returns '' on failure."""
    query = (
        f'{{ repository(owner: "{org}", name: "{repo}") '
        f'{{ issue(number: {issue_number}) {{ id }} }} }}'
    )
    data = _gh_graphql(query)
    if not data:
        return ""
    try:
        return (((data.get("data") or {}).get("repository") or {})
                .get("issue") or {}).get("id", "") or ""
    except (AttributeError, TypeError):
        return ""


def _assign_issue_type(node_id: str, type_id: str) -> bool:
    """Assign a native Issue Type to an issue. Returns True on success."""
    mutation = (
        f'mutation {{ updateIssueIssueType(input: '
        f'{{ issueId: "{node_id}", issueTypeId: "{type_id}" }}) '
        f'{{ issue {{ id }} }} }}'
    )
    data = _gh_graphql(mutation)
    if not data or data.get("errors"):
        return False
    return bool(((data.get("data") or {}).get("updateIssueIssueType") or {}).get("issue"))


def _add_to_project(org: str, project_num: int, issue_url: str) -> str:
    """``gh project item-add``. Returns the project item id (or '' on failure)."""
    try:
        result = _gh(["gh", "project", "item-add", str(project_num),
                      "--owner", org, "--url", issue_url, "--format", "json"])
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("gh project item-add failed: %s", exc)
        return ""
    if result.returncode != 0:
        return ""
    try:
        return (json.loads(result.stdout) or {}).get("id", "") or ""
    except (ValueError, json.JSONDecodeError):
        return ""


def _link_sub_issue(parent_node_id: str, child_node_id: str) -> "tuple[bool, str]":
    """Thin wrapper around _sub_issue_linker so callers get one entry point.
    Returns (ok, message) where 'already linked' counts as ok."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from _sub_issue_linker import link_sub_issue  # noqa: E402
    finally:
        sys.path.pop(0)
    return link_sub_issue(parent_node_id, child_node_id)


def edpa_id_for(item_type: str, issue_number: int) -> str:
    """Derive an EDPA id from item type + GH issue number.
    Example: edpa_id_for('Story', 42) → 'S-42'."""
    prefix = TYPE_PREFIX.get(item_type, item_type[0].upper())
    return f"{prefix}-{issue_number}"


def create_gh_issue(
    org: str,
    repo: str,
    *,
    item_type: str,
    raw_title: str,
    body: str,
    edpa_id: "str | None" = None,
    project_num: "int | None" = None,
    type_ids: "dict | None" = None,
    parent_node_id: "str | None" = None,
    assignee_login: "str | None" = None,
    extra_labels: "Iterable[str] | None" = None,
) -> dict:
    """Create one GH issue and run the standard EDPA post-create pipeline.

    Pipeline (in order):
      1. ``gh issue create`` — single call if ``edpa_id`` is known
         (title = ``"{edpa_id}: {raw_title}"``); otherwise raw title.
      2. resolve node_id via GraphQL.
      3. if ``edpa_id`` was not provided, derive it from item_type + issue
         number and ``gh issue edit --title`` to the canonical form.
      4. if ``type_ids[item_type]`` is set, assign the native Issue Type.
      5. if ``project_num`` is set, add the issue to the project.
      6. if ``parent_node_id`` is set, link as sub-issue of that parent.

    Hard failures (1, 3) raise ``RuntimeError`` so the caller can abort
    before writing local state. Soft failures (4, 5, 6) populate
    ``warnings`` and the caller decides how to surface them — matches the
    "best-effort post-create" pattern used by sync.py push.

    Returns:
        {
          "issue_number": int,
          "node_id": str,
          "project_item_id": str,  # "" if project_num was None or add failed
          "url": str,
          "edpa_id": str,          # passed-through or computed
          "warnings": list[str],
        }
    """
    repo_slug = f"{org}/{repo}"

    title_for_create = (
        f"{edpa_id}: {raw_title}" if edpa_id else raw_title
    )
    cmd = ["gh", "issue", "create",
           "--repo", repo_slug,
           "--title", title_for_create,
           "--body", body]
    if assignee_login:
        cmd += ["--assignee", assignee_login]
    for label in (extra_labels or []):
        cmd += ["--label", label]

    try:
        result = _gh(cmd)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"gh issue create failed: {exc}")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gh issue create failed")

    url = result.stdout.strip()
    try:
        issue_number = int(url.rstrip("/").split("/")[-1])
    except (ValueError, IndexError):
        raise RuntimeError(f"could not parse issue number from {url!r}")

    warnings: list[str] = []

    # 2. Resolve node_id (needed for Issue Type + sub-issue link).
    node_id = _resolve_node_id(org, repo, issue_number)
    if not node_id:
        warnings.append("could not resolve issue node_id (Issue Type and "
                        "sub-issue link will be skipped)")

    # 3. Title rewrite when we did not know the id at create time.
    if not edpa_id:
        edpa_id = edpa_id_for(item_type, issue_number)
        full_title = f"{edpa_id}: {raw_title}"
        try:
            edit = _gh(["gh", "issue", "edit", str(issue_number),
                        "--repo", repo_slug,
                        "--title", full_title])
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(
                f"created #{issue_number} but title rewrite failed: {exc}")
        if edit.returncode != 0:
            raise RuntimeError(
                f"created #{issue_number} but title rewrite failed: "
                f"{edit.stderr.strip()}")

    # 4. Assign Issue Type (best-effort).
    if type_ids and node_id:
        type_id = type_ids.get(item_type)
        if type_id:
            if not _assign_issue_type(node_id, type_id):
                warnings.append(f"Issue Type '{item_type}' not assigned")

    # 5. Add to project (best-effort).
    project_item_id = ""
    if project_num is not None:
        project_item_id = _add_to_project(org, project_num, url)
        if not project_item_id:
            warnings.append(f"could not add issue to project #{project_num}")

    # 6. Link as sub-issue (best-effort).
    if parent_node_id and node_id:
        ok, msg = _link_sub_issue(parent_node_id, node_id)
        if not ok:
            warnings.append(f"sub-issue link failed: {msg}")

    return {
        "issue_number": issue_number,
        "node_id": node_id,
        "project_item_id": project_item_id,
        "url": url,
        "edpa_id": edpa_id,
        "warnings": warnings,
    }
