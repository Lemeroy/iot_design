import pytest

from stroke_host.camera_preview.protocol import encode_test_packet
from stroke_host.camera_preview.serial_worker import (
    CameraPreviewSession,
    PreviewTimeout,
)


JPEG = b"\xff\xd8preview\xff\xd9"


class FakeSerial:
    def __init__(self, responses):
        self.responses = list(responses)
        self.writes = []
        self.closed = False

    @property
    def in_waiting(self):
        return len(self.responses[0]) if self.responses else 0

    def write(self, data):
        self.writes.append(bytes(data))
        return len(data)

    def read(self, size):
        if not self.responses:
            return b""
        data = self.responses.pop(0)
        return data[:size]

    def close(self):
        self.closed = True


def test_session_requests_exactly_one_frame_at_a_time():
    serial_port = FakeSerial(
        [
            encode_test_packet(JPEG, sequence=1),
            encode_test_packet(JPEG, sequence=2),
        ]
    )
    session = CameraPreviewSession(serial_port, timeout=0.2)

    first = session.next_frame()
    assert first.sequence == 1
    assert serial_port.writes == [b"\xa5"]

    second = session.next_frame()
    assert second.sequence == 2
    assert serial_port.writes == [b"\xa5", b"\xa5"]


def test_session_times_out_when_camera_does_not_reply():
    session = CameraPreviewSession(FakeSerial([]), timeout=0)

    with pytest.raises(PreviewTimeout):
        session.next_frame()


def test_session_close_releases_serial_port():
    serial_port = FakeSerial([])
    session = CameraPreviewSession(serial_port)

    session.close()

    assert serial_port.closed
