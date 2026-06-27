"""
Edge case coverage for yaml_edit_signals.py.

Each test exercises one behavior of score_diff() — the pure scoring
function — without going through git. The integration test at the
bottom uses a temporary git repo to exercise the full collection
pipeline (window filter, bot author skip, bulk migration discount).
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts dir to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin/edpa/scripts"))

import yaml  # noqa: E402

from yaml_edit_signals import (  # noqa: E402
    DEFAULT_WEIGHTS,
    collect_yaml_edit_signals,
    score_diff,
)


W = DEFAULT_WEIGHTS


def _diff(text: str) -> list[str]:
    """Take a multi-line string with `+`/`-`/space prefixes and return
    diff lines (one per non-empty input line). Convenience helper for
    unit tests so each scenario reads as a real-looking diff."""
    return [l for l in text.split("\n") if l]


# ─── score_diff() unit tests ────────────────────────────────────────────────


class TestScoreDiff(unittest.TestCase):

    def test_whitespace_only_diff_zero_weight(self):
        diff = ["+    ", "-    "]
        weight, tags, _ = score_diff(diff, W)
        self.assertEqual(weight, 0.0)
        self.assertIn("whitespace_only", tags)

    def test_status_only_change_zero_weight(self):
        # transitions.py owns gate-event credit; yaml_edit must not
        # double-count when the only delta is a status field flip.
        diff = ["-status: Funnel", "+status: Reviewing"]
        weight, _, _ = score_diff(diff, W)
        self.assertEqual(weight, 0.0)

    def test_create_signal_fires_on_new_file(self):
        # New file = id + type + title + initial body, all in adds.
        diff = _diff("""
+id: I-3
+type: Initiative
+title: Audit UX simplification
+status: Funnel
+js: 8
""")
        weight, tags, _ = score_diff(diff, W)
        self.assertGreaterEqual(weight, W["yaml_edit:create"])
        self.assertIn("create", tags)

    def test_block_add_credits_per_top_level_block(self):
        # Two new top-level blocks added (both `key:` with empty value
        # signaling nested content follows).
        diff = _diff("""
+business_case:
+  customer: foo
+  problem: bar
+benefit_hypothesis_statement: |
+  We believe X will...
""")
        weight, tags, _ = score_diff(diff, W)
        # block_add fires for both; benefit_hypothesis_statement also
        # registers as scalar_change since it has an inline value.
        self.assertTrue(any(t.startswith("block_add") for t in tags))
        # Our heuristic counts the standalone scalar separately.
        self.assertGreater(weight, W["yaml_edit:block_add"])

    def test_list_grow_capped_at_10_per_commit(self):
        # 30 list items added → cap at 10.
        bullets = "\n".join(f"+- AC-{i}: criterion {i}" for i in range(1, 31))
        diff = _diff(bullets)
        weight, tags, _ = score_diff(diff, W)
        # Cap=10 → 10 × list_grow from list_grow alone (D-36: 10×0.5 = 5.0).
        list_grow_credit = 10 * W["yaml_edit:list_grow"]
        # Volume bonus for 30 net lines is min(cap, 30/divisor)
        # (D-36: min(1.0, 30/40) = 0.75).
        vol_bonus = min(W["yaml_edit:lines_volume_cap"],
                        30 / W["yaml_edit:lines_volume_divisor"])
        self.assertAlmostEqual(weight, list_grow_credit + vol_bonus, places=1)
        self.assertTrue(any("capped_from_30" in t for t in tags))

    def test_lines_volume_capped(self):
        # 1000-line diff → cap at 3.0.
        diff = ["+filler line " + str(i) for i in range(1000)]
        weight, _, _ = score_diff(diff, W)
        # No scalars, no blocks → bonus is purely lines_volume cap.
        self.assertLessEqual(weight, W["yaml_edit:lines_volume_cap"] + 0.01)

    def test_revert_negative_weight(self):
        # Pure removal commit (lots of - lines, no new id).
        removed = "\n".join(f"-old line {i}" for i in range(20))
        diff = _diff(removed)
        weight, tags, _ = score_diff(diff, W)
        self.assertLess(weight, 0)
        self.assertTrue(any(t.startswith("revert") for t in tags))

    def test_contributors_rebalance_removed(self):
        # D-26: contributors[] is a derived projection of evidence[], not an
        # input — editing it must NOT produce a contributors_rebalance signal.
        diff = _diff("""
