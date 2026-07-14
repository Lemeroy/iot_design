from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_preview_tool_has_no_recording_or_network_code():
    paths = [
        ROOT / "stroke_host" / "camera_preview" / "serial_worker.py",
        ROOT / "stroke_host" / "camera_preview" / "window.py",
        ROOT / "tools" / "camera_usb_preview.py",
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    for forbidden in (
        "requests.",
        "socket.",
        "urllib.",
        "imwrite(",
        "save(",
        "write_bytes(",
    ):
        assert forbidden not in source
