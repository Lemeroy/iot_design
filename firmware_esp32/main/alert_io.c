#include "alert_io.h"
#include "board_pins.h"
#include "log_tag.h"
#include "esp_log.h"

esp_err_t sg_alert_io_init(void)
{
#if CONFIG_STROKEGUARD_HW_ALERT_ENABLE
    ESP_LOGW(SG_TAG_MAIN,
             "alert IO enabled but RGB/buzzer/buttons are pending wiring "
             "confirmation (rgb=%d buzzer=%d btn1=%d)",
             SG_PIN_ALERT_RGB, SG_PIN_ALERT_BUZZER, SG_PIN_BUTTON_1);
    return ESP_ERR_NOT_SUPPORTED;
#else
    ESP_LOGI(SG_TAG_MAIN, "alert IO disabled");
    return ESP_ERR_NOT_SUPPORTED;
#endif
}

esp_err_t sg_alert_io_set_level(const char *level)
{
    (void)level;
    return ESP_ERR_NOT_SUPPORTED;
}
