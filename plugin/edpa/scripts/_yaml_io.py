#!/usr/bin/env python3
"""Shared YAML / backlog-markdown loader.

One implementation of the ``.md``-frontmatter-vs-``.yaml`` split that
``engine.py`` and ``pi_close.py`` previously duplicated (S-242). The
``mcp_server.py`` loader stays separate on purpose — it adds an
mtime-keyed LRU cache for the long-running server process; CLI scripts
are one-shot and don't need it.

Semantics (parameterized because the historical callers differ):

* missing file → ``None``
* parse/OS error → warning on stderr (format preserved from the original
  implementations — tests assert on it), then ``None``
* empty file → ``None`` by default; ``{}`` with ``empty_as_dict=True``
  (pi_close semantics)
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)


def load_yaml(path, *, empty_as_dict: bool = False):
    """Load ``.md`` (frontmatter + ``body``) or ``.yaml`` content.

    Returns the parsed dict, ``None`` on missing/unparseable file, and —
    only when ``empty_as_dict`` is set — ``{}`` for empty content.
    """
    p = Path(path) if not isinstance(path, Path) else path
    if not p.is_file():
        return None
    try:
        if p.suffix == ".md":
            sys.path.insert(0, _SCRIPTS_DIR)
            try:
                from _md_frontmatter import load_md
            finally:
                sys.path.pop(0)
            data = load_md(p)
        else:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError) as exc:
        print(f"WARNING: load_yaml({p}) failed: {exc}", file=sys.stderr)
        return None
    if data is None and empty_as_dict:
        return {}
    return data
