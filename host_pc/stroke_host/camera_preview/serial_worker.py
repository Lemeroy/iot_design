from __future__ import annotations

from collections import deque
import threading
import time
from typing import Protocol

import serial
from PyQt5.QtCore import QThread, pyqtSignal

from .protocol import PreviewFrame, PreviewProtocolError, PreviewStreamParser


REQUEST_FRAME = b"\xA5"


class SerialLike(Protocol):
    @property
    def in_waiting(self) -> int: ...

    def write(self, data: bytes) -> int: ...

    def read(self, size: int) -> bytes: ...

    def close(self) -> None: ...


class PreviewTimeout(TimeoutError):
    pass


class CameraPreviewSession:
    def __init__(self, serial_port: SerialLike, timeout: float = 2.0) -> None:
        self._serial = serial_port
        self._timeout = timeout
        self._parser = PreviewStreamParser()
        self._pending: deque[PreviewFrame] = deque()

    def next_frame(self) -> PreviewFrame:
        if self._pending:
            return self._pending.popleft()
        if self._serial.write(REQUEST_FRAME) != len(REQUEST_FRAME):
            raise OSError("camera preview request was not written")

        deadline = time.monotonic() + self._timeout
        while time.monotonic() <= deadline:
            waiting = max(1, int(self._serial.in_waiting))
            data = self._serial.read(min(waiting, 64 * 1024))
            if not data:
                continue
            self._pending.extend(self._parser.feed(data))
            if self._pending:
                frame = self._pending.popleft()
                if frame.error:
                    raise PreviewProtocolError("camera JPEG conversion failed")
                return frame
        raise PreviewTimeout("camera did not return a frame")

    def close(self) -> None:
        self._serial.close()


class CameraPreviewWorker(QThread):
    frame_ready = pyqtSignal(object)
    status_changed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self, port: str, baudrate: int = 921600, parent=None
    ) -> None:
        super().__init__(parent)
        self.port = port
        self.baudrate = baudrate
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        session = None
        try:
            serial_port = serial.Serial(
                self.port,
                self.baudrate,
                timeout=0.1,
                write_timeout=1.0,
            )
            session = CameraPreviewSession(serial_port)
            self.status_changed.emit(f"Connected: {self.port}")
            while not self._stop.is_set():
                try:
                    frame = session.next_frame()
                except PreviewTimeout:
                    self.status_changed.emit("Waiting for camera frame")
                    continue
                self.frame_ready.emit(frame)
                self.msleep(80)
        except Exception as exc:
            if not self._stop.is_set():
                self.failed.emit(str(exc))
        finally:
            if session is not None:
                session.close()
            self.status_changed.emit("Disconnected")
