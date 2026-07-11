#include "audio_out_max98357.h"
#include "board_pins.h"
#include "log_tag.h"
#include "esp_log.h"

esp_err_t sg_audio_out_max98357_init(void)
{
#if CONFIG_STROKEGUARD_HW_AUDIO_OUT_ENABLE
    ESP_LOGW(SG_TAG_MAIN,
             "MAX98357A enabled but I2S output is pending wiring confirmation "
             "(bclk=%d lrc=%d din=%d)",
             SG_PIN_MAX98357_BCLK, SG_PIN_MAX98357_LRC, SG_PIN_MAX98357_DIN);
    return ESP_ERR_NOT_SUPPORTED;
#else
    ESP_LOGI(SG_TAG_MAIN, "MAX98357A disabled");
    return ESP_ERR_NOT_SUPPORTED;
#endif
}

esp_err_t sg_audio_out_max98357_play_prompt(const char *text)
{
    (void)text;
    return ESP_ERR_NOT_SUPPORTED;
}
