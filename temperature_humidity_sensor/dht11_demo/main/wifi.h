#ifndef WIFI_H
#define WIFI_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdbool.h>
#include "esp_err.h"

/**
 * @brief WiFi 状态回调函数类型
 */
typedef void (*wifi_status_cb_t)(bool connected);

/**
 * @brief 初始化 WiFi STA 模式
 *
 * @param ssid       WiFi SSID
 * @param password   WiFi 密码
 * @param timeout_ms 连接超时时间（毫秒）
 *
 * @return ESP_OK 成功，其他值失败
 */
esp_err_t wifi_init_sta(const char *ssid, const char *password, uint32_t timeout_ms);

/**
 * @brief 注册 WiFi 状态回调函数
 *
 * @param callback 状态回调函数
 */
void wifi_register_callback(wifi_status_cb_t callback);

/**
 * @brief 检查 WiFi 是否已连接
 *
 * @return true 已连接，false 未连接
 */
bool wifi_is_connected(void);

/**
 * @brief 获取当前 WiFi RSSI 信号强度
 *
 * @return RSSI 值（dBm），负值，如 -50，值越大信号越强
 */
int wifi_get_rssi(void);

#ifdef __cplusplus
}
#endif

#endif // WIFI_H