#include "frame_builder.h"
#include "app_config.h"
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

int sg_frame_build_heartbeat(char *buf, size_t cap,
                             uint32_t ts, uint32_t seq, int csi_score)
{
    if (!buf || cap < 32) return -1;
    int n;
    if (csi_score < 0) {
        n = snprintf(buf, cap,
            "{\"type\":\"heartbeat\",\"ts\":%lu,\"seq\":%lu,\"csi_score\":null,\"fw\":\"%s\"}",
            (unsigned long)ts, (unsigned long)seq, SG_FW_VERSION);
    } else {
        n = snprintf(buf, cap,
            "{\"type\":\"heartbeat\",\"ts\":%lu,\"seq\":%lu,\"csi_score\":%d,\"fw\":\"%s\"}",
            (unsigned long)ts, (unsigned long)seq, csi_score, SG_FW_VERSION);
    }
    if (n < 0 || (size_t)n >= cap) return -1;
    return n;
}

/* helper: append string, 返回写入长度或 -1 溢出 */
static int append(char *buf, size_t cap, size_t *pos, const char *fmt, ...)
{
    if (*pos >= cap) return -1;
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(buf + *pos, cap - *pos, fmt, ap);
    va_end(ap);
    if (n < 0 || (size_t)n >= cap - *pos) return -1;
    *pos += (size_t)n;
    return n;
}

int sg_frame_build_fusion(char *buf, size_t cap, const sg_fusion_out_t *o)
{
    if (!buf || !o || cap < 128) return -1;
    size_t p = 0;

    if (append(buf, cap, &p,
               "{\"type\":\"fusion\",\"seq\":%ld,\"final\":%ld,\"level\":\"%s\","
               "\"veto_by\":[",
               (long)o->seq, (long)o->final,
               sg_fusion_level_name(o->level)) < 0) return -1;

    int written = 0;
    if (o->veto_face) {
        if (append(buf, cap, &p, "\"face\"") < 0) return -1;
        written++;
    }
    if (o->veto_speech) {
        if (append(buf, cap, &p, "%s\"speech\"", written ? "," : "") < 0)
            return -1;
        written++;
    }

    if (append(buf, cap, &p,
               "],\"contributions\":{\"face\":%.2f,\"speech\":%.2f,"
               "\"tongue\":%.2f,\"eye\":%.2f,\"csi\":%.2f},"
               "\"used_weights\":{\"face\":%.3f,\"speech\":%.3f,"
               "\"tongue\":%.3f,\"eye\":%.3f,\"csi\":%.3f},"
               "\"reasons\":[",
               (double)o->contrib_face, (double)o->contrib_speech,
               (double)o->contrib_tongue, (double)o->contrib_eye,
               (double)o->contrib_csi,
               (double)o->w_face, (double)o->w_speech,
               (double)o->w_tongue, (double)o->w_eye,
               (double)o->w_csi) < 0) return -1;

    for (int i = 0; i < o->n_reasons; i++) {
        /* 转义反斜杠与引号: 简化处理, 只转义引号 (reasons 内不太可能有反斜杠) */
        if (append(buf, cap, &p, "%s\"", i ? "," : "") < 0) return -1;
        const char *s = o->reasons[i];
        for (; *s; s++) {
            if (p >= cap - 2) return -1;
            if (*s == '"' || *s == '\\') buf[p++] = '\\';
            buf[p++] = *s;
        }
        if (append(buf, cap, &p, "\"") < 0) return -1;
    }
    if (append(buf, cap, &p, "]}") < 0) return -1;
    return (int)p;
}
