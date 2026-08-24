#ifndef DHT11_H
#define DHT11_H

#ifdef __cplusplus
extern "C" {
#endif

#include "driver/gpio.h"
#include "esp_err.h"

typedef struct
{
    gpio_num_t gpio_num;

    uint8_t humidity;

    uint8_t temperature;

} dht11_t;

/**
 * @brief 初始化DHT11
 *
 * @param dev DHT11设备
 * @param gpio GPIO编号
 *
 * @return ESP_OK
 */
esp_err_t dht11_init(dht11_t *dev, gpio_num_t gpio);

/**
 * @brief 读取温湿度
 *
 * @param dev DHT11设备
 *
 * @return ESP_OK
 */
esp_err_t dht11_read(dht11_t *dev);

#ifdef __cplusplus
}
#endif

#endif