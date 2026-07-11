"""StrokeGuard 主界面 (PyQt5 · M4 正式版).

功能:
  - 五模态实时卡片 F/S/T/E/B + 融合分 + 总红黄绿灯
  - 单项否决触发时闪红 + 语音警告
  - 语音引导按钮: 请微笑 / 请说"你好中国" / 请注视镜头
  - reasons 面板显示当前触发理由
  - 数据源切换: sim / synthetic-frame / real / cdc

启动:
    python -m stroke_host.ui.main_window --source synthetic-frame --perception
    python -m stroke_host.ui.main_window --source real --perception
"""
from __future__ import annotations

# ---- 修复 Python 3.14 下 PyQt5 找不到 windows 平台插件的问题 ----
# 必须在 import PyQt5 之前设置环境变量
import os
import sys

def _fix_qt_plugin_path() -> None:
    if os.environ.get("QT_QPA_PLATFORM_PLUGIN_PATH"):
        return
    try:
        import PyQt5
    except ImportError:
        return
    pyqt_dir = os.path.dirname(PyQt5.__file__)
    candidates = [
        os.path.join(pyqt_dir, "Qt5", "plugins", "platforms"),
        os.path.join(pyqt_dir, "Qt", "plugins", "platforms"),
        os.path.join(pyqt_dir, "plugins", "platforms"),
    ]
    for c in candidates:
        if os.path.isdir(c) and os.path.isfile(os.path.join(c, "qwindows.dll")):
            os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = c
            # 同时把 bin 目录塞进 DLL 搜索路径
            bin_dir = os.path.abspath(os.path.join(c, "..", "..", "bin"))
            if os.path.isdir(bin_dir) and hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(bin_dir)
                except OSError:
                    pass
            return

_fix_qt_plugin_path()

import argparse
import logging
import queue
import time
from typing import Optional

from PyQt5.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPalette
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..config.profile_loader import load_profile
from ..fusion import LEVEL_DANGER, LEVEL_INSUFFICIENT, LEVEL_NORMAL, LEVEL_WARNING, fuse
from ..io.cdc_reader import CdcReader
from ..io.frame_recorder import FrameRecorder
from ..io.mqtt_pub import MqttConfig, MqttPublisher
from ..io.s3_bridge import S3Bridge
from ..io.sim_source import RealSource, SimSource, SyntheticFrameSource
from ..main import PerceptionPipeline
from .theme import (
    APP_STYLE,
    HERO_LAYOUT,
    STATUS,
    SURFACE,
    UI_COPY,
    modal_card_style,
    score_color,
    status_light_style,
)
from .tts import TtsWorker

log = logging.getLogger("stroke_host.ui")

MODALS = [
    ("face",   "F 面部对称"),
    ("speech", "S 言语清晰"),
    ("tongue", "T 舌偏(辅助)"),
    ("eye",    "E 眼动"),
    ("csi",    "B 平衡(CSI)"),
]

LEVEL_COLOR = {
    LEVEL_NORMAL:       STATUS["normal"],
    LEVEL_WARNING:      STATUS["warning"],
    LEVEL_DANGER:       STATUS["danger"],
    LEVEL_INSUFFICIENT: STATUS["insufficient"],
}
LEVEL_TEXT_ZH = {
    LEVEL_NORMAL:       "正常",
    LEVEL_WARNING:      "警告",
    LEVEL_DANGER:       "危险 · 请立即拨打 120",
    LEVEL_INSUFFICIENT: "数据不足",
}
GUIDE_TEXTS = {
    "smile":  "请对着镜头微笑,保持三秒",
    "say":    "请清晰地说,你好中国",
    "look":   "请正视镜头保持不动",
}
DISCLAIMER = (
    "本设备是家庭健康风险提示工具, 不是医疗诊断设备。"
    "结果仅作就医时机提示, 不能替代医生的临床诊断与治疗建议。"
    "原始音视频仅在本地处理, 不上传云端。"
    "如出现面部歪斜/言语不清/单侧肢体无力/剧烈头痛/视物模糊/意识改变等症状, "
    "无论本设备提示如何, 请立即拨打 120 (识别脑卒中黄金时间窗为发病后 4.5 小时内)。"
)


