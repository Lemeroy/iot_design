#include "sg_time.h"

#include <time.h>
#include "esp_netif_sntp.h"

#define SG_MIN_VALID_UNIX_TIME 1704067200LL

static bool s_started;

esp_err_t sg_time_sync_start(void)
{
    if (s_started) return ESP_OK;
    esp_sntp_config_t config = ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
    esp_err_t err = esp_netif_sntp_init(&config);
    if (err == ESP_OK) s_started = true;
    return err;
}

int64_t sg_time_unix_seconds(void)
{
    time_t now = time(NULL);
    return (int64_t)now >= SG_MIN_VALID_UNIX_TIME ? (int64_t)now : 0;
}

bool sg_time_is_synced(void)
{
    return sg_time_unix_seconds() != 0;
}
