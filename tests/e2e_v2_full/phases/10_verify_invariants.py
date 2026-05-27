#!/usr/bin/env python3
"""Wave C Unit 11 — Verify engine invariants + snapshot integrity (read-only).

Walks the sandbox under SANDBOX_DIR and asserts the post-conditions left by
Wave B (Units 8-10):

  1. Every iteration `edpa_results.json` has `all_invariants_passed=true`,
     per-person `invariant_ok=true`, and `team_total == sum(total_derived)`.
     For non-IP iterations, each person whose `total_derived > 0` must hit
     `capacity` within tolerance (engine clamps allocation to capacity).
  2. Every frozen snapshot under `.edpa/snapshots/` carries `frozen=true`
     plus a `payload_signature` that, when recomputed (sha256 over the
     payload with `generated_at`, `payload_signature`, `frozen_at` removed),
     matches the stored hex digest exactly. This is the same definition
     used by `engine.py::_payload_signature`.
  3. `backlog.py status` exits 0 (smoke test that the backlog is still
     readable + consistent end-to-end after engine + reports + close).
  4. Cross-PI rollups: aggregate `team_total` per PI and print totals.

Exit code 0 ⇒ all invariants hold ⇒ Wave B output is integrity-clean.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import yaml

SANDBOX = Path('/tmp/edpa-e2e-20260527-142316-c6ac4db8')
ITERATIONS_DIR = SANDBOX / '.edpa' / 'iterations'
REPORTS_GLOB = '.edpa/reports/iteration-PI-*/edpa_results.json'
SNAPSHOT_GLOB = '.edpa/snapshots/PI-2026-*.json'

# tolerance for per-person capacity invariant (engine rounds to 1 decimal,
# but we allow either 1% relative or 0.5h absolute to absorb planning_factor
# rounding).
CAP_REL_TOL = 0.01
CAP_ABS_TOL = 0.5


def load_iteration_types() -> dict[str, str]:
    """Read .edpa/iterations/*.yaml → {iter_id: type} (`IP` or `Iteration`)."""
    out: dict[str, str] = {}
    for f in sorted(ITERATIONS_DIR.glob('PI-2026-*.yaml')):
        data = yaml.safe_load(f.read_text())
        meta = data.get('iteration', {})
        out[meta.get('id', f.stem)] = meta.get('type', 'Iteration')
    return out


def verify_results(iter_types: dict[str, str]) -> list[dict]:
    """Phase 1 — verify edpa_results.json invariants. Returns table rows."""
    report_files = sorted(SANDBOX.glob(REPORTS_GLOB))
    assert len(report_files) == 10, (
        f'Expected 10 results files, got {len(report_files)}'
    )

    rows: list[dict] = []
    for f in report_files:
        data = json.loads(f.read_text())
        iter_id = data['iteration']
        iter_type = iter_types.get(iter_id, 'Iteration')

        # 1) top-level invariant
        assert data.get('all_invariants_passed') is True, (
            f'{iter_id}: all_invariants_passed != true'
        )

        # 2) team_total exists + equals sum of per-person totals
        assert 'team_total' in data, f'{iter_id}: missing team_total'
        people = data.get('people', [])
        sum_p = sum(p.get('total_derived', 0) for p in people)
        team_total = data['team_total']
        assert abs(team_total - sum_p) < 0.01, (
            f'{iter_id}: team_total={team_total} '
            f'!= sum(total_derived)={sum_p}'
        )

        # 3) per-person invariants
        all_ok = True
        for p in people:
            assert p.get('invariant_ok') is True, (
                f'{iter_id}: {p.get("id")} invariant_ok != true'
            )
            cap = p.get('capacity', 0)
            total = p.get('total_derived', 0)
            if total > 0:
                # engine clamps allocated hours to capacity when person had
                # delivery activity; tolerate 1% or 0.5h drift.
                tol = max(CAP_REL_TOL * cap, CAP_ABS_TOL)
                if abs(total - cap) > tol:
                    raise AssertionError(
                        f'{iter_id} {p.get("id")}: total_derived={total} '
                        f'capacity={cap} drift={abs(total - cap)} '
                        f'tol={tol}'
                    )
            # else: person had no activity this iteration → 0 is allowed.

        # IP iterations are expected to carry 0 derived hours (no Done
        # Story/Defect items by SAFe convention). Just emit a note.
        ip_note = ' (IP)' if iter_type == 'IP' else ''

        rows.append({
            'iter_id': iter_id,
            'all_invariants_passed': data['all_invariants_passed'],
            'team_total': team_total,
            'invariant_ok_all_people': all(
                p['invariant_ok'] for p in people
            ),
            'iter_type': iter_type,
            'note': ip_note,
            'people_count': len(people),
        })
        print(
            f'OK {iter_id}{ip_note}: team_total={team_total}h, '
            f'people={len(people)}, '
            f'per-person invariant_ok=all'
        )
    return rows


def verify_snapshots() -> list[dict]:
    """Phase 2 — verify snapshot files are frozen and signatures match."""
    snapshots = sorted(SANDBOX.glob(SNAPSHOT_GLOB))
    assert len(snapshots) >= 10, (
        f'Expected >=10 snapshots, got {len(snapshots)}'
    )

    rows: list[dict] = []
    for f in snapshots:
        data = json.loads(f.read_text())
        assert data.get('frozen') is True, f'{f.name}: frozen != true'
        sig = data.get('payload_signature')
        assert sig, f'{f.name}: missing payload_signature'
        # engine writes raw hex (no `sha256:` prefix) — see
        # engine.py::_payload_signature.
        assert len(sig) == 64 and all(c in '0123456789abcdef' for c in sig), (
            f'{f.name}: payload_signature is not 64-char hex: {sig!r}'
        )

        # Recompute and compare. Engine hashes the payload with `generated_at`
        # excluded *before* it injects `payload_signature` and `frozen_at`,
        # so verification must remove those three keys too.
        trial = {
            k: v for k, v in data.items()
            if k not in ('generated_at', 'payload_signature', 'frozen_at')
        }
        blob = json.dumps(trial, sort_keys=True, ensure_ascii=False)
        recomputed = hashlib.sha256(blob.encode('utf-8')).hexdigest()
        assert recomputed == sig, (
            f'{f.name}: signature mismatch\n'
            f'  stored:     {sig}\n  recomputed: {recomputed}'
        )

        size = f.stat().st_size
        rows.append({
            'name': f.name,
            'frozen': data['frozen'],
            'signature_prefix': sig[:16],
            'size_bytes': size,
        })
        print(
            f'OK {f.name}: frozen=True signature={sig[:16]}… '
            f'size={size}B (recomputed match)'
        )
    return rows


def run_backlog_status() -> str:
    """Phase 3 — backlog.py status must exit 0."""
    cmd = ['python3', str(SANDBOX / '.edpa/engine/scripts/backlog.py'), 'status']
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=SANDBOX)
    sys.stdout.write(result.stdout)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise AssertionError(
            f'backlog.py status exited {result.returncode}'
        )
    return result.stdout


def aggregate_totals(rows: list[dict]) -> tuple[float, float, float]:
    """Phase 4 — cross-PI rollups."""
    pi1 = sum(r['team_total'] for r in rows if r['iter_id'].startswith('PI-2026-1'))
    pi2 = sum(r['team_total'] for r in rows if r['iter_id'].startswith('PI-2026-2'))
    print(f'PI-2026-1 total: {pi1}h')
    print(f'PI-2026-2 total: {pi2}h')
    print(f'Combined total: {pi1 + pi2}h')
    return pi1, pi2, pi1 + pi2


def main() -> int:
    print('=' * 72)
    print('Phase 10 — verify_invariants.py')
    print(f'Sandbox: {SANDBOX}')
    print('=' * 72)

    print('\n[1/4] Iteration metadata (type) …')
    iter_types = load_iteration_types()
    for k, v in iter_types.items():
        print(f'  {k}: {v}')

    print('\n[2/4] Verifying edpa_results.json …')
    result_rows = verify_results(iter_types)

    print('\n[3/4] Verifying snapshots …')
    snap_rows = verify_snapshots()

    print('\n[4/4] Cross-check: backlog.py status …')
    run_backlog_status()

    print('\n--- Aggregate totals ---')
    pi1, pi2, total = aggregate_totals(result_rows)

    print('\n' + '=' * 72)
    print(
        f'VERDICT: PASS — '
        f'{len(result_rows)} iterations, {len(snap_rows)} snapshots, '
        f'PI-1={pi1}h PI-2={pi2}h total={total}h'
    )
    print('=' * 72)
    return 0


if __name__ == '__main__':
    sys.exit(main())
