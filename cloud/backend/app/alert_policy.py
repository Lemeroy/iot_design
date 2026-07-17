"""Per-device screening alert state for cloud notifications."""
from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class _AlertSession:
    active: bool = False
    warning_count: int = 0
    warning_dispatched: bool = False
    danger_dispatched: bool = False
    pending_level: str | None = None


class AlertCoordinator:
    """Apply one-shot alert rules independently for each screening device."""

    def __init__(self) -> None:
        self._sessions: dict[str, _AlertSession] = {}
        self._lock = threading.RLock()

    def start(self, device_id: str) -> None:
        with self._lock:
            self._sessions[device_id] = _AlertSession(active=True)

    def cancel(self, device_id: str) -> None:
        with self._lock:
            self._sessions[device_id] = _AlertSession()

    def observe(self, device_id: str, level: str) -> str | None:
        with self._lock:
            session = self._sessions.setdefault(device_id, _AlertSession())
            if not session.active:
                return None
            if level in {"normal", "insufficient"}:
                session.warning_count = 0
                return None
            if level == "danger":
                session.warning_count = 0
                if session.danger_dispatched or session.pending_level == "danger":
                    return None
                session.pending_level = "danger"
                return "danger"
            if level != "warning":
                return None
            if session.warning_dispatched or session.pending_level == "warning":
                return None
            session.warning_count += 1
            if session.warning_count < 3:
                return None
            session.pending_level = "warning"
            return "warning"

    def mark_dispatched(self, device_id: str, level: str) -> None:
        with self._lock:
            session = self._sessions.setdefault(device_id, _AlertSession())
            if level == "warning":
                session.warning_dispatched = True
            elif level == "danger":
                session.danger_dispatched = True
            if session.pending_level == level:
                session.pending_level = None