+- person: tuma-ondrej
+  cw: 0.3
""")
        weight, tags, _ = score_diff(diff, W)
        self.assertFalse(any(t.startswith("contributors+") for t in tags))

    def test_pure_cw_shift_no_contributors_rebalance(self):
        # Same person, just cw value changed. Adds and removes the same
        # `- person:` line → set difference is empty → no rebalance signal.
        diff = _diff("""
-- person: turyna-martin
-  cw: 0.7
+- person: turyna-martin
+  cw: 0.6
""")
        weight, tags, _ = score_diff(diff, W)
        # No contributors+ tag (set diff empty)
        self.assertFalse(any(t.startswith("contributors+") for t in tags))

    def test_scalar_change_credits_per_field(self):
        # Two scalars set.
        diff = _diff("""
+js: 13
+bv: 8
""")
        weight, tags, _ = score_diff(diff, W)
        # 2 × scalar_change = 1.0
        self.assertAlmostEqual(weight, 2 * W["yaml_edit:scalar_change"], places=1)

    def test_combined_real_commit_yields_expected_weight(self):
        # Realistic commit: adds business_case block + 3 ACs + 2 NFRs
        # + scalar js field. Should add up to a substantive weight.
        diff = _diff("""
+business_case:
+  customer: auditor
+  problem: 4 UI surfaces
+  outcome: single pane
+- AC-1: timeline view
+- AC-2: filter sidebar
+- AC-3: detail panel
+- NFR-1: <2s first paint
+- NFR-2: WCAG 2.1 AA
+js: 8
""")
        weight, tags, _ = score_diff(diff, W)
        # D-36 weights: 1 block_add + 5 list_grow + 1 scalar (js)
        # + lines_volume bonus. Assert structurally against the weight set
        # so this test tracks future re-tunes instead of a frozen literal.
        base = (1 * W["yaml_edit:block_add"]
                + 5 * W["yaml_edit:list_grow"]
                + 1 * W["yaml_edit:scalar_change"])
        self.assertTrue(any(t.startswith("block_add") for t in tags))
        self.assertTrue(any(t.startswith("list_grow") for t in tags))
        # Weight is the structural base plus a small capped volume bonus.
        self.assertGreaterEqual(weight, base)
        self.assertLessEqual(
            weight, base + W["yaml_edit:lines_volume_cap"] + 0.01)
        # Sanity floor: a substantive multi-part edit clears a bare scalar.
        self.assertGreater(weight, W["yaml_edit:scalar_change"])


# ─── D-36 pegged-weight locks ────────────────────────────────────────────────


class TestPeggedWeights(unittest.TestCase):
    """Lock in the D-36 re-tune (pegged to commit_author=4.00).

    These assert the *exact* shipped weight set so an accidental revert of
    the re-tune (or drift between DEFAULT_WEIGHTS and the YAML configs)
    fails loudly rather than silently re-inflating yaml_edit credit.
    """

    def test_default_weights_are_d36_pegged_values(self):
        self.assertEqual(W["yaml_edit:create"], 2.0)
        self.assertEqual(W["yaml_edit:block_add"], 1.0)
        self.assertEqual(W["yaml_edit:list_grow"], 0.5)
        self.assertEqual(W["yaml_edit:scalar_change"], 0.25)
        self.assertEqual(W["yaml_edit:lines_volume_cap"], 1.0)
        self.assertEqual(W["yaml_edit:lines_volume_divisor"], 40)
        self.assertEqual(W["yaml_edit:revert"], -0.5)

    def test_contributors_rebalance_key_is_gone(self):
        # D-26 removed the consumer; D-36 removes the dead key everywhere.
        self.assertNotIn("yaml_edit:contributors_rebalance", W)

    def test_pure_create_scores_exactly_create_weight(self):
        # Minimal new-item diff (id+type+title only, no extra scalars/blocks
        # /bullets, <divisor lines so no volume bonus) → exactly create=2.0.
        diff = _diff("""
