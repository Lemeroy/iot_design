"""Stoppable serial monitor with deterministic port release."""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Callable

import serial
from serial.tools import list_ports


COM_PORT_RE = re.compile(r"^COM[1-9][0-9]{0,2}$", re.IGNORECASE)


class SerialMonitorError(RuntimeError):
    pass


@dataclass(frozen=True)
class SerialPortInfo:
    device: str
    description: str
    hwid: str


def list_serial_ports(*, comports: Callable = list_ports.comports) -> list[SerialPortInfo]:
    return sorted(
        (
            SerialPortInfo(
                device=str(port.device),
                description=str(port.description),
                hwid=str(port.hwid),
            )
            for port in comports()
        ),
        key=lambda item: item.device,
    )


class SerialMonitor:
    def __init__(self, *, serial_factory: Callable = serial.Serial) -> None:
        self._serial_factory = serial_factory
        self._serial = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._error: Exception | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def error(self) -> Exception | None:
        return self._error

    def start(self, port: str, baud: int, on_line: Callable[[str], None]) -> None:
        if self.running:
            raise SerialMonitorError("serial monitor is already running")
        normalized = port.strip().upper()
        if not COM_PORT_RE.fullmatch(normalized):
            raise SerialMonitorError("invalid COM port")
        if baud not in {115200, 460800, 921600}:
            raise SerialMonitorError("unsupported baud rate")
        self._stop.clear()
        self._error = None
        self._thread = threading.Thread(
            target=self._read_loop,
            args=(normalized, baud, on_line),
            name="strokeguard-serial-monitor",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        serial_port = self._serial
        if serial_port is not None:
            serial_port.close()
            self._serial = None
        self._thread = None

    def _read_loop(self, port: str, baud: int, on_line: Callable[[str], None]) -> None:
        try:
            self._serial = self._serial_factory(port=port, baudrate=baud, timeout=0.1)
            while not self._stop.is_set():
                raw = self._serial.readline()
                if raw:
                    on_line(raw.decode("utf-8", errors="replace").rstrip("\r\n"))
        except Exception as exc:
            self._error = exc
        finally:
            serial_port = self._serial
            if serial_port is not None:
                serial_port.close()
                self._serial = None

