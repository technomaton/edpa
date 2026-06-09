#!/usr/bin/env python3
"""
EDPA Syntax Validator — validates YAML, JSON, Python, and (for files under
.edpa/backlog/) backlog item schema.

Used by:
  - Git pre-commit hook (file list from hook script)
  - Claude Code PostToolUse hook (single file via wrapper)
  - CLI validation (directory or file list, "-" / /dev/stdin reads from stdin)

Checks:
  - YAML: syntax + .tmpl files
  - JSON: syntax
  - Python: syntax (ast.parse)
  - Binary detection (UnicodeDecodeError)
  - Backlog item schema: required fields, status enum per type,
    contributors[].as / cw shape (.edpa/backlog/{initiatives,epics,features,stories,defects}/*.yaml)
"""

try:  # best-effort UTF-8 stdio on legacy Windows consoles (cp1250)
    import _console  # noqa: F401
except ImportError:
    pass
import ast
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from _md_frontmatter import load_md as _load_md  # noqa: E402
finally:
    sys.path.pop(0)

YAML_EXTENSIONS = {".yaml", ".yml", ".tmpl"}
MARKDOWN_EXTENSIONS = {".md"}
JSON_EXTENSIONS = {".json"}
PYTHON_EXTENSIONS = {".py"}

# Prose fields that belong in the Markdown body, NOT in frontmatter.
BACKLOG_BODY_FIELDS = {"description", "acceptance_criteria",
                       "refinement_notes", "notes"}

# ─────────────────────────────────────────────────────────────────────
# Backlog schema (kept in sync with templates/cw_heuristics.yaml.tmpl,
# project_setup.py field options, and engine.EVIDENCE_ROLES)
# ─────────────────────────────────────────────────────────────────────
PORTFOLIO_STATUSES = {
    "Funnel", "Reviewing", "Analyzing", "Ready", "Implementing", "Done",
}
DELIVERY_STATUSES = {
    "Funnel", "Analyzing", "Backlog", "Implementing", "Validating",
    "Deploying", "Releasing", "Done",
}
# Non-blocking statuses that legacy backlogs may carry. We accept them
# silently for the validator (no error) but they won't round-trip
# through GitHub Projects because the typed Status fields don't list
# them. Setup docs flag this.
LEGACY_STATUSES = {"Active", "Closed", "Accepted"}

ROAM_STATUSES = {"resolved", "owned", "accepted", "mitigated"}

ITEM_SCHEMA = {
    "Initiative": {
        "dir": "initiatives",
        "required": {"id", "type", "title", "status"},
        "optional": {"parent", "js", "owner", "assignee", "contributors", "iteration",
                     "created_at", "closed_at", "updated_at"},
        "statuses": PORTFOLIO_STATUSES | LEGACY_STATUSES,
        "parent_required": False,
    },
    "Epic": {
        "dir": "epics",
        "required": {"id", "type", "title", "parent", "status"},
        "optional": {"js", "owner", "assignee", "contributors", "iteration",
                     "depends_on", "created_at", "closed_at", "updated_at"},
        "statuses": PORTFOLIO_STATUSES | LEGACY_STATUSES,
        "parent_required": True,
    },
    "Feature": {
        "dir": "features",
        "required": {"id", "type", "title", "parent", "status", "js"},
        "optional": {"owner", "assignee", "contributors", "iteration",
                     "bv", "tc", "rr_oe", "wsjf", "depends_on",
                     "created_at", "closed_at", "updated_at"},
        "statuses": DELIVERY_STATUSES | LEGACY_STATUSES,
        "parent_required": True,
    },
    "Story": {
        "dir": "stories",
        "required": {"id", "type", "title", "parent", "status", "js", "iteration"},
        "optional": {"owner", "assignee", "contributors",
                     "bv", "tc", "rr_oe", "wsjf", "depends_on",
                     "created_at", "closed_at", "updated_at"},
        "statuses": DELIVERY_STATUSES | LEGACY_STATUSES,
        "parent_required": True,
    },
    "Defect": {
        "dir": "defects",
        "required": {"id", "type", "title", "status", "js"},
        "optional": {"parent", "owner", "assignee", "contributors", "iteration",
                     "depends_on", "created_at", "closed_at", "updated_at"},
        "statuses": DELIVERY_STATUSES | LEGACY_STATUSES,
        "parent_required": False,
    },
    "Task": {
        "dir": "tasks",
        "required": {"id", "type", "title", "status"},
        "optional": {"parent", "js", "owner", "assignee", "contributors", "iteration",
                     "created_at", "closed_at", "updated_at"},
        "statuses": DELIVERY_STATUSES | LEGACY_STATUSES,
        "parent_required": False,
    },
    "Risk": {
        "dir": "risks",
        # A risk's lifecycle is its ROAM classification (roam_status), not the
        # delivery workflow — so `status` is optional here (validated against the
        # delivery set only when present).
        "required": {"id", "type", "title"},
        "optional": {"parent", "js", "owner", "assignee", "contributors", "iteration",
                     "status", "roam_status", "severity", "depends_on",
                     "created_at", "closed_at", "updated_at"},
        "statuses": DELIVERY_STATUSES | LEGACY_STATUSES,
        "parent_required": False,
    },
    "Event": {
        "dir": "events",
        "required": {"id", "type", "title", "status"},
        "optional": {"parent", "js", "owner", "assignee", "contributors", "iteration",
                     "depends_on", "created_at", "closed_at", "updated_at"},
        "statuses": DELIVERY_STATUSES | LEGACY_STATUSES,
        "parent_required": False,
    },
}

