#include "sg_mqtt.h"

#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "mqtt_client.h"
#include "esp_event.h"
#include "esp_log.h"
#include "log_tag.h"

#define SG_MQTT_CONNECTED_BIT BIT0
#define SG_MQTT_TOPIC_MAX     80

typedef struct {
    bool active;
    int total_len;
    int received;
    char data[SG_DOWNLINK_MAX + 1];
} sg_mqtt_assembly_t;

static esp_mqtt_client_handle_t s_client;
static EventGroupHandle_t s_events;
static sg_device_config_t s_config;
static sg_mqtt_downlink_cb_t s_downlink_cb;
static void *s_downlink_ctx;
static char s_client_id[SG_DEVICE_ID_MAX + 4];
static char s_uplink_topic[SG_MQTT_TOPIC_MAX];
static char s_downlink_topic[SG_MQTT_TOPIC_MAX];
static sg_mqtt_assembly_t s_assembly;

static void assembly_reset(void)
{
    memset(&s_assembly, 0, sizeof(s_assembly));
}

static bool event_topic_matches(const esp_mqtt_event_handle_t event,
                                const char *expected)
{
    size_t expected_len = strlen(expected);
    return event->topic && event->topic_len == (int)expected_len
        && memcmp(event->topic, expected, expected_len) == 0;
}

static void handle_data(const esp_mqtt_event_handle_t event)
{
    if (event->data_len < 0 || event->total_data_len <= 0
        || event->current_data_offset < 0) {
        assembly_reset();
        return;
    }

    if (event->current_data_offset == 0) {
        assembly_reset();
        if (!event_topic_matches(event, s_downlink_topic)
            || event->total_data_len > SG_DOWNLINK_MAX) {
            ESP_LOGW(SG_TAG_MQTT, "downlink rejected topic/size");
            return;
        }
        s_assembly.active = true;
        s_assembly.total_len = event->total_data_len;
    }

    if (!s_assembly.active
        || event->total_data_len != s_assembly.total_len
        || event->current_data_offset != s_assembly.received
        || event->data_len > s_assembly.total_len - s_assembly.received) {
        ESP_LOGW(SG_TAG_MQTT, "downlink fragment rejected");
        assembly_reset();
        return;
    }

    memcpy(s_assembly.data + s_assembly.received,
           event->data, (size_t)event->data_len);
    s_assembly.received += event->data_len;
    if (s_assembly.received != s_assembly.total_len) return;

    s_assembly.data[s_assembly.total_len] = '\0';
    sg_mqtt_downlink_t downlink = {0};
    sg_contract_err_t err = sg_cloud_parse_advice(
        s_assembly.data, (size_t)s_assembly.total_len,
        &downlink.payload.advice);
    if (err == SG_CONTRACT_OK) {
        downlink.type = SG_MQTT_DOWNLINK_ADVICE;
    } else {
        err = sg_cloud_parse_screening_control(
            s_assembly.data, (size_t)s_assembly.total_len,
            &downlink.payload.control);
        if (err == SG_CONTRACT_OK) downlink.type = SG_MQTT_DOWNLINK_CONTROL;
    }
    assembly_reset();
    if (err != SG_CONTRACT_OK) {
        ESP_LOGW(SG_TAG_MQTT, "downlink parse rejected err=%d", (int)err);
        return;
    }

    ESP_LOGI(SG_TAG_MQTT, "downlink accepted type=%u", (unsigned)downlink.type);
    if (s_downlink_cb) s_downlink_cb(&downlink, s_downlink_ctx);
}

static void mqtt_event_handler(void *handler_args, esp_event_base_t base,
                               int32_t event_id, void *event_data)
{
    (void)handler_args;
    (void)base;
    esp_mqtt_event_handle_t event = event_data;

    switch ((esp_mqtt_event_id_t)event_id) {
        case MQTT_EVENT_CONNECTED:
            xEventGroupSetBits(s_events, SG_MQTT_CONNECTED_BIT);
            if (esp_mqtt_client_subscribe(s_client, s_downlink_topic, 1) < 0) {
                ESP_LOGW(SG_TAG_MQTT, "downlink subscribe failed");
            } else {
                ESP_LOGI(SG_TAG_MQTT, "mqtt connected");
            }
            break;
        case MQTT_EVENT_DISCONNECTED:
            xEventGroupClearBits(s_events, SG_MQTT_CONNECTED_BIT);
            assembly_reset();
            ESP_LOGW(SG_TAG_MQTT, "mqtt disconnected");
            break;
        case MQTT_EVENT_DATA:
            handle_data(event);
            break;
        case MQTT_EVENT_ERROR:
            ESP_LOGW(SG_TAG_MQTT, "mqtt transport error");
            break;
        default:
            break;
    }
}

