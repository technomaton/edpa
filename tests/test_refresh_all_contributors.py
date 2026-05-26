"""Tests for V2.1 Krok C7.6 — detect_contributors.cmd_all_items().

Refreshes contributors[] for EVERY item with evidence (not just
Stories), so gate events on Feature/Epic/Initiative see fresh
contributors[] instead of the stale LBC-time snapshot.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import detect_contributors as dc  # noqa: E402
from _md_frontmatter import load_md, save_md_item  # noqa: E402


# ─── Fixtures ─────────────────────────────────────────────────────────────


def _plant(edpa_root: Path, type_dir: str, item: dict) -> Path:
    p = edpa_root / "backlog" / type_dir / f"{item['id']}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    save_md_item(p, item)
    return p


@pytest.fixture
def edpa_root(tmp_path: Path) -> Path:
    root = tmp_path / ".edpa"
    (root / "config").mkdir(parents=True)
    for d in ("initiatives", "epics", "features", "stories", "defects",
              "events", "risks"):
        (root / "backlog" / d).mkdir(parents=True)
    (root / "config" / "people.yaml").write_text(yaml.safe_dump({
        "people": [
            {"id": "alice", "name": "A", "role": "Dev",
             "github": "alice-bot"},
            {"id": "bob", "name": "B", "role": "Arch",
             "github": "bob-bot"},
        ],
    }))
    (root / "config" / "edpa.yaml").write_text(yaml.safe_dump({
        "project": {"name": "T"},
    }))
    return root


_EV = {
    "type": "commit_author", "person": "alice-bot",
    "weight": 2.78, "ref": "commit/abc1234",
    "at": "2026-05-26T12:00:00Z",
}


# ─── Basic refresh ─────────────────────────────────────────────────────────


def test_refreshes_feature_with_evidence(edpa_root: Path, capsys) -> None:
    """Feature with evidence[] gets contributors[] regenerated."""
    _plant(edpa_root, "features", {
        "id": "F-1", "type": "Feature", "title": "x", "js": 10,
        "contributors": [{"person": "alice", "cw": 1.0,
                          "contribution_score": 3.4, "signals": []}],
        "evidence": [_EV, {**_EV, "person": "bob-bot",
                           "ref": "commit/def5678"}],
    })
    dc.cmd_all_items(edpa_root)

    data = load_md(edpa_root / "backlog" / "features" / "F-1.md")
    contribs = data["contributors"]
    persons = {c["person"] for c in contribs}
    assert persons == {"alice", "bob"}, (
        f"expected both alice + bob in refreshed contributors, got {persons}"
    )

    out = capsys.readouterr().out
    assert "refreshed" in out.lower()


def test_refreshes_all_types_not_just_stories(edpa_root: Path) -> None:
    """Stories, Features, Epics, Initiatives, Defects all get refresh."""
    for type_dir, item_id in [
        ("initiatives", "I-1"), ("epics", "E-1"), ("features", "F-1"),
        ("stories", "S-1"), ("defects", "D-1"),
    ]:
        _plant(edpa_root, type_dir, {
            "id": item_id, "type": type_dir[:-1].capitalize(),
            "title": "x", "js": 5,
            "contributors": [],
            "evidence": [_EV],
        })

    dc.cmd_all_items(edpa_root)

    for type_dir, item_id in [
        ("initiatives", "I-1"), ("epics", "E-1"), ("features", "F-1"),
        ("stories", "S-1"), ("defects", "D-1"),
    ]:
        data = load_md(edpa_root / "backlog" / type_dir / f"{item_id}.md")
        assert data.get("contributors"), (
            f"{item_id}: contributors[] not refreshed"
        )
        assert data["contributors"][0]["person"] == "alice"


def test_skips_items_without_evidence(edpa_root: Path) -> None:
    """Item with no evidence[] → contributors[] left untouched."""
    _plant(edpa_root, "features", {
        "id": "F-1", "type": "Feature", "title": "x", "js": 5,
        "contributors": [{"person": "alice", "cw": 1.0,
                          "contribution_score": 1.0, "signals": []}],
    })
    dc.cmd_all_items(edpa_root)
    data = load_md(edpa_root / "backlog" / "features" / "F-1.md")
    # alice still solo (process_item is no-op when 0 signals)
    assert len(data["contributors"]) == 1
    assert data["contributors"][0]["person"] == "alice"


def test_dry_run_does_not_write(edpa_root: Path) -> None:
    _plant(edpa_root, "features", {
        "id": "F-1", "type": "Feature", "title": "x", "js": 10,
        "contributors": [{"person": "alice", "cw": 1.0,
                          "contribution_score": 3.4, "signals": []}],
        "evidence": [{**_EV, "person": "bob-bot",
                      "ref": "commit/abc1234"}],
    })
    dc.cmd_all_items(edpa_root, dry_run=True)
    data = load_md(edpa_root / "backlog" / "features" / "F-1.md")
    # bob NOT in contributors despite being in evidence (dry-run)
    persons = {c["person"] for c in data["contributors"]}
    assert persons == {"alice"}, f"dry-run leaked write: {persons}"


def test_handles_empty_backlog(edpa_root: Path, capsys) -> None:
    """No items at all → success, scanned 0."""
    rc = dc.cmd_all_items(edpa_root)
    assert rc == 0
    out = capsys.readouterr().out
    assert "scanned 0 total" in out or "scanned 0" in out


# ─── The real bug this fix addresses ──────────────────────────────────────


def test_feature_credit_no_longer_stagnant_at_lbc_author(
    edpa_root: Path,
) -> None:
    """The user's pain point reproduced + fixed.

    Setup: Alice writes LBC for F-7. Bob later does transitions + work.
    contributors[] originally set to {alice: 1.0}. evidence[] grows
    as Bob commits.

    Before C7.6: gate events would inherit {alice: 1.0} forever.
    After C7.6: cmd_all_items refreshes contributors[] from evidence[]
    so Bob ends up in the block too.
    """
    bob_commits = [
        {"type": "commit_author", "person": "bob-bot",
         "weight": 2.78, "ref": f"commit/abc{i}",
         "at": "2026-05-26T12:00:00Z"}
        for i in range(5)
    ]
    _plant(edpa_root, "features", {
        "id": "F-7", "type": "Feature", "title": "Login system", "js": 20,
        "contributors": [
            {"person": "alice", "cw": 1.0,
             "contribution_score": 3.4, "signals": []},
        ],
        "evidence": [
            {"type": "commit_author", "person": "alice-bot",
             "weight": 3.4, "ref": "commit/lbc0001",
             "at": "2026-05-01T10:00:00Z"},
            *bob_commits,
        ],
    })

    dc.cmd_all_items(edpa_root)

    data = load_md(edpa_root / "backlog" / "features" / "F-7.md")
    contribs = data["contributors"]
    by_person = {c["person"]: c["cw"] for c in contribs}
    assert "alice" in by_person
    assert "bob" in by_person
    # Bob committed more → larger share
    assert by_person["bob"] > by_person["alice"], (
        f"Bob did more work but Alice still dominates: {by_person}"
    )
    assert abs(sum(by_person.values()) - 1.0) < 0.01, (
        "cw must normalize to 1.0"
    )
