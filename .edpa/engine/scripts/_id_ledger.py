"""Remote ID ledger — compare-and-swap ID reservation on a git ref.

Why this module exists
----------------------
``id_counter.next_id`` allocates from state inside one working tree (the
tracked counter file + a filesystem scan). Two git worktrees, two clones
or two developers therefore mint the same number, and the collision only
surfaces as a merge conflict later (ADR-014, ``docs/dev-collisions.md``).

This module restores a single arbiter for ID numbers without bringing
back any forge API: the arbiter is the git remote the team already
pushes to. The ledger is a chain of commits on one ref of that remote
(default ``refs/edpa/ids``). Reserving an ID is a push the server accepts
only while the ref still points where the client last saw it — a
compare-and-swap. Exactly one concurrent pusher wins; the others re-read
and retry with the next number.

Ledger shape
------------
* tree     one file, ``counters.yaml``::

               schema: 1
               counters: {Story: 285}   # highest number handed out, per type
               floors:   {Story: 280}   # highest number that may exist
                                        # WITHOUT a reservation record
                                        # (pre-ledger items + cut-over headroom)

* message  the audit record of the reservation (subject + ``EDPA-*`` trailers)
* history  append-only by construction: every commit descends from the tip
           it replaced. Counters and floors are per-type maxima, so two
           histories can always be reconciled by taking the element-wise
           max — a rewound, deleted or force-pushed ledger heals on the
           next write from any clone that still remembers the newer state.

Everything here is git plumbing: no working tree, no index, no checkout.
The push uses ``--no-verify`` on purpose — consumer projects run their
test suites in ``pre-push``, and this push carries one metadata commit,
never source code (same stance as local_evidence.py's tooling commit).

Local refs (shared by every worktree of a clone, named independently of
the remote ref so a branch-hosted ledger never creates a local branch):
    refs/edpa/cache/ids        best ledger state this clone knows
    refs/edpa/observed/<uuid>  one raw observation of the remote ref —
                               private to the observing process and deleted
                               right away (a shared name makes concurrent
                               fetches in sibling worktrees fail each other)

This module is lock-free: correctness comes from the server-side
compare-and-swap. ``id_counter`` only adds an advisory per-clone
turnstile so sibling worktrees do not race each other into retries.
"""
from __future__ import annotations

import os
import random
import re
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_REMOTE = "origin"
DEFAULT_REF = "refs/edpa/ids"
CACHE_REF = "refs/edpa/cache/ids"
_OBSERVED_NS = "refs/edpa/observed"
COUNTERS_FILE = "counters.yaml"
SCHEMA = 1

# A local maximum this far above the ledger is far more likely a stray
# file (S-9999.md) than real pre-ledger work; adopting it would inflate
# the sequence for everyone, permanently.
DEFAULT_MAX_JUMP = 100

_NET_TIMEOUT_SEC = 20
_DEADLINE_SEC = 45
_MAX_ATTEMPTS = 12
_MAX_TRANSIENT = 3

# Auto-maintenance repacks the object store while we read from it; with
# worktrees sharing one store that surfaces as a transiently "missing"
# object. Never let our own calls trigger it.
_GIT_PREFIX = ("-c", "maintenance.auto=false", "-c", "gc.auto=0")

# git >= 2.29. Without it the fetch rewrites the worktree's FETCH_HEAD,
# which a concurrent `git pull` there could then try to merge. Dropped on
# the first "unknown option" so older gits still work.
_fetch_extra: list[str] = ["--no-write-fetch-head"]

_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]+")
# Both values come from the tracked edpa.yaml and end up in git argv —
# refuse anything that could be read as an option or a refspec trick.
_REMOTE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_REF_RE = re.compile(
    r"^refs/[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)+$")


class LedgerError(Exception):
    """Base class — the ledger could not complete the operation."""


class LedgerUnavailable(LedgerError):
    """The remote could not be reached (network, auth, timeout)."""


