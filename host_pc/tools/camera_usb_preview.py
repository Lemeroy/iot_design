from __future__ import annotations

import argparse
from pathlib import Path
import sys


HOST_ROOT = Path(__file__).resolve().parents[1]
if str(HOST_ROOT) not in sys.path:
    sys.path.insert(0, str(HOST_ROOT))

from PyQt5.QtWidgets import QApplication

from stroke_host.camera_preview.window import CameraPreviewWindow


def main() -> int:
    parser = argparse.ArgumentParser(description="StrokeGuard local camera preview")
    parser.add_argument("--port", default="COM4", help="camera serial port")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    window = CameraPreviewWindow(initial_port=args.port)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
