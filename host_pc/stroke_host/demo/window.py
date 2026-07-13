"""Focused real-device presentation and maintenance desktop application."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

import yaml
from PyQt5.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QCloseEvent
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..deployment.idf_runner import IdfInstallation, IdfRunner, IdfRunnerError
from ..deployment.schema import (
    DeploymentConfig,
    DeploymentValidationError,
    validate_deployment,
)
from ..deployment.serial_monitor import SerialMonitor, list_serial_ports
from .cloud_client import (
    AuthenticationRequired,
    CloudClient,
    CloudUnavailable,
    DemoCloudError,
    DeviceOffline,
    DeviceSnapshot,
)
from .theme import APP_STYLE, COLORS, metric_color


DEFAULT_VPS_URL = os.environ.get("STROKEGUARD_DEMO_URL", "http://106.75.229.61:8000")
DEFAULT_DEVICE_ID = os.environ.get("STROKEGUARD_DEVICE_ID", "sg-0001")
METRICS = (
    ("face", "F · 面部对称"),
    ("speech", "S · 言语清晰"),
    ("tongue", "T · 舌偏辅助"),
    ("eye", "E · 眼动"),
    ("csi", "B · CSI 稳定性"),
    ("final", "融合评分"),
)
LEVEL_TEXT = {
    "normal": "状态平稳",
    "warning": "需要关注",
    "danger": "高风险提醒",
    "insufficient": "数据不足",
}


class _TaskSignals(QObject):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(object)


class _Task(QRunnable):
    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = _TaskSignals()

    def run(self) -> None:
        try:
            self.signals.succeeded.emit(self.fn())
        except Exception as exc:
            self.signals.failed.emit(exc)


class DemoWindow(QMainWindow):
    maintenance_log_signal = pyqtSignal(str)

    def __init__(
        self,
        *,
        client_factory: Callable[[str], CloudClient] = CloudClient,
        start_timers: bool = True,
    ) -> None:
        super().__init__()
        self.default_device_id = DEFAULT_DEVICE_ID
        self._client_factory = client_factory
        self._client = client_factory(DEFAULT_VPS_URL)
        self._start_timers = start_timers
        self._thread_pool = QThreadPool(self)
        self._serial_monitor = SerialMonitor()
        self._idf_runner: IdfRunner | None = None
        self._deployment: DeploymentConfig | None = None
        self._closed = False
        self._maintenance_busy = False
        self.maintenance_log_signal.connect(self._append_log_ui)

        self.setWindowTitle("卒中卫士 · 实时演示与设备维护")
        self.resize(1240, 780)
        self.setMinimumSize(1060, 680)
        self.setStyleSheet(APP_STYLE)

        root = QWidget()
        root.setObjectName("appRoot")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        layout.addWidget(self._build_top_bar())

        self.stack = QStackedWidget()
        self.login_page = self._build_login_page()
        self.dashboard_page = self._build_dashboard_page()
        self.maintenance_page = self._build_maintenance_page()
        self.stack.addWidget(self.login_page)
        self.stack.addWidget(self.dashboard_page)
        self.stack.addWidget(self.maintenance_page)
        layout.addWidget(self.stack, 1)

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(5000)
        self.poll_timer.timeout.connect(self.poll_device)
        self.show_login()
        self.refresh_ports()
        self._load_example_yaml()

    @property
    def current_view(self) -> str:
        current = self.stack.currentWidget()
        if current is self.login_page:
            return "login"
        if current is self.maintenance_page:
            return "maintenance"
        return "dashboard"

    def _build_top_bar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("topBar")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(18, 12, 18, 12)
        titles = QVBoxLayout()
        title = QLabel("卒中卫士")
        title.setObjectName("brandTitle")
        subtitle = QLabel("ESP32-S3 多模态脑卒中早期风险提示智能健康镜")
        subtitle.setObjectName("brandSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        layout.addLayout(titles)
        layout.addStretch()
        self.device_badge = QLabel(f"设备  {self.default_device_id}")
        self.device_badge.setObjectName("smallMeta")
        layout.addWidget(self.device_badge)
        return frame

    def _build_login_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.addStretch()
        panel = QFrame()
        panel.setObjectName("loginPanel")
        panel.setMaximumWidth(460)
        box = QVBoxLayout(panel)
        box.setContentsMargins(28, 24, 28, 26)
        heading = QLabel("连接真实设备")
        heading.setProperty("sectionTitle", True)
        box.addWidget(heading)
        note = QLabel("登录 VPS 监控服务后自动连接 sg-0001")
        note.setObjectName("smallMeta")
        box.addWidget(note)
        form = QFormLayout()
        self.url_input = QLineEdit(DEFAULT_VPS_URL)
        self.url_input.setObjectName("vpsUrl")
        self.username_input = QLineEdit()
        self.username_input.setObjectName("username")
        self.password_input = QLineEdit()
        self.password_input.setObjectName("password")
        self.password_input.setEchoMode(QLineEdit.Password)
        form.addRow("服务地址", self.url_input)
        form.addRow("用户名", self.username_input)
        form.addRow("密码", self.password_input)
        box.addLayout(form)
        self.login_status = QLabel("")
        self.login_status.setObjectName("loginStatus")
        self.login_status.setWordWrap(True)
        box.addWidget(self.login_status)
        login = QPushButton("登录并连接设备")
        login.setObjectName("loginButton")
        login.clicked.connect(self.login)
        box.addWidget(login)
        outer.addWidget(panel, alignment=Qt.AlignHCenter)
        outer.addStretch()
        return page

    def _build_dashboard_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        status_row = QHBoxLayout()
        self.connection_state = QLabel("等待连接")
        self.connection_state.setObjectName("connectionState")
        status_row.addWidget(self.connection_state)
        self.last_update = QLabel("尚无真实数据")
        self.last_update.setObjectName("smallMeta")
        status_row.addWidget(self.last_update)
        status_row.addStretch()
        maintenance = QPushButton("设备维护")
        maintenance.setObjectName("maintenanceNav")
        maintenance.clicked.connect(self.show_maintenance)
        status_row.addWidget(maintenance)
        outer.addLayout(status_row)

        body = QHBoxLayout()
        body.setSpacing(12)
        metric_host = QWidget()
        metric_grid = QGridLayout(metric_host)
        metric_grid.setContentsMargins(0, 0, 0, 0)
        metric_grid.setSpacing(10)
        self.metric_labels: dict[str, QLabel] = {}
        for index, (key, title) in enumerate(METRICS):
            card = QFrame()
            card.setProperty("metricCard", True)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 13, 16, 14)
            card_layout.addWidget(QLabel(title))
            value = QLabel("未接入")
            value.setObjectName(f"metric-{key}")
            value.setProperty("metricValue", True)
            value.setStyleSheet(f"color: {COLORS['gray']};")
            card_layout.addWidget(value)
            card_layout.addStretch()
            self.metric_labels[key] = value
            metric_grid.addWidget(card, index // 3, index % 3)
        body.addWidget(metric_host, 3)

        side = QVBoxLayout()
        risk = QFrame()
        risk.setObjectName("riskPanel")
        risk_box = QVBoxLayout(risk)
        risk_box.addWidget(self._section_label("镜端风险提示"))
        self.risk_level = QLabel("等待数据")
        self.risk_level.setObjectName("riskLevel")
        risk_box.addWidget(self.risk_level)
        self.risk_reasons = QLabel("S3 结果为权威状态")
        self.risk_reasons.setWordWrap(True)
        self.risk_reasons.setObjectName("smallMeta")
        risk_box.addWidget(self.risk_reasons)
        side.addWidget(risk)

        advice = QFrame()
        advice.setObjectName("advicePanel")
        advice_box = QVBoxLayout(advice)
        advice_box.addWidget(self._section_label("豆包个性化建议"))
        self.advice_text = QLabel("等待云端返回已完成建议")
        self.advice_text.setObjectName("adviceText")
        self.advice_text.setWordWrap(True)
        self.advice_text.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        advice_box.addWidget(self.advice_text, 1)
        self.advice_meta = QLabel("暂无建议")
        self.advice_meta.setObjectName("adviceMeta")
        self.advice_meta.setProperty("class", "smallMeta")
        advice_box.addWidget(self.advice_meta)
        side.addWidget(advice, 1)
        body.addLayout(side, 2)
        outer.addLayout(body, 1)

        disclaimer = QLabel(
            "本设备用于风险提示与就医提醒，不是医疗诊断设备。若出现突发面部歪斜、言语不清、"
            "肢体无力、视物异常或平衡障碍，请立即拨打 120。原始音视频仅在本地处理。"
        )
        disclaimer.setWordWrap(True)
        disclaimer.setObjectName("smallMeta")
        outer.addWidget(disclaimer)
        return page

    def _build_maintenance_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        nav = QHBoxLayout()
        back = QPushButton("返回实时演示")
        back.clicked.connect(self.show_dashboard)
        nav.addWidget(back)
        nav.addStretch()
        outer.addLayout(nav)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)

        config_panel = QFrame()
        config_panel.setObjectName("maintenancePanel")
        config_box = QVBoxLayout(config_panel)
        config_box.addWidget(self._section_label("设备部署 YAML"))
        path_row = QHBoxLayout()
        self.deployment_path = QLineEdit()
        self.deployment_path.setObjectName("deploymentPath")
        path_row.addWidget(self.deployment_path)
        choose_yaml = QPushButton("打开")
        choose_yaml.clicked.connect(self.choose_yaml)
        path_row.addWidget(choose_yaml)
        config_box.addLayout(path_row)
        self.yaml_editor = QPlainTextEdit()
        self.yaml_editor.setObjectName("yamlEditor")
        self.yaml_editor.setMinimumHeight(250)
        config_box.addWidget(self.yaml_editor)

        secret_form = QFormLayout()
        self.env_inputs: dict[str, QLineEdit] = {}
        fields = (
            ("STROKEGUARD_WIFI_SSID", "Wi-Fi SSID", False),
            ("STROKEGUARD_WIFI_PASSWORD", "Wi-Fi 密码", True),
            ("STROKEGUARD_MQTT_USERNAME", "MQTT 用户名", False),
            ("STROKEGUARD_MQTT_PASSWORD", "MQTT 密码", True),
            ("STROKEGUARD_MANAGER_TOKEN", "管理 Token", True),
        )
        for env_name, label, masked in fields:
            edit = QLineEdit()
            edit.setObjectName(env_name)
            if masked:
                edit.setEchoMode(QLineEdit.Password)
            secret_form.addRow(label, edit)
            self.env_inputs[env_name] = edit
        config_box.addLayout(secret_form)
        action_row = QHBoxLayout()
        validate = QPushButton("校验配置")
        validate.setObjectName("validateButton")
        validate.clicked.connect(self.validate_yaml)
        save = QPushButton("保存本地 YAML")
        save.clicked.connect(self.save_yaml)
        action_row.addWidget(validate)
        action_row.addWidget(save)
        action_row.addStretch()
        config_box.addLayout(action_row)
        grid.addWidget(config_panel, 0, 0, 2, 1)

        task_panel = QFrame()
        task_panel.setObjectName("maintenancePanel")
        task_box = QVBoxLayout(task_panel)
        task_box.addWidget(self._section_label("ESP-IDF 与目标设备"))
        form = QFormLayout()
        self.idf_path = QLineEdit(r"E:\esp\v5.5.3\esp-idf")
        self.idf_path.setObjectName("idfPath")
        self.firmware_path = QLineEdit(str(self._default_firmware_path()))
        self.firmware_path.setObjectName("firmwarePath")
        self.port_combo = QComboBox()
        self.port_combo.setObjectName("serialPort")
        self.port_combo.currentIndexChanged.connect(self.refresh_erase_state)
        form.addRow("ESP-IDF 5.5.3", self.idf_path)
        form.addRow("固件工程", self.firmware_path)
        port_row = QHBoxLayout()
        port_row.addWidget(self.port_combo)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.refresh_ports)
        port_row.addWidget(refresh)
        form.addRow("串口", port_row)
        task_box.addLayout(form)

        self.erase_ack = QCheckBox("我确认允许擦除所选目标板的全部固件与 NVS")
        self.erase_ack.toggled.connect(self.refresh_erase_state)
        task_box.addWidget(self.erase_ack)
        buttons = QGridLayout()
        for index, (text, name, slot) in enumerate(
            (
                ("编译固件", "buildButton", self.build_firmware),
                ("擦除目标板", "eraseButton", self.erase_device),
                ("烧录固件", "flashButton", self.flash_firmware),
                ("启动串口监视", "monitorButton", self.toggle_monitor),
            )
        ):
            button = QPushButton(text)
            button.setObjectName(name)
            button.clicked.connect(slot)
            buttons.addWidget(button, index // 2, index % 2)
        self.erase_button = buttons.itemAtPosition(0, 1).widget()
        cancel = QPushButton("取消当前操作")
        cancel.clicked.connect(self.cancel_tasks)
        buttons.addWidget(cancel, 2, 0, 1, 2)
        task_box.addLayout(buttons)
        self.maintenance_status = QLabel("等待配置校验")
        self.maintenance_status.setObjectName("smallMeta")
        task_box.addWidget(self.maintenance_status)
        grid.addWidget(task_panel, 0, 1)

        log_panel = QFrame()
        log_panel.setObjectName("maintenancePanel")
        log_box = QVBoxLayout(log_panel)
        log_box.addWidget(self._section_label("维护日志（敏感字段已隐藏）"))
        self.maintenance_log = QPlainTextEdit()
        self.maintenance_log.setObjectName("maintenanceLog")
        self.maintenance_log.setReadOnly(True)
        self.maintenance_log.setMinimumHeight(230)
        log_box.addWidget(self.maintenance_log)
        grid.addWidget(log_panel, 1, 1)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        self.refresh_erase_state()
        return page

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("sectionTitle", True)
        return label

    @staticmethod
    def _default_firmware_path() -> Path:
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            beside_exe = exe_dir / "firmware_esp32"
            beside_dist = exe_dir.parent / "firmware_esp32"
            return beside_exe if beside_exe.exists() else beside_dist
        return Path(__file__).resolve().parents[3] / "firmware_esp32"

    @staticmethod
    def _example_yaml_path() -> Path:
        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            return Path(bundle_root) / "stroke_host" / "config" / "device-deployment.example.yaml"
        return Path(__file__).resolve().parents[2] / "config" / "device-deployment.example.yaml"

    def show_login(self, message: str = "") -> None:
        self.stack.setCurrentWidget(self.login_page)
        self.login_status.setText(message)
        self.poll_timer.stop()

    def show_dashboard(self) -> None:
        self.stack.setCurrentWidget(self.dashboard_page)

    def show_maintenance(self) -> None:
        self.stack.setCurrentWidget(self.maintenance_page)

    def login(self) -> None:
        username = self.username_input.text().strip()
        password = self.password_input.text()
        if not username or not password:
            self.login_status.setText("请输入用户名和密码")
            return
        self.login_status.setText("正在连接真实设备…")
        old_client = self._client
        self._client = self._client_factory(self.url_input.text().strip())
        old_client.close()

        def operation():
            self._client.login(username, password)
            self._client.connect(self.default_device_id)
            return self._client.fetch_device()

        self._run_task(operation, self._login_succeeded, self.apply_cloud_error)

    def _login_succeeded(self, result: object) -> None:
        self.password_input.clear()
        self.show_dashboard()
        self.apply_snapshot(result)
        if self._start_timers:
            self.poll_timer.start()

    def poll_device(self) -> None:
        self._run_task(self._client.fetch_device, self.apply_snapshot, self.apply_cloud_error)

    def apply_snapshot(self, snapshot: DeviceSnapshot) -> None:
        self.device_badge.setText(f"设备  {snapshot.device_id}")
        if snapshot.online:
            self._set_connection_state("设备在线", COLORS["green"])
        else:
            self._set_connection_state("设备离线", COLORS["red"])
        if snapshot.received_at is not None:
            self.last_update.setText(
                "VPS 最近接收 " + datetime.fromtimestamp(snapshot.received_at).strftime("%Y-%m-%d %H:%M:%S")
            )
        else:
            self.last_update.setText("尚无真实上行时间")

        values = {key: None for key, _ in METRICS}
        if snapshot.scores is not None:
            values = {
                "face": snapshot.scores.face,
                "speech": snapshot.scores.speech,
                "tongue": snapshot.scores.tongue,
                "eye": snapshot.scores.eye,
                "csi": snapshot.scores.csi,
                "final": snapshot.scores.final,
            }
        for key, value in values.items():
            label = self.metric_labels[key]
            if key == "final" and snapshot.level == "insufficient":
                label.setText("未形成")
                label.setStyleSheet(f"color: {COLORS['gray']};")
            else:
                label.setText("未接入" if value is None else str(value))
                label.setStyleSheet(f"color: {metric_color(value)};")

        self.risk_level.setText(LEVEL_TEXT.get(snapshot.level, "等待数据"))
        level_color = {
            "normal": COLORS["green"],
            "warning": COLORS["amber"],
            "danger": COLORS["red"],
        }.get(snapshot.level, COLORS["gray"])
        self.risk_level.setStyleSheet(f"color: {level_color};")
        details = list(snapshot.reasons)
        if snapshot.veto_by:
            details.append("否决项：" + "、".join(snapshot.veto_by))
        self.risk_reasons.setText("；".join(details) if details else "镜端未报告异常原因")
        if snapshot.advice is None:
            self.advice_text.setText("等待云端返回已完成建议")
            self.advice_meta.setText("暂无建议")
        else:
            self.advice_text.setText(snapshot.advice.advice_text)
            when = datetime.fromtimestamp(snapshot.advice.ts).strftime("%Y-%m-%d %H:%M:%S")
            self.advice_meta.setText(f"来源 {snapshot.advice.source} · {when}")

    def apply_cloud_error(self, error: object) -> None:
        if isinstance(error, AuthenticationRequired):
            self.show_login("登录失效")
        elif isinstance(error, DeviceOffline):
            self._set_connection_state("设备离线", COLORS["red"])
        elif isinstance(error, (CloudUnavailable, DemoCloudError)):
            self._set_connection_state("云端不可达", COLORS["red"])
            self.last_update.setText(self.last_update.text() + " · 当前非实时")
        else:
            self._set_connection_state("云端不可达", COLORS["red"])

    def _set_connection_state(self, text: str, color: str) -> None:
        self.connection_state.setText(text)
        self.connection_state.setStyleSheet(
            f"color: {color}; background: {color}18; border: 1px solid {color}55;"
        )

    def _run_task(self, fn, success, failure) -> None:
        task = _Task(fn)
        task.signals.succeeded.connect(success)
        task.signals.failed.connect(failure)
        self._thread_pool.start(task)

    def _load_example_yaml(self) -> None:
        path = self._example_yaml_path()
        if path.is_file():
            self.deployment_path.setText(str(path))
            self.yaml_editor.setPlainText(path.read_text(encoding="utf-8"))

    def choose_yaml(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开部署 YAML", "", "YAML (*.yaml *.yml)")
        if path:
            self.deployment_path.setText(path)
            self.yaml_editor.setPlainText(Path(path).read_text(encoding="utf-8"))

    def save_yaml(self) -> None:
        default = str(Path(__file__).resolve().parents[2] / "config" / "device-deployment.local.yaml")
        path, _ = QFileDialog.getSaveFileName(self, "保存本地部署 YAML", default, "YAML (*.yaml)")
        if path:
            Path(path).write_text(self.yaml_editor.toPlainText(), encoding="utf-8")
            self.deployment_path.setText(path)
            self._append_log(f"已保存本地配置：{path}")

    def _runtime_environ(self) -> dict[str, str]:
        env = dict(os.environ)
        for name, edit in self.env_inputs.items():
            if edit.text():
                env[name] = edit.text()
        return env

    def validate_yaml(self) -> bool:
        try:
            raw = yaml.safe_load(self.yaml_editor.toPlainText())
            self._deployment = validate_deployment(raw, self._runtime_environ())
            installation = IdfInstallation.discover(Path(self.idf_path.text()))
            project = Path(self.firmware_path.text())
            if not (project / "CMakeLists.txt").is_file():
                raise IdfRunnerError("固件工程缺少 CMakeLists.txt")
            self._idf_runner = IdfRunner(
                installation,
                project,
                on_event=lambda event: self._append_log(
                    f"[{event.stage}] {event.status}: {event.message}"
                ),
            )
            self._idf_runner.prepare(self._deployment)
        except (yaml.YAMLError, DeploymentValidationError, IdfRunnerError, OSError) as exc:
            self.maintenance_status.setText(f"配置无效：{exc}")
            self._append_log(f"配置校验失败：{exc}")
            return False
        self.maintenance_status.setText(
            f"配置有效 · {self._deployment.device_id} · IDF {installation.version}"
        )
        self._append_log("部署配置校验通过，敏感字段不会写入日志")
        return True

    def build_firmware(self) -> None:
        if not self.validate_yaml() or self._idf_runner is None:
            return
        self._run_maintenance(self._idf_runner.build, "固件编译完成")

    def erase_device(self) -> None:
        port = self._selected_port()
        if not port or not self.erase_ack.isChecked():
            return
        answer = QMessageBox.warning(
            self,
            "确认擦除目标板",
            f"将擦除 {port} 上的全部固件和 NVS。是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        if self._idf_runner is None and not self.validate_yaml():
            return
        self._run_maintenance(lambda: self._idf_runner.erase(port, True), "目标板擦除完成")

    def flash_firmware(self) -> None:
        port = self._selected_port()
        if not port:
            self.maintenance_status.setText("请选择 COM 口")
            return
        if self._idf_runner is None and not self.validate_yaml():
            return
        self._run_maintenance(lambda: self._idf_runner.flash(port), "固件烧录完成")

    def _run_maintenance(self, fn, success_message: str) -> None:
        self._set_maintenance_busy(True)

        def success(_):
            self._set_maintenance_busy(False)
            self.maintenance_status.setText(success_message)

        def failure(exc):
            self._set_maintenance_busy(False)
            self.maintenance_status.setText(f"操作失败：{exc}")
            self._append_log(f"操作失败：{exc}")

        self._run_task(lambda: (fn(), None)[1], success, failure)

    def _set_maintenance_busy(self, busy: bool) -> None:
        self._maintenance_busy = busy
        for name in ("validateButton", "buildButton", "eraseButton", "flashButton"):
            button = self.findChild(QPushButton, name)
            if button is not None:
                button.setEnabled(not busy)
        if not busy:
            self.refresh_erase_state()

    def toggle_monitor(self) -> None:
        button = self.findChild(QPushButton, "monitorButton")
        if self._serial_monitor.running:
            self._serial_monitor.stop()
            button.setText("启动串口监视")
            return
        port = self._selected_port()
        if not port:
            self.maintenance_status.setText("请选择 COM 口")
            return
        self._serial_monitor.start(port, 115200, self._append_log)
        button.setText("停止串口监视")

    def cancel_tasks(self) -> None:
        if self._idf_runner is not None:
            self._idf_runner.cancel()
        self._serial_monitor.stop()
        self._set_maintenance_busy(False)
        self._append_log("当前维护操作已取消")

    def refresh_ports(self) -> None:
        selected = self._selected_port()
        self.port_combo.clear()
        for port in list_serial_ports():
            self.port_combo.addItem(f"{port.device} · {port.description}", port.device)
        if selected:
            index = self.port_combo.findData(selected)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
        self.refresh_erase_state()

    def _selected_port(self) -> str:
        value = self.port_combo.currentData()
        return str(value) if value else ""

    def refresh_erase_state(self) -> None:
        if hasattr(self, "erase_button"):
            self.erase_button.setEnabled(
                not self._maintenance_busy
                and bool(self._selected_port())
                and self.erase_ack.isChecked()
            )

    def _append_log(self, line: str) -> None:
        self.maintenance_log_signal.emit(line)

    def _append_log_ui(self, line: str) -> None:
        if self._deployment is not None:
            from ..deployment.schema import redact_text

            line = redact_text(line, self._deployment)
        self.maintenance_log.appendPlainText(line)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._closed:
            self._closed = True
            self.poll_timer.stop()
            self._serial_monitor.stop()
            if self._idf_runner is not None:
                self._idf_runner.cleanup()
            self._client.close()
            self._thread_pool.waitForDone(2000)
        event.accept()


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("StrokeGuard Demo")
    window = DemoWindow()
    window.show()
    raise SystemExit(app.exec_())
