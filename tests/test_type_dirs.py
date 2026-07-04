"""D-52 drift guard — the type→directory/prefix mapping has ONE home.

``id_counter`` owns the canonical tables (Krok 2 of the V2 plan):

  * ``TYPE_DIRS`` / ``TYPE_PREFIX``       — create surface (allocatable types)
  * ``LEGACY_TYPE_DIRS`` / ``…_PREFIX``   — read-only legacy Task surface
  * ``ALL_TYPE_DIRS`` / ``ALL_TYPE_PREFIX`` / ``DIR_TO_TYPE`` /
    ``PREFIX_TO_DIR``                     — full read surface, derived
  * ``ENGINE_CREDIT_DIRS`` / ``GATE_TYPE_DIRS`` — named deliberate subsets

Before D-52 the mapping was hardcoded independently in 7+ modules and the
copies had drifted (backlog.TYPE_DIRS lacked Risk → next_id_for_type
KeyError; local_evidence.PREFIX_TO_DIR lacked T→tasks; engine credited a
"Task" level its loader never loads). Every consumer now imports the
canonical object — this suite fails the build if a module re-declares a
copy (identity checks) or if a deliberately-literal table drifts (equality
checks).

Run: python3 -m pytest tests/test_type_dirs.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugin" / "edpa" / "scripts"))

import _md_frontmatter  # noqa: E402
import _people_loader  # noqa: E402
import backlog  # noqa: E402
import detect_contributors  # noqa: E402
import engine  # noqa: E402
import id_counter  # noqa: E402
import local_evidence  # noqa: E402
import sync_pr_contributions  # noqa: E402
import transitions  # noqa: E402
import validate_syntax  # noqa: E402


# ─── Canonical tables are internally consistent ─────────────────────────────


def test_canonical_tables_cover_same_types():
    assert set(id_counter.TYPE_DIRS) == set(id_counter.TYPE_PREFIX)
    assert set(id_counter.LEGACY_TYPE_DIRS) == set(id_counter.LEGACY_TYPE_PREFIX)
    assert id_counter.ALL_TYPE_DIRS == {
        **id_counter.TYPE_DIRS, **id_counter.LEGACY_TYPE_DIRS,
    }
    assert id_counter.ALL_TYPE_PREFIX == {
        **id_counter.TYPE_PREFIX, **id_counter.LEGACY_TYPE_PREFIX,
    }


def test_canonical_derived_maps_are_bijections():
    dirs = list(id_counter.ALL_TYPE_DIRS.values())
    prefixes = list(id_counter.ALL_TYPE_PREFIX.values())
    assert len(dirs) == len(set(dirs)), "duplicate directory"
    assert len(prefixes) == len(set(prefixes)), "duplicate prefix"
    assert id_counter.DIR_TO_TYPE == {
        d: t for t, d in id_counter.ALL_TYPE_DIRS.items()
    }
    assert id_counter.PREFIX_TO_DIR == {
        p: id_counter.ALL_TYPE_DIRS[t]
        for t, p in id_counter.ALL_TYPE_PREFIX.items()
    }


def test_task_is_legacy_read_only():
    """Task: readable (ALL_*) but never creatable (create surface) —
    the D-3/D-46 design decision, now explicit."""
    assert "Task" not in id_counter.TYPE_DIRS
    assert "Task" not in id_counter.TYPE_PREFIX
    assert id_counter.ALL_TYPE_DIRS["Task"] == "tasks"
    assert id_counter.PREFIX_TO_DIR["T"] == "tasks"


def test_risk_is_creatable():
    """Regression: the drifted backlog.TYPE_DIRS copy lacked Risk (KeyError
    in the dead next_id_for_type). The canonical create surface has it."""
    assert id_counter.TYPE_DIRS["Risk"] == "risks"
    assert id_counter.TYPE_PREFIX["Risk"] == "R"


def test_named_subsets_derive_from_canonical():
    # Engine credit scope: Stories/Defects at Done + gate-event parents.
    # Events/Risks are PI-planning artefacts (deliberately uncredited,
    # see CHANGELOG); Tasks are legacy read-only.
    assert id_counter.ENGINE_CREDIT_DIRS == {
        "stories": "Story", "features": "Feature", "epics": "Epic",
        "initiatives": "Initiative", "defects": "Defect",
    }
    for d, t in id_counter.ENGINE_CREDIT_DIRS.items():
        assert id_counter.TYPE_DIRS[t] == d
    assert not {"events", "risks", "tasks"} & set(id_counter.ENGINE_CREDIT_DIRS)

    assert id_counter.GATE_TYPE_DIRS == {
        "Feature": "features", "Epic": "epics", "Initiative": "initiatives",
    }
    for t, d in id_counter.GATE_TYPE_DIRS.items():
        assert id_counter.TYPE_DIRS[t] == d


# ─── Consumers import the canonical objects (identity, not copies) ──────────


def test_backlog_uses_canonical_tables():
    assert backlog.TYPE_DIRS is id_counter.TYPE_DIRS
    assert backlog.TYPE_PREFIX is id_counter.ALL_TYPE_PREFIX
    assert backlog.PREFIX_TO_DIR is id_counter.PREFIX_TO_DIR
    # Identity map over the full read surface (level == type in V2).
    assert backlog.TYPE_TO_LEVEL == {t: t for t in id_counter.ALL_TYPE_DIRS}
    # The drifted-copy carrier was deleted, not patched.
    assert not hasattr(backlog, "next_id_for_type")


def test_mcp_server_uses_canonical_tables():
    mcp_server = _import_mcp_server()
    assert mcp_server.TYPE_DIRS is id_counter.TYPE_DIRS
    # Scan order is a local choice (most-common dirs first); contents must
    # equal the canonical read surface.
    assert dict(mcp_server.BACKLOG_TYPE_DIRS) == id_counter.DIR_TO_TYPE
    assert set(mcp_server.ITEM_LOOKUP_DIRS) == set(id_counter.DIR_TO_TYPE)
    assert mcp_server._PREFIX_TO_DIR is id_counter.PREFIX_TO_DIR


def test_local_evidence_uses_canonical_tables():
    assert local_evidence.PREFIX_TO_DIR is id_counter.PREFIX_TO_DIR
    assert local_evidence._DIR_TO_TYPE is id_counter.DIR_TO_TYPE
    # Regression (D-52): T→tasks was missing here while detect_contributors
    # had it — commits referencing legacy Task items were silently skipped.
    assert local_evidence.PREFIX_TO_DIR["T"] == "tasks"


def test_sync_pr_contributions_uses_canonical_tables():
    assert sync_pr_contributions.PREFIX_TO_DIR is id_counter.PREFIX_TO_DIR


def test_transitions_uses_canonical_tables():
    """D-67 regression: transitions.py carried a drifted pre-D-52 copy of
    the tracked-dir map without defects/ — Defect status flips emitted no
    state_transition evidence (E2E: D-1..D-3 had commit evidence but
    transitions=[]). The transition-tracked scope IS the delivery-tracked
    engine-credit scope: Events/Risks are PI-planning artefacts and Tasks
    are legacy read-only, all deliberately untracked."""
    assert transitions.TRACKED_DIRS is id_counter.ENGINE_CREDIT_DIRS


def test_detect_contributors_uses_canonical_tables():
    assert detect_contributors.PREFIX_TO_DIR is id_counter.PREFIX_TO_DIR
    assert detect_contributors._ALL_TYPE_DIRS is id_counter.ALL_TYPE_DIRS


def test_engine_uses_canonical_scopes():
    assert engine.ENGINE_CREDIT_DIRS is id_counter.ENGINE_CREDIT_DIRS
    assert engine.GATE_TYPE_DIRS is id_counter.GATE_TYPE_DIRS


def test_people_loader_scans_full_read_surface():
    assert _people_loader._ALL_TYPE_DIRS is id_counter.ALL_TYPE_DIRS


def test_validate_syntax_uses_canonical_prefixes():
    assert validate_syntax.TYPE_PREFIXES is id_counter.ALL_TYPE_PREFIX
    # The per-type schema "dir" fields are part of hand-written schema
    # definitions — pin them to the canonical map by equality.
    assert {
        t: schema["dir"] for t, schema in validate_syntax.ITEM_SCHEMA.items()
    } == id_counter.ALL_TYPE_DIRS


def test_md_frontmatter_level_tokens_match_read_surface():
    # Deliberately literal (leaf module) — equality-pinned here.
    assert set(_md_frontmatter.META_LEVEL_TOKENS) == set(id_counter.ALL_TYPE_DIRS)


# ─── Functional smoke: every creatable type allocates ────────────────────────


def test_next_id_allocates_every_creatable_type(tmp_path):
    """Risk (and every other create-surface type) allocates cleanly — the
    concrete drift bug was a KeyError on Risk in a stale copy."""
    for item_type, prefix in id_counter.TYPE_PREFIX.items():
        assert id_counter.next_id(item_type, tmp_path) == f"{prefix}-1"


def _import_mcp_server():
    import importlib
    return importlib.import_module("mcp_server")
