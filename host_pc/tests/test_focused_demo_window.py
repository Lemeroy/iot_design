from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QApplication, QLabel, QPushButton

from stroke_host.demo.cloud_client import (
    AdviceSnapshot,
    AuthenticationRequired,
    CloudUnavailable,
    DeviceSnapshot,
    ScoreSnapshot,
)


_QT_APP = QApplication.instance() or QApplication([])


class FakeCloudClient:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def make_window():
    from stroke_host.demo.window import DemoWindow

    client = FakeCloudClient()
    window = DemoWindow(
        client_factory=lambda url: client,
        start_timers=False,
    )
    return window, client


def snapshot(*, online=True):
    return DeviceSnapshot(
        device_id="sg-0001",
        online=online,
        received_at=1_789_000_000.5,
        scores=ScoreSnapshot(
            face=None,
            speech=None,
            tongue=None,
            eye=None,
            csi=36,
            final=0,
        ),
        level="insufficient",
        reasons=("insufficient_modalities",),
        veto_by=(),
        advice=AdviceSnapshot(
            advice_text="请保持观察，如突发症状立即拨打120。",
            source="doubao-lite",
            ts=1_789_000_001,
        ),
    )


def test_window_starts_with_login_and_real_default_device():
    window, _ = make_window()
    try:
        assert window.current_view == "login"
        assert window.default_device_id == "sg-0001"
        assert window.findChild(QLabel, "brandTitle").text() == "卒中卫士"
        assert window.findChild(QPushButton, "loginButton") is not None
    finally:
        window.close()


def test_dashboard_has_only_six_real_monitoring_metrics_and_no_dev_sources():
    window, _ = make_window()
    try:
        names = ["face", "speech", "tongue", "eye", "csi", "final"]
        for name in names:
            assert window.findChild(QLabel, f"metric-{name}") is not None
        visible_copy = " ".join(label.text() for label in window.findChildren(QLabel))
        for forbidden in ("模拟", "FPS", "Record", "Perception", "synthetic-frame"):
            assert forbidden not in visible_copy
    finally:
        window.close()


def test_snapshot_renders_missing_modalities_without_synthetic_numbers():
    window, _ = make_window()
    try:
        window.show_dashboard()
        window.apply_snapshot(snapshot())

        assert window.findChild(QLabel, "metric-face").text() == "未接入"
        assert window.findChild(QLabel, "metric-speech").text() == "未接入"
        assert window.findChild(QLabel, "metric-tongue").text() == "未接入"
        assert window.findChild(QLabel, "metric-eye").text() == "未接入"
        assert window.findChild(QLabel, "metric-csi").text() == "36"
        assert window.findChild(QLabel, "metric-final").text() == "未形成"
        assert window.findChild(QLabel, "riskLevel").text() == "数据不足"
        assert "doubao-lite" in window.findChild(QLabel, "adviceMeta").text()
    finally:
        window.close()


def test_window_distinguishes_cloud_auth_device_and_missing_data_states():
    window, _ = make_window()
    try:
        window.show_dashboard()
        window.apply_cloud_error(CloudUnavailable("云端不可达"))
        assert window.findChild(QLabel, "connectionState").text() == "云端不可达"

        window.apply_cloud_error(AuthenticationRequired("登录失效"))
        assert window.current_view == "login"
        assert window.findChild(QLabel, "loginStatus").text() == "登录失效"

        window.show_dashboard()
        window.apply_snapshot(snapshot(online=False))
        assert window.findChild(QLabel, "connectionState").text() == "设备离线"

        window.apply_snapshot(
            DeviceSnapshot(
                device_id="sg-0001",
                online=True,
                received_at=None,
                scores=None,
                level=None,
                reasons=(),
                veto_by=(),
                advice=None,
            )
        )
        assert window.findChild(QLabel, "metric-csi").text() == "未接入"
    finally:
        window.close()


def test_maintenance_page_exposes_yaml_idf_com_and_guarded_erase():
    window, _ = make_window()
    try:
        window.show_maintenance()
        assert window.current_view == "maintenance"
        assert Path(window.firmware_path.text()).resolve() == Path(__file__).resolve().parents[2] / "firmware_esp32"
        for object_name in (
            "deploymentPath",
            "idfPath",
            "serialPort",
            "validateButton",
            "buildButton",
            "eraseButton",
            "flashButton",
            "monitorButton",
            "maintenanceLog",
        ):
            assert window.findChild(QObject, object_name) is not None
        erase = window.findChild(QPushButton, "eraseButton")
        assert erase.isEnabled() is False
        window.erase_ack.setChecked(True)
        window.port_combo.addItem("COM5", "COM5")
        window.port_combo.setCurrentIndex(0)
        window.refresh_erase_state()
        assert erase.isEnabled() is True
    finally:
        window.close()


def test_close_releases_cloud_client_and_maintenance_services():
    window, client = make_window()
    window.close()
    _QT_APP.processEvents()
    assert client.closed is True
