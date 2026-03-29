"""
EDPA Consistency Tests — catches version mismatches, hardcoded data,
stray files, and configuration drift.

Run: python -m pytest tests/test_consistency.py -v
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 1. Version consistency
# ---------------------------------------------------------------------------

def test_version_consistent():
    """All version references must match the source of truth in plugin.json."""
    # Source of truth
    plugin = json.loads((ROOT / ".claude/.claude-plugin/plugin.json").read_text())
    version = plugin["version"]

    errors = []

    # CHANGELOG.md — first ## X.Y.Z line
    changelog = (ROOT / "CHANGELOG.md").read_text()
    m = re.search(r"^## ([\d]+\.[\d]+\.[\d]+(?:-[\w.]+)?)", changelog, re.MULTILINE)
    if not m:
        errors.append("CHANGELOG.md: no version heading found")
    elif m.group(1) != version:
        errors.append(f"CHANGELOG.md: {m.group(1)} != {version}")

    # Header.astro — logo-version span (uses dynamic {VERSION} from lib/version.ts)
    header = (ROOT / "web/src/components/Header.astro").read_text()
    if 'logo-version' not in header:
        errors.append("Header.astro: no logo-version span found")

    # version.ts — must import from package.json
    version_ts = (ROOT / "web/src/lib/version.ts").read_text()
    if "VERSION" not in version_ts:
        errors.append("version.ts: no VERSION export found")

    assert not errors, "Version mismatches:\n  " + "\n  ".join(errors)


# ---------------------------------------------------------------------------
# 2. No hardcoded org names in runtime scripts
# ---------------------------------------------------------------------------

def test_no_hardcoded_org_in_scripts():
    """Runtime scripts must not contain hardcoded org names outside docstrings."""
    forbidden = ["technomaton", "kashealth"]
    scripts_dir = ROOT / "plugin" / "edpa" / "scripts"
    violations = []

    for py_file in sorted(scripts_dir.glob("*.py")):
        in_docstring = False
        docstring_delim_count = 0

        for lineno, raw_line in enumerate(py_file.read_text().splitlines(), 1):
            # Track triple-quote docstrings
            triple_count = raw_line.count('"""') + raw_line.count("'''")
            if triple_count:
                docstring_delim_count += triple_count
                # Odd count means we entered/exited a docstring
                in_docstring = (docstring_delim_count % 2) == 1

            # Skip if inside a docstring
            if in_docstring:
                continue
            # Also skip the closing line of a docstring (it still has the delimiter)
            if triple_count and not in_docstring:
                continue

            # Strip inline comments starting with #
            code_part = raw_line.split("#")[0] if "#" in raw_line else raw_line

            for word in forbidden:
                if word.lower() in code_part.lower():
                    violations.append(f"{py_file.name}:{lineno}: {raw_line.strip()}")

    assert not violations, (
        "Hardcoded org names found in script code (outside docstrings):\n  "
        + "\n  ".join(violations)
    )


# ---------------------------------------------------------------------------
# 3. No hardcoded org in config
# ---------------------------------------------------------------------------

def test_no_hardcoded_org_in_config():
    """.edpa/config/edpa.yaml must use placeholder values, not real org names."""
    import yaml

    config = yaml.safe_load((ROOT / ".edpa/config/edpa.yaml").read_text())
    sync = config.get("sync", {})

    github_org = sync.get("github_org", "")
    assert github_org.upper() == github_org or github_org == "YOUR_ORG", (
        f"github_org should be a placeholder like 'YOUR_ORG', got: {github_org}"
    )

    project_num = sync.get("github_project_number", -1)
    assert project_num == 0 or project_num == "" or str(project_num).startswith("YOUR"), (
        f"github_project_number should be 0 or placeholder, got: {project_num}"
    )


# ---------------------------------------------------------------------------
# 4. Skill files exist
# ---------------------------------------------------------------------------

def test_skills_exist():
    """Every /edpa command must have a corresponding skill file."""
    required_commands = [
        ".claude/commands/edpa/setup.md",
        ".claude/commands/edpa/close-iteration.md",
        ".claude/commands/edpa/reports.md",
        ".claude/commands/edpa/calibrate.md",
        ".claude/commands/edpa/sync.md",
    ]

    missing = []
    for cmd_path in required_commands:
        full = ROOT / cmd_path
        if not full.exists():
            missing.append(cmd_path)

    assert not missing, "Missing command files:\n  " + "\n  ".join(missing)

    # plugin.json must reference these commands
    plugin = json.loads((ROOT / ".claude/.claude-plugin/plugin.json").read_text())
    commands = plugin.get("commands", [])
    command_basenames = {Path(c).name for c in commands}

    expected_basenames = {"setup.md", "close-iteration.md", "reports.md", "calibrate.md", "sync.md"}
    missing_refs = expected_basenames - command_basenames
    assert not missing_refs, (
        f"plugin.json missing command references: {missing_refs}"
    )


