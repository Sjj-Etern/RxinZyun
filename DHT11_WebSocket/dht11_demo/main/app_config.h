#ifndef APP_CONFIG_H
#define APP_CONFIG_H

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief WiFi 配置
 * @note 请根据实际环境修改 SSID 和 PASSWORD
 */
#define APP_WIFI_SSID         "wangxiangjun"
#define APP_WIFI_PASSWORD     "68870000"

/**
 * @brief WebSocket 服务器地址
 * @note 后端 WebSocket 服务尚未开发，当前为占位地址
 * @note 后端就绪后，请替换为实际地址（例如 ws://192.168.1.100:8080/api/dht11/wifi）
 * @note 注意：ESP32 不能使用 127.0.0.1（那是设备自身回环），必须使用后端服务所在 PC 的局域网 IP
 * @note ws:// 为明文，wss:// 为加密（公网部署建议使用 wss://）
 */
#define APP_WS_URL            "ws://192.168.1.107:8080/api/dht11/wifi"

/**
 * @brief 设备标识
 * @note 建议使用 MAC 地址或唯一 ID，便于后端识别
 */
#define APP_DEVICE_ID         "esp32s3_dht11_01"

/**
 * @brief 数据上报周期（毫秒）
 */
#define APP_REPORT_INTERVAL_MS    2000

/**
 * @brief WiFi 连接超时（毫秒）
 */
#define APP_WIFI_TIMEOUT_MS       30000

/**
 * @brief WebSocket 重连间隔（毫秒）
 */
#define APP_WS_RECONNECT_MS       5000

/**
 * @brief DHT11 GPIO 引脚
 */
#define APP_DHT11_GPIO            GPIO_NUM_20

#ifdef __cplusplus
}
#endif

#endif // APP_CONFIG_H