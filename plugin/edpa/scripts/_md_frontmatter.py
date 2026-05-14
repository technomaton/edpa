"""Markdown + YAML frontmatter helper for EDPA backlog items.

Backlog items live in ``.edpa/backlog/{type}/{ID}.md`` as a YAML frontmatter
block (structured metadata: id, status, js, contributors[], …) followed by a
Markdown body (prose: description, acceptance criteria, refinement notes,
notes).

This module is the single source of truth for that format. All readers and
writers in the engine, sync, validator, board, MCP server, and pi-planning
backend go through these helpers — keeping the on-disk format consistent and
the file/issue body symmetric (the file body is what gets pushed to a GitHub
issue body verbatim).
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is a hard dep
    print("ERROR: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    raise


FRONTMATTER_DELIM = "---"
BODY_SECTIONS = ("description", "acceptance_criteria", "refinement_notes", "notes")
SECTION_HEADINGS = {
    "description": "Description",
    "acceptance_criteria": "Acceptance Criteria",
    "refinement_notes": "Refinement Notes",
    "notes": "Notes",
}
EDPA_TRAILER = "\n---\n_Managed by EDPA — edit fields in `.edpa/backlog/`._"


# ─── Parse / serialize ──────────────────────────────────────────────────────


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Split a markdown-with-frontmatter file into (yaml_text, body_text).

    Accepts either ``---\\n...\\n---\\n<body>`` or a body-only file (no
    leading frontmatter). Empty/missing files return ("", "").
    """
    if not text:
        return "", ""
    if not text.startswith(FRONTMATTER_DELIM):
        return "", text
    # split off the leading "---\n"
    rest = text[len(FRONTMATTER_DELIM):]
    if rest.startswith("\r\n"):
        rest = rest[2:]
    elif rest.startswith("\n"):
        rest = rest[1:]
    # find the closing "---" on its own line
    end_match = re.search(r"^---\s*$", rest, flags=re.MULTILINE)
    if not end_match:
        # malformed — treat the whole thing as body
        return "", text
    yaml_text = rest[: end_match.start()]
    body_text = rest[end_match.end():]
    # strip exactly one leading newline from the body
    if body_text.startswith("\r\n"):
        body_text = body_text[2:]
    elif body_text.startswith("\n"):
        body_text = body_text[1:]
    return yaml_text, body_text


def load_md(path: str | Path) -> dict[str, Any] | None:
    """Load a `.md` backlog item. Returns frontmatter fields plus ``body``.

    The returned dict contains every YAML frontmatter key (or empty if no
    frontmatter), plus a ``"body"`` key holding the raw Markdown body
    (possibly empty string). Returns ``None`` if the file is missing.
    """
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        print(f"WARNING: load_md({path}) failed: {exc}", file=sys.stderr)
        return None

    yaml_text, body_text = _split_frontmatter(text)
    try:
        data = yaml.safe_load(yaml_text) if yaml_text.strip() else {}
    except yaml.YAMLError as exc:
        print(f"WARNING: load_md({path}) YAML parse failed: {exc}", file=sys.stderr)
        data = {}
    if not isinstance(data, dict):
        data = {}
    data["body"] = body_text
    return data


def _dump_frontmatter(frontmatter: dict[str, Any]) -> str:
    """Serialize frontmatter dict to YAML, ruamel round-trip when available.

    Falls back to PyYAML for the simple case. We deliberately keep the
    field order as provided by the caller (sort_keys=False) so callers can
    enforce a canonical layout.
    """
    if not frontmatter:
        return ""
    try:
        from ruamel.yaml import YAML  # type: ignore

        ryaml = YAML()
        ryaml.preserve_quotes = True
        ryaml.width = 120
        ryaml.indent(mapping=2, sequence=2, offset=0)
        buf = io.StringIO()
        ryaml.dump(frontmatter, buf)
        return buf.getvalue()
    except ImportError:
        return yaml.dump(
            frontmatter,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=120,
        )