class LedgerMissing(LedgerError):
    """The ledger ref is absent on the remote and unknown to this clone."""


class LedgerRejected(LedgerError):
    """The remote refused the update for a reason that is not a lost race
    (missing push permission, a protected ref, a server-side hook)."""


class LedgerContention(LedgerError):
    """Gave up after bounded retries — other writers kept winning."""


class _Transient(LedgerError):
    """A read that may succeed on a second look (object-store churn)."""


@dataclass
class Reservation:
    """Outcome of one ledger write."""
    numbers: list[int]
    commit: str
    attempts: int = 1
    notes: list[str] = field(default_factory=list)


@dataclass
class _Result:
    returncode: int
    stdout: str
    stderr: str


def check_names(remote: str, ref: str) -> None:
    if not _REMOTE_RE.match(remote or ""):
        raise LedgerError(f"invalid ledger remote name {remote!r}")
    if not _REF_RE.match(ref or "") or ".." in ref or ref.endswith(".lock"):
        raise LedgerError(
            f"invalid ledger ref {ref!r} (expected e.g. {DEFAULT_REF} or "
            f"refs/heads/edpa-ids)"
        )


# ---------------------------------------------------------------------------
# git plumbing
# ---------------------------------------------------------------------------

def _git(repo: Path | str, *args: str, stdin: str | None = None,
         timeout: float | None = None, check: bool = True) -> _Result:
    """Run one git command.

    * bytes I/O, decoded as UTF-8 — no newline translation, so ``mktree``
      input stays byte-exact on Windows;
    * stdin is never inherited: the MCP server's stdin is its JSON-RPC
      stream, and a git child reading it would eat protocol bytes;
    * own process group on POSIX, killed as a whole on timeout — otherwise
      a hung ssh / credential helper outlives the git we gave up on.
    """
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"   # never block an agent on a prompt
    kw = {"start_new_session": True} if os.name == "posix" else {}
    try:
        proc = subprocess.Popen(
            ["git", *_GIT_PREFIX, *args], cwd=str(repo), env=env,
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw,
        )
    except FileNotFoundError as e:
        raise LedgerError("git executable not found") from e
    try:
        out, err = proc.communicate(
            stdin.encode("utf-8") if stdin is not None else None,
            timeout=timeout)
    except subprocess.TimeoutExpired as e:
        try:
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except OSError:
            pass
        proc.communicate()
        raise LedgerUnavailable(
            f"git {args[0]} did not finish within {timeout}s"
        ) from e
    r = _Result(proc.returncode, out.decode("utf-8", "replace"),
                err.decode("utf-8", "replace"))
    if check and r.returncode != 0:
        raise LedgerError(
            f"git {' '.join(args[:2])} failed: {r.stderr.strip()}"
        )
    return r


def _rev(repo: Path | str, name: str) -> str | None:
    r = _git(repo, "rev-parse", "--verify", "--quiet", f"{name}^{{commit}}",
             check=False)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def _is_ancestor(repo: Path | str, older: str, newer: str) -> bool:
    r = _git(repo, "merge-base", "--is-ancestor", older, newer, check=False)
    if r.returncode in (0, 1):
        return r.returncode == 0
    raise _Transient(
        f"cannot compare ledger commits {older[:12]} and {newer[:12]}: "
        f"{r.stderr.strip()}"
    )


def _int_map(raw) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    return {str(k): int(v) for k, v in raw.items()
            if isinstance(v, int) and not isinstance(v, bool)}