def _extract_score(percept: Optional[dict], key: str) -> Optional[int]:
    if not percept:
        return None
    m = percept.get(key)
    if not isinstance(m, dict):
        return None
    s = m.get("score")
    if s is None or s < 0:
        return None
    return int(s)


class _AdviceProxy(QObject):
    """跨线程信号代理: paho 后台线程 -> Qt 主线程."""
    new_advice = pyqtSignal(dict)


# ------------------------------------------------------------------------
# Worker: 在 QThread 里跑 SourceWorker (线程模型: QThread -> stdlib thread)
# 用 signal 把 (frame_json, percept, fusion_dict) 抛给主线程
# ------------------------------------------------------------------------
class BackendWorker(QObject):
    frame_ready = pyqtSignal(dict, dict, dict)  # frame_meta, percept, fusion
    stats_ready = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, args, mqtt_pub=None, profile_dict: Optional[dict] = None,
                 s3_bridge: Optional[S3Bridge] = None) -> None:
        super().__init__()
        self._args = args
        self._stop = False
        self._src = None
        self._rec: Optional[FrameRecorder] = None
        self._pipe: Optional[PerceptionPipeline] = None
        self._mqtt = mqtt_pub
        self._s3 = s3_bridge
        self._profile_dict = profile_dict or {"age": 60, "gender": "other"}
        self._n = 0
        self._t0 = time.time()
        self._n_s3_hit = 0
        self._n_s3_miss = 0

    def request_stop(self) -> None:
        self._stop = True

    def _fuse_via_s3_or_local(self, percept: dict, seq: int, frame) -> tuple[dict, str]:
        """尝试把 percept 发给 S3 让它融合, 拿回结果; 超时/失败降级本地 fuse()."""
        # 本地兜底始终算好, 万一 S3 慢就用它
        local = fuse(percept).as_dict()
        local["source"] = "pc-local"

        if self._s3 is None:
            return local, "pc-local"

        # 提取 scores + 附加字段, 发给 S3
        scores_pack = {
            "face":   _extract_score(percept, "face"),
            "speech": _extract_score(percept, "speech"),
            "tongue": _extract_score(percept, "tongue"),
            "eye":    _extract_score(percept, "eye"),
            "csi":    _extract_score(percept, "csi"),  # None -> S3 用自产
        }
        # face_theta / speech_p_clear 供 S3 单项否决用
        f_raw = ((percept.get("face") or {}).get("raw") or {})
        theta = f_raw.get("theta_abs_deg")
        if theta is not None:
            scores_pack["face_theta"] = float(theta)
        s_raw = ((percept.get("speech") or {}).get("raw") or {})
        p_clear = s_raw.get("p_clear")
        if p_clear is not None:
            scores_pack["speech_p_clear"] = float(p_clear)

        try:
            self._s3.send_scores(scores_pack, seq=seq)
        except Exception as e:
            log.debug("s3 send err: %s", e)
            self._n_s3_miss += 1
            return local, "pc-local"

        # 等 S3 回结果 (超时 300ms, 保证 UI 流畅)
        try:
            fu = self._s3.wait_fusion(seq=seq, timeout=0.30)
        except Exception as e:
            log.debug("s3 wait err: %s", e)
            fu = None

        if fu is None:
            self._n_s3_miss += 1
            return local, "pc-local (s3 timeout)"

        self._n_s3_hit += 1
        fu = dict(fu)
        fu["source"] = "s3"
        return fu, "s3"

    def _make_source(self):
        s = self._args.source
        if s == "cdc":
            return CdcReader(self._args.port, self._args.baud)
        if s == "real":
            return RealSource(cam_index=self._args.cam)
        if s == "synthetic-frame":
            return SyntheticFrameSource()
        return SimSource()

    def _build_pipeline(self):
        return PerceptionPipeline(
            self._src,
            face_backend=self._args.face_backend,
            yolo_weights=self._args.yolo_weights,
        )

    def run(self) -> None:
        try:
            self._src = self._make_source()
            self._src.open()
            if self._args.perception or self._args.source == "real":
                try:
                    self._pipe = self._build_pipeline()
                except Exception as e:
                    log.warning("perception init failed: %s", e)
                    self._pipe = None
            if not self._args.no_record:
                device_id = "sg-0001"
                try:
                    pf = load_profile(self._args.profile)
                    device_id = pf.device_id
                except Exception:
                    pass
                self._rec = FrameRecorder(self._args.data_dir, device_id)
                self._rec.open()

            last_stats = time.time()
            for frame in self._src.frames():
                if self._stop:
                    break
                self._n += 1
                percept = None
                if self._pipe is not None:
                    try:
                        percept = self._pipe.process(frame)
                    except Exception as e:
                        log.debug("perception err: %s", e)
                fusion_dict = {}
                fusion_source = "none"
                if percept:
                    # 尝试从 S3 拿融合结果; 超时降级本地
                    fusion_dict, fusion_source = self._fuse_via_s3_or_local(
                        percept, self._n, frame)
                else:
                    js = frame.json or {}
                    if js.get("csi_score") is not None:
                        fake = {"csi": {"score": int(js["csi_score"]),
                                        "raw": {}, "reasons": []}}
                        fusion_dict = fuse(fake).as_dict()
                        fusion_source = "pc-local"

                # ---- MQTT uplink (只发数值, 节流) ----
                if self._mqtt is not None and fusion_dict:
                    scores_out = {
                        "face": _extract_score(percept, "face"),
                        "speech": _extract_score(percept, "speech"),
                        "tongue": _extract_score(percept, "tongue"),
                        "eye": _extract_score(percept, "eye"),
                        "csi": _extract_score(percept, "csi") or (frame.json or {}).get("csi_score"),
                        "final": fusion_dict.get("final", 0),
                    }
                    try:
                        self._mqtt.publish_uplink(
                            scores=scores_out,
                            level=fusion_dict.get("level", "insufficient"),
                            reasons=fusion_dict.get("reasons", []),
                            veto_by=fusion_dict.get("veto_by", []),
                            profile=self._profile_dict,
                        )
                    except Exception as e:
                        log.debug("mqtt publish err: %s", e)

                fmeta = {
                    "type_name": frame.type_name,
                    "seq": (frame.json or {}).get("seq"),
                    "ts": (frame.json or {}).get("ts"),
                    "csi_score": (frame.json or {}).get("csi_score"),
                    "n": self._n,
                }
                self.frame_ready.emit(fmeta, percept or {}, fusion_dict)

                if self._rec is not None:
                    try:
                        self._rec.write(frame)
                    except Exception as e:
                        log.debug("rec err: %s", e)

                now = time.time()
                if now - last_stats > 1.0:
                    dt = max(0.001, now - self._t0)
                    self.stats_ready.emit({
                        "n": self._n,
                        "fps": self._n / dt,
                        "elapsed": dt,
                        "rec_dir": (self._rec._session_dir.name
                                    if self._rec and self._rec._session_dir else None),
                        "s3_hit": self._n_s3_hit,
                        "s3_miss": self._n_s3_miss,
                    })
                    last_stats = now
        except Exception as e:
            log.exception("backend crashed")
            self.error.emit(f"{type(e).__name__}: {e}")
        finally:
            if self._rec is not None:
                self._rec.close()
                self._rec = None
            if self._src is not None:
                try:
                    self._src.close()
                except Exception:
                    pass


