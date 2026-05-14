"""Tests for tools/migrate_backlog_yaml_to_md.py.

Covers the one-shot migration that converts legacy `.edpa/backlog/**/*.yaml`
items into `.md` with YAML frontmatter + Markdown body.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin/edpa/scripts"))
sys.path.insert(0, str(ROOT / "tools"))

# Load the migration script as a module — its filename has underscores so
# import works without tricks.
spec = importlib.util.spec_from_file_location(
    "migrate_backlog_yaml_to_md",
    ROOT / "tools" / "migrate_backlog_yaml_to_md.py",
)
mig = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mig)

from _md_frontmatter import load_md, parse_body_sections  # noqa: E402


def _seed_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
                    encoding="utf-8")


# ─── Basic conversion ───────────────────────────────────────────────────────


def test_migrate_simple_item(tmp_path):
    src = tmp_path / "backlog" / "stories" / "S-1.yaml"
    _seed_yaml(src, {
        "id": "S-1", "type": "Story", "title": "test",
        "status": "Done", "parent": "F-1", "js": 5,
    })
    changed, msg = mig.migrate_file(src)
    assert changed, msg
    assert not src.exists()
    dest = src.with_suffix(".md")
    assert dest.exists()
    data = load_md(dest)
    assert data["id"] == "S-1"
    assert data["title"] == "test"
    assert data["js"] == 5
    assert data["body"] == ""


def test_migrate_extracts_description_to_body(tmp_path):
    src = tmp_path / "backlog" / "risks" / "R-1.yaml"
    _seed_yaml(src, {
        "id": "R-1", "type": "Risk", "title": "test",
        "description": "If OMOP CDM releases v6, parser breaks.",
    })
    changed, _ = mig.migrate_file(src)
    assert changed
    data = load_md(src.with_suffix(".md"))
    # description leaves frontmatter…
    assert "description" not in {k for k in data if k != "body"}
    # …and lands in the body
    sections = parse_body_sections(data["body"])
    assert sections["description"] == "If OMOP CDM releases v6, parser breaks."


def test_migrate_acceptance_criteria_list(tmp_path):
    src = tmp_path / "backlog" / "stories" / "S-2.yaml"
    _seed_yaml(src, {
        "id": "S-2", "type": "Story", "title": "AC list",
        "acceptance_criteria": ["concept table loads", "FK validation"],
    })
    mig.migrate_file(src)
    data = load_md(src.with_suffix(".md"))
    sections = parse_body_sections(data["body"])
    assert sections["acceptance_criteria"] == [
        "concept table loads",
        "FK validation",
    ]
    # Body should render as Markdown checklist
    assert "- [ ] concept table loads" in data["body"]


def test_migrate_all_prose_fields_round_trip(tmp_path):
    src = tmp_path / "backlog" / "features" / "F-1.yaml"
    _seed_yaml(src, {
        "id": "F-1", "type": "Feature", "title": "rich prose",
        "description": "Big idea here.",
        "acceptance_criteria": "Must pass smoke test.",
        "refinement_notes": "Discussed in PI planning.",
        "notes": "See doc/x.md",
    })
    mig.migrate_file(src)
    data = load_md(src.with_suffix(".md"))
    # Frontmatter retains only non-prose fields
    fm = {k: v for k, v in data.items() if k != "body"}
    assert set(fm) == {"id", "type", "title"}
    # All prose sections present
    sections = parse_body_sections(data["body"])
    assert sections["description"] == "Big idea here."
    assert sections["acceptance_criteria"] == "Must pass smoke test."
    assert sections["refinement_notes"] == "Discussed in PI planning."
    assert sections["notes"] == "See doc/x.md"


def test_migrate_preserves_contributors_list(tmp_path):
    src = tmp_path / "backlog" / "stories" / "S-3.yaml"
    _seed_yaml(src, {
        "id": "S-3", "type": "Story", "title": "with contributors",
        "contributors": [
            {"person": "alice", "cw": 1, "as": "owner"},
            {"person": "bob", "cw": 0.6, "as": "key"},
        ],
    })
    mig.migrate_file(src)
    data = load_md(src.with_suffix(".md"))
    assert data["contributors"] == [
        {"person": "alice", "cw": 1, "as": "owner"},
        {"person": "bob", "cw": 0.6, "as": "key"},
    ]


# ─── Idempotency & safety ───────────────────────────────────────────────────


def test_migrate_skips_when_md_already_exists(tmp_path):
    src = tmp_path / "backlog" / "stories" / "S-1.yaml"
    dest = src.with_suffix(".md")
    _seed_yaml(src, {"id": "S-1", "type": "Story", "title": "yaml"})
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("---\nid: S-1\ntype: Story\ntitle: from-md\n---\n",
                    encoding="utf-8")

    changed, msg = mig.migrate_file(src)
    assert not changed
    assert "skip" in msg.lower()
    # both files survive — operator must resolve manually
    assert src.exists()
    # destination unchanged
    assert "from-md" in dest.read_text(encoding="utf-8")


def test_migrate_dry_run_does_not_write(tmp_path):
    src = tmp_path / "backlog" / "stories" / "S-1.yaml"
    _seed_yaml(src, {"id": "S-1", "type": "Story", "title": "test"})
    changed, msg = mig.migrate_file(src, dry_run=True)
    assert changed
    assert msg.startswith("DRY-RUN")
    # source still exists, no destination
    assert src.exists()
    assert not src.with_suffix(".md").exists()


def test_migrate_skips_non_yaml(tmp_path):
    src = tmp_path / "backlog" / "stories" / "S-1.txt"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("not yaml", encoding="utf-8")
    changed, msg = mig.migrate_file(src)
    assert not changed
    assert "not .yaml" in msg


def test_migrate_skips_non_mapping_yaml(tmp_path):
    src = tmp_path / "backlog" / "stories" / "weird.yaml"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("- just\n- a\n- list\n", encoding="utf-8")
    changed, msg = mig.migrate_file(src)
    assert not changed
    assert "not a YAML mapping" in msg


def test_migrate_handles_malformed_yaml(tmp_path):
    src = tmp_path / "backlog" / "stories" / "broken.yaml"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("key: : :: bad", encoding="utf-8")
    changed, msg = mig.migrate_file(src)
    assert not changed
    assert msg.startswith("ERROR")


# ─── Full-directory walk ────────────────────────────────────────────────────


def test_collect_targets_recursive(tmp_path):
    backlog = tmp_path / "backlog"
    _seed_yaml(backlog / "stories" / "S-1.yaml", {"id": "S-1", "type": "Story"})
    _seed_yaml(backlog / "epics" / "E-1.yaml", {"id": "E-1", "type": "Epic"})
    _seed_yaml(backlog / "features" / "F-1.yaml", {"id": "F-1", "type": "Feature"})
    # Non-yaml siblings should not be collected
    (backlog / "stories" / "S-1.md").write_text("---\nid: S-1\n---\n",
                                                  encoding="utf-8")
    (backlog / "stories" / "README.txt").write_text("note", encoding="utf-8")

    targets = mig.collect_targets([backlog])
    names = sorted(t.name for t in targets)
    assert names == ["E-1.yaml", "F-1.yaml", "S-1.yaml"]


def test_migrate_full_directory_idempotent(tmp_path):
    backlog = tmp_path / "backlog"
    _seed_yaml(backlog / "stories" / "S-1.yaml", {
        "id": "S-1", "type": "Story", "title": "a",
        "description": "first",
    })
    _seed_yaml(backlog / "stories" / "S-2.yaml", {
        "id": "S-2", "type": "Story", "title": "b",
    })

    # First pass: convert
    results = [mig.migrate_file(t) for t in mig.collect_targets([backlog])]
    assert all(changed for changed, _ in results)
    assert sorted(p.name for p in (backlog / "stories").iterdir()) == \
        ["S-1.md", "S-2.md"]

    # Second pass: no .yaml left → 0 targets, 0 changes
    second_targets = mig.collect_targets([backlog])
    assert second_targets == []


# ─── Body section formatting ────────────────────────────────────────────────


def test_migrated_body_has_section_headers(tmp_path):
    """The migration script must produce well-formed ## sections that
    parse_body_sections can recover."""
    src = tmp_path / "backlog" / "stories" / "S-1.yaml"
    _seed_yaml(src, {
        "id": "S-1", "type": "Story", "title": "rich",
        "description": "X\n\nY",
        "notes": "Some links",
    })
    mig.migrate_file(src)
    body = load_md(src.with_suffix(".md"))["body"]
    assert "## Description" in body
    assert "## Notes" in body
    # Round-trip preserves multi-paragraph description.
    sections = parse_body_sections(body)
    assert sections["description"] == "X\n\nY"
    assert sections["notes"] == "Some links"


def test_migrated_yaml_with_block_scalar(tmp_path):
    """The legacy block-scalar workaround (the bug v1.19.6 fix patched)
    must migrate cleanly — block scalars become plain Markdown."""
    src = tmp_path / "backlog" / "stories" / "S-1.yaml"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(textwrap.dedent("""\
        id: S-1
        type: Story
        title: with block scalar
        description: |
          Line 1
          Line 2

          Paragraph 2
    """), encoding="utf-8")
    mig.migrate_file(src)
    data = load_md(src.with_suffix(".md"))
    sections = parse_body_sections(data["body"])
    assert sections["description"].startswith("Line 1")
    assert "Paragraph 2" in sections["description"]
    # Frontmatter is now free of `description:`
    assert "description" not in {k for k in data if k != "body"}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
