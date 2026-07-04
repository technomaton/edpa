#!/usr/bin/env python3
"""
CI-suite tests for board.py — the self-contained HTML Kanban generator (S-246).

board.py is user-facing (wired into /edpa:board via plugin/commands/board.md)
but its only coverage used to live in the opt-in e2e_v2_full harness
(phases/12_verify_backlog.py), which needs real GitHub access and never runs
in CI. These tests exercise the script via subprocess against a minimal
planted `.edpa/` tree so a regression no longer ships silently.

Contract notes (verified against board.py):
  * board.py has NO --edpa-root flag — it discovers the project root by
    walking up from Path.cwd() looking for .edpa/config/people.yaml, so every
    invocation here sets cwd to the planted project dir.
  * --open is never passed (it would launch a browser).
  * One `data-id="<ID>"` attribute is rendered per card — the same assertion
    vocabulary as tests/e2e_v2_full/phases/12_verify_backlog.py.

The planted project + the unfiltered render are module-scoped (subprocess
spawns are the dominant cost); every run writes to its own --output file, and
no test mutates the shared tree, so tests stay order-independent.

Run: python -m pytest tests/test_board.py -v
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BOARD = ROOT / "plugin" / "edpa" / "scripts" / "board.py"

PEOPLE_YAML = """\
project:
  name: Widget Co
people:
  - id: alice
    name: Alice Dev
    role: Dev
  - id: bob
    name: Bob Arch
    role: Arch
    github: bob-gh
