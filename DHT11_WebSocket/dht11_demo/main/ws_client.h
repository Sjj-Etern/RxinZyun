#ifndef WS_CLIENT_H
#define WS_CLIENT_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdbool.h>
#include "esp_err.h"

/**
 * @brief WebSocket 状态回调函数类型
 */
typedef void (*ws_status_cb_t)(bool connected);

/**
 * @brief 初始化 WebSocket 客户端
 *
 * @param uri      WebSocket 服务器 URI (ws://host:port/path 或 wss://host/path)
 * @param device_id 设备标识
 *
 * @return ESP_OK 成功，其他值失败
 */
esp_err_t ws_client_init(const char *uri, const char *device_id);

/**
 * @brief 发送温湿度数据
 *
 * @param temperature 温度值
 * @param humidity    湿度值
 * @param rssi       WiFi 信号强度
 *
 * @return ESP_OK 成功，其他值失败
 */
esp_err_t ws_send_sensor_data(uint8_t temperature, uint8_t humidity, int rssi);

/**
 * @brief 注册 WebSocket 状态回调函数
 *
 * @param callback 状态回调函数
 */
void ws_register_callback(ws_status_cb_t callback);

/**
 * @brief 检查 WebSocket 是否已连接
 *
 * @return true 已连接，false 未连接
 */
bool ws_is_connected(void);

/**
 * @brief 关闭 WebSocket 客户端
 */
void ws_client_close(void);

#ifdef __cplusplus
}
#endif

#endif // WS_CLIENT_H