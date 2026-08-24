#include "ws_client.h"
#include "app_config.h"

#include <string.h>
#include <stdatomic.h>
#include <time.h>

#include "esp_log.h"
#include "esp_websocket_client.h"
#include "esp_timer.h"

static const char *TAG = "WS_CLIENT";

static esp_websocket_client_handle_t g_ws_client = NULL;
static atomic_bool g_ws_connected = false;
static ws_status_cb_t g_status_callback = NULL;
static char g_device_id[32] = {0};

/**
 * @brief WebSocket 事件处理函数
 */
static void ws_event_handler(void *arg, esp_event_base_t event_base,
                             int32_t event_id, void *event_data)
{
    esp_websocket_event_data_t *data = (esp_websocket_event_data_t *)event_data;

    switch (event_id) {
    case WEBSOCKET_EVENT_CONNECTED:
        ESP_LOGI(TAG, "WebSocket connected");
        g_ws_connected = true;
        if (g_status_callback) {
            g_status_callback(true);
        }
        break;

    case WEBSOCKET_EVENT_DISCONNECTED:
        ESP_LOGW(TAG, "WebSocket disconnected");
        g_ws_connected = false;
        if (g_status_callback) {
            g_status_callback(false);
        }
        break;

    case WEBSOCKET_EVENT_DATA:
        // 如果需要处理服务器下发数据，可在此扩展
        ESP_LOGD(TAG, "Received data: %.*s", data->data_len, (char *)data->data_ptr);
        break;

    case WEBSOCKET_EVENT_ERROR:
        ESP_LOGE(TAG, "WebSocket error");
        break;

    case WEBSOCKET_EVENT_CLOSED:
        ESP_LOGI(TAG, "WebSocket closed");
        g_ws_connected = false;
        if (g_status_callback) {
            g_status_callback(false);
        }
        break;

    default:
        break;
    }
}

esp_err_t ws_client_init(const char *uri, const char *device_id)
{
    if (g_ws_client != NULL) {
        ESP_LOGW(TAG, "WebSocket client already initialized");
        return ESP_OK;
    }

    // 保存设备 ID
    if (device_id != NULL) {
        strncpy(g_device_id, device_id, sizeof(g_device_id) - 1);
    } else {
        strncpy(g_device_id, "unknown", sizeof(g_device_id) - 1);
    }

    // 配置 WebSocket 客户端
    // 关键：对于 ws:// (明文) 必须显式禁用 TLS，否则 esp_websocket_client
    // 在某些 IDF 版本下会尝试走 TLS 握手，导致 select() 超时 (10s) 失败。
    esp_websocket_client_config_t ws_cfg = {
        .uri = uri,
        .transport = WEBSOCKET_TRANSPORT_OVER_TCP,  // 强制使用明文 TCP，禁用 TLS
        .reconnect_timeout_ms = APP_WS_RECONNECT_MS,
        .network_timeout_ms = 10000,
        .buffer_size = 512,
        .path = NULL,  // URI 中已包含
        // ===== 显式禁用 TLS（适用于 ws:// 明文连接） =====
        .use_global_ca_store = false,
        .cert_pem = NULL,
        .client_cert = NULL,
        .client_key = NULL,
        .skip_cert_common_name_check = true,
        // ===== 子协议与心跳 =====
        .subprotocol = NULL,
        .user_agent = "esp32s3-dht11/1.0",
        .headers = NULL,
        // ===== Ping 间隔（保持长连接，0 表示禁用） =====
        .ping_interval_sec = 0,
    };

    ESP_LOGI(TAG, "Connecting to WebSocket: %s", uri);

    g_ws_client = esp_websocket_client_init(&ws_cfg);
    if (g_ws_client == NULL) {
        ESP_LOGE(TAG, "Failed to initialize WebSocket client");
        return ESP_FAIL;
    }

    // 注册事件处理函数
    ESP_ERROR_CHECK(esp_websocket_register_events(g_ws_client,
                                                    WEBSOCKET_EVENT_ANY,
                                                    ws_event_handler,
                                                    NULL));

    // 启动连接
    esp_err_t ret = esp_websocket_client_start(g_ws_client);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start WebSocket client: %s", esp_err_to_name(ret));
        esp_websocket_client_destroy(g_ws_client);
        g_ws_client = NULL;
        return ret;
    }

    ESP_LOGI(TAG, "WebSocket client started");
    return ESP_OK;
}

esp_err_t ws_send_sensor_data(uint8_t temperature, uint8_t humidity, int rssi)
{
    if (g_ws_client == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    if (!g_ws_connected) {
        // 静默返回，避免每 2 秒刷屏（连接状态由回调统一打印）
        return ESP_ERR_INVALID_STATE;
    }

    // 构建 JSON 数据（仅包含 temp 和 humi）
    char json_buf[64];
    int len = snprintf(json_buf, sizeof(json_buf),
        "{\"temp\":%u,\"humi\":%u}",
        temperature, humidity);

    if (len < 0 || len >= sizeof(json_buf)) {
        ESP_LOGE(TAG, "Failed to format JSON data");
        return ESP_FAIL;
    }

    // 发送数据（带 1 秒超时，避免 portMAX_DELAY 在异常时死等）
    int ret = esp_websocket_client_send_text(g_ws_client, json_buf, len,
                                              pdMS_TO_TICKS(1000));
    if (ret < 0) {
        ESP_LOGW(TAG, "Send failed, ret=%d", ret);
        return ESP_FAIL;
    }

    ESP_LOGD(TAG, "Sent: %s", json_buf);
    return ESP_OK;
}

void ws_register_callback(ws_status_cb_t callback)
{
    g_status_callback = callback;
}

bool ws_is_connected(void)
{
    return g_ws_connected;
}

void ws_client_close(void)
{
    if (g_ws_client != NULL) {
        esp_websocket_client_stop(g_ws_client);
        esp_websocket_client_destroy(g_ws_client);
        g_ws_client = NULL;
        g_ws_connected = false;
        ESP_LOGI(TAG, "WebSocket client closed");
    }
}