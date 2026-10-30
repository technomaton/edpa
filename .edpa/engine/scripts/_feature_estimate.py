"""The Feature estimate rule (D-102), shared by the schema, `backlog.py
validate` and the MCP write layer.

A Feature is estimated when work on it starts. Before Implementing `js: 0`
means "no estimate yet"; from Implementing on the Feature needs all four WSJF
inputs, because the engine splits its job size across the status gates and
ranks Features by WSJF.

This module has no imports with side effects: mcp_server.py loads it and must
not pull in _console, which reconfigures stdout (see _console's docstring).
"""
from __future__ import annotations

WSJF_FIELDS = ("js", "bv", "tc", "rr_oe")
FEATURE_ESTIMATE_STATUSES = frozenset({
    "Implementing", "Validating", "Deploying", "Releasing", "Done",
})


def missing_wsjf_estimate(item) -> list:
    """The WSJF inputs of ``item`` that are not a number above 0."""
    missing = []
    for field in WSJF_FIELDS:
        value = item.get(field)
        try:
            estimated = not isinstance(value, bool) and float(value) > 0
        except (TypeError, ValueError):
            estimated = False
        if not estimated:
            missing.append(field)
    return missing