+id: D-99
+type: Defect
+title: x
""")
        weight, tags, _ = score_diff(diff, W)
        self.assertIn("create", tags)
        self.assertEqual(weight, W["yaml_edit:create"])  # exactly 2.0

    def test_default_weights_match_shipped_yaml_configs(self):
        # The three lockstep surfaces (DEFAULT_WEIGHTS, live config, template)
        # must agree on every yaml_edit weight. Reads the real files.
        import yaml as _yaml
        for rel in (".edpa/config/cw_heuristics.yaml",
                    "plugin/edpa/templates/cw_heuristics.yaml.tmpl"):
            data = _yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))
            ye = data["yaml_edit_weights"]
            for key in ("yaml_edit:create", "yaml_edit:block_add",
                        "yaml_edit:list_grow", "yaml_edit:scalar_change",
                        "yaml_edit:lines_volume_cap",
                        "yaml_edit:lines_volume_divisor", "yaml_edit:revert"):
                self.assertEqual(
                    ye[key], W[key],
                    msg=f"{rel}:{key} = {ye[key]} != DEFAULT_WEIGHTS {W[key]}")
            # Dead key must not reappear in any config.
            self.assertNotIn("yaml_edit:contributors_rebalance", ye, msg=rel)
            # bulk_item_threshold must be present in both (config + template).
            self.assertEqual(ye["bulk_item_threshold"], 5, msg=rel)


# ─── Integration test with real git repo ────────────────────────────────────


class TestCollectIntegration(unittest.TestCase):
    """End-to-end: build a tiny git repo, make commits, run collector."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="edpa_yaml_edit_test_"))
        self.repo = self.tmpdir / "repo"
        self.edpa = self.repo / ".edpa"
        (self.edpa / "backlog/initiatives").mkdir(parents=True)
        (self.edpa / "backlog/features").mkdir(parents=True)
        (self.edpa / "backlog/stories").mkdir(parents=True)
        (self.edpa / "backlog/defects").mkdir(parents=True)
        (self.edpa / "iterations").mkdir(parents=True)
        (self.edpa / "config").mkdir(parents=True)

        # Iteration window
        (self.edpa / "iterations/PI-2026-1.1.yaml").write_text(yaml.safe_dump({
            "iteration": {
                "id": "PI-2026-1.1",
                "start_date": "2026-05-11",
                "end_date": "2026-05-17",
            }
        }))
        # People mapping
        (self.edpa / "config/people.yaml").write_text(yaml.safe_dump({
            "people": [
                {"id": "alice", "github": "alice-gh",
                 "email": "alice@example.com"},
                {"id": "bob", "github": "bob-gh",
                 "email": "bob@example.com"},
            ]
        }))

        # Init git
        self._run("git init -q", cwd=self.repo)
        self._run("git config user.email tester@example.com", cwd=self.repo)
        self._run("git config user.name Tester", cwd=self.repo)
        # Initial empty commit so log isn't empty
        self._run("git add .", cwd=self.repo)
        self._commit("initial", "alice@example.com",
                     "2026-05-12T09:00:00+00:00")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run(self, cmd, cwd=None, env=None):
        return subprocess.run(cmd, shell=True, cwd=cwd, env=env,
                              check=True, capture_output=True, text=True, encoding="utf-8")

    def _commit(self, msg, email, ts_iso, name="Test User"):
        env = {**os.environ,
               "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
               "GIT_AUTHOR_DATE": ts_iso,
               "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email,
               "GIT_COMMITTER_DATE": ts_iso}
        self._run(f'git commit -q --allow-empty -m "{msg}"',
                  cwd=self.repo, env=env)

    def _write_and_commit(self, rel_path: str, body: dict, msg: str,
                          email: str, ts_iso: str):
        f = self.repo / rel_path
        f.parent.mkdir(parents=True, exist_ok=True)
        if rel_path.endswith(".md"):
            from _md_frontmatter import save_md
            save_md(f, body, "")
        else:
            f.write_text(yaml.safe_dump(body, sort_keys=False))
        self._run(f"git add {rel_path}", cwd=self.repo)
        self._commit(msg, email, ts_iso)

    def test_create_signal_lands_for_alice(self):
        self._write_and_commit(
            ".edpa/backlog/initiatives/I-1.md",
            {"id": "I-1", "type": "Initiative",
             "title": "test init", "status": "Funnel"},
            "EDPA: I-1 created", "alice@example.com",
            "2026-05-13T10:00:00+00:00",
        )
        sigs = collect_yaml_edit_signals(self.edpa, "PI-2026-1.1")
        self.assertIn("I-1", sigs)
        i1 = sigs["I-1"]
        self.assertEqual(len(i1), 1)
        self.assertGreaterEqual(i1[0]["weight"], W["yaml_edit:create"])
        self.assertEqual(i1[0]["login"], "alice-gh")  # email → github

    def test_defect_in_tracked_dirs(self):
        # Bug A regression test: defects must produce signals.
        self._write_and_commit(
            ".edpa/backlog/defects/D-1.md",
            {"id": "D-1", "type": "Defect", "title": "bug", "status": "Done"},
            "EDPA: D-1 fixed", "bob@example.com",
            "2026-05-14T11:00:00+00:00",
        )
        sigs = collect_yaml_edit_signals(self.edpa, "PI-2026-1.1")
        self.assertIn("D-1", sigs)

    def test_outside_window_filtered(self):
        # Iter is 2026-05-11..17; commit at 2026-06-01 must be excluded.
        self._write_and_commit(
            ".edpa/backlog/initiatives/I-2.md",
            {"id": "I-2", "type": "Initiative", "title": "later",
             "status": "Funnel"},
            "EDPA: I-2 created", "alice@example.com",
            "2026-06-01T10:00:00+00:00",
        )
        sigs = collect_yaml_edit_signals(self.edpa, "PI-2026-1.1")
        self.assertNotIn("I-2", sigs)

    def test_bot_author_zero_weight(self):
        self._write_and_commit(
            ".edpa/backlog/features/F-1.md",
            {"id": "F-1", "type": "Feature", "title": "auto", "status": "Funnel"},
            "EDPA: F-1 created", "github-actions[bot]@noreply.example.com",
            "2026-05-13T12:00:00+00:00",
        )
        sigs = collect_yaml_edit_signals(self.edpa, "PI-2026-1.1")
        self.assertNotIn("F-1", sigs)

    def test_tool_commit_message_zero_weight(self):
        self._write_and_commit(
            ".edpa/backlog/features/F-2.md",
            {"id": "F-2", "type": "Feature", "title": "sync",
             "status": "Funnel"},
            "EDPA sync push: 1 created, 0 updated", "alice@example.com",
            "2026-05-13T13:00:00+00:00",
        )
        sigs = collect_yaml_edit_signals(self.edpa, "PI-2026-1.1")
        self.assertNotIn("F-2", sigs)

    def test_bulk_migration_discount(self):
        # Bulk rename commit produces credit reduced to 10% of normal.
        self._write_and_commit(
            ".edpa/backlog/stories/S-1.md",
            {"id": "S-1", "type": "Story", "title": "rename",
             "status": "Funnel"},
            "chore(rename): rr → rr_oe across all stories",
            "alice@example.com", "2026-05-14T09:00:00+00:00",
        )
        sigs = collect_yaml_edit_signals(self.edpa, "PI-2026-1.1")
        self.assertIn("S-1", sigs)
        # Create signal (D-36: 2.0) × bulk_migration_discount (0.1) ≈ 0.2.
        s1 = sigs["S-1"][0]
        self.assertLess(s1["weight"], 1.0)
        self.assertAlmostEqual(
            s1["weight"],
            round(s1["raw_weight"] * W["bulk_migration_discount"], 2),
            places=2,
        )
        self.assertIn("bulk_discount", s1["tags"])

    def test_chore_evidence_commit_not_scored(self):
        # D-26 anti-loop: materialization's own chore(evidence): follow-up
        # commit must never produce yaml_edit (else evidence writes self-credit).
        self._write_and_commit(
            ".edpa/backlog/stories/S-9.md",
            {"id": "S-9", "type": "Story", "title": "x", "status": "Funnel",
             "evidence": [{"type": "commit_author", "person": "alice",
                           "weight": 2.78, "ref": "commit/deadbee"}]},
            "chore(evidence): S-9 from deadbee", "alice@example.com",
            "2026-05-14T09:00:00+00:00",
        )
        sigs = collect_yaml_edit_signals(self.edpa, "PI-2026-1.1")
        self.assertNotIn("S-9", sigs)

    def test_bulk_by_item_count_discount(self):
        # D-26 variant-2: one commit touching > bulk_item_threshold (5) items
        # is bulk seeding/backfill → every yaml_edit it produced is discounted,
        # so the committer can't out-credit the real assignees.
        from _md_frontmatter import save_md
        for i in range(1, 7):  # 6 stories > threshold 5
            f = self.repo / f".edpa/backlog/stories/S-1{i}.md"
            save_md(f, {"id": f"S-1{i}", "type": "Story",
                        "title": f"s{i}", "status": "Funnel"}, "")
        self._run("git add .", cwd=self.repo)
        self._commit("seed initial backlog", "alice@example.com",
                     "2026-05-14T09:00:00+00:00")
        sigs = collect_yaml_edit_signals(self.edpa, "PI-2026-1.1")
        self.assertEqual(len(sigs), 6)
        for slist in sigs.values():
            s = slist[0]
            self.assertIn("bulk_items_discount", s["tags"])
            self.assertLess(s["weight"], s["raw_weight"])


if __name__ == "__main__":
    unittest.main()
