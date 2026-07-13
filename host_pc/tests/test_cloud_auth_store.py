from __future__ import annotations

import threading
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from cloud.backend.app.auth_store import AuthStore, PairingError
from cloud.backend.app.security import (
    hash_pairing_code,
    hash_password,
    hash_session_token,
    new_session_token,
    verify_password,
)


PAIRING_SECRET = b"p" * 32
PASSWORD = "StrongPass123!"


def make_store(tmp_path: Path) -> AuthStore:
    store = AuthStore(tmp_path / "auth.db", pairing_secret=PAIRING_SECRET)
    store.initialize()
    return store


def test_initialize_creates_versioned_schema(tmp_path):
    store = AuthStore(tmp_path / "auth.db", pairing_secret=PAIRING_SECRET)

    store.initialize()

    assert store.schema_version() == 1


def test_initialize_keeps_exactly_one_authoritative_version_row(tmp_path):
    store = AuthStore(tmp_path / "auth.db", pairing_secret=PAIRING_SECRET)

    store.initialize()
    store.initialize()
    store.initialize()

    db = sqlite3.connect(tmp_path / "auth.db")
    try:
        versions = db.execute("SELECT version FROM schema_meta").fetchall()
    finally:
        db.close()
    assert versions == [(1,)]


def test_password_hash_verifies_only_the_original_password():
    password_hash = hash_password(PASSWORD)

    assert password_hash != PASSWORD
    assert verify_password(password_hash, PASSWORD)
    assert not verify_password(password_hash, "WrongPass123!")


def test_pairing_code_hash_requires_exactly_six_decimal_digits():
    assert hash_pairing_code(PAIRING_SECRET, "012345")
    for invalid in ("12345", "1234567", "12a456", " 12345", "12345 "):
        with pytest.raises(ValueError, match="six digits"):
            hash_pairing_code(PAIRING_SECRET, invalid)


def test_session_tokens_are_random_and_only_the_hash_is_persisted(tmp_path):
    store = make_store(tmp_path)
    user = store.create_user("admin", hash_password(PASSWORD), "admin", now=100)
    first = new_session_token()
    second = new_session_token()

    assert first != second
    assert hash_session_token(first) != first
    store.create_session(user.id, expires_at=200, token=first, now=100)

    assert store.authenticate_session(first, now=199).id == user.id
    assert store.authenticate_session(first, now=200) is None
    assert first.encode("ascii") not in (tmp_path / "auth.db").read_bytes()


def test_session_client_type_is_persisted_and_required_for_authentication(tmp_path):
    store = make_store(tmp_path)
    user = store.create_user("admin", hash_password(PASSWORD), "admin", now=100)
    token = store.create_session(
        user.id, expires_at=200, token="pc-session", client_type="pc", now=100
    )

    assert store.authenticate_session(token, client_type="pc", now=101).id == user.id
    assert store.authenticate_session(token, client_type="browser", now=101) is None
    db = sqlite3.connect(tmp_path / "auth.db")
    try:
        assert db.execute("SELECT client_type FROM sessions").fetchone() == ("pc",)
    finally:
        db.close()


def test_revoked_session_cannot_authenticate(tmp_path):
    store = make_store(tmp_path)
    user = store.create_user("admin", hash_password(PASSWORD), "admin", now=100)
    token = store.create_session(user.id, expires_at=200, token="session-token", now=100)

    store.revoke_session(token, now=101)

    assert store.authenticate_session(token, now=102) is None


def test_verify_login_normalizes_username_and_rejects_bad_password(tmp_path):
    store = make_store(tmp_path)
    created = store.create_user("  Family1  ", hash_password(PASSWORD), "user", now=100)

    logged_in = store.verify_login("FAMILY1", PASSWORD, now=101)

    assert created.username == "family1"
    assert logged_in is not None
    assert logged_in.id == created.id
    assert store.verify_login("family1", "WrongPass123!", now=101) is None


def test_admin_user_management_lists_gets_and_deactivates_users(tmp_path):
    store = make_store(tmp_path)
    admin = store.create_user("admin", hash_password(PASSWORD), "admin", now=100)
    user = store.create_user("family1", hash_password(PASSWORD), "user", now=100)

    assert [record.id for record in store.list_users()] == [admin.id, user.id]
    assert store.get_user(user.id) == user
    assert store.set_user_active(user.id, False, now=101).is_active is False
    assert store.verify_login("family1", PASSWORD, now=102) is None


def test_register_device_is_idempotent_and_updates_last_seen(tmp_path):
    store = make_store(tmp_path)

    first = store.register_device("sg-0001", now=100)
    second = store.register_device("sg-0001", now=101)

    assert first.id == second.id
    assert second.last_seen_at == 101
    assert second.owner_user_id is None


