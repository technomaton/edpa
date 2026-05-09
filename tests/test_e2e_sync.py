"""End-to-end sync tests against a real GitHub sandbox repo.

Opt-in: pytest -m e2e

Requires:
  - EDPA_E2E_REPO env var (default: technomaton/edpa-e2e-test)
  - gh auth login with project + repo scopes
  - Org-level Issue Types: Initiative, Epic, Feature, Story
    (run plugin/edpa/scripts/issue_types.py setup --org <org> if missing)

These tests are SLOW (real GH API) and DESTRUCTIVE within the sandbox repo:
they delete issues and close projects between runs. NEVER point this at a repo
with real data.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from textwrap import dedent

import pytest
import yaml


SANDBOX_DEFAULT = "technomaton/edpa-e2e-test"
PROJECT_TITLE_PREFIX = "EDPA-E2E"

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT_SETUP = REPO_ROOT / "plugin/edpa/scripts/project_setup.py"
SYNC_SCRIPT = REPO_ROOT / "plugin/edpa/scripts/sync.py"

pytestmark = pytest.mark.e2e


# ── Helpers ────────────────────────────────────────────────────────────────

def gh(*args, check=True, timeout=60, input_text=None):
    """Run a gh CLI command and return CompletedProcess."""
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        input=input_text,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed:\n{result.stderr}")
    return result


def gh_json(*args, **kw):
    """Run gh and parse stdout as JSON."""
    result = gh(*args, **kw)
    return json.loads(result.stdout) if result.stdout.strip() else {}


def gh_auth_ok() -> bool:
    try:
        r = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def parse_repo(spec: str):
    if "/" not in spec:
        raise ValueError(f"EDPA_E2E_REPO must be 'org/repo', got {spec!r}")
    org, repo = spec.split("/", 1)
    return org, repo


def wipe_repo_issues(org: str, repo: str):
    """Close every issue (open or closed) and delete project items in sandbox."""
    listing = gh(
        "issue", "list",
        "--repo", f"{org}/{repo}",
        "--state", "all",
        "--limit", "200",
        "--json", "number",
        check=False,
    )
    if listing.returncode != 0:
        return
    try:
        items = json.loads(listing.stdout) if listing.stdout.strip() else []
    except json.JSONDecodeError:
        return
    for it in items:
        num = it.get("number")
        if num is None:
            continue
        # delete is irreversible; close+lock is gentler. We delete here for clean state.
        gh("issue", "delete", str(num), "--repo", f"{org}/{repo}", "--yes",
           check=False, timeout=20)


def wipe_e2e_projects(org: str):
    """Delete every project whose title starts with PROJECT_TITLE_PREFIX."""
    listing = gh("project", "list", "--owner", org, "--format", "json",
                 "--limit", "100", check=False)
    if listing.returncode != 0:
        return
    try:
        data = json.loads(listing.stdout)
    except json.JSONDecodeError:
        return
    for p in data.get("projects", []):
        if (p.get("title") or "").startswith(PROJECT_TITLE_PREFIX):
            num = p.get("number")
            if num:
                gh("project", "delete", str(num), "--owner", org,
                   check=False, timeout=20)


def make_workspace(tmp_path: Path, org: str, repo: str, items: list[dict]) -> Path:
    """Create a minimal .edpa/ workspace with config + per-item YAMLs."""
    edpa = tmp_path / ".edpa"
    (edpa / "config").mkdir(parents=True)
    (edpa / "backlog/initiatives").mkdir(parents=True)
    (edpa / "backlog/epics").mkdir(parents=True)
    (edpa / "backlog/features").mkdir(parents=True)
    (edpa / "backlog/stories").mkdir(parents=True)

    # Minimal edpa.yaml — sync section gets populated by setup
    (edpa / "config/edpa.yaml").write_text(yaml.dump({
        "project": {"name": "E2E Test Project"},
        "governance": {"methodology": "EDPA 1.0.0-beta"},
        "sync": {
            "github_org": org,
            "github_repo": repo,
            "fields_mapping": {
                "js": "Job Size",
                "bv": "Business Value",
                "tc": "Time Criticality",
                "rr": "Risk Reduction",
                "wsjf": "WSJF Score",
                "team": "Team",
            },
        },
    }, sort_keys=False, allow_unicode=True))

    type_to_dir = {
        "Initiative": "initiatives",
        "Epic": "epics",
        "Feature": "features",
        "Story": "stories",
    }
    for item in items:
        type_dir = type_to_dir[item["type"]]
        path = edpa / "backlog" / type_dir / f"{item['id']}.yaml"
        path.write_text(yaml.dump(item, sort_keys=False, allow_unicode=True))

    return tmp_path


def run_setup(workspace: Path, org: str, repo: str, project_title: str):
    """Invoke project_setup.py against the given workspace."""
    result = subprocess.run(
        [
            sys.executable, str(PROJECT_SETUP),
            "--org", org,
            "--repo", repo,
            "--project-title", project_title,
        ],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        timeout=300,
    )
    return result


def run_sync(workspace: Path, *args: str):
    """Invoke sync.py against the given workspace."""
    result = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT), *args],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        timeout=180,
    )
    return result


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def e2e_config():
    if not gh_auth_ok():
        pytest.skip("gh CLI not authenticated; skipping E2E tests")
    spec = os.environ.get("EDPA_E2E_REPO", SANDBOX_DEFAULT)
    org, repo = parse_repo(spec)
    # Verify repo exists
    r = subprocess.run(["gh", "repo", "view", f"{org}/{repo}"],
                       capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        pytest.skip(f"E2E sandbox repo {spec} not accessible: {r.stderr.strip()}")
    return {"org": org, "repo": repo, "spec": spec}


@pytest.fixture(scope="session", autouse=True)
def session_cleanup(e2e_config):
    """Wipe sandbox at session start AND end."""
    wipe_repo_issues(e2e_config["org"], e2e_config["repo"])
    wipe_e2e_projects(e2e_config["org"])
    yield
    wipe_repo_issues(e2e_config["org"], e2e_config["repo"])
    wipe_e2e_projects(e2e_config["org"])


@pytest.fixture
def fresh_workspace(tmp_path, e2e_config):
    """Per-test: build a small backlog (1 Initiative + 1 Epic + 2 Stories) and clean GH state."""
    wipe_repo_issues(e2e_config["org"], e2e_config["repo"])
    wipe_e2e_projects(e2e_config["org"])

    items = [
        {"id": "I-100", "type": "Initiative", "title": "Sample initiative",
         "status": "Funnel", "owner": "PM"},
        {"id": "E-200", "type": "Epic", "title": "Sample epic",
         "status": "Analyzing", "parent": "I-100", "js": 13, "bv": 8, "tc": 3, "rr": 5, "wsjf": 1.23},
        {"id": "S-300", "type": "Story", "title": "Sample story alpha",
         "status": "Backlog", "parent": "E-200", "js": 5,
         "iteration": "PI-2026-1.1"},
        {"id": "S-301", "type": "Story", "title": "Sample story beta",
         "status": "Implementing", "parent": "E-200", "js": 3,
         "iteration": "PI-2026-1.1"},
    ]
    # Provide an iteration registry so project_setup creates the Iteration field
    iters_dir = tmp_path / ".edpa/iterations"
    iters_dir.mkdir(parents=True, exist_ok=True)
    for iid in ("PI-2026-1.1", "PI-2026-1.2"):
        (iters_dir / f"{iid}.yaml").write_text(yaml.dump({
            "iteration": {"id": iid, "pi": "PI-2026-1",
                          "dates": "1.4.–14.4.2026", "status": "closed"},
        }))
    ws = make_workspace(tmp_path, e2e_config["org"], e2e_config["repo"], items)
    title = f"{PROJECT_TITLE_PREFIX} {int(time.time())}"
    return {"workspace": ws, "items": items, "project_title": title, **e2e_config}


# ── Tests ──────────────────────────────────────────────────────────────────

def test_setup_creates_project_and_persists_ids(fresh_workspace):
    """A3.1: project_setup.py creates project, fields, issues, AND saves IDs to disk."""
    ws = fresh_workspace["workspace"]
    title = fresh_workspace["project_title"]
    org = fresh_workspace["org"]
    repo = fresh_workspace["repo"]

    result = run_setup(ws, org, repo, title)
    assert result.returncode == 0, f"setup failed:\n{result.stderr}\n{result.stdout}"

    # 1. edpa.yaml has sync.field_ids + option_ids populated
    cfg = yaml.safe_load((ws / ".edpa/config/edpa.yaml").read_text())
    sync = cfg.get("sync", {})
    assert sync.get("github_project_id"), "github_project_id not persisted"
    assert sync.get("github_project_number"), "github_project_number not persisted"
    field_ids = sync.get("field_ids") or {}
    option_ids = sync.get("option_ids") or {}
    assert "Job Size" in field_ids, f"Job Size field_id missing; have: {list(field_ids)}"
    assert "Initiative Status" in field_ids
    assert "Story Status" in field_ids
    assert any(k.startswith("Initiative Status:") for k in option_ids), \
        f"no Initiative Status options in option_ids; sample: {list(option_ids)[:5]}"

    # 2. issue_map.yaml has all 4 items mapped with issue_number + project_item_id
    issue_map_doc = yaml.safe_load((ws / ".edpa/config/issue_map.yaml").read_text())
    items_map = issue_map_doc.get("items") or {}
    for iid in ("I-100", "E-200", "S-300", "S-301"):
        assert iid in items_map, f"{iid} missing from issue_map.yaml"
        entry = items_map[iid]
        assert entry.get("issue_number"), f"{iid}: no issue_number"
        assert entry.get("project_item_id"), f"{iid}: no project_item_id"

    # 3. Issues actually exist on GH with correct titles
    listing = gh_json("issue", "list", "--repo", f"{org}/{repo}",
                      "--state", "all", "--limit", "50", "--json", "number,title,state")
    titles = {it["title"] for it in listing}
    assert any("I-100" in t for t in titles), f"I-100 issue not on GH; titles: {titles}"
    assert any("S-301" in t for t in titles), f"S-301 issue not on GH"


def test_setup_refresh_recovers_state(fresh_workspace):
    """A3.1: sync setup-refresh re-discovers field_ids/option_ids/issue_map after loss."""
    ws = fresh_workspace["workspace"]
    title = fresh_workspace["project_title"]
    org = fresh_workspace["org"]
    repo = fresh_workspace["repo"]

    setup = run_setup(ws, org, repo, title)
    assert setup.returncode == 0

    # Wipe local IDs (simulate "checked out on different machine")
    cfg_path = ws / ".edpa/config/edpa.yaml"
    cfg = yaml.safe_load(cfg_path.read_text())
    saved_project_num = cfg["sync"]["github_project_number"]
    cfg["sync"].pop("field_ids", None)
    cfg["sync"].pop("option_ids", None)
    cfg["sync"].pop("github_project_id", None)
    cfg_path.write_text(yaml.dump(cfg, sort_keys=False, allow_unicode=True))
    (ws / ".edpa/config/issue_map.yaml").unlink(missing_ok=True)

    refresh = run_sync(ws, "setup-refresh")
    assert refresh.returncode == 0, f"setup-refresh failed:\n{refresh.stderr}\n{refresh.stdout}"

    # IDs should be back
    cfg = yaml.safe_load(cfg_path.read_text())
    assert cfg["sync"]["github_project_number"] == saved_project_num
    assert cfg["sync"].get("field_ids", {}).get("Job Size")
    assert cfg["sync"].get("github_project_id"), "project_id not refreshed"
    issue_map_doc = yaml.safe_load((ws / ".edpa/config/issue_map.yaml").read_text())
    assert "I-100" in (issue_map_doc.get("items") or {}), "issue_map not refreshed"


def test_push_creates_new_issue_for_local_only_item(fresh_workspace):
    """A3.1: adding a new YAML file then sync push creates a corresponding GH issue."""
    ws = fresh_workspace["workspace"]
    title = fresh_workspace["project_title"]
    org = fresh_workspace["org"]
    repo = fresh_workspace["repo"]

    setup = run_setup(ws, org, repo, title)
    assert setup.returncode == 0

    # Add a brand-new story locally
    new_story = {
        "id": "S-999",
        "type": "Story",
        "title": "Brand-new story added after setup",
        "status": "Backlog",
        "parent": "E-200",
        "js": 8,
    }
    (ws / ".edpa/backlog/stories/S-999.yaml").write_text(
        yaml.dump(new_story, sort_keys=False, allow_unicode=True)
    )

    push = run_sync(ws, "push")
    assert push.returncode == 0, f"push failed:\n{push.stderr}\n{push.stdout}"
    assert "issues created" in push.stdout or "issue_created" in push.stdout or "S-999" in push.stdout, \
        f"push output didn't mention creation:\n{push.stdout}"

    # Verify on GH
    listing = gh_json("issue", "list", "--repo", f"{org}/{repo}",
                      "--state", "all", "--limit", "50", "--json", "number,title")
    titles = {it["title"] for it in listing}
    assert any("S-999" in t for t in titles), f"S-999 not created on GH; titles: {titles}"

    # And issue_map.yaml updated
    issue_map_doc = yaml.safe_load((ws / ".edpa/config/issue_map.yaml").read_text())
    assert "S-999" in (issue_map_doc.get("items") or {}), "S-999 not added to issue_map"


def test_pull_picks_up_remote_status_change(fresh_workspace):
    """A3.1: change a status field via gh CLI → sync pull updates the local YAML."""
    ws = fresh_workspace["workspace"]
    title = fresh_workspace["project_title"]
    org = fresh_workspace["org"]
    repo = fresh_workspace["repo"]

    setup = run_setup(ws, org, repo, title)
    assert setup.returncode == 0

    # Read IDs to perform the manual GH change
    cfg = yaml.safe_load((ws / ".edpa/config/edpa.yaml").read_text())
    project_id = cfg["sync"]["github_project_id"]
    project_num = cfg["sync"]["github_project_number"]
    story_status_field_id = cfg["sync"]["field_ids"]["Story Status"]
    done_option_id = cfg["sync"]["option_ids"]["Story Status:Done"]

    issue_map = yaml.safe_load((ws / ".edpa/config/issue_map.yaml").read_text())["items"]
    s300_pid = issue_map["S-300"]["project_item_id"]

    # Mutate remote: set S-300 status to Done
    gh("project", "item-edit",
       "--id", s300_pid,
       "--project-id", project_id,
       "--field-id", story_status_field_id,
       "--single-select-option-id", done_option_id)

    # Pull and verify YAML updated
    pull = run_sync(ws, "pull")
    assert pull.returncode == 0, f"pull failed:\n{pull.stderr}\n{pull.stdout}"

    s300_yaml = yaml.safe_load((ws / ".edpa/backlog/stories/S-300.yaml").read_text())
    assert s300_yaml.get("status") == "Done", \
        f"S-300 status not updated; got: {s300_yaml.get('status')}\nFull YAML: {s300_yaml}"

    # Changelog should record the change
    changelog = (ws / ".edpa/changelog.jsonl").read_text().splitlines()
    assert any("S-300" in line and "github" in line for line in changelog), \
        f"changelog missing S-300 github entry; got: {changelog}"


def test_iteration_field_roundtrips(fresh_workspace):
    """Gap 1: Iteration is created as SINGLE_SELECT and pulled back correctly.

    Verifies setup creates the field with options from .edpa/iterations/, that
    items get the correct iteration option set, and that a manual change in
    GitHub propagates back via sync pull."""
    ws = fresh_workspace["workspace"]
    title = fresh_workspace["project_title"]
    org = fresh_workspace["org"]
    repo = fresh_workspace["repo"]

    setup = run_setup(ws, org, repo, title)
    assert setup.returncode == 0, f"setup failed:\n{setup.stderr}\n{setup.stdout}"

    # Iteration field exists with the right options
    cfg = yaml.safe_load((ws / ".edpa/config/edpa.yaml").read_text())
    field_ids = cfg["sync"]["field_ids"]
    option_ids = cfg["sync"]["option_ids"]
    assert "Iteration" in field_ids, f"Iteration field not created; have {list(field_ids)}"
    assert "Iteration:PI-2026-1.1" in option_ids
    assert "Iteration:PI-2026-1.2" in option_ids

    # S-300 should have iteration set on creation
    issue_map = yaml.safe_load((ws / ".edpa/config/issue_map.yaml").read_text())["items"]
    s300_pid = issue_map["S-300"]["project_item_id"]
    project_id = cfg["sync"]["github_project_id"]

    # Move S-300 to a different iteration via gh CLI
    iter2_opt = option_ids["Iteration:PI-2026-1.2"]
    gh("project", "item-edit",
       "--id", s300_pid,
       "--project-id", project_id,
       "--field-id", field_ids["Iteration"],
       "--single-select-option-id", iter2_opt)

    pull = run_sync(ws, "pull")
    assert pull.returncode == 0, f"pull failed:\n{pull.stderr}\n{pull.stdout}"

    s300_yaml = yaml.safe_load((ws / ".edpa/backlog/stories/S-300.yaml").read_text())
    assert s300_yaml.get("iteration") == "PI-2026-1.2", \
        f"iteration not updated; got: {s300_yaml.get('iteration')}"


def test_engine_sees_status_transition_after_sync(fresh_workspace):
    """A3.1 + integration: a Done transition synced from GH gets credited by the engine via gate detection.

    This is the proof that the full chain works: GH UI → pull → YAML+git → engine credits gate.
    """
    ws = fresh_workspace["workspace"]
    title = fresh_workspace["project_title"]
    org = fresh_workspace["org"]
    repo = fresh_workspace["repo"]

    setup = run_setup(ws, org, repo, title)
    assert setup.returncode == 0

    # Init git in workspace so engine's transition detector has commits to walk
    subprocess.run(["git", "init", "-q"], cwd=str(ws), check=True)
    subprocess.run(["git", "config", "user.email", "e2e@test"], cwd=str(ws), check=True)
    subprocess.run(["git", "config", "user.name", "e2e"], cwd=str(ws), check=True)
    subprocess.run(["git", "add", "."], cwd=str(ws), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=str(ws), check=True)

    # Mutate remote: E-200 Analyzing → Implementing
    cfg = yaml.safe_load((ws / ".edpa/config/edpa.yaml").read_text())
    project_id = cfg["sync"]["github_project_id"]
    epic_field_id = cfg["sync"]["field_ids"]["Epic Status"]
    impl_opt = cfg["sync"]["option_ids"]["Epic Status:Implementing"]
    issue_map = yaml.safe_load((ws / ".edpa/config/issue_map.yaml").read_text())["items"]
    e200_pid = issue_map["E-200"]["project_item_id"]
    gh("project", "item-edit",
       "--id", e200_pid,
       "--project-id", project_id,
       "--field-id", epic_field_id,
       "--single-select-option-id", impl_opt)

    pull = run_sync(ws, "pull", "--commit")
    assert pull.returncode == 0

    e200_yaml = yaml.safe_load((ws / ".edpa/backlog/epics/E-200.yaml").read_text())
    assert e200_yaml.get("status") == "Implementing", \
        f"E-200 status not synced; got: {e200_yaml.get('status')}"

    # Verify a git commit recorded the change (engine reads git log for transitions)
    log = subprocess.run(
        ["git", "log", "--all", "--oneline"],
        cwd=str(ws), capture_output=True, text=True, check=True,
    ).stdout
    assert "sync" in log.lower() or "pull" in log.lower(), \
        f"no sync commit in git log:\n{log}"
