#include "audio_inmp441.h"
#include "board_pins.h"
#include "log_tag.h"
#include "esp_log.h"

esp_err_t sg_audio_inmp441_init(void)
{
#if CONFIG_STROKEGUARD_HW_AUDIO_IN_ENABLE
    ESP_LOGW(SG_TAG_MAIN,
             "INMP441 enabled but real I2S capture is pending wiring "
             "confirmation (bclk=%d ws=%d din=%d)",
             SG_PIN_INMP441_BCLK, SG_PIN_INMP441_WS, SG_PIN_INMP441_DIN);
    return ESP_ERR_NOT_SUPPORTED;
#else
    ESP_LOGI(SG_TAG_MAIN, "INMP441 disabled; using synthetic MFCC frame");
    return ESP_ERR_NOT_SUPPORTED;
#endif
}

esp_err_t sg_audio_inmp441_read_mfcc(sg_mfcc_frame_t *out)
{
    if (!out) return ESP_ERR_INVALID_ARG;
    out->frames = 0;
    out->coeffs_per_frame = SG_MFCC_COEFFS;
    return ESP_ERR_NOT_SUPPORTED;
}
