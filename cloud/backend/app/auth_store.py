from __future__ import annotations

import secrets
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .security import (
    hash_pairing_code,
    hash_password,
    hash_session_token,
    new_session_token,
    password_needs_rehash,
    verify_password,
)


SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS schema_meta (
    version INTEGER NOT NULL
);
DELETE FROM schema_meta
WHERE rowid NOT IN (SELECT MIN(rowid) FROM schema_meta);
CREATE UNIQUE INDEX IF NOT EXISTS schema_meta_singleton_unique ON schema_meta((1));

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS users_username_unique ON users(username);

CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY,
    device_id TEXT NOT NULL,
    owner_user_id INTEGER REFERENCES users(id),
    last_seen_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS devices_device_id_unique ON devices(device_id);

CREATE TABLE IF NOT EXISTS pairing_codes (
    id INTEGER PRIMARY KEY,
    device_id TEXT NOT NULL REFERENCES devices(device_id),
    code_hash TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    used_at INTEGER,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at INTEGER NOT NULL
);
DROP INDEX IF EXISTS pairing_codes_code_hash_unique;
CREATE INDEX IF NOT EXISTS pairing_codes_code_hash_index ON pairing_codes(code_hash);
CREATE INDEX IF NOT EXISTS pairing_codes_device_id_index ON pairing_codes(device_id);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    id_hash TEXT NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id),
    client_type TEXT NOT NULL DEFAULT 'browser' CHECK (client_type IN ('browser', 'pc')),
    expires_at INTEGER NOT NULL,
    revoked_at INTEGER,
    created_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS sessions_id_hash_unique ON sessions(id_hash);
