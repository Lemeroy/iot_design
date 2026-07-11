"""pytest fixtures: 让 keyring 在测试中不弹窗/不污染系统凭据."""
import base64
import secrets

import keyring
import keyring.backend
import pytest


class _InMemoryKeyring(keyring.backend.KeyringBackend):
    priority = 100

    def __init__(self):
        self._store = {}

    def get_password(self, service, username):
        return self._store.get((service, username))

    def set_password(self, service, username, password):
        self._store[(service, username)] = password

    def delete_password(self, service, username):
        self._store.pop((service, username), None)


@pytest.fixture(autouse=True)
def _use_in_memory_keyring():
    """所有测试自动切到内存 keyring, 避免污染 Windows 凭据管理器."""
    original = keyring.get_keyring()
    kr = _InMemoryKeyring()
    # 预置一个固定 master key, 保证多个测试可互相解密
    kr.set_password("StrokeGuard", "master-key",
                    base64.b64encode(b"\x01" * 32).decode("ascii"))
    keyring.set_keyring(kr)
    yield
    keyring.set_keyring(original)
