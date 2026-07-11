#include "sensor_frame.h"
#include <stdio.h>

/* Base64 of bytes FF D8 FF D9. It is a tiny SOI/EOI JPEG placeholder for
 * protocol bring-up only. Replace with GC2145 JPEG once the camera is wired. */
#define SG_SYNTH_JPEG_B64 "/9j/2Q=="

static int clamp_csi(int csi_score)
{
    if (csi_score < 0) return 80;
    if (csi_score > 100) return 100;
    return csi_score;
}

int sg_sensor_frame_build_json(char *buf, size_t cap,
                               uint32_t ts, uint32_t seq,
                               int csi_score)
{
    if (!buf || cap < 256) return -1;
    int csi = clamp_csi(csi_score);
    float base = (float)(seq % 10) / 10.0f;

    int n = snprintf(
        buf, cap,
        "{\"type\":\"frame\",\"ts\":%lu,\"seq\":%lu,"
        "\"jpeg_b64\":\"%s\","
        "\"mfcc\":["
            "[%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f],"
            "[%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f],"
            "[%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f],"
            "[%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f]"
        "],\"csi_score\":%d,\"fw\":\"m1b-synth\"}",
        (unsigned long)ts, (unsigned long)seq, SG_SYNTH_JPEG_B64,
        base + 0.00f, base + 0.01f, base + 0.02f, base + 0.03f, base + 0.04f,
        base + 0.05f, base + 0.06f, base + 0.07f, base + 0.08f, base + 0.09f,
        base + 0.10f, base + 0.11f, base + 0.12f,
        base + 0.00f, base + 0.01f, base + 0.02f, base + 0.03f, base + 0.04f,
        base + 0.05f, base + 0.06f, base + 0.07f, base + 0.08f, base + 0.09f,
        base + 0.10f, base + 0.11f, base + 0.12f,
        base + 0.00f, base + 0.01f, base + 0.02f, base + 0.03f, base + 0.04f,
        base + 0.05f, base + 0.06f, base + 0.07f, base + 0.08f, base + 0.09f,
        base + 0.10f, base + 0.11f, base + 0.12f,
        base + 0.00f, base + 0.01f, base + 0.02f, base + 0.03f, base + 0.04f,
        base + 0.05f, base + 0.06f, base + 0.07f, base + 0.08f, base + 0.09f,
        base + 0.10f, base + 0.11f, base + 0.12f,
        csi);
    if (n < 0 || (size_t)n >= cap) return -1;
    return n;
}
