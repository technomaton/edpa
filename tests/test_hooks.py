#!/usr/bin/env python3
"""
EDPA Hook Tests — validates commit info generation, person resolution,
YAML validation, schema strictness, and engine integration.

Run: python -m pytest tests/test_hooks.py -v
"""

import json
import os
import subprocess
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

    PEOPLE_WITH_GITHUB = [
        {"id": "urbanek", "name": "J. Urbanek", "role": "Arch",
         "email": "jaroslav@example.com", "github": "jurby"},
        {"id": "tuma", "name": "O. Tuma", "role": "DevSecOps",
         "email": "tuma@example.com", "github": "tuma-on-gh"},
    ]

    def test_match_by_github_noreply_email(self):
        """GitHub web edits send `<login>@users.noreply.github.com`."""
        person = resolve_person(self.PEOPLE_WITH_GITHUB,
                                email="jurby@users.noreply.github.com")
        assert person is not None
        assert person["id"] == "urbanek"

    def test_match_by_github_privacy_protected_noreply(self):
        """The `<id>+<login>@users.noreply.github.com` form must also match."""
        person = resolve_person(self.PEOPLE_WITH_GITHUB,
                                email="12345+jurby@users.noreply.github.com")
        assert person is not None
        assert person["id"] == "urbanek"

    def test_match_by_github_handle_in_name(self):
        """git user.name set to a github handle resolves through github field."""
        person = resolve_person(self.PEOPLE_WITH_GITHUB, name="tuma-on-gh")
        assert person is not None
        assert person["id"] == "tuma"

    def test_github_match_outranks_email_prefix(self):
        """GitHub login match wins over the id-equals-email-prefix fallback."""
        # email prefix "jaroslav" doesn't match anyone's id; github "jurby" does.
        person = resolve_person(self.PEOPLE_WITH_GITHUB,
                                email="jurby@users.noreply.github.com",
                                name="someone-else")
        assert person["id"] == "urbanek"


# ---------------------------------------------------------------------------
# TestValidateSyntaxEdgeCases
# ---------------------------------------------------------------------------


class TestValidateSyntaxEdgeCases:
    """Test YAML validation edge cases."""

    def test_binary_file(self, tmp_path):
        """Binary file with .yaml extension -> error."""
        binary_file = tmp_path / "bad.yaml"
        binary_file.write_bytes(b"\x00\x01\x02\xff\xfe\x80\x81")
        errors, _ = validate_yaml(binary_file)
        assert len(errors) > 0
        assert "binary" in errors[0].lower() or "error" in errors[0].lower()

    def test_template_file(self):
        """Template file validated as YAML (check cw_heuristics.yaml.tmpl)."""
        tmpl_path = ROOT / "plugin" / "edpa" / "templates" / "cw_heuristics.yaml.tmpl"
        if not tmpl_path.exists():
            pytest.skip("cw_heuristics.yaml.tmpl not found")
        errors, _ = validate_yaml(tmpl_path)
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
        errors, _ = validate_yaml(complex_yaml)
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
        errors, _ = validate_yaml(anchor_yaml)
        assert errors == []

    def test_file_not_found(self, tmp_path):
        """Non-existent file -> error (not crash)."""
        errors, _ = validate_yaml(tmp_path / "nonexistent.yaml")
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
            "schema": "edpa-commit-info/1.0",
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
        doc = {"schema": "edpa-commit-info/1.0", "branch": "main"}
        with pytest.raises(jsonschema.ValidationError):
            validate(doc)

    def test_rejects_wrong_schema_version(self, validate):
        """Wrong schema version rejected."""
        jsonschema = pytest.importorskip("jsonschema")
        doc = self._valid_doc()
        doc["schema"] = "wrong/2.0"
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


class TestCWPipelineV1_11:
    """v1.11: CW computation moved from engine to detect_contributors.

    The legacy `compute_cw(evidence_entry, heuristics, role)` function
    no longer exists. Engine reads `cw` directly from
    `contributors[].cw` (per-item-normalized share produced by
    detect_contributors.py). Role-based overrides were removed in v1.11.

    Direct CW unit tests now live in tests/test_detect_contributors.py
    (see TestAggregation block). Hooks-layer integration is covered by
    the rest of test_hooks.py (resolve_person, find_backlog_item, etc.).
    """

    def test_compute_cw_no_longer_re_exported(self):
        """edpa_commit_info no longer re-exports compute_cw."""
        from edpa_commit_info import resolve_person, find_backlog_item
        assert callable(resolve_person)
        assert callable(find_backlog_item)
        # compute_cw must NOT be importable — its absence is the v1.11 contract
        try:
            from edpa_commit_info import compute_cw  # noqa: F401
            raise AssertionError(
                "compute_cw was removed in v1.11; should not be importable"
            )
        except ImportError:
            pass  # expected


# ---------------------------------------------------------------------------
# PostToolUse hook gating (D-43) — shell-level tests
#
# hooks.json registers edpa_post_commit.sh on every Bash call and
# validate_on_save.sh on every Edit/Write, in EVERY project the plugin
# is enabled for. Both must gate on a .edpa/ directory (walk-up from
# cwd, same pattern as update_engine.sh) BEFORE spawning python3, so
# non-EDPA repos pay ~0 per tool call. A python3 PATH-shim spy proves
# no interpreter is spawned on the skip paths.
# ---------------------------------------------------------------------------

POST_COMMIT_HOOK = ROOT / "plugin" / "edpa" / "scripts" / "hooks" / "edpa_post_commit.sh"
VALIDATE_HOOK = ROOT / "plugin" / "edpa" / "scripts" / "hooks" / "validate_on_save.sh"