"""

PAIRING_CODE_TTL_SECONDS = 600


class PairingError(Exception):
    """Raised when a pairing code cannot be consumed."""


@dataclass(frozen=True)
class UserRecord:
    id: int
    username: str
    password_hash: str
    role: str
    is_active: bool
    created_at: int
    updated_at: int


@dataclass(frozen=True)
class DeviceRecord:
    id: int
    device_id: str
    owner_user_id: int | None
    last_seen_at: int
    created_at: int
    updated_at: int


class AuthStore:
    def __init__(self, db_path: Path, *, pairing_secret: bytes):
        self.db_path = Path(db_path)
        if not isinstance(pairing_secret, bytes) or not pairing_secret:
            raise ValueError("pairing secret is required")
        self.pairing_secret = pairing_secret

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._operation() as db:
            db.executescript(SCHEMA_V1)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(sessions)")}
            if "client_type" not in columns:
                db.execute(
                    "ALTER TABLE sessions ADD COLUMN client_type TEXT NOT NULL DEFAULT 'browser' "
                    "CHECK (client_type IN ('browser', 'pc'))"
                )
            db.execute("INSERT OR IGNORE INTO schema_meta(version) VALUES (1)")

    def schema_version(self) -> int | None:
        with self._operation() as db:
            row = db.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
        return None if row is None or row["version"] is None else int(row["version"])

    def create_user(
        self, username: str, password_hash: str, role: str, *, now: int | None = None
    ) -> UserRecord:
        normalized = _normalize_username(username)
        if role not in {"admin", "user"}:
            raise ValueError("role must be admin or user")
        if not isinstance(password_hash, str) or not password_hash:
            raise ValueError("password hash is required")
        timestamp = _timestamp(now)
        with self._operation() as db:
            cursor = db.execute(
                """
                INSERT INTO users(username, password_hash, role, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (normalized, password_hash, role, timestamp, timestamp),
            )
            row = db.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return _user_from_row(row)

    def verify_login(
        self, username: str, password: str, *, now: int | None = None
    ) -> UserRecord | None:
        normalized = _normalize_username(username)
        timestamp = _timestamp(now)
        with self._operation() as db:
            row = db.execute(
                "SELECT * FROM users WHERE username = ? AND is_active = 1", (normalized,)
            ).fetchone()
            if row is None or not verify_password(row["password_hash"], password):
                return None
            if password_needs_rehash(row["password_hash"]):
                new_hash = hash_password(password)
                db.execute(
                    "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                    (new_hash, timestamp, row["id"]),
                )
                row = db.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
        return _user_from_row(row)

    def list_users(self) -> list[UserRecord]:
        with self._operation() as db:
            rows = db.execute("SELECT * FROM users ORDER BY id").fetchall()
        return [_user_from_row(row) for row in rows]

    def get_user(self, user_id: int) -> UserRecord | None:
        with self._operation() as db:
            row = db.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
        return None if row is None else _user_from_row(row)

    def set_user_active(
        self, user_id: int, is_active: bool, *, now: int | None = None
    ) -> UserRecord | None:
        timestamp = _timestamp(now)
        with self._operation() as db:
            db.execute(
                "UPDATE users SET is_active = ?, updated_at = ? WHERE id = ?",
                (int(bool(is_active)), timestamp, int(user_id)),
            )
            row = db.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
        return None if row is None else _user_from_row(row)

    def create_session(
        self,
        user_id: int,
        expires_at: int,
        *,
        token: str | None = None,
        client_type: str = "browser",
        now: int | None = None,
    ) -> str:
        raw_token = token or new_session_token()
        _validate_client_type(client_type)
        timestamp = _timestamp(now)
        with self._operation() as db:
            db.execute(
                """
                INSERT INTO sessions(id_hash, user_id, client_type, expires_at, created_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    hash_session_token(raw_token),
                    user_id,
                    client_type,
                    int(expires_at),
                    timestamp,
                    timestamp,
                ),
            )
        return raw_token

    def authenticate_session(
        self, token: str, *, client_type: str = "browser", now: int | None = None
    ) -> UserRecord | None:
        timestamp = _timestamp(now)
        token_hash = hash_session_token(token)
        _validate_client_type(client_type)
        with self._operation() as db:
            row = db.execute(
                """
                SELECT users.* FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.id_hash = ?
                  AND sessions.expires_at > ?
                  AND sessions.revoked_at IS NULL
                  AND sessions.client_type = ?
                  AND users.is_active = 1
                """,
                (token_hash, timestamp, client_type),
            ).fetchone()
            if row is None:
                return None
            db.execute(
                "UPDATE sessions SET last_seen_at = ? WHERE id_hash = ?",
                (timestamp, token_hash),
            )
        return _user_from_row(row)

    def revoke_session(self, token: str, *, now: int | None = None) -> None:
        with self._operation() as db:
            db.execute(
                "UPDATE sessions SET revoked_at = COALESCE(revoked_at, ?) WHERE id_hash = ?",
                (_timestamp(now), hash_session_token(token)),
            )

    def register_device(self, device_id: str, *, now: int | None = None) -> DeviceRecord:
        normalized = _normalize_device_id(device_id)
        timestamp = _timestamp(now)
        with self._operation() as db:
            db.execute(
                """
                INSERT INTO devices(device_id, last_seen_at, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    last_seen_at = MAX(devices.last_seen_at, excluded.last_seen_at),
                    updated_at = excluded.updated_at
                """,
                (normalized, timestamp, timestamp, timestamp),
            )
            row = db.execute("SELECT * FROM devices WHERE device_id = ?", (normalized,)).fetchone()
        return _device_from_row(row)

    def create_pairing_code(self, device_id: str, created_by: int, *, now: int | None = None) -> str:
        normalized = _normalize_device_id(device_id)
        timestamp = _timestamp(now)
        with self._operation() as db:
            db.execute("BEGIN IMMEDIATE")
            device = db.execute(
                "SELECT owner_user_id FROM devices WHERE device_id = ?", (normalized,)
            ).fetchone()
            if device is None or device["owner_user_id"] is not None:
                raise PairingError("device is unavailable for pairing")
            db.execute(
                """
                UPDATE pairing_codes
                SET expires_at = ?
                WHERE device_id = ? AND used_at IS NULL AND expires_at > ?
                """,
                (timestamp, normalized, timestamp),
            )
            for _ in range(10):
                code = f"{secrets.randbelow(1_000_000):06d}"
                code_hash = hash_pairing_code(self.pairing_secret, code)
                active = db.execute(
                    """
                    SELECT 1 FROM pairing_codes
                    WHERE code_hash = ? AND used_at IS NULL AND expires_at > ?
                    """,
                    (code_hash, timestamp),
                ).fetchone()
                if active is not None:
                    continue
                db.execute(
                    """
                    INSERT INTO pairing_codes(device_id, code_hash, expires_at, created_by, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        normalized,
                        code_hash,
                        timestamp + PAIRING_CODE_TTL_SECONDS,
                        created_by,
                        timestamp,
                    ),
                )
                return code
        raise PairingError("unable to create pairing code")

    def consume_pairing_code(self, code: str, user_id: int, *, now: int | None = None) -> str:
        timestamp = _timestamp(now)
        code_hash = hash_pairing_code(self.pairing_secret, code)
        with self._operation() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """
                SELECT pairing_codes.id, pairing_codes.device_id, pairing_codes.expires_at,
                       pairing_codes.used_at, devices.owner_user_id
                FROM pairing_codes
                JOIN devices ON devices.device_id = pairing_codes.device_id
                WHERE pairing_codes.code_hash = ?
                  AND pairing_codes.used_at IS NULL
                  AND pairing_codes.expires_at > ?
                """,
                (code_hash, timestamp),
            ).fetchone()
            user = db.execute(
                "SELECT id FROM users WHERE id = ? AND is_active = 1", (user_id,)
            ).fetchone()
            if (
                row is None
                or user is None
                or row["owner_user_id"] is not None
            ):
                raise PairingError("pairing code is invalid or expired")
            ownership = db.execute(
                """
                UPDATE devices SET owner_user_id = ?, updated_at = ?
                WHERE device_id = ? AND owner_user_id IS NULL
                """,
                (user_id, timestamp, row["device_id"]),
            )
            used = db.execute(
                "UPDATE pairing_codes SET used_at = ? WHERE id = ? AND used_at IS NULL",
                (timestamp, row["id"]),
            )
            if ownership.rowcount != 1 or used.rowcount != 1:
                raise PairingError("pairing code is invalid or expired")
            return str(row["device_id"])

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA journal_mode = WAL")
        db.execute("PRAGMA busy_timeout = 5000")
        return db

    @contextmanager
    def _operation(self) -> Iterator[sqlite3.Connection]:
        db = self._connect()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