# Mirror engine.EVIDENCE_ROLES — kept here so the validator stays
# self-contained and doesn't import the full engine module just to
# check a contributor entry.
EVIDENCE_ROLES = {"owner", "key", "reviewer", "consulted"}

# Type → expected `id` prefix (matches naming.item_prefixes default).
TYPE_PREFIXES = {
    "Initiative": "I",
    "Epic": "E",
    "Feature": "F",
    "Story": "S",
    "Defect": "D",
    "Task": "T",
    "Risk": "R",
    "Event": "EV",
}


def _is_iteration_path(path: Path) -> bool:
    """True if path lives under .edpa/iterations/<file>.yaml."""
    parts = path.parts
    if ".edpa" not in parts:
        return False
    try:
        idx = parts.index(".edpa")
    except ValueError:
        return False
    return (idx + 1 < len(parts)
            and parts[idx + 1] == "iterations"
            and path.suffix in YAML_EXTENSIONS)


def _people_ids_for_iteration(path: Path) -> set[str] | None:
    """Find the .edpa/config/people.yaml that sits next to this iteration
    file and return the set of person ids declared there. Returns None
    when people.yaml is missing or unreadable — caller treats that as
    "skip person id cross-check" rather than fail validation."""
    parts = path.parts
    try:
        idx = parts.index(".edpa")
    except ValueError:
        return None
    edpa_dir = Path(*parts[: idx + 1]) if path.is_absolute() else Path(*parts[: idx + 1])
    if path.is_absolute():
        edpa_dir = Path("/" + str(edpa_dir)) if not str(edpa_dir).startswith("/") else edpa_dir
    people_path = edpa_dir / "config" / "people.yaml"
    if not people_path.is_file():
        return None
    try:
        data = yaml.safe_load(people_path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return None
    return {p.get("id") for p in (data.get("people") or []) if isinstance(p, dict) and p.get("id")}


def validate_iteration_people_overrides(path: Path, data, *, strict=False):
    """Validate top-level `people:` block in an iteration YAML.

    The iteration-level `people:` reuses the people.yaml schema as a
    partial override — only fields explicitly set affect the engine.
    Hard errors surface typos that change behaviour (unknown id, no
    matching field touched, negative capacity); soft warnings flag
    entries that compute but smell wrong.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return errors, warnings
    entries = data.get("people")
    if entries is None:
        return errors, warnings
    if not isinstance(entries, list):
        errors.append(
            f"{path}: iteration.people must be a list "
            f"(got {type(entries).__name__})"
        )
        return errors, warnings

    valid_person_ids = _people_ids_for_iteration(path)
    seen_ids: set[str] = set()
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(
                f"{path}: iteration.people[{idx}] must be a mapping "
                f"(got {type(entry).__name__})"
            )
            continue
        pid = entry.get("id")
        if not pid:
            errors.append(f"{path}: iteration.people[{idx}] missing 'id'")
            continue
        if pid in seen_ids:
            errors.append(
                f"{path}: iteration.people[{idx}] duplicates earlier entry "
                f"for id={pid!r} (one override per person per iteration)"
            )
        seen_ids.add(pid)
        if valid_person_ids is not None and pid not in valid_person_ids:
            errors.append(
                f"{path}: iteration.people[{idx}] id={pid!r} "
                f"not found in .edpa/config/people.yaml"
            )

        # Engine knows how to override capacity_per_iteration / capacity.
        # An override entry without any recognised override field is
        # almost certainly a typo — except when only `note:` is set
        # (audit-only annotation, e.g., "Bob worked his usual hours but
        # we want to record context").
        recognised = {"capacity_per_iteration", "capacity"}
        has_capacity_override = any(
            k in entry and entry[k] is not None for k in recognised
        )
        has_note = bool((entry.get("note") or "").strip())
        if not has_capacity_override and not has_note:
            errors.append(
                f"{path}: iteration.people[{idx}] has no override fields. "
                f"Set capacity_per_iteration and/or note."
            )

        for key in recognised:
            val = entry.get(key)
            if val is None:
                continue
            try:
                num = float(val)
            except (TypeError, ValueError):
                errors.append(
                    f"{path}: iteration.people[{idx}].{key} must be numeric "
                    f"(got {val!r})"
                )
                continue
            if num < 0:
                errors.append(
                    f"{path}: iteration.people[{idx}].{key} must be >= 0 "
                    f"(got {num})"
                )

    return errors, warnings


# Backward-compat alias — older callers / tests still importing the
# v1.9.0-RFC name continue to work after the rename to the simpler
# iteration.people[] schema.
validate_capacity_overrides = validate_iteration_people_overrides


def _is_backlog_path(path: Path) -> bool:
    """True if `path` lives under a backlog item dir we know how to validate."""
    parts = path.parts
    if ".edpa" not in parts:
        return False
    try:
        idx = parts.index(".edpa")
    except ValueError:
        return False
    backlog_idx = idx + 1
    if backlog_idx >= len(parts) or parts[backlog_idx] != "backlog":
        return False
    type_idx = backlog_idx + 1
    if type_idx >= len(parts):
        return False
    type_dir = parts[type_idx]
    return any(s["dir"] == type_dir for s in ITEM_SCHEMA.values())


def _schema_for_path(path: Path):
    """Return (item_type, schema) when path is under a known type dir."""
    for item_type, schema in ITEM_SCHEMA.items():
        if f"/backlog/{schema['dir']}/" in str(path).replace("\\", "/"):
            return item_type, schema
    return None, None


def validate_backlog_schema(path: Path, data, *, strict=False):
    """Validate a parsed backlog-item dict against ITEM_SCHEMA.

    Returns (errors, warnings) — both lists of "<path>: <message>" strings.
    Contributors role checks are warnings by default (real-world backlogs
    often use human-readable labels like 'architect' for documentation);
    pass strict=True to upgrade them to errors.
    """
    errors = []
    warnings = []
    if not isinstance(data, dict):
        return [f"{path}: backlog item must be a YAML mapping (got {type(data).__name__})"], warnings

    expected_type, schema = _schema_for_path(path)
    if not schema:
        return errors  # not a backlog file we recognize

    declared_type = data.get("type")
    if declared_type and declared_type != expected_type:
        errors.append(
            f"{path}: type={declared_type!r} but file is under "
            f"backlog/{schema['dir']}/ (expected type={expected_type!r})"
        )

    # Required fields
    for field in schema["required"]:
        if field == "parent":
            # `parent: null` is acceptable for items where parent is optional
            if "parent" not in data:
                if schema["parent_required"]:
                    errors.append(f"{path}: missing required field 'parent'")
            continue
        if field not in data or data[field] in (None, ""):
            errors.append(f"{path}: missing required field {field!r}")

    # ID prefix sanity
    item_id = data.get("id")
    if isinstance(item_id, str):
        prefix = TYPE_PREFIXES.get(expected_type)
        if prefix and not item_id.startswith(f"{prefix}-"):
            errors.append(
                f"{path}: id={item_id!r} should start with {prefix!r}- "
                f"for type {expected_type}"
            )

    # Status enum
    status = data.get("status")
    if status and status not in schema["statuses"]:
        errors.append(
            f"{path}: status={status!r} is not valid for {expected_type}. "
            f"Allowed: {sorted(schema['statuses'])}"
        )

    # roam_status enum (Risk only)
    roam_status = data.get("roam_status")
    if roam_status is not None and expected_type == "Risk":
        if roam_status not in ROAM_STATUSES:
            errors.append(
                f"{path}: roam_status={roam_status!r} is not valid. "
                f"Allowed: {sorted(ROAM_STATUSES)}"
            )

    # JS sanity. Only Stories and Defects must have a positive estimate;
    # Initiatives / Epics / Features carry `js` as optional and frequently
    # land with `js: 0` meaning "no estimate yet at this hierarchy level".
    # Treat 0 as equivalent to missing for the optional-js levels.
    js_required = "js" in schema.get("required", set())
    js = data.get("js")
    if js is not None:
        try:
            js_val = float(js)
            if js_val < 0:
                errors.append(f"{path}: js must be >= 0 (got {js!r})")
            elif js_val == 0 and js_required:
                errors.append(
                    f"{path}: js must be > 0 for {expected_type} "
                    f"(got 0 — Stories/Defects need an estimate)"
                )
        except (TypeError, ValueError):
            errors.append(f"{path}: js must be numeric (got {js!r})")

    # Iteration tag sanity for Stories
    if expected_type == "Story":
        iteration = data.get("iteration", "")
        if iteration and not isinstance(iteration, str):
            errors.append(f"{path}: iteration must be a string (got {type(iteration).__name__})")

    # Contributors schema (v1.11+). Each entry carries:
    #   - person   (required, person id from people.yaml)
    #   - cw       (per-item normalized share, [0,1])
    #   - contribution_score (raw sum of signal weights, ≥ 0)
    #   - signals  (list of signal records with type/ref/weight/...)
    #
    # Legacy keys from earlier schema versions are HARD errors with a
    # migration pointer:
    #   - `role:` / `weight:` (pre-v1.7 names)
    #   - `as:`               (pre-v1.11 role classifier — dropped in v1.11)
    contribs = data.get("contributors")
    if contribs is not None:
        bucket = errors if strict else warnings
        if not isinstance(contribs, list):
            errors.append(f"{path}: contributors must be a list (got {type(contribs).__name__})")
        else:
            cw_sum = 0.0
            cw_seen = 0
            for idx, entry in enumerate(contribs):
                if not isinstance(entry, dict):
                    errors.append(
                        f"{path}: contributors[{idx}] must be a mapping "
                        f"(got {type(entry).__name__})"
                    )
                    continue
                if not entry.get("person"):
                    bucket.append(f"{path}: contributors[{idx}] missing 'person'")

                # Reject legacy keys with migration breadcrumb.
                if "role" in entry:
                    errors.append(
                        f"{path}: contributors[{idx}] uses legacy 'role' — "
                        f"renamed to 'as' in v1.7, then dropped in v1.11. "
                        f"Re-run `detect_contributors.py --pr <N>` to regenerate "
                        f"with v1.11 schema (signals[] + per-item cw share)."
                    )
                if "weight" in entry:
                    errors.append(
                        f"{path}: contributors[{idx}] uses legacy 'weight' — "
                        f"replaced by 'cw' (since v1.7) and 'contribution_score' "
                        f"(since v1.11). Run `detect_contributors.py` to migrate."
                    )
                if "as" in entry:
                    errors.append(
                        f"{path}: contributors[{idx}] uses legacy 'as' field — "
                        f"role classification was dropped in v1.11 (role is now "
                        f"derived from signals[].type at display time). Re-run "
                        f"`detect_contributors.py --pr <N>` to regenerate."
                    )

                # cw — must be in [0,1]
                cw_value = entry.get("cw")
                if cw_value is None:
                    bucket.append(
                        f"{path}: contributors[{idx}] missing 'cw' "
                        f"(per-item share, [0,1])"
                    )
                else:
                    try:
                        cw_num = float(cw_value)
                    except (TypeError, ValueError):
                        errors.append(
                            f"{path}: contributors[{idx}] cw must be numeric "
                            f"(got {cw_value!r})"
                        )
                        continue
                    if not 0 <= cw_num <= 1:
                        errors.append(
                            f"{path}: contributors[{idx}] cw must be in [0,1] "
                            f"(got {cw_num})"
                        )
                    cw_sum += cw_num
                    cw_seen += 1

                # contribution_score — informational, must be ≥ 0 if present
                cs_value = entry.get("contribution_score")
                if cs_value is not None:
                    try:
                        cs_num = float(cs_value)
                        if cs_num < 0:
                            errors.append(
                                f"{path}: contributors[{idx}] "
                                f"contribution_score must be ≥ 0 (got {cs_num})"
                            )
                    except (TypeError, ValueError):
                        errors.append(
                            f"{path}: contributors[{idx}] contribution_score "
                            f"must be numeric (got {cs_value!r})"
                        )

                # signals — list of records with type/ref/weight at minimum
                signals = entry.get("signals")
                if signals is not None:
                    if not isinstance(signals, list):
                        errors.append(
                            f"{path}: contributors[{idx}].signals must be a list"
                        )
                    else:
                        for s_idx, sig in enumerate(signals):
                            if not isinstance(sig, dict):
                                errors.append(
                                    f"{path}: contributors[{idx}].signals[{s_idx}] "
                                    f"must be a mapping"
                                )
                                continue
                            for required in ("type", "ref", "weight"):
                                if required not in sig:
                                    bucket.append(
                                        f"{path}: contributors[{idx}].signals[{s_idx}] "
                                        f"missing '{required}'"
                                    )
                            sw = sig.get("weight")
                            if sw is not None:
                                try:
                                    if float(sw) < 0:
                                        errors.append(
                                            f"{path}: contributors[{idx}].signals"
                                            f"[{s_idx}].weight must be ≥ 0"
                                        )
                                except (TypeError, ValueError):
                                    errors.append(
                                        f"{path}: contributors[{idx}].signals"
                                        f"[{s_idx}].weight must be numeric"
                                    )

            # Per-item invariant: Σ cw = 1.0 (when contributors exist).
            # Allow rounding tolerance because YAML values are
            # rounded to 4 decimals by detect_contributors.
            if cw_seen >= 2 and abs(cw_sum - 1.0) > 0.005:
                bucket.append(
                    f"{path}: Σ contributors[].cw = {cw_sum:.4f}, expected 1.0 "
                    f"(tolerance 0.005). Re-run detect_contributors to recompute."
                )

    return errors, warnings


def validate_yaml(path, *, content=None, strict=False):
    """Validate a single YAML file. Returns (errors, warnings).

    `content` may be passed in for stdin mode; otherwise file is read.
    `strict` upgrades soft schema warnings (unknown contributor role,
    missing person/role) to errors.
    """
    errors = []
    warnings = []
    path = Path(path)

    if content is None:
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            errors.append(f"{path}: file not found")
            return errors, warnings
        except UnicodeDecodeError:
            errors.append(f"{path}: binary file, not valid YAML")
            return errors, warnings

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        errors.append(f"{path}: {e}")
        return errors, warnings

    # Iteration YAMLs may carry top-level `people:` overrides (v1.9+).
    if data is not None and _is_iteration_path(path):
        iter_errors, iter_warnings = validate_iteration_people_overrides(
            path, data, strict=strict)
        errors.extend(iter_errors)
        warnings.extend(iter_warnings)

    return errors, warnings


def validate_markdown(path, *, content=None, strict=False):
    """Validate a single backlog `.md` file (frontmatter + body).

    Only files under ``.edpa/backlog/<type>/`` are subject to schema
    checks; other `.md` files (docs, READMEs, …) are accepted as-is.
    """
    errors: list[str] = []
    warnings: list[str] = []
    path = Path(path)

    # Schema checks apply only to backlog `.md` files.
    if not _is_backlog_path(path):
        return errors, warnings

    if content is not None:
        # stdin mode — parse via the same helper. We round-trip through
        # a temp string by hand-splitting.
        from _md_frontmatter import _split_frontmatter  # type: ignore
        yaml_text, body_text = _split_frontmatter(content)
        try:
            data = yaml.safe_load(yaml_text) if yaml_text.strip() else {}
        except yaml.YAMLError as e:
            return [f"{path}: frontmatter YAML error: {e}"], warnings
        if not isinstance(data, dict):
            data = {}
        data["body"] = body_text
    else:
        data = _load_md(path)
        if data is None:
            return [f"{path}: file not found"], warnings

    # Prose must live in body, not in frontmatter.
    fm_only = {k: v for k, v in data.items() if k != "body"}
    leaked = sorted(BACKLOG_BODY_FIELDS & fm_only.keys())
    if leaked:
        errors.append(
            f"{path}: prose field(s) {leaked!r} must live in the Markdown "
            f"body, not in YAML frontmatter (move them under "
            f"`## Description` etc.)"
        )

    item_errors, item_warnings = validate_backlog_schema(
        path, fm_only, strict=strict)
    errors.extend(item_errors)
    warnings.extend(item_warnings)
    return errors, warnings


def validate_json(path, *, content=None):
    """Validate a single JSON file. Returns (errors, warnings)."""
    path = Path(path)
    if content is None:
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return [f"{path}: file not found"], []
        except UnicodeDecodeError:
            return [f"{path}: binary file, not valid JSON"], []

    try:
        json.loads(content)
    except json.JSONDecodeError as e:
        return [f"{path}: {e}"], []
    return [], []


def validate_python(path, *, content=None):
    """Validate Python syntax. Returns (errors, warnings)."""
    path = Path(path)
    if content is None:
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return [f"{path}: file not found"], []
        except UnicodeDecodeError:
            return [f"{path}: binary file, not valid Python"], []

    try:
        ast.parse(content, filename=str(path))
    except SyntaxError as e:
        return [f"{path}: {e.msg} (line {e.lineno})"], []
    return [], []


def validate_file(path, *, content=None, kind=None, strict=False):
    """Validate a single file based on its extension or explicit kind.

    Returns (errors, warnings).
    """
    path = Path(path)
    if kind is None:
        ext = path.suffix.lower()
        if ext in YAML_EXTENSIONS:
            kind = "yaml"
        elif ext in MARKDOWN_EXTENSIONS:
            kind = "markdown"
        elif ext in JSON_EXTENSIONS:
            kind = "json"
        elif ext in PYTHON_EXTENSIONS:
            kind = "python"
        else:
            return [], []

    if kind == "yaml":
        return validate_yaml(path, content=content, strict=strict)
    if kind == "markdown":
        return validate_markdown(path, content=content, strict=strict)
    if kind == "json":
        return validate_json(path, content=content)
    if kind == "python":
        return validate_python(path, content=content)
    return [], []


def validate_directory(directory, *, strict=False):
    """Validate all supported files in a directory tree.

    Returns (errors, warnings).
    """
    directory = Path(directory)
    all_errors = []
    all_warnings = []
    seen = set()

    for ext_set in [YAML_EXTENSIONS, MARKDOWN_EXTENSIONS,
                    JSON_EXTENSIONS, PYTHON_EXTENSIONS]:
        for ext in ext_set:
            for path in directory.glob(f"**/*{ext}"):
                if path in seen:
                    continue
                seen.add(path)
                e, w = validate_file(path, strict=strict)
                all_errors.extend(e)
                all_warnings.extend(w)

    return all_errors, all_warnings


def _read_stdin():
    return sys.stdin.read()


def main():
    if len(sys.argv) < 2:
        print("Usage: validate_syntax.py <path> [<path> ...]", file=sys.stderr)
        print("       validate_syntax.py - --kind yaml         (read from stdin)",
              file=sys.stderr)
        print("       validate_syntax.py --strict <path>       (upgrade soft warnings to errors)",
              file=sys.stderr)
        sys.exit(1)

    # Parse --kind (stdin mode) and --strict flags out of argv
    kind_override = None
    strict = False
    cleaned = []
    it = iter(sys.argv[1:])
    for arg in it:
        if arg == "--kind":
            try:
                kind_override = next(it).lower()
            except StopIteration:
                print("ERROR: --kind requires a value", file=sys.stderr)
                sys.exit(1)
            continue
        if arg == "--strict":
            strict = True
            continue
        cleaned.append(arg)

    all_errors = []
    all_warnings = []
    for arg in cleaned:
        if arg in ("-", "/dev/stdin"):
            content = _read_stdin()
            kind = kind_override or "yaml"  # default for backlog hooks
            label = Path("<stdin>")
            e, w = validate_file(label, content=content, kind=kind, strict=strict)
            all_errors.extend(e)
            all_warnings.extend(w)
            continue
        p = Path(arg)
        if p.is_dir():
            e, w = validate_directory(p, strict=strict)
            all_errors.extend(e)
            all_warnings.extend(w)
        elif p.is_file():
            e, w = validate_file(p, strict=strict)
            all_errors.extend(e)
            all_warnings.extend(w)
        else:
            all_errors.append(f"{p}: not found")

    for w in all_warnings:
        print(f"WARN:  {w}", file=sys.stderr)

    if all_errors:
        for err in all_errors:
            print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)
    elif all_warnings:
        print(f"All files valid (with {len(all_warnings)} warning"
              f"{'s' if len(all_warnings) != 1 else ''}).")
    else:
        print("All files valid.")


if __name__ == "__main__":
    main()
