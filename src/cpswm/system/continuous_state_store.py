"""Single-writer local durable checkpoint for one continuous runtime.

SQLite FULL commits protect the last complete graph across process interruption.
The exclusive connection prevents two live owners. Source and dependency IDs
are deployment configuration, not assertions supplied by sensor observations.
External action execution still needs reconciliation after an uncertain outcome.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from cpswm.system.continuous_state_codec import StateCodec


class ContinuousStateStore:
    def __init__(self, path: Path, *, source_identity: str, dependency_identity: str):
        if any(
            len(v) != 64 or any(c not in "0123456789abcdef" for c in v)
            for v in (source_identity, dependency_identity)
        ):
            raise ValueError("checkpoint source/dependency identities require SHA256")
        self.source_identity = source_identity
        self.dependency_identity = dependency_identity
        self._db = sqlite3.connect(path, timeout=0, check_same_thread=False)
        try:
            self._db.execute("PRAGMA locking_mode=EXCLUSIVE")
            self._db.execute("PRAGMA journal_mode=DELETE")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS checkpoint (id INTEGER PRIMARY KEY CHECK(id=1), "
                "generation INTEGER NOT NULL, source TEXT NOT NULL, dependencies TEXT NOT NULL, "
                "document TEXT NOT NULL, digest TEXT NOT NULL)"
            )
            self._db.commit()
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS effects (effect_key TEXT PRIMARY KEY, "
                "request_hash TEXT NOT NULL, result TEXT, digest TEXT)"
            )
            self._db.commit()
            row = self._db.execute(
                "SELECT generation, source, dependencies FROM checkpoint WHERE id=1"
            ).fetchone()
            self.generation = 0 if row is None else row[0]
            if row is not None and row[1:] != (source_identity, dependency_identity):
                raise ValueError(
                    "checkpoint source or dependencies differ; explicit migration required"
                )
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS deployment (id INTEGER PRIMARY KEY CHECK(id=1), "
                "source TEXT NOT NULL, dependencies TEXT NOT NULL)"
            )
            binding = self._db.execute(
                "SELECT source,dependencies FROM deployment WHERE id=1"
            ).fetchone()
            if binding is None:
                if self._db.execute("SELECT 1 FROM effects LIMIT 1").fetchone() is not None:
                    raise ValueError("unbound historical effects require explicit migration")
                self._db.execute(
                    "INSERT INTO deployment VALUES (1,?,?)", (source_identity, dependency_identity)
                )
                self._db.commit()
            elif binding != (source_identity, dependency_identity):
                raise ValueError("deployment source or dependencies differ")
        except BaseException:
            self._db.close()
            raise

    @property
    def empty(self) -> bool:
        return self.generation == 0

    def save(self, state: object) -> None:
        document = StateCodec().dumps(state)
        digest = hashlib.sha256(document.encode()).hexdigest()
        with self._db:
            row = self._db.execute("SELECT generation FROM checkpoint WHERE id=1").fetchone()
            if (0 if row is None else row[0]) != self.generation:
                raise RuntimeError("checkpoint generation changed under owner")
            self._db.execute(
                "INSERT OR REPLACE INTO checkpoint VALUES (1,?,?,?,?,?)",
                (
                    self.generation + 1,
                    self.source_identity,
                    self.dependency_identity,
                    document,
                    digest,
                ),
            )
        self.generation += 1

    def load(self) -> object:
        row = self._db.execute("SELECT document,digest FROM checkpoint WHERE id=1").fetchone()
        if row is None:
            raise ValueError("no checkpoint to resume")
        if hashlib.sha256(row[0].encode()).hexdigest() != row[1]:
            raise ValueError("checkpoint digest mismatch")
        return StateCodec().loads(row[0])

    def close(self) -> None:
        self._db.close()

    def execute_once(self, effect_key: str, request: object, executor):
        """Commit intent before dispatch; never redispatch an uncertain effect.

        A saved result may be reused by a rolled-back core transaction. A crash
        after physical execution but before receipt storage requires explicit
        transport reconciliation, not an optimistic retry.
        """
        from cpswm.system.reproducibility import content_sha256

        request_hash = content_sha256(request)
        row = self._db.execute(
            "SELECT request_hash,result,digest FROM effects WHERE effect_key=?", (effect_key,)
        ).fetchone()
        if row is not None:
            if row[0] != request_hash:
                raise ValueError("durable effect request changed on retry")
            if row[1] is None:
                raise RuntimeError("OUTCOME_UNCERTAIN: reconcile effect before retry")
            if hashlib.sha256(row[1].encode()).hexdigest() != row[2]:
                raise ValueError("effect receipt digest mismatch")
            return StateCodec().loads(row[1])
        with self._db:
            self._db.execute(
                "INSERT INTO effects VALUES (?,?,NULL,NULL)", (effect_key, request_hash)
            )
        result = executor(request)
        self.reconcile_effect(effect_key, request, result)
        return result

    def reconcile_effect(self, effect_key: str, request: object, result: object) -> None:
        """Accept the configured transport's recovered receipt for a pending intent."""
        from cpswm.system.reproducibility import content_sha256

        document = StateCodec().dumps(result)
        digest = hashlib.sha256(document.encode()).hexdigest()
        with self._db:
            row = self._db.execute(
                "SELECT request_hash,result,digest FROM effects WHERE effect_key=?", (effect_key,)
            ).fetchone()
            if row is None or row[0] != content_sha256(request):
                raise ValueError("receipt does not match a recorded effect request")
            if row[1] is not None:
                if row[2] != digest:
                    raise ValueError("conflicting durable effect receipt")
                return
            self._db.execute(
                "UPDATE effects SET result=?,digest=? WHERE effect_key=?",
                (document, digest, effect_key),
            )
