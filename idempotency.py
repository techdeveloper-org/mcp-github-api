"""Filesystem-backed idempotency memo for non-idempotent MCP tool operations.

An MCP client cannot distinguish "the request never reached the server" from
"the request reached the server, succeeded, and only the response was lost".
Both look identical: no response arrived. A retry policy that re-sends the
identical request therefore executes a plain create/trigger operation twice and
leaves two resources where one was intended.

The fix implemented here is the idempotency-key pattern applied one layer above
the upstream API (GitHub, Jira and Jenkins expose no idempotency key of their
own). The caller generates a key once, at the point it forms the intent to
create the resource, and reuses that same key unchanged across every retry of
that same intent. A key generated fresh per wire attempt provides zero
protection and is a misuse of this module.

The claim step uses ``os.open`` with ``O_CREAT | O_EXCL``, which is a single
atomic insert-if-absent operation on both POSIX and Windows. A plain
"read the memo, then write it if absent" would reproduce the identical
time-of-check-to-time-of-use race that this module exists to close, merely
relocated from the upstream endpoint to the memo itself: two concurrent retries
would both observe an absent key and both invoke the underlying operation.

Windows-Safe: ASCII only (cp1252 compatible)
"""

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

DEFAULT_TTL_SECONDS = 24 * 60 * 60
DEFAULT_PENDING_TIMEOUT_SECONDS = 15 * 60

_STATUS_PENDING = "pending"
_STATUS_COMPLETED = "completed"


class DuplicateOperationInFlight(RuntimeError):
    """Raised when a key is claimed by an operation that has not yet finished.

    Signals that an identical logical operation is currently executing. The
    correct caller response is to wait and query the upstream system, never to
    execute the operation again under a fresh key.
    """


