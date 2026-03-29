#!/usr/bin/env python3
"""
EDPA Hook Tests — validates commit info generation, person resolution,
YAML validation, schema strictness, and engine integration.

Run: python -m pytest tests/test_hooks.py -v
"""

import json
import sys
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:
    pytest.skip("PyYAML not installed", allow_module_level=True)

ROOT = Path(__file__).resolve().parent.parent

# Add plugin scripts to path
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

from edpa_commit_info import (
    resolve_person,
    load_people,
    load_heuristics,
    find_backlog_item,
    compute_cw,
)
from validate_syntax import validate_yaml


# ---------------------------------------------------------------------------
# TestCommitInfoFallbacks
# ---------------------------------------------------------------------------


class TestCommitInfoFallbacks:
    """Test graceful degradation when EDPA config files are missing."""

    def test_missing_people_yaml(self, tmp_path):
        """No people.yaml -> person field should be null."""
        edpa = tmp_path / ".edpa" / "config"
        edpa.mkdir(parents=True)
        # No people.yaml created
        people = load_people(tmp_path / ".edpa")
        assert people == []
        person = resolve_person(people, email="test@example.com")
        assert person is None

    def test_missing_heuristics(self, tmp_path):
        """No heuristics file -> evidence field should be null."""
        edpa = tmp_path / ".edpa" / "config"
        edpa.mkdir(parents=True)
        heuristics = load_heuristics(tmp_path / ".edpa")
        assert heuristics is None

    def test_missing_backlog(self, tmp_path):
        """No .edpa/backlog/ -> item field should be null."""
        edpa = tmp_path / ".edpa"
        edpa.mkdir(parents=True)
        item = find_backlog_item(str(edpa), branch="feature/S-101")
        assert item is None

    def test_all_missing(self, tmp_path):
        """No .edpa/ at all -> only branch and diff populated."""
        fake_edpa = tmp_path / ".edpa"
        # Don't create it
        people = load_people(fake_edpa)
        assert people == []
        heuristics = load_heuristics(fake_edpa)
        assert heuristics is None
        item = find_backlog_item(str(fake_edpa), branch="main")
        assert item is None


# ---------------------------------------------------------------------------
# TestPersonResolution
# ---------------------------------------------------------------------------


class TestPersonResolution:
    """Test the resolve_person() function with mock people.yaml data."""

    PEOPLE = [
        {"id": "urbanek", "name": "J. Urbanek", "role": "Arch", "email": "jaroslav@example.com"},
        {"id": "tuma", "name": "O. Tuma", "role": "DevSecOps", "email": "tuma@example.com"},
        {"id": "bob", "name": "Bob Dev", "role": "Dev"},
    ]

    def test_match_by_email(self):
        """Person with email matching git config."""
        person = resolve_person(self.PEOPLE, email="jaroslav@example.com")
        assert person is not None
        assert person["id"] == "urbanek"

    def test_match_by_id(self):
        """Person with id matching email prefix."""
        person = resolve_person(self.PEOPLE, email="tuma@corp.com")
        assert person is not None
        assert person["id"] == "tuma"

    def test_match_by_name(self):
        """Person with id matching git name (case-insensitive)."""
        person = resolve_person(self.PEOPLE, name="Bob")
        assert person is not None
        assert person["id"] == "bob"

    def test_no_match(self):
        """Nobody matches -> returns None."""
        person = resolve_person(self.PEOPLE, email="unknown@nowhere.com", name="Nobody")
        assert person is None

    def test_empty_people(self):
        """People list is empty -> returns None."""
        person = resolve_person([], email="test@example.com", name="Test")
        assert person is None

    def test_email_with_empty_prefix(self):
        """Edge case: email like @domain.com should not crash."""
        person = resolve_person(self.PEOPLE, email="@domain.com")
        assert person is None


# ---------------------------------------------------------------------------
# TestValidateSyntaxEdgeCases
# ---------------------------------------------------------------------------


class TestValidateSyntaxEdgeCases:
    """Test YAML validation edge cases."""

    def test_binary_file(self, tmp_path):
        """Binary file with .yaml extension -> error."""
        binary_file = tmp_path / "bad.yaml"
        binary_file.write_bytes(b"\x00\x01\x02\xff\xfe\x80\x81")
        errors = validate_yaml(binary_file)
        assert len(errors) > 0
        assert "binary" in errors[0].lower() or "error" in errors[0].lower()

    def test_template_file(self):
        """Template file validated as YAML (check cw_heuristics.yaml.tmpl)."""
        tmpl_path = ROOT / "plugin" / "edpa" / "templates" / "cw_heuristics.yaml.tmpl"
        if not tmpl_path.exists():
            pytest.skip("cw_heuristics.yaml.tmpl not found")
        errors = validate_yaml(tmpl_path)
        assert errors == [], f"Template has YAML errors: {errors}"

    def test_deeply_nested_yaml(self, tmp_path):
        """Valid but complex YAML -> no errors."""
        complex_yaml = tmp_path / "deep.yaml"
        content = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": {
                            "items": [1, 2, 3],
                            "nested_list": [
                                {"a": 1, "b": {"c": [4, 5, 6]}},
                                {"d": {"e": {"f": "deep"}}},
                            ],
                        }
                    }
                }
            }
        }
        complex_yaml.write_text(yaml.dump(content))
        errors = validate_yaml(complex_yaml)
        assert errors == []

    def test_yaml_with_anchors(self, tmp_path):
        """YAML anchors/aliases -> no errors."""
        anchor_yaml = tmp_path / "anchors.yaml"
        anchor_yaml.write_text(
            "defaults: &defaults\n"
            "  role: Dev\n"
            "  fte: 1.0\n"
            "\n"
            "person1:\n"
            "  <<: *defaults\n"
            "  id: alice\n"
            "\n"
            "person2:\n"
            "  <<: *defaults\n"
            "  id: bob\n"
        )
        errors = validate_yaml(anchor_yaml)
        assert errors == []

    def test_file_not_found(self, tmp_path):
        """Non-existent file -> error (not crash)."""
        errors = validate_yaml(tmp_path / "nonexistent.yaml")
        assert len(errors) > 0
        assert "not found" in errors[0].lower()


