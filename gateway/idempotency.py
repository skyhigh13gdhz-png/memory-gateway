from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class IdempotencyDecision:
    action: str  # execute | replay | conflict | blocked
    response: dict[str, Any] | None = None
    state: str | None = None


def request_digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class IdempotencyStore:
    """Small persistent at-most-once ledger for Retain requests.

    Explicit keys remain durable. Automatic fingerprint entries replay only
    inside a bounded window, while pending/uncertain entries never expire
    automatically because resending them could create a duplicate document.
    """

    def __init__(self, path: Path, automatic_window_seconds: int = 900) -> None:
        self.path = path
        self.automatic_window_seconds = automatic_window_seconds
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS retain_idempotency (
                scope TEXT NOT NULL,
                key TEXT NOT NULL,
                request_digest TEXT NOT NULL,
                key_kind TEXT NOT NULL,
                state TEXT NOT NULL,
                response_json TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (scope, key)
            )
            """
        )
        return connection

    def begin(self, scope: str, key: str, digest: str, *, explicit: bool) -> IdempotencyDecision:
        now = time.time()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                DELETE FROM retain_idempotency
                WHERE key_kind = 'automatic' AND state = 'completed' AND created_at < ?
                """,
                (now - self.automatic_window_seconds,),
            )
            row = connection.execute(
                "SELECT * FROM retain_idempotency WHERE scope = ? AND key = ?",
                (scope, key),
            ).fetchone()
            if row is not None and row["request_digest"] != digest:
                return IdempotencyDecision("conflict", state=str(row["state"]))
            if row is not None:
                age = now - float(row["created_at"])
                if row["state"] == "completed":
                    if row["key_kind"] == "automatic" and age > self.automatic_window_seconds:
                        connection.execute(
                            "DELETE FROM retain_idempotency WHERE scope = ? AND key = ?",
                            (scope, key),
                        )
                    else:
                        response = json.loads(row["response_json"]) if row["response_json"] else None
                        return IdempotencyDecision("replay", response=response, state="completed")
                else:
                    return IdempotencyDecision("blocked", state=str(row["state"]))
            connection.execute(
                """
                INSERT INTO retain_idempotency
                    (scope, key, request_digest, key_kind, state, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?)
                """,
                (scope, key, digest, "explicit" if explicit else "automatic", now, now),
            )
            return IdempotencyDecision("execute", state="pending")

    def complete(self, scope: str, key: str, response: dict[str, Any]) -> None:
        serialized = json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE retain_idempotency
                SET state = 'completed', response_json = ?, updated_at = ?
                WHERE scope = ? AND key = ?
                """,
                (serialized, time.time(), scope, key),
            )

    def mark_uncertain(self, scope: str, key: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE retain_idempotency
                SET state = 'uncertain', updated_at = ?
                WHERE scope = ? AND key = ?
                """,
                (time.time(), scope, key),
            )
