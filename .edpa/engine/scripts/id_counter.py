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
_POOL_NAME = "id_pool.yaml"           # numbers reserved ahead for offline use

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


# ─── Pre-reserved numbers (offline use) ─────────────────────────────────────
# Reserve-then-use can never diverge from the ledger; use-then-reserve is
# exactly how V1's --local fallback produced two ID series. So the only
# offline path is a block reserved while online and consumed later.

def _read_pool(state: Path) -> dict[str, list[int]]:
    try:
        data = yaml.safe_load((state / _POOL_NAME).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    pool = data.get("pool") if isinstance(data, dict) else None
    if not isinstance(pool, dict):
        return {}
    return {str(k): sorted(int(n) for n in v if isinstance(n, int))
            for k, v in pool.items() if isinstance(v, list)}


def _write_pool(state: Path, pool: dict[str, list[int]]) -> None:
    path = state / _POOL_NAME
    fd, tmp_path = tempfile.mkstemp(suffix=".yaml", prefix=".id_pool_",
                                    dir=str(state))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump({"pool": {k: v for k, v in sorted(pool.items()) if v}},
                           f, sort_keys=True, default_flow_style=False)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _pool_take(state: Path, item_type: str) -> int | None:
    with _state_lock(state):
        pool = _read_pool(state)
        numbers = pool.get(item_type) or []
        if not numbers:
            return None
        number = numbers.pop(0)
        pool[item_type] = numbers
        _write_pool(state, pool)
        return number


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


def _ids_block(text: str | None) -> dict:
    try:
        data = yaml.safe_load(text or "") or {}
    except yaml.YAMLError:
        return {}
    ids = data.get("ids") if isinstance(data, dict) else None
    return ids if isinstance(ids, dict) else {}


def _ids_config(root: Path) -> dict:
    path = root / ".edpa" / "config" / "edpa.yaml"
    try:
        return _ids_block(path.read_text(encoding="utf-8"))
    except OSError:
        return {}


def _target_ids_config(root: Path, remote: str) -> dict:
    """The ``ids:`` block of edpa.yaml on the remote's integration branch,
    as of the last fetch (no network). This is how a clone learns that the
    project opted in before it has merged the opt-in commit anywhere."""
    layout = _git_layout(root)
    if layout is None or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", remote):
        return {}
    _common, prefix = layout
    path = (f"{prefix}/" if prefix else "") + ".edpa/config/edpa.yaml"
    for branch in ("HEAD", "main", "master"):
        text = _git_out(root, "show", f"refs/remotes/{remote}/{branch}:{path}")
        if text is not None:
            return _ids_block(text)
    return {}


def resolve_authority(root: Path | str) -> Authority:
    """Who hands out IDs for the project at ``root``.

    1. ``EDPA_ID_AUTHORITY=local|remote`` — explicit override.
    2. ``ids.authority: local|remote`` in the tracked ``edpa.yaml`` of
       this checkout.
    3. ``auto`` (the default): ``remote`` once this clone has seen an ID
       ledger, or once the remote's integration branch opted in (as of
       the last fetch); else ``local``.

    Step 3 is what makes a cut-over work. A tracked flag exists per
    branch, and worktrees cut before the opt-in commit do not have it —
    but they share the clone's ledger cache and its remote-tracking refs,
    so they all switch as soon as one of them reserves an ID or the clone
    fetches the opt-in commit.
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
        target = _target_ids_config(root, remote)
        try:
            if ledger.known_locally(root):
                # Where the ledger lives: this checkout's config if it says,
                # else the integration branch's, else where this clone last
                # reached it — never blindly the default (a custom-ref
                # project must not grow a second ledger at refs/edpa/ids).
                seen = ledger.remembered(root) or (remote, ref)
                return Authority(
                    "remote",
                    str(cfg.get("remote") or target.get("remote") or seen[0]),
                    str(cfg.get("ref") or target.get("ref") or seen[1]),
                    "discovered")
        except ledger.LedgerError:
            pass
        if str(target.get("authority") or "").strip().lower() == "remote":
            return Authority("remote", str(target.get("remote") or remote),
                             str(target.get("ref") or ref), "discovered")
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
                f"written. Check the connection / git credentials and retry "
                f"(to work offline, reserve a block beforehand: "
                f"id_counter.py reserve --type <Type> --count N)."
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
    except ledger.LedgerUnavailable as e:
        number = _pool_take(state, item_type)
        if number is None:
            raise _remote_failure(ledger, e, auth) from e
        left = len(_read_pool(state).get(item_type) or [])
        print(f"id_counter: remote unreachable — using pre-reserved "
              f"{prefix}-{number} ({left} left for {item_type})", file=sys.stderr)
        with _state_lock(state):
            _bump_hwm(state, item_type, number)
        _mirror_legacy(root, item_type, number)
        return f"{prefix}-{number}"
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


# ─── CLI ────────────────────────────────────────────────────────────────────

def _find_project_root(start: Path) -> Path | None:
    p = start.resolve()
    for candidate in (p, *p.parents):
        if (candidate / ".edpa").is_dir():
            return candidate
    return None


def _require_ledger():
    ledger = _ledger()
    if ledger is None:
        raise IdCounterError(
            "_id_ledger.py is missing from this engine — update the EDPA "
            "plugin / re-vendor the engine")
    return ledger


def reserve_block(item_type: str, root: Path | str, count: int) -> list[str]:
    """Reserve ``count`` IDs now and keep them in this clone's pool; they
    are handed out by ``next_id`` only when the remote is unreachable."""
    if item_type not in TYPE_PREFIX:
        raise ValueError(f"Unknown item type: {item_type}")
    root = Path(root)
    auth = resolve_authority(root)
    if auth.mode != "remote":
        raise IdCounterError(
            "a block can only be pre-reserved under the remote ID authority "
            "(the local counter needs no network to begin with)")
    ledger = _require_ledger()
    state = _state_dir(root)
    if state is None:
        raise IdCounterError("remote ID authority needs a git repository")
    prefix = TYPE_PREFIX[item_type]
    floor = max(
        _scan_fs_max(root / ".edpa" / "backlog" / TYPE_DIRS[item_type], item_type),
        _safe_counter(root / _COUNTER_REL, item_type),
        _safe_counter(_hwm_path(state), item_type),
    )
    try:
        with _turnstile(state):
            res = ledger.reserve(root, item_type, prefix, floor=floor,
                                 count=count, remote=auth.remote, ref=auth.ref)
    except ledger.LedgerError as e:
        raise _remote_failure(ledger, e, auth) from e
    with _state_lock(state):
        pool = _read_pool(state)
        pool[item_type] = sorted(set(pool.get(item_type, [])) | set(res.numbers))
        _write_pool(state, pool)
        _bump_hwm(state, item_type, res.numbers[-1])
    return [f"{prefix}-{n}" for n in res.numbers]


def init_remote(root: Path | str, *, headroom: int = 0, fetch: bool = True,
                remote: str | None = None, ref: str | None = None) -> dict:
    """Plan the bootstrap of the ID ledger: per-type floors this clone can
    prove (plus optional headroom). Returns the plan; ``apply_init_remote`` writes it.

    The floor is the highest number that may exist without a reservation
    record. It has to cover every pre-ledger item anywhere — so all remote
    branches are fetched into a private namespace first (a single-branch
    or shallow clone sees them too).

    By default there is no headroom: numbering simply continues, without
    gaps. That requires everyone to be on a ledger-aware plugin before
    the cut-over — a session still minting from an outdated allocator
    gets a number the ledger hands to someone else, and is stopped by the
    hooks. ``headroom`` > 0 leaves numbers free for such stragglers.

    ``headroom`` is the most any type gets; a type receives about a tenth
    of its current size (at least 1). Stragglers mint in proportion to
    how busy a type is, and a flat 20 would turn the next Initiative of a
    three-Initiative project into I-24.
    """
    root = Path(root)
    auth = resolve_authority(root)
    remote = remote or auth.remote
    ref = ref or auth.ref
    ledger = _require_ledger()
    ledger.check_names(remote, ref)
    if _git_layout(root) is None:
        raise IdCounterError("init-remote needs a git repository")
    if _git_out(root, "remote", "get-url", remote) is None:
        raise IdCounterError(f"git remote {remote!r} is not configured")

    scan_ns = "refs/edpa/scan"
    namespaces: tuple[str, ...] = ("refs/heads", "refs/remotes")
    fetched = False
    if fetch:
        try:
            r = subprocess.run(
                ["git", "fetch", "--quiet", "--no-tags", remote,
                 f"+refs/heads/*:{scan_ns}/*"], cwd=str(root),
                capture_output=True, text=True, encoding="utf-8",
                stdin=subprocess.DEVNULL, check=False, timeout=600)
            failure = None if r.returncode == 0 else (r.stderr or "").strip()
        except subprocess.TimeoutExpired:
            failure = "git fetch did not finish within 10 minutes"
        if failure is not None:
            raise IdCounterError(
                f"cannot fetch the branches of {remote!r} — the floor would be "
                f"a guess. Fix the connection or pass --no-fetch.\n{failure}")
        fetched = True
        namespaces += (scan_ns,)
    try:
        seen = scan_known_max(root, namespaces)
    finally:
        for name in (_git_out(root, "for-each-ref", "--format=%(refname)",
                              scan_ns) or "").split():
            _git_out(root, "update-ref", "-d", name)
    floors = {t: (v + min(headroom, max(1, -(-v // 10))) if v > 0 and headroom > 0
                  else v)
              for t, v in seen.items()}
    return {"remote": remote, "ref": ref, "seen": seen, "floors": floors,
            "headroom": headroom, "fetched": fetched}


def apply_init_remote(root: Path | str, plan: dict) -> None:
    """Create the ledger from ``plan``, or lift an existing one to it
    (idempotent: a ledger already at or above the plan is left as is)."""
    ledger = _require_ledger()
    try:
        ledger.raise_floors(
            Path(root), plan["floors"], create=True,
            remote=plan["remote"], ref=plan["ref"],
            subject=f"init: seed ID ledger (headroom {plan['headroom']})")
    except ledger.LedgerError as e:
        raise IdCounterError(f"could not create the ID ledger: {e}") from e


def write_opt_in(root: Path | str, plan: dict) -> list[Path]:
    """Prepare the opt-in commit in the working tree: the ``ids:`` block in
    edpa.yaml. Not committed — it goes through the project's normal review.

    The tracked ``id_counters.yaml`` is deliberately left untouched. Every
    branch that created a ticket before the cut-over carries a counter
    bump; rewriting (or deleting) the file here would hand each of them a
    conflict the moment they meet this commit. Left alone, it keeps
    merging as it always did until those branches drain, and nothing new
    writes it any more.
    """
    root = Path(root)
    changed: list[Path] = []
    cfg = root / ".edpa" / "config" / "edpa.yaml"
    text = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
    if not _ids_config(root):
        block = ("\n# ID authority (ADR-014): ticket IDs are reserved on the "
                 "shared git remote\n# (compare-and-swap on a ref) so they are "
                 "unique across worktrees, branches\n# and developers. See "
                 "docs/dev-collisions.md.\nids:\n  authority: remote\n")
        if plan["remote"] != DEFAULT_LEDGER_REMOTE:
            block += f"  remote: {plan['remote']}\n"
        if plan["ref"] != DEFAULT_LEDGER_REF:
            block += f"  ref: {plan['ref']}\n"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(text.rstrip("\n") + "\n" + block if text else block.lstrip("\n"),
                       encoding="utf-8")
        changed.append(cfg)
    return changed


def _status(root: Path, refresh: bool) -> dict:
    auth = resolve_authority(root)
    ledger = _ledger()
    state = _state_dir(root)
    ledger_state, ledger_error = None, None
    if ledger is not None and state is not None:
        try:
            if refresh:
                ledger.refresh(root, remote=auth.remote, ref=auth.ref)
                auth = resolve_authority(root)   # may just have been discovered
            cached = ledger.cached_state(root)
            if cached is not None:
                ledger_state = {"counters": cached[0], "floors": cached[1]}
        except ledger.LedgerError as e:
            ledger_error = str(e)
    info: dict = {
        "authority": auth.mode, "source": auth.source,
        "remote": auth.remote, "ref": auth.ref,
        "ledger": ledger_state, "ledger_error": ledger_error,
        "local": {}, "pool": _read_pool(state) if state else {},
    }
    for t, d in TYPE_DIRS.items():
        info["local"][t] = {
            "files": _scan_fs_max(root / ".edpa" / "backlog" / d, t),
            "tracked": _safe_counter(root / _COUNTER_REL, t),
            "clone": _safe_counter(_hwm_path(state), t) if state else 0,
        }
    return info


def _print_status(info: dict) -> None:
    how = {"env": f"${AUTHORITY_ENV}", "config": "ids.authority in edpa.yaml",
           "discovered": "this clone has seen the project's ID ledger "
                         "or its opt-in on the integration branch",
           "default": "no ledger known"}[info["source"]]
    print(f"ID authority: {info['authority']}  ({how})")
    if info["authority"] == "remote" or info["ledger"]:
        print(f"Ledger:       {info['ref']} on {info['remote']}"
              + ("" if info["ledger"] else "  — not seen by this clone yet"))
    if info["ledger_error"]:
        print(f"              ! {info['ledger_error']}")
    led = info["ledger"] or {"counters": {}, "floors": {}}
    print()
    print(f"  {'type':<11}{'ledger':>8}{'floor':>8}{'files':>8}"
          f"{'tracked':>9}{'clone':>8}  pre-reserved")
    def cell(v) -> str:
        return str(v) if v else "-"

    for t, prefix in TYPE_PREFIX.items():
        loc = info["local"][t]
        pool = ", ".join(f"{prefix}-{n}" for n in info["pool"].get(t, []))
        print(f"  {t:<11}{cell(led['counters'].get(t)):>8}"
              f"{cell(led['floors'].get(t)):>8}{cell(loc['files']):>8}"
              f"{cell(loc['tracked']):>9}{cell(loc['clone']):>8}  {pool}")
    print()
    print("  ledger   highest number reserved on the remote (cached copy)")
    print("  floor    numbers up to here may exist without a reservation record")
    print("  files    highest item file in this checkout")
    print("  tracked  .edpa/config/id_counters.yaml in this checkout")
    print("  clone    high-water mark shared by this clone's worktrees")


def _doctor(root: Path, *, raise_floors: bool) -> int:
    auth = resolve_authority(root)
    ledger = _require_ledger()
    problems = 0
    print(f"ID authority: {auth.mode} ({auth.source})")
    try:
        known = ledger.refresh(root, remote=auth.remote, ref=auth.ref)
    except ledger.LedgerError as e:
        print(f"✗ cannot reach the ledger: {e}")
        return 1
    if not known:
        print(f"· no ID ledger at {auth.ref} on {auth.remote} "
              f"(run: id_counter.py init-remote)")
        return 0 if auth.mode == "local" else 1
    counters, floors = ledger.cached_state(root)
    print(f"✓ ledger reachable: {auth.ref} on {auth.remote}")

    local = _checkout_max(root)
    above = {t: v for t, v in local.items() if v > counters.get(t, 0)}
    unreserved: list[str] = []
    for t, d in TYPE_DIRS.items():
        prefix = TYPE_PREFIX[t]
        for f in sorted((root / ".edpa" / "backlog" / d).glob(f"{prefix}-*.md")):
            num = f.stem.rsplit("-", 1)[-1]
            if num.isdigit() and int(num) > floors.get(t, 0) \
                    and ledger.find_record(root, f.stem) is None:
                unreserved.append(f.stem)
    if unreserved:
        problems += 1
        print(f"✗ {len(unreserved)} item(s) above the floor without a "
              f"reservation: {', '.join(unreserved[:12])}"
              + (" …" if len(unreserved) > 12 else ""))
    else:
        print("✓ every item above the floor has a reservation record")
    if above:
        problems += 1
        print("✗ this checkout holds numbers above the ledger: "
              + ", ".join(f"{TYPE_PREFIX[t]}-{v} (ledger {counters.get(t, 0)})"
                          for t, v in above.items()))
    if raise_floors and (above or unreserved):
        wanted = {t: v for t, v in local.items() if v > floors.get(t, 0)}
        try:
            ledger.raise_floors(root, wanted, remote=auth.remote, ref=auth.ref,
                                subject="floors: adopt local items (doctor --raise)")
        except ledger.LedgerError as e:
            print(f"✗ could not raise the floors: {e}")
            return 1
        print("→ floors raised to: "
              + ", ".join(f"{TYPE_PREFIX[t]}-{v}" for t, v in wanted.items()))
        return 0
    if problems:
        print("\nIf those items are real pre-ledger work, adopt them: "
              "id_counter.py doctor --raise")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    try:  # best-effort UTF-8 stdio on legacy Windows consoles (cp1250)
        import _console  # noqa: F401
    except ImportError:
        pass

    parser = argparse.ArgumentParser(
        prog="id_counter",
        description="EDPA ID allocator — status, remote ledger bootstrap, "
                    "scripted allocation.")
    parser.add_argument("--root", help="project root (default: nearest "
                        "directory with .edpa/, walking up from cwd)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status", help="who allocates IDs here, and the "
                       "counters each layer holds")
    p.add_argument("--refresh", action="store_true",
                   help="read the remote ledger first (network)")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("next", help="allocate one ID and print it")
    p.add_argument("--type", required=True, choices=sorted(TYPE_PREFIX))
    p.add_argument("--title")
    p.add_argument("--parent")
    p.add_argument("--created-at", dest="created_at")

    p = sub.add_parser("reserve", help="pre-reserve a block of IDs for "
                       "offline use (remote authority)")
    p.add_argument("--type", required=True, choices=sorted(TYPE_PREFIX))
    p.add_argument("--count", type=int, required=True)

    p = sub.add_parser("init-remote", help="create the ID ledger on the "
                       "shared remote (once per repository)")
    p.add_argument("--headroom", type=int, default=0,
                   help="leave numbers free above each type's highest known "
                        "ID for sessions still on an outdated allocator: "
                        "about a tenth of a type's size, at most this many. "
                        "Default 0 — numbering continues without gaps")
    p.add_argument("--remote")
    p.add_argument("--ref")
    p.add_argument("--no-fetch", action="store_true",
                   help="do not fetch the remote's branches before scanning")
    p.add_argument("--apply", action="store_true",
                   help="skip the confirmation prompt")
    p.add_argument("--write-config", action="store_true",
                   help="also prepare the opt-in change in the working tree "
                        "(ids.authority: remote in edpa.yaml)")

    p = sub.add_parser("doctor", help="check this checkout against the ledger")
    p.add_argument("--raise", dest="raise_floors", action="store_true",
                   help="adopt this checkout's unreserved items as pre-ledger "
                        "(raises the ledger floors)")
    p.add_argument("--rebuild", action="store_true",
                   help="local authority: re-seed id_counters.yaml from the "
                        "item files (never lowers a counter)")
    p.add_argument("--forget", action="store_true",
                   help="drop this clone's cached copy of the ledger")

    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else _find_project_root(Path.cwd())
    if root is None or not (root / ".edpa").is_dir():
        print("ERROR: no .edpa/ directory found (run from the project, or "
              "pass --root)", file=sys.stderr)
        return 2

    try:
        if args.command == "status":
            info = _status(root, args.refresh)
            if args.json:
                print(json.dumps(info, indent=2, sort_keys=True))
            else:
                _print_status(info)
            return 0

        if args.command == "next":
            print(next_id(args.type, root, meta={
                "title": args.title, "parent": args.parent,
                "created_at": args.created_at}))
            return 0

        if args.command == "reserve":
            if args.count < 1:
                print("ERROR: --count must be >= 1", file=sys.stderr)
                return 2
            ids = reserve_block(args.type, root, args.count)
            print(f"Reserved {ids[0]}..{ids[-1]} — kept for offline use in "
                  f"this clone.")
            return 0

        if args.command == "init-remote":
            plan = init_remote(root, headroom=max(args.headroom, 0),
                               fetch=not args.no_fetch,
                               remote=args.remote, ref=args.ref)
            print(f"ID ledger: {plan['ref']} on {plan['remote']}")
            print("Highest ID found across worktrees and branches"
                  + ("" if plan["fetched"] else " (remote branches NOT fetched)")
                  + (f", + headroom (up to {plan['headroom']} per type)"
                     if plan["headroom"] else "") + ":\n")
            for t, prefix in TYPE_PREFIX.items():
                if plan["seen"][t]:
                    print(f"  {t:<11} {prefix}-{plan['seen'][t]:<6} → floor "
                          f"{prefix}-{plan['floors'][t]:<6} first new ID "
                          f"{prefix}-{plan['floors'][t] + 1}")
            print()
            if not args.apply:
                try:
                    answer = input("Create the ledger? [y/N]: ").strip().lower()
                except EOFError:
                    answer = ""
                if answer != "y":
                    print("Aborted — nothing was written.")
                    return 1
            apply_init_remote(root, plan)
            print("Ledger ready. Every session of this clone now reserves IDs "
                  "there.")
            if args.write_config:
                for path in write_opt_in(root, plan):
                    print(f"  prepared: {path.relative_to(root)}")
                print("Commit that change through your normal review — it "
                      "switches everyone else.")
            else:
                print("Next: opt the project in (one reviewed commit): "
                      "re-run with --write-config, or set `ids.authority: "
                      "remote` in .edpa/config/edpa.yaml.")
            return 0

        if args.command == "doctor":
            if args.forget:
                _require_ledger().forget(root)
                print("Dropped the cached ledger copy of this clone.")
                return 0
            if args.rebuild:
                counters = seed_counters_from_fs(root)
                print("id_counters.yaml: " + ", ".join(
                    f"{k}={v}" for k, v in sorted(counters.items()) if v))
                return 0
            return _doctor(root, raise_floors=args.raise_floors)
    except IdCounterError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
