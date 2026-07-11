"""M4 left hero layout sizing tests."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication


def _app():
    app = QApplication.instance()
    return app or QApplication([])


def test_left_hero_uses_smaller_light_and_larger_score(monkeypatch):
    from stroke_host.ui import main_window

    class DummyTts:
        available = False

        def open(self):
            pass

        def close(self):
            pass

        def speak(self, *args, **kwargs):
            pass

    monkeypatch.setattr(main_window, "TtsWorker", DummyTts)
    app = _app()
    args = main_window._build_argparser().parse_args([
        "--source", "synthetic-frame",
        "--no-record",
    ])

    win = main_window.MainWindow(args)

    assert win.lbl_light.width() == 132
    assert win.lbl_light.height() == 132
    assert "font-size: 108px" in win.lbl_final.styleSheet()
    win.close()
    app.processEvents()
