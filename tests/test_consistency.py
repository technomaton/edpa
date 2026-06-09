"""
EDPA Consistency Tests — catches version mismatches, hardcoded data,
stray files, and configuration drift.

Run: python -m pytest tests/test_consistency.py -v
"""
import json
import os
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
    # Source of truth — `plugin/.claude-plugin/plugin.json` in the repo.
    # Pre-v1.18.3 the `.claude/` symlink farm exposed this at
    # `.claude/.claude-plugin/plugin.json`; that symlink is gone now, and
    # the runtime copy after `/plugin install` lives in
    # `~/.claude/plugins/cache/edpa/.claude-plugin/plugin.json` (out of
    # repo). Read directly from the source-of-truth location.
    plugin = json.loads((ROOT / "plugin/.claude-plugin/plugin.json").read_text())
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

    # Legitimate occurrences of "technomaton" / "kashealth" in code that
    # are NOT hardcoded org assumptions but bot-commit / domain filters,
    # log-message namespacing, or other domain-of-this-project references
    # that legitimately ship with the engine.
    allowlist = {
        # yaml_edit_signals.py filters out bot commits from @noreply.<github-app>.com
        # patterns; the @noreply\.technomaton\.com regex is the bot for THIS repo's
        # own GH App, not a customer assumption. Adding/removing it would change
        # bot-commit handling, which is engine behaviour we want covered, but the
        # consistency rule doesn't apply to it. Match by "noreply" substring so
        # the regex's backslash-escaped dots don't disrupt the lookup.
        ("yaml_edit_signals.py", "noreply"),
    }

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

            # Allowlist match — line legitimately contains a forbidden token
            if any(token in raw_line for fname, token in allowlist if fname == py_file.name):
                continue

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
    # Layout changed in v1.18.3: commands flattened from
    # .claude/commands/edpa/X.md → .claude/commands/X.md so the Claude
    # Code plugin spec's auto-discovery (commands at plugin root, not in
    # a self-named sub-namespace) works under /plugin install via the
    # marketplace flow.
    # v1.19.5 dropped 5 wrapper commands (add/sync/setup/reports/
    # calibrate) that just invoked the same-named skill — they caused
    # duplicate /add + /edpa:add entries in the palette. Only commands
    # without a corresponding skill remain: close-iteration and board.
    required_commands = [
        "plugin/commands/close-iteration.md",
        "plugin/commands/board.md",
    ]

    missing = []
    for cmd_path in required_commands:
        full = ROOT / cmd_path
        if not full.exists():
            missing.append(cmd_path)

    assert not missing, "Missing command files:\n  " + "\n  ".join(missing)

    # plugin.json must reference these commands
    plugin = json.loads((ROOT / "plugin/.claude-plugin/plugin.json").read_text())
    commands = plugin.get("commands", [])
    command_basenames = {Path(c).name for c in commands}

    expected_basenames = {"close-iteration.md", "board.md"}
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
# 6. Role overrides — REMOVED in v1.11
# ---------------------------------------------------------------------------
#
# The role_overrides matrix (BO/PM/Arch reviewer = 0.30 etc.) was tied to
# the engine's compute_cw() function. v1.11 moved CW computation to
# detect_contributors.py, where it now uses additive signal aggregation
# instead of priority-based role lookup. Calibration of strategic role
# bias (PM/BO/Arch under-weighting) is handled by signal_weights that
# autocalib finds against ground truth — no role_overrides table needed.
#
# If per-role signal multipliers return in v1.12 (e.g., to address
# small-sample calibration issues for strategic roles), they will be
# tested in tests/test_detect_contributors.py at the aggregation layer.


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
        # v1.20.0+: items are .md (YAML frontmatter + Markdown body).
        # Reject stale .yaml files — they signal an incomplete migration.
        stale_yaml = list(path.glob("*.yaml"))
        if stale_yaml:
            errors.append(
                f"{name}/ still has {len(stale_yaml)} legacy .yaml file(s) — "
                f"run tools/migrate_backlog_yaml_to_md.py"
            )
        count = len(list(path.glob("*.md")))
        if count < 1:
            errors.append(f"{name}/ has no .md files (need >= 1)")
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
    """requirements.txt and requirements-dev.txt must exist and resolve to pyyaml.

    Accepts a literal `pyyaml` line OR an `-r requirements.txt` include that
    transitively pulls it in.
    """
    for fname in ("requirements.txt", "requirements-dev.txt"):
        path = ROOT / fname
        assert path.exists(), f"{fname} not found"
        content = path.read_text().lower()
        if "pyyaml" in content:
            continue
        # Accept transitive include: -r requirements.txt
        includes = [
            line.split(maxsplit=1)[1].strip()
            for line in content.splitlines()
            if line.strip().startswith("-r ")
        ]
        resolved = any(
            "pyyaml" in (ROOT / inc).read_text().lower()
            for inc in includes
            if (ROOT / inc).exists()
        )
        assert resolved, f"{fname} must contain 'pyyaml' directly or via -r include"


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
@pytest.mark.skipif(
    not (ROOT / "web" / "node_modules" / ".bin" / "astro").exists(),
    reason="web/node_modules not installed — run `npm ci` in web/",
)
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


# ---------------------------------------------------------------------------
# 13. Plugin hooks paths
# ---------------------------------------------------------------------------

def test_plugin_hooks_paths():
    """All paths referenced in hooks.json must exist."""
    hooks_path = ROOT / "plugin" / "hooks" / "hooks.json"
    if not hooks_path.exists():
        pytest.skip("hooks.json not found")
    hooks = json.loads(hooks_path.read_text())
    for event_hooks in hooks["hooks"].values():
        for matcher_group in event_hooks:
            for hook in matcher_group["hooks"]:
                cmd = hook["command"]
                resolved = cmd.replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT / "plugin"))
                assert Path(resolved).exists(), f"Hook script missing: {resolved}"


# ---------------------------------------------------------------------------
# 14. plugin.json hooks reference
# ---------------------------------------------------------------------------

def test_plugin_json_hooks_reference():
    """Claude Code auto-loads hooks/hooks.json — plugin.json must NOT reference it
    (causes duplicate-hooks error in CC v2.1.139+). If hooks field is present it
    must point to a *different* file."""
    pj = json.loads((ROOT / "plugin/.claude-plugin/plugin.json").read_text())
    hooks_ref = pj.get("hooks")
    standard = "./hooks/hooks.json"
    assert hooks_ref != standard, (
        "plugin.json must not reference hooks/hooks.json — CC loads it automatically"
    )
    if hooks_ref:
        hooks_path = ROOT / "plugin" / hooks_ref.lstrip("./")
        assert hooks_path.exists(), f"hooks file not found at {hooks_path}"


# ---------------------------------------------------------------------------
# 15. Hook scripts executable
# ---------------------------------------------------------------------------

def test_hook_scripts_executable():
    """Hook shell scripts must be executable."""
    hooks_dir = ROOT / "plugin" / "edpa" / "scripts" / "hooks"
    for sh in hooks_dir.glob("*.sh"):
        assert os.access(sh, os.X_OK), f"{sh.name} not executable"
    pre_commit = hooks_dir / "pre-commit"
    if pre_commit.exists():
        assert os.access(pre_commit, os.X_OK), "pre-commit not executable"