def _run_hook(hook, cwd, stdin, path_prepend=None):
    env = os.environ.copy()
    if path_prepend is not None:
        env["PATH"] = f"{path_prepend}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        ["sh", str(hook)],
        input=stdin, cwd=str(cwd), env=env,
        capture_output=True, text=True, timeout=30, encoding="utf-8",
    )


def _python3_spy(tmp_path):
    """PATH dir whose python3 shim records every invocation in a marker."""
    bindir = tmp_path / "spybin"
    bindir.mkdir()
    marker = tmp_path / "python3_invoked"
    shim = bindir / "python3"
    shim.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 0\n", encoding="utf-8")
    shim.chmod(0o755)
    return bindir, marker


class TestPostCommitHookGating:
    """edpa_post_commit.sh: .edpa gate + raw 'git commit' pre-filter."""

    @staticmethod
    def _stdin(command):
        return json.dumps({"tool_input": {"command": command}})

    def test_non_edpa_cwd_exits_silently_without_python(self, tmp_path):
        bindir, marker = _python3_spy(tmp_path)
        proj = tmp_path / "proj"
        proj.mkdir()
        r = _run_hook(POST_COMMIT_HOOK, proj,
                      self._stdin("git commit -m 'feat(S-1): x'"),
                      path_prepend=bindir)
        assert r.returncode == 0
        assert r.stdout == ""
        assert r.stderr == ""
        assert not marker.exists(), "python3 spawned in a non-EDPA repo"

    def test_non_commit_bash_skips_before_python(self, tmp_path):
        bindir, marker = _python3_spy(tmp_path)
        proj = tmp_path / "proj"
        (proj / ".edpa").mkdir(parents=True)
        r = _run_hook(POST_COMMIT_HOOK, proj, self._stdin("ls -la"),
                      path_prepend=bindir)
        assert r.returncode == 0
        assert r.stdout == ""
        assert r.stderr == ""
        assert not marker.exists(), "python3 spawned for a non-commit command"

    def test_git_commit_in_edpa_project_reaches_python(self, tmp_path):
        # Gate + pre-filter passed -> the authoritative python3 JSON
        # parse runs (the spy prints nothing, so the hook then exits 0).
        bindir, marker = _python3_spy(tmp_path)
        proj = tmp_path / "proj"
        (proj / ".edpa").mkdir(parents=True)
        r = _run_hook(POST_COMMIT_HOOK, proj,
                      self._stdin("git commit -m 'feat(S-1): x'"),
                      path_prepend=bindir)
        assert r.returncode == 0
        assert marker.exists(), "gate wrongly blocked a git commit in an EDPA repo"


class TestValidateOnSaveGating:
    """validate_on_save.sh: .edpa gates (cwd + file dir) and extension pre-filter."""

    @staticmethod
    def _stdin(path):
        return json.dumps({"tool_input": {"file_path": str(path)}})

    def test_non_edpa_cwd_exits_silently_without_python(self, tmp_path):
        bindir, marker = _python3_spy(tmp_path)
        proj = tmp_path / "proj"
        proj.mkdir()
        bad = proj / "bad.yaml"
        bad.write_text("key: [unclosed\n", encoding="utf-8")
        r = _run_hook(VALIDATE_HOOK, proj, self._stdin(bad), path_prepend=bindir)
        assert r.returncode == 0
        assert r.stdout == ""
        assert r.stderr == ""
        assert not marker.exists(), "python3 spawned in a non-EDPA repo"

    def test_unsupported_extension_skips_before_python(self, tmp_path):
        bindir, marker = _python3_spy(tmp_path)
        proj = tmp_path / "proj"
        (proj / ".edpa").mkdir(parents=True)
        f = proj / "main.go"
        f.write_text("package main\n", encoding="utf-8")
        r = _run_hook(VALIDATE_HOOK, proj, self._stdin(f), path_prepend=bindir)
        assert r.returncode == 0
        assert r.stdout == ""
        assert r.stderr == ""
        assert not marker.exists(), "python3 spawned for an unsupported extension"

    def test_valid_file_in_edpa_project_produces_no_stderr(self, tmp_path):
        # Regression: the hook used to iterate validate_file's
        # (errors, warnings) TUPLE, printing 'EDPA: validation error: []'
        # twice for perfectly valid files.
        proj = tmp_path / "proj"
        (proj / ".edpa").mkdir(parents=True)
        good = proj / "good.yaml"
        good.write_text("key: value\n", encoding="utf-8")
        r = _run_hook(VALIDATE_HOOK, proj, self._stdin(good))
        assert r.returncode == 0
        assert r.stderr == ""

    def test_invalid_yaml_in_edpa_project_reports_error(self, tmp_path):
        proj = tmp_path / "proj"
        (proj / ".edpa").mkdir(parents=True)
        bad = proj / "bad.yaml"
        bad.write_text("key: [unclosed\n", encoding="utf-8")
        r = _run_hook(VALIDATE_HOOK, proj, self._stdin(bad))
        assert r.returncode == 0, "hook must stay fail-open even on errors"
        assert "EDPA: validation error" in r.stderr

    def test_file_outside_edpa_project_not_validated(self, tmp_path):
        # cwd is an EDPA project, but the edited file lives elsewhere —
        # unrelated projects' files must not get EDPA-validated.
        proj = tmp_path / "proj"
        (proj / ".edpa").mkdir(parents=True)
        outside = tmp_path / "other"
        outside.mkdir()
        bad = outside / "bad.yaml"
        bad.write_text("key: [unclosed\n", encoding="utf-8")
        r = _run_hook(VALIDATE_HOOK, proj, self._stdin(bad))
        assert r.returncode == 0
        assert r.stderr == ""
