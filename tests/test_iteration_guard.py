"""D-25: the engine must refuse a PI label passed as ``--iteration``.

The engine scores ONE iteration. A Story/Defect/Task only counts on an
exact iteration match (see ``load_backlog_items``), so pointing
``--iteration`` at a PI (``PI-YYYY-N``) silently drops every item tagged
``<pi>.N`` and emits a plausible-looking but under-counted report. PI
rollups belong to ``pi_close`` (the ``edpa_pi_close`` tool). These cover
the importable predicate (``_is_pi_id``) and the CLI guard (subprocess),
mirroring ``test_create_pi.py``.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugin" / "edpa" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from engine import _is_pi_id  # noqa: E402


def _mk_edpa(tmp_path: Path) -> Path:
    """A minimal .edpa/iterations/ with one PI, its sub-iterations, and a
    free-form iteration id (no ``pi:`` block)."""
    iters = tmp_path / ".edpa" / "iterations"
    iters.mkdir(parents=True)
    (iters / "PI-2026-1.yaml").write_text(
        yaml.safe_dump({"pi": {"id": "PI-2026-1", "status": "active",
                               "pi_iterations": 5}}),
        encoding="utf-8",
    )
    for n in (1, 2, 3):
        (iters / f"PI-2026-1.{n}.yaml").write_text(
            yaml.safe_dump({"iteration": {"id": f"PI-2026-1.{n}",
                                          "pi": "PI-2026-1"}}),
            encoding="utf-8",
        )
    # Free-form iteration id: a real iteration file, but no PI shape.
    (iters / "sprint-12.yaml").write_text(
        yaml.safe_dump({"iteration": {"id": "sprint-12"}}),
        encoding="utf-8",
    )
    return tmp_path / ".edpa"


# -- unit: _is_pi_id ----------------------------------------------------------

def test_is_pi_id_true_for_pi(tmp_path: Path) -> None:
    edpa = _mk_edpa(tmp_path)
    assert _is_pi_id(edpa, "PI-2026-1") is True


def test_is_pi_id_false_for_iteration(tmp_path: Path) -> None:
    edpa = _mk_edpa(tmp_path)
    assert _is_pi_id(edpa, "PI-2026-1.1") is False


def test_is_pi_id_false_for_freeform_id(tmp_path: Path) -> None:
    """An iteration file without a ``pi:`` block must never be flagged —
    this is what keeps the guard from false-positiving on projects that
    use non-``PI-YYYY-N.M`` iteration ids."""
    edpa = _mk_edpa(tmp_path)
    assert _is_pi_id(edpa, "sprint-12") is False


def test_is_pi_id_false_for_missing_or_empty(tmp_path: Path) -> None:
    edpa = _mk_edpa(tmp_path)
    assert _is_pi_id(edpa, "PI-2099-9") is False   # no such file
    assert _is_pi_id(edpa, None) is False
    assert _is_pi_id(edpa, "") is False


# -- integration: CLI guard ---------------------------------------------------

def test_cli_rejects_pi_as_iteration(tmp_path: Path) -> None:
    edpa = _mk_edpa(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "engine.py"),
         "--edpa-root", str(edpa), "--iteration", "PI-2026-1"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode != 0
    # Points the user at the right tool and the iteration form.
    assert "edpa_pi_close" in proc.stderr
    assert "PI-2026-1.1" in proc.stderr


def test_cli_does_not_flag_a_real_iteration(tmp_path: Path) -> None:
    """A genuine ``.N`` iteration must pass the guard. It may still fail
    later (this fixture has no config/backlog), but never with the PI
    message."""
    edpa = _mk_edpa(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "engine.py"),
         "--edpa-root", str(edpa), "--iteration", "PI-2026-1.1"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert "is a PI, not an iteration" not in proc.stderr