esp_err_t sg_mqtt_start(const sg_device_config_t *cfg,
                        sg_mqtt_downlink_cb_t cb, void *ctx)
{
    if (!cfg || !sg_device_config_mqtt_ready(cfg)) return ESP_ERR_INVALID_ARG;
    if (s_client) return ESP_ERR_INVALID_STATE;

    s_config = *cfg;
    s_downlink_cb = cb;
    s_downlink_ctx = ctx;
    assembly_reset();

    int client_len = snprintf(s_client_id, sizeof(s_client_id),
                              "sg-%s", s_config.device_id);
    int up_len = snprintf(s_uplink_topic, sizeof(s_uplink_topic),
                          "strokeguard/%s/uplink", s_config.device_id);
    int down_len = snprintf(s_downlink_topic, sizeof(s_downlink_topic),
                            "strokeguard/%s/downlink", s_config.device_id);
    if (client_len < 0 || (size_t)client_len >= sizeof(s_client_id)
        || up_len < 0 || (size_t)up_len >= sizeof(s_uplink_topic)
        || down_len < 0 || (size_t)down_len >= sizeof(s_downlink_topic)) {
        return ESP_ERR_INVALID_SIZE;
    }

    s_events = xEventGroupCreate();
    if (!s_events) return ESP_ERR_NO_MEM;

    const esp_mqtt_client_config_t mqtt_cfg = {
        .broker.address.uri = s_config.mqtt_uri,
        .credentials.username = s_config.mqtt_user,
        .credentials.client_id = s_client_id,
        .credentials.authentication.password = s_config.mqtt_pass,
        .session.keepalive = 30,
        .network.reconnect_timeout_ms = 5000,
        .task.stack_size = 6144,
        .buffer.size = SG_DOWNLINK_MAX + 256,
        .buffer.out_size = SG_CLOUD_UPLINK_MAX + 256,
        .outbox.limit = 8192,
    };

    s_client = esp_mqtt_client_init(&mqtt_cfg);
    if (!s_client) {
        vEventGroupDelete(s_events);
        s_events = NULL;
        return ESP_ERR_NO_MEM;
    }
    esp_err_t err = esp_mqtt_client_register_event(
        s_client, ESP_EVENT_ANY_ID, mqtt_event_handler, NULL);
    if (err == ESP_OK) err = esp_mqtt_client_start(s_client);
    if (err != ESP_OK) {
        esp_mqtt_client_destroy(s_client);
        s_client = NULL;
        vEventGroupDelete(s_events);
        s_events = NULL;
        return err;
    }
    ESP_LOGI(SG_TAG_MQTT, "mqtt starting device=%s", s_config.device_id);
    return ESP_OK;
}

esp_err_t sg_mqtt_publish_uplink(const char *json, size_t len)
{
    if (!s_client || !json || len == 0 || len > SG_CLOUD_UPLINK_MAX) {
        return ESP_ERR_INVALID_STATE;
    }
    if (!sg_mqtt_connected()) return ESP_ERR_TIMEOUT;
    int message_id = esp_mqtt_client_enqueue(
        s_client, s_uplink_topic, json, (int)len, 1, 0, true);
    return message_id < 0 ? ESP_FAIL : ESP_OK;
}

bool sg_mqtt_connected(void)
{
    return s_events
        && (xEventGroupGetBits(s_events) & SG_MQTT_CONNECTED_BIT) != 0;
}

void sg_mqtt_stop(void)
{
    if (s_client) {
        esp_mqtt_client_stop(s_client);
        esp_mqtt_client_destroy(s_client);
        s_client = NULL;
    }
    if (s_events) {
        vEventGroupDelete(s_events);
        s_events = NULL;
    }
    assembly_reset();
}
