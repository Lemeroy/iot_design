"""Profile form and high-contrast YAML workspace."""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QTextFormat
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..config.profile_loader import (
    DeviceEndpoint,
    ProfileFile,
    Thresholds,
    UserProfile,
    load_profile,
    parse_profile_yaml,
)
from ..config.profile_store import dump_profile_yaml, save_profile_atomic


class _LineNumberArea(QWidget):
    def __init__(self, editor: "YamlEditor") -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:
        self._editor.paint_line_numbers(event)


class YamlEditor(QPlainTextEdit):
    """Compact code editor with stable line-number geometry."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._line_number_area = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_number_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setFont(QFont("Cascadia Mono", 11))
        self.setTabStopWidth(self.fontMetrics().horizontalAdvance(" ") * 2)
        self.setStyleSheet("""
            QPlainTextEdit {
                background: #06110f;
                color: #edf9f5;
                border: 1px solid #2e685b;
                border-radius: 6px;
                padding: 8px 8px 8px 0;
                selection-background-color: #58d7d1;
                selection-color: #04110d;
            }
        """)
        self._update_line_number_width()
        self._highlight_current_line()

    def line_number_area_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return 14 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_line_number_width(self, _count=0) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(0, rect.y(),
                                          self._line_number_area.width(),
                                          rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_width()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        contents = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(contents.left(), contents.top(),
                  self.line_number_area_width(), contents.height())
        )

    def _highlight_current_line(self) -> None:
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor("#102923"))
        selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])

    def paint_line_numbers(self, event) -> None:
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), QColor("#0d1e1b"))
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(
            self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor("#8ba59d"))
                painter.drawText(
                    0, top, self._line_number_area.width() - 7,
                    self.fontMetrics().height(), Qt.AlignRight,
                    str(number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            number += 1


class ConfigPanel(QWidget):
    profile_saved = pyqtSignal(object)
    pull_requested = pyqtSignal()
    push_requested = pyqtSignal(object)

    def __init__(self, profile_path: str | Path, parent=None) -> None:
        super().__init__(parent)
        self._profile_path = Path(profile_path)
        self._sync_busy = False
        self._valid_profile: ProfileFile | None = None
        self._build_ui()
        self._load_initial_profile()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("设备配置")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #eaf7f2;")
        header.addWidget(title)
        header.addStretch(1)
        self.validation_label = QLabel()
        self.validation_label.setObjectName("ValidationStatus")
        self.validation_label.setStyleSheet("color: #ff8b8b; font-weight: 600;")
        header.addWidget(self.validation_label)
        root.addLayout(header)

        self.mode_tabs = QTabWidget()
        root.addWidget(self.mode_tabs, stretch=1)

        form_page = QWidget()
        form_root = QVBoxLayout(form_page)
        form_root.setContentsMargins(14, 14, 14, 14)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.device_id = QLineEdit()
        self.host = QLineEdit()
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.age = QSpinBox()
        self.age.setRange(0, 130)
        self.gender = QComboBox()
        self.gender.addItems(["M", "F", "other"])
        self.conditions = QLineEdit()
        self.meds = QLineEdit()
        self.stroke_history = QCheckBox()

        form.addRow("设备 ID", self.device_id)
        form.addRow("局域网地址", self.host)
        form.addRow("管理端口", self.port)
        form.addRow("年龄", self.age)
        form.addRow("性别", self.gender)
        form.addRow("慢性病", self.conditions)
        form.addRow("长期用药", self.meds)
        form.addRow("既往卒中史", self.stroke_history)
        form_root.addLayout(form)

        baseline = QFrame()
        baseline.setObjectName("MedicalBaseline")
        baseline_layout = QFormLayout(baseline)
        baseline_layout.setContentsMargins(12, 12, 12, 12)
        baseline_layout.addRow(QLabel("医学只读基线"))
        self.face_threshold = QLabel("30")
        self.mouth_threshold = QLabel("20°")
        self.speech_threshold = QLabel("35")
        baseline_layout.addRow("面部危险阈值", self.face_threshold)
        baseline_layout.addRow("口角偏移阈值", self.mouth_threshold)
        baseline_layout.addRow("言语危险阈值", self.speech_threshold)
        form_root.addWidget(baseline)
        form_root.addStretch(1)

        form_actions = QHBoxLayout()
        form_actions.addStretch(1)
        self.apply_form_button = QPushButton("更新 YAML")
        self.apply_form_button.clicked.connect(self.apply_form_to_yaml)
        form_actions.addWidget(self.apply_form_button)
        form_root.addLayout(form_actions)
        self.mode_tabs.addTab(form_page, "表单")

        yaml_page = QWidget()
        yaml_root = QVBoxLayout(yaml_page)
        yaml_root.setContentsMargins(4, 8, 4, 4)
        self.yaml_editor = YamlEditor()
        self.yaml_editor.textChanged.connect(self.validate_yaml)
        yaml_root.addWidget(self.yaml_editor)
        self.apply_yaml_button = QPushButton("应用到表单")
        self.apply_yaml_button.clicked.connect(self.apply_yaml_to_form)
        yaml_root.addWidget(self.apply_yaml_button, alignment=Qt.AlignRight)
        self.mode_tabs.addTab(yaml_page, "YAML")
        self.mode_tabs.currentChanged.connect(self._mode_changed)

        actions = QHBoxLayout()
        self.pull_button = QPushButton("从设备读取")
        self.revert_button = QPushButton("恢复未保存内容")
        self.save_button = QPushButton("保存本地")
        self.sync_button = QPushButton("同步到设备")
        self.save_button.setObjectName("PrimaryButton")
        self.pull_button.clicked.connect(self.pull_requested.emit)
        self.revert_button.clicked.connect(self._load_initial_profile)
        self.save_button.clicked.connect(self.save_local)
        self.sync_button.clicked.connect(self._emit_push)
        actions.addWidget(self.pull_button)
        actions.addWidget(self.revert_button)
        actions.addStretch(1)
        actions.addWidget(self.save_button)
        actions.addWidget(self.sync_button)
        root.addLayout(actions)

    def _load_initial_profile(self) -> None:
        try:
            profile = load_profile(self._profile_path)
        except FileNotFoundError:
            profile = ProfileFile(
                device_id="sg-0001",
                user=UserProfile(age=0, gender="other"),
            )
        except (OSError, UnicodeError, ValueError):
            try:
                invalid_text = self._profile_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                invalid_text = ""
            profile = ProfileFile(
                device_id="sg-0001",
                user=UserProfile(age=0, gender="other"),
            )
            self.set_profile(profile)
            self.yaml_editor.setPlainText(invalid_text)
            self.validate_yaml()
            return
        self.set_profile(profile)

    @staticmethod
    def _split_items(value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]

    def _profile_from_form(self) -> ProfileFile:
        return ProfileFile(
            device_id=self.device_id.text().strip(),
            device=DeviceEndpoint(
                host=self.host.text().strip(), port=self.port.value()
            ),
            user=UserProfile(
                age=self.age.value(),
                gender=self.gender.currentText(),
                conditions=self._split_items(self.conditions.text()),
                meds=self._split_items(self.meds.text()),
                stroke_history=self.stroke_history.isChecked(),
            ),
            thresholds=Thresholds(),
        )

    def current_profile(self) -> ProfileFile:
        return parse_profile_yaml(self.yaml_editor.toPlainText())

    def set_profile(self, profile: ProfileFile) -> None:
        self.device_id.setText(profile.device_id)
        self.host.setText(profile.device.host)
        self.port.setValue(profile.device.port)
        self.age.setValue(profile.user.age)
        self.gender.setCurrentText(profile.user.gender)
        self.conditions.setText(", ".join(profile.user.conditions))
        self.meds.setText(", ".join(profile.user.meds))
        self.stroke_history.setChecked(profile.user.stroke_history)
        self.yaml_editor.setPlainText(dump_profile_yaml(profile))
        self.validate_yaml()

    def apply_form_to_yaml(self) -> bool:
        try:
            profile = self._profile_from_form()
        except ValueError as exc:
            self.validation_label.setText(str(exc).splitlines()[0])
            self.save_button.setEnabled(False)
            self.sync_button.setEnabled(False)
            return False
        self.yaml_editor.setPlainText(dump_profile_yaml(profile))
        return self.validate_yaml()

    def apply_yaml_to_form(self) -> bool:
        if not self.validate_yaml():
            return False
        profile = self._valid_profile
        assert profile is not None
        self.device_id.setText(profile.device_id)
        self.host.setText(profile.device.host)
        self.port.setValue(profile.device.port)
        self.age.setValue(profile.user.age)
        self.gender.setCurrentText(profile.user.gender)
        self.conditions.setText(", ".join(profile.user.conditions))
        self.meds.setText(", ".join(profile.user.meds))
        self.stroke_history.setChecked(profile.user.stroke_history)
        return True

    def validate_yaml(self) -> bool:
        try:
            self._valid_profile = self.current_profile()
        except ValueError as exc:
            self._valid_profile = None
            self.validation_label.setText(str(exc).splitlines()[0])
            self.validation_label.setStyleSheet("color: #ff8b8b; font-weight: 600;")
        else:
            self.validation_label.setText("配置有效")
            self.validation_label.setStyleSheet("color: #58d7d1; font-weight: 600;")
        valid = self._valid_profile is not None
        self.save_button.setEnabled(valid and not self._sync_busy)
        self.sync_button.setEnabled(valid and not self._sync_busy)
        return valid

    def save_local(self) -> None:
        if not self.validate_yaml():
            return
        profile = self._valid_profile
        assert profile is not None
        try:
            save_profile_atomic(self._profile_path, profile)
        except OSError:
            self.validation_label.setText("保存失败，请检查文件权限")
            self.validation_label.setStyleSheet("color: #ff8b8b; font-weight: 600;")
            return
        self.validation_label.setText("已保存")
        self.profile_saved.emit(profile)

    def set_sync_busy(self, busy: bool) -> None:
        self._sync_busy = busy
        self.pull_button.setEnabled(not busy)
        self.validate_yaml()

    def _emit_push(self) -> None:
        if self.validate_yaml() and self._valid_profile is not None:
            self.push_requested.emit(self._valid_profile)

    def _mode_changed(self, index: int) -> None:
        if index == 1:
            self.apply_form_to_yaml()
        else:
            self.apply_yaml_to_form()