# ---------------------------------------------------------------------------
# TestSchemaStrictness
# ---------------------------------------------------------------------------


class TestSchemaStrictness:
    """Test the edpa_commit_info.schema.json for strictness."""

    @pytest.fixture
    def schema(self):
        schema_path = ROOT / "plugin" / "edpa" / "schemas" / "edpa_commit_info.schema.json"
        if not schema_path.exists():
            pytest.skip("Schema file not found")
        return json.loads(schema_path.read_text())

    @pytest.fixture
    def validate(self, schema):
        jsonschema = pytest.importorskip("jsonschema")
        def _validate(instance):
            jsonschema.validate(instance, schema)
        return _validate

    def _valid_doc(self):
        return {
            "branch": "main",
            "diff": "some diff",
            "person": None,
            "evidence": None,
            "item": None,
        }

    def test_rejects_extra_top_level_fields(self, validate):
        """additionalProperties=false enforced."""
        jsonschema = pytest.importorskip("jsonschema")
        doc = self._valid_doc()
        doc["extra_field"] = "should fail"
        with pytest.raises(jsonschema.ValidationError):
            validate(doc)

    def test_rejects_invalid_role_enum(self, validate):
        """role 'Unknown' rejected."""
        jsonschema = pytest.importorskip("jsonschema")
        doc = self._valid_doc()
        doc["person"] = {"id": "test", "role": "Unknown"}
        with pytest.raises(jsonschema.ValidationError):
            validate(doc)

    def test_rejects_negative_cw(self, validate):
        """cw: -0.5 rejected via role_weights minimum constraint."""
        jsonschema = pytest.importorskip("jsonschema")
        doc = self._valid_doc()
        doc["evidence"] = {
            "role_weights": {
                "owner": -0.5,
                "key": 0.6,
                "reviewer": 0.25,
                "consulted": 0.15,
            }
        }
        with pytest.raises(jsonschema.ValidationError):
            validate(doc)

    def test_rejects_missing_diff(self, validate):
        """diff field required."""
        jsonschema = pytest.importorskip("jsonschema")
        doc = {"branch": "main"}
        with pytest.raises(jsonschema.ValidationError):
            validate(doc)

    def test_accepts_valid_doc(self, validate):
        """A valid document should pass."""
        validate(self._valid_doc())

    def test_accepts_null_person(self, validate):
        """Person can be null."""
        doc = self._valid_doc()
        doc["person"] = None
        validate(doc)


# ---------------------------------------------------------------------------
# TestEngineIntegration
# ---------------------------------------------------------------------------


class TestEngineIntegration:
    """Test engine integration from edpa_commit_info module."""

    def test_compute_cw_importable(self):
        """import compute_cw from edpa_commit_info module."""
        from edpa_commit_info import compute_cw as cw_func
        assert callable(cw_func)

    def test_compute_cw_with_role_override(self):
        """Arch reviewer = 0.30."""
        heuristics = {
            "role_weights": {"owner": 1.0, "key": 0.6, "reviewer": 0.25, "consulted": 0.15},
            "role_overrides": {
                "Arch": {"owner": 1.0, "key": 0.6, "reviewer": 0.30, "consulted": 0.15},
            },
        }
        evidence_entry = {
            "signals": ["pr_reviewer"],
            "evidence_score": 1.0,
            "manual_cw": None,
        }
        cw = compute_cw(evidence_entry, heuristics, person_role="Arch")
        assert abs(cw - 0.30) < 0.001

    def test_compute_cw_fallback(self):
        """Unknown role -> generic weights."""
        heuristics = {
            "role_weights": {"owner": 1.0, "key": 0.6, "reviewer": 0.25, "consulted": 0.15},
            "role_overrides": {
                "Arch": {"owner": 1.0, "key": 0.6, "reviewer": 0.30, "consulted": 0.15},
            },
        }
        evidence_entry = {
            "signals": ["pr_reviewer"],
            "evidence_score": 1.0,
            "manual_cw": None,
        }
        cw = compute_cw(evidence_entry, heuristics, person_role="UnknownRole")
        assert abs(cw - 0.25) < 0.001, f"Expected generic reviewer=0.25, got {cw}"
