/**
 ****************************************************************************************************
 * @file        emission.h
 * @author      正点原子团队(ALIENTEK)
 * @version     V1.0
 * @date        2023-08-26
 * @brief       RMT红外解码驱动代码
 * @license     Copyright (c) 2020-2032, 广州市星翼电子科技有限公司
 ****************************************************************************************************
 * @attention
 *
 * 实验平台:正点原子 ESP32-S3 开发板
 * 在线视频:www.yuanzige.com
 * 技术论坛:www.openedv.com
 * 公司网址:www.alientek.com
 * 购买地址:openedv.taobao.com
 *
 ****************************************************************************************************
 */

#ifndef __REMOTE_H__
#define __REMOTE_H__

#include <stdio.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_idf_version.h"
#include "freertos/queue.h"
#include "esp_log.h"
#include "driver/rmt_tx.h"
#include "driver/rmt_rx.h"
#include "ir_nec_encoder.h"
#include "lcd.h"


/* 引脚定义 */
#define RMT_RX_PIN                  GPIO_NUM_2  /* 连接RX_PIN的GPIO端口 */
#define RMT_TX_PIN                  GPIO_NUM_8  /* 连接TX_PIN的GPIO端口 */
#define RMT_RESOLUTION_HZ           1000000     /* 1MHz, 1 tick = 1us */
#define RMT_NEC_DECODE_MARGIN       200         /* 判断NEC时序时长的容差值，小于（值+此值），大于（值-此值）为正确 */

/* NEC 协议时序时间，协议头9.5ms 4.5ms 逻辑0两个电平时长，逻辑1两个电平时长，重复码两个电平时长 */
#define NEC_LEADING_CODE_DURATION_0 9000
#define NEC_LEADING_CODE_DURATION_1 4500
#define NEC_PAYLOAD_ZERO_DURATION_0 560
#define NEC_PAYLOAD_ZERO_DURATION_1 560
#define NEC_PAYLOAD_ONE_DURATION_0  560
#define NEC_PAYLOAD_ONE_DURATION_1  1690
#define NEC_REPEAT_CODE_DURATION_0  9000
#define NEC_REPEAT_CODE_DURATION_1  2250

extern uint8_t Floor_Num;

/* 函数声明 */
void emission_init(void);
void example_parse_nec_frame(rmt_symbol_word_t *rmt_nec_symbols, size_t symbol_num);
bool RMT_Rx_Done_Callback(rmt_channel_handle_t channel, const rmt_rx_done_event_data_t *edata, void *user_data);

// void ir_option(uint8_t direction, uint16_t delaytime, rmt_channel_handle_t tx_c, rmt_encoder_handle_t nec_ecd,rmt_transmit_config_t transmit_cfg);
void new_emission_init(void);
void Lift2UpDown(uint8_t direction,uint8_t step);
void toFloor(uint8_t nFloor); // 移动到指定楼层（初始位置默认为1楼）

/* ===== 电梯门控制（继电器模拟按键）===== */
void door_open(void);         // 开门：继电器3(GPIO17)吸合50ms后释放
void door_close(void);        // 关门：继电器4(GPIO18)吸合50ms后释放

/* ===== 电源控制（方案A：持续吸合模式，继电器5@GPIO19串在供电回路）===== */
void power_init(void);        // 上电初始化电源（默认开机持续供电，POWER_BOOT_DEFAULT可配）
void power_on(void);          // 开机：继电器5持续吸合（持续供电）
void power_off(void);         // 关机：继电器5释放（断电）
bool power_is_on(void);       // 查询当前电源状态（true=供电中）

/* ===== 楼层移动异步任务（避免toFloor阻塞TCP recv循环导致断连）===== */
void floor_move_task_start(void);      // 启动楼层移动独立任务（app_init调用一次）
void request_go_floor(uint8_t floor);  // 异步请求楼层移动（非阻塞，供TCP任务调用）
#endif