# ------------------------------------------------------------------------
# 模态卡片
# ------------------------------------------------------------------------
class ModalCard(QFrame):
    def __init__(self, key: str, title: str) -> None:
        super().__init__()
        self.key = key
        self.setObjectName("ModalCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(152)
        self.setStyleSheet(modal_card_style(SURFACE["line"], active=False))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)
        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("MetricTitle")
        self.lbl_score = QLabel("--")
        self.lbl_score.setObjectName("MetricScore")
        f = QFont("Segoe UI", 38, QFont.Bold)
        self.lbl_score.setFont(f)
        self.lbl_score.setStyleSheet(f"color: {STATUS['insufficient']};")
        self.lbl_reason = QLabel("")
        self.lbl_reason.setWordWrap(True)
        self.lbl_reason.setObjectName("SmallMeta")
        self.lbl_reason.setMinimumHeight(34)
        lay.addWidget(self.lbl_title)
        lay.addWidget(self.lbl_score)
        lay.addWidget(self.lbl_reason)

    def update(self, score: Optional[int], reasons: list, level_color: str) -> None:
        if score is None or score < 0:
            self.lbl_score.setText("--")
            self.lbl_score.setStyleSheet(f"color: {STATUS['insufficient']};")
            self.lbl_reason.setText("未就绪")
            self.setStyleSheet(modal_card_style(SURFACE["line"], active=False))
        else:
            color = score_color(score)
            self.lbl_score.setText(str(score))
            self.lbl_score.setStyleSheet(f"color: {color};")
            reason_text = "; ".join(reasons[:2]) if reasons else "状态稳定"
            self.lbl_reason.setText(reason_text)
            self.setStyleSheet(modal_card_style(color, active=True))

    @staticmethod
    def _color(score: int) -> str:
        return score_color(score)


