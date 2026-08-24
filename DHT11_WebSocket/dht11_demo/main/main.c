#include <stdio.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_log.h"
#include "esp_system.h"

#include "dht11.h"
#include "app_config.h"
#include "wifi.h"
#include "ws_client.h"

static const char *TAG = "APP";

/**
 * @brief WiFi 状态变化回调
 */
static void on_wifi_status(bool connected)
{
    if (connected) {
        ESP_LOGI(TAG, "[CB] WiFi UP, RSSI=%d dBm", wifi_get_rssi());
    } else {
        ESP_LOGW(TAG, "[CB] WiFi DOWN");
    }
}

/**
 * @brief WebSocket 状态变化回调
 */
static void on_ws_status(bool connected)
{
    if (connected) {
        ESP_LOGI(TAG, "[CB] WebSocket UP");
    } else {
        ESP_LOGW(TAG, "[CB] WebSocket DOWN (will auto-reconnect)");
    }
}

void app_main(void)
{
    printf("========== DHT11 + WiFi + WebSocket Started ==========\n");
    printf("Device ID : %s\n", APP_DEVICE_ID);
    printf("WS URL    : %s\n", APP_WS_URL);
    printf("Interval  : %d ms\n", APP_REPORT_INTERVAL_MS);

    // 初始化 DHT11 传感器
    dht11_t sensor;
    dht11_init(&sensor, APP_DHT11_GPIO);

    // 注册状态回调（用于在串口观察连接状态）
    wifi_register_callback(on_wifi_status);
    ws_register_callback(on_ws_status);

    // 初始化 WiFi（阻塞等待 IP，超时 APP_WIFI_TIMEOUT_MS）
    esp_err_t wifi_ret = wifi_init_sta(APP_WIFI_SSID,
                                       APP_WIFI_PASSWORD,
                                       APP_WIFI_TIMEOUT_MS);
    if (wifi_ret != ESP_OK) {
        ESP_LOGE(TAG, "WiFi init failed: %s (sensor loop will keep running)",
                 esp_err_to_name(wifi_ret));
    }

    // 初始化 WebSocket 客户端（后端未就绪时会自动重试，不会卡死）
    esp_err_t ws_ret = ws_client_init(APP_WS_URL, APP_DEVICE_ID);
    if (ws_ret != ESP_OK) {
        ESP_LOGE(TAG, "WebSocket init failed: %s", esp_err_to_name(ws_ret));
    }

    // 传感器读取 + 数据上报主循环
    while (1)
    {
        if (dht11_read(&sensor) == ESP_OK)
        {
            // 串口输出（保留，便于后端未就绪时通过串口查看数据）
            // 格式: [SENSOR_DATA]{"temp":30,"humi":70}
            printf("[SENSOR_DATA]{\"temp\":%d,\"humi\":%d}\n",
                   sensor.temperature,
                   sensor.humidity);
            fflush(stdout);

            // 通过 WebSocket 上报（带 RSSI 信号强度）
            int rssi = wifi_get_rssi();
            esp_err_t send_ret = ws_send_sensor_data(sensor.temperature,
                                                     sensor.humidity,
                                                     rssi);
            // 未连接时静默（连接状态由回调统一打印，避免刷屏）
            if (send_ret != ESP_OK && send_ret != ESP_ERR_INVALID_STATE) {
                ESP_LOGW(TAG, "WS send failed: %s",
                         esp_err_to_name(send_ret));
            }
        }
        else
        {
            ESP_LOGE(TAG, "Read DHT11 failed");
        }

        vTaskDelay(pdMS_TO_TICKS(APP_REPORT_INTERVAL_MS));
    }
}
