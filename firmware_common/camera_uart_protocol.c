#include "camera_uart_protocol.h"

#include <string.h>

#define SG_CAMERA_UART_FLAG_FACE 0x01U
#define SG_CAMERA_UART_FLAG_EYE 0x02U
#define SG_CAMERA_UART_FLAG_TONGUE 0x04U
#define SG_CAMERA_UART_FLAGS_MASK 0x07U

static uint16_t crc16_ccitt(const uint8_t *data, size_t length)
{
    uint16_t crc = 0xffffU;
    for (size_t i = 0; i < length; ++i) {
        crc ^= (uint16_t)data[i] << 8;
        for (unsigned bit = 0; bit < 8; ++bit) {
            crc = (crc & 0x8000U) != 0U
                ? (uint16_t)((crc << 1) ^ 0x1021U)
                : (uint16_t)(crc << 1);
        }
    }
    return crc;
}

static bool face_valid(const sg_camera_face_metrics_t *value)
{
    return !value->valid || (value->score <= 100U && value->quality <= 100U
        && value->mouth_angle_deg >= -90 && value->mouth_angle_deg <= 90);
}

static bool modal_valid(const sg_camera_modal_metrics_t *value)
{
    return !value->valid || (value->score <= 100U && value->quality <= 100U
        && value->signed_value >= -100 && value->signed_value <= 100);
}

sg_camera_uart_result_t sg_camera_uart_encode(
    const sg_camera_uart_payload_t *payload,
    uint16_t sequence,
    uint8_t out[SG_CAMERA_UART_PACKET_SIZE])
{
    if (payload == NULL || out == NULL) return SG_CAMERA_UART_BAD_ARGUMENT;
    if (!face_valid(&payload->face) || !modal_valid(&payload->eye)
        || !modal_valid(&payload->tongue)
        || payload->screening.stage > SG_STAGE_ERROR
        || payload->screening.progress > 100U) {
        return SG_CAMERA_UART_BAD_VALUE;
    }

    memset(out, 0, SG_CAMERA_UART_PACKET_SIZE);
    out[0] = SG_CAMERA_UART_MAGIC0;
    out[1] = SG_CAMERA_UART_MAGIC1;
    out[2] = SG_CAMERA_UART_VERSION;
    out[3] = SG_CAMERA_UART_PACKET_SIZE;
    out[4] = (uint8_t)(sequence & 0xffU);
    out[5] = (uint8_t)(sequence >> 8);
    if (payload->face.valid) {
        out[6] |= SG_CAMERA_UART_FLAG_FACE;
        out[7] = payload->face.score;
        out[8] = (uint8_t)payload->face.mouth_angle_deg;
        out[9] = payload->face.quality;
    }
    if (payload->eye.valid) {
        out[6] |= SG_CAMERA_UART_FLAG_EYE;
        out[10] = payload->eye.score;
        out[11] = (uint8_t)payload->eye.signed_value;
        out[12] = payload->eye.quality;
    }
    if (payload->tongue.valid) {
        out[6] |= SG_CAMERA_UART_FLAG_TONGUE;
        out[13] = payload->tongue.score;
        out[14] = (uint8_t)payload->tongue.signed_value;
        out[15] = payload->tongue.quality;
    }
    out[16] = (uint8_t)payload->screening.stage;
    out[17] = payload->screening.progress;
    const uint16_t crc = crc16_ccitt(out, SG_CAMERA_UART_PACKET_SIZE - 2U);
    out[18] = (uint8_t)(crc & 0xffU);
    out[19] = (uint8_t)(crc >> 8);
    return SG_CAMERA_UART_OK;
}

