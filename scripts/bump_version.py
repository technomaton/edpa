#!/usr/bin/env python3
"""Single-command version bump across the entire EDPA repo.

Sources of truth (after bump, both equal `new_version`):
  - plugin/.claude-plugin/plugin.json   (read by engine.py at runtime)
  - web/package.json                     (read by web/src/lib/version.ts)

Files that import from the sources of truth (no edit needed, automatic):
  - plugin/edpa/scripts/engine.py        (get_version() reads plugin.json)
  - web/src/pages/**/*.astro             (import { VERSION } from lib/version)
  - web/src/layouts/Layout.astro         (same)
  - web/src/components/{Header,Footer}.astro (same)

Files that contain the version literally and need manual update (this
script handles them):
  - plugin/edpa/templates/edpa.yaml.tmpl       (`methodology: "EDPA X.Y.Z-tag"`)
  - plugin/skills/edpa-reports/SKILL.md       (example output blocks)
  - plugin/skills/edpa-setup/SKILL.md         (example output blocks)
  - docs/methodology.md                       (header line "Version X.Y.Z-tag — Month Year")
  - README.md                                 (badge URL + demo block + version mentions)
  - CHANGELOG.md                              (existing entries are immutable; this script
                                                ONLY warns if the bump target is missing
                                                from CHANGELOG.md — does NOT add an entry)

Usage:
    python scripts/bump_version.py 1.2.0-beta            # dry-run
    python scripts/bump_version.py 1.2.0-beta --apply    # write changes
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CZECH_MONTHS = ["Leden", "Únor", "Březen", "Duben", "Květen", "Červen",
                "Červenec", "Srpen", "Září", "Říjen", "Listopad", "Prosinec"]
ENGLISH_MONTHS = ["January", "February", "March", "April", "May", "June",
                  "July", "August", "September", "October", "November", "December"]


def current_version_from_plugin() -> str:
    p = REPO_ROOT / "plugin/.claude-plugin/plugin.json"
    return json.loads(p.read_text())["version"]


def bump_json_field(path: Path, new_version: str, apply: bool) -> bool:
    text = path.read_text()
    new_text = re.sub(
        r'("version"\s*:\s*)"[^"]+"',
        rf'\1"{new_version}"',
        text,
        count=1,
    )
    if new_text != text and apply:
        path.write_text(new_text)
    return new_text != text


def bump_literal(path: Path, old: str, new: str, apply: bool) -> int:
    """Replace `old` with `new` in path. Returns number of replacements."""
    text = path.read_text()
    count = text.count(old)
    if count and apply:
        path.write_text(text.replace(old, new))
    return count


def bump_methodology_md(path: Path, new_version: str, apply: bool) -> bool:
    """Replace the `**Version X.Y.Z-tag — Month Year — Author**` header."""
    text = path.read_text()
    today = date.today()
    month_en = ENGLISH_MONTHS[today.month - 1]
    new_line = f"**Version {new_version} — {month_en} {today.year} — Jaroslav Urbanek, Lead Architect**"
    new_text = re.sub(
        r"\*\*Version [^\*]+ — \w+ \d{4} — Jaroslav Urbanek, Lead Architect\*\*",
        new_line,
        text,
        count=1,
    )
    if new_text != text and apply:
        path.write_text(new_text)
    return new_text != text


def bump_readme(path: Path, old: str, new: str, apply: bool) -> int:
    """Replace literal old version in README. Includes badge URL escaping."""
    text = path.read_text()
    # Badge URL uses `--` for `-`, e.g. 1.0.0--beta
    old_badge = old.replace("-", "--")
    new_badge = new.replace("-", "--")
    new_text = text.replace(old_badge, new_badge).replace(old, new)
    count = (text.count(old_badge) - new_text.count(old_badge)
             + text.count(old) - new_text.count(new))
    if new_text != text and apply:
        path.write_text(new_text)
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("new_version", help="e.g. 1.2.0-beta")
    parser.add_argument("--apply", action="store_true",
                        help="Write changes (default: dry-run)")
    args = parser.parse_args()

    if not re.match(r"^\d+\.\d+\.\d+(-[a-z]+(\.\d+)?)?$", args.new_version):
        print(f"ERROR: {args.new_version!r} is not a valid semver-ish "
              f"(expected like 1.2.0 or 1.2.0-beta)", file=sys.stderr)
        return 1

    old = current_version_from_plugin()
    new = args.new_version
    if old == new:
        print(f"Already at {new}. Nothing to do.")
        return 0

    print(f"Bumping {old} -> {new}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    print()

    # 1. JSON sources of truth
    plugin_json = REPO_ROOT / "plugin/.claude-plugin/plugin.json"
    web_pkg = REPO_ROOT / "web/package.json"
    print(f"  {'✓' if bump_json_field(plugin_json, new, args.apply) else '·'} plugin/.claude-plugin/plugin.json (version field)")
    print(f"  {'✓' if bump_json_field(web_pkg, new, args.apply) else '·'} web/package.json (version field)")

    # 2. Literal references
    targets = [
        REPO_ROOT / "plugin/edpa/templates/edpa.yaml.tmpl",
        REPO_ROOT / "plugin/skills/edpa-reports/SKILL.md",
        REPO_ROOT / "plugin/skills/edpa-setup/SKILL.md",
    ]
    for t in targets:
        n = bump_literal(t, old, new, args.apply)
        rel = t.relative_to(REPO_ROOT)
        print(f"  {'✓' if n else '·'} {rel}  ({n} replacement(s))")

    # 3. README — badge + body
    readme = REPO_ROOT / "README.md"
    n = bump_readme(readme, old, new, args.apply)
    print(f"  {'✓' if n else '·'} README.md  ({n} replacement(s) including badge)")

    # 4. docs/methodology.md — Version header line
    methodology = REPO_ROOT / "docs/methodology.md"
    print(f"  {'✓' if bump_methodology_md(methodology, new, args.apply) else '·'} docs/methodology.md (Version + month + year)")

    # 5. CHANGELOG.md — informational check only, never auto-edits
    changelog = REPO_ROOT / "CHANGELOG.md"
    if not args.apply:
        if new not in changelog.read_text():
            print(f"  ⚠ CHANGELOG.md does not yet mention {new} — add an entry by hand.")

    print()
    if args.apply:
        print("Done. Don't forget:")
        print("  1. Add a CHANGELOG.md entry for the new release")
        print("  2. cd web && vercel build --prod && vercel deploy --prebuilt --prod")
        print("  3. git commit + push")
    else:
        print("Dry-run. Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
