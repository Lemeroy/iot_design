"""M1a/M2/M3 实时观察窗口 (tkinter, 零新增依赖).

后台线程消费 frame 源, 主线程 100ms 拉队列刷新 UI.
展示:
  - 大号 CSI (M1a 心跳帧) 或 5 模态卡片 (M2+M3, data 帧)
  - sparkline + 统计 + 日志尾

启动:
    python -m stroke_host.gui.observer --source sim
    python -m stroke_host.gui.observer --source cdc --port COM3
    python -m stroke_host.gui.observer --source synthetic-frame --perception
    python -m stroke_host.gui.observer --source real --perception
"""
from __future__ import annotations

import argparse
import base64
import logging
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Optional

import numpy as np

from ..config.profile_loader import load_profile
from ..io.cdc_reader import CdcReader, Frame, TYPE_DATA
from ..io.frame_recorder import FrameRecorder
from ..io.sim_source import RealSource, SimSource, SyntheticFrameSource

log = logging.getLogger("stroke_host.gui")

# 交通灯阈值 (与 Dr.Chen 草稿一致)
CSI_DANGER = 30
CSI_WARN = 60

SPARK_LEN = 60
LOG_TAIL = 30
UI_TICK_MS = 100

MODALS = [
    ("face",   "F 面部对称"),
    ("speech", "S 言语清晰"),
    ("tongue", "T 舌偏 (辅助)"),
    ("eye",    "E 眼动"),
    ("csi",    "B 平衡 (CSI)"),
]


def _traffic_color(score: Optional[int]) -> str:
    if score is None or score < 0:
        return "#888888"
    if score < CSI_DANGER:
        return "#e74c3c"
    if score < CSI_WARN:
        return "#f1c40f"
    return "#2ecc71"


class SourceWorker(threading.Thread):
    """后台读帧 + (可选) 感知推理, 结果放 queue."""

    def __init__(self, source_factory, out_q: queue.Queue,
                 rec: Optional[FrameRecorder] = None,
                 enable_perception: bool = False,
                 face_backend: str = "auto",
                 yolo_weights: str = "") -> None:
        super().__init__(name="src-worker", daemon=True)
        self._factory = source_factory
        self._q = out_q
        self._rec = rec
        self._stop = threading.Event()
        self._enable_perception = enable_perception
        self._face_backend = face_backend
        self._yolo_weights = yolo_weights
        self._pipe = None
        self.err: Optional[str] = None
        self.source = None

    def stop(self) -> None:
        self._stop.set()

    def _build_pipeline(self):
        from ..main import PerceptionPipeline
        try:
            return PerceptionPipeline(
                self.source,
                face_backend=self._face_backend,
                yolo_weights=self._yolo_weights,
            )
        except Exception as e:
            log.warning("perception init failed: %s", e)
            return None

    def run(self) -> None:
        try:
            self.source = self._factory()
            self.source.open()
            if self._enable_perception:
                self._pipe = self._build_pipeline()
            for frame in self.source.frames():
                if self._stop.is_set():
                    break
                res = None
                if self._pipe is not None:
                    try:
                        res = self._pipe.process(frame)
                    except Exception as e:
                        log.debug("perception err: %s", e)
                try:
                    self._q.put_nowait((frame, res))
                except queue.Full:
                    pass
                if self._rec is not None:
                    try:
                        self._rec.write(frame)
                    except Exception as e:
                        log.warning("record err: %s", e)
        except Exception as e:
            self.err = f"{type(e).__name__}: {e}"
            log.exception("source worker crashed")
        finally:
            try:
                if self.source is not None:
                    self.source.close()
            except Exception:
                pass