def _state_at(repo: Path | str, commit: str) -> tuple[dict[str, int], dict[str, int]]:
    """``(counters, floors)`` recorded in a ledger commit."""
    r = _git(repo, "cat-file", "-p", f"{commit}:{COUNTERS_FILE}", check=False)
    if r.returncode != 0:
        raise _Transient(
            f"ledger commit {commit[:12]} has no readable {COUNTERS_FILE}: "
            f"{r.stderr.strip()}"
        )
    try:
        data = yaml.safe_load(r.stdout) or {}
    except yaml.YAMLError as e:
        raise LedgerError(
            f"ledger commit {commit[:12]}: cannot parse {COUNTERS_FILE}: {e}"
        ) from e
    if not isinstance(data, dict):
        return {}, {}
    return _int_map(data.get("counters")), _int_map(data.get("floors"))


def _merge_max(*maps: dict[str, int] | None) -> dict[str, int]:
    out: dict[str, int] = {}
    for m in maps:
        for k, v in (m or {}).items():
            if int(v) > out.get(k, 0):
                out[k] = int(v)
    return out


def _one_line(value) -> str:
    """Collapse to a single trailer-safe line (titles are free text)."""
    return _CONTROL_RE.sub(" ", str(value)).strip()[:200]


def _message(subject: str, trailers: list[tuple[str, str | None]]) -> str:
    lines = [_one_line(subject), ""]
    lines += [f"{k}: {_one_line(v)}" for k, v in trailers
              if v is not None and str(v).strip()]
    # Two worktrees of one person can otherwise build a byte-identical
    # commit (same tree, parent, identity, second, text); git then answers
    # the second push with "up to date" and both would own the number.
    lines.append(f"EDPA-Nonce: {uuid.uuid4().hex}")
    return "\n".join(lines) + "\n"


def _commit(repo: Path | str, parents: list[str], counters: dict[str, int],
            floors: dict[str, int], message: str) -> str:
    body = yaml.safe_dump(
        {"schema": SCHEMA,
         "counters": dict(sorted(counters.items())),
         "floors": dict(sorted(floors.items()))},
        sort_keys=False, default_flow_style=False,
    )
    blob = _git(repo, "hash-object", "-w", "--stdin", stdin=body).stdout.strip()
    tree = _git(repo, "mktree",
                stdin=f"100644 blob {blob}\t{COUNTERS_FILE}\n").stdout.strip()
    args = ["commit-tree", tree]
    for p in parents:
        args += ["-p", p]
    r = _git(repo, *args, stdin=message, check=False)
    if r.returncode == 0:
        return r.stdout.strip()
    if _git(repo, "var", "GIT_COMMITTER_IDENT", check=False).returncode != 0:
        # Same stance as _auto_commit: surface the missing identity rather
        # than record a reservation under a synthetic name.
        raise LedgerError(
            "cannot record the reservation: git user.name / user.email are "
            "not configured — the ledger records who reserved each ID"
        )
    raise _Transient(f"cannot create the ledger commit: {r.stderr.strip()}")


def _observe(repo: Path | str, remote: str, ref: str,
             timeout: float | None = None) -> str | None:
    """Fetch the remote ledger tip and return its sha, or ``None`` when the
    ref does not exist on the remote.

    The fetch lands in a ref private to this call — never in the trusted
    cache (a fetch outside refs/heads accepts rewinds), and never in a
    shared name (sibling worktrees observing at once would fail each
    other's ref update). The objects stay available without the ref: they
    are fresh, and the cache keeps them once the write succeeds.

    Raises :class:`LedgerUnavailable` when the remote cannot be reached.
    """
    tmp = f"{_OBSERVED_NS}/{uuid.uuid4().hex}"
    timeout = timeout or _NET_TIMEOUT_SEC

    def fetch() -> _Result:
        return _git(repo, "fetch", "--quiet", "--no-tags",
                    "--no-recurse-submodules", *_fetch_extra, remote,
                    f"+{ref}:{tmp}", timeout=timeout, check=False)

    try:
        r = fetch()
        if r.returncode == 129 and _fetch_extra:   # usage error: old git
            _fetch_extra.clear()
            r = fetch()
        if r.returncode == 0:
            sha = _rev(repo, tmp)
            if sha is None:
                raise LedgerUnavailable(
                    f"fetched {ref} from {remote!r} but cannot resolve it")
            return sha
    finally:
        _git(repo, "update-ref", "-d", tmp, check=False)
    # A missing ref and an unreachable remote both fail the fetch;
    # ls-remote tells them apart by exit code (2 = no matching ref), so no
    # human-readable message has to be parsed.
    probe = _git(repo, "ls-remote", "--exit-code", remote, ref,
                 timeout=timeout, check=False)
    if probe.returncode == 2:
        return None
    detail = (probe.stderr if probe.returncode != 0 else r.stderr).strip()
    raise LedgerUnavailable(
        f"cannot read the ID ledger {ref} from remote {remote!r}: {detail}"
    )


