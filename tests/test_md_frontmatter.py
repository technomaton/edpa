"""Tests for the `.md` + YAML-frontmatter backlog format helper."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin/edpa/scripts"))

from _md_frontmatter import (  # noqa: E402
    EDPA_TRAILER,
    format_body_sections,
    format_issue_body,
    load_md,
    parse_body_sections,
    save_md,
    save_md_item,
    strip_issue_body_chrome,
    update_frontmatter_field,
)


SAMPLE_FRONTMATTER = {
    "id": "S-200",
    "type": "Story",
    "title": "OMOP parser impl.",
    "js": 8,
    "bv": 8,
    "tc": 5,
    "rr_oe": 3,
    "status": "Done",
    "parent": "F-100",
    "assignee": "turyna",
    "iteration": "PI-2026-1.2",
    "iteration_half": 1,
    "contributors": [
        {"person": "turyna", "cw": 1, "as": "owner"},
        {"person": "tuma", "cw": 0.6, "as": "key"},
    ],
}

SAMPLE_BODY = (
    "## Description\n\n"
    "Parse OMOP CDM v5.4 vocabulary CSVs.\n\n"
    "## Acceptance Criteria\n\n"
    "- [ ] Concept table imports\n"
    "- [ ] Concept_relationship validates FKs\n"
    "- [x] Smoke test passes on demo data\n\n"
    "## Notes\n\n"
    "See: https://ohdsi.org\n"
)


class TestRoundTrip(unittest.TestCase):
    def test_load_save_roundtrip_preserves_frontmatter(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "S-200.md"
            save_md(p, SAMPLE_FRONTMATTER, SAMPLE_BODY)
            data = load_md(p)
            assert data is not None
            for k, v in SAMPLE_FRONTMATTER.items():
                self.assertEqual(data[k], v, f"field {k}")
            self.assertEqual(data["body"], SAMPLE_BODY)

    def test_save_md_item_splits_body_key(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "S-201.md"
            item = {**SAMPLE_FRONTMATTER, "body": SAMPLE_BODY}
            save_md_item(p, item)
            text = p.read_text(encoding="utf-8")
            # body key must not leak into frontmatter
            self.assertNotIn("body:", text.split("---", 2)[1])
            self.assertIn(SAMPLE_BODY.strip(), text)

    def test_empty_body(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "E-1.md"
            save_md(p, {"id": "E-1", "type": "Epic", "title": "x", "status": "Funnel"}, "")
            data = load_md(p)
            assert data is not None
            self.assertEqual(data["body"], "")
            self.assertEqual(data["id"], "E-1")

    def test_load_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(load_md(Path(d) / "nope.md"))

    def test_body_without_frontmatter(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "raw.md"
            p.write_text("# Just markdown\n\nNo frontmatter at all.\n", encoding="utf-8")
            data = load_md(p)
            assert data is not None
            self.assertEqual(data["body"], "# Just markdown\n\nNo frontmatter at all.\n")
            # No frontmatter keys other than body.
            self.assertEqual(set(data.keys()), {"body"})


class TestUpdateField(unittest.TestCase):
    def test_update_preserves_other_fields_and_body(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "S-200.md"
            save_md(p, SAMPLE_FRONTMATTER, SAMPLE_BODY)
            self.assertTrue(update_frontmatter_field(p, "status", "Implementing"))
            data = load_md(p)
            assert data is not None
            self.assertEqual(data["status"], "Implementing")
            self.assertEqual(data["id"], "S-200")
            self.assertEqual(data["contributors"][0]["person"], "turyna")
            self.assertEqual(data["body"], SAMPLE_BODY)

    def test_update_new_field(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "S-200.md"
            save_md(p, SAMPLE_FRONTMATTER, "")
            self.assertTrue(update_frontmatter_field(p, "wsjf", 4.2))
            data = load_md(p)
            assert data is not None
            self.assertEqual(data["wsjf"], 4.2)


class TestParseBody(unittest.TestCase):
    def test_parse_all_sections(self):
        out = parse_body_sections(SAMPLE_BODY)
        self.assertIn("description", out)
        self.assertIn("Parse OMOP", out["description"])
        self.assertEqual(
            out["acceptance_criteria"],
            ["Concept table imports", "Concept_relationship validates FKs",
             "Smoke test passes on demo data"],
        )
        self.assertIn("ohdsi.org", out["notes"])

    def test_ac_falls_back_to_string_when_not_checkboxes(self):
        body = "## Acceptance Criteria\n\nMust be approved by stakeholder.\n"
        out = parse_body_sections(body)
        self.assertEqual(out["acceptance_criteria"], "Must be approved by stakeholder.")

    def test_empty_body_returns_empty_dict(self):
        self.assertEqual(parse_body_sections(""), {})

    def test_ignores_unknown_headings(self):
        body = "## Random\n\nfoo\n\n## Description\n\nbar\n"
        out = parse_body_sections(body)
        self.assertEqual(out, {"description": "bar"})

    def test_stops_at_edpa_trailer(self):
        body = (
            "## Description\n\nThe real content.\n"
            "\n---\n_Managed by EDPA — edit fields in `.edpa/backlog/`._\n"
        )
        out = parse_body_sections(body)
        self.assertEqual(out["description"], "The real content.")


class TestFormatBody(unittest.TestCase):
    def test_format_round_trip_through_parse(self):
        item = {
            "description": "Parse OMOP CDM v5.4 vocabulary CSVs.",
            "acceptance_criteria": ["a", "b"],
            "notes": "See: https://ohdsi.org",
        }
        body = format_body_sections(item)
        parsed = parse_body_sections(body)
        self.assertEqual(parsed["description"], item["description"])
        self.assertEqual(parsed["acceptance_criteria"], item["acceptance_criteria"])
        self.assertEqual(parsed["notes"], item["notes"])

    def test_format_empty_when_no_prose(self):
        self.assertEqual(format_body_sections({"id": "S-1"}), "")


class TestIssueBody(unittest.TestCase):
    def test_format_issue_body_contains_meta_line(self):
        item = {**SAMPLE_FRONTMATTER, "body": SAMPLE_BODY}
        body = format_issue_body(item)
        self.assertTrue(body.startswith("Story · "))
        self.assertIn("JS=8", body)
        self.assertIn("owner=turyna", body)
        self.assertIn("iteration=PI-2026-1.2", body)
        self.assertIn("## Description", body)
        self.assertIn("_Managed by EDPA", body)

    def test_format_issue_body_empty_body(self):
        item = {"type": "Story", "js": 3, "body": ""}
        body = format_issue_body(item)
        self.assertIn("Story", body)
        self.assertIn("_Managed by EDPA", body)

    def test_strip_chrome_recovers_body(self):
        item = {**SAMPLE_FRONTMATTER, "body": SAMPLE_BODY}
        gh_body = format_issue_body(item)
        recovered = strip_issue_body_chrome(gh_body)
        self.assertNotIn("_Managed by EDPA", recovered)
        self.assertNotIn("JS=8", recovered)
        self.assertIn("## Description", recovered)
        self.assertIn("## Acceptance Criteria", recovered)

    def test_strip_chrome_user_edited(self):
        """User edits the GH issue body — meta line still gets stripped."""
        gh = (
            "Story · JS=5, owner=alice\n\n"
            "## Description\n\nUser added this.\n\n"
            "## Notes\n\nMore notes.\n"
            f"{EDPA_TRAILER}"
        )
        recovered = strip_issue_body_chrome(gh)
        self.assertIn("User added this", recovered)
        self.assertIn("## Notes", recovered)
        self.assertNotIn("JS=5", recovered)
        self.assertNotIn("_Managed by EDPA", recovered)


if __name__ == "__main__":
    unittest.main()
