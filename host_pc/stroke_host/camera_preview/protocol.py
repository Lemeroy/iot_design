from __future__ import annotations

from dataclasses import dataclass
import struct
import zlib


MAGIC = b"SGJP"
VERSION = 1
HEADER = struct.Struct("<4sBBHII4B")
CRC = struct.Struct("<I")
MAX_JPEG_SIZE = 128 * 1024
FLAG_ERROR = 0x01
FLAG_FACE_DETECTED = 0x02
FLAG_LANDMARKS_VALID = 0x04
FLAG_GEOMETRY_VALID = 0x08
FLAG_BASELINE_READY = 0x10
FLAG_F_VALID = 0x20


class PreviewProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class PreviewFrame:
    sequence: int
    jpeg: bytes
    bbox: tuple[int, int, int, int]
    flags: int = 0

    @property
    def error(self) -> bool:
        return bool(self.flags & FLAG_ERROR)

    @property
    def face_detected(self) -> bool:
        return bool(self.flags & FLAG_FACE_DETECTED)

    @property
    def landmarks_valid(self) -> bool:
        return bool(self.flags & FLAG_LANDMARKS_VALID)

    @property
    def geometry_valid(self) -> bool:
        return bool(self.flags & FLAG_GEOMETRY_VALID)

    @property
    def baseline_ready(self) -> bool:
        return bool(self.flags & FLAG_BASELINE_READY)

    @property
    def f_valid(self) -> bool:
        return bool(self.flags & FLAG_F_VALID)


def _valid_jpeg(payload: bytes) -> bool:
    return len(payload) >= 4 and payload[:2] == b"\xff\xd8" and payload[-2:] == b"\xff\xd9"


def encode_test_packet(
    jpeg: bytes,
    *,
    sequence: int,
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0),
    flags: int = 0,
) -> bytes:
    if len(jpeg) > MAX_JPEG_SIZE:
        raise PreviewProtocolError("JPEG exceeds preview size limit")
    if not _valid_jpeg(jpeg):
        raise PreviewProtocolError("invalid JPEG markers")
    header = HEADER.pack(
        MAGIC, VERSION, flags, HEADER.size, sequence, len(jpeg), *bbox
    )
    checksum = zlib.crc32(header[4:] + jpeg)
    return header + jpeg + CRC.pack(checksum)


class PreviewStreamParser:
    def __init__(self) -> None:
        self._buffer = bytearray()
        self.rejected_frames = 0

    def feed(self, data: bytes) -> list[PreviewFrame]:
        self._buffer.extend(data)
        frames: list[PreviewFrame] = []

        while True:
            magic_at = self._buffer.find(MAGIC)
            if magic_at < 0:
                if len(self._buffer) > len(MAGIC) - 1:
                    del self._buffer[: -(len(MAGIC) - 1)]
                return frames
            if magic_at:
                del self._buffer[:magic_at]
            if len(self._buffer) < HEADER.size:
                return frames

            fields = HEADER.unpack_from(self._buffer)
            _, version, flags, header_size, sequence, jpeg_size, *bbox = fields
            if (
                version != VERSION
                or header_size != HEADER.size
                or jpeg_size > MAX_JPEG_SIZE
            ):
                self.rejected_frames += 1
                del self._buffer[0]
                continue

            packet_size = HEADER.size + jpeg_size + CRC.size
            if len(self._buffer) < packet_size:
                return frames

            jpeg = bytes(self._buffer[HEADER.size : HEADER.size + jpeg_size])
            expected_crc = CRC.unpack_from(self._buffer, HEADER.size + jpeg_size)[0]
            actual_crc = zlib.crc32(bytes(self._buffer[4 : HEADER.size]) + jpeg)
            valid_payload = bool(flags & FLAG_ERROR) or _valid_jpeg(jpeg)
            if expected_crc != actual_crc or not valid_payload:
                self.rejected_frames += 1
                del self._buffer[:packet_size]
                continue

            frames.append(
                PreviewFrame(
                    sequence=sequence,
                    jpeg=jpeg,
                    bbox=tuple(bbox),
                    flags=flags,
                )
            )
            del self._buffer[:packet_size]