sg_camera_uart_result_t sg_camera_uart_parse(
    const uint8_t *data,
    size_t length,
    sg_camera_uart_payload_t *payload,
    uint16_t *sequence)
{
    if (data == NULL || payload == NULL || sequence == NULL) {
        return SG_CAMERA_UART_BAD_ARGUMENT;
    }
    if (length != SG_CAMERA_UART_PACKET_SIZE
        || data[3] != SG_CAMERA_UART_PACKET_SIZE) {
        return SG_CAMERA_UART_BAD_LENGTH;
    }
    if (data[0] != SG_CAMERA_UART_MAGIC0 || data[1] != SG_CAMERA_UART_MAGIC1) {
        return SG_CAMERA_UART_BAD_MAGIC;
    }
    if (data[2] != SG_CAMERA_UART_VERSION) return SG_CAMERA_UART_BAD_VERSION;
    const uint16_t expected = (uint16_t)data[18] | (uint16_t)data[19] << 8;
    if (crc16_ccitt(data, SG_CAMERA_UART_PACKET_SIZE - 2U) != expected) {
        return SG_CAMERA_UART_BAD_CRC;
    }
    if ((data[6] & ~SG_CAMERA_UART_FLAGS_MASK) != 0U) {
        return SG_CAMERA_UART_BAD_VALUE;
    }

    const uint8_t face_raw[4] = {
        (data[6] & SG_CAMERA_UART_FLAG_FACE) != 0U, data[7], data[8], data[9],
    };
    const uint8_t eye_raw[4] = {
        (data[6] & SG_CAMERA_UART_FLAG_EYE) != 0U, data[10], data[11], data[12],
    };
    const uint8_t tongue_raw[4] = {
        (data[6] & SG_CAMERA_UART_FLAG_TONGUE) != 0U,
        data[13], data[14], data[15],
    };
    const uint8_t stage_raw[4] = {data[16], data[17], 0, 0};
    sg_camera_uart_payload_t parsed = {0};
    if (sg_camera_face_metrics_parse(face_raw, sizeof(face_raw), &parsed.face)
            != SG_CAMERA_PROTOCOL_OK
        || sg_camera_modal_parse(eye_raw, sizeof(eye_raw), &parsed.eye)
            != SG_CAMERA_PROTOCOL_OK
        || sg_camera_modal_parse(tongue_raw, sizeof(tongue_raw), &parsed.tongue)
            != SG_CAMERA_PROTOCOL_OK
        || sg_camera_stage_parse(stage_raw, sizeof(stage_raw), &parsed.screening)
            != SG_CAMERA_PROTOCOL_OK) {
        return SG_CAMERA_UART_BAD_VALUE;
    }
    *payload = parsed;
    *sequence = (uint16_t)data[4] | (uint16_t)data[5] << 8;
    return SG_CAMERA_UART_OK;
}

static void stream_resync(sg_camera_uart_stream_t *stream)
{
    size_t next = 1U;
    while (next < stream->used
           && stream->buffer[next] != SG_CAMERA_UART_MAGIC0) {
        ++next;
    }
    if (next == stream->used) {
        stream->used = 0;
        return;
    }
    memmove(stream->buffer, stream->buffer + next, stream->used - next);
    stream->used -= next;
}

bool sg_camera_uart_stream_feed(
    sg_camera_uart_stream_t *stream,
    uint8_t byte,
    sg_camera_uart_payload_t *payload,
    uint16_t *sequence)
{
    if (stream == NULL || payload == NULL || sequence == NULL) return false;
    if (stream->used == 0U) {
        if (byte == SG_CAMERA_UART_MAGIC0) stream->buffer[stream->used++] = byte;
        return false;
    }
    if (stream->used == 1U && byte != SG_CAMERA_UART_MAGIC1) {
        if (byte != SG_CAMERA_UART_MAGIC0) stream->used = 0U;
        return false;
    }
    stream->buffer[stream->used++] = byte;
    if (stream->used == 4U
        && (stream->buffer[2] != SG_CAMERA_UART_VERSION
            || stream->buffer[3] != SG_CAMERA_UART_PACKET_SIZE)) {
        stream_resync(stream);
        return false;
    }
    if (stream->used < SG_CAMERA_UART_PACKET_SIZE) return false;

    const bool complete = sg_camera_uart_parse(
        stream->buffer, stream->used, payload, sequence) == SG_CAMERA_UART_OK;
    if (complete) stream->used = 0U;
    else stream_resync(stream);
    return complete;
}
