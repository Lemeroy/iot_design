#include "audio_nmo432.h"

#include <limits.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

#include "driver/i2s_std.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "app_config.h"
#include "board_pins.h"
#include "log_tag.h"

static i2s_chan_handle_t s_rx_channel;

static int16_t sample_to_i16(int32_t raw)
{
    int32_t scaled = raw >> 16;
    if (scaled > INT16_MAX) return INT16_MAX;
    if (scaled < INT16_MIN) return INT16_MIN;
    return (int16_t)scaled;
}

esp_err_t sg_audio_nmo432_read(sg_audio_block_t *out, uint32_t timeout_ms)
{
    if (out == NULL) return ESP_ERR_INVALID_ARG;
    memset(out, 0, sizeof(*out));
    if (s_rx_channel == NULL) return ESP_ERR_INVALID_STATE;

    int32_t raw[SG_NMO432_BLOCK_SAMPLES];
    size_t bytes_read = 0;
    esp_err_t err = i2s_channel_read(
        s_rx_channel, raw, sizeof(raw), &bytes_read, timeout_ms);
    if (err != ESP_OK) return err;
    if (bytes_read != sizeof(raw)) return ESP_ERR_INVALID_SIZE;

    int16_t minimum = INT16_MAX;
    int16_t maximum = INT16_MIN;
    int32_t peak_abs = 0;
    double energy = 0.0;
    for (size_t i = 0; i < SG_NMO432_BLOCK_SAMPLES; ++i) {
        int16_t sample = sample_to_i16(raw[i]);
        out->samples[i] = sample;
        if (sample < minimum) minimum = sample;
        if (sample > maximum) maximum = sample;
        int32_t magnitude = sample == INT16_MIN ? 32768 : abs(sample);
        if (magnitude > peak_abs) peak_abs = magnitude;
        if (magnitude >= 32767) ++out->clipped_samples;
        energy += (double)sample * (double)sample;
    }
    out->peak = (int16_t)(peak_abs > INT16_MAX ? INT16_MAX : peak_abs);
    out->rms = (float)sqrt(energy / SG_NMO432_BLOCK_SAMPLES);
    out->valid = minimum != maximum
        && out->clipped_samples <= SG_NMO432_BLOCK_SAMPLES / 20;
    return ESP_OK;
}

static void audio_diagnostic_task(void *arg)
{
    (void)arg;
    uint32_t blocks = 0;
    uint32_t valid_blocks = 0;
    float latest_rms = 0.0f;
    int latest_peak = 0;
    while (1) {
        sg_audio_block_t block;
        esp_err_t err = sg_audio_nmo432_read(&block, 1000);
        ++blocks;
        if (err == ESP_OK) {
            latest_rms = block.rms;
            latest_peak = block.peak;
            if (block.valid) ++valid_blocks;
        }
        if (blocks >= 250) {
            ESP_LOGI(SG_TAG_MAIN,
                     "NMO432 quality valid=%lu/%lu rms=%.1f peak=%d speech=unavailable",
                     (unsigned long)valid_blocks, (unsigned long)blocks,
                     (double)latest_rms, latest_peak);
            blocks = 0;
            valid_blocks = 0;
        }
    }
}

esp_err_t sg_audio_nmo432_init(void)
{
    if (s_rx_channel != NULL) return ESP_ERR_INVALID_STATE;

    i2s_chan_config_t channel_config = I2S_CHANNEL_DEFAULT_CONFIG(
        I2S_NUM_AUTO, I2S_ROLE_MASTER);
    esp_err_t err = i2s_new_channel(&channel_config, NULL, &s_rx_channel);
    if (err != ESP_OK) return err;

    i2s_std_config_t standard_config = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(16000),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(
            I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = SG_PIN_NMO432_BCLK,
            .ws = SG_PIN_NMO432_WS,
            .dout = I2S_GPIO_UNUSED,
            .din = SG_PIN_NMO432_DIN,
            .invert_flags = {0},
        },
    };
#if CONFIG_STROKEGUARD_NMO432_CHANNEL_LEFT
    standard_config.slot_cfg.slot_mask = I2S_STD_SLOT_LEFT;
#else
    standard_config.slot_cfg.slot_mask = I2S_STD_SLOT_RIGHT;
#endif
    err = i2s_channel_init_std_mode(s_rx_channel, &standard_config);
    if (err == ESP_OK) err = i2s_channel_enable(s_rx_channel);
    if (err != ESP_OK) {
        i2s_del_channel(s_rx_channel);
        s_rx_channel = NULL;
        return err;
    }
    if (xTaskCreatePinnedToCore(
            audio_diagnostic_task, "nmo432", SG_TASK_AUDIO_STACK, NULL,
            SG_TASK_AUDIO_PRIO, NULL, SG_TASK_AUDIO_CORE) != pdPASS) {
        i2s_channel_disable(s_rx_channel);
        i2s_del_channel(s_rx_channel);
        s_rx_channel = NULL;
        return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}