def _normalize_username(username: str) -> str:
    if not isinstance(username, str):
        raise ValueError("username is required")
    normalized = username.strip().casefold()
    if not normalized:
        raise ValueError("username is required")
    return normalized


def _normalize_device_id(device_id: str) -> str:
    if not isinstance(device_id, str):
        raise ValueError("device id is required")
    normalized = device_id.strip()
    if not normalized:
        raise ValueError("device id is required")
    return normalized


def _timestamp(value: int | None) -> int:
    return int(time.time()) if value is None else int(value)


def _validate_client_type(client_type: str) -> None:
    if client_type not in {"browser", "pc"}:
        raise ValueError("client type must be browser or pc")


def _user_from_row(row: sqlite3.Row) -> UserRecord:
    return UserRecord(
        id=int(row["id"]),
        username=str(row["username"]),
        password_hash=str(row["password_hash"]),
        role=str(row["role"]),
        is_active=bool(row["is_active"]),
        created_at=int(row["created_at"]),
        updated_at=int(row["updated_at"]),
    )


def _device_from_row(row: sqlite3.Row) -> DeviceRecord:
    return DeviceRecord(
        id=int(row["id"]),
        device_id=str(row["device_id"]),
        owner_user_id=None if row["owner_user_id"] is None else int(row["owner_user_id"]),
        last_seen_at=int(row["last_seen_at"]),
        created_at=int(row["created_at"]),
        updated_at=int(row["updated_at"]),
    )
