import struct
import zlib

import pytest

from stroke_host.camera_preview.protocol import (
    MAX_JPEG_SIZE,
    PreviewProtocolError,
    PreviewStreamParser,
    encode_test_packet,
)


JPEG = b"\xff\xd8camera-preview\xff\xd9"


def test_parser_accepts_partial_packet_and_preserves_bbox():
    packet = encode_test_packet(JPEG, sequence=7, bbox=(120, 96, 80, 90))
    parser = PreviewStreamParser()

    assert parser.feed(packet[:9]) == []
    frames = parser.feed(packet[9:])

    assert len(frames) == 1
    assert frames[0].jpeg == JPEG
    assert frames[0].sequence == 7
    assert frames[0].bbox == (120, 96, 80, 90)


def test_parser_resynchronizes_after_console_text_and_multiple_packets():
    first = encode_test_packet(JPEG, sequence=10)
    second = encode_test_packet(JPEG, sequence=11)
    parser = PreviewStreamParser()

    frames = parser.feed(b"I (42) boot log\r\n" + first + second)

    assert [frame.sequence for frame in frames] == [10, 11]


def test_parser_rejects_bad_crc_then_recovers_at_next_magic():
    broken = bytearray(encode_test_packet(JPEG, sequence=1))
    broken[-1] ^= 0xFF
    valid = encode_test_packet(JPEG, sequence=2)
    parser = PreviewStreamParser()

    frames = parser.feed(bytes(broken) + valid)

    assert [frame.sequence for frame in frames] == [2]
    assert parser.rejected_frames == 1


@pytest.mark.parametrize("jpeg", [b"not-jpeg", b"\xff\xd8missing-end"])
def test_test_encoder_rejects_invalid_jpeg(jpeg):
    with pytest.raises(PreviewProtocolError):
        encode_test_packet(jpeg, sequence=1)


def test_parser_rejects_oversized_length_without_waiting_for_payload():
    header = struct.pack(
        "<4sBBHII4B", b"SGJP", 1, 0, 20, 9, MAX_JPEG_SIZE + 1, 0, 0, 0, 0
    )
    parser = PreviewStreamParser()

    assert parser.feed(header + b"SGJP") == []
    assert parser.rejected_frames == 1


def test_crc_covers_header_after_magic_and_jpeg_payload():
    packet = encode_test_packet(JPEG, sequence=99, bbox=(1, 2, 3, 4))
    header_size = struct.unpack_from("<H", packet, 6)[0]
    jpeg_size = struct.unpack_from("<I", packet, 12)[0]
    expected_crc = struct.unpack_from("<I", packet, header_size + jpeg_size)[0]

    assert expected_crc == zlib.crc32(packet[4 : header_size + jpeg_size])