def save_md(path: str | Path, frontmatter: dict[str, Any], body: str = "") -> None:
    """Write a `.md` backlog item.

    ``frontmatter`` should NOT contain a ``body`` key (callers using
    ``load_md`` need to pop it first, or use the convenience
    :func:`save_md_item` which accepts a single merged dict).
    ``body`` is written verbatim — it should already be Markdown text.
    A trailing newline is ensured.
    """
    fm_dict = {k: v for k, v in frontmatter.items() if k != "body"}
    yaml_text = _dump_frontmatter(fm_dict)
    parts = [f"{FRONTMATTER_DELIM}\n", yaml_text]
    if not yaml_text.endswith("\n"):
        parts.append("\n")
    parts.append(f"{FRONTMATTER_DELIM}\n")
    if body:
        if not body.startswith("\n"):
            parts.append("\n")
        parts.append(body)
        if not body.endswith("\n"):
            parts.append("\n")
    Path(path).write_text("".join(parts), encoding="utf-8")


def save_md_item(path: str | Path, item: dict[str, Any]) -> None:
    """Convenience: split an item dict (with ``body`` key) into FM + body."""
    body = item.get("body") or ""
    fm = {k: v for k, v in item.items() if k != "body"}
    save_md(path, fm, body)


def update_frontmatter_field(
    path: str | Path, field: str, value: Any
) -> bool:
    """Update one frontmatter field in-place, preserving body and other keys.

    Uses ruamel.yaml round-trip so quotes, list styles, and comments inside
    the frontmatter survive the write. Returns True on success.
    """
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        print(
            f"WARNING: update_frontmatter_field({path}, {field!r}) read failed: {exc}",
            file=sys.stderr,
        )
        return False

    yaml_text, body_text = _split_frontmatter(text)
    try:
        from ruamel.yaml import YAML  # type: ignore

        ryaml = YAML()
        ryaml.preserve_quotes = True
        ryaml.width = 120
        ryaml.indent(mapping=2, sequence=2, offset=0)
        doc = ryaml.load(yaml_text) if yaml_text.strip() else {}
        if doc is None:
            doc = {}
        doc[field] = value
        buf = io.StringIO()
        ryaml.dump(doc, buf)
        new_yaml = buf.getvalue()
    except ImportError:
        # Fallback: lose comments but preserve field order via PyYAML.
        data = yaml.safe_load(yaml_text) if yaml_text.strip() else {}
        if not isinstance(data, dict):
            data = {}
        data[field] = value
        new_yaml = yaml.dump(
            data, default_flow_style=False, allow_unicode=True,
            sort_keys=False, width=120,
        )
    except Exception as exc:  # pragma: no cover - defensive
        print(
            f"WARNING: update_frontmatter_field({path}, {field!r}) failed: {exc}",
            file=sys.stderr,
        )
        return False

    parts = [f"{FRONTMATTER_DELIM}\n", new_yaml]
    if not new_yaml.endswith("\n"):
        parts.append("\n")
    parts.append(f"{FRONTMATTER_DELIM}\n")
    if body_text:
        if not body_text.startswith("\n"):
            parts.append("\n")
        parts.append(body_text)
        if not body_text.endswith("\n"):
            parts.append("\n")
    p.write_text("".join(parts), encoding="utf-8")
    return True


# ─── Body sections ──────────────────────────────────────────────────────────

_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", flags=re.MULTILINE)


def parse_body_sections(body: str) -> dict[str, Any]:
    """Best-effort split of a markdown body into known prose sections.

    Recognizes the canonical headings (case-insensitive, ignores extra
    whitespace): Description, Acceptance Criteria, Refinement Notes, Notes.
    Returns a dict keyed by ``BODY_SECTIONS``; missing sections are absent.
    For ``acceptance_criteria``: if all non-empty lines are ``- [ ]`` / ``- [x]``
    checkboxes, the value is a list of stripped strings; otherwise the raw
    section text.
    """
    if not body:
        return {}
    # Map normalized heading text -> canonical key
    head_to_key = {v.lower(): k for k, v in SECTION_HEADINGS.items()}

    matches = list(_SECTION_RE.finditer(body))
    out: dict[str, Any] = {}
    for i, m in enumerate(matches):
        heading = m.group(1).strip().lower()
        key = head_to_key.get(heading)
        if not key:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        # also stop at the EDPA trailer if present
        chunk = body[start:end]
        trailer_idx = chunk.find("\n---\n_Managed by EDPA")
        if trailer_idx >= 0:
            chunk = chunk[:trailer_idx]
        chunk = chunk.strip()
        if not chunk:
            continue
        if key == "acceptance_criteria":
            lines = [ln.rstrip() for ln in chunk.splitlines() if ln.strip()]
            if lines and all(re.match(r"^-\s*\[[ xX]\]\s+", ln) for ln in lines):
                out[key] = [
                    re.sub(r"^-\s*\[[ xX]\]\s+", "", ln) for ln in lines
                ]
                continue
        out[key] = chunk
    return out