def test_pairing_code_is_single_use_and_never_stored_plaintext(tmp_path):
    store = make_store(tmp_path)
    admin = store.create_user("admin", hash_password(PASSWORD), "admin", now=100)
    store.register_device("sg-0001", now=100)
    code = store.create_pairing_code("sg-0001", admin.id, now=100)
    raw_db = (tmp_path / "auth.db").read_bytes()
    assert code.encode() not in raw_db
    user = store.create_user("user1", hash_password(PASSWORD), "user", now=100)

    assert store.consume_pairing_code(code, user.id, now=101) == "sg-0001"
    with pytest.raises(PairingError):
        store.consume_pairing_code(code, user.id, now=102)


def test_new_pairing_code_invalidates_previous_unused_code(tmp_path):
    store = make_store(tmp_path)
    admin = store.create_user("admin", hash_password(PASSWORD), "admin", now=100)
    user = store.create_user("user1", hash_password(PASSWORD), "user", now=100)
    store.register_device("sg-0001", now=100)
    old_code = store.create_pairing_code("sg-0001", admin.id, now=100)
    new_code = store.create_pairing_code("sg-0001", admin.id, now=101)

    with pytest.raises(PairingError):
        store.consume_pairing_code(old_code, user.id, now=102)
    assert store.consume_pairing_code(new_code, user.id, now=102) == "sg-0001"


def test_pairing_code_expires_after_ten_minutes(tmp_path):
    store = make_store(tmp_path)
    admin = store.create_user("admin", hash_password(PASSWORD), "admin", now=100)
    user = store.create_user("user1", hash_password(PASSWORD), "user", now=100)
    store.register_device("sg-0001", now=100)
    code = store.create_pairing_code("sg-0001", admin.id, now=100)

    with pytest.raises(PairingError):
        store.consume_pairing_code(code, user.id, now=700)


def test_pairing_hash_can_be_reused_after_consumption(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    admin = store.create_user("admin", hash_password(PASSWORD), "admin", now=100)
    first_user = store.create_user("user1", hash_password(PASSWORD), "user", now=100)
    second_user = store.create_user("user2", hash_password(PASSWORD), "user", now=100)
    monkeypatch.setattr("cloud.backend.app.auth_store.secrets.randbelow", lambda _: 123456)
    store.register_device("sg-0001", now=100)
    first_code = store.create_pairing_code("sg-0001", admin.id, now=100)
    assert store.consume_pairing_code(first_code, first_user.id, now=101) == "sg-0001"
    store.register_device("sg-0002", now=101)

    second_code = store.create_pairing_code("sg-0002", admin.id, now=101)

    assert second_code == first_code == "123456"
    assert store.consume_pairing_code(second_code, second_user.id, now=102) == "sg-0002"


def test_pairing_hash_can_be_reused_after_expiry(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    admin = store.create_user("admin", hash_password(PASSWORD), "admin", now=100)
    user = store.create_user("user1", hash_password(PASSWORD), "user", now=100)
    monkeypatch.setattr("cloud.backend.app.auth_store.secrets.randbelow", lambda _: 123456)
    store.register_device("sg-0001", now=100)
    first_code = store.create_pairing_code("sg-0001", admin.id, now=100)

    second_code = store.create_pairing_code("sg-0001", admin.id, now=701)

    assert second_code == first_code == "123456"
    assert store.consume_pairing_code(second_code, user.id, now=702) == "sg-0001"


def test_active_pairing_hash_collision_retries_with_a_new_code(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    admin = store.create_user("admin", hash_password(PASSWORD), "admin", now=100)
    values = iter((123456, 123456, 654321))
    monkeypatch.setattr(
        "cloud.backend.app.auth_store.secrets.randbelow", lambda _: next(values)
    )
    store.register_device("sg-0001", now=100)
    first_code = store.create_pairing_code("sg-0001", admin.id, now=100)
    store.register_device("sg-0002", now=100)

    second_code = store.create_pairing_code("sg-0002", admin.id, now=100)

    assert first_code == "123456"
    assert second_code == "654321"


def test_concurrent_pairing_consumption_has_exactly_one_winner(tmp_path):
    store = make_store(tmp_path)
    admin = store.create_user("admin", hash_password(PASSWORD), "admin", now=100)
    first_user = store.create_user("user1", hash_password(PASSWORD), "user", now=100)
    second_user = store.create_user("user2", hash_password(PASSWORD), "user", now=100)
    store.register_device("sg-0001", now=100)
    code = store.create_pairing_code("sg-0001", admin.id, now=100)
    barrier = threading.Barrier(2)

    def consume(user_id: int) -> str | None:
        barrier.wait()
        try:
            return store.consume_pairing_code(code, user_id, now=101)
        except PairingError:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(consume, (first_user.id, second_user.id)))

    assert results.count("sg-0001") == 1
    assert results.count(None) == 1
