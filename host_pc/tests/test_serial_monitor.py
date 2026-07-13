from __future__ import annotations

import threading
import time


class FakeSerial:
    def __init__(self, *args, **kwargs):
        self.lines = [b"boot ok\n", b"MQTT connected\n"]
        self.closed = False

    def readline(self):
        if self.lines:
            return self.lines.pop(0)
        time.sleep(0.01)
        return b""

    def close(self):
        self.closed = True


def test_list_serial_ports_returns_stable_device_information():
    from stroke_host.deployment.serial_monitor import list_serial_ports

    class Port:
        device = "COM5"
        description = "USB JTAG/serial debug unit"
        hwid = "USB VID:PID=303A:1001"

    ports = list_serial_ports(comports=lambda: [Port()])

    assert len(ports) == 1
    assert ports[0].device == "COM5"
    assert ports[0].description.startswith("USB")


def test_serial_monitor_streams_lines_and_releases_port():
    from stroke_host.deployment.serial_monitor import SerialMonitor

    created = []
    lines = []
    ready = threading.Event()

    def factory(*args, **kwargs):
        serial = FakeSerial(*args, **kwargs)
        created.append(serial)
        return serial

    def on_line(line):
        lines.append(line)
        if len(lines) == 2:
            ready.set()

    monitor = SerialMonitor(serial_factory=factory)
    monitor.start("COM5", 115200, on_line)
    assert ready.wait(1)
    monitor.stop()

    assert lines == ["boot ok", "MQTT connected"]
    assert created[0].closed is True
    assert monitor.running is False


def test_serial_monitor_rejects_invalid_port_name():
    from stroke_host.deployment.serial_monitor import SerialMonitor, SerialMonitorError

    monitor = SerialMonitor(serial_factory=FakeSerial)

    try:
        monitor.start("COM5 & whoami", 115200, lambda line: None)
    except SerialMonitorError as exc:
        assert "COM port" in str(exc)
    else:
        raise AssertionError("invalid port was accepted")
