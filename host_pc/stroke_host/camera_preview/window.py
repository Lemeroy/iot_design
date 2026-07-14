from __future__ import annotations

import time

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from serial.tools import list_ports

from .protocol import PreviewFrame
from .serial_worker import CameraPreviewWorker


class CameraPreviewWindow(QMainWindow):
    def __init__(self, initial_port: str = "COM4") -> None:
        super().__init__()
        self._initial_port = initial_port
        self._worker: CameraPreviewWorker | None = None
        self._last_frame_at: float | None = None
        self._build_ui()
        self._refresh_ports()

    def _build_ui(self) -> None:
        self.setWindowTitle("StrokeGuard Camera Debug Preview")
        self.resize(900, 720)
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #15191d; color: #eef2f4; }
            QFrame#toolbar { background: #20262b; border: 1px solid #343c42; }
            QComboBox, QPushButton { min-height: 34px; padding: 0 12px; }
            QPushButton { background: #2d7d68; border: 0; color: white; }
            QPushButton:hover { background: #36947b; }
            QLabel#camera { background: #090b0d; border: 1px solid #343c42; }
            QLabel#status { color: #a8b4bb; }
            """
        )

        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        toolbar = QFrame(root)
        toolbar.setObjectName("toolbar")
        bar = QHBoxLayout(toolbar)
        bar.setContentsMargins(10, 8, 10, 8)
        self.port_combo = QComboBox(toolbar)
        self.refresh_button = QPushButton("Refresh ports", toolbar)
        self.connect_button = QPushButton("Connect", toolbar)
        self.refresh_button.clicked.connect(self._refresh_ports)
        self.connect_button.clicked.connect(self._toggle_connection)
        bar.addWidget(QLabel("Camera port", toolbar))
        bar.addWidget(self.port_combo, 1)
        bar.addWidget(self.refresh_button)
        bar.addWidget(self.connect_button)
        layout.addWidget(toolbar)

        self.camera_label = QLabel("Camera offline", root)
        self.camera_label.setObjectName("camera")
        self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setMinimumSize(640, 480)
        layout.addWidget(self.camera_label, 1)

        status_row = QHBoxLayout()
        self.status_label = QLabel("Disconnected", root)
        self.status_label.setObjectName("status")
        self.telemetry_label = QLabel("No frames", root)
        status_row.addWidget(self.status_label, 1)
        status_row.addWidget(self.telemetry_label)
        layout.addLayout(status_row)
        self.setCentralWidget(root)

    def _refresh_ports(self) -> None:
        selected = self.port_combo.currentText() or self._initial_port
        ports = [item.device for item in list_ports.comports()]
        self.port_combo.clear()
        self.port_combo.addItems(ports)
        target = self.port_combo.findText(selected)
        if target < 0:
            target = self.port_combo.findText(self._initial_port)
        if target >= 0:
            self.port_combo.setCurrentIndex(target)

    def _toggle_connection(self) -> None:
        if self._worker is not None:
            self._disconnect()
            return
        port = self.port_combo.currentText().strip()
        if not port:
            self.status_label.setText("No serial port selected")
            return
        worker = CameraPreviewWorker(port, parent=self)
        worker.frame_ready.connect(self._show_frame)
        worker.status_changed.connect(self.status_label.setText)
        worker.failed.connect(self._show_error)
        worker.finished.connect(self._worker_finished)
        self._worker = worker
        self.connect_button.setText("Disconnect")
        self.port_combo.setEnabled(False)
        self.refresh_button.setEnabled(False)
        worker.start()

    def _disconnect(self) -> None:
        if self._worker is not None:
            self._worker.stop()
            self._worker.wait(3000)
        self._worker_finished()

    def _worker_finished(self) -> None:
        self._worker = None
        self.connect_button.setText("Connect")
        self.port_combo.setEnabled(True)
        self.refresh_button.setEnabled(True)

    def _show_error(self, message: str) -> None:
        self.status_label.setText(f"Error: {message}")

    def _show_frame(self, frame: PreviewFrame) -> None:
        image = QImage.fromData(frame.jpeg, "JPEG")
        if image.isNull():
            self._show_error("Invalid JPEG image")
            return

        pixmap = QPixmap.fromImage(image)
        cx, cy, width, height = frame.bbox
        if width and height:
            painter = QPainter(pixmap)
            painter.setPen(QPen(QColor("#29d39a"), 3))
            box_width = width * pixmap.width() / 255
            box_height = height * pixmap.height() / 255
            left = cx * pixmap.width() / 255 - box_width / 2
            top = cy * pixmap.height() / 255 - box_height / 2
            painter.drawRect(int(left), int(top), int(box_width), int(box_height))
            painter.end()

        shown = pixmap.scaled(
            self.camera_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.camera_label.setPixmap(shown)

        now = time.monotonic()
        fps = 0.0 if self._last_frame_at is None else 1.0 / max(now - self._last_frame_at, 1e-3)
        self._last_frame_at = now
        face = "face" if width and height else "no face"
        self.telemetry_label.setText(
            f"seq {frame.sequence}  {len(frame.jpeg) / 1024:.1f} KiB  {fps:.1f} FPS  {face}"
        )

    def closeEvent(self, event) -> None:
        self._disconnect()
        super().closeEvent(event)
