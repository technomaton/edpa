"""ID allocator for EDPA item types.

Two authorities, one entry point (``next_id``):

``local``   ``max(counter_file, fs_scan, clone high-water mark) + 1``. The
            tracked counter (``.edpa/config/id_counters.yaml``) is written
            atomically under a file lock. Since ADR-014 a second lock and a
            high-water mark live in the git common dir, so every worktree
            of one clone draws from the same sequence. Other clones and
            other people are still not coordinated — that is what the
            remote authority is for.

``remote``  The number is reserved on the shared git remote first
            (``_id_ledger``: compare-and-swap on ``refs/edpa/ids``), so it
            is unique across worktrees, branches, clones and developers
            the moment it is returned. The tracked counter is no longer
            the authority and is not rewritten (see ``_mirror_legacy``).

Which one applies is resolved per clone — see ``resolve_authority``.

Counter file layout (``.edpa/config/id_counters.yaml``)::

    counters:
      Defect: 9
      Epic: 12
      Event: 3
      Feature: 34
      Initiative: 5
      Risk: 2
      Story: 78

See ``docs/v2/decisions.md`` ADR-014 and ``docs/dev-collisions.md``.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml
try:
    from filelock import FileLock, Timeout
except ImportError:
    # filelock not installed (e.g. a fresh Windows box where the one-time
    # dependency install was skipped). Fall back to a pure-stdlib lock so ID
    # allocation still works instead of crashing the bootstrap with
    # ModuleNotFoundError. The fallback preserves the cross-process
    # mutual-exclusion contract; see _fallback_lock for its limitations.
    from _fallback_lock import FileLock, Timeout

# ─── Canonical type metadata (Krok 2) ───────────────────────────────────────
# Single source of truth for the item-type → backlog-directory / ID-prefix
# mapping. backlog.py, mcp_server.py, local_evidence.py, detect_contributors,
# sync_pr_contributions, validate_syntax, engine, and _people_loader import
# these tables instead of re-declaring them; tests/test_type_dirs.py fails
# the build if a consumer carries a drifted copy (D-52).

# Create surface: the types the allocator / CLI / MCP create tools support.
TYPE_DIRS = {
    "Initiative": "initiatives",
    "Epic":       "epics",
    "Feature":    "features",
    "Story":      "stories",
    "Defect":     "defects",
    "Event":      "events",
    "Risk":       "risks",
}

TYPE_PREFIX = {
    "Initiative": "I",
    "Epic":       "E",
    "Feature":    "F",
    "Story":      "S",
    "Defect":     "D",
    "Event":      "EV",
    "Risk":       "R",
}

# Legacy read-only surface: migrated projects may hold Task items under
# backlog/tasks/ (first-class read support since D-3/D-46). Tasks stay
# readable, filterable, updatable, and schema-validated everywhere, but are
# never creatable (no allocator/CLI/MCP entry above) and never engine-credited
# (see ENGINE_CREDIT_DIRS below).
LEGACY_TYPE_DIRS = {"Task": "tasks"}
LEGACY_TYPE_PREFIX = {"Task": "T"}

# Read surface: every type/dir/prefix a loader may encounter (create + legacy).
ALL_TYPE_DIRS = {**TYPE_DIRS, **LEGACY_TYPE_DIRS}
ALL_TYPE_PREFIX = {**TYPE_PREFIX, **LEGACY_TYPE_PREFIX}
DIR_TO_TYPE = {d: t for t, d in ALL_TYPE_DIRS.items()}
PREFIX_TO_DIR = {p: ALL_TYPE_DIRS[t] for t, p in ALL_TYPE_PREFIX.items()}

# Named scope subsets — deliberate divergences from the full read surface,
# derived here from the canonical tables so they cannot drift as inline
# literals in consumer modules.
#
# Engine credit scope (engine.load_backlog_items): Events and Risks are
# PI-planning artefacts and deliberately earn no engine credit (see
# CHANGELOG); Tasks are legacy read-only and never engine-loaded.
ENGINE_CREDIT_DIRS = {
    TYPE_DIRS[t]: t for t in ("Story", "Feature", "Epic", "Initiative",
                              "Defect")
}
# Gate-event scope: parent levels credited via status-transition gate events.
GATE_TYPE_DIRS = {t: TYPE_DIRS[t] for t in ("Feature", "Epic", "Initiative")}

_COUNTER_REL = Path(".edpa/config/id_counters.yaml")
_LOCK_REL = Path(".edpa/.id_counter.lock")
_LOCK_TIMEOUT_SEC = 5

# Coarse per-project backlog write lock (D-52) — see backlog_write_lock().
_BACKLOG_LOCK_NAME = ".backlog.lock"
BACKLOG_LOCK_TIMEOUT_SEC = 5


class IdCounterError(Exception):
    """Raised when the ID counter is in an unrecoverable state."""


class BacklogLockTimeout(TimeoutError):
    """Raised when the per-project backlog write lock cannot be acquired.

    Callers degrade explicitly and loudly — the MCP server returns an
    ERROR result, the post-commit evidence emitter prints a stderr note
    and leaves catch-up to ``--materialize`` — instead of proceeding
    unlocked (silent lost updates) or hanging forever.
    """


@contextlib.contextmanager
def backlog_write_lock(edpa_root: Path | str,
                       timeout: "float | None" = None):
    """One coarse per-project mutex for backlog item read-modify-write cycles.

    ``_md_frontmatter.save_md`` writes are atomic (tempfile + os.replace),
    which prevents torn files but not lost updates: two writers that
    interleave load → mutate → save silently drop one side's changes. The
    long-running MCP server and the git post-commit evidence emitter are a
    real single-machine multi-writer pairing, so both wrap their cycles in
    this lock (``.edpa/.backlog.lock``).

    Rules for critical sections:
      * lock ONLY the load → mutate → save cycle — never git calls or other
        long work, so hold times stay in the milliseconds;
      * the lock is NOT reentrant — never call another locked section from
        inside one (the only sanctioned nesting is the ID-counter lock,
        which next_id takes as a strict leaf).

    Raises :class:`BacklogLockTimeout` with a clear message when the lock
    cannot be acquired within ``timeout`` seconds (default
    ``BACKLOG_LOCK_TIMEOUT_SEC``; the module constant is read at call time
    so tests can shrink it).
    """
    if timeout is None:
        timeout = BACKLOG_LOCK_TIMEOUT_SEC
    lock_path = Path(edpa_root) / _BACKLOG_LOCK_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(lock_path), timeout=timeout)
    try:
        lock.acquire()
    except Timeout as e:
        raise BacklogLockTimeout(
            f"could not acquire backlog write lock {lock_path} within "
            f"{timeout}s — another EDPA process is writing backlog items "
            f"(retry; if no other process is running, delete the stale "
            f"lock file)"
        ) from e
    try:
        yield
    finally:
        lock.release()


def _read_counter(counter_path: Path, item_type: str) -> int:
    if not counter_path.exists():
        return 0
    try:
        data = yaml.safe_load(counter_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise IdCounterError(f"Cannot parse {counter_path}: {e}") from e
    return int((data.get("counters") or {}).get(item_type, 0))


def _scan_fs_max(backlog_dir: Path, item_type: str) -> int:
    if not backlog_dir.exists():
        return 0
    pattern = re.compile(rf"^{re.escape(TYPE_PREFIX[item_type])}-(\d+)$")
    max_num = 0
    for f in backlog_dir.glob("*.md"):
        m = pattern.match(f.stem)
        if m:
            num = int(m.group(1))
            if num > max_num:
                max_num = num
    return max_num


def _write_counter_atomic(counter_path: Path, item_type: str, value: int) -> None:
    counter_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if counter_path.exists():
        try:
            data = yaml.safe_load(counter_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            raise IdCounterError(f"Cannot parse {counter_path}: {e}") from e
    counters = data.get("counters") or {}
    counters[item_type] = value
    data["counters"] = counters

    fd, tmp_path = tempfile.mkstemp(
        suffix=".yaml",
        prefix=".id_counters_",
        dir=str(counter_path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=True, default_flow_style=False)
        os.replace(tmp_path, counter_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ─── Per-clone state (ADR-014) ──────────────────────────────────────────────
# Lives in the git common dir, which every worktree of a clone shares and
# which is never part of a checkout — no untracked files, no .gitignore.

_STATE_DIRNAME = "edpa"
_STATE_LOCK_NAME = "id.lock"          # guards the high-water mark file
_HWM_NAME = "id_hwm.yaml"             # same layout as id_counters.yaml
_TURNSTILE_NAME = "id-net.lock"       # advisory, held across the network
_TURNSTILE_WAIT_SEC = 45

AUTHORITY_ENV = "EDPA_ID_AUTHORITY"
DEFAULT_LEDGER_REMOTE = "origin"
DEFAULT_LEDGER_REF = "refs/edpa/ids"


def _git_out(root: Path | str, *args: str, stdin: str | None = None) -> str | None:
    """stdout of a quick local git query, or ``None`` when there is nothing
    usable: not a repository, git missing, or — in tests that stub
    ``subprocess.run`` — an empty fake answer. Never raises."""
    try:
        r = subprocess.run(
            ["git", *args], cwd=str(root), capture_output=True, text=True,
            encoding="utf-8", check=False,
            **({"input": stdin} if stdin is not None
               else {"stdin": subprocess.DEVNULL}),
        )
    except (OSError, ValueError):
        return None
    out = getattr(r, "stdout", None)
    if getattr(r, "returncode", 1) != 0 or not isinstance(out, str):
        return None
    return out if out.strip() else None


def _git_layout(root: Path | str) -> tuple[Path, str] | None:
    """``(git common dir, path of root inside its worktree)`` — or ``None``
    outside a git repository."""
    out = _git_out(root, "rev-parse", "--git-common-dir", "--show-prefix")
    if out is None:
        return None
    lines = out.splitlines()
    common = Path(lines[0].strip())
    if not common.is_absolute():
        common = Path(root) / common
    prefix = lines[1].strip().strip("/") if len(lines) > 1 else ""
    return common.resolve(), prefix


def _state_dir(root: Path | str) -> Path | None:
    """Allocator state shared by all worktrees of this clone, or ``None``
    outside git (then only the legacy per-tree lock and counter apply)."""
    layout = _git_layout(root)
    if layout is None:
        return None
    common, prefix = layout
    state = common / _STATE_DIRNAME
    if prefix:          # an .edpa/ project nested inside a larger repository
        state = state / ("sub-" + hashlib.sha1(prefix.encode()).hexdigest()[:12])
    return state


@contextlib.contextmanager
def _state_lock(state: Path | None):
    if state is None:
        yield
        return
    state.mkdir(parents=True, exist_ok=True)
    lock_path = state / _STATE_LOCK_NAME
    try:
        with FileLock(str(lock_path), timeout=_LOCK_TIMEOUT_SEC):
            yield
    except Timeout as e:
        raise IdCounterError(
            f"Could not acquire {lock_path} within {_LOCK_TIMEOUT_SEC}s"
        ) from e


@contextlib.contextmanager
def _turnstile(state: Path):
    """Queue sibling worktrees through the network phase one at a time.

    Advisory only: the remote arbitrates the winner, so a timeout here
    just means proceeding and possibly retrying a lost race. That is also
    why the microsecond locks above are never held across a network call —
    a queue of agents would run them into their 5 s timeout.
    """
    state.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(state / _TURNSTILE_NAME), timeout=_TURNSTILE_WAIT_SEC)
    try:
        lock.acquire()
        held = True
    except Timeout:
        held = False
    try:
        yield
    finally:
        if held:
            lock.release()


def _safe_counter(path: Path, item_type: str) -> int:
    try:
        return _read_counter(path, item_type)
    except (IdCounterError, OSError, ValueError, TypeError):
        return 0


def _checkout_max(project_root: Path) -> dict[str, int]:
    """Highest number per type one checkout holds: item files (committed
    or not) and its tracked counter."""
    backlog = project_root / ".edpa" / "backlog"
    counter = project_root / _COUNTER_REL
    return {
        t: max(_scan_fs_max(backlog / d, t), _safe_counter(counter, t))
        for t, d in TYPE_DIRS.items()
    }


def _merge_max(*maps: dict[str, int]) -> dict[str, int]:
    out = {t: 0 for t in TYPE_DIRS}
    for m in maps:
        for k, v in m.items():
            if k in out and int(v) > out[k]:
                out[k] = int(v)
    return out


_TREE_ITEM_RE = re.compile(r"^([^/]+)/([A-Z]{1,3})-(\d{1,9})\.md$")


def _refs_max(root: Path, prefix: str, namespaces: tuple[str, ...]) -> dict[str, int]:
    """Highest number per type at the tip of every ref in ``namespaces``.

    Branch tips mostly share one backlog tree and one counter blob, so
    they are resolved in a single batch and each distinct object is read
    once — dozens of branches cost a handful of git calls.
    """
    listing = _git_out(root, "for-each-ref", "--format=%(objectname)",
                       *namespaces)
    commits = sorted(set((listing or "").split()))
    if not commits:
        return {}
    base = f"{prefix}/" if prefix else ""

    def distinct(path: str, kind: str) -> set[str]:
        out = _git_out(
            root, "cat-file", "--batch-check=%(objectname) %(objecttype)",
            stdin="".join(f"{c}:{base}{path}\n" for c in commits))
        return {ln.split()[0] for ln in (out or "").splitlines()
                if ln.endswith(f" {kind}")}

    found: dict[str, int] = {}
    for tree in distinct(".edpa/backlog", "tree"):
        for name in (_git_out(root, "ls-tree", "-r", "--name-only", tree)
                     or "").splitlines():
            m = _TREE_ITEM_RE.match(name)
            if not m:
                continue
            item_type = DIR_TO_TYPE.get(m.group(1))
            if item_type in TYPE_PREFIX and TYPE_PREFIX[item_type] == m.group(2):
                found[item_type] = max(found.get(item_type, 0), int(m.group(3)))
    for blob in distinct(_COUNTER_REL.as_posix(), "blob"):
        try:
            data = yaml.safe_load(_git_out(root, "cat-file", "-p", blob) or "") or {}
            for k, v in (data.get("counters") or {}).items():
                if k in TYPE_DIRS and isinstance(v, int) and v > found.get(k, 0):
                    found[k] = v
        except (yaml.YAMLError, AttributeError):
            continue
    return found


def scan_known_max(root: Path | str,
                   ref_namespaces: tuple[str, ...] = ("refs/heads", "refs/remotes"),
                   ) -> dict[str, int]:
    """Highest ID number per type this clone can see anywhere: every
    worktree's files and tracked counter, and the tip of every local and
    remote-tracking branch. Offline — fetch first for a fuller picture.
    """
    root = Path(root)
    layout = _git_layout(root)
    if layout is None:
        return _merge_max(_checkout_max(root))
    _common, prefix = layout
    maps = [_checkout_max(root)]
    for line in (_git_out(root, "worktree", "list", "--porcelain") or "").splitlines():
        if line.startswith("worktree "):
            other = Path(line[len("worktree "):]) / prefix
            if (other / ".edpa").is_dir():
                maps.append(_checkout_max(other))
    maps.append(_refs_max(root, prefix, ref_namespaces))
    return _merge_max(*maps)


def _hwm_path(state: Path) -> Path:
    return state / _HWM_NAME


def _ensure_hwm(state: Path, root: Path) -> None:
    """First use in this clone: seed the shared high-water mark from every
    worktree and branch, so the first allocation after an upgrade cannot
    repeat a number another worktree already holds unmerged."""
    path = _hwm_path(state)
    if path.exists():
        return
    seed = scan_known_max(root)          # outside the lock: may take a moment
    with _state_lock(state):
        if not path.exists():
            _write_map_atomic(path, seed)


def _write_map_atomic(path: Path, counters: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix=".yaml", prefix=f".{path.stem}_",
                                    dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump({"counters": dict(counters)}, f,
                           sort_keys=True, default_flow_style=False)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _bump_hwm(state: Path, item_type: str, value: int) -> None:
    """Raise the shared high-water mark (caller holds the state lock)."""
    path = _hwm_path(state)
    if value > _safe_counter(path, item_type):
        _write_counter_atomic(path, item_type, value)


# ─── Allocation authority ───────────────────────────────────────────────────

@dataclass(frozen=True)
class Authority:
    mode: str        # "local" | "remote"
    remote: str
    ref: str
    source: str      # "env" | "config" | "discovered" | "default"


def _ledger():
    """Import ``_id_ledger`` lazily: id_counter must stay importable on its
    own (tools that vendor just this file keep working in local mode)."""
    try:
        import _id_ledger
    except ImportError:
        here = str(Path(__file__).resolve().parent)
        if here not in sys.path:
            sys.path.insert(0, here)
        try:
            import _id_ledger
        except ImportError:
            return None
    return _id_ledger


def _ids_config(root: Path) -> dict:
    path = root / ".edpa" / "config" / "edpa.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    ids = data.get("ids") if isinstance(data, dict) else None
    return ids if isinstance(ids, dict) else {}


def resolve_authority(root: Path | str) -> Authority:
    """Who hands out IDs for the project at ``root``.

    1. ``EDPA_ID_AUTHORITY=local|remote`` — explicit override.
    2. ``ids.authority: local|remote`` in the tracked ``edpa.yaml``.
    3. ``auto`` (the default): ``remote`` once this clone has seen an ID
       ledger, else ``local``.

    Step 3 is what makes a cut-over work: a tracked flag exists per
    branch, and worktrees cut before the opt-in commit do not have it —
    but they all share the clone's ledger cache, so they switch together.
    """
    root = Path(root)
    cfg = _ids_config(root)
    remote = str(cfg.get("remote") or DEFAULT_LEDGER_REMOTE)
    ref = str(cfg.get("ref") or DEFAULT_LEDGER_REF)
    env = os.environ.get(AUTHORITY_ENV, "").strip().lower()
    if env in ("local", "remote"):
        return Authority(env, remote, ref, "env")
    mode = str(cfg.get("authority") or "auto").strip().lower()
    if mode in ("local", "remote"):
        return Authority(mode, remote, ref, "config")
    if mode != "auto":
        raise IdCounterError(
            f"ids.authority must be auto, local or remote — got {mode!r}")
    ledger = _ledger()
    if ledger is not None and _git_layout(root) is not None:
        try:
            if ledger.known_locally(root):
                return Authority("remote", remote, ref, "discovered")
        except ledger.LedgerError:
            pass
    return Authority("local", remote, ref, "default")


def _mirror_legacy(root: Path, item_type: str, value: int) -> None:
    """Keep an OLD vendored pre-commit hook satisfied.

    Before ADR-014, ``validate_ids --staged`` demanded that the tracked
    counter grow with every new item. A worktree whose vendored engine
    predates the ledger still runs that check, so the reserved number is
    mirrored into its counter file. Everywhere else the file is left
    alone — that is what removes it as the hot-spot every parallel ticket
    branch used to conflict on.
    """
    engine = root / ".edpa" / "engine" / "scripts"
    counter_path = root / _COUNTER_REL
    if not (engine / "validate_ids.py").exists() \
            or (engine / "_id_ledger.py").exists() \
            or not counter_path.exists():
        return
    lock_path = root / _LOCK_REL
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # The legacy lock: an old allocator in this worktree takes it too.
        with FileLock(str(lock_path), timeout=_LOCK_TIMEOUT_SEC):
            if value > _safe_counter(counter_path, item_type):
                _write_counter_atomic(counter_path, item_type, value)
    except (Timeout, IdCounterError, OSError):
        pass        # the ID is already reserved; the mirror is a courtesy


def _next_id_local(item_type: str, root: Path) -> str:
    counter_path = root / _COUNTER_REL
    lock_path = root / _LOCK_REL
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    backlog_dir = root / ".edpa" / "backlog" / TYPE_DIRS[item_type]
    state = _state_dir(root)
    if state is not None:
        try:
            _ensure_hwm(state, root)
        except OSError:
            state = None    # common dir not writable: per-tree behaviour only

    with _state_lock(state):
        try:
            with FileLock(str(lock_path), timeout=_LOCK_TIMEOUT_SEC):
                counter_val = _read_counter(counter_path, item_type)
                fs_max = _scan_fs_max(backlog_dir, item_type)
                hwm = _safe_counter(_hwm_path(state), item_type) if state else 0
                next_num = max(counter_val, fs_max, hwm) + 1
                _write_counter_atomic(counter_path, item_type, next_num)
                if state is not None:
                    _bump_hwm(state, item_type, next_num)
                return f"{TYPE_PREFIX[item_type]}-{next_num}"
        except Timeout as e:
            raise IdCounterError(
                f"Could not acquire {lock_path} within {_LOCK_TIMEOUT_SEC}s"
            ) from e


def _remote_failure(ledger, exc: Exception, auth: Authority) -> IdCounterError:
    where = f"{auth.ref} on remote {auth.remote!r}"
    if isinstance(exc, ledger.LedgerMissing):
        text = (f"this project reserves IDs on the shared remote, but the ID "
                f"ledger ({where}) does not exist yet. Create it once per "
                f"repository: python3 .edpa/engine/scripts/id_counter.py "
                f"init-remote")
    elif isinstance(exc, ledger.LedgerUnavailable):
        text = (f"cannot reach the ID ledger ({where}). A ticket ID is only "
                f"reserved online — no ID was assigned and nothing was "
                f"written. Check the connection / git credentials and retry."
                f"\n{exc}")
    elif isinstance(exc, ledger.LedgerRejected):
        text = (f"the remote does not let this environment update the ID "
                f"ledger ({where}). Create the ticket from a clone that may "
                f"push there (a sandbox limited to its own branch cannot "
                f"reserve IDs).\n{exc}")
    else:
        text = f"could not reserve an ID in the ledger ({where}): {exc}"
    return IdCounterError(text)


def _next_id_remote(item_type: str, root: Path, auth: Authority,
                    meta: dict) -> str:
    ledger = _ledger()
    if ledger is None:
        raise IdCounterError(
            "remote ID authority is configured but _id_ledger.py is missing "
            "from this engine — update the EDPA plugin / re-vendor the engine")
    state = _state_dir(root)
    if state is None:
        raise IdCounterError(
            "remote ID authority needs a git repository with a remote")
    prefix = TYPE_PREFIX[item_type]
    floor = max(
        _scan_fs_max(root / ".edpa" / "backlog" / TYPE_DIRS[item_type], item_type),
        _safe_counter(root / _COUNTER_REL, item_type),
        _safe_counter(_hwm_path(state), item_type),
    )
    branch = (_git_out(root, "symbolic-ref", "--short", "-q", "HEAD") or "").strip()
    try:
        with _turnstile(state):
            res = ledger.reserve(
                root, item_type, prefix, floor=floor,
                remote=auth.remote, ref=auth.ref,
                title=meta.get("title"), parent=meta.get("parent"),
                branch=branch or None, created_at=meta.get("created_at"),
            )
    except ledger.LedgerError as e:
        raise _remote_failure(ledger, e, auth) from e
    number = res.numbers[0]
    for note in res.notes:
        print(f"id_counter: {note}", file=sys.stderr)
    with _state_lock(state):
        _bump_hwm(state, item_type, number)
    _mirror_legacy(root, item_type, number)
    return f"{prefix}-{number}"


def next_id(item_type: str, root: Path | str, *, meta: dict | None = None) -> str:
    """Reserve and return the next available ID for ``item_type``.

    Local authority::

        next = max(tracked counter, fs scan, clone high-water mark) + 1

    under the per-tree lock (``.edpa/.id_counter.lock``) and, inside a git
    repository, the per-clone lock — so neither two processes in one tree
    nor two worktrees of one clone can be handed the same number.

    Remote authority: the number comes from a compare-and-swap on the
    shared ledger and is unique across every clone. ``meta`` (``title``,
    ``parent``, ``created_at``) goes into the reservation record; the
    hooks later match a new item against it. Needs the network; fails
    with an actionable :class:`IdCounterError` instead of guessing.
    """
    if item_type not in TYPE_PREFIX:
        raise ValueError(f"Unknown item type: {item_type}")

    root = Path(root)
    auth = resolve_authority(root)
    if auth.mode == "remote":
        return _next_id_remote(item_type, root, auth, meta or {})
    return _next_id_local(item_type, root)


def seed_counters_from_fs(root: Path | str) -> dict[str, int]:
    """Raise ``counter[type]`` to at least ``max(fs_scan)`` — never lower it.

    Used by ``migrate_v1_to_v2.py`` to seed an ``id_counters.yaml`` for a
    project whose IDs were previously allocated by GitHub (no local
    counter file existed), by ``project_setup.py`` on every run, and as a
    recovery operation if the counter file is lost. A counter above the
    filesystem maximum is information (the highest item was deleted) and
    must survive a re-run, or its number would be handed out again.

    Returns the resulting ``{type: counter}`` map.
    """
    root = Path(root)
    counter_path = root / _COUNTER_REL
    lock_path = root / _LOCK_REL
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    backlog_root = root / ".edpa" / "backlog"

    try:
        with FileLock(str(lock_path), timeout=_LOCK_TIMEOUT_SEC):
            counters: dict[str, int] = {}
            for item_type, dir_name in TYPE_DIRS.items():
                counters[item_type] = max(
                    _scan_fs_max(backlog_root / dir_name, item_type),
                    _safe_counter(counter_path, item_type),
                )
            _write_map_atomic(counter_path, counters)
            return counters
    except Timeout as e:
        raise IdCounterError(
            f"Could not acquire {lock_path} within {_LOCK_TIMEOUT_SEC}s"
        ) from e