def _store_root() -> Path:
    """Return the root directory holding idempotency records.

    Honours the MCP_IDEMPOTENCY_DIR environment variable so deployments can
    place the memo on a volume shared by every process that serves the same
    logical caller.

    Returns:
        Path to the record root directory.
    """
    override = os.environ.get("MCP_IDEMPOTENCY_DIR", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".claude" / "memory" / "mcp-idempotency"


class IdempotencyStore:
    """Atomic insert-if-absent memo mapping an operation key to its outcome.

    Args:
        namespace: Logical operation family, e.g. "github_create_issue".
            Keys are scoped per namespace so the same caller-supplied key used
            for two different operations cannot collide.
        ttl_seconds: Age after which a completed record stops suppressing a
            replay and the key may be claimed again.
        pending_timeout_seconds: Age after which a claimed-but-never-completed
            record is treated as abandoned by a crashed process.
    """

    def __init__(
        self,
        namespace: str,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        pending_timeout_seconds: int = DEFAULT_PENDING_TIMEOUT_SECONDS,
    ) -> None:
        self._namespace = namespace
        self._ttl = ttl_seconds
        self._pending_timeout = pending_timeout_seconds
        self._dir = _store_root() / namespace

    def _path(self, key: str) -> Path:
        """Return the record path for a key.

        The filename is the SHA-256 of the key rather than the key itself: the
        key is caller-supplied and may embed identifiers that have no business
        appearing in a directory listing, and hashing also removes any path
        separator or reserved-name hazard from the filename.

        Args:
            key: Caller-supplied idempotency key.

        Returns:
            Path of the JSON record backing this key.
        """
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._dir / (digest + ".json")

    def claim(self, key: str) -> Optional[Dict[str, Any]]:
        """Atomically claim a key, or return the record that already holds it.

        Args:
            key: Caller-supplied idempotency key.

        Returns:
            None when the key was claimed by this call and the caller must now
            execute the underlying operation. Otherwise the existing record
            dict, whose ``status`` is either "completed" or "pending".
        """
        path = self._path(key)
        self._dir.mkdir(parents=True, exist_ok=True)

        record = {
            "status": _STATUS_PENDING,
            "key_sha256": hashlib.sha256(key.encode("utf-8")).hexdigest(),
            "namespace": self._namespace,
            "claimed_at": time.time(),
            "pid": os.getpid(),
        }
        payload = json.dumps(record, default=str)

        for _ in range(2):
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                existing = self._read(path)
                if existing is None:
                    self._discard(path)
                    continue
                if self._is_reclaimable(existing):
                    self._discard(path)
                    continue
                return existing
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
            except OSError:
                self._discard(path)
                raise
            return None

        raise RuntimeError(
            "Could not claim idempotency key in namespace '{}': the record is "
            "being reclaimed concurrently".format(self._namespace)
        )

    def complete(self, key: str, result: Dict[str, Any]) -> None:
        """Record the outcome of a successfully executed operation.

        Args:
            key: The key claimed by a prior ``claim`` call.
            result: The tool result dict to replay on any later retry.
        """
        path = self._path(key)
        record = {
            "status": _STATUS_COMPLETED,
            "key_sha256": hashlib.sha256(key.encode("utf-8")).hexdigest(),
            "namespace": self._namespace,
            "completed_at": time.time(),
            "result": result,
        }
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(record, default=str), encoding="utf-8")
        temp.replace(path)

    def release(self, key: str) -> None:
        """Drop a claim so a failed operation can be retried under the same key.

        Args:
            key: The key claimed by a prior ``claim`` call.
        """
        self._discard(self._path(key))

    def _is_reclaimable(self, record: Dict[str, Any]) -> bool:
        """Return True when an existing record no longer suppresses execution.

        Args:
            record: A previously stored record dict.

        Returns:
            True when the record is an expired completion or an abandoned claim.
        """
        now = time.time()
        status = record.get("status")
        if status == _STATUS_COMPLETED:
            return (now - float(record.get("completed_at", 0.0))) > self._ttl
        return (now - float(record.get("claimed_at", 0.0))) > self._pending_timeout

    @staticmethod
    def _read(path: Path) -> Optional[Dict[str, Any]]:
        """Read a record, returning None when it is missing or unreadable.

        Args:
            path: Record path.

        Returns:
            Parsed record dict, or None when the file is absent, empty, or not
            valid JSON (which happens when a claim was interrupted mid-write).
        """
        try:
            raw = path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            return None
        if not raw.strip():
            return None
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _discard(path: Path) -> None:
        """Delete a record, tolerating a concurrent deleter.

        Args:
            path: Record path.
        """
        try:
            path.unlink()
        except (FileNotFoundError, OSError):
            pass


def run_once(
    namespace: str,
    key: Optional[str],
    operation: Callable[[], Dict[str, Any]],
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> Dict[str, Any]:
    """Execute a non-idempotent operation at most once per idempotency key.

    Args:
        namespace: Logical operation family used to scope the key.
        key: Caller-supplied idempotency key, generated once per logical
            operation and reused across all its retries. When None or empty the
            operation runs unprotected, which preserves the previous behaviour
            for callers that have not adopted keys.
        operation: Zero-argument callable performing the underlying mutation.
        ttl_seconds: Replay window for a recorded outcome.

    Returns:
        The operation result, annotated with ``idempotency_key`` and
        ``idempotent_replay``. On a replay the recorded first outcome is
        returned and the underlying operation is not executed again.

    Raises:
        DuplicateOperationInFlight: If an identical logical operation is
            already executing and has not yet recorded an outcome.
    """
    if not key:
        return operation()

    store = IdempotencyStore(namespace, ttl_seconds=ttl_seconds)
    existing = store.claim(key)

    if existing is not None:
        if existing.get("status") == _STATUS_COMPLETED:
            replay = dict(existing.get("result") or {})
            replay["idempotency_key"] = key
            replay["idempotent_replay"] = True
            return replay
        raise DuplicateOperationInFlight(
            "An operation with idempotency key '{}' in namespace '{}' is "
            "already in flight. Query the upstream system for its outcome "
            "instead of reissuing the request under a new key.".format(
                key, namespace
            )
        )

    try:
        result = operation()
    except BaseException:
        store.release(key)
        raise

    store.complete(key, result)
    recorded = dict(result)
    recorded["idempotency_key"] = key
    recorded["idempotent_replay"] = False
    return recorded