def format_body_sections(item: dict[str, Any]) -> str:
    """Compose a Markdown body from prose fields in an item dict.

    Used by the YAML→MD migration script and as a fallback when callers
    have structured prose but no body yet. Returns "" when no prose fields
    are present.
    """
    parts: list[str] = []
    if item.get("description"):
        parts.append(f"## {SECTION_HEADINGS['description']}\n\n"
                     f"{str(item['description']).strip()}\n")
    ac = item.get("acceptance_criteria")
    if ac:
        if isinstance(ac, list):
            ac_md = "\n".join(f"- [ ] {c}" for c in ac)
        else:
            ac_md = str(ac).strip()
        parts.append(f"## {SECTION_HEADINGS['acceptance_criteria']}\n\n{ac_md}\n")
    if item.get("refinement_notes"):
        parts.append(
            f"## {SECTION_HEADINGS['refinement_notes']}\n\n"
            f"{str(item['refinement_notes']).strip()}\n"
        )
    if item.get("notes"):
        parts.append(f"## {SECTION_HEADINGS['notes']}\n\n"
                     f"{str(item['notes']).strip()}\n")
    return "\n".join(parts)


# ─── GitHub issue body ──────────────────────────────────────────────────────


def format_issue_body(item: dict[str, Any]) -> str:
    """Build the GitHub issue body for a backlog item.

    The body is the file's raw Markdown body, prefixed with a one-line meta
    summary (level + key WSJF inputs + owner + iteration) and suffixed with
    the EDPA trailer. This is what gets pushed to the GH issue ``body``
    field on every sync push.
    """
    meta: list[str] = []
    for k in ("js", "bv", "tc", "rr_oe", "wsjf"):
        v = item.get(k)
        if v:
            meta.append(f"{k.upper()}={v}")
    if item.get("assignee"):
        meta.append(f"owner={item['assignee']}")
    if item.get("iteration"):
        meta.append(f"iteration={item['iteration']}")
    level = item.get("level") or item.get("type") or ""
    meta_line = level + (" · " + ", ".join(meta) if meta else "")

    body = (item.get("body") or "").strip()
    parts = [meta_line]
    if body:
        parts.append("")  # blank line
        parts.append(body)
    parts.append(EDPA_TRAILER.lstrip("\n"))
    return "\n".join(parts)


def strip_issue_body_chrome(issue_body: str) -> str:
    """Inverse helper for pull: strip the meta line + EDPA trailer.

    Used on the pull path so the body written back to the local `.md` file
    is just the user-authored prose (no auto-generated chrome).
    """
    if not issue_body:
        return ""
    text = issue_body.replace("\r\n", "\n")
    # Drop the trailing EDPA trailer if present.
    trailer_idx = text.find("\n---\n_Managed by EDPA")
    if trailer_idx >= 0:
        text = text[:trailer_idx]
    # Drop the first line (meta line). It's auto-generated and starts with
    # the level token (Story / Feature / Epic / Initiative / Defect / Task)
    # optionally followed by " · …". We keep this conservative: only strip
    # if the first non-empty line matches the known shape.
    lines = text.split("\n")
    LEVELS = {"Story", "Feature", "Epic", "Initiative", "Defect", "Task",
              "Risk", "Milestone"}
    for i, ln in enumerate(lines):
        if not ln.strip():
            continue
        head = ln.split(" · ", 1)[0].strip()
        if head in LEVELS:
            # drop this line + any single blank line that follows
            del lines[i]
            if i < len(lines) and not lines[i].strip():
                del lines[i]
        break
    return "\n".join(lines).strip()
