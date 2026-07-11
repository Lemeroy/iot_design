#include "display_st7789.h"
#include "board_pins.h"
#include "log_tag.h"
#include "esp_log.h"

esp_err_t sg_display_st7789_init(void)
{
#if CONFIG_STROKEGUARD_HW_DISPLAY_ENABLE
    ESP_LOGW(SG_TAG_MAIN,
             "ST7789 enabled but panel init is pending wiring confirmation "
             "(mosi=%d sclk=%d cs=%d dc=%d)",
             SG_PIN_ST7789_MOSI, SG_PIN_ST7789_SCLK,
             SG_PIN_ST7789_CS, SG_PIN_ST7789_DC);
    return ESP_ERR_NOT_SUPPORTED;
#else
    ESP_LOGI(SG_TAG_MAIN, "ST7789 disabled");
    return ESP_ERR_NOT_SUPPORTED;
#endif
}

esp_err_t sg_display_st7789_show_status(const char *level,
                                        const char *advice_text)
{
    (void)level;
    (void)advice_text;
    return ESP_ERR_NOT_SUPPORTED;
}