# ------------------------------------------------------------------------
# 主窗口
# ------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self, args) -> None:
        super().__init__()
        self._args = args
        self.setWindowTitle("StrokeGuard · 卒中卫士")
        self.resize(1220, 820)
        self._apply_dark_palette()
        self.setWindowTitle(f"{UI_COPY['app_title']} | StrokeGuard")
        self.setStyleSheet(APP_STYLE)

        self._thread: Optional[QThread] = None
        self._worker: Optional[BackendWorker] = None
        self._mqtt: Optional[MqttPublisher] = None
        self._s3: Optional[S3Bridge] = None
        self._profile_dict: dict = {}
        self._tts = TtsWorker()
        self._tts.open()
        self._last_level = LEVEL_NORMAL
        self._last_veto: list = []
        self._blink_state = False
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._on_blink)

        # 跨线程建议信号 (从 mqtt 后台线程 emit, 主线程接收)
        self._advice_signal = _AdviceProxy()
        self._advice_signal.new_advice.connect(self._on_advice)

        self._build_ui()

    def _apply_dark_palette(self) -> None:
        pal = QPalette()
        pal.setColor(QPalette.Window, QColor(SURFACE["app_bg"]))
        pal.setColor(QPalette.WindowText, QColor(SURFACE["text"]))
        pal.setColor(QPalette.Base, QColor(SURFACE["panel"]))
        pal.setColor(QPalette.AlternateBase, QColor(SURFACE["panel_soft"]))
        pal.setColor(QPalette.Text, QColor(SURFACE["text"]))
        pal.setColor(QPalette.Button, QColor(SURFACE["panel_lift"]))
        pal.setColor(QPalette.ButtonText, QColor(SURFACE["text"]))
        self.setPalette(pal)

    # ---------- UI ----------
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(14)

        # ---- 顶部工具条 ----
        top = QFrame()
        top.setObjectName("ControlStrip")
        bar = QHBoxLayout(top)
        bar.setContentsMargins(16, 12, 16, 12)
        bar.setSpacing(10)
        brand_col = QVBoxLayout()
        brand_col.setSpacing(2)
        lbl_brand = QLabel(UI_COPY["app_title"])
        lbl_brand.setObjectName("BrandTitle")
        lbl_subtitle = QLabel(UI_COPY["subtitle"])
        lbl_subtitle.setObjectName("BrandSubtitle")
        brand_col.addWidget(lbl_brand)
        brand_col.addWidget(lbl_subtitle)
        bar.addLayout(brand_col, stretch=1)
        bar.addWidget(QLabel("Source:"))
        self.cbo_source = QComboBox()
        self.cbo_source.addItems(["sim", "synthetic-frame", "real", "cdc"])
        self.cbo_source.setCurrentText(self._args.source)
        bar.addWidget(self.cbo_source)

        bar.addWidget(QLabel("Port:"))
        self.edt_port = QLineEdit(self._args.port)
        self.edt_port.setMaximumWidth(80)
        bar.addWidget(self.edt_port)

        self.chk_record = QCheckBox("Record")
        self.chk_record.setChecked(not self._args.no_record)
        bar.addWidget(self.chk_record)

        self.chk_perception = QCheckBox("Perception")
        self.chk_perception.setChecked(True)
        bar.addWidget(self.chk_perception)

        self.chk_tts = QCheckBox("Voice alerts")
        self.chk_tts.setChecked(True)
        bar.addWidget(self.chk_tts)

        self.chk_cloud = QCheckBox("Cloud")
        self.chk_cloud.setChecked(bool(os.environ.get("SG_MQTT_HOST")))
        bar.addWidget(self.chk_cloud)

        self.chk_s3 = QCheckBox("S3 Fusion")
        self.chk_s3.setChecked(False)
        self.chk_s3.setToolTip(
            "在 Port 里填 S3 的 COM 口, 勾选此项后 PC 感知分会发到 S3, "
            "由 S3 端计算融合分并回传; 超时会自动降级本地融合."
        )
        bar.addWidget(self.chk_s3)

        self.btn_start = QPushButton("Start")
        self.btn_stop = QPushButton("Stop")
        self.btn_start.setObjectName("PrimaryButton")
        self.btn_stop.setObjectName("DangerButton")
        self.btn_stop.setEnabled(False)
        self.btn_start.clicked.connect(self._on_start)
        self.btn_stop.clicked.connect(self._on_stop)
        bar.addWidget(self.btn_start)
        bar.addWidget(self.btn_stop)
        bar.addStretch(1)
        root.addWidget(top)

        # ---- 主体: 左总灯 + 右5卡 ----
        body = QHBoxLayout()
        body.setSpacing(14)

        # 左侧: 总红黄绿 + 数字 + level 文本 + reasons
        hero = QFrame()
        hero.setObjectName("MirrorHero")
        left = QVBoxLayout(hero)
        left.setContentsMargins(18, 18, 18, 18)
        left.setSpacing(10)
        self.lbl_light = QLabel()
        self.lbl_light.setFixedSize(
            HERO_LAYOUT["light_size"], HERO_LAYOUT["light_size"]
        )
        self.lbl_light.setStyleSheet(status_light_style(STATUS["insufficient"]))
        left.addWidget(self.lbl_light, alignment=Qt.AlignHCenter)

        self.lbl_final = QLabel("--")
        self.lbl_final.setFont(
            QFont("Segoe UI", HERO_LAYOUT["score_font_pt"], QFont.Bold)
        )
        self._set_final_style(STATUS["insufficient"])
        self.lbl_final.setAlignment(Qt.AlignCenter)
        left.addWidget(self.lbl_final)

        self.lbl_level = QLabel("等待启动")
        self.lbl_level.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        self.lbl_level.setAlignment(Qt.AlignCenter)
        self.lbl_level.setStyleSheet(f"color: {SURFACE['muted']};")
        left.addWidget(self.lbl_level)

        left.addWidget(QLabel("Reasons:"))
        self.txt_reasons = QTextEdit()
        self.txt_reasons.setReadOnly(True)
        self.txt_reasons.setMaximumHeight(120)
        left.addWidget(self.txt_reasons)

        # 语音引导按钮
        guide_row = QHBoxLayout()
        self.btn_smile = QPushButton("请微笑")
        self.btn_say = QPushButton("请说\"你好中国\"")
        self.btn_look = QPushButton("请正视镜头")
        self.btn_smile.clicked.connect(lambda: self._speak_force(GUIDE_TEXTS["smile"]))
        self.btn_say.clicked.connect(lambda: self._speak_force(GUIDE_TEXTS["say"]))
        self.btn_look.clicked.connect(lambda: self._speak_force(GUIDE_TEXTS["look"]))
        guide_row.addWidget(self.btn_smile)
        guide_row.addWidget(self.btn_say)
        guide_row.addWidget(self.btn_look)
        left.addLayout(guide_row)

        body.addWidget(hero, stretch=2)

        # 右侧: 5 模态卡片 (2x3 grid, 最后一格留空)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self._cards = {}
        for i, (k, title) in enumerate(MODALS):
            card = ModalCard(k, title)
            self._cards[k] = card
            grid.addWidget(card, i // 2, i % 2)
        right = QVBoxLayout()
        right.setSpacing(12)
        right.addLayout(grid)

        # 云端建议卡片
        adv_frame = QFrame()
        adv_frame.setObjectName("AdvicePanel")
        adv_frame.setStyleSheet(
            "QFrame { background: #202a35; border: 1px solid #3a5060; "
            "border-radius: 8px; padding: 8px; }"
        )
        adv_frame.setStyleSheet("")
        adv_lay = QVBoxLayout(adv_frame)
        adv_lay.setContentsMargins(10, 8, 10, 8)
        adv_title_row = QHBoxLayout()
        lbl_adv_title = QLabel("AI 健康建议")
        lbl_adv_title.setStyleSheet("color: #7fb3ff; font-weight: bold;")
        lbl_adv_title.setText(UI_COPY["advice_title"])
        lbl_adv_title.setStyleSheet(f"color: {STATUS['accent']}; font-weight: bold;")
        adv_title_row.addWidget(lbl_adv_title)
        self.lbl_adv_meta = QLabel("(等待云端推送)")
        self.lbl_adv_meta.setStyleSheet("color: #666; font-size: 10px;")
        self.lbl_adv_meta.setObjectName("SmallMeta")
        adv_title_row.addWidget(self.lbl_adv_meta)
        adv_title_row.addStretch(1)
        adv_lay.addLayout(adv_title_row)
        self.txt_advice = QTextEdit()
        self.txt_advice.setReadOnly(True)
        self.txt_advice.setStyleSheet(
            "QTextEdit { background: #1a222b; color: #dfe8f0; "
            "font-family: 'Microsoft YaHei'; font-size: 13px; border: none; }"
        )
        self.txt_advice.setMinimumHeight(90)
        self.txt_advice.setStyleSheet("")
        self.txt_advice.setPlainText("云端 LLM 建议将在此显示. 勾选顶部 Cloud 后启动.")
        adv_lay.addWidget(self.txt_advice)
        right.addWidget(adv_frame)

        right.addStretch(1)
        body.addLayout(right, stretch=3)

        root.addLayout(body, stretch=1)

        # ---- 底部: 统计 + 免责 ----
        self.lbl_stats = QLabel("idle")
        self.lbl_stats.setObjectName("SmallMeta")
        self.lbl_stats.setStyleSheet(
            f"color: {SURFACE['muted']}; font-family: Consolas;"
        )
        root.addWidget(self.lbl_stats)

        lbl_disc = QLabel(DISCLAIMER)
        lbl_disc.setWordWrap(True)
        lbl_disc.setStyleSheet(
            f"color: {SURFACE['muted']}; font-size: 10px; padding: 8px; "
            f"background: {SURFACE['panel']}; border-left: 3px solid {STATUS['accent']};"
        )
        root.addWidget(lbl_disc)

    # ---------- lifecycle ----------
    def _on_start(self) -> None:
        if self._thread and self._thread.isRunning():
            return
        args = argparse.Namespace(**vars(self._args))
        args.source = self.cbo_source.currentText()
        args.port = self.edt_port.text()
        args.perception = self.chk_perception.isChecked()
        args.no_record = not self.chk_record.isChecked()

        # 加载 profile 供 MQTT uplink 使用
        try:
            pf = load_profile(args.profile)
            self._profile_dict = pf.user.model_dump()
            device_id = pf.device_id
        except Exception as e:
            log.warning("profile load failed: %s", e)
            self._profile_dict = {"age": 60, "gender": "other",
                                  "conditions": [], "meds": [], "stroke_history": False}
            device_id = "sg-0001"

        # 启动 MQTT
        if self.chk_cloud.isChecked():
            cfg = MqttConfig.from_env()
            cfg.device_id = device_id
            if not cfg.host or cfg.host == "127.0.0.1" and not os.environ.get("SG_MQTT_HOST"):
                self.txt_advice.setPlainText(
                    "云端未配置: 请设置环境变量 SG_MQTT_HOST / SG_MQTT_USER / SG_MQTT_PASS 后重启."
                )
                self._mqtt = None
            else:
                self._mqtt = MqttPublisher(
                    cfg,
                    on_advice=lambda d: self._advice_signal.new_advice.emit(d),
                )
                self._mqtt.start()

        # 启动 S3 Bridge (CDC 双向)
        if self.chk_s3.isChecked() and args.port:
            try:
                self._s3 = S3Bridge(args.port, args.baud)
                self._s3.start()
                self.txt_reasons.append(f"=== S3Bridge connected @ {args.port} ===")
            except Exception as e:
                log.warning("S3Bridge start failed: %s", e)
                self.txt_reasons.append(f"!! S3Bridge failed: {e}")
                self._s3 = None

        self._thread = QThread(self)
        self._worker = BackendWorker(args, mqtt_pub=self._mqtt,
                                     profile_dict=self._profile_dict,
                                     s3_bridge=self._s3)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.frame_ready.connect(self._on_frame)
        self._worker.stats_ready.connect(self._on_stats)
        self._worker.error.connect(self._on_error)
        self._thread.start()

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.txt_reasons.append("=== start ===")
        self._speak_force("卒中卫士开始监测")

    def _on_stop(self) -> None:
        if self._worker is not None:
            self._worker.request_stop()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
        self._thread = None
        self._worker = None
        if self._mqtt is not None:
            self._mqtt.stop()
            self._mqtt = None
        if self._s3 is not None:
            try:
                self._s3.stop()
            except Exception:
                pass
            self._s3 = None
        self._blink_timer.stop()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.txt_reasons.append("=== stop ===")

    def _on_advice(self, data: dict) -> None:
        """从 MQTT downlink 接收到 LLM 建议."""
        text = data.get("advice_text", "")
        level = data.get("level", "")
        ts = data.get("ts", 0)
        src = data.get("source", "?")
        self.txt_advice.setPlainText(text or "(空建议)")
        from datetime import datetime
        try:
            when = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
        except Exception:
            when = "?"
        self.lbl_adv_meta.setText(f"[{level}] {when} · {src}")

    def _on_error(self, msg: str) -> None:
        self.txt_reasons.append(f"!! ERROR: {msg}")
        self._on_stop()

    def closeEvent(self, evt) -> None:  # noqa: N802
        self._on_stop()
        self._tts.close()
        super().closeEvent(evt)

    # ---------- 数据信号 ----------
    def _on_stats(self, s: dict) -> None:
        line = f"frames={s['n']}  fps={s['fps']:.2f}  elapsed={s['elapsed']:.1f}s"
        if s.get("rec_dir"):
            line += f"  |  rec={s['rec_dir']}"
        hit = s.get("s3_hit", 0)
        miss = s.get("s3_miss", 0)
        if hit or miss:
            line += f"  |  S3 fusion: {hit} hit / {miss} miss"
        self.lbl_stats.setText(line)

    def _on_frame(self, fmeta: dict, percept: dict, fusion: dict) -> None:
        # 更新模态卡片
        for k, _ in MODALS:
            m = percept.get(k) if percept else None
            score = m.get("score") if isinstance(m, dict) else None
            reasons = m.get("reasons", []) if isinstance(m, dict) else []
            # 兜底: heartbeat 帧的 csi_score 直接进 CSI 卡片
            if k == "csi" and (score is None or score < 0) and fmeta.get("csi_score") is not None:
                score = int(fmeta["csi_score"])
                reasons = []
            color = LEVEL_COLOR[LEVEL_NORMAL]
            self._cards[k].update(score, reasons, color)

        # 融合结果
        if not fusion:
            return
        final = fusion.get("final", 0)
        level = fusion.get("level", LEVEL_INSUFFICIENT)
        veto = fusion.get("veto_by", [])
        reasons = fusion.get("reasons", [])

        self.lbl_final.setText(str(final) if level != LEVEL_INSUFFICIENT else "--")
        self._set_final_style(LEVEL_COLOR[level])
        # 融合来源加进 level 显示
        src = fusion.get("source", "")
        src_tag = ""
        if src == "s3":
            src_tag = "  [S3]"
        elif src.startswith("pc-local"):
            src_tag = f"  [{src}]"
        self.lbl_level.setText(LEVEL_TEXT_ZH[level] + src_tag)
        self.lbl_level.setStyleSheet(f"color: {LEVEL_COLOR[level]};")
        self._set_light(LEVEL_COLOR[level])

        # reasons 面板
        if reasons:
            self.txt_reasons.append(f"[#{fmeta['n']}] " + " | ".join(reasons))
            # 简单尾行控制
            doc = self.txt_reasons.document()
            if doc.blockCount() > 100:
                cursor = self.txt_reasons.textCursor()
                cursor.movePosition(cursor.Start)
                cursor.select(cursor.BlockUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()

        # 语音警告 + 闪灯
        if self.chk_tts.isChecked():
            if level == LEVEL_DANGER and (level != self._last_level or veto != self._last_veto):
                if veto:
                    if "face" in veto:
                        self._speak_force("检测到面部不对称,请立即就医并拨打 120")
                    elif "speech" in veto:
                        self._speak_force("检测到言语不清,请立即就医并拨打 120")
                    else:
                        self._speak_force("检测到高风险,请立即就医并拨打 120")
                else:
                    self._speak_force("整体评分偏低,请注意休息并考虑就医")
            elif level == LEVEL_WARNING and self._last_level == LEVEL_NORMAL:
                self._tts.speak("检测到异常,请复查")

        # 闪灯
        if level == LEVEL_DANGER:
            if not self._blink_timer.isActive():
                self._blink_timer.start(400)
        else:
            self._blink_timer.stop()
            self._set_light(LEVEL_COLOR[level])

        self._last_level = level
        self._last_veto = veto

    # ---------- helpers ----------
    def _set_final_style(self, color: str) -> None:
        self.lbl_final.setStyleSheet(
            f"color: {color}; "
            f"font-size: {HERO_LAYOUT['score_font_pt']}px; "
            "font-weight: 800;"
        )

    def _set_light(self, hex_color: str) -> None:
        self.lbl_light.setStyleSheet(status_light_style(hex_color, active=True))

    def _on_blink(self) -> None:
        self._blink_state = not self._blink_state
        color = LEVEL_COLOR[LEVEL_DANGER] if self._blink_state else "#440000"
        self._set_light(color)

    def _speak_force(self, text: str) -> None:
        if self.chk_tts.isChecked():
            self._tts.speak(text, force=True)


# ------------------------------------------------------------------------
# entry
# ------------------------------------------------------------------------
def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stroke-ui",
                                description="StrokeGuard main UI (PyQt5)")
    p.add_argument("--source", choices=["cdc", "sim", "synthetic-frame", "real"], default="sim")
    p.add_argument("--port", default="COM3")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--cam", type=int, default=0)
    p.add_argument("--profile", default="config/profile.yaml")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--no-record", action="store_true")
    p.add_argument("--perception", action="store_true")
    p.add_argument("--face-backend", choices=["auto", "mediapipe", "yolo"],
                   default="auto",
                   help="face backend: auto prefers YOLO only when weights exist")
    p.add_argument("--yolo-weights", default="",
                   help="optional YOLOv8 face weights path")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main() -> None:
    args = _build_argparser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    app = QApplication(sys.argv)
    win = MainWindow(args)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
