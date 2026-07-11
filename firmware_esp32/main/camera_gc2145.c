#include "camera_gc2145.h"
#include "board_pins.h"
#include "log_tag.h"
#include "esp_log.h"

esp_err_t sg_camera_gc2145_init(void)
{
#if CONFIG_STROKEGUARD_HW_CAMERA_ENABLE
    ESP_LOGW(SG_TAG_MAIN,
             "GC2145 enabled but real driver is pending wiring confirmation "
             "(xclk=%d siod=%d sioc=%d)",
             SG_PIN_GC2145_XCLK, SG_PIN_GC2145_SIOD, SG_PIN_GC2145_SIOC);
    return ESP_ERR_NOT_SUPPORTED;
#else
    ESP_LOGI(SG_TAG_MAIN, "GC2145 disabled; using synthetic JPEG frame");
    return ESP_ERR_NOT_SUPPORTED;
#endif
}

esp_err_t sg_camera_gc2145_capture(sg_camera_gc2145_frame_t *out)
{
    if (!out) return ESP_ERR_INVALID_ARG;
    out->jpeg_b64 = NULL;
    out->jpeg_b64_len = 0;
    out->width = 0;
    out->height = 0;
    return ESP_ERR_NOT_SUPPORTED;
}