_UNKNOWN = object()


def _advance_cache(repo: Path | str, new: str, known=_UNKNOWN) -> None:
    """Move the cache forward to ``new`` — best effort, never backwards.

    Sibling processes finish in any order and contend for the ref lock; a
    stale cache is harmless (the next read catches up), so nothing here
    may fail a reservation that the remote already accepted.

    ``known`` is the cache value the caller already proved ``new`` to
    descend from: one compare-and-swap then settles the common case.
    """
    if known is not _UNKNOWN and _git(
            repo, "update-ref", CACHE_REF, new, known or "",
            check=False).returncode == 0:
        return
    for _ in range(5):
        current = _rev(repo, CACHE_REF)
        if current == new:
            return
        try:
            if current is not None and not _is_ancestor(repo, current, new):
                return                     # cache is ahead of / beside it
        except LedgerError:
            return
        if _git(repo, "update-ref", CACHE_REF, new, current or "",
                check=False).returncode == 0:
            return
        time.sleep(random.uniform(0.01, 0.05))


def _push(repo: Path | str, remote: str, ref: str, new: str,
          expect: str | None) -> tuple[str, str]:
    """Push ``new`` to ``ref`` iff the remote still holds ``expect``.

    An empty lease value means "the ref must not exist yet". Returns
    ``(flag, output)`` where flag is git's porcelain status character for
    the ref: ``" "`` fast-forward, ``"*"`` new ref, ``"!"`` rejected,
    ``"="`` up to date, ``""`` when git reported nothing for it (transport
    failure). Only ``" "`` / ``"*"`` with a zero exit status is a win —
    ``"="`` means somebody else's identical object is already there.
    """
    r = _git(repo, "push", "--no-verify", "--porcelain",
             "--recurse-submodules=no",
             f"--force-with-lease={ref}:{expect or ''}",
             remote, f"{new}:{ref}", timeout=_NET_TIMEOUT_SEC, check=False)
    flag = ""
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1].endswith(f":{ref}"):
            flag = parts[0]
            break
    if r.returncode != 0 and flag in (" ", "*"):
        flag = ""
    return flag, "\n".join(
        x for x in (r.stdout.strip(), r.stderr.strip()) if x)


def _base(repo: Path | str, observed: str | None, cached: str | None,
          notes: list[str]) -> tuple[list[str], dict[str, int], dict[str, int]]:
    """Parents and starting ``(counters, floors)`` for the next commit.

    Normally the remote tip. When the remote is behind, gone, or diverged
    from what this clone remembers, the new commit is built so that it
    still fast-forwards the remote *and* carries the remembered state:
    every parent list returned here either contains ``observed`` or is a
    cache that was just proven to descend from it.
    """
    if observed is None and cached is None:
        return [], {}, {}
    if cached is None or cached == observed:
        return ([observed], *_state_at(repo, observed))
    if observed is None:
        notes.append("ledger ref was missing on the remote — restored from "
                     "this clone's cache")
        return ([cached], *_state_at(repo, cached))
    if _is_ancestor(repo, cached, observed):
        return ([observed], *_state_at(repo, observed))
    if _is_ancestor(repo, observed, cached):
        notes.append("remote ledger was behind this clone's cache — "
                     "fast-forwarded it")
        return ([cached], *_state_at(repo, cached))
    notes.append("remote ledger diverged from this clone's cache — merged "
                 "both histories (per-type max)")
    oc, of = _state_at(repo, observed)
    cc, cf = _state_at(repo, cached)
    return [observed, cached], _merge_max(oc, cc), _merge_max(of, cf)


