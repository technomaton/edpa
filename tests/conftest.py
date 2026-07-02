"""Shared pytest setup for the EDPA test suite.

The engine intentionally ships as loose flat scripts (modules in
``plugin/edpa/scripts/`` import each other top-level so they can be
vendored without pip). Tests therefore import engine modules straight
off ``sys.path``.

This conftest puts the canonical scripts directory on ``sys.path`` once
for the whole suite, so new test files do not need the historical
two-line ``sys.path.insert`` header. Existing per-file headers are
idempotent duplicates; files with a standalone ``__main__`` runner keep
theirs so ``python3 tests/test_x.py`` still works outside pytest.
"""

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "plugin" / "edpa" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