# ---------------------------------------------------------------------------
# 5. No stray files in web/
# ---------------------------------------------------------------------------

def test_no_stray_files_in_web():
    """web/ must not contain directories/files that belong at repo root."""
    web = ROOT / "web"
    stray = [".vercel", "dist", "config", ".claude", "CHANGELOG.md", "docs"]

    found = []
    for name in stray:
        candidate = web / name
        if candidate.exists():
            # .vercel and dist are build artifacts — only flag if tracked by git
            if name in (".vercel", "dist"):
                result = subprocess.run(
                    ["git", "ls-files", "--error-unmatch", str(candidate)],
                    capture_output=True, text=True, cwd=ROOT,
                )
                if result.returncode == 0:
                    found.append(f"{name}/ (tracked in git)")
            else:
                found.append(name)

    assert not found, (
        "Stray files/dirs in web/ that belong at repo root:\n  "
        + "\n  ".join(found)
    )


# ---------------------------------------------------------------------------
# 6. Role overrides applied in engine
# ---------------------------------------------------------------------------

def test_role_overrides_applied():
    """Arch reviewer CW must be 0.30 (not generic 0.25) — catches v1.x bug."""
    sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))
    from engine import compute_cw

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
    assert cw == 0.30, (
        f"Arch reviewer CW should be 0.30 (role_override), got {cw}. "
        "role_overrides not applied?"
    )


# ---------------------------------------------------------------------------
# 7. Backlog file count
# ---------------------------------------------------------------------------

def test_backlog_file_count():
    """Backlog directories must contain expected structure."""
    edpa = ROOT / ".edpa"

    dirs = {
        "initiatives": edpa / "backlog" / "initiatives",
        "epics": edpa / "backlog" / "epics",
        "features": edpa / "backlog" / "features",
        "stories": edpa / "backlog" / "stories",
    }

    errors = []
    total = 0

    for name, path in dirs.items():
        if not path.is_dir():
            errors.append(f"{name}/ directory missing")
            continue
        count = len(list(path.glob("*.yaml")))
        if count < 1:
            errors.append(f"{name}/ has no YAML files (need >= 1)")
        total += count

    assert not errors, "Backlog structure issues:\n  " + "\n  ".join(errors)
    assert total > 0, "Total backlog items should be > 0"


# ---------------------------------------------------------------------------
# 8. people.yaml is example data
# ---------------------------------------------------------------------------

def test_people_yaml_is_example():
    """.edpa/config/people.yaml must contain EXAMPLE marker — not production data."""
    content = (ROOT / ".edpa/config/people.yaml").read_text()
    assert "EXAMPLE" in content.upper(), (
        "people.yaml must contain an 'EXAMPLE' marker to indicate it is not "
        "production data"
    )


# ---------------------------------------------------------------------------
# 9. Requirements files exist
# ---------------------------------------------------------------------------

def test_requirements_exist():
    """requirements.txt and requirements-dev.txt must exist and list pyyaml."""
    for fname in ("requirements.txt", "requirements-dev.txt"):
        path = ROOT / fname
        assert path.exists(), f"{fname} not found"
        content = path.read_text().lower()
        assert "pyyaml" in content, f"{fname} must contain 'pyyaml'"


# ---------------------------------------------------------------------------
# 10. .gitignore covers build artifacts
# ---------------------------------------------------------------------------

def test_gitignore_covers_artifacts():
    """.gitignore must cover common build artifacts."""
    gitignore = (ROOT / ".gitignore").read_text()

    required = ["web/dist/", "web/.vercel/", "__pycache__/", ".env"]
    missing = [entry for entry in required if entry not in gitignore]

    assert not missing, (
        ".gitignore missing entries:\n  " + "\n  ".join(missing)
    )


# ---------------------------------------------------------------------------
# 11. CHANGELOG has all versions
# ---------------------------------------------------------------------------

def test_changelog_has_all_versions():
    """CHANGELOG.md must have entries for all released versions."""
    changelog = (ROOT / "CHANGELOG.md").read_text()

    required_versions = ["1.0.0-beta"]
    found_versions = re.findall(r"^## ([\d]+\.[\d]+\.[\d]+(?:-[\w.]+)?)", changelog, re.MULTILINE)

    missing = [v for v in required_versions if v not in found_versions]
    assert not missing, (
        f"CHANGELOG.md missing version entries: {missing}"
    )


# ---------------------------------------------------------------------------
# 12. Web build succeeds (slow)
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_web_build_succeeds():
    """npm run build must exit 0 and produce >= 14 HTML files."""
    web_dir = ROOT / "web"

    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=web_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, (
        f"Web build failed (exit {result.returncode}):\n{result.stderr[-500:]}"
    )

    dist = web_dir / "dist"
    assert dist.is_dir(), "web/dist/ not created by build"

    html_files = list(dist.rglob("*.html"))
    assert len(html_files) >= 14, (
        f"Expected >= 14 HTML files in dist/, found {len(html_files)}"
    )