def _transact(repo: Path | str, remote: str, ref: str, mutate, *,
              create: bool, deadline: float = _DEADLINE_SEC) -> Reservation:
    """One compare-and-swap update of the ledger.

    ``mutate(counters, floors)`` edits both maps in place and returns
    ``(subject, trailers, numbers)``, or ``None`` when it has nothing to
    write. No commit is made for ``None`` unless the remote needs healing.
    """
    check_names(remote, ref)
    started = time.monotonic()
    transient = refusals = 0
    last_error: LedgerError | None = None
    observed = _observe(repo, remote, ref)

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        if time.monotonic() - started > deadline:
            break
        cached = _rev(repo, CACHE_REF)
        if observed is None and cached is None and not create:
            raise LedgerMissing(
                f"the ID ledger {ref} does not exist on remote {remote!r}. "
                f"Initialize it once per repository: "
                f"python3 .edpa/engine/scripts/id_counter.py init-remote"
            )
        notes: list[str] = []
        try:
            parents, counters, floors = _base(repo, observed, cached, notes)
            plan = mutate(counters, floors)
            healing = parents != ([observed] if observed else [])
            if plan is None and not healing:
                if observed:
                    _advance_cache(repo, observed)
                return Reservation([], observed or "", attempt, notes)
            subject, trailers, numbers = plan or (
                "sync: reconcile ledger histories", [], [])
            # The lease below turns into a forced update once it matches;
            # _base guarantees these parents extend the remote tip, so the
            # update can only ever be a fast-forward.
            new = _commit(repo, parents, counters, floors,
                          _message(subject, trailers))
        except _Transient as e:
            # A concurrent repack in the shared object store can hide an
            # object for a moment; look again instead of failing the user.
            transient += 1
            last_error = e
            if transient > _MAX_TRANSIENT:
                break
            time.sleep(random.uniform(0.05, 0.2))
            observed = _observe(repo, remote, ref)
            continue

        try:
            flag, output = _push(repo, remote, ref, new, observed)
        except LedgerUnavailable as e:      # timed out — it may have landed
            flag, output = "", str(e)
        if flag not in (" ", "*"):
            # Lost race, refusal, or an ambiguous outcome (a timeout after
            # the server applied it) — ask the remote which one it was.
            latest = _observe(repo, remote, ref)
            try:
                ours = latest is not None and (
                    latest == new or _is_ancestor(repo, new, latest))
            except _Transient:
                ours = False                # cannot tell: reserve afresh
            if not ours:
                if latest != observed:
                    observed = latest                      # lost the race
                    time.sleep(random.uniform(0.05, 0.25) * min(attempt, 6))
                    continue
                refusals += 1
                if flag == "!" and refusals >= 2:
                    raise LedgerRejected(
                        f"remote {remote!r} refused the update of {ref} and "
                        f"nobody else moved it, so this is not a lost race — "
                        f"check push permission / ref protection:\n{output}"
                    )
                last_error = LedgerUnavailable(
                    f"push to {remote!r} failed:\n{output}")
                time.sleep(random.uniform(0.1, 0.3))
                continue
        _advance_cache(repo, new, known=cached)
        return Reservation(list(numbers), new, attempt, notes)

    if last_error is not None:
        raise last_error
    raise LedgerContention(
        f"could not update the ID ledger {ref} on {remote!r} within "
        f"{_MAX_ATTEMPTS} attempts / {int(deadline)}s — other writers kept "
        f"winning. Retry."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def reserve(repo: Path | str, item_type: str, prefix: str, *,
            floor: int = 0, count: int = 1,
            remote: str = DEFAULT_REMOTE, ref: str = DEFAULT_REF,
            title: str | None = None, parent: str | None = None,
            branch: str | None = None, created_at: str | None = None,
            max_jump: int | None = DEFAULT_MAX_JUMP,
            deadline: float = _DEADLINE_SEC) -> Reservation:
    """Reserve ``count`` consecutive numbers for ``item_type``.

    ``floor`` is the highest number the caller already sees locally
    (filesystem scan, legacy counter). When it is above the ledger, those
    numbers exist without a reservation record, so the ledger adopts it as
    the type's floor and the reservation starts after it. ``max_jump``
    caps how far a local maximum may pull the shared sequence
    (``None`` disables the guard).
    """
    if count < 1:
        raise ValueError("count must be >= 1")

    def mutate(counters: dict[str, int], floors: dict[str, int]):
        current = counters.get(item_type, 0)
        local = int(floor)
        if local > current:
            if max_jump is not None and local - current > max_jump:
                raise LedgerError(
                    f"this checkout holds {prefix}-{local}, {local - current} "
                    f"above the shared ledger ({prefix}-{current}). That looks "
                    f"like a stray file rather than real work; remove it, or "
                    f"adopt it on purpose with: python3 "
                    f".edpa/engine/scripts/id_counter.py doctor --raise"
                )
            floors[item_type] = max(floors.get(item_type, 0), local)
        start = max(current, local) + 1
        numbers = list(range(start, start + count))
        counters[item_type] = numbers[-1]
        ids = [f"{prefix}-{n}" for n in numbers]
        if count == 1:
            subject = f"alloc {ids[0]}: {title}" if title else f"alloc {ids[0]}"
        else:
            subject = f"reserve {ids[0]}..{ids[-1]} ({count})"
        trailers: list[tuple[str, str | None]] = [("EDPA-Id", i) for i in ids]
        trailers += [("EDPA-Type", item_type), ("EDPA-Title", title),
                     ("EDPA-Parent", parent), ("EDPA-Branch", branch),
                     ("EDPA-Created-At", created_at)]
        return subject, trailers, numbers

    return _transact(repo, remote, ref, mutate, create=False,
                     deadline=deadline)


def raise_floors(repo: Path | str, floors: dict[str, int], *,
                 remote: str = DEFAULT_REMOTE, ref: str = DEFAULT_REF,
                 create: bool = False, subject: str | None = None,
                 deadline: float = _DEADLINE_SEC) -> Reservation:
    """Declare that numbers up to ``floors[type]`` may exist without a
    reservation record, and lift the counters to at least those values
    (never lowers anything).

    With ``create=True`` this is the bootstrap: it creates the ledger when
    the ref does not exist yet. No commit is made when the ledger already
    exists at or above every floor.
    """
    wanted = {k: int(v) for k, v in floors.items() if int(v) > 0}

    def mutate(counters: dict[str, int], current_floors: dict[str, int]):
        existed = bool(counters) or bool(current_floors)
        raised = {k: v for k, v in wanted.items()
                  if v > current_floors.get(k, 0) or v > counters.get(k, 0)}
        if not raised and existed:
            return None
        for k, v in raised.items():
            current_floors[k] = max(current_floors.get(k, 0), v)
            counters[k] = max(counters.get(k, 0), v)
        trailers: list[tuple[str, str | None]] = [
            ("EDPA-Floor", f"{k}={v}") for k, v in sorted(raised.items())]
        return (subject or "floors: raise per-type high-water marks",
                trailers, [])

    return _transact(repo, remote, ref, mutate, create=create,
                     deadline=deadline)


def refresh(repo: Path | str, *, remote: str = DEFAULT_REMOTE,
            ref: str = DEFAULT_REF, timeout: float | None = None) -> bool:
    """Read the remote ledger and advance the local cache. Never writes to
    the remote. Returns whether this clone now knows a ledger.

    ``timeout`` shortens the per-call network wait for callers on an
    interactive path (git hooks)."""
    check_names(remote, ref)
    observed = _observe(repo, remote, ref, timeout)
    if observed is None:
        return _rev(repo, CACHE_REF) is not None
    # Remote behind or diverged: _advance_cache keeps the cache — the next
    # write heals the remote, and the cache knows the newer reservations.
    _advance_cache(repo, observed)
    return True


def known_locally(repo: Path | str) -> bool:
    """Has this clone ever seen a ledger? Offline, no network."""
    return _rev(repo, CACHE_REF) is not None


def cached_state(repo: Path | str) -> tuple[dict[str, int], dict[str, int]] | None:
    """``(counters, floors)`` from the local cache — offline. ``None`` when
    this clone has never seen a ledger."""
    cached = _rev(repo, CACHE_REF)
    return _state_at(repo, cached) if cached else None


def forget(repo: Path | str) -> None:
    """Drop this clone's ledger cache (it is re-read from the remote) and
    any observation ref a killed process left behind."""
    _git(repo, "update-ref", "-d", CACHE_REF, check=False)
    r = _git(repo, "for-each-ref", "--format=%(refname)", _OBSERVED_NS,
             check=False)
    for name in r.stdout.split():
        _git(repo, "update-ref", "-d", name, check=False)


_LOG_FORMAT = "%H%x1f%an%x1f%ae%x1f%aI%x1f%s%x1f%(trailers:only,unfold)%x1e"


def _parse_log(text: str) -> list[dict]:
    out: list[dict] = []
    for raw in text.split("\x1e"):
        raw = raw.strip("\n")
        if not raw:
            continue
        commit, by, email, at, subject, trailers = (
            raw.split("\x1f") + [""] * 6)[:6]
        rec: dict = {"commit": commit, "by": by, "email": email, "at": at,
                     "subject": subject, "ids": [], "floors": {}}
        for line in trailers.splitlines():
            key, sep, value = line.partition(":")
            if not sep:
                continue
            key, value = key.strip(), value.strip()
            if key == "EDPA-Id":
                rec["ids"].append(value)
            elif key == "EDPA-Floor":
                name, _, num = value.partition("=")
                if num.isdigit():
                    rec["floors"][name] = int(num)
            elif key.startswith("EDPA-") and key != "EDPA-Nonce":
                rec[key[5:].lower().replace("-", "_")] = value
        out.append(rec)
    return out


def entries(repo: Path | str, *, limit: int | None = None) -> list[dict]:
    """Audit records from the locally cached ledger, newest first.

    Each record: ``commit, by, email, at, subject, ids, floors`` plus one
    key per ``EDPA-*`` trailer (``type``, ``title``, ``parent``,
    ``branch``, ``created_at``).
    """
    if not known_locally(repo):
        return []
    args = ["log", f"--format={_LOG_FORMAT}"]
    if limit:
        args.append(f"-{int(limit)}")
    r = _git(repo, *args, CACHE_REF, check=False)
    return _parse_log(r.stdout) if r.returncode == 0 else []


def find_record(repo: Path | str, item_id: str) -> dict | None:
    """The reservation record for ``item_id`` in the local cache, if any."""
    if not re.fullmatch(r"[A-Z]{1,3}-\d{1,9}", item_id or ""):
        return None
    if not known_locally(repo):
        return None
    r = _git(repo, "log", "-1", f"--grep=^EDPA-Id: {item_id}$",
             f"--format={_LOG_FORMAT}", CACHE_REF, check=False)
    found = _parse_log(r.stdout) if r.returncode == 0 else []
    return found[0] if found and item_id in found[0]["ids"] else None
