#include "camera_score_target.h"

#include "driver/i2c_slave.h"
#include "hal/gpio_types.h"

static i2c_slave_dev_handle_t s_target;

esp_err_t sg_camera_score_target_init(void)
{
    if (s_target != NULL) return ESP_ERR_INVALID_STATE;
    const i2c_slave_config_t config = {
        .i2c_port = I2C_NUM_1,
        .sda_io_num = GPIO_NUM_47,
        .scl_io_num = GPIO_NUM_48,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .send_buf_depth = 128,
        .slave_addr = SG_CAMERA_I2C_ADDRESS,
        .addr_bit_len = I2C_ADDR_BIT_LEN_7,
        .intr_priority = 0,
    };
    return i2c_new_slave_device(&config, &s_target);
}

esp_err_t sg_camera_score_target_serve(const sg_camera_face_response_t *response)
{
    if (response == NULL) return ESP_ERR_INVALID_ARG;
    if (s_target == NULL) return ESP_ERR_INVALID_STATE;
    return i2c_slave_transmit(
        s_target, (const uint8_t *)response, sizeof(*response), 1000);
}
