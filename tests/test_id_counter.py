"""Tests for plugin/edpa/scripts/id_counter.py.

Covers the local-first ID allocation contract: counter file + fs_scan
take the max, the counter file is bumped atomically, a file lock keeps
concurrent processes from racing, and unknown types / corrupted YAML
fail loudly.
"""

from __future__ import annotations

import multiprocessing as mp
import sys
import threading
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import id_counter
from id_counter import IdCounterError, TYPE_DIRS, next_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_repo(tmp_path: Path) -> Path:
    """Empty .edpa/ structure with no counter and no backlog items."""
    (tmp_path / ".edpa" / "config").mkdir(parents=True)
    (tmp_path / ".edpa" / "backlog").mkdir(parents=True)
    for d in TYPE_DIRS.values():
        (tmp_path / ".edpa" / "backlog" / d).mkdir()
    return tmp_path


def _write_counter(root: Path, counters: dict) -> None:
    path = root / ".edpa" / "config" / "id_counters.yaml"
    path.write_text(yaml.safe_dump({"counters": counters}, sort_keys=True))


def _make_item(root: Path, item_type: str, num: int) -> None:
    prefix = id_counter.TYPE_PREFIX[item_type]
    d = root / ".edpa" / "backlog" / TYPE_DIRS[item_type]
    (d / f"{prefix}-{num}.md").write_text(f"---\nid: {prefix}-{num}\n---\n")


# ---------------------------------------------------------------------------
# Basic allocation
# ---------------------------------------------------------------------------

def test_empty_repo_starts_at_one(fresh_repo: Path) -> None:
    assert next_id("Story", fresh_repo) == "S-1"


def test_counter_only_no_fs(fresh_repo: Path) -> None:
    _write_counter(fresh_repo, {"Story": 5})
    assert next_id("Story", fresh_repo) == "S-6"


def test_fs_only_no_counter(fresh_repo: Path) -> None:
    _make_item(fresh_repo, "Story", 3)
    assert next_id("Story", fresh_repo) == "S-4"


def test_counter_greater_than_fs_wins(fresh_repo: Path) -> None:
    _write_counter(fresh_repo, {"Story": 10})
    _make_item(fresh_repo, "Story", 3)
    assert next_id("Story", fresh_repo) == "S-11"


def test_fs_greater_than_counter_wins(fresh_repo: Path) -> None:
    """Manual filesystem edit must be detected (Layer 1 in plan.md)."""
    _write_counter(fresh_repo, {"Story": 3})
    _make_item(fresh_repo, "Story", 10)
    assert next_id("Story", fresh_repo) == "S-11"


def test_counter_bumped_after_allocation(fresh_repo: Path) -> None:
    next_id("Story", fresh_repo)
    data = yaml.safe_load((fresh_repo / ".edpa/config/id_counters.yaml").read_text())
    assert data["counters"]["Story"] == 1
    next_id("Story", fresh_repo)
    data = yaml.safe_load((fresh_repo / ".edpa/config/id_counters.yaml").read_text())
    assert data["counters"]["Story"] == 2


def test_per_type_counters_independent(fresh_repo: Path) -> None:
    assert next_id("Story", fresh_repo) == "S-1"
    assert next_id("Epic", fresh_repo) == "E-1"
    assert next_id("Story", fresh_repo) == "S-2"
    assert next_id("Risk", fresh_repo) == "R-1"


def test_all_known_types_allocate(fresh_repo: Path) -> None:
    for item_type, prefix in id_counter.TYPE_PREFIX.items():
        assert next_id(item_type, fresh_repo) == f"{prefix}-1"


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------

def test_unknown_type_raises(fresh_repo: Path) -> None:
    with pytest.raises(ValueError, match="Unknown item type"):
        next_id("Saga", fresh_repo)


def test_corrupted_counter_yaml_raises(fresh_repo: Path) -> None:
    (fresh_repo / ".edpa/config/id_counters.yaml").write_text(
        "counters: {Story: 5\n  not valid yaml here"
    )
    with pytest.raises(IdCounterError, match="Cannot parse"):
        next_id("Story", fresh_repo)


def test_no_tmp_files_left_behind(fresh_repo: Path) -> None:
    next_id("Story", fresh_repo)
    leftovers = list((fresh_repo / ".edpa" / "config").glob(".id_counters_*"))
    assert leftovers == []


def test_counter_file_is_yaml_dict_with_counters_key(fresh_repo: Path) -> None:
    next_id("Story", fresh_repo)
    data = yaml.safe_load((fresh_repo / ".edpa/config/id_counters.yaml").read_text())
    assert isinstance(data, dict)
    assert "counters" in data
    assert isinstance(data["counters"], dict)


# ---------------------------------------------------------------------------
# fs_scan edge cases
# ---------------------------------------------------------------------------

def test_fs_scan_ignores_wrong_prefix(fresh_repo: Path) -> None:
    _make_item(fresh_repo, "Story", 5)
    # Drop a junk file with a wrong prefix into the stories dir.
    (fresh_repo / ".edpa/backlog/stories/JUNK-99.md").write_text("---\n---\n")
    assert next_id("Story", fresh_repo) == "S-6"


def test_fs_scan_ignores_non_md_files(fresh_repo: Path) -> None:
    _make_item(fresh_repo, "Story", 5)
    (fresh_repo / ".edpa/backlog/stories/S-10.txt").write_text("S-10 in wrong ext")
    assert next_id("Story", fresh_repo) == "S-6"


def test_fs_scan_ignores_non_integer_suffix(fresh_repo: Path) -> None:
    _make_item(fresh_repo, "Story", 5)
    (fresh_repo / ".edpa/backlog/stories/S-foo.md").write_text("---\n---\n")
    assert next_id("Story", fresh_repo) == "S-6"


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------

def _worker_allocate(root_str: str, item_type: str, n: int) -> list[str]:
    """Worker for multi-process concurrency test (must be top-level for pickling)."""
    # Each child process has to re-import after spawn.
    sys.path.insert(0, str(Path(root_str).parent / "plugin" / "edpa" / "scripts"))
    import id_counter as ic  # noqa: F811
    return [ic.next_id(item_type, Path(root_str)) for _ in range(n)]


def test_threads_get_unique_ids(fresh_repo: Path) -> None:
    """20 threads × 5 allocations → 100 unique IDs, no collision."""
    results: list[list[str]] = [[] for _ in range(20)]

    def run(idx: int) -> None:
        for _ in range(5):
            results[idx].append(next_id("Story", fresh_repo))

    threads = [threading.Thread(target=run, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    flat = [x for sub in results for x in sub]
    assert len(flat) == 100
    assert len(set(flat)) == 100, "duplicate IDs allocated under thread contention"

    nums = sorted(int(x.split("-")[1]) for x in flat)
    assert nums == list(range(1, 101))


def test_processes_get_unique_ids(fresh_repo: Path, tmp_path: Path) -> None:
    """4 processes × 10 allocations → 40 unique IDs.

    Uses ``fork`` start method to inherit sys.path; falls back to a
    skip if the platform default is spawn-only (we still cover the
    threaded case above).
    """
    ctx = mp.get_context("fork") if "fork" in mp.get_all_start_methods() else None
    if ctx is None:
        pytest.skip("fork start method unavailable on this platform")

    with ctx.Pool(4) as pool:
        chunks = pool.starmap(
            _worker_allocate,
            [(str(fresh_repo), "Story", 10)] * 4,
        )
    flat = [x for chunk in chunks for x in chunk]
    assert len(flat) == 40
    assert len(set(flat)) == 40, "duplicate IDs allocated under process contention"