"""

# Six items across four levels covering all three board columns, plus the
# fallback column mapping (portfolio status "Implementing" has no column of
# its own and lands in Planned).
BACKLOG_FILES = {
    "epics/E-1.md": (
        "---\n"
        "id: E-1\n"
        "type: Epic\n"
        "title: Payments epic\n"
        "status: Implementing\n"
        "---\n"
    ),
    "features/F-1.md": (
        "---\n"
        "id: F-1\n"
        "type: Feature\n"
        "title: Checkout flow\n"
        "parent: E-1\n"
        "status: In Progress\n"
        "js: 8\n"
        "bv: 8\n"
        "tc: 5\n"
        "rr_oe: 3\n"
        "wsjf: 2.0\n"
        "iteration: PI-2026-1.1\n"
        "assignee: alice\n"
        "---\n"
    ),
    "stories/S-1.md": (
        "---\n"
        "id: S-1\n"
        "type: Story\n"
        'title: "Escape <b>me</b> & friends"\n'
        "parent: F-1\n"
        "status: Planned\n"
        "js: 5\n"
        "wsjf: 7.5\n"
        "iteration: PI-2026-1.1\n"
        "assignee: alice\n"
        "---\n"
    ),
    "stories/S-2.md": (
        "---\n"
        "id: S-2\n"
        "type: Story\n"
        "title: Second story\n"
        "parent: F-1\n"
        "status: In Progress\n"
        "js: 3\n"
        "iteration: PI-2026-1.2\n"
        "assignee: bob\n"
        "---\n"
    ),
    "stories/S-3.md": (
        "---\n"
        "id: S-3\n"
        "type: Story\n"
        "title: Done story\n"
        "parent: F-1\n"
        "status: Done\n"
        "js: 2\n"
        "iteration: PI-2026-2.1\n"
        "---\n"
    ),
    "defects/D-1.md": (
        "---\n"
        "id: D-1\n"
        "type: Defect\n"
        "title: Fix crash\n"
        "status: Done\n"
        "iteration: PI-2026-1.1\n"
        "---\n"
    ),
}

ALL_IDS = ("E-1", "F-1", "S-1", "S-2", "S-3", "D-1")


def _plant_config(root):
    config = root / ".edpa" / "config"
    config.mkdir(parents=True)
    (config / "people.yaml").write_text(PEOPLE_YAML, encoding="utf-8")


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    """Minimal .edpa/ tree board.py can discover by walking up from cwd."""
    root = tmp_path_factory.mktemp("board-project")
    _plant_config(root)
    for rel, text in BACKLOG_FILES.items():
        item = root / ".edpa" / "backlog" / rel
        item.parent.mkdir(parents=True, exist_ok=True)
        item.write_text(text, encoding="utf-8")
    return root


def _run_board(cwd, *args):
    return subprocess.run(
        [sys.executable, str(BOARD), *args],
        cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )


def _generate(project, *args, name="board.html"):
    """Run board.py --output <project>/<name> [args]; return (proc, html)."""
    out = project / name
    proc = _run_board(project, "--output", str(out), *args)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert out.is_file()
    return proc, out.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def full_board(project):
    """One unfiltered render shared by the read-only content tests."""
    return _generate(project)


def _card_count(html_text):
    """Same card-count vocabulary as e2e phase 12: one data-id per card."""
    return len(re.findall(r'data-id="', html_text))


def test_board_renders_one_card_per_item(project, full_board):
    proc, html_text = full_board
    assert "Board written to" in proc.stdout
    assert "(6 items loaded)" in proc.stdout
    assert _card_count(html_text) == len(ALL_IDS)
    for item_id in ALL_IDS:
        assert html_text.count(f'data-id="{item_id}"') == 1, item_id
    # project name from people.yaml lands in the <title>
    assert "<title>EDPA Board — Widget Co</title>" in html_text
    for col in ("Planned", "In Progress", "Done"):
        assert f'<span class="column__title">{col}</span>' in html_text
    # footer shows the rendered (post-filter) count
    assert "<span>6 items</span>" in html_text
    # e2e phase 12 size floor for a self-contained snapshot
    assert (project / "board.html").stat().st_size > 1024


def test_board_column_placement_and_wsjf_order(full_board):
    _, html_text = full_board
    # fixture is balanced: 2 cards per column (E-1 "Implementing" → Planned)
    assert html_text.count('<span class="column__count">2</span>') == 3
    # Done cards carry the dimming modifier class
    assert html_text.count('class="card card--done"') == 2
    # within a column, cards sort by WSJF descending:
    # Planned: S-1 (7.5) before E-1 (unset → 0)
    assert html_text.index('data-id="S-1"') < html_text.index('data-id="E-1"')
    # In Progress: F-1 (2.0) before S-2 (unset → 0)
    assert html_text.index('data-id="F-1"') < html_text.index('data-id="S-2"')


def test_board_escapes_html_in_titles(full_board):
    _, html_text = full_board
    assert "Escape &lt;b&gt;me&lt;/b&gt; &amp; friends" in html_text
    assert "<b>me</b>" not in html_text


def test_board_card_metadata(full_board):
    _, html_text = full_board
    # GitHub avatar <img> for people with a github: login
    assert "https://github.com/bob-gh.png?size=40" in html_text
    # colored-initials fallback for people without one
    assert '<div class="card__avatar" title="Alice Dev">AD</div>' in html_text
    # parent breadcrumb resolves against the full (unfiltered) item index
    assert '<span class="card__parent">F-1 Checkout flow</span>' in html_text
    # WSJF dots + JS badge
    assert 'title="BV: 8"' in html_text
    assert '<span class="card__js" title="Job Size">5</span>' in html_text


def test_board_iteration_filter(project):
    proc, html_text = _generate(
        project, "--iteration", "PI-2026-1", name="board-iter.html")
    assert _card_count(html_text) == 4
    for item_id in ("F-1", "S-1", "S-2", "D-1"):
        assert f'data-id="{item_id}"' in html_text, item_id
    # S-3 is PI-2026-2.1 and E-1 has no iteration — both filtered out
    assert 'data-id="S-3"' not in html_text
    assert 'data-id="E-1"' not in html_text
    assert "<span>4 items</span>" in html_text
    # the dropdown offers only iterations present in the filtered set
    assert '<option value="PI-2026-2.1"' not in html_text
    # stdout reports the pre-filter load count
    assert "(6 items loaded)" in proc.stdout


def test_board_level_filter_story(project):
    _, html_text = _generate(project, "--level", "story", name="board-story.html")
    assert _card_count(html_text) == 3
    for item_id in ("S-1", "S-2", "S-3"):
        assert f'data-id="{item_id}"' in html_text, item_id
    for item_id in ("E-1", "F-1", "D-1"):
        assert f'data-id="{item_id}"' not in html_text, item_id


def test_board_level_filter_feature(project):
    _, html_text = _generate(project, "--level", "feature", name="board-feature.html")
    assert _card_count(html_text) == 1
    assert 'data-id="F-1"' in html_text


def test_board_default_output_path(project):
    proc = _run_board(project)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    out = project / ".edpa" / "board.html"
    assert out.is_file()
    assert 'data-id="S-1"' in out.read_text(encoding="utf-8")


def test_board_level_help_matches_reality(project):
    """D-68: the --level help claimed "(default: story)" but no default is set,
    so a no-arg board renders ALL levels (locked by
    test_board_renders_one_card_per_item). The help text must describe that
    reality rather than a default the code does not apply."""
    proc = _run_board(project, "--help")
    assert proc.returncode == 0
    # argparse wraps help across lines — collapse whitespace before matching
    help_text = " ".join(proc.stdout.split())
    assert "(default: all levels)" in help_text
    assert "(default: story)" not in help_text


# D-75: risks are part of a SAFe program board, but their lifecycle is the
# ROAM disposition (roam_status), not the Planned/In Progress/Done delivery
# status the columns model. board.py renders them in a dedicated "Risks (ROAM)"
# section and keeps them out of the status columns.
RISK_BACKLOG_FILES = {
    "stories/S-9.md": (
        "---\n"
        "id: S-9\n"
        "type: Story\n"
        "title: Lone story\n"
        "status: Planned\n"
        "js: 3\n"
        "iteration: PI-2026-1.1\n"
        "assignee: alice\n"
        "---\n"
    ),
    "risks/R-1.md": (
        "---\n"
        "id: R-1\n"
        "type: Risk\n"
        "title: Broker migration risk\n"
        "status: Funnel\n"        # incidental portfolio status, NOT a column
        "roam_status: owned\n"
        "severity: high\n"
        "assignee: bob\n"
        "---\n"
    ),
    "risks/R-2.md": (
        "---\n"
        "id: R-2\n"
        "type: Risk\n"
        "title: Rate limit risk\n"
        "status: Implementing\n"
        "roam_status: mitigated\n"
        "severity: medium\n"
        "---\n"
    ),
}


@pytest.fixture(scope="module")
def risk_project(tmp_path_factory):
    """Project with one delivery story plus two risks."""
    root = tmp_path_factory.mktemp("board-risk-project")
    _plant_config(root)
    for rel, text in RISK_BACKLOG_FILES.items():
        item = root / ".edpa" / "backlog" / rel
        item.parent.mkdir(parents=True, exist_ok=True)
        item.write_text(text, encoding="utf-8")
    return root


def test_board_renders_risks_in_roam_section(risk_project):
    proc, html_text = _generate(risk_project, name="board-risk.html")
    # loaded count reports risks separately from delivery items
    assert "1 items, 2 risks loaded" in proc.stdout
    # dedicated ROAM section is present (title span, not the CSS comment)
    assert '<div class="risk-panel">' in html_text
    assert '<span class="risk-panel__title">Risks (ROAM)</span>' in html_text
    # Slice out the rendered panel (body-only; excludes the <head> CSS where the
    # same class/attr names also appear) and assert against that.
    panel = html_text[html_text.index('<div class="risk-panel__list">'):
                      html_text.index('<div class="footer">')]
    # both risks render exactly once, tagged as Risk cards
    assert panel.count('data-id="R-1"') == 1
    assert panel.count('data-id="R-2"') == 1
    assert panel.count('data-type="Risk"') == 2
    # each risk surfaces its ROAM disposition + severity
    assert "roam--owned" in panel
    assert "roam--mitigated" in panel
    assert "risk-sev--high" in panel
    assert "risk-sev--medium" in panel
    # human-readable ROAM labels
    assert "Owned" in panel
    assert "Mitigated" in panel
    # risks must NOT leak into the delivery-status columns: their lifecycle is
    # ROAM, not Planned/In Progress/Done. Assert structurally by slicing out the
    # columns block (everything before the risk panel).
    cols = html_text[html_text.index('<div class="columns">'):
                     html_text.index('<div class="risk-panel">')]
    assert 'data-id="R-1"' not in cols
    assert 'data-id="R-2"' not in cols
    # the sole delivery item still lives in a status column
    assert 'data-id="S-9"' in cols
    # Risk is offered as a type-filter option so risks can be isolated
    assert '<option value="Risk">Risk</option>' in html_text


def test_board_risk_section_hidden_under_level_filter(risk_project):
    # A --level drill-down is a delivery-level focus; program-level risks are
    # omitted so the view stays scoped to the requested level.
    _, html_text = _generate(
        risk_project, "--level", "story", name="board-risk-story.html")
    # no rendered panel (the CSS comment still mentions "Risks (ROAM)", so key
    # off the structural marker, not the bare string)
    assert '<div class="risk-panel">' not in html_text
    assert 'data-id="R-1"' not in html_text
    assert 'data-id="R-2"' not in html_text
    assert 'data-id="S-9"' in html_text


def test_board_empty_backlog_fails(tmp_path):
    _plant_config(tmp_path)
    proc = _run_board(tmp_path)
    assert proc.returncode == 1
    assert "No backlog items found" in proc.stdout


def test_board_outside_project_fails(tmp_path):
    proc = _run_board(tmp_path)
    assert proc.returncode == 1
    assert "cannot find .edpa" in proc.stdout
