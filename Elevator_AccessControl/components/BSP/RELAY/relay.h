/**
 * 继电器控制
 */

#ifndef __RELAY_H_
#define __RELAY_H_

#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

// ====================== 固定配置 ======================
// 控制继电器1
// #define RELAY_GPIO_PIN    GPIO_NUM_10   // 你开发板 P1 排针的 IO10

// void relay_init(void);
// void relay_on(void);
// void relay_off(void);

#include "esp_err.h"
#include "driver/gpio.h"

void relay_init_all(void);          // 初始化所有继电器
void relay_on(int num);             // 继电器吸合
void relay_off(int num);            // 继电器断开
bool relay_is_on(int num);          // 读取继电器控制端口状态

#endif