class ObserverApp:
    def __init__(self, args) -> None:
        self.args = args
        self.root = tk.Tk()
        self.root.title("StrokeGuard Observer")
        self.root.geometry("880x680")
        self.root.minsize(700, 560)

        self._q: queue.Queue = queue.Queue(maxsize=256)
        self._worker: Optional[SourceWorker] = None
        self._rec: Optional[FrameRecorder] = None

        self._n_frames = 0
        self._t0 = time.time()
        self._spark: list[Optional[int]] = []
        self._log_lines: list[str] = []
        self._modal_labels: dict = {}
        self._modal_boxes: dict = {}

        self._build_ui()
        self._schedule_tick()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- UI ----------
    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 6}

        # 顶部工具条
        bar = ttk.Frame(self.root)
        bar.pack(fill=tk.X, **pad)

        self.var_source = tk.StringVar(value=self.args.source)
        self.var_port = tk.StringVar(value=self.args.port)
        self.var_record = tk.BooleanVar(value=not self.args.no_record)
        self.var_perception = tk.BooleanVar(value=self.args.perception
                                            or self.args.source == "real")

        ttk.Label(bar, text="Source:").pack(side=tk.LEFT)
        ttk.Combobox(bar, textvariable=self.var_source,
                     values=["sim", "synthetic-frame", "cdc", "real"],
                     width=15, state="readonly").pack(side=tk.LEFT, padx=4)
        ttk.Label(bar, text="Port:").pack(side=tk.LEFT)
        ttk.Entry(bar, textvariable=self.var_port, width=8).pack(side=tk.LEFT, padx=4)
        ttk.Checkbutton(bar, text="Record", variable=self.var_record).pack(side=tk.LEFT, padx=8)
        ttk.Checkbutton(bar, text="Perception", variable=self.var_perception).pack(side=tk.LEFT)

        self.btn_start = ttk.Button(bar, text="Start", command=self._on_start)
        self.btn_start.pack(side=tk.LEFT, padx=8)
        self.btn_stop = ttk.Button(bar, text="Stop", command=self._on_stop, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT)

        # 中央: 交通灯 + 大号最终指示 (取 min(可用模态) 作为总灯)
        mid = ttk.Frame(self.root)
        mid.pack(fill=tk.X, **pad)

        self.canvas_light = tk.Canvas(mid, width=100, height=100,
                                      highlightthickness=0, bg=self.root["bg"])
        self.canvas_light.pack(side=tk.LEFT, padx=12)
        self._light = self.canvas_light.create_oval(10, 10, 90, 90,
                                                    fill="#888888", outline="")

        info = ttk.Frame(mid)
        info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.var_score = tk.StringVar(value="--")
        self.lbl_score = tk.Label(info, textvariable=self.var_score,
                                  font=("Segoe UI", 48, "bold"))
        self.lbl_score.pack(anchor="w")
        self.var_score_sub = tk.StringVar(value="min modal score (rough)")
        ttk.Label(info, textvariable=self.var_score_sub,
                  foreground="#666").pack(anchor="w")

        # 5 模态卡片
        card = ttk.LabelFrame(self.root, text="Modalities (0-100)")
        card.pack(fill=tk.X, **pad)
        for i, (k, name) in enumerate(MODALS):
            box = tk.Frame(card, bd=1, relief=tk.SOLID, bg="#333")
            box.grid(row=0, column=i, padx=4, pady=4, sticky="nsew")
            card.grid_columnconfigure(i, weight=1)
            ttk.Label(box, text=name, foreground="#ccc",
                      background="#333",
                      font=("Segoe UI", 9)).pack(anchor="w", padx=6, pady=(4, 0))
            var = tk.StringVar(value="--")
            lbl = tk.Label(box, textvariable=var, bg="#333", fg="#888",
                           font=("Segoe UI", 24, "bold"))
            lbl.pack(anchor="w", padx=6, pady=(0, 4))
            self._modal_labels[k] = (var, lbl)
            self._modal_boxes[k] = box

        # sparkline (跟随最终指示)
        spark_frame = ttk.LabelFrame(self.root, text="Final score trend (last 60 frames)")
        spark_frame.pack(fill=tk.X, **pad)
        self.canvas_spark = tk.Canvas(spark_frame, height=80, bg="#1e1e1e",
                                      highlightthickness=0)
        self.canvas_spark.pack(fill=tk.X, padx=6, pady=6)

        # 统计
        stat = ttk.LabelFrame(self.root, text="Stats")
        stat.pack(fill=tk.X, **pad)
        self.var_stats = tk.StringVar(value="idle")
        ttk.Label(stat, textvariable=self.var_stats,
                  font=("Consolas", 10)).pack(anchor="w", padx=8, pady=4)

        # 日志
        log_frame = ttk.LabelFrame(self.root, text="Recent frames")
        log_frame.pack(fill=tk.BOTH, expand=True, **pad)
        self.txt_log = tk.Text(log_frame, height=8, bg="#1e1e1e", fg="#ddd",
                               font=("Consolas", 9), state=tk.DISABLED)
        self.txt_log.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

    def _make_source(self):
        s = self.var_source.get()
        if s == "cdc":
            return CdcReader(self.var_port.get(), self.args.baud)
        if s == "real":
            return RealSource(cam_index=self.args.cam)
        if s == "synthetic-frame":
            return SyntheticFrameSource()
        return SimSource()

    def _on_start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._n_frames = 0
        self._t0 = time.time()
        self._spark.clear()
        self._log_lines.clear()
        self._push_log("=== start ===")

        if self.var_record.get():
            device_id = self._load_device_id()
            self._rec = FrameRecorder(self.args.data_dir, device_id)
            self._rec.open()

        self._worker = SourceWorker(
            self._make_source, self._q, self._rec,
            enable_perception=self.var_perception.get(),
            face_backend=self.args.face_backend,
            yolo_weights=self.args.yolo_weights,
        )
        self._worker.start()
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)

    def _on_stop(self) -> None:
        if self._worker is not None:
            self._worker.stop()
            self._worker.join(timeout=2)
            self._worker = None
        if self._rec is not None:
            self._rec.close()
            self._rec = None
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self._push_log("=== stop ===")

    def _on_close(self) -> None:
        self._on_stop()
        self.root.destroy()

    def _load_device_id(self) -> str:
        try:
            pf = load_profile(self.args.profile)
            return pf.device_id
        except Exception as e:
            log.warning("profile load failed: %s, use default id", e)
            return "sg-0001"

    # ---------- tick ----------
    def _schedule_tick(self) -> None:
        self.root.after(UI_TICK_MS, self._tick)

    def _tick(self) -> None:
        try:
            drained = 0
            latest_frame = None
            latest_res = None
            while drained < 50:
                try:
                    item = self._q.get_nowait()
                except queue.Empty:
                    break
                frame, res = item
                latest_frame, latest_res = frame, res
                drained += 1
                self._n_frames += 1
                js = frame.json or {}
                extras = ""
                if res:
                    parts = []
                    for k, _ in MODALS:
                        m = res.get(k)
                        if m and m["score"] >= 0:
                            tag = {"face": "F", "speech": "S",
                                   "tongue": "T", "eye": "E", "csi": "B"}[k]
                            parts.append(f"{tag}={m['score']}")
                    if parts:
                        extras = "  " + " ".join(parts)
                self._push_log(
                    f"#{self._n_frames-1:>5d} {frame.type_name:<9} "
                    f"csi={js.get('csi_score')} seq={js.get('seq')} ts={js.get('ts')}"
                    f"{extras}"
                )

            if drained > 0:
                self._update_all(latest_frame, latest_res)
            self._update_stats()

            if self._worker and not self._worker.is_alive() and self._worker.err:
                self._push_log(f"!! worker error: {self._worker.err}")
                self._on_stop()
        finally:
            self._schedule_tick()

    def _update_all(self, frame: Frame, res: Optional[dict]) -> None:
        js = frame.json or {}

        # 更新 5 卡片
        scores_available = []
        for k, _ in MODALS:
            var, lbl = self._modal_labels[k]
            box = self._modal_boxes[k]
            m = (res or {}).get(k)
            if m and m["score"] >= 0:
                s = m["score"]
                scores_available.append(s)
                var.set(str(s))
                lbl.config(fg=_traffic_color(s))
                box.config(highlightbackground=_traffic_color(s),
                           highlightthickness=2, bg="#222")
            else:
                # 特例: heartbeat 帧携带 csi_score, csi 卡片仍可显
                if k == "csi" and js.get("csi_score") is not None:
                    s = int(js["csi_score"])
                    scores_available.append(s)
                    var.set(str(s))
                    lbl.config(fg=_traffic_color(s))
                else:
                    var.set("--")
                    lbl.config(fg="#666")

        # 总指示: 取最小可用分 (风险提示"宁误报")
        if scores_available:
            final = min(scores_available)
        elif js.get("csi_score") is not None:
            final = int(js["csi_score"])
        else:
            final = None
        self._update_final(final)

    def _update_final(self, final: Optional[int]) -> None:
        if final is None:
            self.var_score.set("--")
            self.lbl_score.config(fg="#666")
            self.canvas_light.itemconfig(self._light, fill="#888")
            self._spark.append(None)
        else:
            self.var_score.set(str(final))
            color = _traffic_color(final)
            self.lbl_score.config(fg=color)
            self.canvas_light.itemconfig(self._light, fill=color)
            self._spark.append(final)
        if len(self._spark) > SPARK_LEN:
            self._spark = self._spark[-SPARK_LEN:]
        self._update_spark()

    def _update_spark(self) -> None:
        c = self.canvas_spark
        c.delete("all")
        w = int(c.winfo_width())
        h = int(c.winfo_height())
        if w < 10 or h < 10:
            return
        y_warn = h - int(h * CSI_WARN / 100)
        y_dgr = h - int(h * CSI_DANGER / 100)
        c.create_line(0, y_warn, w, y_warn, fill="#444", dash=(2, 3))
        c.create_line(0, y_dgr, w, y_dgr, fill="#663", dash=(2, 3))

        pts = self._spark
        if len(pts) < 2:
            return
        step = w / max(SPARK_LEN - 1, 1)
        prev = None
        for i, v in enumerate(pts):
            if v is None:
                prev = None
                continue
            x = int(i * step)
            y = h - int(h * max(0, min(100, v)) / 100)
            if prev is not None:
                px, py = prev
                c.create_line(px, py, x, y, fill=_traffic_color(v), width=2)
            prev = (x, y)

    def _update_stats(self) -> None:
        dt = max(0.001, time.time() - self._t0)
        fps = self._n_frames / dt
        line = f"frames={self._n_frames}  fps={fps:5.2f}  elapsed={dt:6.1f}s"
        if self._worker and self._worker.source is not None and isinstance(
                self._worker.source, CdcReader):
            r = self._worker.source
            line += f"  |  cdc ok={r.n_ok} crc_err={r.n_crc_err} resync={r.n_resync}"
        if self._rec is not None and self._rec._session_dir:
            line += f"  |  rec={self._rec._session_dir.name}"
        self.var_stats.set(line)

    def _push_log(self, s: str) -> None:
        self._log_lines.append(s)
        if len(self._log_lines) > LOG_TAIL:
            self._log_lines = self._log_lines[-LOG_TAIL:]
        self.txt_log.config(state=tk.NORMAL)
        self.txt_log.delete("1.0", tk.END)
        self.txt_log.insert(tk.END, "\n".join(self._log_lines))
        self.txt_log.see(tk.END)
        self.txt_log.config(state=tk.DISABLED)

    def run(self) -> None:
        self.root.mainloop()


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stroke-observer",
                                description="StrokeGuard live observer")
    p.add_argument("--source", choices=["cdc", "sim", "synthetic-frame", "real"], default="sim")
    p.add_argument("--port", default="COM3")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--cam", type=int, default=0)
    p.add_argument("--profile", default="config/profile.yaml")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--no-record", action="store_true")
    p.add_argument("--perception", action="store_true",
                   help="enable F/S/Tongue/E/B scoring on data frames")
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
    app = ObserverApp(args)
    app.run()


if __name__ == "__main__":
    main()
